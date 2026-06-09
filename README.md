# MGIMO Branch Ranker

Static executive dashboard for prioritizing countries for prospective MGIMO foreign branches, plus a separate student attraction dashboard. The project is designed for GitHub Pages: vanilla JavaScript, local JSON/CSV/GeoJSON, local Leaflet/Plotly assets, no backend, no secrets, and no local absolute paths.

## Online

- Branch ranking dashboard: https://arseniy24rus.github.io/MGIMO-branch-ranker/
- Student attraction dashboard: https://arseniy24rus.github.io/MGIMO-branch-ranker/students.html

## Local Start

```bash
npm ci
npm run start
```

Default local URL: `http://127.0.0.1:4173/`.

On Windows, `npm run start` is the portable release command. The local helper batch file is intentionally not included in this public release package.

## QA

```bash
npm ci
npx playwright install --with-deps
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python src/validate_dashboard_inputs.py
python scripts/validate_demography_v3.py
python scripts/dashboard_review_score.py
python -m pytest -q
npx playwright test
npm run qa
```

`npm run qa` runs the dashboard input validator, pytest suite, and Playwright acceptance tests against the static dashboard. Generated test outputs are ignored and must not be committed.

## Structure

```text
docs/index.html                         GitHub Pages branch ranking dashboard
docs/students.html                      SAI_MGIMO_V3 student attraction dashboard
docs/assets/app.js                      branch dashboard state, map, charts, evidence, exports
docs/assets/students.js                 student attraction dashboard state, map, charts, exports
docs/assets/style.css                   visual system
docs/assets/vendor/                     local Leaflet, Plotly, and flag assets
docs/locales/                           RU/EN UI strings
docs/data/                              static Pages payloads, traces, model outputs, references, GeoJSON
configs/                                model configuration
src/                                    reproducible ranking package and validators
scripts/                                data/model build, review, and quality scripts
data/                                   raw, reference, snapshot, and current output data
tests/                                  pytest and Playwright test suites
.github/workflows/pages.yml             validation and GitHub Pages deployment
```

## Methodological Guardrails

- Every displayed value must trace to source, year, raw value, normalization, and weight.
- Vietnam remains in the common ranking with status `В подготовке`; this status does not add an index bonus.
- Student attraction is a separate `SAI_MGIMO_V3` model, not a copy of branch ranking.
- Fact and modelled potential are visually and textually separated.
- The branch opportunity index uses geometric aggregation, so weak dimensions constrain the final result.

## Deployment

GitHub Actions validates the release on every push to `main` and deploys the `docs/` directory to GitHub Pages only after validation succeeds. Pages must be configured to use GitHub Actions as the source.

This repository intentionally excludes prompts, logs, local review artifacts, legacy snapshots, dependency folders, and generated browser reports.
