"""Configuration parameters for loan evaluation."""

from pydantic import BaseModel, model_validator
from typing import Literal, Optional
import logging

logger = logging.getLogger(__name__)

# Singleton instance for efficient memory usage (avoids recreating instance per request)
_default_params_instance: Optional['OptionalParams'] = None

def get_optional_params() -> 'OptionalParams':
    """
    Get the default OptionalParams instance (singleton pattern).
    
    Benefits:
    - Memory efficient: Only one instance in memory
    - Performance: Avoids validation overhead on every request
    - Thread-safe: OptionalParams is immutable after creation
    
    Returns:
        OptionalParams: Cached default parameters instance
    """
    global _default_params_instance
    if _default_params_instance is None:
        _default_params_instance = OptionalParams()
        logger.debug("OptionalParams singleton initialized")
    return _default_params_instance


class OptionalParams(BaseModel):
    """Configurable threshold and weight parameters for loan evaluation."""

    # Credit scoring parameters
    max_delinquency: int = 10
    max_track_record: int = 6
    max_history_depth: int = 4
    max_stacking: int = 3
    max_hunger: int = 2

    # ---- serious derogatory definition ------------------------------------
    derog_min_overdue: float = 10_000          # amount outstanding overdue
    derog_dpd: int = 90                         # or >= this many days past due
    derog_classifications: tuple = ("LOST", "WRITTEN OFF", "WRITTEN-OFF",
                                    "WRITEOFF", "DOUBTFUL")
    derog_report_months: int = 24              # reported within last N months...
                                               # ...or still actively reported

    # ---- what counts as an "active" facility ------------------------------
    active_report_months: int = 24             # recently reported => active
    # (a facility is also active if it still carries balance or overdue)

    # ---- component 1: worst-DPD -> points ---------------------------------
    # (upper_dpd_inclusive, points); first matching row wins
    delinquency_bands: tuple = ((0, 10), (30, 7), (90, 4), (180, 1))
    delinquency_above_max: int = 0             # > last band

    # ---- component 2: clean-rate -> points --------------------------------
    # (min_clean_rate_pct, points); highest matching threshold wins
    track_bands: tuple = ((95, 6), (85, 4), (70, 2))
    track_below_min: int = 0
    track_thin_file_months: int = 6            # < this many months of grid...
    track_thin_file_cap: int = 4               # ...caps the component at this
    track_no_grid_neutral: int = 4             # no grid at all -> neutral

    # ---- component 3: history depth ---------------------------------------
    depth_full_years: float = 3
    depth_full_clean_closed: int = 3           # ...and this many clean closed -> max
    depth_mid_years: float = 1
    depth_mid_clean_closed: int = 1
    depth_limited: int = 2                     # fallback / no record
    # a closed facility is "clean" if its worst DPD stayed below this
    clean_closed_dpd: int = 90
    depth_mid:int = 3

    # ---- component 4: credit stacking -------------------------------------
    # (max_active_facilities, points); first matching row wins
    stacking_bands: tuple = ((2, 3), (4, 2), (6, 1))
    stacking_above_max: int = 0

    # ---- component 5: credit hunger ---------------------------------------
    hunger_lookback_months: int = 12           # enquiries within this window
    hunger_bands: tuple = ((1, 2), (3, 1))
    hunger_above_max: int = 0

    # ---- final grade bands ------------------------------------------------
    grade_good_min: int = 20                   # >= -> Good
    grade_average_min: int = 12                # >= -> Average, else Poor

    # ---- no-CRC-record neutral profile (sums to 13/25) --------------------
    neutral_delinquency: int = 2
    neutral_track_record: int = 4
    neutral_history_depth: int = 2
    neutral_stacking: int = 3
    neutral_hunger: int = 2

    # Geographic and device restrictions
    BLACKLISTED: Optional[list] = ['kogi','niger','minna','gombe',
                    'jigawa','dutse','katsina','zamfara','kebbi']
    
    ALLOWED_DEVICE: Optional[list] = ['android', 'ios', 'iphone']

    MAX_ELIGIBLE_AMOUNT: Optional[float] = 500_000
    
    # Age restrictions
    MAX_AGE: Optional[int] = 60
    MIN_AGE: Optional[int] = 21
    
    # Financial thresholds
    VOLATILITY_COEFFICIENT: Optional[float] = 0.1
    REPAYMENT_FRACTION_NON_SALARIED: Optional[float] = 0.55  # 55% of disposable income
    REPAYMENT_FRACTION_SALARIED: Optional[float] = 0.55      # 55% of disposable income
    ZEROING_BASE: Optional[float] = 1000
    MIN_RISK_SCORE: Optional[float] = 50
    MIN_ELIGIBLE_AMOUNT: Optional[float] = 5000
    
    # Repayment performance scoring
    ON_TIME_REPAYMENT: Optional[int] = 2
    DUE_DATE_REPAYMENT: Optional[int] = 1
    LATE_REPAYMENT: Optional[int] = -2
    SALARY_DIFF_TOL: Optional[float] = 0.05

    SALARY_CAP: Optional[dict] = {
        "A": 500_000,
        "B": 400_000,
        "C": 300_000,
        "D": 200_000,
    }

    NON_SALARY_CAP: Optional[dict] = {
        "A": 300_000,
        "B": 200_000,
        "C": 150_000,
        "D": 100_000,
    }

    MAX_ELIGIBLE_AMOUNT: Optional[dict] = {'salaried': SALARY_CAP, 'non_salaried': NON_SALARY_CAP}
    MIN_CREDIT_SCORE:Optional[float] = 10
    # Financial ratios
    DTIR: Optional[float] = 0.46  # Debt-to-Income Ratio threshold
    
    # Cash flow metrics
    MIN_WEEKS_FOR_SLOPE: Optional[int] = 24
    SALARY_RECENCY_DAYS: Optional[int] = 90
    INFLOW_MARGIN: Optional[float] = 0.2
    PERFORMANCE_NEUTRAL: Optional[float] = 0.5
    TREND_NEUTRAL: Optional[float] = 0.5

    # Product policy controls
    SALARY_BASELINE_MODE: Literal["median", "min_non_zero"] = "min_non_zero"
    QUALIFICATION_REASON_MODE: Literal["fail_fast", "collect_all"] = "fail_fast"
    BACKGROUND_COLLECT_ALL_REASONS_ENABLED: Optional[bool] = True
    PRICING_SCHEDULE_VERSION: Literal["zedvance_short_tenor", "quickloan_legacy"] = "quickloan_legacy"

    # Income thresholds
    BNPL_TENOR_LIST_DEV: Optional[list] = [3,6,9,12,15,18]
    BNPL_TENOR_LIST_PROD: Optional[list] = [3,6,9]
    BNPL_PROD_ENABLED: Optional[bool] = False
    BNPL_SELF_EMPLOYED_ENABLED: Optional[bool] = False
    BNPL_income_param: Optional[float] = 250_000
    BNPL_MINIMUM_CL: Optional[float] = 50_000
    BNPL_PROCESSING_FEE: Optional[float] = 0.01
    income_param: Optional[float] = 100_000
    self_employed_income_param: Optional[float] = 70_000
    min_tier: Optional[int] = 2
    salary_window_days: tuple[int, int] = (20, 7)
    salary_max_cycles: int = 6
    salary_min_cycles: int = 3
    salary_max_cv: float=0.1
    salary_max_date_drift: int = 3

    # Geographic policy controls
    PILOT_LOCATION: Optional[list] = ['abuja', 'port harcourt', 'ph', 'lagos', 'ikeja', 'rivers']
    PILOT_MODE_ENABLED: Optional[bool] = True

    # Betting policy controls
    BETTING_RATE: Optional[float] = 0.2
    HYBRID_BETTING_POLICY_ENABLED: Optional[bool] = False

   # Salary Earners Parameter Weights
    salary_income_weight: Optional[int] = 20
    salary_net_surplus_weight: Optional[int] = 5 # Adjusted to 5 from 10
    salary_balance_floor_weight: Optional[int] = 5
    salary_persistence_weight: Optional[int] = 15
    
   # Non Salary Earners Parameter Weights
    non_salary_persistence_weight: Optional[int] = 20
    non_salary_volatility_weight: Optional[int] = 10
    non_salary_balance_floor_weight: Optional[int] = 5 # Adjusted to 5 from 10
    non_salary_trend_weight: Optional[int] = 10

    # Common weights
    performance_weight: Optional[int] = 10
    betting_weight: Optional[int] = 10
    zeroing_weight: Optional[int] = 10
    credit_score_weight: Optional[int] = 25

    @model_validator(mode="after")
    def validate_weights(self):
        """Ensure scoring weights sum to 100."""

        # Validate salaried customer weights
        salary_total_main = sum([
            self.salary_income_weight, 
            self.salary_net_surplus_weight, 
            self.salary_balance_floor_weight,
            self.credit_score_weight, 
            self.salary_persistence_weight, 
            self.betting_weight,
            self.zeroing_weight,
            self.performance_weight
        ])
        if salary_total_main != 100:
            raise ValueError(f"Salaried weights must sum to 100. Got {salary_total_main}.")

        # Validate non-salaried customer weights
        non_salary_total_main = sum([
            self.non_salary_persistence_weight, 
            self.non_salary_volatility_weight, 
            self.non_salary_balance_floor_weight,
            self.zeroing_weight, 
            self.non_salary_trend_weight, 
            self.betting_weight,
            self.performance_weight,
            self.credit_score_weight
        ])
        if non_salary_total_main != 100:
            raise ValueError(f"Non-salaried weights must sum to 100. Got {non_salary_total_main}.")

        return self

    def policy_mode_label(self) -> str:
        """Build a compact policy identifier for telemetry grouping."""
        return "|".join([
            f"pricing:{self.PRICING_SCHEDULE_VERSION}",
            f"salary:{self.SALARY_BASELINE_MODE}",
            f"qualify:{self.QUALIFICATION_REASON_MODE}",
            f"pilot:{'on' if self.PILOT_MODE_ENABLED else 'off'}",
            f"hybrid_betting:{'on' if self.HYBRID_BETTING_POLICY_ENABLED else 'off'}",
        ])
