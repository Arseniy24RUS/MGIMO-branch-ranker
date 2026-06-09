# Dashboard Methodology

Russian version: [METHODOLOGY_RU.md](METHODOLOGY_RU.md)

The dashboard shows country-level directions for MGIMO MFA Russia international cooperation. It supports executive discussion and does not replace legal, diplomatic, partner, city, or financial due diligence for a concrete location.

## Branch Index

The branch page uses one final opportunity index built from seven factors: market attractiveness, program-industry relevance, legal-partnership context, economic context, financial feasibility, operational feasibility, and strategic talent fit.

The final score is a geometrically weighted index:

```text
Index = 100 * exp(sum(w_i * ln(epsilon + I_i)))
```

Users can edit the seven factor weights; the browser normalizes them to 100 percent and recalculates the map, ranking, selected country card, factor bars, and decomposition. Recommendation categories remain the base classification from the prepared model.

## Statuses And Filters

Russia, unfriendly countries, special territories, and countries with existing MGIMO presence remain visible on the map and in reference panels, but they are not treated as new automatic branch-opening recommendations.

Vietnam remains in the common ranking and map with status `В подготовке`. This status does not add a bonus to the final index, finance model, or any factor. In the data trace, the preparation flag has zero weight and is used only as a governance status.

## Evidence

Every displayed value is tied to source, year, raw value, normalized value, weight, unit, and observation status. Factor tabs read `factor_inputs_long.json`, while `branch_factor_indicator_dictionary_v3.csv/json` records official codes and names for the inputs of the seven branch factors.

Finance values are model calculations and are labelled as calculated. Official or reference statistical series are separated from calculated assumptions in tooltips, tables, and the Data trace panel.

## Demography

The core demographic cohort for both branch and student analytics is population aged 15-24. The mandatory demographic source is UN World Population Prospects 2024 PopulationBySingleAgeSex bulk. Production builds fail if a listed country is not covered.

The age-sex pyramid shows men on the left and women on the right; only age groups 15-19 and 20-24 are highlighted.

## Student Index

The students page uses the separate `SAI_MGIMO_V3` model. It is not a copy of the branch ranking and is not part of the branch-opening formula.

Recommended `SAI_MGIMO_V3` weights:

- `A_YOUTH_OPPORTUNITY` - 0.50;
- `A_OUTBOUND_MOBILITY_UIS` - 0.16;
- `A_LEGAL_PARTNERSHIP_CONTEXT` - 0.12;
- `A_PROGRAM_RELEVANCE` - 0.08;
- `A_AFFORDABILITY_ACCESS` - 0.06;
- `A_DIGITAL_REACH` - 0.04;
- `A_DATAQ` - 0.04.

`A_OUTBOUND_MOBILITY_UIS` uses UNESCO DataHub UIS dataset `uis006`, indicator `MOR.5T8.40510`. Countries without a real UIS row do not receive a SAI score or practical rank.

## Student Flows

Factual country-level MGIMO student flows are shown only when an open country-level source is available. If no such rows exist, the interface states that factual flows are absent.

Dashed arrows on the students map show modelled attraction potential from open indicators. They are not factual MGIMO students, do not show student counts, and are separated from factual flows.
