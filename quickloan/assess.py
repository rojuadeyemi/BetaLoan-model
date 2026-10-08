"""Risk assessment and scoring logic."""

from abc import ABC, abstractmethod
from typing import Dict, Type, Tuple, Any
from quickloan.optional import OptionalParams

class BaseAssessment(ABC):
    """
    Base class for risk assessment.
    Handles shared scoring logic, banding, and loan offer generation.
    """

    # Loan product schedules by customer type and risk band.
    # Keep both schedules available to support controlled rollouts.
    _SALARIED_SCHEDULE = {
        'A': {'multiplier': 1.0,  'max_tenor': 30, 'pricing': 0.003},
        'B': {'multiplier': 0.85, 'max_tenor': 30, 'pricing': 0.003},
        'C': {'multiplier': 0.72, 'max_tenor': 30, 'pricing': 0.0035},
        'D': {'multiplier': 0.50, 'max_tenor': 30, 'pricing': 0.004},
    }
    
    _NON_SALARIED_SCHEDULE = {
        'A': {'multiplier': 1.0,  'max_tenor': 14, 'pricing': 0.006},
        'B': {'multiplier': 0.85, 'max_tenor': 14, 'pricing': 0.0065},
        'C': {'multiplier': 0.72, 'max_tenor': 14, 'pricing': 0.007},
        'D': {'multiplier': 0.50, 'max_tenor': 14, 'pricing': 0.008},
    }
    LOAN_SCHEDULES = {
        'zedvance_short_tenor': {
            'salaried': _SALARIED_SCHEDULE,
            'non_salaried': _NON_SALARIED_SCHEDULE,
        },
        'quickloan_legacy': {
            'salaried': _SALARIED_SCHEDULE,
            'non_salaried': _NON_SALARIED_SCHEDULE,
        },
    }


    def __init__(
        self,
        result_dict: Dict,
        score: Any,
        on_time: int,
        late: int,
        due: int,
        params: OptionalParams
    ):
        self.r = result_dict
        self.on_time = on_time
        self.late = late
        self.due = due
        self.p = params
        self.score = score
        self.monthly_income = self.r.get('salary') if self.r.get('customer_type') == 'salaried' else self.r.get('inflow_median', 0)*4

        # Common thresholds
        self.ineligibility_reasons = []

        betting_amount = self.r.get('betting_amount', 0)
        self.betting_ratio = betting_amount / self.monthly_income if self.monthly_income else 0

        #Betting check
        if self.betting_ratio > self.p.BETTING_RATE:
            self.ineligibility_reasons.append({
                'reason_code': 'EXCESSIVE_BETTING_ACTIVITY',
                'reason_message': f'Betting ratio {self.betting_ratio:.2%} exceeds maximum allowed {self.p.BETTING_RATE:.2%}'
            })

        # Income check
        income_param = self.p.income_param if self.r.get('customer_type') == 'salaried' else self.p.self_employed_income_param
        if self.monthly_income < income_param:
            self.ineligibility_reasons.append({
                'reason_code': 'INSUFFICIENT_INCOME',
                'reason_message': f'Customer monthly income {self.monthly_income} is below {income_param} threshold'
            })

    def _loan_schedule(self) -> Dict:
        """Resolve active pricing schedule by configured product policy mode."""
        return self.LOAN_SCHEDULES.get(
            self.p.PRICING_SCHEDULE_VERSION,
            self.LOAN_SCHEDULES['zedvance_short_tenor'],
        )

    @staticmethod
    def step_score(value, thresholds, weight):

        for t, m in thresholds:
            if value >= t:
                return weight * m
        return 0

    @staticmethod
    def band(score):
        for threshold, band in [(85,"A"),(75,"B"),(55,"C"),(50,"D")]:
            if score >= threshold:
                return band
        return "E"

    # Shared scoring methods
    @property
    def betting_score(self):
        """Score based on betting activity (lower is better)."""
        return self.step_score(
            self.betting_ratio,
            [(0.21, 0), (0.1, 0.5), (0.05, 0.8), (0, 1)],
            self.p.betting_weight
        )
    
    @property
    def zeroing_rate_score(self):
        """Score based on account going to zero balance (lower is better)."""
        return self.step_score(
            self.r.get("zeroing_rate", 1),
            [(0.41, 0), (0.26, 0.3), (0.11, 0.6), (0, 1)],
            self.p.zeroing_weight
        )

    @property
    def credit_score(self):
        if not hasattr(self.score, 'total_score'):
            return 0
        return self.score.total_score
    
    @property
    def performance_score(self):
        total = self.on_time + self.late + self.due

        # if it's a first timer
        if total == 0:
            return self.p.PERFORMANCE_NEUTRAL*self.p.performance_weight

        raw = (
            self.on_time * self.p.ON_TIME_REPAYMENT
            + self.due * self.p.DUE_DATE_REPAYMENT
            + self.late * self.p.LATE_REPAYMENT
        ) / total

        # Allows for penalization
        return self.p.performance_weight * raw/2

    @abstractmethod
    def compute_risk(self):
        """Compute risk score (implemented by subclasses)."""
        pass

    @abstractmethod
    def final_qualification(self):
        """Check final qualification criteria (implemented by subclasses)."""
        pass


    def calculate(self):
        """Execute qualification and scoring pipeline."""
        self.final_qualification()
        self.compute_risk()

        #remove series lenght from result dict
        self.r.pop('series_length', None)

        # Hard risk guardrail before offer generation.
        if self.r.get('risk_score', 0) < self.p.MIN_RISK_SCORE:
            self.r['status'] = 'ineligible'
            self.ineligibility_reasons.append({
                'reason_code': 'LOW_RISK_SCORE',
                'reason_message': f"Customer total risk score ({self.r.get('risk_score', 0):.2f}) is less than minimum of {self.p.MIN_RISK_SCORE:.0f} required"
            })

        if self.r.get('status','ineligible') == 'ineligible':
            self.r.update({
                'max_tenor': 0, 'pricing': 0, 'installment': 0,
                'principal_offer': 0, 'max_yield': 0
            })

            return self.r, self.ineligibility_reasons

        # Apply loan schedule based on customer type, risk band, and policy mode.
        loan_schedule = self._loan_schedule()
        self.r.update(loan_schedule[self.r['customer_type']][self.r['risk_band']])

        # Calculate Daily installment
        self.r['installment']= self.r['multiplier']*self.r['disposable_income']/30

        # Calculate principal offer using standard loan formula
        max_amount = self.p.MAX_ELIGIBLE_AMOUNT.get(self.r['customer_type'], {}).get(self.r['risk_band'], 0)
        interest_factor = 1 + self.r.get('pricing',0) * self.r.get('max_tenor',0)
        self.r['principal_offer'] = self.r['installment'] * self.r.get('max_tenor',0) / interest_factor
        if self.r['principal_offer'] > max_amount:
            # cap the principat and recompute daily installment
            self.r['principal_offer'] = max_amount
            self.r['installment'] = (
                self.r['principal_offer']
                * interest_factor
                / self.r.get('max_tenor')
            )
        if self.r['principal_offer'] <= self.p.MIN_ELIGIBLE_AMOUNT:
                    # cap the principat and recompute daily installment
                    self.r['principal_offer'] = self.p.MIN_ELIGIBLE_AMOUNT
                    self.r['installment'] = (
                        self.r['principal_offer']
                        * interest_factor
                        / self.r.get('max_tenor')
                    )

        self.r['max_yield'] = self.r['principal_offer'] * self.r['max_tenor'] * self.r['pricing']

        # Clean up
        self.r.pop('multiplier', None)

        return self.r, self.ineligibility_reasons

class SalaryCustomer(BaseAssessment):
    """Assessment model for salaried customers."""

    def final_qualification(self):
        """Validate salaried customer against thresholds."""
        recency = self.r.get("recency", True)
        dtir = self.r.get("existing_dtir", 0)

        # DTI check
        if dtir > self.p.DTIR:
            self.ineligibility_reasons.append({
                'reason_code': 'DTIR_TOO_HIGH',
                'reason_message': f'Debt-to-Income Ratio of {dtir:.2%} exceeds maximum threshold of {self.p.DTIR:.2%}'
            })

        # Salary recency check
        if not recency:
            self.ineligibility_reasons.append({
                'reason_code': 'STALE_STATEMENT',
                'reason_message': f'Last salary receipt exceeds allowed recency window of {self.p.SALARY_RECENCY_DAYS} days'
            })

        self.r["status"] = "eligible" if not self.ineligibility_reasons else "ineligible"

    def compute_risk(self):
        """Calculate risk score for salaried customer."""
        scores = [
            # Income score
            self.step_score(
                self.r.get("salary", 0),
                [(500000, 1), (250000, .75), (150000, .5), (100000, .25)],
                self.p.salary_income_weight
            ),

            # Net surplus score
            self.step_score(
                self.r.get("base_net", 0),
                [(200000,1), (100000,0.8), (50000,0.6), (30000,0.2)],
                self.p.salary_net_surplus_weight
            ),

            # Balance floor score
            self.step_score(
                self.r.get("balance_floor", 0),
                [(150000, 1), (75000, .6), (30000, .3)],
                self.p.salary_balance_floor_weight
            ),

            # Persistence score
            self.step_score(
                self.r.get("persistence", 0),
                [(0.9,1),(0.8,0.75),(0.6,0.5),(0.4,0.3)],
                self.p.salary_persistence_weight
            ),

            # Shared scores
            self.credit_score,
            self.betting_score,
            self.zeroing_rate_score,
            self.performance_score
        ]

        risk = int(sum(scores))

        self.r.update({
            "credit_score":self.credit_score,
            "risk_score": risk,
            "risk_band": self.band(risk),
        })


class NonSalaryCustomer(BaseAssessment):
    """Assessment model for non-salaried (self-employed) customers."""

    def final_qualification(self):
        """Validate non-salaried customer against thresholds."""

        # Thresholds
        #min_series_length = self.p.MIN_WEEKS_FOR_SLOPE
        #series_length = self.r.get('series_length')


        #has_sufficient_weeks = series_length >= min_series_length

        """if not has_sufficient_weeks:
            self.ineligibility_reasons.append({
                'reason_code': 'INSUFFICIENT_WEEKLY_DATA',
                'reason_message': f'Only {series_length} weeks of data available; minimum of {min_series_length} required'
            })"""

        self.r["status"] = "eligible" if not self.ineligibility_reasons else "ineligible"

    def compute_risk(self):
        """Calculate risk score for non-salaried customer."""
        scores = [
            # Persistence score
            self.r.get("persistence", 0) * self.p.non_salary_persistence_weight,

            # Volatility score
            self.step_score(
                self.r.get("cv_net", 1),
                [(1.5, 0.4), (0.8, 0.6), (0.6, 0.8), (0, 1)],
                self.p.non_salary_volatility_weight
            ),

            # Balance floor score
            self.step_score(
                self.r.get("balance_floor", 0),
                [(5000, 1), (3000, .6), (1000, .3)],
                self.p.non_salary_balance_floor_weight
            ),

            # Shared scores
            self.credit_score,
            self.betting_score,
            self.zeroing_rate_score,
            self.performance_score
        ]

        # Trend score
        slope = self.r.get('slope', -999)
        if slope > 0:
            scores.append(self.p.non_salary_trend_weight)
        elif slope <= 0:
            scores.append(self.p.non_salary_trend_weight * self.p.TREND_NEUTRAL)

        risk = int(sum(scores))

        self.r.update({
            "credit_score":self.credit_score,
            "risk_score": risk,
            "risk_band": self.band(risk),
        })


class AssessmentFactory:
    """Factory for creating appropriate assessment processor."""

    MAP: Dict[str, Type[BaseAssessment]] = {
        "salaried": SalaryCustomer,
        "non_salaried": NonSalaryCustomer
    }

    @classmethod
    def create_processor(cls, result_dict, *args, **kwargs):
        """Create assessment processor based on customer type."""
        processor_class = cls.MAP.get(result_dict.get("customer_type", "non_salaried"))
        if not processor_class:
            raise ValueError(f"Unknown customer type: {result_dict.get('customer_type')}")
        return processor_class(result_dict, *args, **kwargs)

class ScoreCalculator:
    """
    Public interface for risk assessment and scoring.
    Orchestrates the full scoring pipeline.
    """

    def __init__(
        self,
        result_dict,
        score,
        on_time,
        late,
        due,
        params: OptionalParams
    ):
        self.result_dict = result_dict
        self.score = score
        self.on_time = on_time
        self.late = late
        self.due = due
        self.p = params

    def assess_customer(self) -> Tuple[Dict, list]:
        """Execute full assessment and return decision with reasons."""
        processor = AssessmentFactory.create_processor(
            self.result_dict,
            self.score,
            self.on_time,
            self.late,
            self.due,
            self.p
        )

        return processor.calculate()
