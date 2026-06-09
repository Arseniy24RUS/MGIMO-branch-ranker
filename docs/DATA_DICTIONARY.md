# Dashboard Data Dictionary

The dashboard reads static files from `docs/data/`. The canonical payload is `mgimo_dashboard_data.json`; `dashboard_payload.json` is a byte-identical alias for compatibility.

## Public Entities

- Countries: country profile, base recommendation category, map coordinates, current index score, finance, demography, governance, program profile, and management explanation.
- Weight model: seven editable factor weights normalized to 100 percent in the browser; categories remain the original base classification.
- Finance: initial investment, operating expenses, revenue, NPV range, probability of positive NPV, enrollment, and payback.
- Demography series: annual actual values from 2000 and annual forecast values through 2050, with total population and the 15-24 cohort used in executive charts.
- Age-sex pyramid: five-year age groups by sex; only 15-19 and 20-24 are highlighted.
- Program profiles: relative suitability of MGIMO program directions.
- Branch and students navigation: student-demand, branch finance, partner format, program fit, and institutional-check sections.
- Presence and constraints: existing branch presence, countries with project status in preparation, unfriendly countries, Russia as domestic context, and special territories.
- Factor inputs: `factorInputs` before normalization, including demography, education, economy, governance, logistics, partners, finance assumptions, and project-reference flags. `branch_factor_indicator_dictionary_v3.csv/json` records official codes, names, source keys, years, units, weights, and observation status for the seven branch factors.
- Student attraction: separate SAI_MGIMO_V3 rows, component traces, open-data score inputs, observed-flow coverage, and a dashed modelled-potential map layer. Factual flow counts are published only when an open country-level source exists; dashed arrows are modelled potential and are not student-count data.
- Sources: human-readable source and imputation passport used in the interface.

## User-Facing Metrics

- Opportunity index: final branch-priority country score under the current seven-factor weights.
- Market attractiveness: scale and quality of addressable student demand.
- MGIMO fit: program and partner compatibility.
- Political and operational environment: governance, logistics, internet, and operational feasibility.
- Finance feasibility: NPV, payback, uncertainty range, and probability of a positive result.
- Data trace: source key, year, raw value, normalized value, normalization method, input weight, factor weight, and observation status for displayed values.
- Next step: recommended management action for the selected country.

Internal calculation column names can remain in processing code and model review CSVs for reproducibility, but the dashboard UI and executive exports use human-readable labels.
