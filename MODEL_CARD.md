# PESI-KG Model Card

## Model family

PESI-KG is a multi-stage computational system rather than a single estimator. It combines typed KG assembly, feature engineering, enzyme-state trajectory signatures, target-ranking models, rule-based chemical screening, scenario selectivity, typed pair/synergy inference, diversity-constrained portfolio selection, FoodDB identifier normalization, and evidence-path reconstruction.

## Intended use

- Prioritize plant enzyme-state targets for research review.
- Screen inhibitor-like or naturally contextualized compound pairs.
- Compare candidates under crop, weed, and growth-stage scenarios.
- Reconstruct the evidence chain supporting each recommendation.
- Identify food/ingredient occurrence context for matched compounds.
- Generate grounded explanations and scientific reports for assay planning.

## Not intended use

Do not use PESI outputs as pesticide efficacy claims, application-rate advice, formulation instructions, food/extract recommendations, crop-safety determinations, toxicity conclusions, or regulatory submissions without independent validation.

## Major inference layers

1. **Knowledge graph:** typed source records and provenance.
2. **Enzyme-state signature:** stage trajectory, pathway, kinetic, structural, and plant-context signals.
3. **Critical-transition ranking:** target importance and herbicide-target context.
4. **Pair optimization:** chemical compatibility, target fit, portfolio diversity, and penalty terms.
5. **Scenario selectivity:** comparative weed-vulnerability and crop-impact proxies.
6. **Typed pairing/synergy inference:** complementary evidence features; not measured synergy.
7. **Food-source normalization:** identifier-first mapping to FoodDB occurrence records.
8. **Evidence path:** pair → target → family → pathway → stage → inhibitor class → source evidence.
9. **Interpretation:** deterministic or DeepSeek-backed explanation constrained to supplied artifacts.

## Evidence tiers

Each recommendation separates:

- Direct database or curated evidence.
- Model inference.
- Proxy assumptions.
- Weak or unsupported assumptions.

The interface exposes these layers instead of collapsing them into a single confidence statement.

## Pseudo-lab output

The pseudo-lab layer produces a **relative assay-prioritization simulation band**. It is not a dose, concentration recommendation, formulation, or field application rate.

## Food-source model behavior

Compound mapping is identifier-first and deterministic. Food-source rows are emitted only after a compound match and a FoodDB occurrence record. Pair-level shared sources are intersections of the retained source records for both compounds. No source is inferred from chemical class or general phytochemical knowledge alone.

## Validation status

- Existing audit and medium computational portfolio gates are retained.
- FoodDB mapping coverage is reported separately and is not treated as efficacy validation.
- KG augmentation is idempotency-tested.
- Evidence-path, source-context, API, and report sections are covered by automated tests.
- Current package validation: 20 pytest tests, Python compile pass, Svelte check pass, Svelte build pass.

## Limitations

- Rankings depend on upstream data coverage and naming quality.
- Enzyme-state trajectories are computational representations.
- Synergy, selectivity, hazard, persistence, and crop-impact values are screening proxies.
- Food occurrence does not imply bioavailability, extractability, safety, or intervention utility.
- DeepSeek explanations can improve readability but cannot strengthen the underlying evidence.
