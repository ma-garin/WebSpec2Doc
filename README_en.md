# WebSpec2Doc

**Automatic QA test-input document generator, from a URL.**

Just point it at the URL of a running web system, and it automatically generates the documents a QA engineer needs to start test design.

> Even in a workplace where the answer is "there's no documentation, so just click around and learn it," this gets you to a state where you can begin test design on day one.

> New here? A plain-language, jargon-free guide is available → [docs/GUIDE_en.md](docs/GUIDE_en.md). 日本語の README は [README.md](README.md)。

---

## Key features

| Feature | Description |
|------|------|
| **Automatic screen-spec generation** | Organizes input fields, constraints, locator candidates, and test conditions per screen |
| **Test-technique recommendation** | Auto-selects equivalence partitioning, boundary value analysis, decision tables, etc. from screen elements |
| **Screen transition diagram/table** | UML transition diagrams (sequence, communication, activity, test-viewpoint map) plus an ISTQB-standard transition table |
| **State exploration** | Automatically opens and records "hidden states" revealed by modals, tabs, accordions, etc. (SPA-aware) |
| **Evidence attachment** | Ties generated specs and test conditions to the actually-measured selectors and screenshot coordinates |
| **Viewpoint management** | Manage test viewpoints with a tree taxonomy and inline editing (3-pane UI, AI suggestions) |
| **Spec drift detection** | Re-crawls and detects diffs (added/removed/changed) from the previous run, analyzing affected screens |
| **Traceability** | Tracks screen → test viewpoint → test scenario relationships |
| **Automatic login** | Enter ID/PASSWORD in the GUI to cover sites requiring authentication |
| **Crawl politeness** | Respects robots.txt, per-origin rate limiting, and destructive-request blocking, enabled by default |
| **ROI dashboard** | Estimates and displays saved effort (hours, yen) from usage records (`/usage`) |
| **Screenshots** | Captures every screen and shows it alongside the spec |

---

## Generated artifacts

| File | Contents |
|---------|------|
| `report.html` | Per-screen specs, test conditions, and screenshots in one report |
| `report.json` | Structured JSON (for automation / CI integration) |
| `spec.xlsx` | Excel spec sheet (for transfer into test-management tools) |
| `screens.md` / `forms.md` | Markdown screen/form listings |
| `transition.mmd` | Screen transition diagram (Mermaid format) |
| `report.pdf` | PDF version of the report |
| `diff_report.html` | Spec-drift diff report (with `--compare`) |
| `screenshots/` | Screenshots of each screen (PNG) |

---

## Setup

```bash
git clone https://github.com/ma-garin/WebSpec2Doc.git
cd WebSpec2Doc

# Use Python 3.12 (3.13 is unsupported because greenlet fails to build)
python3.12 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

pip install -r requirements-dev.txt
python scripts/manage_playwright_runtime.py install
make setup-hooks    # install pre-commit hooks (enables quality gates)
make test           # sanity check
```

Chromium is installed by default under `./.runtime/ms-playwright`, not in the
shared user cache. After updating Playwright, always re-run
`manage_playwright_runtime.py install` inside the same virtual environment.
`make check-runtime` actually launches Chromium to verify the package/browser
combination.

---

## Try it now (bundled demo)

You can experience every feature against the bundled demo site — no external site and no OpenAI API key required.

```bash
make demo       # starts the demo site (8766) and the app (8765) together
# → enter http://127.0.0.1:8766/ into the app's URL field and click "Analyze"
```

The demo flow is in [docs/demo/DEMO_SCRIPT.md](docs/demo/DEMO_SCRIPT.md), and
sample outputs are in [docs/demo/sample_output/](docs/demo/sample_output/).

---

## Using the GUI (recommended)

```bash
python app.py   # → opens http://127.0.0.1:8765
```

### Usable in 4 steps

```
Step 1  Analyze    → enter a URL and click "Analyze". Detects N screens
Step 2  Configure  → choose screens to capture, set login, set diff options
Step 3  Run        → watch progress via live preview during the crawl
Step 4  Report     → review and export artifacts across the tabs
```

#### Sites that require authentication

When the analysis detects a screen that needs login, an ID/PASSWORD form
appears automatically right below the screen list, tagged "login required".
Pressing "Login" logs in automatically and re-analyzes, including the
post-authentication pages. Passwords are discarded immediately after the
session is established and are never stored.

---

## Using the CLI

```bash
# minimal
python src/main.py --url https://example.com

# with HTML report (recommended)
python src/main.py --url https://example.com --format md,html,excel,json

# spec drift detection
python src/main.py --url https://example.com --compare

# save a login session (for post-auth pages)
python src/main.py --login https://example.com/login
python src/main.py --url https://example.com --auth auth.json
```

### CLI options

| Option | Default | Description |
|-----------|-----------|------|
| `--url` | required | URL to crawl |
| `--depth` | `3` | link-following depth |
| `--max-pages` | `50` | maximum pages to crawl |
| `--output` | `./output` | output directory |
| `--format` | `md` | output formats (`md,html,excel,pdf,json`, comma-separated) |
| `--compare` | off | output the diff against the previous snapshot |
| `--auth` | — | crawl using a saved session (auth.json) |

---

## On-prem deployment (venv + systemd)

> **No containers.** In organizations with more than 1,000 employees, Docker
> Desktop becomes a paid license, so this project keeps no dependency on Docker
> (no Dockerfile or compose definitions).

```bash
# create a Python 3.12 venv and install dependencies
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/manage_playwright_runtime.py install --with-deps
.venv/bin/python scripts/manage_playwright_runtime.py check

# by default only local loopback is allowed (external access gets 403)
# to use it from the internal network, specify allowed hosts explicitly
WEBSPEC2DOC_TRUSTED_HOSTS=webspec2doc.internal .venv/bin/python app.py
```

For persistent operation, run it as a systemd service (e.g.
`/etc/systemd/system/webspec2doc.service`):

```ini
[Unit]
Description=WebSpec2Doc
After=network.target

[Service]
WorkingDirectory=/opt/webspec2doc
Environment=WEBSPEC2DOC_TRUSTED_HOSTS=webspec2doc.internal
Environment=PLAYWRIGHT_BROWSERS_PATH=/opt/webspec2doc/.runtime/ms-playwright
ExecStart=/opt/webspec2doc/.venv/bin/python app.py
Restart=on-failure
User=webspec2doc

[Install]
WantedBy=multi-user.target
```

If `WEBSPEC2DOC_TRUSTED_HOSTS` is unset, it stays localhost-only as before.

---

## Documentation

**[docs/README.md](docs/README.md) is the index of all documents** (with current/historical status). Main entry points:

- [Plain-language guide (for non-engineers)](docs/GUIDE_en.md) / [日本語](docs/GUIDE_ja.md)
- [Quick-start guide](docs/userguide.md)
- [Developer handbook](docs/DEVELOPMENT.md)
- [Feature-expansion roadmap](docs/11_機能拡張ロードマップ_現新比較とUX検証.md)
- [Demo script](docs/demo/DEMO_SCRIPT.md)

---

## Tech stack

| Purpose | Library |
|------|-----------|
| Browser automation | [Playwright](https://playwright.dev/python/) |
| Graph processing | [networkx](https://networkx.org/) |
| Transition diagrams (GUI) | [Mermaid](https://mermaid.js.org/) (sequence, communication, activity) |
| Excel output | [openpyxl](https://openpyxl.readthedocs.io/) |
| Web server | [Flask](https://flask.palletsprojects.com/) |
| Testing | pytest + Playwright E2E |

- Python 3.12 (3.13 unsupported due to greenlet build failure)
- GUI port: **8765** (avoids conflict with macOS AirPlay)

---

## Troubleshooting — when local capture fails

Almost always this is caused by an environment mismatch (Python / Playwright /
Chromium / dependency versions). First run the environment doctor for a
one-shot diagnosis:

```bash
make doctor
```

Each FAIL item shows a fix command. Typical causes:

| Symptom | Cause | Fix |
|---|---|---|
| pip install fails / greenlet error at startup | Python 3.13+ (no wheel for playwright 1.44) | recreate the venv with Python 3.12 |
| browser launch fails with `Executable doesn't exist` etc. | Chromium runtime mismatch | `make setup-runtime` |
| capture of 127.0.0.1 or internal IPs is rejected | SSRF protection (on by default) | set `WEBSPEC2DOC_ALLOW_LOCAL=1` |
| specific pages are skipped | login-wall detection / robots Disallow | check the reason in the log (recorded in `audit.jsonl`) |

If the environment is healthy (all PASS) but capture still fails, check the
target site's factors (auth, robots, rate limiting) in
`output/<domain>/audit.jsonl` and the run log.

---

## License

MIT
