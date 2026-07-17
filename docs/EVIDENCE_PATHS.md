# Recommendation Evidence Paths

## Purpose

Ranked lists alone do not explain why PESI produced a candidate. The evidence-path service reconstructs the available artifact chain for one recommendation without inventing missing links.

## Canonical path

```text
compound pair
→ target enzyme
→ enzyme family
→ pathway/reaction context
→ growth-stage enzyme state
→ known inhibitor class
→ FoodDB source context
```

Each step includes a relationship, source label, and evidence tier.

## Supporting panels

### Enzyme-state reasoning

- Assigned growth stage.
- Target class.
- Trajectory peak, curvature, and critical-transition time.
- Kinetic record count.
- Kinetic, structure, plant-context, pathway-essentiality, and uncertainty signals.

### Scenario selectivity

- Why crop/weed context changes ranking.
- Weed vulnerability proxy.
- Crop vulnerability proxy.
- Selectivity-margin proxy.
- Stage relevance and explicit limitation.

### Pairing rationale

- Functional evidence signals.
- Target-family alignment.
- Pairing support score.
- Explicit statement that pairing is inferred, not measured synergy.

### Compound intelligence

For each compound:

- Why it passed exclusion rules.
- Priority class.
- Phytochemical class.
- Functional-group hits.
- Natural-product and availability signals.
- Hazard, persistence, and intervention-suitability proxies.

### Confidence and limitations

The service separates:

```text
direct evidence
model inference
proxy assumptions
weak or unsupported assumptions
```

### Assay prioritization

Pseudo-lab rows are translated into a relative assay-priority simulation band. This section is never described as a recommended dose or application rate.

## API

```text
GET /api/v1/inference/recommendations/{recommendation_id}/evidence-path
GET /api/v1/inference/targets/{target_id}/state-reasoning
```

## Frontend behavior

Evidence is loaded lazily when the user opens a recommendation or target. The primary results page remains compact. Developer-facing raw tables remain under diagnostics.

## AI interpretation

The DeepSeek request contains the chosen user-facing recommendation, scenario, and complete evidence-path payload. If DeepSeek is unavailable, the deterministic fallback uses the same payload. Neither path may assert evidence not present in the artifacts.
