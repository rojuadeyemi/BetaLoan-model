from sqlalchemy import Column, Integer, String, Float, DateTime, JSON
from datetime import datetime, timezone
from betaloan.database import Base

class Log(Base):
    __tablename__ = "beta_loan_TBL"

    # Auto generated fields
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Input fields
    credit_score = Column(Float)
    date_of_birth = Column(String)
    location = Column(String)
    tier = Column(Integer)
    user_agent_str = Column(String)
    on_time_repayment = Column(Integer)
    late_repayment = Column(Integer)
    due_date_repayment = Column(Integer)


    # Output fields
    status = Column(String)
    risk_band = Column(String)
    risk_score = Column(Float)
    max_amount = Column(Float)
    pricing = Column(Float)
    max_tenor = Column(Float)
    net_to_gross = Column(Float)
    inflow_median = Column(Float)
    base_net = Column(Float)
    cv_net = Column(Float)
    persistence = Column(Float)
    zeroing_rate = Column(Float)
    disposable_income = Column(Float)
    slope = Column(Float)
    betting_count = Column(Integer)
    balance_floor = Column(Float)
    salary=Column(Float)
    customer_type = Column(String)
    existing_dtir = Column(Float)
    installment = Column(Float)
    principal_offer = Column(Float)
    max_yield = Column(Float)
    ineligibility_reasons = Column(JSON)
