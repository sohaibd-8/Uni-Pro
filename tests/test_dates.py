from unipro.utils.dates import parse_user_date


def test_parse_jalali_date():
    value = parse_user_date("1405/08/20")
    assert value.year == 2026


def test_parse_gregorian_date():
    value = parse_user_date("2026/11/11")
    assert value.isoformat() == "2026-11-11"
