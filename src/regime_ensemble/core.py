"""RAE-001: deterministic, point-in-time mixture-of-experts evaluation.

This module consumes evidence; it never fetches prices, trains base models,
constructs portfolio weights, or places orders.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any

ENGINE_VERSION = "0.1.0"
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_PROB_TOL = 1e-8


class ContractError(ValueError):
    """A supplied artifact violates its versioned input contract."""


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise ContractError(message)


def _fields(value: Any, required: set[str], optional: set[str], name: str) -> dict:
    _require(isinstance(value, dict), f"{name} must be an object")
    _require(required <= value.keys(), f"{name}: missing {sorted(required - value.keys())}")
    _require(value.keys() <= required | optional, f"{name}: unexpected {sorted(value.keys() - required - optional)}")
    return value


def _text(value: Any, name: str) -> str:
    _require(isinstance(value, str) and bool(value.strip()), f"{name} must be nonempty text")
    return value


def _timestamp(value: Any, name: str) -> datetime:
    _text(value, name)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"{name} must be an ISO-8601 timestamp") from exc
    _require(parsed.tzinfo is not None and parsed.utcoffset() is not None, f"{name} needs a timezone")
    return parsed.astimezone(timezone.utc)


def _number(value: Any, name: str, low: float | None = None, high: float | None = None) -> float:
    _require(type(value) in (float, int) and math.isfinite(value), f"{name} must be finite numeric")
    result = float(value)
    _require(low is None or result >= low, f"{name} below {low}")
    _require(high is None or result <= high, f"{name} above {high}")
    return result


def _positive_int(value: Any, name: str, allow_zero: bool = False) -> int:
    _require(type(value) is int and value >= (0 if allow_zero else 1), f"{name} must be a positive integer")
    return value


def _sha(value: Any, name: str) -> str:
    _require(isinstance(value, str) and bool(_HASH.fullmatch(value)), f"{name} must be lowercase SHA-256 hex")
    return value


def _probabilities(value: Any, keys: set[str], name: str) -> dict[str, float]:
    _require(isinstance(value, dict) and set(value) == keys, f"{name} keys must equal {sorted(keys)}")
    probs = {key: _number(value[key], f"{name}.{key}", 0, 1) for key in sorted(keys)}
    _require(abs(sum(probs.values()) - 1) <= _PROB_TOL, f"{name} must sum to one")
    return probs


def _digest(data: Any) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _validate_policy(policy: Any) -> tuple[dict, set[str], set[str]]:
    policy = _fields(policy, {
        "schema_version", "base_weights", "max_expert_weight", "max_weight_delta",
        "min_matured_outcomes", "max_snapshot_age_days", "max_forecast_age_days",
    }, set(), "policy")
    _require(policy["schema_version"] == "ensemble_policy_v1", "unsupported policy schema")
    weights = policy["base_weights"]
    _require(isinstance(weights, dict) and bool(weights), "policy.base_weights is required")
    regimes = set(weights)
    experts: set[str] | None = None
    for regime, values in weights.items():
        _text(regime, "regime name")
        _require(isinstance(values, dict) and len(values) >= 2, "each regime must configure at least two experts")
        if experts is None:
            experts = set(values)
        _require(set(values) == experts, "every regime must declare the same experts")
        for model, weight in values.items():
            _text(model, "expert name")
            _number(weight, f"base_weights.{regime}.{model}", 0, 1)
        _require(abs(sum(values.values()) - 1) <= _PROB_TOL, f"base_weights.{regime} must sum to one")
    assert experts is not None
    cap = _number(policy["max_expert_weight"], "max_expert_weight", 0, 1)
    _require(cap * len(experts) >= 1 - _PROB_TOL, "expert weight cap makes allocation impossible")
    _number(policy["max_weight_delta"], "max_weight_delta", 0, 1)
    _positive_int(policy["min_matured_outcomes"], "min_matured_outcomes")
    _positive_int(policy["max_snapshot_age_days"], "max_snapshot_age_days")
    _positive_int(policy["max_forecast_age_days"], "max_forecast_age_days")
    return policy, regimes, experts


def _cap_weights(raw: dict[str, float], cap: float) -> dict[str, float]:
    """Water-fill a normalized allocation while respecting hard per-expert caps."""
    remaining = set(raw)
    result = {name: 0.0 for name in raw}
    available = 1.0
    while remaining:
        mass = sum(raw[name] for name in remaining)
        _require(mass > 0, "zero remaining weight mass")
        candidates = {name: available * raw[name] / mass for name in remaining}
        saturated = {name for name, weight in candidates.items() if weight > cap + _PROB_TOL}
        if not saturated:
            for name, weight in candidates.items():
                result[name] = weight
            break
        for name in saturated:
            result[name] = cap
            available -= cap
        remaining -= saturated
        _require(available >= -_PROB_TOL, "weight cap infeasible")
    return {name: result[name] for name in sorted(result)}


def _hold(run: dict, policy: dict, reason: str) -> dict:
    return {
        "schema_version": "ensemble_decision_v1", "engine_version": ENGINE_VERSION,
        "run_id": run["run_id"], "asset": run["asset"],
        "horizon_sessions": run["horizon_sessions"], "evaluation_at": run["evaluation_at"],
        "status": "HOLD_FOR_REVIEW", "reason": reason, "weights": None,
        "expected_return": None, "probability_positive": None,
        "input_sha256": _digest(run), "policy_sha256": _digest(policy),
    }


def evaluate(run: dict, policy: dict) -> dict:
    """Evaluate a frozen, same-asset/same-horizon bundle without future information.

    Invalid schemas raise ContractError. Valid but ineligible evidence yields a
    HOLD_FOR_REVIEW decision, never a silent best-effort forecast.
    """
    policy, regimes, configured_experts = _validate_policy(policy)
    run = _fields(run, {
        "schema_version", "run_id", "evaluation_at", "asset", "horizon_sessions",
        "macro", "forecasts", "reliability",
    }, {"previous_weights"}, "run")
    _require(run["schema_version"] == "ensemble_run_v1", "unsupported run schema")
    _text(run["run_id"], "run_id")
    _text(run["asset"], "asset")
    horizon = _positive_int(run["horizon_sessions"], "horizon_sessions")
    evaluation_at = _timestamp(run["evaluation_at"], "evaluation_at")

    macro = _fields(run["macro"], {
        "schema_version", "observed_at", "available_at", "artifact_sha256", "probabilities",
    }, set(), "macro")
    _require(macro["schema_version"] == "macro_regime_snapshot_v1", "unsupported macro schema")
    _sha(macro["artifact_sha256"], "macro.artifact_sha256")
    observed = _timestamp(macro["observed_at"], "macro.observed_at")
    macro_available = _timestamp(macro["available_at"], "macro.available_at")
    _require(observed <= macro_available, "macro observed after publication")
    probabilities = _probabilities(macro["probabilities"], regimes, "macro.probabilities")
    if macro_available > evaluation_at:
        return _hold(run, policy, "macro snapshot not yet available at evaluation")
    if evaluation_at - observed > timedelta(days=policy["max_snapshot_age_days"]):
        return _hold(run, policy, "macro snapshot is stale")

    forecasts = run["forecasts"]
    reliability = run["reliability"]
    _require(isinstance(forecasts, list) and len(forecasts) == len(configured_experts), "one forecast per configured expert required")
    _require(isinstance(reliability, list) and len(reliability) == len(configured_experts), "one reliability record per expert required")
    by_model: dict[str, dict] = {}
    origin: datetime | None = None
    for forecast in forecasts:
        f = _fields(forecast, {
            "schema_version", "model_id", "model_version", "asset", "horizon_sessions",
            "origin_at", "available_at", "expected_return", "probability_positive", "artifact_sha256",
        }, set(), "forecast")
        _require(f["schema_version"] == "expert_forecast_v1", "unsupported forecast schema")
        model = _text(f["model_id"], "model_id")
        _require(model in configured_experts and model not in by_model, "missing, duplicate, or unconfigured expert")
        _text(f["model_version"], "model_version")
        _require(f["asset"] == run["asset"] and f["horizon_sessions"] == horizon, "expert asset/horizon mismatch")
        _sha(f["artifact_sha256"], "forecast.artifact_sha256")
        _number(f["expected_return"], "expected_return")
        _number(f["probability_positive"], "probability_positive", 0, 1)
        f_origin = _timestamp(f["origin_at"], "forecast.origin_at")
        available = _timestamp(f["available_at"], "forecast.available_at")
        _require(f_origin <= available, "forecast available before its origin")
        if origin is None:
            origin = f_origin
        _require(f_origin == origin, "experts must share a forecast origin timestamp")
        if available > evaluation_at or f_origin > evaluation_at:
            return _hold(run, policy, f"{model} forecast not available at evaluation")
        if evaluation_at - f_origin > timedelta(days=policy["max_forecast_age_days"]):
            return _hold(run, policy, f"{model} forecast is stale")
        by_model[model] = f
    _require(set(by_model) == configured_experts, "forecast coverage mismatch")

    evidence: dict[str, dict] = {}
    for item in reliability:
        r = _fields(item, {
            "schema_version", "model_id", "model_version", "evaluated_through",
            "available_at", "matured_outcomes", "score", "artifact_sha256",
        }, set(), "reliability")
        _require(r["schema_version"] == "expert_reliability_v1", "unsupported reliability schema")
        model = _text(r["model_id"], "reliability.model_id")
        _require(model in by_model and model not in evidence, "missing or duplicate reliability record")
        _require(r["model_version"] == by_model[model]["model_version"], "reliability version mismatch")
        _sha(r["artifact_sha256"], "reliability.artifact_sha256")
        _positive_int(r["matured_outcomes"], "matured_outcomes", allow_zero=True)
        score = _number(r["score"], "reliability.score", 0, 1)
        cutoff = _timestamp(r["evaluated_through"], "reliability.evaluated_through")
        available = _timestamp(r["available_at"], "reliability.available_at")
        _require(cutoff <= available, "reliability evaluated after publication")
        if available > evaluation_at or cutoff >= origin:
            return _hold(run, policy, f"{model} reliability evidence is not point-in-time eligible")
        if r["matured_outcomes"] < policy["min_matured_outcomes"]:
            return _hold(run, policy, f"{model} has insufficient matured outcomes")
        if score <= 0:
            return _hold(run, policy, f"{model} has zero evidence-based reliability")
        evidence[model] = r
    _require(set(evidence) == configured_experts, "reliability coverage mismatch")

    raw = {model: sum(probabilities[regime] * policy["base_weights"][regime][model]
                      for regime in regimes) * evidence[model]["score"]
           for model in sorted(configured_experts)}
    total = sum(raw.values())
    _require(total > 0, "all mixture expert weights are zero")
    weights = _cap_weights(raw, policy["max_expert_weight"])
    prior = run.get("previous_weights")
    if prior is not None:
        previous = _probabilities(prior, configured_experts, "previous_weights")
        if any(abs(weights[m] - previous[m]) > policy["max_weight_delta"] + _PROB_TOL for m in weights):
            return _hold(run, policy, "expert weight drift exceeds stability limit")

    return {
        "schema_version": "ensemble_decision_v1", "engine_version": ENGINE_VERSION,
        "run_id": run["run_id"], "asset": run["asset"],
        "horizon_sessions": horizon, "evaluation_at": run["evaluation_at"],
        "status": "RESEARCH_ONLY", "reason": "eligible evidence; not trading approval",
        "weights": weights,
        "expected_return": sum(weights[m] * by_model[m]["expected_return"] for m in weights),
        "probability_positive": sum(weights[m] * by_model[m]["probability_positive"] for m in weights),
        "contributors": {m: {"model_version": by_model[m]["model_version"],
                             "forecast_sha256": by_model[m]["artifact_sha256"],
                             "reliability_sha256": evidence[m]["artifact_sha256"]}
                         for m in weights},
        "macro_sha256": macro["artifact_sha256"],
        "input_sha256": _digest(run), "policy_sha256": _digest(policy),
    }
