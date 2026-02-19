# 🚀 BetaLoan -- Risk Scoring & Underwriting Engine

**BetaLoan** is a production-ready, rule-based credit risk scoring and
underwriting engine built for fintech lending environments.

The system ingests structured JSON bank statement data and customer
metadata, engineers financial and behavioral features, determines
eligibility, classifies customers (Salaried vs Non-Salaried), applies
differentiated underwriting logic, and generates explainable loan
decisions.

The application is built using FastAPI, PostgreSQL, and Docker, and is
designed for scalability, auditability, and enterprise deployment.

------------------------------------------------------------------------

# 🏗 System Architecture

                    ┌───────────────┐
                    │   Client App  │
                    └───────┬───────┘
                            │
                            ▼
                    ┌───────────────┐
                    │   FastAPI     │
                    │  REST Layer   │
                    └───────┬───────┘
                            │
                            ▼
                    ┌───────────────┐
                    │ Risk Engine   │
                    │ - JSON Parser │
                    │ - Feature Eng │
                    │ - Qualification│
                    │ - Underwriting│
                    └───────┬───────┘
                            │
                            ▼
                    ┌───────────────┐
                    │ PostgreSQL    │
                    │ Decision Logs │
                    └───────────────┘

------------------------------------------------------------------------

# 📥 Data Sources

## 1️⃣ JSON Bank Statement (via API)

-   Account inflows & outflows
-   Daily balances
-   Transaction timestamps
-   Salary detection
-   Betting detection etc

## 2️⃣ Customer Metadata

-   Date of birth
-   Location
-   Device User agent
-   Credit score
-   Account tier
-   On-time repayment count
-   Late repayment count
-   Due date repayment count

------------------------------------------------------------------------

# ⚙️ Model Development

## Feature Engineering

Derived metrics include:

-   Net-to-gross ratio
-   Median inflow
-   Base net cashflow
-   Persistence ratio
-   Zeroing rate
-   Disposable income
-   Betting count
-   Balance floor
-   Salary estimation
-   Existing DTIR
-   Trend slope (where applicable)

## Qualification Logic

All customers pass through the same eligibility criteria:

-   Net cashflow must be positive
-   Zero balance rate must be within threshold
-   Disposable income must meet minimum
-   Debt-to-income ratio must be acceptable
-   The account must be minimum of tier 2
-   Credit Score must be at least 650 or null for first timer
-   The applicants must be in location not blacklisted from our services
-   Age must be between 21 and 65

If any condition fails → `status = ineligible`

## Customer Classification

Customers are classified as:

-   Salaried
-   Non-salaried

## Underwriting Logic

Underwriting differs by customer type:

-   Income stability weighting
-   Cashflow persistence analysis
-   Behavioral risk penalties
-   Debt burden adjustment

------------------------------------------------------------------------

## Model Deployment

### Prerequisites

- Python 3.10-3.12
- Pip (Python package installer)

### Setup

1. **Clone the repository:**

    ```sh
    git clone https://github.com/rojuadeyemi/BetaLoan-model.git
    cd BetaLoan-model
    ```

2. **Create a virtual environment:**

You can also create a virtual environment manually using the following approach.

For *Linux/Mac*:

```sh
python -m venv .venv
source .venv/bin/activate 
```

For *Windows*:
    
```sh
python -m venv .venv
.venv\Scripts\activate
```

3. **Install the required dependencies:**

    ```sh
    pip install -U pip
    pip install -r requirements.txt
    ```

4. **Create an Environment File**

Create a .env file with the DB credentials:
    ```sh
    POSTGRES_USER=postgres_user
    POSTGRES_PASSWORD=user_password
    POSTGRES_DB=betaloan_db
    POSTGRES_HOST=localhost
    POSTGRES_PORT=5432
    ```

# 💻 Local Setup (Without Docker)

1. Start PostgreSQL locally and create the database (betaloan_db).

2. Run the API:

`uvicorn betaloan_app:app --host 0.0.0.0 --port 8000 --reload`

3. Access Swagger docs at:

    http://127.0.0.1:8000/docs


# 🐳 Docker Setup

1. Build & run:

    `docker-compose up --build`

2. Stop services:

    `docker-compose down`

3. Access API:

    `http://localhost:8000/docs`


# 🧪 Alternative Docker Setup (Recommended)
1. Pull from Betaloan image from Docker Hub

    `docker pull aderoju/betaloan:latest`

2. Create a `docker-compose.yml` file

```
services:
  app:
    image: aderoju/betaloan:latest
    ports:
      - "8000:8000"
    depends_on:
      - db
    env_file:
      - .env

  db:
    image: postgres:15
    container_name: postgres_db
    restart: always
    env_file:
      - .env
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432" # this allows external client to interract
                    # should be removed for production

volumes:
  pgdata:

```

3. Then run everything - No need to rebuild
    `docker-compose up -d`

4. 3. Access API:

    `http://localhost:8000/docs`

------------------------------------------------------------------------
# 📊 Sample Input

```
{"customer":{"credit_score":700,
"tier":2,
"on_time_repayment":0,
"late_repayment":0,
"due_date_repayment":0,                       
"date_of_birth":"09-11-1991",           
"location":"ibadan",                              
"user_agent_str":"Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko)",
"statement_data":{
    "status": "successful",
    "message": "Transaction retrieved successfully",
    "timestamp": "2025-04-09T11:29:09.598Z",
    "data": [
        {
            "id": "67f63cb02b37b4800e6262c0",
            "narration": "NIBSS Instant Payment Outward 000013250408192140000082931531 NIP TRANSFER TO OPAY - Pascal Thuraya",
            "amount": 10000000,
            "type": "debit",
            "category": null,
            "balance": 68804840,
            "date": "2025-04-08T01:00:00.000Z",
            "currency": "NGN"
        }
        ]
        }
}
}
```

# 📊 Sample Model Output

``` python
{'net_to_gross': -0.000875701385362034,
 'inflow_median': 998782.25,
 'base_net': -874.6350000000093,
 'cv_net': None,
 'persistence': 1.0,
 'zeroing_rate': 0.40540540540540543,
 'disposable_income': 401623.0545,
 'slope': None,
 'betting_count': 0,
 'balance_floor': 359.115,
 'salary': 738782.29,
 'customer_type': 'salaried',
 'existing_dtir': 0.006371572604968644,
 'status': 'ineligible',
 'risk_score': 50.0,
 'risk_band': 'D',
 'max_tenor': 30,
 'pricing': 0.007,
 'installment': 4685.6023025,
 'principal_offer': 116171.95791322314,
 'max_yield': 24396.111161776862,
 'ineligibility_reasons': [{'reason_code': 'NEGATIVE_NET_CASHFLOW',
   'reason_message': 'Net cashflow (-875) less than 0 is not acceptable'},
  {'reason_code': 'HIGH_ZEROING',
   'reason_message': 'Account has high proportion (41%) of days hitting zero balance'}]}

```

Decisions are fully explainable and include ineligibility reasons where
applicable.

------------------------------------------------------------------------

# 🌐 API Endpoints

## POST `/evaluate`

-   Accepts input payload
-   Runs underwriting engine
-   Stores inputs & outputs
-   Returns decision

## GET `/logs`

-   Returns latest 50 stored evaluations
-   Supports audit & monitoring

------------------------------------------------------------------------
### Technologies Used:
* Tools: Python, Docker, docker-compose
* Frameworks and Libraries: FastAPI, Pandas, NumPy, SQLAlchemy
* Database: PostgreSQL, PGAdmin
* Version Control: Git
-------------------------------------------------------------------------

# 📈 Model Evaluation Strategy

The model performance can be evaluated using:

-   Default rate by risk band
-   Portfolio yield
-   Acceptance rate
-   Vintage analysis
-   Risk band migration tracking

------------------------------------------------------------------------

# 🔮 Future Roadmap

-   Real-time ingestion pipeline
-   Kafka/RabbitMQ integration
-   ML-driven probability of default model
-   Monitoring dashboard
-   Model drift detection
-   Automated risk reporting

------------------------------------------------------------------------
