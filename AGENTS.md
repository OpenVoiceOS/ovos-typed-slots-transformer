# AGENTS.md for ovos-typed-slots-transformer

Reference typed-slots transformer plugin (OVOS-TRANSFORM-1 §3.7): computes the
OVOS-INTENT-1 §5.6 `typed_slots` map for `number`, `date`, `duration` and
`color` using the OVOS parsers.

## Setup
```
uv pip install -e .
```
Runtime deps: `ovos-plugin-manager`, `ovos-spec-tools`, and the three parsers
(`ovos-number-parser`, `ovos-date-parser`, `ovos-color-parser`), all hard. The
lazy per-type imports are a robustness measure for pruned installs, not an
optional-extras scheme.

## Test
```
uv pip install -e ".[test]"
pytest tests
```

## Lint/Typecheck
No project lint config. CI runs `ruff` through the shared workflow.

## Layout
- `ovos_typed_slots_transformer/__init__.py`: `TypedSlotsTransformer`, the four
  `_EXTRACTORS` functions, timezone resolution, per-type validation.
- `ovos_typed_slots_transformer/version.py`: the semver block, bumped by CI.
- `tests/test_plug.py`: pytest cases against the plugin instance.

Entry-point group: `opm.transformer.typed_slots`.

## Conventions (org hard rules)
- Branches: `dev` (work) and `master` (stable). NEVER `main`.
- Never edit `version.py`. gh-automations bumps semver from conventional-commit
  prefixes (`feat:`, `fix:`, `feat!:`).
- Commit identity: `JarbasAi <jarbasai@mailfence.com>`.
- Reference `OpenVoiceOS/gh-automations` reusable workflows at `@dev`.
- No meta-commentary (no history, no dates) in docs, commits, code comments.

## Gotchas
- The plugin MUST NOT alter `utterances` or `Message.context`. It returns a new
  map and nothing else.
- Spans index the candidate they were read from, not a merged string. Consumers
  identify the candidate via `utterance[start:end] == surface`.
- `date` values are serialized with the session zone's offset. A naive anchor
  would silently produce deployment-local times.
- The map holds only types with at least one entry. An empty list is never
  written, so a key is present exactly when extraction produced something.
- Nothing raises out of `transform`, including an unresolvable `location.tz`,
  which falls back to the deployment zone.
- OPM instantiates plugins as `plug(config=...)`, so `priority` is read from the
  plugin's own config section.
