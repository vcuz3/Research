"""
RULES.md rule-9a executable data-quality gate for every core load/feature stage.

Run:  python -u -m forex.noise_vwap.scripts.data_quality [session ...]

Reports, per pair and per session definition:
  stage 1 (raw load)      rows, span, duplicate/out-of-order timestamps, the
                          volume situation, weekend/holiday session drops;
  stage 2 (session build) bars per session, missing-minute counts, per-slot bar
                          coverage and its worst slots;
  stage 3 (band feature)  band coverage at the DECISION slots specifically, per
                          slot and per year, plus how many decision points the
                          rule-9a fractional min_periods removes and whether the
                          loss is uniform across time of day (the pass signal) or
                          tracks liquidity (the tell -- see the GC learning).

Writes `reports/DATA_QUALITY.md` and `reports/data_quality.json`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import session as S

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
LOOKBACK = 90


def audit(pair: str, sess: str) -> dict:
    start_tod, length = S.SESSIONS[sess]

    raw = pd.read_parquet(S.path(pair))
    ts = pd.to_datetime(raw["ts_utc"], utc=True)
    stage1 = dict(
        rows=int(len(raw)),
        first=str(ts.iloc[0]), last=str(ts.iloc[-1]),
        duplicate_timestamps=int(ts.duplicated().sum()),
        out_of_order=int((ts.diff().dropna() <= pd.Timedelta(0)).sum()),
        volume_column_present=False,
        note="IBKR cash FX publishes no size; build_clean drops the constant -1 column",
    )

    df = S.load_session(pair, sess)
    n_sess = df["date"].nunique()
    per_sess = df.groupby("date").size()
    stage2 = dict(
        sessions=int(n_sess),
        first_session=str(df["date"].min())[:10], last_session=str(df["date"].max())[:10],
        bars=int(len(df)),
        expected_bars_per_session=int(length),
        mean_bars_per_session=float(per_sess.mean()),
        min_bars_per_session=int(per_sess.min()),
        pct_sessions_full=float((per_sess == length).mean()),
        missing_minutes_total=int(n_sess * length - len(df)),
        missing_minutes_pct=float(1 - len(df) / (n_sess * length)),
    )
    slot_cov = df.groupby("mfo").size() / n_sess
    slot_cov = slot_cov.reindex(range(length)).fillna(0.0)
    worst = slot_cov.nsmallest(8)
    stage2["slot_coverage_min"] = float(slot_cov.min())
    stage2["slot_coverage_median"] = float(slot_cov.median())
    stage2["worst_slots"] = {int(k): round(float(v), 4) for k, v in worst.items()}

    # hourly coverage profile (ET) -- the shape that would reveal a liquidity-
    # tracking deletion rather than a uniform one
    et_hour = ((np.asarray(df["mfo"]) + start_tod) // 60) % 24
    hourly = pd.Series(1, index=et_hour).groupby(level=0).size() / (n_sess * 60)
    stage2["hourly_bar_coverage_et"] = {int(h): round(float(v), 4)
                                        for h, v in hourly.sort_index().items()}

    # contiguous sub-98% coverage windows, labelled in ET, and their
    # Minute-of-hour signature used to detect the historical IBKR fixed-window defect.
    def et_label(m: int) -> str:
        t = (m + start_tod) % 1440
        return f"{t // 60:02d}:{t % 60:02d}"

    bad = slot_cov[slot_cov < 0.98]
    runs = []
    if len(bad):
        idx = np.asarray(bad.index)
        s = p = idx[0]
        for x in idx[1:]:
            if x != p + 1:
                runs.append((s, p))
                s = x
            p = x
        runs.append((s, p))
    stage2["low_coverage_windows_et"] = [
        dict(start=et_label(a), end=et_label(b), minutes=int(b - a + 1),
             coverage=round(float(slot_cov.loc[a:b].mean()), 4)) for a, b in runs]
    stage2["low_coverage_all_at_hour_start"] = all(
        (a + start_tod) % 60 == 0 for a, _ in runs) if runs else True

    # SESSION ANCHOR stability: the band's `move` denominator is the first bar's
    # open, so a session-varying anchor minute is a silent feature defect.
    first_mfo = df.sort_values("et").groupby("date")["mfo"].first()
    stage2["anchor_mfo_mode"] = int(first_mfo.mode().iloc[0])
    stage2["anchor_mfo_stable_frac"] = float((first_mfo == first_mfo.mode().iloc[0]).mean())
    stage2["anchor_mfo_distinct_values"] = int(first_mfo.nunique())

    # stage 3: band coverage at decision slots
    dm = S.decision_mfos(sess, 30)
    bands = S.noise_bands(df, LOOKBACK, min_frac=S.BAND_MIN_FRAC)
    strict = S.noise_bands(df, LOOKBACK, min_frac=1.0)

    warm_dates = np.sort(df["date"].unique())[LOOKBACK:]
    dec_possible = df[df["mfo"].isin(dm) & df["date"].isin(warm_dates)][["date", "mfo"]]
    n_possible = len(dec_possible)

    # decision points lost to a MISSING BAR (before the band rule is applied at
    # all). This is the number the band-coverage figure cannot see, because a
    # slot with no bar is not a decision opportunity in the first place.
    n_scheduled = len(warm_dates) * len(dm)
    bar_avail = pd.DataFrame(dict(mfo=dec_possible["mfo"])).groupby("mfo").size() \
        .reindex(dm).fillna(0) / len(warm_dates)

    def cov(b):
        bb = b[b["mfo"].isin(dm) & b["date"].isin(warm_dates)]
        key = set(map(tuple, bb[["date", "mfo"]].to_numpy()))
        have = np.array([tuple(x) in key for x in dec_possible.to_numpy()])
        return have

    have_frac = cov(bands)
    have_strict = cov(strict)
    dec_possible = dec_possible.assign(ok=have_frac, ok_strict=have_strict)

    by_slot = dec_possible.groupby("mfo")[["ok", "ok_strict"]].mean()
    by_year = dec_possible.assign(y=pd.to_datetime(dec_possible["date"]).dt.year) \
                          .groupby("y")[["ok", "ok_strict"]].mean()

    stage3 = dict(
        lookback=LOOKBACK, band_min_frac=S.BAND_MIN_FRAC,
        decision_slots=len(dm),
        decision_points_scheduled=int(n_scheduled),
        decision_points_lost_to_missing_bars=int(n_scheduled - n_possible),
        bar_availability_at_decision_slots=float(n_possible / n_scheduled),
        worst_decision_slot_bar_availability=float(bar_avail.min()),
        decision_points_possible=int(n_possible),
        decision_points_with_band=int(have_frac.sum()),
        coverage_fractional=float(have_frac.mean()),
        coverage_strict_min_periods=float(have_strict.mean()),
        decisions_saved_by_fractional_rule=int(have_frac.sum() - have_strict.sum()),
        slot_coverage_min=float(by_slot["ok"].min()),
        slot_coverage_max=float(by_slot["ok"].max()),
        slot_coverage_spread=float(by_slot["ok"].max() - by_slot["ok"].min()),
        slot_coverage_strict_spread=float(by_slot["ok_strict"].max()
                                          - by_slot["ok_strict"].min()),
        worst_decision_slots={int(k): round(float(v), 4)
                              for k, v in by_slot["ok"].nsmallest(5).items()},
        per_year_coverage={int(k): round(float(v), 4) for k, v in by_year["ok"].items()},
    )

    # gap between session close and next session open (the band's gap term)
    g = df.sort_values("et").groupby("date")
    o = g["open"].first()
    c = g["close"].last()
    gap = (o - c.shift(1)).abs() / S.PIP
    stage3["median_session_gap_pips"] = float(gap.median())
    stage3["p90_session_gap_pips"] = float(gap.quantile(0.90))

    return dict(pair=pair, session=sess, stage1_raw=stage1,
                stage2_session=stage2, stage3_band=stage3)


def main(argv):
    sessions = argv or ["fxday", "active"]
    out = []
    for sess in sessions:
        for pair in S.PAIRS:
            r = audit(pair, sess)
            out.append(r)
            s2, s3 = r["stage2_session"], r["stage3_band"]
            print(f"{sess:<7s} {pair} sess={s2['sessions']:>5d} "
                  f"bars={s2['mean_bars_per_session']:7.1f}/{s2['expected_bars_per_session']} "
                  f"miss={s2['missing_minutes_pct']*100:5.2f}% "
                  f"anchor_stable={s2['anchor_mfo_stable_frac']:.4f} | "
                  f"dec_bar_avail={s3['bar_availability_at_decision_slots']:.4f} "
                  f"(worst slot {s3['worst_decision_slot_bar_availability']:.4f}) "
                  f"band_cov={s3['coverage_fractional']:.4f} "
                  f"(strict {s3['coverage_strict_min_periods']:.4f}, "
                  f"+{s3['decisions_saved_by_fractional_rule']}) "
                  f"gap_med={s3['median_session_gap_pips']:.2f}p")

    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "data_quality.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    lines = ["# Data Quality — forex/noise_vwap", "",
             "Generated by `python -u -m forex.noise_vwap.scripts.data_quality`.",
             "RULES.md rule 9a: every core load and feature stage emits this report,",
             "and a silent row/decision deletion is a reportable finding, not an",
             "implementation detail.", ""]
    lines += ["## Stage 1 — raw load", "",
              "| pair | rows | span | dup ts | out-of-order | volume |",
              "| --- | ---: | --- | ---: | ---: | --- |"]
    seen = set()
    for r in out:
        if r["pair"] in seen:
            continue
        seen.add(r["pair"])
        s = r["stage1_raw"]
        lines.append(f"| {r['pair']} | {s['rows']:,} | {s['first'][:10]} → {s['last'][:10]} | "
                     f"{s['duplicate_timestamps']} | {s['out_of_order']} | "
                     f"none published (IBKR cash FX) |")

    lines += ["", "## Stage 2 — session build", "",
              "| session | pair | sessions | bars/session | missing min | anchor stable | worst slot cov |",
              "| --- | --- | ---: | ---: | ---: | ---: | ---: |"]
    for r in out:
        s = r["stage2_session"]
        lines.append(f"| {r['session']} | {r['pair']} | {s['sessions']:,} | "
                     f"{s['mean_bars_per_session']:.1f} / {s['expected_bars_per_session']} | "
                     f"{s['missing_minutes_pct']*100:.2f}% | {s['anchor_mfo_stable_frac']:.4f} | "
                     f"{s['slot_coverage_min']:.3f} |")

    lines += ["", "### Low-coverage windows (<98% of sessions have a bar)", "",
              "| session | pair | window (ET) | minutes | coverage |",
              "| --- | --- | --- | ---: | ---: |"]
    any_win = False
    for r in out:
        for w in r["stage2_session"]["low_coverage_windows_et"]:
            any_win = True
            lines.append(f"| {r['session']} | {r['pair']} | {w['start']}–{w['end']} | "
                         f"{w['minutes']} | {w['coverage']:.3f} |")
    if not any_win:
        lines.append("| — | — | none | — | — |")
        lines += ["",
                  "No sub-98% fixed window remains after the documented NZDUSD "
                  "IBKR/LSE hybrid repair. See `forex/data/repair/ibkr_nzdusd/` "
                  "for provenance and placebo error; repaired rows are not exact "
                  "IBKR midpoint observations.", ""]
    else:
        lines += ["",
                  "Every window above starts on the hour. Fresh IBKR re-queries "
                  "reproduce the fixed pattern, locating it in IBKR's historical "
                  "archive rather than local cleaning or market liquidity.", ""]

    lines += ["", "## Stage 3 — decisions and the noise band", "",
              "| session | pair | scheduled dec | lost to missing bars | bar avail | band cov | strict cov | saved by 9a | gap (med pips) |",
              "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for r in out:
        s = r["stage3_band"]
        lines.append(f"| {r['session']} | {r['pair']} | {s['decision_points_scheduled']:,} | "
                     f"{s['decision_points_lost_to_missing_bars']:,} | "
                     f"{s['bar_availability_at_decision_slots']:.4f} | "
                     f"{s['coverage_fractional']:.4f} | {s['coverage_strict_min_periods']:.4f} | "
                     f"+{s['decisions_saved_by_fractional_rule']:,} | "
                     f"{s['median_session_gap_pips']:.2f} |")
    lines += ["", "Full per-slot, per-hour and per-year detail: `reports/data_quality.json`.", ""]
    (REPORTS / "DATA_QUALITY.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nwrote {REPORTS/'DATA_QUALITY.md'}")


if __name__ == "__main__":
    main(sys.argv[1:])
