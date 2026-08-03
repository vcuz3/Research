# Claims register — forex/noise_vwap

This project is a cross-instrument PORT, not a paper replication, so there are
no published FX numbers to reproduce. The register therefore records (a) the
claims inherited from the source strategy that the port puts to the test, and
(b) the claims this project itself makes, each with the evidence that settles it.

The paper-faithful claims for the source strategy are registered in
`futures/nq/noise_vwap/paper/CLAIMS.md`; the reference result there
(NQ zero-day daily Sharpe ~0.92, vol-targeted ~1.18) is the external benchmark.

## A. Inherited claims put to the test

| id | claim | tolerance / gate | status | evidence |
| --- | --- | --- | --- | --- |
| A1 | Displacement beyond a same-time-of-day noise area measured from the session open is followed by intraday CONTINUATION | mean signed forward return > 0 with cluster-robust t >= 2 | **holds on NQ/ES, FAILS on FX**. NQ +4.7..+24.5 ticks (t +2.4..+4.0); ES +1.0..+2.7 (t +1.2..+3.2); FX −0.062..+0.061 band-widths, no reliable sign | `artifacts/runs/EXP-0002/` |
| A2 | A session-anchored average price (VWAP) confirms direction as an entry gate | gate improves the primary metric | **holds directionally on FX** (+0.068..+0.164 Sharpe on 8/8 combos) but improves a loser into a smaller loser | `artifacts/runs/EXP-0001/` |
| A3 | A session-anchored average price is a useful trailing-stop reference | `both` beats a band-only stop | **fails on FX**: the volume-free `band` stop matches or beats `both` on 8/8 combos | `artifacts/runs/EXP-0001/` |
| A4 | The strategy transfers across instruments with a well-defined trading day | median gross pips/trade > 0 | **fails**: median −0.548 (`fxday`) / −0.455 (`active`) pips/trade before any cost, 4/4 pairs | `artifacts/runs/EXP-0001/` |

## B. Claims this project makes

| id | claim | gate | status | evidence |
| --- | --- | --- | --- | --- |
| B1 | TWAP is the VWAP formula evaluated at constant volume, i.e. the exact degenerate limit, not a heuristic proxy | exact equality under constant weights AND inequality under varying weights, both asserted | **verified** | `tests/test_core.py::test_twap_is_vwap_under_constant_volume`, `::test_twap_differs_from_a_real_volume_weighted_average` |
| B2 | `stop_ref="band"` is genuinely volume-free (no anchor can influence it) | perturbing the anchor leaves the trade set bit-identical, while `both` changes | **verified** | `tests/test_core.py::test_band_stop_ignores_the_anchor_entirely` |
| B3 | The engine never fills at the signal bar's own close or at a band/stop level | asserted on toy sessions with non-zero inter-bar links | **verified** | `tests/test_core.py::test_entry_fills_at_the_next_bar_open_never_the_signal_close`, `::test_no_fill_at_the_band_or_stop_level` |
| B4 | `core/engine_nb.py` is trade-level identical to `core/engine.py` | every trade row equal, prices exactly (0.0 tolerance), across the full config grid on real data | **verified**, 400 configurations | `tests/test_parity.py` |
| B5 | The Null C shuffle pins the opening atom and preserves session net move, atom multiset and diffusivity | multi-seed invariant tests | **verified** (null unspent — no real pass cleared its primary metric) | `tests/test_core.py` null section |
| B6 | Bands and TWAP are causal | a future bar cannot change a past value | **verified** | `tests/test_core.py::test_bands_use_only_strictly_prior_sessions`, `::test_twap_is_causal` |
| B7 | The rule-9a fractional `min_periods` keeps decisions that the strict rule would silently delete | fractional keeps a slot the strict rule nulls; coverage uniform across slots | **verified**; saves 6,296–6,587 decision points/pair on `fxday`, per-slot spread 0.0000 | `tests/test_core.py::test_band_min_periods_is_fractional_not_strict`, `reports/DATA_QUALITY.md` |
| B8 | No decision can land in an IBKR `:00–:14` archive gap | asserted for every decision mfo in both sessions | **verified** | `tests/test_core.py::test_decision_clock_avoids_the_archive_holes` |
| B9 | Per-signal and session-averaged estimands disagree in sign here because signal count is endogenous to the outcome | corr(session mean, session count) materially > 0 and the two estimands differ in sign | **verified**: corr +0.41 on FX, +0.23..+0.44 on NQ/ES; signs opposite on both | `artifacts/runs/EXP-0002/review.md`, `reports/FINDINGS.md` §D |

## C. Unresolved

| id | item | why it is unresolved |
| --- | --- | --- |
| C1 | Realistic FX transaction costs | the IBKR archive is midpoint-only, so 0.50 pip/side is an assumption, not a measurement. It does not affect the verdict (gross is negative) but blocks any future deployable FX claim here. |
| C2 | Independent review of EXP-0001 and EXP-0002 | outstanding |
