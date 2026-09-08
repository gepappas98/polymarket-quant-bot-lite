from bot.execution_calibration import CALIBRATION_VERSION, calibrate_real_l2
from bot.historical_data import HistoricalL2Snapshot


def rows():
    return [
        HistoricalL2Snapshot(
            "market", "token", 1_000, ( {"price": "0.48", "size": "10"}, ),
            ( {"price": "0.52", "size": "10"}, ),
        ),
        HistoricalL2Snapshot(
            "market", "token", 2_000, ( {"price": "0.49", "size": "8"}, ),
            ( {"price": "0.53", "size": "12"}, ),
        ),
        HistoricalL2Snapshot(
            "market", "token", 3_000, ( {"price": "0.50", "size": "8"}, ),
            ( {"price": "0.54", "size": "12"}, ),
        ),
        HistoricalL2Snapshot(
            "market", "token", 4_000, ( {"price": "0.49", "size": "8"}, ),
            ( {"price": "0.53", "size": "12"}, ),
        ),
    ]


def test_calibration_is_real_and_chronological_out_of_sample():
    result = calibrate_real_l2(rows(), fee_bps=10, slippage_bps=2)
    assert result.fill_model_version == CALIBRATION_VERSION
    assert result.calibration_dataset.startswith("REAL_HISTORICAL_POLYMARKET:")
    assert result.train_count == 2
    assert result.out_of_sample_count == 2
    assert result.maker_fill_range[0] <= result.maker_fill_assumption <= result.maker_fill_range[1]
    assert "Exact queue position is unavailable" in result.assumptions[1]
    assert result.observed_fill_count == 0


def test_calibration_rejects_empty_real_observations():
    import pytest

    with pytest.raises(ValueError, match="at least one Polymarket L2 observation"):
        calibrate_real_l2([], fee_bps=0, slippage_bps=0)
