# Claude Functional Integrity Rule

Claude must not mark implementation, review, UX evaluation, persona evaluation, or strategy review as complete unless the actual execution path has been verified.

Required verification path:

```text
UI → API → backend route → service/core → output → persistence → error handling → user-visible evidence
```

Do not treat the following as sufficient:

- UI exists
- Button exists
- Test passed
- Persona reviewed
- Strategy reviewed
- Looks usable
- Code looks clean

For every critical or high risk feature, Claude must check:

- happy path
- failure path
- timeout
- cancellation
- auth / login wall
- robots / restriction handling
- partial result / recovery
- logs or evidence
- user-visible error or status

Run these ONLY when the user explicitly requests them (see speed-harness.md H-7).
When not requested, deliver with every unverified item explicitly marked 未実行 / 未検証:

```bash
python scripts/quality_harness.py   # on user request only
make test                           # on user request only
make verify-ui                      # on user request only
```

If any item is unverified, say `未確認` and do not present it as done.

If a development-process failure occurs, use explicit RCA frameworks:

- 5 Whys
- Fishbone
- FMEA
- CAPA
- DoD update

Ad-hoc RCA without a named framework is prohibited.
