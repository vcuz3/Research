import math

from forex.build_macro_events import name_similarity, parse_macro_value, stable_id


def test_parse_macro_value_scalars_and_units():
    assert parse_macro_value("2.3%").value == 2.3
    assert parse_macro_value("2.3%").unit == "percentage_points"
    assert parse_macro_value("256K").value == 256_000
    assert parse_macro_value("A$-0.925B").value == -925_000_000
    assert parse_macro_value("<0.1%").comparator == "<"


def test_parse_macro_value_rejects_compound_auction_result():
    parsed = parse_macro_value("4.68|2.5")
    assert math.isnan(parsed.value)
    assert parsed.status == "compound"


def test_name_similarity_handles_period_noise_but_separates_events():
    assert name_similarity("CPI Flash Estimate y/y", "CPI YoY Flash DEC") > 0.70
    assert name_similarity("Unemployment Rate", "Retail Sales") < 0.30
    assert name_similarity("Retail Sales m/m", "Retail Sales YoY") < 0.30


def test_stable_id_is_deterministic_and_sensitive_to_pair():
    assert stable_id("event", "EURUSD") == stable_id("event", "EURUSD")
    assert stable_id("event", "EURUSD") != stable_id("event", "GBPUSD")
