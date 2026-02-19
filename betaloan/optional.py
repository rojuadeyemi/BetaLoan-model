from pydantic import BaseModel, model_validator
from typing import Optional

class OptionalParams(BaseModel):

    #Thresholds
    BLACKLISTED: Optional[list] = ['kogi','lokoja','niger','minna','gombe',
                    'jigawa','dutse','katsina','zamfara','kebbi']
    
    ALLOWED_DEVICE: Optional[list] = ['android', 'ios', 'iphone']
    MAX_AGE: Optional[int] = 65
    MIN_AGE: Optional[int] = 21
    MIN_CREDIT_SCORE: Optional[float] = 650
    VOLATILITY_COEFFICIENT: Optional[float] = 0.35
    REPAYMENT_FRACTION_NON_SALARIED: Optional[float] = 0.4 # 40% of disposable income
    REPAYMENT_FRACTION_SALARIED: Optional[float] = 0.55 # 55% of disposable income
    ZEROING_BASE: Optional[int] = 1000
    ON_TIME_REPAYMENT: Optional[int] = 2
    DUE_DATE_REPAYMENT: Optional[int] = 1
    LATE_REPAYMENT: Optional[int] = -2
    SAL_BALANCE_FLOOR: Optional[float] = 30_000
    NON_SAL_BALANCE_FLOOR: Optional[float] = 5_000
    DTIR: Optional[float] = 0.46
    MIN_PERSISTENCE: Optional[float] = 0.5
    MIN_NET_SURPLUS: Optional[float] = 0
    MAX_ZEROING: Optional[float] = 0.4
    MIN_SLOPE_COEF: Optional[float] = -0.5
    MIN_NET_TO_GROSS: Optional[float] = 0.05

    income_param_salary: Optional[int] = 150000
    income_param_non_salary: Optional[int] = 100000
    min_tier: Optional[int] = 2


    # Salary Earners Parameter Weights
    salary_income_weight: Optional[int] = 20
    salary_net_surplus_weight: Optional[int] = 15
    salary_balance_floor_weight: Optional[int] = 10
    salary_credit_score_weight: Optional[int] = 10
    salary_persistence_weight: Optional[int] = 15
    
    # Non Salary Earners Parameter Weights
    non_salary_persistence_weight: Optional[int] = 20
    non_salary_volatility_weight: Optional[int] = 15
    non_salary_balance_floor_weight: Optional[int] = 10
    non_salary_trend_weight: Optional[int] = 10
    non_salary_credit_score_weight: Optional[int] = 15

    # Common weights
    performance_weight: Optional[int] = 10
    betting_weight: Optional[int] = 10
    zeroing_weight: Optional[int] = 10

    @model_validator(mode="after")
    def validate_weights(self):

        # Total main weights
        salary_total_main = sum([
            self.salary_income_weight, self.salary_net_surplus_weight, self.non_salary_balance_floor_weight,
            self.salary_credit_score_weight, self.salary_persistence_weight, self.betting_weight,
            self.zeroing_weight,self.performance_weight
        ])
        if salary_total_main != 100:
            raise ValueError(f"Main Total weights must sum to 100. Got {salary_total_main}.")

        non_salary_total_main = sum([
            self.non_salary_persistence_weight, self.non_salary_volatility_weight, self.salary_balance_floor_weight,
            self.zeroing_weight, self.non_salary_trend_weight, self.betting_weight,
            self.performance_weight,self.non_salary_credit_score_weight
        ])
        if non_salary_total_main != 100:
            raise ValueError(f"Main Total weights must sum to 100. Got {non_salary_total_main}.")

        return self