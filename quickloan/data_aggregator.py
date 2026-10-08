"""Financial aggregation and metrics calculation."""

import pandas as pd
import numpy as np
from quickloan.optional import OptionalParams
from typing import Optional

class Aggregator:
    """
    Fast and memory-efficient financial feature aggregation.
    Computes key metrics for underwriting decisions.
    """

    def __init__(self, df, params: OptionalParams):
        self.df = df
        self.params = params

        # Ensure key columns exist
        expected_cols = {"date", "amount", "category", "type", "monthyear","weekno","balance"}
        missing = expected_cols - set(self.df.columns)
        if missing:
            raise ValueError(f"Missing expected columns: {missing}")

        # Precompute masks for speed
        cat = df["category"]
        typ = df["type"]

        self.mask_transfer = cat.eq("transfer")
        self.all = ~cat.eq("others")
        
        self.mask_salary = cat.eq("salary")
        self.mask_credit = typ.eq("credit")

        self.data = (
            df[cat.isin(['loan_repayment', 'betting','salary','transfer'])] #transfer is included to ensure all months return
            .pivot_table(
                index='monthyear',
                columns='category',
                values='amount',
                aggfunc='sum',
                fill_value=0,
            )
        )
        
        if not self.data.get("betting", pd.Series()).empty:
            self.betting_amount = self.data.get("betting").max()
        else:
            self.betting_amount = 0

        # EOD balances (used for zeroing rate, then freed)
        eod_bal = df.groupby("date")["balance"].last().dropna()

        # Zeroing rate
        self.zeroing_rate = self._compute_zeroing_rate(eod_bal)

    @staticmethod
    def clamp(x, lo, hi):
        """Clamp value to range."""
        return np.clip(x, lo, hi)

    def _compute_zeroing_rate(self, eod_bal):
        """Calculate percentage of days account balance hit zero."""
        if len(eod_bal) == 0:
            return 1.0

        inflow = (
            self.df.loc[self.mask_credit & self.mask_transfer]
            .groupby("date")["amount"]
            .sum()
        )

        common = eod_bal.index.intersection(inflow.index)

        median_inflow = (
            np.nanmedian(inflow.loc[common].values) if len(common) else 0
        )

        threshold = self.params.ZEROING_BASE

        return float(np.mean(eod_bal.values < threshold))

    def _aggregate_period(self, mask, index_col):
        """Aggregate amounts by period (week or month)."""
        summary = (
            self.df[mask]
            .pivot_table(
                index=index_col,
                columns="type",
                values="amount",
                aggfunc="sum",
                fill_value=0,
            )
        )

        if summary.empty:
            return np.zeros(0), np.zeros(0)

        net = summary.get("credit", 0) - summary.get("debit", 0)
        gross = summary.get("credit", 0)

        return net, gross

    def weekly_aggregate(self,repayment):
        """Calculate metrics for non-salaried customers (weekly patterns)."""
        net, gross = self._aggregate_period(self.mask_transfer, "weekno")

        if len(net) == 0:
            return {}

        # Clamp outliers to 10-90 percentile
        p10, p90 = np.nanpercentile(net, [10, 90])
        base_net = np.nanmedian(self.clamp(net, p10, p90))
        gross_med = np.nanmedian(gross)

        mean_net = np.nanmean(net)
        cv = np.nanstd(net) / abs(mean_net) if abs(mean_net) > 0 else 1
        vol_penalty = self.clamp(cv, 0, 2)

        monthly_inflow = gross_med * 4

        di = monthly_inflow*self.params.INFLOW_MARGIN

        # Fit regression on net inflow trend only when series is long enough.
        series_length = len(net)
        if series_length < self.params.MIN_WEEKS_FOR_SLOPE:
            slope = -1
        else:
            time_t = np.arange(series_length)
            slope = np.polyfit(time_t, net, 1)[0]

        # 25th percentile of end-of-week balances
        bal_floor = np.nanpercentile(
            self.df.groupby("weekno")["balance"].last().values,
            25
        )

        repayment = repayment.iloc[-1] if len(repayment) >= 1 else 0

        return {
            "net_to_gross": base_net / gross_med if gross_med else 0,
            "inflow_median": gross_med,
            "base_net": base_net,
            "cv_net": vol_penalty,
            "persistence": float(np.mean(net >= 0)),
            "zeroing_rate": self.zeroing_rate,
            "disposable_income": self.params.REPAYMENT_FRACTION_NON_SALARIED * di,
            "slope": slope,
            "betting_amount":self.betting_amount,
            "balance_floor": bal_floor,
            "salary": None,
            "customer_type": "non_salaried",
            "existing_dtir": repayment/(monthly_inflow),
            "recency":None,
            "series_length": self.df['weekno'].nunique(),
        }

    def monthly_aggregate(self,salary, last_salary_date,repayment):
        """Calculate metrics for salaried customers (monthly patterns)."""
        net, gross = self._aggregate_period(self.all, "monthyear")

        if len(net) == 0:
            return {}
        
        # Salary analysis
        if not isinstance(salary, pd.Series):
            salary = pd.Series(salary if salary is not None else [], dtype=float)

        salary_non_zero = salary[salary > 0]

        if self.params.SALARY_BASELINE_MODE == "min_non_zero":
            baseline_salary = np.nanmin(salary_non_zero) if len(salary_non_zero) else 0
        else:
            baseline_salary = np.nanmedian(salary_non_zero) if len(salary_non_zero) else 0

        # Loan repayment analysis (last 1 month)
        repayment = repayment.iloc[-1] if len(repayment) >= 1 else 0

        dtir = repayment / baseline_salary if baseline_salary else 0

        base_net = np.nanmedian(net)
        gross_med = np.nanmedian(gross)

        eom_bal = self.df.groupby("monthyear")["balance"].last()

        reference_date = self.df["date"].max()
        cutoff_date = reference_date - pd.Timedelta(days=self.params.SALARY_RECENCY_DAYS)
        recency = bool(pd.notna(last_salary_date) and last_salary_date >= cutoff_date)

        return {
            "net_to_gross": base_net / gross_med if gross_med else 0,
            "inflow_median": gross_med,
            "base_net": base_net,
            "cv_net": None,
            "persistence": float(len(salary_non_zero) / len(gross)) if len(gross) > 0 else 0,
            "zeroing_rate": self.zeroing_rate,
            "disposable_income": max(
                baseline_salary * (self.params.REPAYMENT_FRACTION_SALARIED - dtir),
                0
            ),
            "slope": None,
            "betting_amount": self.betting_amount,
            "balance_floor": np.nanpercentile(eom_bal.values, 25),
            "salary": baseline_salary,
            "customer_type": "salaried",
            "existing_dtir": dtir,
            "recency": recency,
            "series_length": self.df['weekno'].nunique(),
        }
    
# ------------------------------------------------------ salary detection
    def detect_salary(self) -> tuple[pd.Series, Optional[pd.Timestamp], Optional[str]]:
        """Monthly salary amounts, the date of the last one"""
        labelled = self.df[self.df["category"].eq("salary")]
        if not labelled.empty:
            monthly = labelled.groupby("monthyear")["amount"].sum().sort_index()
            return monthly, labelled["date"].max()

        amounts, last_date = self._salary_by_pattern()
        if amounts:
            return pd.Series(amounts, dtype=float), last_date
        return pd.Series(dtype=float), None

    def _salary_by_pattern(self) -> tuple[list[float], Optional[pd.Timestamp]]:
        """Find a recurring, stable salary credit.

        A candidate must:
          * fall inside the configured amount range and the salary window,
          * arrive once per salary cycle, for enough cycles,
          * be stable in amount (CV below the threshold), and
          * land within a few days of its usual payday.

        Amounts are bucketed on a log scale, so "the same salary give or take a
        few percent" clusters together without any pairwise comparison. Paydays
        are measured against the END of the salary cycle's month rather than the
        day number, so a payday that straddles month end (31 Jan, 1 Mar, 30 Mar,
        1 May) reads as regular instead of swinging by 15 days.
        """
        s = self.params
        credits = self.df.loc[
            self.mask_credit
            & self.df["amount"].ge(s.income_param),
            ["date", "amount"],
        ].copy()
        if credits.empty:
            return [], None

        late, early = s.salary_window_days
        day = credits["date"].dt.day
        credits = credits[(day >= late) | (day <= early)].copy()
        if credits.empty:
            return [], None

        # Credits on the 1st-7th belong to the previous month's salary cycle.
        cycle_date = credits["date"].where(credits["date"].dt.day > early,
                                           credits["date"] - pd.DateOffset(months=1))
        credits["cycle"] = cycle_date.dt.to_period("M")
        credits["cluster"] = (np.log(credits["amount"]) / np.log1p(s.SALARY_DIFF_TOL)).round().astype(int)

        # One payment per cluster per cycle (a salary arrives once a month).
        # Cycles with two payments of the same size are dropped from here on, so
        # a one-off duplicate can't distort the stability or regularity checks.
        per_cycle = credits.groupby(["cluster", "cycle"]).size().reset_index(name="n")
        clean = credits.merge(per_cycle.loc[per_cycle["n"] == 1, ["cluster", "cycle"]],
                              on=["cluster", "cycle"], how="inner")

        cycles = clean.groupby("cluster")["cycle"].nunique()
        candidates = cycles[(cycles >= s.salary_min_cycles) & (cycles <= s.salary_max_cycles)]
        if candidates.empty:
            return [], None

        stats = clean.groupby("cluster")["amount"].agg(["mean", "std"]).loc[candidates.index]
        stats["cv"] = (stats["std"] / stats["mean"]).fillna(0)
        stable = stats[stats["cv"] < s.salary_max_cv]
        if stable.empty:
            return [], None

        kept = {}
        for cluster in stable.index:
            rows = clean[clean["cluster"] == cluster]
            if self._payday_is_regular(rows) and self._cycle_is_regular(rows):
                kept[cluster] = self._cycle_continuity(rows)
        if not kept:
            return [], None

        stable = stable.loc[list(kept)].assign(continuity=pd.Series(kept))
        best = stable.sort_values(["continuity", "mean"], ascending=False).index[0]
        rows = clean[clean["cluster"] == best].sort_values("date")
        return rows["amount"].tolist(), rows["date"].iloc[-1]

    @staticmethod
    def _cycle_ordinals(rows: pd.DataFrame) -> pd.Series:
        """Salary cycles as month numbers, de-duplicated and sorted."""
        cycles = rows["cycle"].astype("period[M]")
        return (cycles.dt.year * 12 + cycles.dt.month).drop_duplicates().sort_values()

    def _cycle_is_regular(self, rows: pd.DataFrame) -> bool:
        """Is the salary paid every cycle, with no long gap?

        Measured as the gap between *consecutive* cycles, not the spread around
        the median: a perfectly monthly salary has median-deviations that grow
        with the length of the history, so six consecutive months would fail a
        tolerance that three months passes.
        """
        ordinals = self._cycle_ordinals(rows)
        if len(ordinals) < 2:
            return False
        return bool(ordinals.diff().dropna().max() <= self.s.salary_max_cycle_gap)

    def _cycle_continuity(self, rows: pd.DataFrame) -> float:
        """1.0 when every month in the observed span was paid; lower with gaps.

        Used to rank candidates, so an unbroken monthly salary is preferred over
        one of the same size with a skipped month.
        """
        ordinals = self._cycle_ordinals(rows)
        if len(ordinals) < 2:
            return 0.0
        span = int(ordinals.iloc[-1] - ordinals.iloc[0]) + 1
        return round(len(ordinals) / span, 3)

    def _payday_is_regular(self, rows: pd.DataFrame) -> bool:
        """Do these payments land within `salary_max_date_drift` days of the usual payday?

        Each payment is positioned relative to the last day of its cycle month
        (31 Jan -> 0, 30 Jan -> -1, 1 Feb -> +1), which makes 28/29/30/31-day
        months comparable and keeps month-end paydays together.
        """
        if len(rows) < 2:
            return False
        cycle_end = rows["cycle"].astype("period[M]").dt.to_timestamp(how="end").dt.normalize()
        position = (rows["date"].dt.normalize() - cycle_end).dt.days
        return bool((position - position.median()).abs().max() <= self.params.salary_max_date_drift)

    def compute(self):
        """Entry point: select aggregation method based on salary presence."""

        repayment = self.data.get('loan_repayment', pd.Series(dtype=float))

        salary, last_date = self.detect_salary()
        if len(salary) and float(salary.sum()) > 0:
            result = self.monthly_aggregate(salary, last_date, repayment)
        else:
            result = self.weekly_aggregate(repayment)
        
        self.df = None
        self.mask_transfer = None
        self.mask_salary = None
        self.mask_betting = None
        self.all = None
        self.mask_credit = None
        return result
