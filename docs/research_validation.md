# Research validation and release gates

The engine begins in `EXPERIMENT`. Synthetic tests demonstrate software consistency, **not** predictive accuracy. These gates must be met before any `FROZEN` research release.

| Milestone | Work and acceptance evidence | Status |
| --- | --- | --- |
| RAE-001 | Versioned contracts, deterministic gating/blending, CI, synthetic tests | Foundation implemented |
| RAE-002 | Point-in-time macro regime snapshot producer: source publication lag, probabilistic calibration and provenance | Pending |
| RAE-003 | Adapters for technical, fundamental and applicable TMF forecasts; real artifact hash checks; common horizon and origin | Pending |
| RAE-004 | Audited expert reliability from matured out-of-sample forecasts; explicit benchmark and minimum sample sizes | Pending |
| RAE-005 | Locked expanding/rolling walk-forward splits, no overlap leakage, predeclared static/equal-weight baselines, regime ablations | Pending |
| RAE-006 | Prospective forward log with immutable predictions, realized returns, maturity tracking and changed-only data accumulation audit | Pending |
| RAE-007 | Independent paper-money run plus portfolio-risk, turnover, transaction-cost and execution review | Pending |
| RAE-008 | Orchestrator integration approval; immutable model, policy, dependency versions and validated release tag | Pending |

## Evaluation checklist

- **Data:** count new observations per engine and date, most recent observation age, rejected/stale rows, timestamp availability, source fingerprints; check mixed vendor conventions and TMF OHLCV evidence gate.
- **Maturation:** count forecasts generated, forecasts with matured outcomes, and unresolved future targets for every asset/horizon/expert; prevent repeated/revised origin IDs from being double-counted.
- **Forecast quality:** proper scoring rules (Brier for direction; log loss where valid), calibration/reliability plots, mean absolute return error, confidence intervals, coverage and subgroup performance.
- **Comparisons:** equal-weight, static reliability-only, static regime-only, each individual expert and simple non-ensemble baselines; report improvements **out of sample** by regime and time window.
- **Dependence:** quantify expert residual/error correlation, source overlap, macro double-counting and robustness to regime uncertainty, missing evidence and regime shifts.
- **Statistical uncertainty:** block bootstrap or time-series-aware confidence intervals, sample-size/multiple-testing caveats and no threshold retuning on locked holdout.
- **Operational:** deterministic reproductions, drift and cap tests, version/contract compatibility, immutable prospective records, paper-money reconciliation and explicit human review.

**Promotion:** `IDEA → EXPERIMENT → BACKTESTED → FORWARD_TESTED → PAPER_TRADING → VALIDATED → FROZEN`. No stage is inferred solely from a green CI run. Published claims must identify the exact code commit, policy hash, expert/model versions, date windows, source hashes and acceptance authority.
