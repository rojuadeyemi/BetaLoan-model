from abc import ABC, abstractmethod
from typing import Dict, Type
from enum import Enum
from betaloan.optional import OptionalParams

class CustomerType(Enum):
    SALARIED = "salaried"
    NONSALARIED = "non_salaried"

class BaseAssessment(ABC):
    """
    Shared logic for all customers.
    Handles:
    - step scoring
    - shared features (betting, zeroing, repayment performance)
    - banding
    """

    # Loan Schedule
    DATA = {'salaried':{
        'A': {
            'multiplier': 1,
            'max_tenor': 30,
            'pricing': 0.003        # daily interest rate
        },
        'B': {
            'multiplier': 0.85,
            'max_tenor': 30,
            'pricing': 0.005        # daily interest rate
        },
        'C': {
            'multiplier': 0.65,
            'max_tenor': 30,
            'pricing': 0.006        # daily interest rate
        },
        'D': {
            'multiplier': 0.35,
            'max_tenor': 30,
            'pricing': 0.007        # daily interest rate
        }
    },
    "non_salaried":{
        'A': {
            'multiplier': 1,
            'max_tenor': 4,
            'pricing': 0.028        # weekly interest rate
        },
        'B': {
            'multiplier': 0.85,
            'max_tenor': 4,
            'pricing': 0.035        # weekly interest rate
        },
        'C': {
            'multiplier': 0.65,
            'max_tenor': 4,
            'pricing': 0.042        # weekly interest rate
        },
        'D': {
            'multiplier': 0.35,
            'max_tenor': 4,
            'pricing': 0.049        # weekly interest rate
        }
    }
    }

    def __init__(
        self,
        result_dict: Dict,
        score: float,
        on_time: int,
        late: int,
        due: int,
        params: OptionalParams
    ):
        self.r = result_dict

        self.on_time = on_time
        self.late = late
        self.due = due

        self.p =  params
        self.score = score or self.p.MIN_CREDIT_SCORE

        # Common Thresholds
        self.benchmark_dtir = self.p.DTIR
        self.min_persistence = self.p.MIN_PERSISTENCE
        self.min_net_surplus = self.p.MIN_NET_SURPLUS
        self.max_zeroing = self.p.MAX_ZEROING

        self.ineligibility_reasons = []

        # Check betting count
        betting_count = self.r['betting_count']
        if betting_count > 3:
            self.ineligibility_reasons.append({
                'reason_code': 'EXCESSIVE_BETTING_ACTIVITY',
                'reason_message': f'Betting transaction count {betting_count} exceeds maximum allowed of 3'
            })

    @staticmethod
    def step_score(value, thresholds, weight):
        """
        thresholds = [(min_value, multiplier), ...]
        sorted descending
        """
        for t, m in thresholds:
            if value >= t:
                return weight * m
        return 0

    @staticmethod
    def band(score):
        if score >= 85:
            return "A"
        if score >= 75:
            return "B"
        if score >= 55:
            return "C"
        return "D"

    # =====================================================
    # --------- SHARED SCORES ------------------------------
    # =====================================================

    def betting_score(self):
        return self.step_score(
            -self.r.get("betting_count", 0),
            [(-1, 1), (-3, 0.3), (-999, 0)],
            self.p.betting_weight)

    def zeroing_rate_score(self):
        
        return self.step_score(
            -self.r.get("zeroing_rate", 1),
            [(-0.1, 1), (-0.25, 0.6), (-0.4, 0.3)],
            self.p.zeroing_weight
        )

    def performance_score(self):
        total = self.on_time + self.late + self.due

        # if it's a first timer, return 0
        if total == 0:
            return 0

        raw = (
            self.on_time * self.p.ON_TIME_REPAYMENT
            + self.due * self.p.DUE_DATE_REPAYMENT
            + self.late * self.p.LATE_REPAYMENT
        ) / total

        scaled = (raw + 2) / 4

        return (
            self.p.performance_weight
            if scaled >= 0.8
            else 0
        )


    @abstractmethod
    def compute_risk(self):
        pass

    @abstractmethod
    def final_qualification(self):
        pass

    def calculate(self):
        self.final_qualification()
        self.compute_risk()

        self.r.update(self.DATA[self.r['customer_type']][self.r['risk_band']])
        if self.r['customer_type']=="salaried":
            # Daily installment
            self.r['installment']= self.r['multiplier']*self.r['disposable_income']/self.r['max_tenor']
        else:
            # Weekly Installment
            self.r['installment']= self.r['multiplier']*self.r['disposable_income']

        self.r['principal_offer'] = self.r['installment']*self.r['max_tenor']/(1+self.r['pricing']*self.r['max_tenor'])
        self.r['max_yield'] = self.r['principal_offer']*self.r['max_tenor']*self.r['pricing']

        # remove multiplier from the dict
        self.r.pop('multiplier',None)

        return self.r


# =========================================================
# SALARIED CUSTOMER
# =========================================================

class SalaryCustomer(BaseAssessment):

    # -----------------------------------------------------
    # QUALIFICATION
    # -----------------------------------------------------
    def final_qualification(self):

        salary = self.r["salary"]
        persistence = self.r["persistence"]
        surplus = self.r["base_net"]
        zeroing = self.r["zeroing_rate"]
        dtir = self.r["existing_dtir"]
        #bal_floor = self.r["balance_floor"]

        # Benchmarks
        #bal_floor_benchmark = self.p.SAL_BALANCE_FLOOR
        income_param = self.p.income_param_salary


        """if bal_floor < bal_floor_benchmark:
            self.ineligibility_reasons.append({
                'reason_code': 'LOW_BALANCE_FLOOR ',
                'reason_message': f'Month end balance floor of {bal_floor} is too low to support repayment'
            })"""
        
        if dtir > self.benchmark_dtir:
            self.ineligibility_reasons.append({
                'reason_code': 'DTIR_TOO_HIGH',
                'reason_message': f'Debt-to-Income Ratio of {dtir:.2%} exceeds maximum threshold of {self.benchmark_dtir}'
            })

        if salary < income_param:
            self.ineligibility_reasons.append({
                'reason_code': 'INSUFFICIENT_INCOME',
                'reason_message': f'Customer monthly salary {salary} is below {income_param} threshold'
            })

        if persistence < self.min_persistence:
            self.ineligibility_reasons.append({
                'reason_code': 'LOW_PERSISTENCE',
                'reason_message': f'Salary observed in {persistence:.0f} of the total months, less than {self.min_persistence} threshold'
            })

        if surplus <= self.min_net_surplus:
            self.ineligibility_reasons.append({
                'reason_code': 'NEGATIVE_NET_CASHFLOW',
                'reason_message': f'Net cashflow ({surplus:.0f}) less than {self.min_net_surplus} is not acceptable'
            })

        if zeroing > self.max_zeroing:
            self.ineligibility_reasons.append({
                'reason_code': 'HIGH_ZEROING',
                'reason_message': f'Account has high proportion ({zeroing:.0%}) of days hitting zero balance'
            })


        eligible = (
            salary >= income_param
            and dtir <= self.benchmark_dtir
            and persistence >= self.min_persistence
            and surplus > self.min_net_surplus
            and zeroing <= self.max_zeroing
            #and bal_floor >= bal_floor_benchmark
        )

        self.r["status"] = "eligible" if eligible else "ineligible"

    # -----------------------------------------------------
    # RISK
    # -----------------------------------------------------
    def compute_risk(self):

        scores = [
            self.step_score(
                self.r["salary"],
                [(500000,1),(250000,.75),(150000,.5),(100000,.25)],
                self.p.salary_income_weight
            ),

        self.step_score(
            self.r["base_net"],
            [(200000,1), (100000,.67), (50000,.33)],
            self.p.salary_net_surplus_weight
        )
            ,

            self.step_score(
                self.r["balance_floor"],
                [(150000,1),(75000,.6),(30000,.3)],
                self.p.salary_balance_floor_weight
            ),

            self.step_score(
                self.r["persistence"],
                [(0.9,1),(0.8,.67),(0.65,.33)],
                self.p.salary_persistence_weight
            ),

            self.step_score(
                self.score,
                [(750,1),(700,.8),(650,.5)],
                self.p.salary_credit_score_weight
            ),

            self.betting_score(),
            self.zeroing_rate_score(),
            self.performance_score()
        ]

        risk = sum(scores)

        self.r.update({
            "risk_score": risk,
            "risk_band": self.band(risk)
        })

# =========================================================
# NON SALARIED CUSTOMER
# =========================================================

class NonSalaryCustomer(BaseAssessment):

    def final_qualification(self):

        income = self.r['inflow_median']
        #bal_floor = self.r['balance_floor']
        slope = self.r['slope']
        persistence = self.r["persistence"]
        surplus = self.r["base_net"]
        zeroing = self.r["zeroing_rate"]
        net_to_gross = self.r['net_to_gross']

        # Thresholds
        #bal_floor_param = self.p.NON_SAL_BALANCE_FLOOR
        min_trend_coef = self.p.MIN_SLOPE_COEF
        min_income = self.p.income_param_non_salary
        min_net_to_gross = self.p.MIN_NET_TO_GROSS

        """if bal_floor > bal_floor_param:
            self.ineligibility_reasons.append({
                'reason_code': 'LOW_BALANCE_FLOOR ',
                'reason_message': f'Account balance floor {bal_floor:.2f} is too low to support repayment'
            })"""

        if slope < min_trend_coef:
            self.ineligibility_reasons.append({
                'reason_code': 'DETERIORATING_TREND ',
                'reason_message': f'Trend coefficienet {slope:.2f} shows that cash flow is declining over the observation period'
            })

        if income < min_income:
            self.ineligibility_reasons.append({
                'reason_code': 'INSUFFICIENT_INFLOW',
                'reason_message': f'Customer inflow {income} is below {min_income} threshold'
            })

        if persistence < self.min_persistence:
            self.ineligibility_reasons.append({
                'reason_code': 'LOW_PERSISTENCE',
                'reason_message': f'Salary observed in {persistence} of the total weeks, less than {self.min_persistence:.0%} threshold'
            })

        if net_to_gross < min_net_to_gross :
            self.ineligibility_reasons.append({
                'reason_code': 'LOW_NET_GROSS',
                'reason_message': f'Ratio of Net-Inflow to Gross-Inflow {net_to_gross:.0f} is below the threshold of {min_net_to_gross}'
            })

        if surplus <=self.min_net_surplus :
            self.ineligibility_reasons.append({
                'reason_code': 'NEGATIVE_NET_CASHFLOW',
                'reason_message': f'Net cashflow ({surplus:.0f}) less than {self.min_net_surplus} is not acceptable'
            })

        if zeroing > self.max_zeroing:
            self.ineligibility_reasons.append({
                'reason_code': 'HIGH_ZEROING',
                'reason_message': f'Account has high proportion ({zeroing:.0%}) of days hitting zero balance'
            })


        eligible = (
            income >= min_income
            and persistence >= self.min_persistence
            #and bal_floor >= bal_floor_param
            and zeroing <= self.max_zeroing
            and slope >= min_trend_coef
            and surplus > self.min_net_surplus
            and net_to_gross >= min_net_to_gross
        )

        self.r["status"] = "eligible" if eligible else "ineligible"

    def compute_risk(self):

        scores = [
            
                self.r["persistence"] * self.p.non_salary_persistence_weight
            ,
            self.step_score(
                -self.r["cv_net"],
                [(-0.4,1),(-0.6,.67),(-0.8,.33),(-1.5,.2)],
                self.p.non_salary_volatility_weight
            ),

            self.step_score(
                self.r["balance_floor"],
                [(50000,1),(30000,.6),(5000,.3)],
                self.p.non_salary_balance_floor_weight
            ),

            self.step_score(
                self.score,
                [(750,1),(700,.8),(650,.5)],
                self.p.non_salary_credit_score_weight
            ),
            self.betting_score(),
            self.zeroing_rate_score(),
            self.performance_score()
        ]

        # trend
        slope = self.r["slope"]
        if slope > 0:
            scores.append(self.p.non_salary_trend_weight)
        elif slope == 0:
            scores.append(self.p.non_salary_trend_weight * 0.5)

        risk = sum(scores)

        self.r.update({
            "risk_score": risk,
            "risk_band": self.band(risk)
        })

# =========================================================
# FACTORY
# =========================================================

class ProcessorFactory:

    MAP: Dict[str, Type[BaseAssessment]] = {
        "salaried": SalaryCustomer,
        "non_salaried": NonSalaryCustomer
    }

    @classmethod
    def create_processor(cls, result_dict, *args, **kwargs):
        return cls.MAP[result_dict["customer_type"]](
            result_dict, *args, **kwargs
        )

class ScoreCalculator:
    """
    Public interface used by underwriting pipeline
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

    def assess_customer(self):

        processor = ProcessorFactory.create_processor(
            self.result_dict,
            self.score,
            self.on_time,
            self.late,
            self.due,
            self.p
        )

        return processor.calculate(), processor.ineligibility_reasons

