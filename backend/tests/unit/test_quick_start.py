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


# --- _section_file ---

def test_section_file_skips_when_user_says_no(capsys):
    import quick_start
    mock_import = MagicMock()
    with patch("builtins.input", return_value="n"):
        quick_start._section_file("PPF", mock_import, [], 1)
    mock_import.assert_not_called()


def test_section_file_imports_one_file_then_stops():
    import quick_start
    mock_import = MagicMock()
    with patch("builtins.input", side_effect=["y", "/tmp/ppf.csv", "n"]), \
         patch("os.path.isfile", return_value=True):
        quick_start._section_file("PPF", mock_import, [], 1)
    mock_import.assert_called_once_with("/tmp/ppf.csv", 1)


def test_section_file_imports_multiple_files():
    import quick_start
    mock_import = MagicMock()
    with patch("builtins.input", side_effect=["y", "/tmp/a.csv", "y", "/tmp/b.csv", "n"]), \
         patch("os.path.isfile", return_value=True):
        quick_start._section_file("EPF", mock_import, [], 1)
    assert mock_import.call_count == 2
    mock_import.assert_any_call("/tmp/a.csv", 1)
    mock_import.assert_any_call("/tmp/b.csv", 1)


def test_section_file_retries_on_missing_file():
    import quick_start
    mock_import = MagicMock()
    # First path doesn't exist, second does
    with patch("builtins.input", side_effect=["y", "/bad/path.csv", "/tmp/good.csv", "n"]), \
         patch("os.path.isfile", side_effect=[False, True]):
        quick_start._section_file("PPF", mock_import, [], 1)
    mock_import.assert_called_once_with("/tmp/good.csv", 1)


def test_section_file_prompts_member_when_multi_member():
    import quick_start
    mock_import = MagicMock()
    members = [
        {"id": 1, "pan": "AAAAA1111A", "name": "Dhiraj"},
        {"id": 2, "pan": "BBBBB2222B", "name": "Priya"},
    ]
    # answers: has investments? y, member=1, file path, another? n
    with patch("builtins.input", side_effect=["y", "1", "/tmp/epf.pdf", "n"]), \
         patch("os.path.isfile", return_value=True):
        quick_start._section_file("EPF", mock_import, members, None)
    mock_import.assert_called_once_with("/tmp/epf.pdf", 1)


# --- _prompt helper ---

def test_prompt_returns_string_by_default():
    import quick_start
    with patch("builtins.input", return_value="  HDFC FD  "):
        result = quick_start._prompt("Name: ")
    assert result == "HDFC FD"


def test_prompt_casts_to_float():
    import quick_start
    with patch("builtins.input", return_value="7.5"):
        result = quick_start._prompt("Rate: ", cast=float)
    assert result == 7.5


def test_prompt_retries_on_invalid_cast():
    import quick_start
    with patch("builtins.input", side_effect=["abc", "-1", "500000"]):
        result = quick_start._prompt("Amount: ", cast=float, validate=lambda x: x > 0)
    assert result == 500000.0


# --- _add_fd_interactive ---

def test_add_fd_interactive_calls_cmd_add_fd():
    import quick_start
    inputs = [
        "HDFC FD 2024",   # name
        "HDFC",           # bank
        "500000",         # principal
        "7.1",            # rate
        "2024-01-15",     # start
        "2025-01-15",     # maturity
        "QUARTERLY",      # compounding
    ]
    with patch("builtins.input", side_effect=inputs), \
         patch("quick_start.cmd_add_fd") as mock_cmd:
        quick_start._add_fd_interactive(member_id=1)
    mock_cmd.assert_called_once_with(
        "HDFC FD 2024", "HDFC", 500000.0, 7.1,
        "2024-01-15", "2025-01-15", "QUARTERLY", 1
    )


# --- _add_rd_interactive ---

def test_add_rd_interactive_calls_cmd_add_rd():
    import quick_start
    inputs = [
        "SBI RD 2024",   # name
        "SBI",           # bank
        "10000",         # installment
        "6.5",           # rate
        "2024-01-01",    # start
        "2026-01-01",    # maturity
        "QUARTERLY",     # compounding
    ]
    with patch("builtins.input", side_effect=inputs), \
         patch("quick_start.cmd_add_rd") as mock_cmd:
        quick_start._add_rd_interactive(member_id=2)
    mock_cmd.assert_called_once_with(
        "SBI RD 2024", "SBI", 10000.0, 6.5,
        "2024-01-01", "2026-01-01", "QUARTERLY", 2
    )


# --- _add_gold_interactive ---

def test_add_gold_interactive_calls_cmd_add_gold():
    import quick_start
    inputs = [
        "Digital Gold",  # name
        "2023-06-01",    # date
        "10",            # units
        "5800",          # price
    ]
    with patch("builtins.input", side_effect=inputs), \
         patch("quick_start.cmd_add_gold") as mock_cmd:
        quick_start._add_gold_interactive(member_id=1)
    mock_cmd.assert_called_once_with("Digital Gold", "2023-06-01", 10.0, 5800.0, 1)


# --- _add_real_estate_interactive ---

def test_add_real_estate_interactive_calls_cmd_add_real_estate():
    import quick_start
    inputs = [
        "Venezia Flat",   # name
        "7500000",        # purchase amount
        "2020-11-09",     # purchase date
        "12000000",       # current value
        "2024-01-01",     # value date
    ]
    with patch("builtins.input", side_effect=inputs), \
         patch("quick_start.cmd_add_real_estate") as mock_cmd:
        quick_start._add_real_estate_interactive(member_id=3)
    mock_cmd.assert_called_once_with(
        "Venezia Flat", 7500000.0, "2020-11-09", 12000000.0, "2024-01-01", 3
    )


# --- _section_manual ---

def test_section_manual_skips_when_user_says_no():
    import quick_start
    mock_add = MagicMock()
    with patch("builtins.input", return_value="n"):
        quick_start._section_manual("FD", mock_add, [], 1)
    mock_add.assert_not_called()


def test_section_manual_adds_one_then_stops():
    import quick_start
    mock_add = MagicMock()
    with patch("builtins.input", side_effect=["y", "n"]):
        quick_start._section_manual("FD", mock_add, [], 1)
    mock_add.assert_called_once_with(1)


def test_section_manual_adds_multiple():
    import quick_start
    mock_add = MagicMock()
    with patch("builtins.input", side_effect=["y", "y", "n"]):
        quick_start._section_manual("FD", mock_add, [], 1)
    assert mock_add.call_count == 2


def test_section_manual_prompts_member_when_multi_member():
    import quick_start
    mock_add = MagicMock()
    members = [
        {"id": 1, "pan": "AAAAA1111A", "name": "Dhiraj"},
        {"id": 2, "pan": "BBBBB2222B", "name": "Priya"},
    ]
    # has investments? y, member=2, add another? n
    with patch("builtins.input", side_effect=["y", "2", "n"]):
        quick_start._section_manual("FD", mock_add, members, None)
    mock_add.assert_called_once_with(2)
