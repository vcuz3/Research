from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd


# ============================================================
# USER CONFIGURATION
# ============================================================

ACCOUNT_SIZE = 25_000

DATE_COLUMN = "date"

# pnl2 must be incremental PnL:
#
#   equity_after_row = equity_before_row + pnl2
#
# Rows must be chronologically ordered and sufficiently granular
# to represent the intraday equity path.
#
# Examples:
#   - tick-by-tick mark-to-market PnL
#   - bar-by-bar mark-to-market PnL
#   - sequential trade/event PnL, with limitations described below

EVALUATION_FEE = 25.0

# Enter the PA activation fee you actually pay.
# It is deliberately not hard-coded from current pricing.
PA_ACTIVATION_FEE = 0.0

# True:
# Automatically request the largest permitted payout at the end
# of the first eligible day.
AUTO_REQUEST_PAYOUT = True

# Apex evaluates days using its trading-session definition.
# If your date column already contains the correct trading day,
# leave this as False.
#
# If timestamp rows after midnight should belong to the previous
# futures trading session, construct a trading_day column yourself
# before running the simulation.
USE_NORMALIZED_CALENDAR_DATE = True

# Model a fresh evaluation immediately after:
#   - evaluation failure
#   - evaluation expiration
#   - PA closure
#   - completion of six PA payouts
RESTART_AFTER_COMPLETION = True

# The code assumes five new qualifying days are required after
# each approved payout.
RESET_QUALIFYING_DAYS_AFTER_PAYOUT = True

# Account platform affects how the evaluation threshold behaves.
#
# "rithmic":
#   Evaluation threshold stops when it reaches the target balance.
#
# "wealthcharts":
#   Same treatment as Rithmic.
#
# "tradovate":
#   Evaluation trailing threshold continues indefinitely.
EVALUATION_PLATFORM = "rithmic"


# ============================================================
# VERIFIED ACCOUNT PARAMETERS
# ============================================================

ACCOUNT_RULES = {
    25_000: {
        "evaluation_target": 1_500.0,
        "max_drawdown": 1_000.0,
        "qualifying_day_profit": 100.0,
        "safety_net_balance": 26_100.0,
        "minimum_balance_to_request": 26_600.0,
        "payout_caps": [
            1_000.0,
            1_000.0,
            1_000.0,
            1_000.0,
            1_000.0,
            1_000.0,
        ],
    },
    50_000: {
        "evaluation_target": 3_000.0,
        "max_drawdown": 2_000.0,
        "qualifying_day_profit": 200.0,
        "safety_net_balance": 52_100.0,
        "minimum_balance_to_request": 52_600.0,
        "payout_caps": [
            1_500.0,
            2_000.0,
            2_500.0,
            2_500.0,
            3_000.0,
            3_000.0,
        ],
    },
    100_000: {
        "evaluation_target": 6_000.0,
        "max_drawdown": 3_000.0,
        "qualifying_day_profit": 250.0,
        "safety_net_balance": 103_100.0,
        "minimum_balance_to_request": 103_600.0,
        "payout_caps": [
            2_000.0,
            2_500.0,
            3_000.0,
            3_000.0,
            4_000.0,
            4_000.0,
        ],
    },
    150_000: {
        "evaluation_target": 9_000.0,
        "max_drawdown": 4_000.0,
        "qualifying_day_profit": 300.0,
        "safety_net_balance": 154_100.0,
        "minimum_balance_to_request": 154_600.0,
        "payout_caps": [
            2_500.0,
            3_000.0,
            3_000.0,
            4_000.0,
            4_000.0,
            5_000.0,
        ],
    },
}


# ============================================================
# PA DAILY-LOSS-LIMIT TIERS
# ============================================================
#
# Profit means:
#
#   end-of-day account balance - PA starting balance
#
# The tier reached from an end-of-day balance applies to the
# following trading day.

PA_DLL_TIERS = {
    25_000: [
        # minimum profit, DLL
        (0.0, 500.0),
        (1_000.0, 500.0),
        (2_000.0, 1_250.0),
    ],
    50_000: [
        (0.0, 1_000.0),
        (1_500.0, 1_000.0),
        (3_000.0, 2_000.0),
        (6_000.0, 3_000.0),
    ],
    100_000: [
        (0.0, 1_750.0),
        (2_000.0, 1_750.0),
        (3_000.0, 1_750.0),
        (5_000.0, 2_500.0),
        (10_000.0, 3_500.0),
    ],
    150_000: [
        (0.0, 2_500.0),
        (2_000.0, 2_500.0),
        (3_000.0, 2_500.0),
        (5_000.0, 3_000.0),
        (10_000.0, 4_000.0),
    ],
}


# ============================================================
# VALIDATION
# ============================================================

if ACCOUNT_SIZE not in ACCOUNT_RULES:
    raise ValueError(
        f"ACCOUNT_SIZE must be one of "
        f"{sorted(ACCOUNT_RULES.keys())}."
    )

if EVALUATION_PLATFORM.lower() not in {
    "rithmic",
    "wealthcharts",
    "tradovate",
}:
    raise ValueError(
        "EVALUATION_PLATFORM must be 'rithmic', "
        "'wealthcharts', or 'tradovate'."
    )

required_columns = {DATE_COLUMN, PNL_COLUMN}
missing_columns = required_columns.difference(df.columns)

if missing_columns:
    raise ValueError(
        f"Missing required columns: {sorted(missing_columns)}"
    )

sim_df = df[[DATE_COLUMN, PNL_COLUMN]].copy()

sim_df[DATE_COLUMN] = pd.to_datetime(
    sim_df[DATE_COLUMN],
    errors="coerce",
)

sim_df[PNL_COLUMN] = pd.to_numeric(
    sim_df[PNL_COLUMN],
    errors="coerce",
)

invalid_mask = (
    sim_df[DATE_COLUMN].isna()
    | sim_df[PNL_COLUMN].isna()
    | ~np.isfinite(sim_df[PNL_COLUMN])
)

if invalid_mask.any():
    print(
        f"Dropping {int(invalid_mask.sum()):,} rows with "
        f"invalid timestamps or PnL."
    )

sim_df = (
    sim_df.loc[~invalid_mask]
    .sort_values(DATE_COLUMN, kind="stable")
    .reset_index(drop=True)
)

if sim_df.empty:
    raise ValueError("No valid observations remain.")

if USE_NORMALIZED_CALENDAR_DATE:
    sim_df["trading_day"] = sim_df[DATE_COLUMN].dt.normalize()
else:
    # Assumes DATE_COLUMN is already the desired trading-day label.
    sim_df["trading_day"] = sim_df[DATE_COLUMN]


# ============================================================
# STATE CLASSES
# ============================================================

@dataclass
class EvaluationState:
    evaluation_number: int
    start_timestamp: pd.Timestamp
    start_trading_day: pd.Timestamp
    equity: float
    peak_equity: float
    trailing_threshold: float
    active: bool = True


@dataclass
class PAState:
    pa_number: int
    start_timestamp: pd.Timestamp
    start_trading_day: pd.Timestamp

    equity: float
    peak_equity: float
    trailing_threshold: float

    payout_number: int = 0
    approved_payouts: float = 0.0

    # Daily PnL records since the last approved payout.
    cycle_daily_pnl: list[float] = field(default_factory=list)

    # Number of days in the current payout cycle meeting the
    # minimum daily-profit requirement.
    qualifying_days: int = 0

    active: bool = True
    dll_paused_today: bool = False

    # DLL applicable for the current day. This is set using the
    # prior day's closing balance.
    current_day_dll: float = 0.0


# ============================================================
# HELPER FUNCTIONS
# ============================================================

rules = ACCOUNT_RULES[ACCOUNT_SIZE]

STARTING_BALANCE = float(ACCOUNT_SIZE)
EVALUATION_TARGET = rules["evaluation_target"]
EVALUATION_TARGET_BALANCE = STARTING_BALANCE + EVALUATION_TARGET

MAX_DRAWDOWN = rules["max_drawdown"]
QUALIFYING_DAY_PROFIT = rules["qualifying_day_profit"]

SAFETY_NET_BALANCE = rules["safety_net_balance"]
MINIMUM_BALANCE_TO_REQUEST = rules[
    "minimum_balance_to_request"
]

PAYOUT_CAPS = rules["payout_caps"]
MAX_PAYOUTS = len(PAYOUT_CAPS)
MINIMUM_PAYOUT = 500.0


def get_pa_dll(equity: float) -> float:
    """
    Return the PA DLL associated with the current EOD balance.

    The resulting DLL is intended for the following trading day.
    """
    account_profit = equity - STARTING_BALANCE
    account_profit = max(account_profit, 0.0)

    applicable_dll = PA_DLL_TIERS[ACCOUNT_SIZE][0][1]

    for minimum_profit, dll in PA_DLL_TIERS[ACCOUNT_SIZE]:
        if account_profit >= minimum_profit:
            applicable_dll = dll
        else:
            break

    return float(applicable_dll)


def get_evaluation_threshold(
    peak_equity: float,
) -> float:
    """
    Calculate the Evaluation trailing threshold.

    Rithmic/WealthCharts:
        threshold trails peak by MAX_DRAWDOWN but stops when the
        threshold reaches the evaluation target balance.

    Tradovate:
        threshold trails peak indefinitely.
    """
    uncapped_threshold = peak_equity - MAX_DRAWDOWN

    if EVALUATION_PLATFORM.lower() in {
        "rithmic",
        "wealthcharts",
    }:
        return min(
            uncapped_threshold,
            EVALUATION_TARGET_BALANCE,
        )

    return uncapped_threshold


def get_pa_threshold(
    peak_equity: float,
) -> float:
    """
    Calculate the PA trailing threshold.

    It trails MAX_DRAWDOWN behind peak equity until reaching:

        starting balance + $100

    It then stops permanently.
    """
    pa_threshold_cap = STARTING_BALANCE + 100.0

    return min(
        peak_equity - MAX_DRAWDOWN,
        pa_threshold_cap,
    )


def calculate_consistency(
    daily_pnl_values: list[float],
) -> tuple[float, float, float]:
    """
    Returns:
        net_profit_since_payout
        largest_profitable_day
        consistency_ratio

    Losing days reduce net profit.

    If net profit is not positive, consistency is infinite and
    payout eligibility is false.
    """
    if not daily_pnl_values:
        return 0.0, 0.0, np.inf

    net_profit = float(np.sum(daily_pnl_values))

    profitable_days = [
        pnl for pnl in daily_pnl_values if pnl > 0
    ]

    largest_profit_day = (
        max(profitable_days)
        if profitable_days
        else 0.0
    )

    if net_profit <= 0:
        consistency_ratio = np.inf
    else:
        consistency_ratio = (
            largest_profit_day / net_profit
        )

    return (
        net_profit,
        float(largest_profit_day),
        float(consistency_ratio),
    )


def calculate_payout_eligibility(
    pa: PAState,
) -> dict:
    """
    Test all payout requirements at EOD.
    """
    (
        net_cycle_profit,
        largest_profit_day,
        consistency_ratio,
    ) = calculate_consistency(pa.cycle_daily_pnl)

    has_five_qualifying_days = pa.qualifying_days >= 5

    # The Apex example marks exactly 50% as qualifying.
    consistency_met = consistency_ratio <= 0.50

    balance_met = (
        pa.equity >= MINIMUM_BALANCE_TO_REQUEST
    )

    has_payout_slot = pa.payout_number < MAX_PAYOUTS

    withdrawable_above_safety_net = max(
        pa.equity - SAFETY_NET_BALANCE,
        0.0,
    )

    next_payout_cap = (
        PAYOUT_CAPS[pa.payout_number]
        if has_payout_slot
        else 0.0
    )

    maximum_request = min(
        withdrawable_above_safety_net,
        next_payout_cap,
    )

    minimum_payout_met = (
        maximum_request >= MINIMUM_PAYOUT
    )

    eligible = all(
        [
            pa.active,
            has_five_qualifying_days,
            consistency_met,
            balance_met,
            minimum_payout_met,
            has_payout_slot,
        ]
    )

    return {
        "eligible": eligible,
        "qualifying_days": pa.qualifying_days,
        "net_cycle_profit": net_cycle_profit,
        "largest_profit_day": largest_profit_day,
        "consistency_ratio": consistency_ratio,
        "consistency_met": consistency_met,
        "balance_met": balance_met,
        "withdrawable_above_safety_net":
            withdrawable_above_safety_net,
        "next_payout_cap": next_payout_cap,
        "maximum_request": maximum_request,
        "has_payout_slot": has_payout_slot,
    }


def start_evaluation(
    evaluation_number: int,
    timestamp: pd.Timestamp,
    trading_day: pd.Timestamp,
) -> EvaluationState:
    peak = STARTING_BALANCE

    return EvaluationState(
        evaluation_number=evaluation_number,
        start_timestamp=timestamp,
        start_trading_day=trading_day,
        equity=STARTING_BALANCE,
        peak_equity=peak,
        trailing_threshold=get_evaluation_threshold(peak),
    )


def start_pa(
    pa_number: int,
    timestamp: pd.Timestamp,
    trading_day: pd.Timestamp,
) -> PAState:
    peak = STARTING_BALANCE

    return PAState(
        pa_number=pa_number,
        start_timestamp=timestamp,
        start_trading_day=trading_day,
        equity=STARTING_BALANCE,
        peak_equity=peak,
        trailing_threshold=get_pa_threshold(peak),
        current_day_dll=get_pa_dll(STARTING_BALANCE),
    )


# ============================================================
# SIMULATION OUTPUT COLLECTIONS
# ============================================================

event_records: list[dict] = []
daily_records: list[dict] = []
payout_records: list[dict] = []
evaluation_records: list[dict] = []
pa_records: list[dict] = []


# ============================================================
# GLOBAL SIMULATION STATE
# ============================================================

phase = "evaluation"

evaluation_number = 1
pa_number = 0

total_evaluation_fees = EVALUATION_FEE
total_activation_fees = 0.0
total_gross_payouts = 0.0

first_row = sim_df.iloc[0]

evaluation: Optional[EvaluationState] = start_evaluation(
    evaluation_number=evaluation_number,
    timestamp=first_row[DATE_COLUMN],
    trading_day=first_row["trading_day"],
)

pa: Optional[PAState] = None


# ============================================================
# MAIN DAILY LOOP
# ============================================================

grouped_days = list(
    sim_df.groupby("trading_day", sort=True)
)

for day_position, (trading_day, day_df) in enumerate(
    grouped_days
):
    day_df = day_df.sort_values(
        DATE_COLUMN,
        kind="stable",
    )

    first_timestamp = day_df.iloc[0][DATE_COLUMN]
    last_timestamp = day_df.iloc[-1][DATE_COLUMN]

    # --------------------------------------------------------
    # Start fresh evaluation if no lifecycle is active
    # --------------------------------------------------------
    if phase == "inactive":
        if not RESTART_AFTER_COMPLETION:
            break

        evaluation_number += 1
        total_evaluation_fees += EVALUATION_FEE

        evaluation = start_evaluation(
            evaluation_number=evaluation_number,
            timestamp=first_timestamp,
            trading_day=trading_day,
        )

        pa = None
        phase = "evaluation"

    # ========================================================
    # EVALUATION DAY
    # ========================================================

    if phase == "evaluation":
        assert evaluation is not None

        day_start_equity = evaluation.equity
        day_breached = False

        for row in day_df.itertuples(index=False):
            timestamp = getattr(row, DATE_COLUMN)
            incremental_pnl = float(
                getattr(row, PNL_COLUMN)
            )

            equity_before = evaluation.equity
            evaluation.equity += incremental_pnl

            evaluation.peak_equity = max(
                evaluation.peak_equity,
                evaluation.equity,
            )

            evaluation.trailing_threshold = (
                get_evaluation_threshold(
                    evaluation.peak_equity
                )
            )

            event_records.append(
                {
                    "timestamp": timestamp,
                    "trading_day": trading_day,
                    "phase": "evaluation",
                    "account_number":
                        evaluation.evaluation_number,
                    "incremental_pnl": incremental_pnl,
                    "equity_before": equity_before,
                    "equity_after": evaluation.equity,
                    "peak_equity":
                        evaluation.peak_equity,
                    "trailing_threshold":
                        evaluation.trailing_threshold,
                    "dll_threshold": np.nan,
                    "event": "observation",
                }
            )

            # Touching the threshold fails immediately.
            if (
                evaluation.equity
                <= evaluation.trailing_threshold
            ):
                day_breached = True
                evaluation.active = False

                evaluation_records.append(
                    {
                        "evaluation_number":
                            evaluation.evaluation_number,
                        "start_timestamp":
                            evaluation.start_timestamp,
                        "end_timestamp": timestamp,
                        "result": "failed_drawdown",
                        "ending_equity":
                            evaluation.equity,
                        "peak_equity":
                            evaluation.peak_equity,
                        "final_threshold":
                            evaluation.trailing_threshold,
                    }
                )

                event_records[-1]["event"] = (
                    "evaluation_failed_drawdown"
                )

                break

        day_pnl = evaluation.equity - day_start_equity

        daily_records.append(
            {
                "trading_day": trading_day,
                "phase": "evaluation",
                "account_number":
                    evaluation.evaluation_number,
                "start_equity": day_start_equity,
                "end_equity": evaluation.equity,
                "day_pnl": day_pnl,
                "qualifying_day": False,
                "dll_hit": False,
                "drawdown_breach": day_breached,
                "payout": 0.0,
            }
        )

        if day_breached:
            phase = "inactive"
            evaluation = None
            continue

        # Evaluation access period is 30 consecutive calendar days.
        elapsed_calendar_days = (
            pd.Timestamp(trading_day).normalize()
            - pd.Timestamp(
                evaluation.start_trading_day
            ).normalize()
        ).days + 1

        # Passing is assessed at EOD, not merely when the target
        # is temporarily touched intraday.
        if evaluation.equity >= EVALUATION_TARGET_BALANCE:
            evaluation.active = False

            evaluation_records.append(
                {
                    "evaluation_number":
                        evaluation.evaluation_number,
                    "start_timestamp":
                        evaluation.start_timestamp,
                    "end_timestamp": last_timestamp,
                    "result": "passed",
                    "ending_equity":
                        evaluation.equity,
                    "peak_equity":
                        evaluation.peak_equity,
                    "final_threshold":
                        evaluation.trailing_threshold,
                }
            )

            # Activate the PA immediately for simulation purposes,
            # with trading beginning on the next available day.
            pa_number += 1
            total_activation_fees += PA_ACTIVATION_FEE

            pa = start_pa(
                pa_number=pa_number,
                timestamp=last_timestamp,
                trading_day=trading_day,
            )

            evaluation = None
            phase = "pa"

        elif elapsed_calendar_days >= 30:
            evaluation.active = False

            evaluation_records.append(
                {
                    "evaluation_number":
                        evaluation.evaluation_number,
                    "start_timestamp":
                        evaluation.start_timestamp,
                    "end_timestamp": last_timestamp,
                    "result": "expired",
                    "ending_equity":
                        evaluation.equity,
                    "peak_equity":
                        evaluation.peak_equity,
                    "final_threshold":
                        evaluation.trailing_threshold,
                }
            )

            phase = "inactive"
            evaluation = None

        continue

    # ========================================================
    # PERFORMANCE ACCOUNT DAY
    # ========================================================

    if phase == "pa":
        assert pa is not None

        day_start_equity = pa.equity
        day_dll = pa.current_day_dll

        # DLL is based on loss from the beginning of the session.
        dll_threshold = day_start_equity - day_dll

        pa.dll_paused_today = False

        drawdown_breached = False
        dll_hit = False

        for row in day_df.itertuples(index=False):
            timestamp = getattr(row, DATE_COLUMN)
            incremental_pnl = float(
                getattr(row, PNL_COLUMN)
            )

            if pa.dll_paused_today:
                # Remaining observations are ignored because Apex
                # pauses trading after the DLL is hit.
                continue

            equity_before = pa.equity
            pa.equity += incremental_pnl

            pa.peak_equity = max(
                pa.peak_equity,
                pa.equity,
            )

            pa.trailing_threshold = get_pa_threshold(
                pa.peak_equity
            )

            event = "observation"

            # A permanent PA close has priority where the observed
            # endpoint is at or below the trailing threshold.
            if pa.equity <= pa.trailing_threshold:
                event = "pa_closed_drawdown"
                drawdown_breached = True
                pa.active = False

            elif pa.equity <= dll_threshold:
                event = "dll_hit"
                dll_hit = True
                pa.dll_paused_today = True

            event_records.append(
                {
                    "timestamp": timestamp,
                    "trading_day": trading_day,
                    "phase": "pa",
                    "account_number": pa.pa_number,
                    "incremental_pnl": incremental_pnl,
                    "equity_before": equity_before,
                    "equity_after": pa.equity,
                    "peak_equity": pa.peak_equity,
                    "trailing_threshold":
                        pa.trailing_threshold,
                    "dll_threshold": dll_threshold,
                    "event": event,
                }
            )

            if drawdown_breached:
                break

        day_pnl = pa.equity - day_start_equity

        qualifying_day = (
            day_pnl >= QUALIFYING_DAY_PROFIT
        )

        payout_amount = 0.0

        if drawdown_breached:
            pa_records.append(
                {
                    "pa_number": pa.pa_number,
                    "start_timestamp":
                        pa.start_timestamp,
                    "end_timestamp": last_timestamp,
                    "result": "closed_drawdown",
                    "payout_count": pa.payout_number,
                    "gross_payouts":
                        pa.approved_payouts,
                    "ending_equity": pa.equity,
                    "peak_equity":
                        pa.peak_equity,
                    "final_threshold":
                        pa.trailing_threshold,
                }
            )

            daily_records.append(
                {
                    "trading_day": trading_day,
                    "phase": "pa",
                    "account_number": pa.pa_number,
                    "start_equity": day_start_equity,
                    "end_equity": pa.equity,
                    "day_pnl": day_pnl,
                    "qualifying_day":
                        qualifying_day,
                    "dll_hit": dll_hit,
                    "drawdown_breach": True,
                    "payout": 0.0,
                }
            )

            phase = "inactive"
            pa = None
            continue

        # Add the full day's net result to the payout-cycle
        # consistency calculation.
        pa.cycle_daily_pnl.append(day_pnl)

        if qualifying_day:
            pa.qualifying_days += 1

        eligibility = calculate_payout_eligibility(pa)

        if (
            AUTO_REQUEST_PAYOUT
            and eligibility["eligible"]
        ):
            payout_amount = eligibility[
                "maximum_request"
            ]

            pa.payout_number += 1
            pa.approved_payouts += payout_amount
            total_gross_payouts += payout_amount

            payout_records.append(
                {
                    "pa_number": pa.pa_number,
                    "payout_number":
                        pa.payout_number,
                    "request_date": trading_day,
                    "balance_before_payout":
                        pa.equity,
                    "payout_amount":
                        payout_amount,
                    "balance_after_payout":
                        pa.equity - payout_amount,
                    "qualifying_days":
                        eligibility["qualifying_days"],
                    "net_profit_since_prior_payout":
                        eligibility["net_cycle_profit"],
                    "largest_profit_day":
                        eligibility[
                            "largest_profit_day"
                        ],
                    "consistency_ratio":
                        eligibility[
                            "consistency_ratio"
                        ],
                    "payout_cap":
                        eligibility[
                            "next_payout_cap"
                        ],
                }
            )

            # Remove the approved payout from account equity.
            pa.equity -= payout_amount

            # A payout does not reset the PA trailing threshold.
            # Peak equity also remains historical.
            pa.trailing_threshold = get_pa_threshold(
                pa.peak_equity
            )

            # Consistency resets after an approved payout.
            pa.cycle_daily_pnl = []

            if RESET_QUALIFYING_DAYS_AFTER_PAYOUT:
                pa.qualifying_days = 0

            # Account completes its payout cycle after payout six.
            if pa.payout_number >= MAX_PAYOUTS:
                pa.active = False

                pa_records.append(
                    {
                        "pa_number": pa.pa_number,
                        "start_timestamp":
                            pa.start_timestamp,
                        "end_timestamp":
                            last_timestamp,
                        "result":
                            "completed_six_payouts",
                        "payout_count":
                            pa.payout_number,
                        "gross_payouts":
                            pa.approved_payouts,
                        "ending_equity": pa.equity,
                        "peak_equity":
                            pa.peak_equity,
                        "final_threshold":
                            pa.trailing_threshold,
                    }
                )

                phase = "inactive"

        daily_records.append(
            {
                "trading_day": trading_day,
                "phase": "pa",
                "account_number": pa.pa_number,
                "start_equity": day_start_equity,
                "end_equity": pa.equity,
                "day_pnl": day_pnl,
                "qualifying_day": qualifying_day,
                "dll_hit": dll_hit,
                "drawdown_breach": False,
                "payout": payout_amount,
            }
        )

        if phase == "inactive":
            pa = None
            continue

        # Set the DLL for the next trading day based on this
        # day's post-payout closing balance.
        pa.current_day_dll = get_pa_dll(pa.equity)


# ============================================================
# CLOSE OUT STILL-ACTIVE ACCOUNTS
# ============================================================

if phase == "evaluation" and evaluation is not None:
    evaluation_records.append(
        {
            "evaluation_number":
                evaluation.evaluation_number,
            "start_timestamp":
                evaluation.start_timestamp,
            "end_timestamp":
                sim_df.iloc[-1][DATE_COLUMN],
            "result": "open_at_end_of_data",
            "ending_equity": evaluation.equity,
            "peak_equity": evaluation.peak_equity,
            "final_threshold":
                evaluation.trailing_threshold,
        }
    )

elif phase == "pa" and pa is not None:
    pa_records.append(
        {
            "pa_number": pa.pa_number,
            "start_timestamp": pa.start_timestamp,
            "end_timestamp":
                sim_df.iloc[-1][DATE_COLUMN],
            "result": "open_at_end_of_data",
            "payout_count": pa.payout_number,
            "gross_payouts":
                pa.approved_payouts,
            "ending_equity": pa.equity,
            "peak_equity": pa.peak_equity,
            "final_threshold":
                pa.trailing_threshold,
        }
    )


# ============================================================
# OUTPUT DATAFRAMES
# ============================================================

events_df = pd.DataFrame(event_records)
daily_summary_df = pd.DataFrame(daily_records)
evaluations_df = pd.DataFrame(evaluation_records)
performance_accounts_df = pd.DataFrame(pa_records)
payouts_df = pd.DataFrame(payout_records)


# ============================================================
# SUMMARY METRICS
# ============================================================

evaluation_passes = (
    evaluations_df["result"].eq("passed").sum()
    if not evaluations_df.empty
    else 0
)

evaluation_failures = (
    evaluations_df["result"]
    .isin(["failed_drawdown", "expired"])
    .sum()
    if not evaluations_df.empty
    else 0
)

pa_drawdown_closures = (
    performance_accounts_df["result"]
    .eq("closed_drawdown")
    .sum()
    if not performance_accounts_df.empty
    else 0
)

completed_six_payouts = (
    performance_accounts_df["result"]
    .eq("completed_six_payouts")
    .sum()
    if not performance_accounts_df.empty
    else 0
)

total_fees = (
    total_evaluation_fees
    + total_activation_fees
)

net_cash_profit = (
    total_gross_payouts
    - total_fees
)

average_payout = (
    payouts_df["payout_amount"].mean()
    if not payouts_df.empty
    else np.nan
)

print("=" * 62)
print("APEX INTRADAY ACCOUNT LIFECYCLE SIMULATION")
print("=" * 62)

print(f"Account size:                 ${ACCOUNT_SIZE:,.0f}")
print(f"Evaluation platform:          {EVALUATION_PLATFORM}")
print()

print(f"Evaluations started:          {evaluation_number}")
print(f"Evaluations passed:           {evaluation_passes}")
print(f"Evaluations failed/expired:   {evaluation_failures}")
print()

print(f"PAs activated:                {pa_number}")
print(f"PAs closed by drawdown:       {pa_drawdown_closures}")
print(f"PAs completing 6 payouts:     {completed_six_payouts}")
print()

print(f"Approved payouts:             {len(payouts_df)}")
print(f"Gross payouts:                ${total_gross_payouts:,.2f}")
print(f"Evaluation fees:              ${total_evaluation_fees:,.2f}")
print(f"PA activation fees:           ${total_activation_fees:,.2f}")
print(f"Total fees:                   ${total_fees:,.2f}")
print(f"Net cash profit:              ${net_cash_profit:,.2f}")

if pd.notna(average_payout):
    print(f"Average payout:               ${average_payout:,.2f}")
else:
    print("Average payout:               N/A")