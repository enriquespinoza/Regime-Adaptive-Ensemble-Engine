# Contracts — version 1

Strict JSON field names are enforced by `src/regime_ensemble/core.py`. All timestamps are ISO-8601 with a timezone. A trading session is an **origin/horizon unit**, not a calendar day.

| Artifact | Required identity / evidence | Core fields |
| --- | --- | --- |
| `ensemble_run_v1` | `run_id`, `asset`, `horizon_sessions`, `evaluation_at` | `macro`, `forecasts[]`, `reliability[]`, optional `previous_weights` |
| `macro_regime_snapshot_v1` | `observed_at`, `available_at`, `artifact_sha256` | `probabilities` keyed by policy regimes, nonnegative and sum to 1 |
| `expert_forecast_v1` | `model_id`, `model_version`, `artifact_sha256` | `asset`, `horizon_sessions`, `origin_at`, `available_at`, `expected_return`, `probability_positive` |
| `expert_reliability_v1` | `model_id`, `model_version`, `artifact_sha256` | `evaluated_through`, `available_at`, `matured_outcomes`, `score` [0,1] |
| `ensemble_policy_v1` | Versioned standalone policy JSON | Regime-to-expert `base_weights`, expert cap, max weight delta, minimum matured outcomes and freshness thresholds |
| `ensemble_decision_v1` | `run_id`, `engine_version`, input and policy SHA-256 | `status`, reason, research weights, expected return, positive-return probability and contributor SHA-256s |

## Compatibility and temporal conditions

- One forecast and one reliability record **per configured expert**; every regime must list the same expert set. Configure a different policy for a different instrument/eligible expert set.
- Experts must match the run's asset, horizon and **exact forecast origin timestamp**. This avoids mixing 1-day and 5-day targets or forecasts made at different decision times.
- Forecast origin precedes its publication; publication must be at or before evaluation. Reliability cutoff precedes its publication **and** precedes the forecast origin. This ensures the reported reliability sample does not include the outcome being forecast.
- Macro snapshot observed time precedes publication, which must be no later than evaluation. Freshness limits apply to the observation age and forecast origin age.
- A prior weight vector, if supplied, must cover the exact expert set, be normalized, and satisfy the predeclared drift gate.
- Every `artifact_sha256` is lowercase 64-character hexadecimal. At present, the engine validates hash **format** and preserves the reference; the orchestrator must check hashes against actual artifact bytes and immutable source snapshots.

## Integration obligations

The orchestrator should pair these contracts with a common `run_id`, immutable artifact store, availability-lagged joins, data-source IDs, release calendars, exact version pins, and a schema registry. Reliability producers must document scoring rules (e.g., out-of-sample Brier skill relative to benchmark), number of matured forecasts, eligible window, exclusions, and versioned source history. A score in [0,1] is accepted as supplied research input; **its statistical meaning is not established by this contract**.

`RESEARCH_ONLY` means eligible for further *research comparison*, never automatic order authorization. `HOLD_FOR_REVIEW` has null prediction and weights, preventing silent fallback. Invalid data raises a validation error; no result should be promoted.
