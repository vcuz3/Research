import importlib.util
import sys
import unittest
from datetime import date
from pathlib import Path


SCRIPT = Path(__file__).with_name("download_binance_btcusdt_1m.py")
SPEC = importlib.util.spec_from_file_location("downloader", SCRIPT)
downloader = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = downloader
SPEC.loader.exec_module(downloader)


class DownloaderTests(unittest.TestCase):
    def test_requested_months_crosses_year(self):
        self.assertEqual(
            downloader.requested_months(date(2017, 12, 20), date(2018, 2, 2)),
            [date(2017, 12, 1), date(2018, 1, 1), date(2018, 2, 1)],
        )

    def test_days_in_month_slice_is_inclusive(self):
        self.assertEqual(
            downloader.days_in_month_slice(date(2017, 8, 1), date(2017, 8, 17), date(2017, 8, 18)),
            [date(2017, 8, 17), date(2017, 8, 18)],
        )

    def test_timestamp_units_normalize_to_milliseconds(self):
        self.assertEqual(downloader.milliseconds("1502928000000"), (1502928000000, "milliseconds"))
        self.assertEqual(downloader.milliseconds("1735689600000000"), (1735689600000, "microseconds"))

    def test_parquet_schema_has_typed_utc_timestamps(self):
        self.assertEqual(str(downloader.PARQUET_SCHEMA.field("open_time").type), "timestamp[ms, tz=UTC]")
        self.assertEqual(str(downloader.PARQUET_SCHEMA.field("number_of_trades").type), "int64")

    def test_one_second_archive_url_and_interval(self):
        archive = downloader.monthly_archive(date(2020, 1, 1), "1s")
        self.assertTrue(archive.url.endswith("/BTCUSDT/1s/BTCUSDT-1s-2020-01.zip"))
        self.assertEqual(downloader.INTERVAL_MS["1s"], 1_000)


if __name__ == "__main__":
    unittest.main()
