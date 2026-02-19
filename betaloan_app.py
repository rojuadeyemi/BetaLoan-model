from fastapi import FastAPI, HTTPException,Depends
from betaloan.optional import OptionalParams
from betaloan.loan_decision_engine import BetaLoan
from sqlalchemy.orm import Session
import logging
from betaloan.models import Log
from betaloan.schemas import CustomerData, LogResponse
from betaloan.database import SessionLocal, engine, Base
from typing import List
from pydantic import BaseModel
from typing import Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Loan Evaluation Service", version="1.0.0")
Base.metadata.create_all(bind=engine)  # Auto create table

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class EvaluateRequest(BaseModel):
    customer: CustomerData
    params: Optional[OptionalParams] = None

# Root route for testing
@app.get("/")
def root():
    return {"message": "Welcome to the Loan Evaluation API"}

# POST endpoint to evaluate customer data
@app.post("/evaluate")
def evaluate_customer(request: EvaluateRequest,
                      db: Session = Depends(get_db)):

    params = request.params or OptionalParams()

    loan = BetaLoan(
        request.customer.statement_data,
        request.customer.user_agent_str,
        request.customer.date_of_birth,
        request.customer.location,
        request.customer.credit_score,
        request.customer.tier,
        request.customer.on_time_repayment,
        request.customer.late_repayment,
        request.customer.due_date_repayment,
        params=params
    )

    results = loan.get_decision()

    print(results)

     # Save to DB
    try:
        log = Log(
                user_agent_str=request.customer.user_agent_str,
                date_of_birth=request.customer.date_of_birth,
                location= request.customer.location,
                on_time_repayment=request.customer.on_time_repayment,
                late_repayment=request.customer.late_repayment,
                due_date_repayment=request.customer.due_date_repayment,
                credit_score=request.customer.credit_score,
                tier=request.customer.tier,
                # Output fields
                **results
        )

        db.add(log)
        db.commit()
    except Exception as e:
        print(f"Failed to log request: {e}") 

    return results

# endpoint for getting the records from the DB (maximum of 50 records)
@app.get("/logs", response_model=List[LogResponse])
def get_logs(db: Session = Depends(get_db)):
    return db.query(Log).order_by(Log.timestamp.desc()).limit(50).all()

# Error handling for wrong data
@app.exception_handler(HTTPException)
def handle_error(request, exc):
    return {"status": "error", "detail": exc.detail}
