PROJECT_ROOT := $(shell pwd)
VENV := $(PROJECT_ROOT)/airflow-venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
AIRFLOW := $(VENV)/bin/airflow
UVICORN := $(VENV)/bin/uvicorn

QDRANT_DATA := /home/tarash-ubuntu/qdrant_data
QDRANT_CONTAINER := qdrant

.PHONY: setup qdrant airflow mcp all stop

setup:
	@echo "🔧 Activating venv and installing dependencies..."
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

qdrant:
	@echo "🧠 Starting Qdrant..."
	docker rm -f $(QDRANT_CONTAINER) || true
	docker run -d \
		--name $(QDRANT_CONTAINER) \
		-p 6333:6333 \
		-p 6334:6334 \
		-v $(QDRANT_DATA):/qdrant/storage \
		qdrant/qdrant

airflow:
	@echo "🌬 Starting Airflow using venv..."
	$(AIRFLOW) webserver --port 8080 

mcp:
	@echo "🧠 Starting MCP HTTP server using venv..."
	$(UVICORN) mcp_server:app --host 0.0.0.0 --port 8000 &

all: setup qdrant airflow mcp
	@echo "🚀 All services started inside airflow-venv"

stop:
	@echo "🛑 Stopping services..."
	docker stop $(QDRANT_CONTAINER) || true
	pkill -f "$(AIRFLOW)" || true
	pkill -f "$(UVICORN)" || true
