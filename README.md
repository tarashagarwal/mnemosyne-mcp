# mnemosyne-mcp

<p align="center">
  <img src="https://github.com/user-attachments/assets/ebf5b04e-5270-40a1-b64e-686a7c2b87bd" width="700">
</p>

**Persistent knowledge and memory infrastructure for AI systems**

Mnemosyne MCP is a knowledge and memory server built around Apache Airflow pipelines that ingest documents and web data, enrich and structure information, and maintain a persistent, shared knowledge layer for AI clients and agents to retrieve consistent context over time.

---

## Architecture Overview

Mnemosyne MCP separates orchestration, processing, and storage concerns:

- Airflow orchestrates ingestion and enrichment pipelines
- Services handle document parsing, scraping, enrichment, and storage
- API layer (future) exposes stored knowledge for retrieval

```
Airflow DAGs
    ↓
Ingestion Services
    ↓
Enrichment Services
    ↓
Storage Layer
    ↓
Query / API Layer
```

---

## Repository Structure

```text
mnemosyne-mcp/
├── airflow/
│   ├── dags/          # Airflow DAG definitions (orchestration only)
│   ├── plugins/       # Custom Airflow operators, hooks, sensors
│   └── logs/          # Airflow runtime logs (auto-generated)
├── services/
│   ├── ingestion/     # Document and web ingestion logic
│   ├── enrichment/    # Cleaning, chunking, embeddings, metadata
│   └── storage/       # Persistence and indexing layer
├── api/               # Future query / MCP-compatible API
├── requirements.txt   # Project dependencies
└── README.md
```

---

## Running Airflow Locally

### Prerequisites

- Python 3.10
- pip and venv
- Linux or macOS recommended

---

### 1. Create and activate virtual environment

```bash
python3.10 -m venv airflow-venv
source airflow-venv/bin/activate
pip install --upgrade pip
```

---

### 2. Install project dependencies

```bash
pip install -r requirements.txt
```

---

### 3. Set Airflow home directory

```bash
export AIRFLOW_HOME=$(pwd)/airflow
```

(Optional: add this to your shell configuration.)

---

### 4. Install Apache Airflow

Airflow must be installed using constraints to avoid dependency conflicts.

```bash
export AIRFLOW_VERSION=2.9.3
export PYTHON_VERSION=3.10

pip install "apache-airflow==${AIRFLOW_VERSION}" \
  --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt"
```

---

### 5. Initialize Airflow database

```bash
airflow db init
```

---

### 6. Create admin user

```bash
airflow users create \
  --username admin \
  --password admin \
  --firstname Admin \
  --lastname User \
  --role Admin \
  --email admin@example.com
```

---

### 7. Start Airflow services

Open two terminals with the virtual environment activated.

**Terminal 1 – Start Webserver**

```bash
airflow webserver --port 8080
```

**Terminal 2 – Start Scheduler**

```bash
airflow scheduler
```

---

### 8. Access Airflow UI

Open your browser and visit:

```text
http://localhost:8080
```

Login using:
- Username: admin
- Password: admin

---

## Development Notes

- Keep DAG files lightweight; orchestration only
- Place all processing logic inside `services/`
- SQLite is used by default for local development
- Airflow example DAG warnings are expected and safe

---

## Roadmap

- Document ingestion pipelines (PDF, HTML, DOCX)
- Web scraping and enrichment workflows
- Structured storage and indexing layer
- Query and MCP-compatible API
- Public and managed deployment support

---

## License

MIT