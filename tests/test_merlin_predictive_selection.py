from __future__ import annotations

from merlin_predictive_selection import PredictiveModelSelector, QueryFeatures


def test_get_status_reports_training_samples_without_type_error(
    monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    selector = PredictiveModelSelector()
    selector.training_data = [(QueryFeatures.from_query("write code quickly"), "mistral")]

    status = selector.get_status()

    assert status["model_count"] == len(selector.model_weights)
    assert status["training_samples"] == 1
    assert set(status["model_scores"]) == set(selector.model_weights)
    assert all(isinstance(score, float) for score in status["model_scores"].values())
    assert all(score >= 0.0 for score in status["model_scores"].values())
