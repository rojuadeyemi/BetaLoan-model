import numpy as np
from betaloan.optional import OptionalParams

class Aggregator:
    """
    Fast + memory-efficient feature aggregation for underwriting.
    Designed for large transaction datasets.
    """

    def __init__(self, df, params: OptionalParams):
        self.df = df

        self.params = params

        # -------------------------
        # Precompute ONCE for speed
        # -------------------------
        cat = df["category"]
        typ = df["type"]

        self.mask_transfer = cat.eq("transfer")
        self.mask_salary = cat.eq("salary")
        self.mask_betting = cat.eq("betting")
        self.all = ~cat.eq("others")

        self.mask_credit = typ.eq("credit")

        self.salary_check = self.mask_salary.sum()
        self.betting_count = self.mask_betting.sum()

        # EOD balances (used by both paths)
        self.eod_bal = df.groupby("date")["balance"].last().dropna()

        # Zeroing rate
        self.zeroing_rate = self._compute_zeroing_rate()

    # ---------------------------------------------------
    # Helpers
    # ---------------------------------------------------
    @staticmethod
    def clamp(x, lo, hi):
        return np.clip(x, lo, hi)

    def _compute_zeroing_rate(self):
        if len(self.eod_bal) == 0:
            return 1.0

        inflow = (
            self.df.loc[self.mask_credit & self.mask_transfer]
            .groupby("date")["amount"]
            .sum()
        )

        common = self.eod_bal.index.intersection(inflow.index)

        median_inflow = (
            np.nanmedian(inflow.loc[common].values) if len(common) else 0
        )

        threshold = max(
            self.params.ZEROING_BASE,
            0.01 * median_inflow
        )

        return float(np.mean(self.eod_bal.values <= threshold))

    # ---------------------------------------------------
    # Core reusable aggregation
    # ---------------------------------------------------
    def _aggregate_period(self, mask,index_col):
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
            return np.zeros(0), np.zeros(0), summary.index

        net = summary.get("credit", 0) - summary.get("debit", 0)
        gross = summary.get("credit", 0)

        return net.values, gross.values

    # ---------------------------------------------------
    # Weekly (non-salary)
    # ---------------------------------------------------
    def weekly_aggregate(self):
        net, gross = self._aggregate_period(self.mask_transfer, "weekno")

        if len(net) == 0:
            return {}

        # Clamp outliers
        p10, p90 = np.nanpercentile(net, [10, 90])
        base_net = np.nanmedian(self.clamp(net, p10, p90))
        gross_med = np.nanmedian(gross)

        mean_net = np.nanmean(net)
        cv = np.nanstd(net) / abs(mean_net) if abs(mean_net) > 0 else 1
        vol_penalty = self.clamp(cv, 0, 2)

        persistence = float(np.mean(net >= 0))
        persist_penalty = 1 if persistence >= 0.7 else persistence / 0.7

        di = base_net * (
            1 - self.params.VOLATILITY_COEFFICIENT * vol_penalty
        ) * persist_penalty

        # Fit regression on net inflow
        time_t =  np.arange(len(net))

        slope = np.polyfit(time_t, net, 1)[0]

        # Obtain 25th percentile of the end of week balances
        bal_floor = np.nanpercentile(
            self.df.groupby("weekno")["balance"].last().values,
            25
        )

        return {
            "net_to_gross": base_net / gross_med if gross_med else 0,
            "inflow_median": gross_med,
            "base_net": base_net,
            "cv_net": vol_penalty,
            "persistence": persistence,
            "zeroing_rate": self.zeroing_rate,
            "disposable_income": (
                self.params.REPAYMENT_FRACTION_NON_SALARIED * di
            ),
            "slope": slope,
            "betting_count": self.betting_count,
            "balance_floor": bal_floor,
            "salary": None,
            "customer_type": "non_salaried",
            "existing_dtir": None,
        }

    # ---------------------------------------------------
    # Monthly (salary)
    # ---------------------------------------------------
    def monthly_aggregate(self):
        net, gross = self._aggregate_period(self.all, "monthyear")

        if len(net) == 0:
            return {}
        
        data = self.df.pivot_table(
                index='monthyear',
                columns="category",
                values="amount",
                aggfunc="sum",
                fill_value=0,
            )
        # Salary
        salary = data['salary']

        median_salary = np.nanmedian(salary) if len(salary) else 0

        # pick the last 2 values
        repayment = data['loan_repayment'][-2:]

        #pick the average
        mean_repayment = np.nanmean(repayment) if len(repayment) else 0
        dtir = mean_repayment / median_salary if median_salary else 0

        base_net = np.nanmedian(net)
        gross_med = np.nanmedian(gross)

        eom_bal = self.df.groupby("monthyear")["balance"].last()

        return {
            "net_to_gross": base_net / gross_med if gross_med else 0,
            "inflow_median": gross_med,
            "base_net": base_net,
            "cv_net": None,
            "persistence": float(len(salary) / len(gross)),
            "zeroing_rate": self.zeroing_rate,
            "disposable_income": median_salary * (
                self.params.REPAYMENT_FRACTION_SALARIED - dtir
            ) if self.params.REPAYMENT_FRACTION_SALARIED > dtir else 0,
            "slope": None,
            "betting_count": self.betting_count,
            "balance_floor": np.nanpercentile(eom_bal.values, 25),
            "salary": median_salary,
            "customer_type": "salaried",
            "existing_dtir": dtir,
        }

    # ---------------------------------------------------
    # Entry point
    # ---------------------------------------------------
    def compute(self):
        if self.salary_check > 0:
            return self.monthly_aggregate()
        return self.weekly_aggregate()
