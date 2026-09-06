import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from ovos_utils.log import LOG

import ovos_typed_slots_transformer as plug
from ovos_typed_slots_transformer import TypedSlotsTransformer

LISBON = ZoneInfo("Europe/Lisbon")
ALL_TYPES = frozenset({"number", "date", "duration", "color"})


class StubSession:
    def __init__(self, lang="en-US", tz="Europe/Lisbon"):
        self.lang = lang
        self.location = {"tz": tz}


def assert_invariant(typed_slots, utterances):
    for entries in typed_slots.values():
        for entry in entries:
            start, end = entry["span"]
            assert any(utt[start:end] == entry["surface"] for utt in utterances)
            assert start <= end


@pytest.fixture
def ovos_caplog(caplog, monkeypatch):
    """`caplog`, wired to see the OVOS logger.

    `LOG.create_logger` caches loggers and turns propagation off on them, so
    pytest's root handler never sees a record unless both are undone.
    """
    create = LOG.create_logger.__func__

    def propagating(cls, name, tostdout=True):
        logger = create(cls, name, tostdout)
        logger.propagate = True
        return logger

    monkeypatch.setattr(LOG, "_loggers", {})
    monkeypatch.setattr(LOG, "create_logger", classmethod(propagating))
    caplog.set_level(logging.DEBUG)
    return caplog


def transform(utterances, declared_types, config=None, session=None):
    plugin = TypedSlotsTransformer(config=config)
    return plugin.transform(utterances, declared_types, session or StubSession())


def test_number_entries_carry_a_json_number():
    utterances = ["turn the volume up to fifty two"]
    slots = transform(utterances, {"number"})
    assert_invariant(slots, utterances)
    values = [e["value"] for e in slots["number"]]
    assert 52 in values
    assert all(isinstance(v, (int, float)) for v in values)


def test_duration_entries_are_seconds():
    utterances = ["set a timer for two hours and thirty minutes"]
    slots = transform(utterances, {"duration"})
    assert_invariant(slots, utterances)
    assert [e["value"] for e in slots["duration"]] == [2 * 3600 + 30 * 60]


def test_color_entries_carry_hex_and_name():
    utterances = ["paint the kitchen light red"]
    slots = transform(utterances, {"color"})
    assert_invariant(slots, utterances)
    assert slots["color"]
    for entry in slots["color"]:
        assert set(entry["value"]) == {"hex", "name"}
        assert len(entry["value"]["hex"]) == 7
        assert entry["value"]["hex"].startswith("#")
        int(entry["value"]["hex"][1:], 16)


def test_date_values_are_rfc3339_in_the_session_zone():
    utterances = ["remind me next friday at 5 pm"]
    slots = transform(utterances, {"date"})
    assert_invariant(slots, utterances)
    assert slots["date"]
    for entry in slots["date"]:
        value = datetime.fromisoformat(entry["value"])
        assert value.utcoffset() == LISBON.utcoffset(value.replace(tzinfo=None))


def test_only_declared_types_are_computed(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("undeclared type was computed")

    for slot_type in ("date", "duration", "color"):
        monkeypatch.setitem(plug._EXTRACTORS, slot_type, boom)
    slots = transform(["ninety nine red balloons"], {"number"})
    assert set(slots) == {"number"}


def test_all_types_config_ignores_the_declared_set():
    utterances = ["five red balloons in two minutes tomorrow"]
    slots = transform(utterances, frozenset(), config={"all_types": True})
    assert set(slots) == ALL_TYPES
    assert_invariant(slots, utterances)


def test_every_candidate_is_covered():
    utterances = ["turn on seven lights", "turn on eleven lights"]
    slots = transform(utterances, {"number"})
    assert_invariant(slots, utterances)
    surfaces = {e["surface"] for e in slots["number"]}
    assert {"seven", "eleven"} <= surfaces


def test_the_input_list_is_untouched():
    utterances = ["nine red balloons"]
    before = list(utterances)
    transform(utterances, ALL_TYPES)
    assert utterances == before
    assert utterances[0] is before[0]


def test_unregistered_declared_type_is_ignored():
    slots = transform(["four thirty"], {"number", "shoe_size"})
    assert set(slots) == {"number"}


def test_a_failing_parser_drops_only_its_own_type(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("parser exploded")

    monkeypatch.setitem(plug._EXTRACTORS, "color", boom)
    slots = transform(["nine red balloons"], {"number", "color"})
    assert set(slots) == {"number"}
    assert slots["number"]


def test_a_type_that_finds_nothing_is_omitted():
    utterances = ["turn the lamp red"]
    slots = transform(utterances, ALL_TYPES)
    assert set(slots) == {"color"}  # no number, date or duration was written
    assert_invariant(slots, utterances)


def test_a_missing_parser_drops_only_its_own_type(monkeypatch):
    def missing(*args, **kwargs):
        raise ImportError("no such parser")

    monkeypatch.setitem(plug._EXTRACTORS, "color", missing)
    monkeypatch.setattr(plug, "_warned", set(), raising=False)
    slots = transform(["nine red balloons"], {"number", "color"})
    assert set(slots) == {"number"}


def test_malformed_entries_are_dropped_not_raised(monkeypatch):
    monkeypatch.setitem(plug._EXTRACTORS, "color",
                        lambda *args, **kwargs: [{"span": [0, 3], "surface": "red"}])
    slots = transform(["red nine"], {"number", "color"})
    assert set(slots) == {"number"}


def test_an_empty_declared_set_computes_nothing():
    assert transform(["nine red balloons"], frozenset()) == {}


def test_the_entry_point_is_discoverable():
    from ovos_plugin_manager.typed_slots_transformers import find_typed_slots_transformer_plugins
    plugins = find_typed_slots_transformer_plugins()
    assert plugins["ovos-typed-slots-transformer"] is TypedSlotsTransformer


def test_supported_types_are_the_four_registered_types():
    from ovos_spec_tools import REGISTERED_TYPES
    assert TypedSlotsTransformer.supported_types == frozenset(REGISTERED_TYPES)


def test_priority_comes_from_the_config_section():
    assert TypedSlotsTransformer().priority == 50
    assert TypedSlotsTransformer(config={"priority": 10}).priority == 10


def test_an_unresolvable_session_zone_falls_back_to_the_deployment_zone(monkeypatch):
    monkeypatch.setattr(plug, "_warned", set(), raising=False)
    monkeypatch.setattr(plug, "Configuration",
                        lambda: {"location": {"timezone": {"code": "Asia/Tokyo"}}})
    utterances = ["nine red balloons tomorrow"]
    session = StubSession(tz="Not/AZone")
    slots = TypedSlotsTransformer().transform(utterances, {"number", "color", "date"},
                                              session)
    assert_invariant(slots, utterances)
    assert slots["number"] and slots["color"]
    assert slots["date"]
    for entry in slots["date"]:
        assert datetime.fromisoformat(entry["value"]).utcoffset() == timedelta(hours=9)


def test_an_unsupported_language_warns_once_and_never_raises(ovos_caplog, monkeypatch):
    monkeypatch.setattr(plug, "_warned", set(), raising=False)
    session = StubSession(lang="xx-XX")
    plugin = TypedSlotsTransformer()

    def warnings():
        return [r.getMessage() for r in ovos_caplog.records
                if r.levelno == logging.WARNING and "'number'" in r.getMessage()]

    plugin.transform(["nine red balloons"], {"number"}, session)
    after_first = warnings()
    assert set(after_first) == {"'number' slots are not supported in 'xx-XX', "
                                "the type will not be computed"}

    plugin.transform(["four red balloons"], {"number"}, session)
    assert warnings() == after_first  # the second call warned again about nothing

    # an unsupported language is a warning, not a failure: no error, no traceback
    assert not [r for r in ovos_caplog.records if r.levelno >= logging.ERROR]
    assert not [r for r in ovos_caplog.records if r.exc_info]


def test_an_unsupported_language_yields_no_types_at_all(monkeypatch):
    monkeypatch.setattr(plug, "_warned", set(), raising=False)
    session = StubSession(lang="xx-XX")
    slots = TypedSlotsTransformer().transform(["nine red balloons"], ALL_TYPES, session)
    # the number parser refuses the language and the other three find nothing,
    # so every type is omitted rather than mapped to an empty list
    assert slots == {}


def test_construction_omits_empty_types_without_the_validator(monkeypatch):
    # `_validated` also drops empty-list types (via spec-tools), so this
    # bypasses it to pin the omission rule in `transform` on its own.
    monkeypatch.setattr(plug.TypedSlotsTransformer, "_validated",
                        staticmethod(lambda typed_slots: typed_slots))
    monkeypatch.setitem(plug._EXTRACTORS, "number", lambda *args, **kwargs: [])
    monkeypatch.setitem(plug._EXTRACTORS, "color",
                        lambda *args, **kwargs: [plug._entry(0, 3, "red", "red")])
    slots = transform(["red"], {"number", "color"})
    assert set(slots) == {"color"}


def test_construction_returns_an_empty_map_without_the_validator(monkeypatch):
    monkeypatch.setattr(plug.TypedSlotsTransformer, "_validated",
                        staticmethod(lambda typed_slots: typed_slots))
    for slot_type in ALL_TYPES:
        monkeypatch.setitem(plug._EXTRACTORS, slot_type, lambda *args, **kwargs: [])
    assert transform(["nine red balloons"], ALL_TYPES) == {}
