"""Risk assessment and scoring logic."""

from abc import ABC, abstractmethod
from typing import Dict, Type, Tuple, Any
from quickloan.optional import OptionalParams
from quickloan.qualifier import LoanQualifier

class BaseAssessment(ABC):
    """
    Base class for risk assessment.
    Handles shared scoring logic, banding, and loan offer generation.
    """

    # Loan product schedules by customer type and risk band..
    _SALARIED_SCHEDULE = {
                'A': 1.0,
                'B': 0.85,
                'C':  0.75,
                'D': 0.55,
                'E': 0
            }
    _NON_SALARIED_SCHEDULE = {
                'A': 1.0,
                'B': 0.85,
                'C':  0.75,
                'D': 0.55,
                'E': 0
            }
    LOAN_SCHEDULES = {
            'salaried': _SALARIED_SCHEDULE,
            'non_salaried': _NON_SALARIED_SCHEDULE
    }


    def __init__(
        self,
        result_dict: Dict,
        score: Any,
        dob,
        params: OptionalParams
    ):
        self.dob = dob
        self.r = result_dict
        self.p = params
        self.score = score

        # Common thresholds
        self.ineligibility_reasons = []
        
        self.monthly_income = self.r.get('salary') if self.r.get('customer_type') == 'salaried' else self.r.get('inflow_median', 0) * 4
        

        betting_amount = self.r.get('betting_amount', 0)
        self.betting_ratio = betting_amount / self.monthly_income if self.monthly_income else 0

        #Betting check
        if self.betting_ratio > self.p.BETTING_RATE:
            self.ineligibility_reasons.append({
                'reason_code': 'EXCESSIVE_BETTING_ACTIVITY',
                'reason_message': f'Betting ratio {self.betting_ratio:.2%} exceeds maximum allowed {self.p.BETTING_RATE:.2%}'
            })

        # Income check
        if self.monthly_income < self.p.BNPL_income_param:
            self.ineligibility_reasons.append({
                'reason_code': 'INSUFFICIENT_INCOME',
                'reason_message': f'Customer monthly income {self.monthly_income} is below {self.p.BNPL_income_param} threshold'
            })

    @staticmethod
    def step_score(value, thresholds, weight):

        for t, m in thresholds:
            if value >= t:
                return weight * m
        return 0

    @staticmethod
    def band(score):
        for threshold, band in [(90,"A"),(80,"B"),(60,"C"),(50,"D")]:
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
    
    def age_score(self, dob) -> float:
        age = LoanQualifier.calculate_age(dob)
        if age is None:
            return 0
        if age < 22 or age > 55:
            return 0
        if 30 <= age <= 45:
            return 10
        if 46 <= age <= 55:
            return 8
        if 22 <= age <= 29:
            return 6
        return 0

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


        if not self.p.BNPL_SELF_EMPLOYED_ENABLED and self.r.get('customer_type') == 'non_salaried':
            self.ineligibility_reasons.append({
                                    'reason_code': 'SELF_EMPLOYED_BNPL_DISABLED',
                                    'reason_message': f'Self-employed customers are currently not eligible for BNPL'
                                })
            
            return {"status":"ineligible","credit_limits":{},"ineligibility_reasons":self.ineligibility_reasons}
        
        self.final_qualification()
        self.compute_risk()

        status = self.r.get('status','ineligible')

        if status == 'ineligible':

            return {"status":status,"credit_limits":{},"ineligibility_reasons":self.ineligibility_reasons}
        
        # Apply loan schedule based on customer type, and risk band.
        debt_service = self.LOAN_SCHEDULES.get(self.r['customer_type']).get(self.r['risk_band'])

        # Calculate Monthly disposable income
        one_month_credit_limit = self.r['disposable_income'] * debt_service
         
        CL = {}

        tenor_list = self.p.BNPL_TENOR_LIST_PROD if self.p.BNPL_PROD_ENABLED else self.p.BNPL_TENOR_LIST_DEV
        
        for tenor in tenor_list:
            if self.r['risk_score'] <50:
                CL[f"{tenor}"] = self.p.BNPL_MINIMUM_CL
            else:
                CL[f"{tenor}"] = one_month_credit_limit * tenor
    
        return {"status":status, "credit_limits":CL,"ineligibility_reasons":self.ineligibility_reasons}

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
            self.age_score(self.dob)
        ]

        risk = int(sum(scores))

        self.r.update({
            "risk_score": risk,
            "risk_band": self.band(risk),
        })


class NonSalaryCustomer(BaseAssessment):
    """Assessment model for non-salaried (self-employed) customers."""

    def final_qualification(self):
        """Validate non-salaried customer against thresholds."""

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
            self.age_score(self.dob)
        ]

        # Trend score
        slope = self.r.get('slope', -999)
        if slope > 0:
            scores.append(self.p.non_salary_trend_weight)
        elif slope <= 0:
            scores.append(self.p.non_salary_trend_weight * 0.5)

        risk = int(sum(scores))

        self.r.update({
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

class BNPLScoreCalculator:
    """
    Public interface for risk assessment and scoring.
    Orchestrates the full scoring pipeline.
    """

    def __init__(
        self,
        result_dict,
        score,
        dob,
        params: OptionalParams
    ):
        self.result_dict = result_dict
        self.score = score
        self.dob = dob
        self.p = params

    def assess_customer(self) -> Tuple[Dict, list]:
        """Execute full assessment and return decision with reasons."""
        processor = AssessmentFactory.create_processor(
            self.result_dict,
            self.score,
            self.dob,
            self.p
        )

        return processor.calculate()
