# PR318 boundary/recovery/E2E evidence

Target /tmp/ws2d-pr318-closure, starting HEAD 6b91b86. No product edits by boundary agent.

## Recovery classification
- fix/release-readiness committed branch: `git diff native/integration...fix/release-readiness` empty: category 1, contained.
- release-readiness uncommitted url_safety numeric-IP/trailing-dot normalization, reverse fetch redirect prevention, static route safe-destination guard: category 3 as independently useful security hardening but not newly regressed by PR318, outside this productization acceptance scope; preserve, do not import. Main instructed scope separation.
- release-readiness tierflow heading parsing: category 1/2, integration already has equivalent _REF_FOLLOWERS handling; do not replace.
- release docs/tests: supporting above unrelated changes, preserve outside scope.
- feat/native-product-runtime UI/runtime diff restores vendor driver.js/Mermaid and lacks browser_detect/wsd-diagram/wsd-tour: category 2 older alternate implementation, directly reverses current acceptance criteria; no recovery.
- integrated native/E2b own SVG/tour code already present: category 1.
- no category 3 acceptance-required release/UI/runtime difference identified; recovered files 0.

## Static product runtime boundary
Scope web/src/static/templates/app.py. Inspected subprocess call sites, executable command construction, static assets, script URLs. Product launches Python/internal modules, operating-system `open`/`pgrep`, and user-configured target verification commands; no fixed REA/claude/codex/gh/git/node/npm/npx invocation/fallback dependency found. Python Playwright's packaged driver implementation is not a product requirement for a separately installed Node CLI.
- Required external CLI invocations REA/claude/codex/gh/git: 0.
- Required installed Node/npm/npx runtime invocations: 0.
- Runtime npm install/browser download: 0.
- production CDN scripts: 0.
- tracked static/vendor files: 0; no src/ux/assets remains.
- Mermaid syntax export remains in generators/view-transition; this produces text and is not Mermaid runtime dependency.
- Healing verify_command default is empty. Customer package.json can cause `npm test` suggestion at project_store.py:460; customer-chosen verification command can invoke tools installed for their target repo. No automatic CLI fallback. This is NOT a claim that user-provided commands cannot run npm/git.

## Tests/browser
1. First pytest E2E default bundled-browser selection: SVG 4 passed, 5 setup errors because bundled chromium_headless_shell absent. No install/download performed.
2. Re-execution with existing Chrome --browser-channel chrome: tests/e2e/test_ui_smoke_e2e.py + test_user_guide_scroll_e2e.py: 5 passed in 12.73s.
3. Custom browser real UI probe through product browser_detect.launch_browser on isolated server :8768: 1920x1080 and 1366x768, real restart-tour click, next step, Escape dismiss, WsdDiagram SVG rendering. Both sizes pass. pageerror=0, HTTP errors=0, external requests=0. Server terminated in finally.
4. Screenshot visual inspection at 1366: tour popover/target visible and within viewport; Start->Done SVG labels/connector visible. 1920 screenshots also recorded.

Artifacts:
- /tmp/ws2d-boundary-tests.log (initial environment failure + 4 SVG pass)
- /tmp/ws2d-boundary-e2e.log (5 Chrome E2E pass)
- /tmp/ws2d-boundary-browser.log (browser assertions)
- /tmp/ws2d-tour-1366.png and -1920.png
- /tmp/ws2d-svg-1366.png and -1920.png
- tests/e2e/screenshots/layout_1920x1080.png and layout_1366x768.png

No full verify-ui / all regression executed. Main may decide remaining checks based on all delegated results.

## Independent final diff review
Reviewed Main's quality/feature_contracts.yml diff against implementation and a11y rule diff.
- No feature contract or required_tests category removed. Browser/SVG, Python execution/export, browser unavailable, native a11y, dulwich and native reverse modules are newly registered.
- Removed axe_runner/run_axe/verify_axe_asset and rea_adapter/normalize_static contract pointers target deleted legacy implementation; replacements register run_native_a11y and native evidence/parser modules. Removed asset failure modes are replaced by snapshot_unavailable and rule_not_evaluated_not_passed. Native parse/cancel failure modes replace provider-specific conditions. This is alignment to actual implementation, not removal of tested capability or gate weakening.
- runner.py:98-151 confirms snapshot failure, unimplemented rule, timeout and rule exception remain executed=False / not evaluated paths. No conversion to PASS.
- rules_aria.py fix applies general generic-name prohibition and required-owned-role validation. aria-busy / unresolved aria-owns remain cant_tell; explicit allowed role still passes. Added tests cover the symmetric explicit-role and loading exceptions. No fixture identifiers or axe output copied into runtime.
- No Critical/High finding in reviewed diffs. This scoped review does not certify every preexisting a11y rule.
- Static machine evidence saved /tmp/ws2d-runtime-static-gate.json: 675 scoped files, 19 Python execution sites, 0 forbidden literal executable calls. JSON lists all call sites and explicitly records customer-command/dynamic-command limitations. Manual review of command construction supplements this literal scan.
