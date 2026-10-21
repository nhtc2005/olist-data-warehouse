# E-commerce Data Warehouse and DSS

This project builds a small decision-support system for the Olist e-commerce dataset. It loads raw CSV files into PostgreSQL, rebuilds a dimensional warehouse, derives a late-delivery feature mart, and presents sales and delivery-risk analysis in Streamlit.

## Architecture

```text
Raw CSV files
    -> staging
    -> dw star schema
    -> mart.order_delivery_ml_features
    -> Logistic Regression scoring
    -> mart.order_late_risk
    -> Streamlit dashboard
```

Airflow runs the three data pipelines on demand:

1. `olist_staging_pipeline`: profiles the source files, reloads staging, and validates it.
2. `olist_dw_pipeline`: rebuilds and validates the data warehouse.
3. `olist_ml_features_pipeline`: rebuilds and validates the ML feature mart.

Model training is a deliberate local step because the Olist data is static. It uses a chronological split and writes the current model output for the dashboard.

## Business questions

The system supports the following questions:

1. How do revenue and order volume change over time?
2. Which product categories and customer states contribute the most revenue?
3. How does the late-delivery rate change by month?
4. Which scored orders have the highest predicted risk of late delivery and should be prioritised for review?

## Prerequisites

- Docker Desktop with Docker Compose
- Python 3.12 or later for the notebook, model-training script, and Streamlit dashboard

Create `.env` from `.env.example` and set the required database and Airflow credentials before the first startup.

## Run the data platform

Start the containers from the project root:

```powershell
docker compose up --build
```

Open Airflow at `http://localhost:8080`, then run the DAGs in this order:

```text
olist_staging_pipeline
    -> olist_dw_pipeline
    -> olist_ml_features_pipeline
```

The warehouse database is exposed through the port configured by `DB_PORT` in `.env`.

## Train and score the model

After the ML feature-mart DAG finishes successfully, install the local dependencies if needed:

```powershell
pip install -r requirements-notebook.txt
```

Then train the selected Logistic Regression model and generate risk scores:

```powershell
python src\ml\train_model.py
```

The script overwrites the current model and metadata under `models/`, then refreshes `mart.order_late_risk` with validation and test scores.

## Run the dashboard

Install the dashboard dependencies if needed:

```powershell
pip install -r requirements-streamlit.txt
```

Start Streamlit:

```powershell
streamlit run src\app\app.py
```

Open `http://localhost:8501`. The dashboard contains:

- **Overview:** revenue, orders, average order value, and late-delivery trends.
- **Sales analysis:** revenue by product category and customer state.
- **Late-delivery DSS:** model metrics, high-risk trend, and prioritised orders.

## Project structure

```text
data/raw/          Source Olist CSV files
dags/              Airflow DAG definitions
src/etl/           Staging and warehouse transformations
src/ml/            Feature mart, model training, and validation
src/app/           Streamlit entry point, pages, and queries
docs/              Data, warehouse, and modeling documentation
models/            Generated model and metadata files
```

## Documentation

- [Source data profile](docs/source_data_profile.md)
- [Data dictionary](docs/data_dictionary.md)
- [Modeling notes](docs/modeling.md)
