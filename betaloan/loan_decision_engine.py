import logging
import numpy as np

from betaloan.data_extraction import DataExtractor
from betaloan.data_aggregator import Aggregator
from betaloan.qualifier import LoanQualifier
from betaloan.assess import ScoreCalculator
from betaloan.optional import OptionalParams

logger = logging.getLogger(__name__)

# =========================================================
# BETALOAN PIPELINE
# =========================================================

class BetaLoan:
    """
    End-to-end underwriting pipeline:
    ETL - Qualification - Aggregation - Scoring
    """

    def __init__(
        self,
        statement_data,
        user_agent_str,
        date_of_birth,
        location,
        credit_score,
        tier,
        on_time_repayment,
        late_repayment,
        due_date_repayment,
        params: OptionalParams | None = None
    ):

        self.statement_data = statement_data
        self.user_agent_str = user_agent_str
        self.date_of_birth = date_of_birth
        self.location = location

        self.score = credit_score
        self.tier = tier

        self.on_time = on_time_repayment
        self.late = late_repayment
        self.due = due_date_repayment

        self.params = params or OptionalParams()

        self.df = None
        self.reasons = []


    @staticmethod
    def _empty_result(reasons):
        
        return {'net_to_gross': None,
        'inflow_median': None,
        'base_net': None,
        'cv_net': None,
        'persistence': None,
        'zeroing_rate': None,
        'disposable_income': None,
        'slope': None,
        'betting_count': None,
        'balance_floor': None,
        'salary': None,
        'customer_type': 'unknown',
        'existing_dtir': None,
        'status': 'ineligible',
        'risk_score': None,
        'risk_band': None,
        'max_tenor': None,
        'pricing': None,
        'installment': None,
        'principal_offer': None,
        'max_yield': None,
        'ineligibility_reasons': reasons
        }

    def _extract(self):

        df = DataExtractor(self.statement_data).transform_data()

        if df.empty:
            self.reasons.append({
                "reason_code": "NO_TRANSACTION_DATA",
                "reason_message": "No transaction data found"
            })
            return None

        return df

    # -----------------------------------------------------

    def _qualify(self):

        q = LoanQualifier(
            self.date_of_birth,
            self.user_agent_str,
            self.location,
            self.score,
            self.tier,
            params=self.params
        )

        ok = q.is_qualified()
        self.reasons.extend(q.ineligibility_reasons)

        return ok

    # -----------------------------------------------------

    def _aggregate(self, df):
        return Aggregator(df, params=self.params).compute()

    # -----------------------------------------------------

    def _score(self, result_dict):

        scorer = ScoreCalculator(
            result_dict,
            self.score,
            self.on_time,
            self.late,
            self.due,
            params=self.params
        )

        return scorer.assess_customer()

    def get_decision(self):

        # Extract
        df = self._extract()
        if df is None:
            return self._empty_result(self.reasons)

        # Qualify
        if not self._qualify():
            return self._empty_result(self.reasons)

        # Aggregate
        result_dict = self._aggregate(df)

        # Score
        final,reasons = self._score(result_dict)
        logger.info(f"is_passed_underwriting={len(reasons) == 0}")

        # Merge ineligibility reasons from scorer
        self.reasons.extend(reasons)

        final["ineligibility_reasons"] = self.reasons

        # Convert all numpy types to native Python
        for k, v in final.items():
            if isinstance(v, (np.generic, np.integer, np.floating)):
                final[k] = v.item()  # .item() converts numpy type to native int/float
        return final
