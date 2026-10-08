"""ExtraCash / BNPL decision console.

Streamlit front-end for the QuickLoan decision engine. Collects applicant
inputs, runs the engine, and renders Extra Cash and BNPL outcomes.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import traceback
from datetime import date
from typing import Any, Mapping

import pandas as pd
import streamlit as st

st.set_page_config(page_title="ExtraCash & BNPL Decisioning", page_icon="₦", layout="wide")

# ----------------------------------------------------------------- engine import

ENGINE_ERROR: str | None = None
try:
    from quickloan.loan_decision_engine import QuickLoan
    from quickloan.bnpl_schedule import ITEM_SCHEDULE
    from quickloan.optional import OptionalParams
except Exception:  # noqa: BLE001
    ENGINE_ERROR = traceback.format_exc()
    QuickLoan = None
    OptionalParams = None
    ITEM_SCHEDULE = {}

DASH = "—"


# -------------------------------------------------------------------- formatting

def _num(v: Any) -> float | None:
    """Coerce to a finite float, or None if missing / non-numeric / NaN / inf."""
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def naira(v: Any) -> str:
    f = _num(v)
    return DASH if f is None else f"₦{f:,.0f}"


def pct(v: Any) -> str:
    f = _num(v)
    return DASH if f is None else f"{f:.1%}"


def number(v: Any, decimals: int = 2) -> str:
    f = _num(v)
    if f is None:
        return DASH
    return f"{f:,.0f}" if f.is_integer() else f"{f:,.{decimals}f}"


def integer(v: Any) -> str:
    f = _num(v)
    return DASH if f is None else f"{round(f):,}"


def text(v: Any) -> str:
    return DASH if v in (None, "") else str(v).replace("_", " ").capitalize()


def reasons_frame(reasons: list) -> pd.DataFrame:
    """Normalise reasons that may be strings or dicts into a tidy table."""
    if all(isinstance(r, Mapping) for r in reasons):
        return pd.DataFrame(reasons)
    return pd.DataFrame({"Reason": [str(r) for r in reasons]})


def lookup_tenor(offers: Mapping | None, tenor: Any) -> Any:
    """Tenor keys may be int or str depending on serialisation; try both."""
    if not offers:
        return None
    for key in (tenor, str(tenor)):
        if key in offers:
            return offers[key]
    try:
        return offers.get(int(tenor))
    except (TypeError, ValueError):
        return None


def tenor_sort_key(t: Any) -> tuple[int, Any]:
    try:
        return (0, int(t))
    except (TypeError, ValueError):
        return (1, str(t))


def status_banner(status: Any, has_reasons: bool) -> None:
    if status is None:
        st.warning("**Status: Unavailable** — the engine returned no status.")
    elif status == "ineligible":
        suffix = " — see reasons below." if has_reasons else "."
        st.error(f"**Status: Ineligible**{suffix}")
    else:
        st.success(f"**Status: {text(status)}**")


# ------------------------------------------------------------------ sidebar form

st.sidebar.title("Applicant inputs")

statement_data: Any = None
with st.sidebar.expander("Bank statement", expanded=True):
    src = st.radio("Source", ["Upload .json", "Paste JSON", "File path"],
                   label_visibility="collapsed")
    stmt_note = ""
    if src == "Upload .json":
        up = st.file_uploader("Aggregator response", type=["json"], key="stmt_upload")
        if up is not None:
            try:
                statement_data = json.load(up)
                stmt_note = f"Loaded {up.name}"
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                st.error(f"Invalid JSON: {e}")
    elif src == "Paste JSON":
        raw = st.text_area("Aggregator response", height=160, placeholder='{"data": [...]}')
        if raw.strip():
            try:
                statement_data = json.loads(raw)
                stmt_note = "Parsed pasted JSON"
            except json.JSONDecodeError as e:
                st.error(f"Invalid JSON: {e}")
    else:
        path = st.text_input("Path to fixture", value="fixtures/statement.json").strip()
        if path:
            try:
                with open(path, encoding="utf-8") as fh:
                    statement_data = json.load(fh)
                stmt_note = f"Loaded {path}"
            except FileNotFoundError:
                st.error(f"File not found: {path}")
            except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
                st.error(f"Could not read {path}: {e}")
    if stmt_note:
        st.caption(f":green[{stmt_note}]")

c1, c2 = st.sidebar.columns(2)
date_of_birth = c1.date_input("Date of birth", value=date(1995, 6, 15),
                              min_value=date(1940, 1, 1), max_value=date.today())
tier = c2.selectbox("KYC tier", [1, 2, 3], index=1)
location = st.sidebar.text_input("Location", value="Lagos").strip()
user_agent_str = st.sidebar.text_input(
    "User agent",
    value="Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120 Mobile",
).strip()
current_balance = st.sidebar.number_input("Current balance (₦)", value=0, step=1000)

# Credit bureau ----------------------------------------------------------------
st.sidebar.markdown("**Credit bureau**")
score_mode = st.sidebar.radio("Bureau input", ["Numeric score", "Paste CRC JSON", "Upload CRC .json"],
                              label_visibility="collapsed")
credit_score: Any
if score_mode == "Numeric score":
    credit_score = st.sidebar.slider("Score", 1, 25, 1)
else:
    credit_score = {}
    crc_raw = ""
    if score_mode == "Paste CRC JSON":
        crc_raw = st.sidebar.text_area("CRC response", height=120, placeholder='{"BODY": {...}}')
    else:
        crc_up = st.sidebar.file_uploader("CRC response", type=["json"], key="crc_upload")
        if crc_up is not None:
            crc_raw = crc_up.getvalue().decode("utf-8", errors="replace")
    if crc_raw.strip():
        try:
            credit_score = json.loads(crc_raw)
        except json.JSONDecodeError:
            st.sidebar.caption(":red[Invalid JSON — the engine will return INVALID_CREDIT_REPORT.]")
    else:
        st.sidebar.caption("No report supplied — an empty report will be sent.")

# Repayment history ------------------------------------------------------------
st.sidebar.markdown("**Repayment history**")
r1, r2, r3 = st.sidebar.columns(3)
on_time = int(r1.number_input("On time", min_value=0, value=0, step=1))
late = int(r2.number_input("Late", min_value=0, value=0, step=1))
due = int(r3.number_input("Due", min_value=0, value=0, step=1))

# Configuration ----------------------------------------------------------------
st.sidebar.markdown("**Configuration**")
schedule_envs = list(ITEM_SCHEDULE.keys()) or ["dev"]
default_env = os.environ.get("QUICKLOAN_ENV", "dev")
env = st.sidebar.selectbox(
    "BNPL item schedule", schedule_envs,
    index=schedule_envs.index(default_env) if default_env in schedule_envs else 0,
)
st.sidebar.caption(
    f"Engine parameters follow the `QUICKLOAN_ENV` variable (currently "
    f"`{os.environ.get('QUICKLOAN_ENV', 'dev (unset)')}`). The selector above only "
    f"changes the item schedule used for BNPL quotes."
)
self_employed_enabled = st.sidebar.checkbox(
    "Allow self-employed for BNPL", value=False,
    help="Sets BNPL_SELF_EMPLOYED_ENABLED on the engine parameters for this run only.",
)

# Fingerprint of every input, so stale results can be flagged.
inputs_fp = hashlib.sha256(json.dumps(
    [statement_data, user_agent_str, date_of_birth, location, credit_score, tier,
     on_time, late, due, current_balance, self_employed_enabled],
    sort_keys=True, default=str,
).encode()).hexdigest()

run = st.sidebar.button("Run decision", type="primary", width="stretch",
                        disabled=statement_data is None or QuickLoan is None)
if st.sidebar.button("Clear", width="stretch"):
    for k in ("engine", "results", "inputs_fp"):
        st.session_state.pop(k, None)

# --------------------------------------------------------------------- run model

st.title("Loan Applicant Profile")

if ENGINE_ERROR:
    st.error("Could not import the QuickLoan package. Check that it is installed "
             "or on PYTHONPATH, then rerun.")
    with st.expander("Traceback"):
        st.code(ENGINE_ERROR)
    st.stop()

if run:
    with st.spinner("Running decision pipeline…"):
        try:
            # Set on the instance, not the class, so concurrent sessions don't
            # leak this flag into each other's runs.
            params = OptionalParams()
            params.BNPL_SELF_EMPLOYED_ENABLED = self_employed_enabled
            engine = QuickLoan(
                statement_data, user_agent_str, date_of_birth, location,
                credit_score, tier, on_time, late, due,
                current_balance=current_balance,
                params=params,
            )
            st.session_state["results"] = engine.get_decision()
            st.session_state["engine"] = engine
            st.session_state["inputs_fp"] = inputs_fp
        except Exception:  # noqa: BLE001
            for k in ("engine", "results", "inputs_fp"):
                st.session_state.pop(k, None)
            st.error("The pipeline failed before returning a decision.")
            st.code(traceback.format_exc())

results = st.session_state.get("results")
engine = st.session_state.get("engine")

if not results:
    st.info("Load a bank statement in the sidebar and press **Run decision**.")
    st.stop()

if st.session_state.get("inputs_fp") != inputs_fp:
    st.warning("Inputs have changed since the last run. Results below reflect the "
               "previous inputs — press **Run decision** to refresh.")

extra: dict = results.get("extra_cash") or {}
bnpl: dict = results.get("bnpl") or {}
extra_cash_reasons: list = extra.get("ineligibility_reasons") or []
bnpl_reasons: list = bnpl.get("ineligibility_reasons") or []
bnpl_offers: dict = bnpl.get("credit_limits") or {}

# ------------------------------------------------------------------ headline row

customer_type = extra.get("customer_type")
salary = _num(extra.get("salary"))
inflow_median = _num(extra.get("inflow_median"))

# Salaried: declared salary. Otherwise (or if salary is missing): weekly inflow
# median x 4 as a monthly proxy.
if customer_type == "salaried" and salary is not None:
    monthly_income = salary
else:
    monthly_income = inflow_median * 4 if inflow_median is not None else None

betting_amount = _num(extra.get("betting_amount"))
betting_ratio = (
    betting_amount / monthly_income
    if betting_amount is not None and monthly_income and monthly_income > 0
    else None
)

k = st.columns(6)
k[0].metric("Customer type", text(customer_type))
k[1].metric("Risk band", extra.get("risk_band") or DASH)
k[2].metric("Risk score", integer(extra.get("risk_score")))
k[3].metric("Betting / income", pct(betting_ratio),
            help="Betting spend divided by estimated monthly income.")
k[4].metric("Disposable income", naira(extra.get("disposable_income")))
k[5].metric("Existing DTIR", pct(extra.get("existing_dtir")),
            help="Existing debt-to-income ratio.")

tab_cash, tab_dec, tab_bnpl, tab_raw = st.tabs(
    ["Cashflow signals", "Extra Cash offer", "BNPL offers", "Raw output"]
)

# ------------------------------------------------------------------- cashflow

with tab_cash:
    MONEY = ("base_net", "inflow_median", "disposable_income", "balance_floor", "salary")
    RATES = ("net_to_gross", "persistence", "zeroing_rate", "existing_dtir")
    OTHER = ("cv_net", "slope", "recency")
    LABELS = {"cv_net": "Volatility (CV of net flow)", "existing_dtir": "Existing DTIR"}

    rows = []
    for key in MONEY + RATES + OTHER:
        v = extra.get(key)
        label = LABELS.get(key, key.replace("_", " ").capitalize())
        if key == "salary":
            value = "••••" if v is not None else DASH  # masked: PII
        elif key in MONEY:
            value = naira(v)
        elif key in RATES:
            value = pct(v) if _num(v) is not None else (str(v) if v not in (None, "") else DASH)
        else:
            value = number(v, decimals=3) if _num(v) is not None else (str(v) if v not in (None, "") else DASH)
        rows.append({"Signal": label, "Value": value})
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

# ------------------------------------------------------------------- decision

with tab_dec:
    status_banner(extra.get("status"), bool(extra_cash_reasons))
    if extra_cash_reasons:
        st.subheader("Ineligibility reasons")
        st.dataframe(reasons_frame(extra_cash_reasons), width="stretch", hide_index=True)

    max_tenor = extra.get("max_tenor")
    st.dataframe(
        pd.DataFrame([
            {"Field": "Status", "Value": text(extra.get("status"))},
            {"Field": "Customer type", "Value": text(customer_type)},
            {"Field": "Risk band", "Value": extra.get("risk_band") or DASH},
            {"Field": "Risk score", "Value": integer(extra.get("risk_score"))},
            {"Field": "Pricing", "Value": extra.get("pricing") if extra.get("pricing") is not None else DASH},
            {"Field": "Max tenor", "Value": DASH if max_tenor is None else str(max_tenor)},
            {"Field": "Principal offer", "Value": naira(extra.get("principal_offer"))},
            {"Field": "Installment", "Value": naira(extra.get("installment"))},
            {"Field": "Max yield", "Value": number(extra.get("max_yield"))},
            {"Field": "Bureau score", "Value": DASH if extra.get("credit_score") is None
                                                else str(extra.get("credit_score"))},
        ]).astype(str),
        width="stretch", hide_index=True,
    )

# ----------------------------------------------------------------------- BNPL

with tab_bnpl:
    status_banner(bnpl.get("status"), bool(bnpl_reasons))
    if bnpl_reasons:
        st.subheader("Ineligibility reasons")
        st.dataframe(reasons_frame(bnpl_reasons), width="stretch", hide_index=True)

    if not bnpl_offers:
        st.info("No BNPL credit limits were returned for this applicant.")
    else:
        st.subheader("BNPL credit limits")
        st.dataframe(
            pd.DataFrame([
                {"Tenor": f"{t} months", "Credit limit": naira(v)}
                for t, v in sorted(bnpl_offers.items(), key=lambda kv: tenor_sort_key(kv[0]))
            ]),
            width="stretch", hide_index=True,
        )

        st.divider()
        st.subheader("Quote a specific item")

        item_schedule = ITEM_SCHEDULE.get(env) or {}
        if not item_schedule:
            st.warning(f"No item schedule is configured for `{env}`.")
        elif engine is None:
            st.warning("Engine session expired — press **Run decision** again to quote.")
        else:
            q1, q2, q3 = st.columns([3, 2, 2])
            asset = q1.selectbox("Asset", list(item_schedule.keys()), key="bnpl_asset",
                                 format_func=lambda s: s.replace("_", " ").title())
            tenors = sorted(item_schedule[asset], key=tenor_sort_key)
            ten = q2.selectbox("Tenor", tenors, key="bnpl_tenor",
                               format_func=lambda t: f"{t} months")
            price = q3.number_input("Item price (₦)", min_value=5000, step=5000,
                                    value=200000, key="item_price")

            credit_limit = lookup_tenor(bnpl_offers, ten)
            q = None
            if not _num(credit_limit):
                st.error(f"No credit limit is available for a {ten}-month tenor.")
            else:
                try:
                    q = engine.bnpl_quote(asset, ten, price, credit_limit, env=env)
                except Exception:  # noqa: BLE001
                    st.error("`bnpl_quote` failed unexpectedly.")
                    st.code(traceback.format_exc())

            if q:
                row1 = st.columns(4)
                row1[0].metric("Product price", naira(q.get("product_price")))
                row1[1].metric("Total down payment", naira(q.get("total_downpayment")))
                row1[2].metric("Loan amount", naira(q.get("loan_amount")))
                row1[3].metric("Monthly repayment", naira(q.get("monthly_repayment")))

                row2 = st.columns(4)
                row2[0].metric("Total repayment", naira(q.get("total_repayment")))
                row2[1].metric("Additional down payment", naira(q.get("compulsory_downpayment")),
                               help="Extra down payment required because the credit "
                                    "limit is below the amount to be financed.")
                row2[2].metric("Credit limit", naira(q.get("credit_limit")))
                row2[3].metric("Asset type", text(q.get("asset_name")))

                extra_dp = _num(q.get("compulsory_downpayment")) or 0
                if extra_dp > 0:
                    st.warning(
                        f"Down payment = {naira(q.get('required_downpayment'))} standard "
                        f"+ **{naira(extra_dp)} additional**, because only "
                        f"{naira(credit_limit)} can be financed at this tenor."
                    )

# ------------------------------------------------------------------ raw output

with tab_raw:
    st.json(results, expanded=False)
    st.download_button(
        "Download decision JSON",
        json.dumps(results, indent=2, default=str),
        file_name=f"decision_{date.today():%Y%m%d}.json",
        mime="application/json",
    )