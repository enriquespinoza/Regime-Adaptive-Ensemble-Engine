"""Synthetic fixtures test mechanisms, not realized financial performance."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

from regime_ensemble import ContractError, evaluate

ROOT = Path(__file__).resolve().parents[1]


class EnsembleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.run = json.loads((ROOT / "examples/synthetic_tmf_run.json").read_text())
        self.policy = json.loads((ROOT / "config/ensemble_policy_v1.json").read_text())

    def test_output_is_deterministic_and_normalized(self) -> None:
        first = evaluate(self.run, self.policy)
        self.assertEqual(first, evaluate(self.run, self.policy))
        self.assertEqual(first["status"], "RESEARCH_ONLY")
        self.assertAlmostEqual(sum(first["weights"].values()), 1)
        self.assertLessEqual(max(first["weights"].values()), 0.65)
        self.assertTrue(0 <= first["probability_positive"] <= 1)
        self.assertEqual(len(first["input_sha256"]), 64)

    def test_inputs_are_not_mutated(self) -> None:
        before = copy.deepcopy((self.run, self.policy))
        evaluate(self.run, self.policy)
        self.assertEqual(before, (self.run, self.policy))

    def test_output_changes_when_reliability_changes(self) -> None:
        before = evaluate(self.run, self.policy)["weights"]
        self.run["reliability"][0]["score"] = 0.9
        after = evaluate(self.run, self.policy)["weights"]
        self.assertGreater(after["technical"], before["technical"])

    def test_output_changes_when_regime_probabilities_change(self) -> None:
        before = evaluate(self.run, self.policy)["weights"]
        self.run["macro"]["probabilities"] = {"risk_on": 1, "risk_off": 0, "transition": 0}
        after = evaluate(self.run, self.policy)["weights"]
        self.assertGreater(after["technical"], before["technical"])

    def test_weight_cap_redistributes_mass(self) -> None:
        self.policy["max_expert_weight"] = 0.4
        got = evaluate(self.run, self.policy)["weights"]
        self.assertAlmostEqual(sum(got.values()), 1)
        self.assertLessEqual(max(got.values()), 0.4 + 1e-9)

    def test_stability_gate_accepts_unchanged_weights(self) -> None:
        self.run["previous_weights"] = evaluate(self.run, self.policy)["weights"]
        self.assertEqual(evaluate(self.run, self.policy)["status"], "RESEARCH_ONLY")

    def test_stability_gate_holds_large_weight_shift(self) -> None:
        self.run["previous_weights"] = {"technical": 0.7, "fundamental": 0.2, "tmf": 0.1}
        self.assertEqual(evaluate(self.run, self.policy)["status"], "HOLD_FOR_REVIEW")

    def test_no_future_macro_information(self) -> None:
        self.run["macro"]["available_at"] = "2026-11-04T12:00:00Z"
        self.assertEqual(evaluate(self.run, self.policy)["status"], "HOLD_FOR_REVIEW")

    def test_no_stale_macro_information(self) -> None:
        self.run["macro"]["observed_at"] = "2026-10-01T20:00:00Z"
        self.assertEqual(evaluate(self.run, self.policy)["status"], "HOLD_FOR_REVIEW")

    def test_no_future_expert_information(self) -> None:
        self.run["forecasts"][0]["available_at"] = "2026-11-04T12:00:00Z"
        self.assertEqual(evaluate(self.run, self.policy)["status"], "HOLD_FOR_REVIEW")

    def test_no_stale_expert_information(self) -> None:
        self.run["evaluation_at"] = "2026-11-07T21:00:00Z"
        self.assertEqual(evaluate(self.run, self.policy)["status"], "HOLD_FOR_REVIEW")

    def test_insufficient_matured_outcomes_holds(self) -> None:
        self.run["reliability"][0]["matured_outcomes"] = 5
        self.assertEqual(evaluate(self.run, self.policy)["status"], "HOLD_FOR_REVIEW")

    def test_reliability_trained_on_origin_holds(self) -> None:
        self.run["reliability"][0]["evaluated_through"] = "2026-10-30T20:00:00Z"
        self.run["reliability"][0]["available_at"] = "2026-10-31T00:00:00Z"
        self.assertEqual(evaluate(self.run, self.policy)["status"], "HOLD_FOR_REVIEW")

    def test_future_reliability_holds(self) -> None:
        self.run["reliability"][0]["available_at"] = "2026-11-04T12:00:00Z"
        self.assertEqual(evaluate(self.run, self.policy)["status"], "HOLD_FOR_REVIEW")

    def test_zero_reliability_holds(self) -> None:
        self.run["reliability"][0]["score"] = 0
        self.assertEqual(evaluate(self.run, self.policy)["status"], "HOLD_FOR_REVIEW")

    def test_mismatched_horizon_rejected(self) -> None:
        self.run["forecasts"][0]["horizon_sessions"] = 10
        with self.assertRaises(ContractError):
            evaluate(self.run, self.policy)

    def test_mismatched_asset_rejected(self) -> None:
        self.run["forecasts"][0]["asset"] = "SPY"
        with self.assertRaises(ContractError):
            evaluate(self.run, self.policy)

    def test_mismatched_model_version_rejected(self) -> None:
        self.run["reliability"][0]["model_version"] = "other-version"
        with self.assertRaises(ContractError):
            evaluate(self.run, self.policy)

    def test_duplicate_expert_rejected(self) -> None:
        self.run["forecasts"][1]["model_id"] = "technical"
        with self.assertRaises(ContractError):
            evaluate(self.run, self.policy)

    def test_different_origin_rejected(self) -> None:
        self.run["forecasts"][1]["origin_at"] = "2026-10-30T19:00:00Z"
        with self.assertRaises(ContractError):
            evaluate(self.run, self.policy)

    def test_invalid_probability_mass_rejected(self) -> None:
        self.run["macro"]["probabilities"]["risk_on"] = 0.3
        with self.assertRaises(ContractError):
            evaluate(self.run, self.policy)

    def test_naive_timestamp_rejected(self) -> None:
        self.run["evaluation_at"] = "2026-11-03T21:00:00"
        with self.assertRaises(ContractError):
            evaluate(self.run, self.policy)

    def test_negative_or_nonfinite_return_rejected(self) -> None:
        self.run["forecasts"][0]["expected_return"] = float("nan")
        with self.assertRaises(ContractError):
            evaluate(self.run, self.policy)

    def test_invalid_cap_rejected(self) -> None:
        self.policy["max_expert_weight"] = 0.3
        with self.assertRaises(ContractError):
            evaluate(self.run, self.policy)

    def test_unexpected_fields_rejected(self) -> None:
        self.run["live_trade_approval"] = True
        with self.assertRaises(ContractError):
            evaluate(self.run, self.policy)

    def test_cli_emits_research_artifact(self) -> None:
        done = subprocess.run([
            sys.executable, "-m", "regime_ensemble.cli", "--input",
            str(ROOT / "examples/synthetic_tmf_run.json"), "--policy",
            str(ROOT / "config/ensemble_policy_v1.json"),
        ], capture_output=True, text=True, check=False)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout)["status"], "RESEARCH_ONLY")


if __name__ == "__main__":
    unittest.main()
