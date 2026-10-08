FROM python:3.10-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    LITELLM_LOCAL_MODEL_COST_MAP=True HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 \
    MPLCONFIGDIR=/tmp/matplotlib
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements-service.txt requirements-runtime.txt ./
RUN pip install --no-cache-dir -r requirements-service.txt -r requirements-runtime.txt \
    && pip check
COPY locagent_service ./locagent_service
COPY util ./util
COPY dependency_graph ./dependency_graph
COPY plugins ./plugins
COPY repo_index ./repo_index
USER 10001:10001
CMD ["python", "-m", "locagent_service.worker"]
