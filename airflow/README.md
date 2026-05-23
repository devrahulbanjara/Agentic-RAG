# Airflow Configuration

Apache Airflow configuration and DAGs.
## Contents

- `dags/hello_world_dag.py`: smoke-test DAG verifying Airflow scheduler, API, and database connectivity.
- `init-db.sql`: database initialization script.

## Directory Structure

```
airflow/
├── README.md           # This file
├── init-db.sql         # Database initialization
└── dags/
    └── hello_world_dag.py  # Connectivity smoke-test DAG
```

## Usage

Airflow runs via Docker Compose:

- Web UI: http://localhost:8080
- Default credentials: `admin` / auto-generated password

## Roadmap

Planned DAGs:
- arXiv paper fetching
- PDF processing workflows
- Data pipeline orchestration
