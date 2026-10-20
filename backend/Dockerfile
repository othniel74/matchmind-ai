FROM python:3.12-slim
WORKDIR /app
COPY requirements*.txt ./
ARG INSTALL_AGENTS=false
RUN if [ "$INSTALL_AGENTS" = "true" ]; then pip install --no-cache-dir -r requirements-agents.txt; else pip install --no-cache-dir -r requirements.txt; fi
COPY app ./app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
