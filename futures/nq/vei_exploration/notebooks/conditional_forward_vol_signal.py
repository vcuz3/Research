import marimo

__generated_with = "0.23.15"
app = marimo.App(width="full")


@app.cell
def _():
    from pathlib import Path
    import warnings

    import marimo as mo
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
    from scipy.stats import spearmanr
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline

    return (
        HistGradientBoostingRegressor,
        Path,
        Pipeline,
        SimpleImputer,
        mo,
        np,
        pd,
        plt,
        spearmanr,
        warnings,
    )


@app.cell
def _(mo):
    mo.md(r"""
    # Does the two-feature volatility core contain a conditional signal?

    **Question.** Is the high pooled IC mostly the model reconstructing the
    intraday volatility curve, or can it rank forward 30-minute volatility at a
    fixed decision time better than the causal same-slot median available for free?

    This notebook reproduces the frozen core from EXP-0011:

    - target: forward 30-minute realized volatility divided by its causal
      trailing 90-session same-slot median;
    - features: that same-slot median and `range_rv_15m`;
    - model: untuned histogram gradient boosting on `log1p(target)`;
    - evaluation: annual expanding-window out-of-sample predictions.

    The normalized prediction is converted back to basis points:

    \[
    \widehat{RV}_{30m} = \widehat{RV}_{30m,\,norm}
    \times \operatorname{median}_{90,\,same\ slot}(RV_{30m}).
    \]

    ## Predeclared diagnostic

    The core survives as a **conditional signal** only if both NQ and ES have:

    1. positive log-MSE skill versus the same-slot median;
    2. a positive within-slot IC improvement whose 90% session-block interval is
       above zero; and
    3. a positive FWL residual correlation whose 90% interval is above zero after
       residualising `log(fwd_rv)` and `log(forecast)` on `log(slot median)`.

    The stricter slot-by-weekday view directly removes comparisons such as Tuesday
    morning versus Friday afternoon. It is a robustness diagnostic, not an extra
    promotion gate. All history through 2026-07-14 is already consumed; this is a
    decisive diagnostic of the existing programme, not fresh holdout evidence.
    """)
    return


@app.cell
def _(mo):
    start_year = mo.ui.number(2016, 2026, value=2016, step=1, label="First OOS year")
    end_year = mo.ui.number(2016, 2026, value=2026, step=1, label="Last OOS year")
    max_iter = mo.ui.dropdown(
        options={"Full / frozen (220 trees)": 220, "Smoke test (40 trees)": 40},
        value="Full / frozen (220 trees)",
        label="Model run",
    )
    bootstrap_draws = mo.ui.dropdown(
        options={"Fast (100 draws)": 100, "Default (300 draws)": 300, "Thorough (1,000 draws)": 1000},
        value="Default (300 draws)",
        label="Session bootstrap",
    )
    run_analysis = mo.ui.run_button(label="Build data and run conditional test")
    mo.vstack(
        [
            mo.hstack([start_year, end_year, max_iter, bootstrap_draws], justify="start"),
            run_analysis,
            mo.md(
                "The full setting matches EXP-0011. Smoke mode is only a plumbing check "
                "and should not be used for the verdict."
            ),
        ]
    )
    return bootstrap_draws, end_year, max_iter, run_analysis, start_year


@app.cell
def _(
    HistGradientBoostingRegressor,
    Path,
    Pipeline,
    SimpleImputer,
    np,
    pd,
    spearmanr,
    warnings,
):
    warnings.filterwarnings(
        "ignore",
        message="Could not find the number of physical cores.*",
        category=UserWarning,
        module="joblib.*",
    )
    def _find_project_dir():
        cwd = Path.cwd().resolve()
        candidates = [cwd, *cwd.parents, cwd / "futures" / "nq" / "vei_exploration"]
        for candidate in candidates:
            if candidate.name == "vei_exploration" and (candidate / "MEMORY.md").exists():
                return candidate
        raise FileNotFoundError(
            "Could not locate futures/nq/vei_exploration. Start Marimo from the "
            "Research workspace or from inside the project."
        )

    PROJECT_DIR = _find_project_dir()
    DATA_DIR = PROJECT_DIR.parent / "data"
    INSTRUMENTS = ("NQ", "ES")
    HORIZON_MIN = 30
    SLOT_LOOKBACK = 90
    SLOT_MIN_OBS = 60
    RANDOM_SEED = 20260730
    DECISION_MFOS = tuple(
        m for m in range(29, 390, 30) if m + HORIZON_MIN + 1 < 390
    )

    def _target_paths_for_session(group):
        opens = group["open"].to_numpy(float)
        mfo = group["mfo"].to_numpy(int)
        symbols = group["symbol"].astype(str).to_numpy()
        rolls = group["is_roll"].fillna(False).to_numpy(bool)
        rv_bp = np.full(len(group), np.nan)
        for p in range(len(group)):
            end = p + HORIZON_MIN + 1
            if (
                end >= len(group)
                or mfo[p + 1] != mfo[p] + 1
                or mfo[end] != mfo[p] + HORIZON_MIN + 1
            ):
                continue
            if np.any(rolls[p + 1 : end + 1]) or np.any(
                symbols[p + 1 : end + 1] != symbols[p + 1]
            ):
                continue
            path = np.diff(np.log(opens[p + 1 : end + 1]))
            if len(path) == HORIZON_MIN and np.all(np.isfinite(path)):
                rv_bp[p] = 1e4 * np.sqrt(np.sum(path * path))
        return pd.Series(rv_bp, index=group.index, name="fwd_rv_bp")

    def _clock_label(mfo, offset=0):
        minutes = 9 * 60 + 30 + int(mfo) + int(offset)
        return f"{minutes // 60:02d}:{minutes % 60:02d}"

    def build_decision_frame(instrument):
        path = DATA_DIR / f"{instrument}_1m_clean.parquet"
        required = ["ts_utc", "symbol", "open", "high", "low", "close", "is_roll"]
        raw = pd.read_parquet(path, columns=required)
        raw["ts_utc"] = pd.to_datetime(raw.ts_utc, utc=True)
        duplicate_ts = int(raw.ts_utc.duplicated().sum())
        out_of_order = int((raw.ts_utc.diff().dropna() < pd.Timedelta(0)).sum())
        raw = raw.sort_values("ts_utc").reset_index(drop=True)

        et = raw.ts_utc.dt.tz_convert("America/New_York")
        raw["calendar_date"] = et.dt.tz_localize(None).dt.normalize()
        raw["tod"] = et.dt.hour * 60 + et.dt.minute
        link_gap = raw.ts_utc.diff().ne(pd.Timedelta(minutes=1))
        symbol_change = raw.symbol.astype(str).ne(raw.symbol.astype(str).shift(1))
        bad_link = link_gap | symbol_change | raw.is_roll.fillna(False)
        raw["range_log"] = np.log(raw.high / raw.low).mask(bad_link)
        raw["range_rv_15m"] = np.sqrt(
            raw.range_log.pow(2).rolling(15, min_periods=15).sum()
        )

        rth = raw.loc[(raw.tod >= 570) & (raw.tod < 960)].copy()
        rth["sdate"] = rth.calendar_date
        rth["mfo"] = rth.tod - 570
        rth = rth.sort_values(["sdate", "mfo"]).reset_index(drop=True)
        rth["rth_pos"] = np.arange(len(rth))
        daily = rth.groupby("sdate").agg(
            rth_rows=("mfo", "size"),
            rth_unique=("mfo", "nunique"),
            roll_rows=("is_roll", "sum"),
        )

        targets = rth.groupby("sdate", group_keys=False).apply(
            _target_paths_for_session
        )
        if isinstance(targets.index, pd.MultiIndex):
            targets.index = targets.index.droplevel(0)
        rth["fwd_rv_bp"] = targets.sort_index()

        d = rth.loc[rth.mfo.isin(DECISION_MFOS)].copy()
        d["fwd_rv_bp_slot_median90"] = d.groupby("mfo")["fwd_rv_bp"].transform(
            lambda s: s.shift(1).rolling(
                SLOT_LOOKBACK, min_periods=SLOT_MIN_OBS
            ).median()
        )
        d["fwd_rv_bp_norm"] = d.fwd_rv_bp / d.fwd_rv_bp_slot_median90.replace(
            0, np.nan
        )
        d["instrument"] = instrument
        d["year"] = d.sdate.dt.year
        d["weekday"] = d.sdate.dt.day_name().str[:3]
        d["decision_et"] = d.mfo.map(lambda x: _clock_label(x, 0))
        d["forecast_start_et"] = d.mfo.map(lambda x: _clock_label(x, 1))

        eligible = d.dropna(
            subset=["range_rv_15m", "fwd_rv_bp", "fwd_rv_bp_slot_median90"]
        )
        chosen = eligible.sample(min(80, len(eligible)), random_state=RANDOM_SEED)
        range_errors = []
        target_errors = []
        median_errors = []
        exact_clock = []
        nonoverlap = []
        for row in chosen.itertuples(index=False):
            p = int(row.rth_pos)
            look = rth.iloc[p - 14 : p + 1]
            future = rth.iloc[p + 1 : p + HORIZON_MIN + 2]
            reference_range = np.sqrt(np.square(np.log(look.high / look.low)).sum())
            reference_target = 1e4 * np.sqrt(
                np.square(np.diff(np.log(future.open.to_numpy(float)))).sum()
            )
            history = d.loc[
                (d.mfo == row.mfo) & (d.sdate < row.sdate), "fwd_rv_bp"
            ].tail(SLOT_LOOKBACK)
            reference_median = (
                history.median() if history.notna().sum() >= SLOT_MIN_OBS else np.nan
            )
            range_errors.append(abs(reference_range - row.range_rv_15m))
            target_errors.append(abs(reference_target - row.fwd_rv_bp))
            median_errors.append(
                abs(reference_median - row.fwd_rv_bp_slot_median90)
            )
            exact_clock.append(
                len(future) == HORIZON_MIN + 1
                and future.sdate.nunique() == 1
                and future.mfo.iloc[0] == row.mfo + 1
                and future.mfo.iloc[-1] == row.mfo + HORIZON_MIN + 1
            )
            nonoverlap.append(look.ts_utc.max() < future.ts_utc.min())

        quality = {
            "instrument": instrument,
            "raw_rows": len(raw),
            "rth_rows": len(rth),
            "sessions": d.sdate.nunique(),
            "first_session": d.sdate.min(),
            "last_session": d.sdate.max(),
            "duplicate_ts": duplicate_ts,
            "out_of_order_ts": out_of_order,
            "timestamp_or_contract_breaks": int(bad_link.sum()),
            "incomplete_rth_sessions": int(daily.rth_unique.ne(390).sum()),
            "roll_rows": int(raw.is_roll.fillna(False).sum()),
            "decision_rows": len(d),
            "missing_target": int(d.fwd_rv_bp.isna().sum()),
            "missing_range_feature": int(d.range_rv_15m.isna().sum()),
            "missing_slot_median": int(d.fwd_rv_bp_slot_median90.isna().sum()),
        }
        audit = {
            "instrument": instrument,
            "sampled_rows": len(chosen),
            "max_range_error": float(np.nanmax(range_errors)),
            "max_target_error_bp": float(np.nanmax(target_errors)),
            "max_slot_median_error_bp": float(np.nanmax(median_errors)),
            "exact_future_clock": bool(np.all(exact_clock)),
            "feature_target_nonoverlap": bool(np.all(nonoverlap)),
        }
        coverage = (
            d.groupby(["instrument", "year", "mfo"], as_index=False)
            .agg(
                rows=("ts_utc", "size"),
                target_valid=("fwd_rv_bp", "count"),
                range_valid=("range_rv_15m", "count"),
                median_valid=("fwd_rv_bp_slot_median90", "count"),
            )
        )
        for column in ["target_valid", "range_valid", "median_valid"]:
            coverage[column.replace("_valid", "_coverage")] = coverage[column] / coverage.rows

        keep = [
            "instrument",
            "ts_utc",
            "sdate",
            "year",
            "weekday",
            "mfo",
            "decision_et",
            "forecast_start_et",
            "fwd_rv_bp",
            "fwd_rv_bp_norm",
            "fwd_rv_bp_slot_median90",
            "range_rv_15m",
        ]
        return d[keep].reset_index(drop=True), quality, audit, coverage

    def make_model(seed, iterations):
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy="median", add_indicator=True)),
                (
                    "model",
                    HistGradientBoostingRegressor(
                        max_iter=iterations,
                        learning_rate=0.04,
                        max_leaf_nodes=15,
                        l2_regularization=1.0,
                        random_state=seed,
                    ),
                ),
            ]
        )

    def walkforward_core(frame, first_year, last_year, iterations):
        features = ["fwd_rv_bp_slot_median90", "range_rv_15m"]
        parts = []
        for year in range(first_year, last_year + 1):
            train = frame.loc[frame.year < year].dropna(subset=["fwd_rv_bp_norm"])
            test = frame.loc[frame.year == year].dropna(
                subset=["fwd_rv_bp_norm", "fwd_rv_bp_slot_median90"]
            )
            if len(train) < 1000 or len(test) < 100:
                continue
            model = make_model(RANDOM_SEED + year, iterations)
            model.fit(
                train[features], np.log1p(train.fwd_rv_bp_norm.clip(lower=0))
            )
            forecast_ratio = np.expm1(model.predict(test[features])).clip(min=1e-8)
            part = test[
                [
                    "instrument",
                    "ts_utc",
                    "sdate",
                    "year",
                    "weekday",
                    "mfo",
                    "decision_et",
                    "forecast_start_et",
                    "fwd_rv_bp",
                    "fwd_rv_bp_norm",
                    "fwd_rv_bp_slot_median90",
                    "range_rv_15m",
                ]
            ].copy()
            part["forecast_ratio"] = forecast_ratio
            part["forecast_bp"] = (
                part.forecast_ratio * part.fwd_rv_bp_slot_median90
            )
            parts.append(part)
        if not parts:
            return pd.DataFrame()
        return pd.concat(parts, ignore_index=True)

    def safe_spearman(x, y):
        x = np.asarray(x, float)
        y = np.asarray(y, float)
        mask = np.isfinite(x) & np.isfinite(y)
        if mask.sum() < 3 or np.unique(x[mask]).size < 2 or np.unique(y[mask]).size < 2:
            return np.nan
        return float(spearmanr(x[mask], y[mask]).statistic)

    def safe_corr(x, y):
        x = np.asarray(x, float)
        y = np.asarray(y, float)
        mask = np.isfinite(x) & np.isfinite(y)
        if mask.sum() < 3 or np.std(x[mask]) == 0 or np.std(y[mask]) == 0:
            return np.nan
        return float(np.corrcoef(x[mask], y[mask])[0, 1])

    def grouped_rank_ic(frame, groups, x, y, min_group_n=20):
        columns = list(dict.fromkeys(list(groups) + [x, y]))
        work = frame[columns].replace([np.inf, -np.inf], np.nan).dropna().copy()
        grouped = work.groupby(list(groups), observed=True)
        sizes = grouped[x].transform("size")
        work = work.loc[sizes >= min_group_n].copy()
        if len(work) < 3:
            return np.nan
        grouped = work.groupby(list(groups), observed=True)
        xr = grouped[x].rank(method="average", pct=True)
        yr = grouped[y].rank(method="average", pct=True)
        xr = xr - xr.groupby([work[g] for g in groups]).transform("mean")
        yr = yr - yr.groupby([work[g] for g in groups]).transform("mean")
        return safe_corr(xr, yr)

    def fwl_log_diagnostic(frame):
        work = frame[
            ["fwd_rv_bp", "forecast_bp", "fwd_rv_bp_slot_median90"]
        ].replace([np.inf, -np.inf], np.nan).dropna()
        values = np.log(work.to_numpy(float).clip(min=1e-12))
        log_y, log_forecast, log_median = values.T
        design = np.column_stack([np.ones(len(work)), log_median])

        def residualize(value):
            beta = np.linalg.lstsq(design, value, rcond=None)[0]
            return value - design @ beta

        y_resid = residualize(log_y)
        forecast_resid = residualize(log_forecast)
        corr = safe_corr(y_resid, forecast_resid)
        slope = float(
            np.dot(forecast_resid, y_resid)
            / np.dot(forecast_resid, forecast_resid)
        )
        return corr, corr * corr, slope

    def metric_bundle(frame):
        work = frame.replace([np.inf, -np.inf], np.nan).dropna(
            subset=[
                "fwd_rv_bp",
                "fwd_rv_bp_norm",
                "forecast_bp",
                "forecast_ratio",
                "fwd_rv_bp_slot_median90",
            ]
        )
        y = work.fwd_rv_bp.to_numpy(float)
        forecast = work.forecast_bp.to_numpy(float)
        median = work.fwd_rv_bp_slot_median90.to_numpy(float)
        log_y = np.log(np.maximum(y, 1e-12))
        log_forecast = np.log(np.maximum(forecast, 1e-12))
        log_median = np.log(np.maximum(median, 1e-12))
        fwl_corr, fwl_r2, fwl_slope = fwl_log_diagnostic(work)
        ratio_log_corr = safe_corr(log_y - log_median, log_forecast - log_median)
        median_log_mse = float(np.mean(np.square(log_y - log_median)))
        forecast_log_mse = float(np.mean(np.square(log_y - log_forecast)))
        pooled_log_corr = safe_corr(log_y, log_forecast)
        baseline_log_corr = safe_corr(log_y, log_median)
        within_model = grouped_rank_ic(work, ["mfo"], "forecast_bp", "fwd_rv_bp")
        within_median = grouped_rank_ic(
            work, ["mfo"], "fwd_rv_bp_slot_median90", "fwd_rv_bp"
        )
        weekday_model = grouped_rank_ic(
            work, ["mfo", "weekday"], "forecast_bp", "fwd_rv_bp"
        )
        weekday_median = grouped_rank_ic(
            work,
            ["mfo", "weekday"],
            "fwd_rv_bp_slot_median90",
            "fwd_rv_bp",
        )
        return {
            "n": len(work),
            "pooled_raw_ic_model": safe_spearman(forecast, y),
            "pooled_raw_ic_median": safe_spearman(median, y),
            "pooled_normalized_ic": safe_spearman(
                work.forecast_ratio, work.fwd_rv_bp_norm
            ),
            "within_slot_ic_model": within_model,
            "within_slot_ic_median": within_median,
            "within_slot_ic_delta": within_model - within_median,
            "within_slot_ratio_ic": grouped_rank_ic(
                work, ["mfo"], "forecast_ratio", "fwd_rv_bp_norm"
            ),
            "slot_weekday_ic_model": weekday_model,
            "slot_weekday_ic_median": weekday_median,
            "slot_weekday_ic_delta": weekday_model - weekday_median,
            "pooled_log_r2_model": pooled_log_corr * pooled_log_corr,
            "pooled_log_r2_median": baseline_log_corr * baseline_log_corr,
            "fwl_resid_corr": fwl_corr,
            "fwl_resid_r2": fwl_r2,
            "fwl_resid_slope": fwl_slope,
            "log_ratio_corr": ratio_log_corr,
            "log_ratio_r2": ratio_log_corr * ratio_log_corr,
            "forecast_log_mse": forecast_log_mse,
            "median_log_mse": median_log_mse,
            "log_mse_skill": 1.0 - forecast_log_mse / median_log_mse,
            "raw_mae_model_bp": float(np.mean(np.abs(y - forecast))),
            "raw_mae_median_bp": float(np.mean(np.abs(y - median))),
        }

    def bootstrap_metrics(frame, draws, seed):
        grouped_indices = [
            np.asarray(indices, dtype=int)
            for indices in frame.groupby("sdate", sort=False).indices.values()
        ]
        rng = np.random.default_rng(seed)
        metric_names = [
            "within_slot_ic_delta",
            "slot_weekday_ic_delta",
            "fwl_resid_corr",
            "fwl_resid_r2",
            "log_mse_skill",
        ]
        sampled = {name: np.empty(draws) for name in metric_names}
        for draw in range(draws):
            selections = rng.integers(0, len(grouped_indices), len(grouped_indices))
            index = np.concatenate([grouped_indices[i] for i in selections])
            result = metric_bundle(frame.iloc[index])
            for name in metric_names:
                sampled[name][draw] = result[name]
        rows = []
        point = metric_bundle(frame)
        for name in metric_names:
            lo, hi = np.nanpercentile(sampled[name], [5, 95])
            rows.append(
                {
                    "metric": name,
                    "point": point[name],
                    "ci_90_lo": lo,
                    "ci_90_hi": hi,
                }
            )
        return pd.DataFrame(rows)

    def detail_table(frame, groups):
        rows = []
        for keys, group in frame.groupby(groups, observed=True):
            if not isinstance(keys, tuple):
                keys = (keys,)
            row = dict(zip(groups, keys))
            row.update(
                {
                    "n": len(group),
                    "model_raw_ic": safe_spearman(group.forecast_bp, group.fwd_rv_bp),
                    "median_raw_ic": safe_spearman(
                        group.fwd_rv_bp_slot_median90, group.fwd_rv_bp
                    ),
                    "conditional_ratio_ic": safe_spearman(
                        group.forecast_ratio, group.fwd_rv_bp_norm
                    ),
                }
            )
            row["model_minus_median_ic"] = row["model_raw_ic"] - row["median_raw_ic"]
            rows.append(row)
        return pd.DataFrame(rows)

    return (
        DATA_DIR,
        INSTRUMENTS,
        RANDOM_SEED,
        bootstrap_metrics,
        build_decision_frame,
        detail_table,
        metric_bundle,
        walkforward_core,
    )


@app.cell
def _(DATA_DIR, INSTRUMENTS, build_decision_frame, mo, pd, run_analysis):
    mo.stop(
        not run_analysis.value,
        mo.callout(
            mo.md(
                f"Ready. Data will be read from `{DATA_DIR}` only after you press "
                "**Build data and run conditional test**."
            ),
            kind="info",
        ),
    )
    _frames = {}
    _quality_rows = []
    _audit_rows = []
    _coverage_parts = []
    for _instrument in INSTRUMENTS:
        _frame, _quality, _audit, _coverage = build_decision_frame(_instrument)
        _frames[_instrument] = _frame
        _quality_rows.append(_quality)
        _audit_rows.append(_audit)
        _coverage_parts.append(_coverage)
    decision_frames = _frames
    quality_report = pd.DataFrame(_quality_rows)
    alignment_audit = pd.DataFrame(_audit_rows)
    coverage_report = pd.concat(_coverage_parts, ignore_index=True)
    assert quality_report.duplicate_ts.eq(0).all()
    assert quality_report.out_of_order_ts.eq(0).all()
    assert alignment_audit.exact_future_clock.all()
    assert alignment_audit.feature_target_nonoverlap.all()
    assert alignment_audit.max_range_error.max() < 1e-12
    assert alignment_audit.max_target_error_bp.max() < 1e-9
    assert alignment_audit.max_slot_median_error_bp.max() < 1e-9
    return alignment_audit, coverage_report, decision_frames, quality_report


@app.cell
def _(alignment_audit, coverage_report, mo, quality_report):
    _coverage_summary = (
        coverage_report.groupby(["instrument", "mfo"], as_index=False)
        .agg(
            rows=("rows", "sum"),
            target_coverage=("target_coverage", "mean"),
            range_coverage=("range_coverage", "mean"),
            median_coverage=("median_coverage", "mean"),
        )
    )
    mo.ui.tabs(
        {
            "Load quality": mo.vstack(
                [
                    mo.md(
                        "Duplicate/order checks are hard assertions. Contract/timestamp "
                        "breaks are masked before the rolling range is formed."
                    ),
                    quality_report,
                ]
            ),
            "Causal alignment audit": mo.vstack(
                [
                    mo.md(
                        "Sampled rows recompute the range, future target, and trailing "
                        "same-slot median from raw bars. All errors must be numerically zero."
                    ),
                    alignment_audit,
                ]
            ),
            "Coverage by slot": _coverage_summary,
            "Coverage by year and slot": coverage_report,
        }
    )
    return


@app.cell
def _(
    INSTRUMENTS,
    decision_frames,
    end_year,
    max_iter,
    mo,
    pd,
    start_year,
    walkforward_core,
):
    _first_year = int(start_year.value)
    _last_year = int(end_year.value)
    mo.stop(_first_year > _last_year, mo.md("First OOS year must not exceed last OOS year."))
    _prediction_parts = []
    for _instrument in INSTRUMENTS:
        _part = walkforward_core(
            decision_frames[_instrument],
            _first_year,
            _last_year,
            int(max_iter.value),
        )
        mo.stop(_part.empty, mo.md(f"No eligible OOS rows for {_instrument}."))
        _prediction_parts.append(_part)
    oos_predictions = pd.concat(_prediction_parts, ignore_index=True)
    return (oos_predictions,)


@app.cell
def _(
    INSTRUMENTS,
    RANDOM_SEED,
    bootstrap_draws,
    bootstrap_metrics,
    detail_table,
    metric_bundle,
    oos_predictions,
    pd,
):
    _summary_rows = []
    _bootstrap_parts = []
    _yearly_rows = []
    for _j, _instrument in enumerate(INSTRUMENTS):
        _frame = oos_predictions.loc[oos_predictions.instrument == _instrument].copy()
        _metrics = metric_bundle(_frame)
        _metrics["instrument"] = _instrument
        _summary_rows.append(_metrics)
        _boot = bootstrap_metrics(
            _frame,
            int(bootstrap_draws.value),
            RANDOM_SEED + 1000 * (_j + 1),
        )
        _boot.insert(0, "instrument", _instrument)
        _bootstrap_parts.append(_boot)
        for _year, _year_frame in _frame.groupby("year"):
            _year_metrics = metric_bundle(_year_frame)
            _year_metrics.update({"instrument": _instrument, "year": int(_year)})
            _yearly_rows.append(_year_metrics)

    conditional_summary = pd.DataFrame(_summary_rows).set_index("instrument")
    bootstrap_intervals = pd.concat(_bootstrap_parts, ignore_index=True)
    yearly_diagnostics = pd.DataFrame(_yearly_rows)
    per_slot = detail_table(oos_predictions, ["instrument", "mfo", "decision_et", "forecast_start_et"])
    per_slot_weekday = detail_table(
        oos_predictions,
        ["instrument", "mfo", "decision_et", "forecast_start_et", "weekday"],
    )

    _gate = bootstrap_intervals.pivot(index="instrument", columns="metric", values="ci_90_lo")
    gate_table = conditional_summary[
        ["log_mse_skill", "within_slot_ic_delta", "fwl_resid_corr"]
    ].copy()
    gate_table["within_slot_delta_ci_lo"] = _gate["within_slot_ic_delta"]
    gate_table["fwl_corr_ci_lo"] = _gate["fwl_resid_corr"]
    gate_table["passes"] = (
        gate_table.log_mse_skill.gt(0)
        & gate_table.within_slot_delta_ci_lo.gt(0)
        & gate_table.fwl_corr_ci_lo.gt(0)
    )

    if gate_table.passes.all():
        automatic_verdict = "CONDITIONAL SIGNAL SURVIVES on both markets."
        verdict_kind = "success"
    elif (
        gate_table.log_mse_skill.le(0).all()
        and gate_table.within_slot_delta_ci_lo.le(0).all()
    ):
        automatic_verdict = (
            "CALIBRATION-DOMINANT: the core does not beat the free same-slot median "
            "on the predeclared conditional tests."
        )
        verdict_kind = "danger"
    else:
        automatic_verdict = (
            "MIXED DIAGNOSTIC: the two-market conditional gate does not pass; do not "
            "promote this into strategy work without clean future evidence."
        )
        verdict_kind = "warn"

    _calibration_parts = []
    for _instrument, _frame in oos_predictions.groupby("instrument"):
        _work = _frame.copy()
        _work["forecast_ratio_decile"] = pd.qcut(
            _work.forecast_ratio, 10, labels=False, duplicates="drop"
        )
        _calibration = (
            _work.groupby("forecast_ratio_decile", as_index=False)
            .agg(
                n=("fwd_rv_bp_norm", "size"),
                mean_forecast_ratio=("forecast_ratio", "mean"),
                mean_actual_ratio=("fwd_rv_bp_norm", "mean"),
                median_actual_ratio=("fwd_rv_bp_norm", "median"),
            )
        )
        _calibration.insert(0, "instrument", _instrument)
        _calibration_parts.append(_calibration)
    calibration_by_decile = pd.concat(_calibration_parts, ignore_index=True)
    return (
        automatic_verdict,
        bootstrap_intervals,
        calibration_by_decile,
        conditional_summary,
        gate_table,
        per_slot,
        per_slot_weekday,
        verdict_kind,
        yearly_diagnostics,
    )


@app.cell
def _(
    automatic_verdict,
    bootstrap_intervals,
    conditional_summary,
    gate_table,
    mo,
    verdict_kind,
):
    _headline_columns = [
        "n",
        "pooled_raw_ic_model",
        "pooled_raw_ic_median",
        "pooled_normalized_ic",
        "within_slot_ic_model",
        "within_slot_ic_median",
        "within_slot_ic_delta",
        "slot_weekday_ic_delta",
        "fwl_resid_corr",
        "fwl_resid_r2",
        "log_ratio_r2",
        "log_mse_skill",
        "raw_mae_model_bp",
        "raw_mae_median_bp",
    ]
    mo.vstack(
        [
            mo.callout(mo.md(f"## {automatic_verdict}"), kind=verdict_kind),
            mo.md(
                "**Main summary.** Pooled IC is shown beside the free median. The "
                "conditional columns remove clock-slot ordering; positive log-MSE skill "
                "means the model beats the median in out-of-sample squared log error."
            ),
            conditional_summary[_headline_columns],
            mo.md("**Predeclared two-market gate**"),
            gate_table,
            mo.md("**90% session-block intervals**"),
            bootstrap_intervals,
        ]
    )
    return


@app.cell
def _(
    calibration_by_decile,
    mo,
    per_slot,
    per_slot_weekday,
    yearly_diagnostics,
):
    _year_columns = [
        "instrument",
        "year",
        "n",
        "pooled_raw_ic_model",
        "pooled_raw_ic_median",
        "within_slot_ic_delta",
        "slot_weekday_ic_delta",
        "fwl_resid_corr",
        "fwl_resid_r2",
        "log_mse_skill",
    ]
    mo.ui.tabs(
        {
            "Per slot": per_slot,
            "Per slot × weekday": per_slot_weekday,
            "Yearly stability": yearly_diagnostics[_year_columns],
            "Conditional calibration": calibration_by_decile,
        }
    )
    return


@app.cell
def _(conditional_summary, mo, np, per_slot, plt):
    _summary_plot = conditional_summary.reset_index()
    _metric_labels = [
        ("pooled_raw_ic_model", "Pooled model IC"),
        ("pooled_raw_ic_median", "Pooled median IC"),
        ("within_slot_ic_model", "Within-slot model IC"),
        ("within_slot_ic_median", "Within-slot median IC"),
        ("fwl_resid_corr", "FWL residual corr"),
    ]
    _x = np.arange(len(_metric_labels))
    _width = 0.36
    _fig1, _ax1 = plt.subplots(figsize=(11, 4.8))
    for _j, _instrument in enumerate(_summary_plot.instrument):
        _values = [_summary_plot.loc[_j, _name] for _name, _ in _metric_labels]
        _ax1.bar(_x + (_j - 0.5) * _width, _values, _width, label=_instrument)
    _ax1.axhline(0, color="black", linewidth=0.8)
    _ax1.set_xticks(_x, [_label for _, _label in _metric_labels], rotation=18, ha="right")
    _ax1.set_ylabel("Correlation / rank IC")
    _ax1.set_title("Pooled strength versus conditional strength")
    _ax1.legend()
    _fig1.tight_layout()

    _fig2, _axes = plt.subplots(1, 2, figsize=(13, 4.6), sharey=True)
    for _axis, (_instrument, _group) in zip(_axes, per_slot.groupby("instrument")):
        _group = _group.sort_values("mfo")
        _axis.plot(
            _group.forecast_start_et,
            _group.model_raw_ic,
            marker="o",
            label="core forecast",
        )
        _axis.plot(
            _group.forecast_start_et,
            _group.median_raw_ic,
            marker="o",
            label="free median",
        )
        _axis.plot(
            _group.forecast_start_et,
            _group.conditional_ratio_ic,
            marker="o",
            label="forecast ratio vs actual ratio",
        )
        _axis.axhline(0, color="black", linewidth=0.8)
        _axis.set_title(_instrument)
        _axis.tick_params(axis="x", rotation=65)
        _axis.set_xlabel("Forecast starts (ET)")
    _axes[0].set_ylabel("Spearman IC across days at fixed slot")
    _axes[-1].legend(fontsize=8)
    _fig2.suptitle("Does the model rank volatility within each decision slot?")
    _fig2.tight_layout()
    mo.vstack([_fig1, _fig2])
    return


@app.cell
def _(automatic_verdict, conditional_summary, mo):
    _nq = conditional_summary.loc["NQ"]
    _es = conditional_summary.loc["ES"]
    mo.md(
        f"""
        ## How to read the result

        **Automated preregistered read:** {automatic_verdict}

        - Pooled raw IC is `{_nq.pooled_raw_ic_model:.3f}` NQ and
          `{_es.pooled_raw_ic_model:.3f}` ES. The median-only IC beside it shows how
          much ordering was already available from the intraday baseline.
        - Within-slot model-minus-median IC is `{_nq.within_slot_ic_delta:+.3f}` NQ and
          `{_es.within_slot_ic_delta:+.3f}` ES. This is the direct answer to whether the
          forecast improves ranking at a fixed clock decision.
        - FWL residual R² is `{_nq.fwl_resid_r2:.3f}` NQ and
          `{_es.fwl_resid_r2:.3f}` ES. It measures association left after removing the
          log same-slot median from both actual and forecast volatility.
        - Log-MSE skill versus the free median is `{_nq.log_mse_skill:+.1%}` NQ and
          `{_es.log_mse_skill:+.1%}` ES. Positive is an actual forecasting improvement;
          zero means no gain; negative means the model is worse.

        IC is not additively decomposable, so do **not** interpret
        `within-slot IC / pooled IC` as a literal percentage of signal retained. Read the
        conditional metrics, loss improvement, confidence intervals, slot table, and
        yearly stability together.
        """
    )
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
