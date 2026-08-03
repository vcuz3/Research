import numpy as np
import pandas as pd


def simulate_trade(minutes, entry_slot, direction, atr, atr_mult, target, pip_size):
    entry_rows = minutes.loc[minutes.slot == entry_slot]
    if len(entry_rows) != 1 or not np.isfinite(atr) or atr <= 0:
        return None
    entry = float(entry_rows.iloc[0].open)
    stop = entry - direction * atr_mult * atr
    if (direction == 1 and entry >= target) or (direction == -1 and entry <= target):
        return None
    path = minutes.loc[minutes.slot >= entry_slot]
    for row in path.itertuples():
        op, hi, lo = float(row.open), float(row.high), float(row.low)
        if direction == 1:
            if op <= stop:
                return _exit(entry, op, stop, target, row.slot, "stop_gap", direction, pip_size)
            if op >= target:
                return _exit(entry, op, stop, target, row.slot, "target_gap", direction, pip_size)
            stop_hit, target_hit = lo <= stop, hi >= target
        else:
            if op >= stop:
                return _exit(entry, op, stop, target, row.slot, "stop_gap", direction, pip_size)
            if op <= target:
                return _exit(entry, op, stop, target, row.slot, "target_gap", direction, pip_size)
            stop_hit, target_hit = hi >= stop, lo <= target
        if stop_hit:
            reason = "stop_ambiguous" if target_hit else "stop"
            return _exit(entry, stop, stop, target, row.slot, reason, direction, pip_size)
        if target_hit:
            return _exit(entry, target, stop, target, row.slot, "target", direction, pip_size)
    eod = path.loc[path.slot == 1439]
    if len(eod) != 1:
        return None
    return _exit(entry, float(eod.iloc[0].close), stop, target, 1439, "eod", direction, pip_size)


def _exit(entry, exit_price, stop, target, exit_slot, reason, direction, pip_size):
    gross = direction * (exit_price - entry) / pip_size
    risk = abs(entry - stop) / pip_size
    return {
        "entry_price": entry, "exit_price": exit_price, "stop_price": stop,
        "target_price": target, "exit_slot": int(exit_slot), "exit_reason": reason,
        "gross_pips": gross, "initial_risk_pips": risk,
        "gross_r": gross / risk if risk > 0 else np.nan,
    }


def run_variant(raw, bars, eligible, pair, pip_size, target_name, cfg):
    trades, audit = [], []
    minute_groups = {d: g.sort_values("slot") for d, g in raw.groupby("trading_date") if d in eligible}
    bar_groups = {d: g.sort_values("slot_start") for d, g in bars.groupby("trading_date") if d in eligible}
    for date, minutes in minute_groups.items():
        daybars = bar_groups.get(date)
        if daybars is None:
            continue
        asian = minutes.loc[minutes.slot < 420]
        if asian.empty:
            continue
        ah, al = float(asian.high.max()), float(asian.low.min())
        midpoint = (ah + al) / 2.0
        flat_after_slot = 419
        ignored = ambiguous = invalid_geometry = capped = entries = 0
        signal_start = cfg.get("signal_start_slot", 420)
        signal_end = cfg.get("signal_end_slot_start", 1430)
        max_trades = cfg.get("max_trades_per_day")
        candidates = daybars.loc[(daybars.slot_start >= signal_start) & (daybars.slot_start <= signal_end)]
        for signal in candidates.itertuples():
            high_signal = bool(signal.high > ah and signal.rsi > cfg["rsi_high"] and
                               signal.rsi <= cfg.get("rsi_high_cap", np.inf))
            low_signal = bool(signal.low < al and signal.rsi < cfg["rsi_low"] and
                              signal.rsi >= cfg.get("rsi_low_floor", -np.inf))
            if not (high_signal or low_signal):
                continue
            if max_trades is not None and entries >= max_trades:
                capped += 1
                continue
            decision_slot = int(signal.slot_end)
            if decision_slot < flat_after_slot:
                ignored += 1
                continue
            if high_signal and low_signal:
                ambiguous += 1
                continue
            direction = -1 if high_signal else 1
            target = midpoint if target_name == "midpoint" else (al if direction == -1 else ah)
            result = simulate_trade(minutes, int(signal.slot_start + 5), direction,
                                    float(signal.atr), cfg["atr_multiplier"], target, pip_size)
            if result is None:
                invalid_geometry += 1
                continue
            result.update({
                "pair": pair, "trading_date": date, "target": target_name,
                "direction": "long" if direction == 1 else "short",
                "signal_slot": int(signal.slot_start), "entry_slot": int(signal.slot_start + 5),
                "signal_rsi": float(signal.rsi), "signal_atr_pips": float(signal.atr / pip_size),
                "asian_range_pips": float((ah - al) / pip_size),
            })
            trades.append(result)
            entries += 1
            flat_after_slot = int(result["exit_slot"])
        audit.append({"pair":pair, "trading_date":date, "target":target_name,
                      "entries":entries, "ignored_signals":ignored,
                      "capped_signals":capped, "ambiguous_signals":ambiguous,
                      "invalid_geometry":invalid_geometry})
    return pd.DataFrame(trades), pd.DataFrame(audit)
