from pathlib import Path

from bot.data_boundary import DataSource, worker_boundary


def test_paper_execution_uses_real_input_but_is_simulated():
    metadata = worker_boundary(execution_mode="paper")
    assert metadata["data_source"] == "REAL"
    assert metadata["market_data_source"] == "REAL"
    assert metadata["execution_mode"] == "PAPER"
    assert metadata["is_simulated"] is True
    assert metadata["execution_mode"] != "LIVE"


def test_demo_and_mock_are_distinct_from_real():
    assert DataSource.DEMO.value == "DEMO"
    assert DataSource.MOCK.value == "MOCK"
    assert DataSource.DEMO != DataSource.REAL
    assert DataSource.MOCK != DataSource.REAL


def test_fake_classes_are_confined_to_tests():
    production_roots = [Path("bot"), Path("src")]
    for root in production_roots:
        for path in root.rglob("*"):
            if path.suffix not in {".py", ".ts", ".tsx"} or path.name.endswith(".test.ts"):
                continue
            source = path.read_text(encoding="utf-8")
            assert "class FakeBook" not in source
            assert "class FakeClient" not in source
            assert "class FakeResponse" not in source
