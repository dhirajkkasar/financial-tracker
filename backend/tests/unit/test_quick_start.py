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


# --- _resolve_member ---

def test_resolve_member_creates_member_when_none_exist(capsys):
    with patch("quick_start._api") as mock_api:
        mock_api.side_effect = [
            [],  # GET /members → empty
            {"id": 1, "pan": "ABCDE1234F", "name": "Dhiraj"},  # POST /members
        ]
        with patch("builtins.input", side_effect=["ABCDE1234F", "Dhiraj"]):
            import quick_start
            members, single_id = quick_start._resolve_member()
    assert single_id == 1
    assert len(members) == 1
    assert members[0]["pan"] == "ABCDE1234F"


def test_resolve_member_auto_selects_single_member(capsys):
    with patch("quick_start._api", return_value=[{"id": 2, "pan": "ZZZZZ9999Z", "name": "Priya"}]):
        import quick_start
        members, single_id = quick_start._resolve_member()
    assert single_id == 2
    captured = capsys.readouterr()
    assert "Using: Priya" in captured.out


def test_resolve_member_returns_none_for_multi_member(capsys):
    two_members = [
        {"id": 1, "pan": "AAAAA1111A", "name": "Dhiraj"},
        {"id": 2, "pan": "BBBBB2222B", "name": "Priya"},
    ]
    with patch("quick_start._api", return_value=two_members):
        import quick_start
        members, single_id = quick_start._resolve_member()
    assert single_id is None
    assert len(members) == 2


# --- _ask_member ---

def test_ask_member_returns_correct_member_id():
    members = [
        {"id": 10, "pan": "AAAAA1111A", "name": "Dhiraj"},
        {"id": 20, "pan": "BBBBB2222B", "name": "Priya"},
    ]
    with patch("builtins.input", return_value="2"):
        import quick_start
        result = quick_start._ask_member(members, "EPF")
    assert result == 20


def test_ask_member_retries_on_invalid_input():
    members = [
        {"id": 10, "pan": "AAAAA1111A", "name": "Dhiraj"},
        {"id": 20, "pan": "BBBBB2222B", "name": "Priya"},
    ]
    with patch("builtins.input", side_effect=["0", "abc", "1"]):
        import quick_start
        result = quick_start._ask_member(members, "FD")
    assert result == 10
