import pytest
from unittest.mock import patch, MagicMock


# --- _check_db_empty ---

def test_check_db_empty_exits_with_help_when_assets_exist(capsys):
    with patch("quick_start._api", return_value=[{"id": 1}]):
        with pytest.raises(SystemExit) as exc_info:
            import quick_start
            quick_start._check_db_empty()
        assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "existing data" in captured.out
    assert "python cli.py import ppf" in captured.out
    assert "python cli.py add fd" in captured.out


def test_check_db_empty_returns_when_no_assets():
    with patch("quick_start._api", return_value=[]):
        import quick_start
        # Should not raise
        quick_start._check_db_empty()
