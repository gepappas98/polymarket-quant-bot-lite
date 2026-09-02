import builtins
from app.services import ml_service


def test_retrain_insufficient_without_xgboost(monkeypatch):
    original = builtins.__import__
    def missing(name, *args, **kwargs):
        if name == "xgboost":
            raise ImportError
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", missing)
    assert ml_service.retrain_model() == {"status": "skipped", "reason": "xgboost not installed"}
