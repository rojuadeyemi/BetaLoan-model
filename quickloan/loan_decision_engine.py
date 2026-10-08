"""Main loan evaluation pipeline orchestrator."""
from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np

from personal.data_extraction import DataExtractor
from quickloan.data_aggregator import Aggregator
from quickloan.qualifier import LoanQualifier
from quickloan.assess import ScoreCalculator
from quickloan.optional import OptionalParams
from quickloan.bnpl_schedule import ITEM_SCHEDULE
from quickloan.crc_scoring import score_crc_report
from quickloan.bnpl_assess import BNPLScoreCalculator

logger = logging.getLogger(__name__)

EXTRA_CASH_FIELDS = (
    "net_to_gross", "inflow_median", "base_net", "cv_net", "persistence",
    "zeroing_rate", "disposable_income", "slope", "credit_score",
    "balance_floor", "salary", "existing_dtir", "recency", "risk_score",
    "risk_band", "max_tenor", "pricing", "installment", "principal_offer",
    "max_yield",
)


def _to_native(obj: Any) -> Any:
    """Recursively convert numpy scalars/arrays to JSON-serialisable Python types."""
    if isinstance(obj, np.generic):          # covers integer, floating, bool_, str_
        return obj.item()
    if isinstance(obj, np.ndarray):
        return [_to_native(v) for v in obj.tolist()]
    if isinstance(obj, dict):
        return {k: _to_native(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_native(v) for v in obj]
    return obj


class BNPLError(Exception):
    """Business-rule rejection — safe to surface to the client."""

    def __init__(self, code: str, message: str, **context):
        self.code = code
        self.message = message
        self.context = context
        super().__init__(f"{code}: {message}")

    def to_dict(self) -> dict:
        return {"error_code": self.code, "message": self.message, **self.context}


class _ManualScore:
    """Wraps a pre-computed bureau score so it matches the BureauScoreResult interface."""

    def __init__(self, total_score: float):
        self.total_score = total_score
        self.has_record = True


class QuickLoan:
    """
    End-to-end underwriting pipeline:
    Qualification - ETL - Aggregation - Scoring

    Cheap eligibility checks run BEFORE statement extraction, so a disqualified
    applicant never pays for the parse.
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
        params: OptionalParams | None = None,
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

        self.params = params or OptionalParams()
        self.reasons: list[dict] = []

        # If a numeric score is provided directly, wrap it; otherwise parse CRC report.
        if isinstance(credit_score, (int, float)) and not isinstance(credit_score, bool):
            self.score = _ManualScore(float(credit_score))
        else:
            self.score = score_crc_report(credit_score)

        self.credit_score = getattr(self.score, "total_score", None)

    # ---------------------------------------------------------------- helpers

    @staticmethod
    def _empty_result(reasons: list[dict]) -> dict:
        extra_cash = dict.fromkeys(EXTRA_CASH_FIELDS, None)
        extra_cash["customer_type"] = "unknown"
        extra_cash["status"] = "ineligible"
        extra_cash["ineligibility_reasons"] = reasons
        bnpl = {"status": "ineligible", "credit_limits": {}, "ineligibility_reasons": reasons}
        return {
            "extra_cash": extra_cash,
            "bnpl": bnpl,
        }

    def _reject(self, code: str, message: str) -> dict:
        self.reasons.append({"reason_code": code, "reason_message": message})
        logger.warning("Rejected: %s - %s", code, message)
        return self._empty_result(self.reasons)

    # ------------------------------------------------------------ pipeline
    def _qualify(self) -> bool:
        q = LoanQualifier(
            self.date_of_birth,
            self.user_agent_str,
            self.location,
            self.tier,
            params=self.params,
        )
        ok = q.is_qualified()
        self.reasons.extend(q.ineligibility_reasons)
        if not ok:
            logger.warning("Applicant disqualified: %s", q.ineligibility_reasons)
        return ok

    def _extract(self):
        df = DataExtractor(
            self.statement_data, current_balance=self.current_balance
        ).transform_data()
        return None if df.empty else df

    def _aggregate(self, df):
        return Aggregator(df, params=self.params).compute() or None

    def _score(self, result_dict):
        return ScoreCalculator(
            result_dict,
            self.score,
            self.on_time,
            self.late,
            self.due,
            params=self.params,
        ).assess_customer()

    def _bnpl_score(self, result_dict):
        return BNPLScoreCalculator(
            result_dict,
            self.score,
            self.date_of_birth,
            params=self.params,
        ).assess_customer()

    def get_decision(self) -> dict:
        # Idempotent: re-running must not double-append reasons.
        self.reasons = []

        # --- no credit report parsing for applicants we reject anyway.
        if not hasattr(self.score, "total_score"):
            return self._reject(
                "INVALID_CREDIT_REPORT",
                "No BODY node found in CRC Response or invalid credit report structure",
            )

        if self.score.total_score < self.params.MIN_CREDIT_SCORE:
            self.reasons.append(
                        {
                            'reason_code': 'LOW_CREDIT_SCORE',
                            'reason_message': f'Credit score {self.score.total_score} is below the minimum threshold of {self.params.MIN_CREDIT_SCORE}'
                        }
                    )
            return self._empty_result(self.reasons)

        if not self._qualify():
            return self._empty_result(self.reasons)

        df = self._extract()
        if df is None:
            return self._reject("NO_TRANSACTION_DATA", "No transaction data found")

        result_dict = self._aggregate(df)
        if result_dict is None:
            return self._reject("NO_CASHFLOW_DATA", "No cashflow data found")

        final, reasons = self._score(result_dict)
        self.reasons.extend(reasons)
        final["ineligibility_reasons"] = self.reasons

        # Calculate BNPL indicative offers
        bnpl_offer = self._bnpl_score(result_dict)
        final_result = {"extra_cash":_to_native(final),"bnpl":_to_native(bnpl_offer) }

        return final_result

    # ---------------------------------------------------------------- BNPL
    def bnpl_quote(self,asset_name, tenor, product_price,credit_limit,env='dev') -> dict:
        """Price known. Job: the actual plan."""

        # validate inputs
        tenor = str(tenor)
        n = validate_input(asset_name, tenor, product_price, credit_limit, env=env)

        rac = ITEM_SCHEDULE.get(env, 'dev').get(asset_name, {}).get(tenor)

        f, d = rac["tenor_fee"], rac["down_payment"]

        markup = int(product_price * (1 + f))

        required = markup * d
        compulsory = max(markup - required - credit_limit, 0)
        total_downpayment = math.ceil(required + compulsory)
        loan_amount = markup - total_downpayment
        processing_fee = self.params.BNPL_PROCESSING_FEE
        total_repayment = int(round(loan_amount * (1 + processing_fee)))

        return {
            "asset_name": asset_name,
            "tenor": tenor,
            "product_price": product_price,
            "credit_limit": credit_limit,
            "markup_price": markup,
            "required_downpayment": math.ceil(required),
            "compulsory_downpayment": math.ceil(compulsory),
            "total_downpayment": total_downpayment,
            "loan_amount": loan_amount,
            "total_repayment": total_repayment,
            "monthly_repayment": int(round(total_repayment / n))
        }


# -------------------------------------------------------------- validation
def validate_input(asset_name, tenor, price, credit_limit, env='dev') -> str:
    """Validate and return the NORMALISED tenor key. Callers must use the return value."""
    
    if credit_limit is None or credit_limit <= 0:
        raise BNPLError(
            "NO_CREDIT_LIMIT",
            "You do not have enough credit limit to purchase this item.",
        )

    item_schedule = ITEM_SCHEDULE.get(env)

    if asset_name not in item_schedule:
        raise BNPLError(
            "UNKNOWN_ASSET_TYPE",
            f"Product provided ({asset_name}) not available for financing.",
            available_options=sorted(item_schedule),
        )

    schedule = item_schedule[asset_name]

    if tenor not in schedule:
        raise BNPLError(
            "TENOR_UNAVAILABLE",
            f"Provided tenor ({tenor}) not available for {asset_name}.",
            available_options=sorted(schedule, key=int),
        )

    if not isinstance(price, (int, float)) or isinstance(price, bool) or price <= 0:
        raise BNPLError("INVALID_PRICE", "Item price must be a number greater than zero.")

    return int(tenor)
