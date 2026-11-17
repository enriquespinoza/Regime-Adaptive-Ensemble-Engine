# Architecture and ownership boundaries

## Responsibilities

| Component | Owns | Does not own |
| --- | --- | --- |
| Scanner | Candidate universe, eligibility, ranking | Forecast calibration or order approval |
| Technical / Fundamental / TMF engines | Their own versioned predictions and tests | Cross-model allocation |
| Macro snapshot producer | Point-in-time regime probabilities + evidence | Final ensemble weights |
| **Regime-Adaptive Ensemble** | Conditional mixture weights, research forecast, gating and provenance | Security selection, portfolio weights, execution |
| Systematic Trading Research Platform | Scheduling, adapter verification, frozen runs, lineage, promotion gates | Internal expert algorithms |
| Portfolio optimizer | Allocation and risk constraints | Independent forecast construction |
| Execution engine | Approved simulated/paper orders, reconciliation | Research model fitting |
| Decision Review Engine | Retrospective decisions and failure patterns | Mutating frozen forecasts |

## Reproducible run flow

1. Orchestrator identifies a fixed `asset`, `horizon_sessions`, `origin_at`, and evaluation timestamp.
2. Source engines publish immutable forecasts with `model_version`, `available_at`, and `artifact_sha256`. The macro producer publishes `macro_regime_snapshot_v1` with its earliest availability timestamp.
3. The orchestrator independently verifies original artifact bytes against each advertised SHA and stores the raw immutable bundle; **the RAE engine does not currently fetch or verify external artifact bytes**.
4. Reliability artifacts are computed only from outcomes matured and publicly available **before the forecast origin**. The orchestrator checks that those reliability reports actually correspond to held-out observations and have not been retroactively rewritten.
5. RAE-001 enforces structural and temporal contracts; it returns `HOLD_FOR_REVIEW` when evidence is incomplete, stale or late.
6. For eligible input, RAE-001 combines the predeclared regime weights and reliability scores. It caps concentration and rejects excessive weight change versus an optionally supplied previous allocation.
7. Output JSON records bundle and policy hashes; the orchestrator may submit it to independent backtesting, review, optimization, and paper validation as a **new** versioned artifact.

## Safety and inference boundaries

- No look-ahead: `available_at <= evaluation_at`; all experts must share a forecast origin; reliability observation cutoff must be strictly earlier than that origin.
- A positive reliability score and `matured_outcomes >= 30` are *eligibility rules only*. Reliability estimation is not implemented here; submitted scores are not independently substantiated by the evaluator.
- Both policy weights and reliability estimates must be selected before locked holdout periods. Avoid in-sample tuning on the evaluation period.
- Every required expert must participate; no opportunistic exclusion of a poorly performing forecast. A distinct policy version is required to change expert sets or parameters.
- A `HOLD_FOR_REVIEW` or invalid bundle never produces a tradable recommendation.
- This engine neither reads credentials nor calls brokerage APIs. Output does not contain an order schema or approval instruction.

## Known limitations of RAE-001

- Policy values and regime probability fixture are *illustrative*, not trained or calibrated.
- No learned regime classifier, feature ingestion, adaptive training, Bayesian update, or drift adaptation beyond the deterministic stability gate.
- Arithmetic mixtures of expected returns and event probabilities need calibration testing. Expert errors may be correlated, and weighting by standalone reliability can double-count shared macro data.
- Calendar-day freshness thresholds do not replace session-aware publication-lag checks required by a future orchestrator adapter.
- The supplied SHA strings are provenance references only; byte-for-byte evidence verification remains an upstream integration requirement.
