from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional


# Normalized domain model
@dataclass
class Facility:
    """A single credit facility, normalized from the CRC report."""
    institution: str = ""
    account_number: str = ""
    sanctioned_amount: float = 0.0
    current_balance: float = 0.0
    amount_overdue: float = 0.0
    current_dpd: int = 0
    max_dpd: int = 0
    classification: str = ""
    reason: str = "" # status of open accounts
    status: str = "" # # status of closed accounts
    date_opened: Optional[date] = None
    date_reported: Optional[date] = None
    reported_age_days: Optional[int] = None
    is_written_off: bool = False
    legal_action: bool = False
    payment_grid: list = field(default_factory=list)   # ["OK","892","ND",...]
    is_closed: bool = False
    raw: dict = field(default_factory=dict)


@dataclass
class CRCData:
    """Everything the scorer needs, extracted from one CRC report."""
    has_record: bool = True
    facilities: list = field(default_factory=list)     # open/active facilities
    closed_facilities: list = field(default_factory=list) # closed facilities
    file_first_reported: Optional[date] = None
    enquiries_recent: int = 0
    raw_body: dict = field(default_factory=dict)


# Coercion helpers

_DATE_FORMATS = ("%d-%b-%Y", "%d-%B-%Y", "%Y-%m-%d", "%d/%m/%Y",
                 "%m/%d/%Y", "%d-%m-%Y", "%Y%m%d")

_EMPTY = (None, "", "NULL", "N/A", "-")


def _to_date(value: Any) -> Optional[date]:
    if value in _EMPTY:
        return None
    if isinstance(value, (date, datetime)):
        return value.date() if isinstance(value, datetime) else value
    text = str(value).strip()
    # ISO with timezone, e.g. 2025-06-30T00:00:00+01:00
    m = re.match(r"^(\d{4}-\d{2}-\d{2})T", text)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y-%m-%d").date()
        except ValueError:
            pass
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _to_money(value: Any) -> float:
    if value in _EMPTY:
        return 0.0
    cleaned = re.sub(r"[^\d.]", "", str(value))
    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0


def _to_int(value: Any) -> int:
    if value in _EMPTY:
        return 0
    cleaned = re.sub(r"[^\d]", "", str(value))
    return int(cleaned) if cleaned else 0

# ---- payment-grid interpretation -----------------------------------------
_GRID_CLEAN = {"OK", "0", "00", "000", "C", "P"}          # marked clean / paid
_GRID_NODATA = {"", "ND", "XXX", "X", "-", "NA", "N/A", "NONE", "NULL"}


def grid_is_clean(cell: str) -> Optional[bool]:
    """
    Interpret one payment-grid cell.
      True  -> month marked OK / clean
      False -> month with delinquency (a DPD number > 0, or a bad code)
      None  -> no data for this month (excluded from the rate)
    """
    v = str(cell).strip().upper()
    if v in _GRID_NODATA:
        return None
    if v in _GRID_CLEAN:
        return True
    if v.isdigit():
        return int(v) == 0
    # any other non-empty marker (e.g. 'D', 'L') treated as delinquent
    return False


# Record accessor
class _Record:

    __slots__ = ("raw",)

    def __init__(self, raw: dict):
        self.raw = raw

    def first(self, *keys: str) -> Any:
        for key in keys:
            value = self.raw.get(key)
            if value:
                return value
        return None

    def text(self, *keys: str) -> str:
        return str(self.first(*keys) or "").strip()

    def upper(self, *keys: str) -> str:
        return self.text(*keys).upper()

    def money(self, *keys: str) -> float:
        return _to_money(self.first(*keys))

    def integer(self, *keys: str) -> int:
        return _to_int(self.first(*keys))

    def date(self, *keys: str) -> Optional[date]:
        return _to_date(self.first(*keys))


# Json Loader
def json_decoder(value, max_depth=10):
    if hasattr(value, "read"):
        value = value.read()

    if isinstance(value, bytes):
        value = value.decode("utf-8")

    obj = value

    for _ in range(max_depth):
        if not isinstance(obj, str):
            return obj

        s = obj.strip()
        if not s:
            return {}

        # Try normal JSON first
        try:
            obj = json.loads(s)
            continue
        except json.JSONDecodeError:
            pass

        # Try escaped JSON
        try:
            obj = json.loads(s.encode().decode("unicode_escape"))
            continue
        except Exception:
            break

    return obj


# Extractor

class CRCExtractor:
    """
    Parses a loaded CRC document into CRCData. Field candidates live in the
    per-facility parsers; adjust them once against a live report and the rest
    of the pipeline is untouched.
    """

    OPEN_ARRAY = "CreditFacilityHistory24"
    CLOSED_NODE = "ClosedAccounts"
    OVERVIEW = "CreditProfileOverview"
    ENQUIRY_NODES = ("InquiryHistoryDetails", "Inquiry_Product")

    def __init__(self, raw: Any, max_depth: int = 10):
        self.doc = json_decoder(raw, max_depth) # parsed json

    def extract(self) -> CRCData:
        doc = self.doc

        # No-hit response -> applicant has no bureau record
        if isinstance(doc, dict) and "ConsumerNoHitResponse" in doc:
            return CRCData(has_record=False)

        body = self._find_body(doc)
        if not body:
            return {'failed': True, 'message': "No BODY node found in CRC response"}

        facilities = [self._open_facility(r)
                      for r in (body.get(self.OPEN_ARRAY) or [])
                      if isinstance(r, dict)]

        closed = [self._closed_facility(r)
                  for r in self._closed_records(body)
                  if isinstance(r, dict)]

        first_reported, enquiries = self._overview(body)

        has_record = bool(facilities or closed or first_reported)

        return CRCData(
            has_record=has_record,
            facilities=facilities,
            closed_facilities=closed,
            file_first_reported=first_reported,
            enquiries_recent=enquiries,
            raw_body=body,
        )

    # ---- envelope / node location ----------------------------------------

    @staticmethod
    def _find_body(doc: Any) -> dict:
        """Locate the BODY node regardless of exact envelope."""
        if isinstance(doc, dict):
            if "ConsumerHitResponse" in doc:
                return doc["ConsumerHitResponse"].get("BODY", {}) or {}
            if "BODY" in doc:
                return doc["BODY"] or {}
        return {}

    def _closed_records(self, body: dict) -> list:
        node = body.get(self.CLOSED_NODE) or {}
        if isinstance(node, dict):
            return node.get(self.CLOSED_NODE) or []
        return node or []

    # ---- facility parsers ------------------------------------------------

    @staticmethod
    def _extract_payment_grid(rec: dict) -> list:
        """Pull MONTH1..MONTH24 (chronological-ish) from a facility."""
        return [str(rec.get(f"MONTH{i}") or "").strip()
                for i in range(1, 25)
                if f"MONTH{i}" in rec]

    @classmethod
    def _open_facility(cls, raw: dict) -> Facility:
        rec = _Record(raw)

        cls_val = rec.upper("ASSET_CLASSIFICATION_CAL", "ASSET_CLASSIFICATION")
        reason = rec.upper("REASON_CODE_VALUE") 

        grid = cls._extract_payment_grid(raw)
        grid_dpds = [int(c) for c in grid if c.isdigit()]
        cur_dpd = rec.integer("NUM_OF_DAYS_IN_ARREARS_CAL",
                              "NUM_OF_DAYS_IN_ARREARS")

        age_raw = raw.get("DATE_REPORTED_AGE")
        reported_age_days = (_to_int(age_raw)
                             if age_raw not in (None, "") else None)

        return Facility(
            institution=rec.text("INSTITUTION_NAME"),
            account_number=rec.text("ACCOUNT_NUMBER"),
            sanctioned_amount=rec.money("SANCTIONED_AMOUNT_CAL",
                                        "SANCTIONED_AMOUNT"),
            current_balance=rec.money("CURRENT_BALANCE_CAL",
                                      "CURRENT_BALANCE"),
            amount_overdue=rec.money("AMOUNT_OVERDUE_CAL",
                                     "OVER_DUE_AMT_PRICIPAL"),
            current_dpd=cur_dpd,
            max_dpd=max([cur_dpd] + grid_dpds),
            classification=cls_val,
            reason=reason,
            status=(rec.upper("ACCOUNT_STATUS") or reason),
            date_opened=rec.date("ACC_OPEN_DISB_DT", "SANCTION_DATE",
                                 "FIRST_DISBURSE_DATE"),
            date_reported=rec.date("REPORTED_DT_TEXT", "DATE_REPORTED"),
            reported_age_days=reported_age_days,
            is_written_off=("WRITTEN" in reason or "WRITTEN" in cls_val
                            or rec.money("AMOUNT_WRITTEN_OFF") > 0),
            legal_action=rec.upper("LEGAL_ACTION_STATUS") == "YES",
            payment_grid=grid,
            is_closed=False,
            raw=raw,
        )

    @staticmethod
    def _closed_facility(raw: dict) -> Facility:
        rec = _Record(raw)
        cls_val = rec.upper("ASSET_CLASSIFICATION")

        return Facility(
            institution=rec.text("INSTITUTION_NAME"),
            sanctioned_amount=rec.money("SANCTION_AMOUNT"),
            current_balance=0.0,
            amount_overdue=rec.money("OVER_DUE_AMT_PRICIPAL"),
            current_dpd=0,
            max_dpd=rec.integer("MAX_NUM_DAYS_DUE"),
            classification=cls_val,
            status=(rec.upper("ACCOUNT_STATUS") or "CLOSED"),
            date_opened=rec.date("SANCTION_DATE", "FIRST_DISBURSE_DATE"),
            date_reported=rec.date("REPORTED_DATE"),
            is_written_off="WRITTEN" in cls_val,
            legal_action=rec.upper("LEGAL_ACTION_STATUS") == "YES",
            is_closed=True,
            raw=raw,
        )

    # ---- profile overview: file age + enquiry count ----------------------

    def _overview(self, body: dict) -> tuple[Optional[date], int]:
        first_reported: Optional[date] = None
        enquiries = 0

        for row in body.get(self.OVERVIEW) or []:
            itype = str(row.get("INDICATOR_TYPE") or "").upper()
            if itype == "FIRST_REPORTED":
                first_reported = _to_date(row.get("VALUE"))
            elif "INQUIRY" in itype or "ENQUIR" in itype:
                enquiries = max(enquiries, _to_int(row.get("VALUE")))

        # explicit enquiry list overrides the summary count if larger
        for node in self.ENQUIRY_NODES:
            lst = body.get(node)
            if isinstance(lst, list) and len(lst) > enquiries:
                enquiries = len(lst)

        return first_reported, enquiries


# Module-level entry point (stable API for the scoring layer)

def parse_crc(raw: Any) -> CRCData:
    """Parse a raw CRC response into the CRCData the scorer consumes."""
    return CRCExtractor(raw).extract()