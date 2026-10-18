# Real-deployment shape. The lab sandbox has no Docker daemon, so simaws pushes a deterministic
# source archive of the same files instead (see docs/deployment.md).
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir "pydantic>=2" httpx
COPY src/ /app/src/
ENV PYTHONPATH=/app/src
ENTRYPOINT ["python", "-m", "riskservice.cli"]
