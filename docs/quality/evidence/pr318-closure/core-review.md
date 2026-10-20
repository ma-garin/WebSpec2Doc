# Core validation PR318

## Residual changes classification
- native/R3 and native/R4 committed changes: category 1 already included (triple-dot diff empty).
- R3 untracked canonical.py/files.py: category 2 older copies; integration has same modules and canonical regression tests passed; no required missing feature established.
- R4 untracked native/__init__.py: category 2 older export facade (15 vs 9 lines), current native package exports production run_static_analysis directly. No retrieval.
- feat/native-product-runtime Reverse/System02/Healing files: category 2 older parallel implementation. Reverse service reintroduces rea_adapter/provider contract; PW retains TS/old runner bridge; integration has direct native AST, Python spec generator/runner, dulwich, REST, common LLM. Untracked native.py/source_maps.py/browser_runtime.py/native_playwright.py are parallel replacements, not patches to current architecture. No AC-essential delta identified. No file copied/deleted.
- Recovery count: 0. Comparison evidence: /tmp/ws2d-core-old.diff. Remaining unreviewed experimental fixture/research files are category 5, preserved.

## Newly discovered and fixed production wiring failures
1. Native dependency JSON used source_node_id/target_node_id/flat line,col; GUI read only old provider location.value/properties. All graph sources became missing; S09 unknown_module. Minimal _dependencies native-shape support preserves source, resolved target, location and external flag. Legacy reader unchanged.
2. pw_spec_api.case registered to registered_cases(), but pw_runner only read __pw_case__/CASES. Actual generated specs executed 0 cases. Runner now resets and consumes production registry, retaining old formats. Regression tests prove repeated and separate specs don't leak registrations, empty remains empty.

Changed by this worker only:
- web/routes/reverse_analysis.py
- web/services/pw_runner.py
- tests/test_reverse_analysis_gui_api.py
- tests/test_pw_runner.py

## Tests
- Baseline targeted native/PW/Healing/LLM: 257 passed, 0 failed, 2.01s.
- CLI/GUI/probe/runtime/canonical wiring: 116 passed, 0 failed, 4.40s (before wiring fixes).
- After native graph fix: GUI/S02 viewpoints/S09 impact 59 passed, 0 failed, 3.15s.
- After runner fix: pw_runner/spec_py_generator/playwright_executor 91 passed, 0 failed, 0.77s.
- Tests overlap; do not sum as unique test count.
- Logs /tmp/ws2d-core-tests.log, /tmp/ws2d-core-wiring-tests.log, /tmp/ws2d-core-fix-tests.log, /tmp/ws2d-core-final-runner-tests.log.

## Same-evidence System01→03→02→09
Actual native parser on real fixture directory -> saved reverse_analysis.json -> production site_evidence() -> production run_probe/store (fake navigator fixture only) -> S02 build_viewpoints -> S09 build_layer.
20 candidates, 4 routes. Three concrete routes reached in fixture; parameter route remains unconfirmed. S02 has 4 route viewpoints, executed=null without run record. S09 3 dependency edges, 2 affected candidates, 4 routes, 6 APIs, 9 test-candidate links. Same route ID/state/location preserved in final S09 output.
Product Truth violations observed in these assertions: 0. Static inferred remains inferred even when reach_status observed. Reached explicitly says function correctness unconfirmed. S09 tests are candidate links, not execution verification.
Evidence /tmp/ws2d-core-flow-result.json. Permanent regression test test_native_evidence_survives_system01_03_02_09.

## Actual generated Python spec execution
Production generate_spec_py -> actual run_playwright -> Python pw_runner -> installed Chrome -> local read-only /settings HTML -> raw/report JSON and HTML.
PASS 1 / FAIL 0 / TOTAL 1, 2842ms. One allowed local request, zero denied. Spec was genuinely generated from candidate/report JSON (not manually decorated test). No runtime download/install/external CLI.
Evidence /tmp/ws2d-core-browser-result.json; script /tmp/ws2d-core-browser.py.
S09 intentionally does not accept execution result records: candidate links only; not extended as new requirement.

## Safe read-only real site native measurement
GET https://docs.python.org/3/_static/documentation_options.js HTTP200, 330 bytes; no form submission/write request. Native complete, 1 module candidate, 0 dependencies, 0.419s total. No dynamic execution. Limitation: no router declaration; no evidence of real site's runtime reach or functional correctness.
Evidence /tmp/ws2d-core-readonly.json.

## LLM / browser behavior
- Existing no-openai-egress contract called all four required entrypoints: Ollama configuration 4 requests only to 127.0.0.1:11434; OpenAI configuration 4 to api.openai.com; mock transport, no paid API requests or local Ollama service required.
- Browser absent tests assert BLOCKED/browser unavailable, pass=fail=0, success false.
- TS execution rejected with export-only reason. Actual Python Chrome execution confirmed above.
- Healing native agents and dulwich tests passed (mock OpenAI/Ollama/REST as appropriate); no live account mutation.
