FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir "pydantic>=2" httpx
COPY src/ /app/src/
ENV PYTHONPATH=/app/src
ENTRYPOINT ["python", "-m", "riskservice.cli"]
