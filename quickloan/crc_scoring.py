from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from itertools import chain
from typing import Optional, Any

from quickloan.crc_extraction import (
    CRCData,
    Facility,
    parse_crc,
    grid_is_clean,
)

from quickloan.optional import OptionalParams

# Helper functions
def score_from_upper_bands(
    value: float | int,
    bands: list[tuple[int, int]],
    default: int,
) -> int:
    """
    Score by UPPER bound: the first band whose limit `value` does not exceed
    wins. Used by delinquency (worst DPD), stacking and hunger, where a lower
    value is better.
    """

    for upper, score in bands:
        if value <= upper:
            return score

    return default


def score_from_lower_bands(
    value: float | int,
    bands: list[tuple[int, int]],
    default: int,
) -> int:
    """
    Score by LOWER threshold: the first band whose minimum `value` meets or
    exceeds wins. Used by the payment track record (clean rate %), where a
    higher value is better. Bands must be ordered highest-threshold first.
    """

    for minimum, score in bands:
        if value >= minimum:
            return score

    return default


def band_label(
    value: float | int,
    bands: list[tuple[int, int]],
) -> str:
    """
    Human-readable description of the matched upper band.
    """

    for upper, _ in bands:
        if value <= upper:
            return f"<= {upper}"

    return f"> {bands[-1][0]}"


# Facility-level checks
class CRCChecks:
    """
    Encapsulates reusable business rules applied to facilities.
    """

    def __init__(self, params: OptionalParams):

        self.p = params

    def is_active(self, facility: Facility) -> bool:
        """
        Determines whether a facility should be considered active.
        """

        if facility.is_closed:
            return False

        if facility.current_balance > 0:
            return True

        if facility.amount_overdue > 0:
            return True

        age = facility.reported_age_days

        if age is None:
            return facility.date_reported is not None

        return age <= self.p.active_report_months * 30

    def is_serious_derogatory(self, facility: Facility) -> bool:
        """
        Determines whether a facility is considered a serious derogatory.
        """

        if facility.amount_overdue < self.p.derog_min_overdue:
            return False

        adverse = (
            any(
                cls in facility.classification
                for cls in self.p.derog_classifications
            )
            or any(
                cls in facility.reason
                for cls in self.p.derog_classifications
            )
            or facility.is_written_off
            or facility.current_dpd >= self.p.derog_dpd
        )

        if not adverse:
            return False

        age = facility.reported_age_days

        if age is None:
            return True

        return age <= self.p.derog_report_months * 30


# Component model

@dataclass(slots=True)
class Component:
    """
    Represents one scoring component.
    """

    name: str
    score: int
    max_score: int
    detail: str

    @property
    def percentage(self) -> float:
        """
        Percentage score achieved for this component.
        """
        
        if self.max_score == 0:
            return 0.0

        return self.score / self.max_score * 100


# Final score model
@dataclass(slots=True)
class BureauScoreResult:
    """
    Final bureau scoring result.
    """

    total_score: int
    grade: str
    has_record: bool
    offer_restricted: bool
    components: list[Component]
    as_of: date

    @property
    def max_score(self) -> int:
        return sum(c.max_score for c in self.components)

    def component(self, name: str) -> Optional[Component]:
        """
        Returns a component by name.
        """

        return next(
            (c for c in self.components if c.name == name),
            None,
        )

    def to_dict(self) -> dict:
        """
        JSON-serialisable representation.
        """

        return {
            "total_score": self.total_score,
            "grade": self.grade,
            "has_record": self.has_record,
            "offer_restricted": self.offer_restricted,
            "as_of": self.as_of.isoformat(),
            "components": [
                {
                    "name": c.name,
                    "score": c.score,
                    "max_score": c.max_score,
                    "score(%)": c.percentage,
                    "detail": c.detail,
                }
                for c in self.components
            ],
        }


# Preprocessed cache

@dataclass(slots=True)
class ScoreCache:
    """
    Holds all preprocessed values required during scoring.
    """

    active_facilities: list[Facility]
    serious_derogs: list[Facility]
    clean_closed_facilities: list[Facility]

    total_grid_months: int
    clean_grid_months: int

    worst_active_dpd: int

    active_count: int
    deduped_active_count: int
    closed_clean_count: int


# CRC Bureau Scorer
class CRCBureauScorer:
    """
    Computes the 25-point CRC Bureau Sub-Score.

    The scorer performs a single preprocessing pass over the facilities and
    caches commonly-used statistics so that each component score can be
    calculated in O(1).
    """

    def __init__(
        self,
        data: CRCData,
        params: OptionalParams | None = None,
    ):

        self.data = data
        self.p = params or OptionalParams()

        self.checks = CRCChecks(self.p)

        # ---------------------------------------------------------
        # Cached collections
        # ---------------------------------------------------------

        self.cache = ScoreCache(
            active_facilities=[],
            serious_derogs=[],
            clean_closed_facilities=[],
            total_grid_months=0,
            clean_grid_months=0,
            worst_active_dpd=0,
            active_count=0,
            deduped_active_count=0,
            closed_clean_count=0,
        )

        # Precompute everything once
        self._preprocess()

    def _preprocess(self) -> None:
        """
        Performs a single pass through every facility (open + closed) and
        builds the cache.
        """

        active_keys: set[tuple[str, int, str]] = set()

        cache = self.cache

        for facility in chain(
            self.data.facilities,
            self.data.closed_facilities,
        ):

            # Payment Grid
            for cell in facility.payment_grid:

                verdict = grid_is_clean(cell)

                if verdict is None: # dont count
                    continue

                cache.total_grid_months += 1

                if verdict:
                    cache.clean_grid_months += 1

                        # Compute once

            is_active = self.checks.is_active(facility)

            is_derog = (
                is_active
                and self.checks.is_serious_derogatory(facility)
            )

            # Active
            if is_active:

                cache.active_facilities.append(facility)

                cache.active_count += 1

                cache.worst_active_dpd = max(
                    cache.worst_active_dpd,
                    facility.current_dpd,
                )

                if is_derog:
                    cache.serious_derogs.append(facility)

                active_keys.add(
                    (
                        facility.institution.upper(),
                        round(facility.sanctioned_amount),
                        facility.date_opened.isoformat()
                        if facility.date_opened
                        else "",
                    )
                )

                        # Closed
            
            elif (
                facility.is_closed
                and facility.max_dpd < self.p.clean_closed_dpd
                and not facility.is_written_off
                and not facility.legal_action
            ):

                cache.clean_closed_facilities.append(facility)

        cache.closed_clean_count = len(
            cache.clean_closed_facilities
        )

        cache.deduped_active_count = len(active_keys)

    def _payment_clean_rate(self) -> float:

        cache = self.cache

        if cache.total_grid_months == 0:
            return 0.0

        return (
            cache.clean_grid_months
            / cache.total_grid_months
            * 100
        )

    def _file_age_years(
        self,
        as_of: date,
    ) -> float:

        if self.data.file_first_reported is None:
            return 0.0

        return (
            (as_of - self.data.file_first_reported).days
            / 365.25
        )

    def _grade(
        self,
        total: int,
    ) -> str:

        if total >= self.p.grade_good_min:
            return "Good"

        if total >= self.p.grade_average_min:
            return "Average"

        return "Poor"
    
    # Component 1 — Current Delinquency (max 10)
    def score_current_delinquency(self) -> Component:

        cache = self.cache

        if cache.serious_derogs:

            names = ", ".join(
                sorted(
                    {
                        f.institution
                        for f in cache.serious_derogs
                    }
                )
            )[:120]

            return Component(
                "Current Delinquency",
                0,
                self.p.max_delinquency,
                (
                    f"Active serious derogatory "
                    f"({len(cache.serious_derogs)}): {names}"
                ),
            )

        if cache.active_count == 0:

            return Component(
                "Current Delinquency",
                self.p.max_delinquency,
                self.p.max_delinquency,
                "No active facilities.",
            )

        score = score_from_upper_bands(
            cache.worst_active_dpd,
            self.p.delinquency_bands,
            self.p.delinquency_above_max,
        )

        return Component(
            "Current Delinquency",
            score,
            self.p.max_delinquency,
            (
                f"Worst DPD = "
                f"{cache.worst_active_dpd}"
            ),
        )
    
    # Component 2 — Payment Track Record (max 6)
    def score_payment_track_record(self) -> Component:

        cache = self.cache

        # No payment grid anywhere -> neutral score
        if cache.total_grid_months == 0:

            return Component(
                "Payment Track Record",
                self.p.track_no_grid_neutral,
                self.p.max_track_record,
                "No payment grid available.",
            )

        rate = self._payment_clean_rate()

        score = score_from_lower_bands(
            rate,
            self.p.track_bands,
            self.p.track_below_min,
        )

        detail = (
            f"{cache.clean_grid_months}/{cache.total_grid_months} "
            f"months OK ({rate:.1f}% clean)"
        )

        # Thin-file guard: too few months of history cannot earn the top band
        if (
            cache.total_grid_months < self.p.track_thin_file_months
            and score > self.p.track_thin_file_cap
        ):

            score = self.p.track_thin_file_cap

            detail += (
                f"; thin file "
                f"(<{self.p.track_thin_file_months} months) "
                f"capped at {self.p.track_thin_file_cap}"
            )

        return Component(
            "Payment Track Record",
            score,
            self.p.max_track_record,
            detail,
        )
    
    # Component 3 — Credit History Depth (max 4)
    def score_credit_history_depth(
        self,
        as_of: date,
    ) -> Component:

        if not self.data.has_record:

            return Component(
                "Credit History Depth",
                self.p.depth_limited,
                self.p.max_history_depth,
                "No bureau record.",
            )

        age_years = self._file_age_years(as_of)

        clean_closed = self.cache.closed_clean_count

        if (
            age_years >= self.p.depth_full_years
            and clean_closed >= self.p.depth_full_clean_closed
        ):

            score = self.p.max_history_depth

        elif (
            age_years >= self.p.depth_mid_years
            and clean_closed >= self.p.depth_mid_clean_closed
        ):

            # mid tier defaults to 3 if OptionalParams doesn't define it
            score = self.p.depth_mid

        else:

            score = self.p.depth_limited

        return Component(
            "Credit History Depth",
            score,
            self.p.max_history_depth,
            (
                f"File age {age_years:.1f}y, "
                f"{clean_closed} clean closed facilities"
            ),
        )
    
    # Component 4 — Credit Stacking (max 3)
    def score_credit_stacking(self) -> Component:

        n = self.cache.deduped_active_count

        score = score_from_upper_bands(
            n,
            self.p.stacking_bands,
            self.p.stacking_above_max,
        )

        return Component(
            "Credit Stacking",
            score,
            self.p.max_stacking,
            (
                f"{n} active facilities (deduped) "
                f"({band_label(n, self.p.stacking_bands)})"
            ),
        )
    
    # Component 5 — Credit Hunger (max 2)
    def score_credit_hunger(self) -> Component:

        n = self.data.enquiries_recent

        score = score_from_upper_bands(
            n,
            self.p.hunger_bands,
            self.p.hunger_above_max,
        )

        return Component(
            "Credit Hunger",
            score,
            self.p.max_hunger,
            (
                f"{n} enquiries in last "
                f"{self.p.hunger_lookback_months} months "
                f"({band_label(n, self.p.hunger_bands)})"
            ),
        )
    
    # No-record neutral profile
    def _neutral_result(
        self,
        as_of: date,
    ) -> BureauScoreResult:

        p = self.p

        components = [
            Component(
                "Current Delinquency",
                p.neutral_delinquency,
                p.max_delinquency,
                "No CRC record -> neutral.",
            ),
            Component(
                "Payment Track Record",
                p.neutral_track_record,
                p.max_track_record,
                "No CRC record -> neutral.",
            ),
            Component(
                "Credit History Depth",
                p.neutral_history_depth,
                p.max_history_depth,
                "No CRC record -> neutral.",
            ),
            Component(
                "Credit Stacking",
                p.neutral_stacking,
                p.max_stacking,
                "No CRC record -> neutral.",
            ),
            Component(
                "Credit Hunger",
                p.neutral_hunger,
                p.max_hunger,
                "No CRC record -> neutral.",
            ),
        ]

        total = sum(c.score for c in components)

        return BureauScoreResult(
            total_score=total,
            grade=self._grade(total),
            has_record=False,
            offer_restricted=False,
            components=components,
            as_of=as_of,
        )
    
    # Assembly
    def score(
        self,
        as_of: date | None = None,
    ) -> BureauScoreResult:
        """
        Runs all five components and assembles the final result.
        """

        as_of = as_of or date.today()

        if not self.data.has_record:
            return self._neutral_result(as_of)

        components = [
            self.score_current_delinquency(),
            self.score_payment_track_record(),
            self.score_credit_history_depth(as_of),
            self.score_credit_stacking(),
            self.score_credit_hunger(),
        ]

        total = sum(c.score for c in components)

        offer_restricted = bool(self.cache.serious_derogs)

        return BureauScoreResult(
            total_score=total,
            grade=self._grade(total),
            has_record=True,
            offer_restricted=offer_restricted,
            components=components,
            as_of=as_of,
        )


# Convenience entry points
def score_crc_data(
    data: CRCData,
    params: OptionalParams | None = None,
    as_of: date | None = None,
) -> BureauScoreResult:
    """
    Score an already-extracted CRCData object.
    """

    return CRCBureauScorer(data, params).score(as_of)

def score_crc_report(
    raw: Any,
    params: OptionalParams | None = None,
    as_of: date | None = None,
) -> BureauScoreResult:

    json_data = parse_crc(raw)

    if not isinstance(json_data, CRCData):
        return json_data  # propagate error dict

    return score_crc_data(json_data, params, as_of)