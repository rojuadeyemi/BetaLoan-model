"""Main loan evaluation pipeline orchestrator."""
import logging
import numpy as np

from personal.data_extraction import DataExtractor
from quickloan.data_aggregator import Aggregator
from quickloan.qualifier import LoanQualifier
from quickloan.assess import ScoreCalculator
from quickloan.optional import OptionalParams
from quickloan.crc_scoring import score_crc_report
logger = logging.getLogger(__name__)


class _ManualScore:
    """Wraps a pre-computed bureau score so it matches the BureauScoreResult interface."""
    def __init__(self, total_score: float):
        self.total_score = total_score
        self.has_record = True


class QuickLoan:
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
        current_balance=None,
        params: OptionalParams | None = None
    ):

        self.statement_data = statement_data
        self.user_agent_str = user_agent_str
        self.date_of_birth = date_of_birth
        self.location = location
        self.tier = tier

        self.on_time = on_time_repayment
        self.late = late_repayment
        self.due = due_date_repayment
        self.current_balance = current_balance or 0
        self.credit_score = 0

        self.params = params or OptionalParams()

        self.df = None
        self.reasons = []

        # If a numeric score is provided directly, wrap it; otherwise parse CRC report.
        if isinstance(credit_score, (int, float)):
            self.score = _ManualScore(float(credit_score))
        else:
            self.score = score_crc_report(credit_score)


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
        'credit_score': None, # changed from betting_count
        'balance_floor': None,
        'salary': None,
        'customer_type': 'unknown',
        'existing_dtir': None,
        'status': 'ineligible',
        'recency':None,
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

        df = DataExtractor(self.statement_data, current_balance=self.current_balance).transform_data()

        if df.empty:
            logger.warning("No transaction data found during extraction")
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
            self.tier,
            params=self.params
        )

        ok = q.is_qualified()
        self.reasons.extend(q.ineligibility_reasons)
        if not ok:
            logger.warning("Applicant disqualified: %s", q.ineligibility_reasons)

        return ok

    # -----------------------------------------------------

    def _aggregate(self, df):
        result = Aggregator(df, params=self.params).compute()

        if not result:
            logger.warning("No cashflow data found during analysis")
            self.reasons.append({
                "reason_code": "NO_CASHFLOW_DATA",
                "reason_message": "No cashflow data found"
            })
            return None
        return result


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

        # check if the score object has the attribute 'total_score'
        if not hasattr(self.score, 'total_score'):
            self.reasons.append(
                {
                    'reason_code': 'INVALID_CREDIT_REPORT',
                    'reason_message': 'No BODY node found in CRC Response or invalid credit report structure'
                }
            )
            return self._empty_result(self.reasons)

        if self.score.total_score < self.params.MIN_CREDIT_SCORE:
            self.reasons.append(
                {
                    'reason_code': 'LOW_CREDIT_SCORE',
                    'reason_message': f'Credit score {self.score.total_score} is below the minimum threshold of {self.params.MIN_CREDIT_SCORE}'
                }
            )
            return self._empty_result(self.reasons)

        # Qualify
        if not self._qualify():
            return self._empty_result(self.reasons)

        # Aggregate
        result_dict = self._aggregate(df)
        if result_dict is None:
            return self._empty_result(self.reasons)
        del df  # Free DataFrame memory (5-10MB) after aggregation

        # Score
        final, reasons = self._score(result_dict)

        # Merge ineligibility reasons from scorer
        self.reasons.extend(reasons)

        final["ineligibility_reasons"] = self.reasons

        # Convert all numpy types to native Python
        for k, v in final.items():
            if isinstance(v, (np.generic, np.integer, np.floating)):
                final[k] = v.item()  # .item() converts numpy type to native int/float

        return final