#!/usr/bin/env python3
"""Convenience entry point for BTCUSDT 1-second klines from 2020 onward."""

from download_binance_btcusdt_1m import main


if __name__ == "__main__":
    raise SystemExit(main(default_interval="1s"))
