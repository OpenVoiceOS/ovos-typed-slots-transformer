# ovos-typed-slots-transformer

The reference typed-slots transformer for OVOS. It reads the candidate utterances
and returns the typed-slots map of OVOS-INTENT-1 §5.6: for each type it was asked
for, a list of `{"span": [start, end], "surface", "value"}` entries whose offsets
are half-open code-point positions, so `utterance[start:end] == surface` always
holds. It computes four types with the OVOS parsers — `number` as a JSON number,
`date` as (an RFC 3339 timestamp in the session's zone, taken from `location.tz` and
falling back to the deployment zone), `duration` (seconds) and `color` (a
`{"hex": "#rrggbb", "name"}` pair). It never touches the utterances or the
message context, and every map it returns is checked against the spec before it
leaves the plugin. A type whose entries fail validation is logged and dropped
rather than raised.

The orchestrator loads one typed-slots transformer, hands it the set of types the
registered intents declared, and carries the resulting map to intent matching.
Because the plugin sees every candidate utterance and computes over all of them,
an entry's span indexes the candidate it was read from, and the surface invariant
is what lets a consumer tell which candidate an entry belongs to. The map carries
only types with at least one entry, never an empty list: a key is present exactly
when extraction produced something. A type is therefore absent whether its parser
found no such expression, is not installed, does not cover the session language,
or raised, and a consumer reads absence as "no slots of this type" without having
to distinguish those cases. All three parsers are hard dependencies, so a normal
install can compute all four types, and the lazy per-type imports only matter to
someone who has pruned one of them out.

Language coverage is the parser's, not the plugin's. The number parser refuses a
language it does not implement, so nothing is written for `number` under one. The
date parser instead answers any language by falling back to an English-driven
parser, so its results for an uncovered language are only as good as that
fallback.

## Configuration

Under `typed_slots_transformers` in `mycroft.conf`:

```json
{
  "typed_slots_transformers": {
    "ovos-typed-slots-transformer": {
      "priority": 50,
      "all_types": false
    }
  }
}
```

`all_types` computes all four supported types regardless of what the intents
declared, which is useful when something downstream of intent matching wants the
slots. It costs time on every utterance and is off by default.

## Cost

Extraction is per type and per candidate utterance, so the price is the sum of
the declared types times the number of candidates. On a ten-word English sentence
the date and duration parsers dominate at roughly 8 ms each, numbers cost under
2 ms, and colours are effectively free at well under a millisecond. Asking for all
four costs under 20 ms. Declaring only the types an intent actually needs is the
cheapest thing a skill can do here.
