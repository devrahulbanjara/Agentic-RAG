from datetime import datetime, timedelta

import psycopg2
from airflow import DAG
from airflow.operators.python import PythonOperator
from src.core.config import settings


def hello_world():
    print("Hello from Airflow! ....")
    return "success"


def check_services():
    """Check Postgres is reachable."""
    conn = psycopg2.connect(settings.postgres_psycopg2_dsn)
    try:
        print("Database: Connected successfully")
    finally:
        conn.close()

    return "Services are accessible"


default_args = {
    "owner": "rahul",
    "depends_on_past": False,
    "start_date": datetime(2024, 1, 1),
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

dag = DAG(
    "hello_world",
    default_args=default_args,
    description="Hello World DAG",
    schedule=None,
    catchup=False,
    tags=["testing"],
)

hello_task = PythonOperator(
    task_id="hello_world",
    python_callable=hello_world,
    dag=dag,
)

service_check_task = PythonOperator(
    task_id="check_services",
    python_callable=check_services,
    dag=dag,
)

hello_task >> service_check_task
