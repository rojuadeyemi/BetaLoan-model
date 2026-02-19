from datetime import datetime, date
import pandas as pd
import logging
from betaloan.optional import OptionalParams

logger = logging.getLogger(__name__)

class LoanQualifier:
    def __init__(
        self,
        date_of_birth,
        user_agent_str,
        location,
        score,
        tier,
        params: OptionalParams
    ):
        self.date_of_birth = date_of_birth
        self.user_agent_str = user_agent_str
        self.location = location.lower()
        self.score = score
        self.tier = tier

        # Instance-level reasons
        self.ineligibility_reasons = []

        # Load parameters
        self.params = params

        self.min_credit_score = self.params.MIN_CREDIT_SCORE

    def is_qualified(self) -> bool:
        age = self._calculate_age()
        phone_ok = self._is_valid_device()
        score = self._normalize_score()

        min_age = self.params.MIN_AGE
        max_age = self.params.MAX_AGE
        min_tier = self.params.min_tier

        rules = [
            (
                age < min_age,
                "AGE_TOO_YOUNG",
                f"Applicant age {age} is below minimum {min_age}",
            ),
            (
                age > max_age,
                "AGE_TOO_OLD",
                f"Applicant age {age} exceeds maximum {max_age}",
            ),
            (
                not phone_ok,
                "INVALID_DEVICE_TYPE",
                "Applicant device is not a supported smartphone",
            ),
            (
                self.location in self.params.BLACKLISTED,
                "LOCATION_NOT_SUPPORTED",
                f"Location '{self.location}' is not supported",
            ),
            (
                score < self.min_credit_score,
                "CREDIT_SCORE_TOO_LOW",
                f"Credit score {score} is below minimum of {self.min_credit_score}",
            ),
            (
                self.tier < min_tier,
                "TIER_INSUFFICIENT",
                f"Tier {self.tier} is below minimum of {min_tier}",
            ),
        ]

        qualified = True

        for failed, code, message in rules:
            
            if failed:
                qualified = False
                self.ineligibility_reasons.append({
                    "reason_code": code,
                    "reason_message": message,
                })

        logger.info(f"is_qualified={qualified}")
        return qualified

    def _calculate_age(self) -> int:
        
        """Calculates the applicant's age in years."""
        dob = self.date_of_birth
        if isinstance(dob, str):
            # Try multiple date formats
            for fmt in ["%d-%m-%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"]:
                try:
                    dob = datetime.strptime(dob, fmt).date()
                    break
                except ValueError:
                    continue
            else:
                # If no format worked, try pandas to_datetime as last resort
                try:
                    dob = pd.to_datetime(dob).date()
                except:
                    raise ValueError(f"Error: Invalid date format '{dob}'. Expected formats: dd-mm-yyyy, yyyy-mm-dd, or ISO format")

        if not isinstance(dob, (datetime, date)):
            raise TypeError(f"Error: Invalid date format '{dob}'. Expected a date object or string")

        # Convert datetime to date if needed
        if isinstance(dob, datetime):
            dob = dob.date()

        today = date.today()
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

        return age

    def _is_valid_device(self) -> bool:
        ua = self.user_agent_str.lower()
        return any(dev in ua for dev in self.params.ALLOWED_DEVICE)

    def _normalize_score(self) -> float:
        try:
            return float(self.score)
        except (TypeError, ValueError):
            return self.min_credit_score
