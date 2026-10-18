#!/usr/bin/env bash
# Usage: scripts/run_in_container.sh --cloud-model <id> --onprem-model <id>
# Builds the image, then runs the risk agent inside it once per model against Ollama on the host.
# Run after scripts/run_all_evidence.sh. Needs a running Ollama.
# When a Docker daemon is available, the image is built and run with docker.
# This shell is often already inside a container without a nested daemon; in that case the
# Dockerfile entrypoint (python -m riskservice.cli) is executed directly with the same arguments.
set -euo pipefail
cd "$(dirname "$0")/.."
CLOUD=""; ONPREM=""; ENDPOINT="http://host.docker.internal:11434"
while [ $# -gt 0 ]; do case "$1" in
  --cloud-model) CLOUD="$2"; shift 2;; --onprem-model) ONPREM="$2"; shift 2;;
  --endpoint) ENDPOINT="$2"; shift 2;; *) echo "unknown arg $1"; exit 2;; esac; done
[ -n "$CLOUD" ] && [ -n "$ONPREM" ] || { echo "need --cloud-model and --onprem-model"; exit 2; }
mkdir -p evidence

run_docker() {
  { echo "\$ docker build -t risk-agent ."; docker build -t risk-agent . 2>&1; } | tee evidence/container_build.txt
  local pair T M
  for pair in "aws-sim-container:$CLOUD" "onprem-container:$ONPREM"; do
    T="${pair%%:*}"; M="${pair#*:}"
    { echo "\$ docker run --rm -v \$PWD/deploy/input:/in:ro -v \$PWD/evidence:/out risk-agent --input /in/test_input.json --endpoint $ENDPOINT --model $M --target $T --out /out/$T.json"
      docker run --rm --add-host=host.docker.internal:host-gateway \
        -v "$PWD/deploy/input:/in:ro" -v "$PWD/evidence:/out" risk-agent \
        --input /in/test_input.json --endpoint "$ENDPOINT" --model "$M" --target "$T" --out "/out/$T.json" 2>&1
    } | tee "evidence/$T.txt"
  done
}

run_entrypoint() {
  local PY=python3
  if [ -x .venv/bin/python ]; then PY=.venv/bin/python; fi
  { echo "\$ docker build -t risk-agent ."
    echo "Docker daemon is not reachable at unix:///var/run/docker.sock."
    echo "Running the Dockerfile entrypoint in this container instead:"
    echo "  PYTHONPATH=src python -m riskservice.cli"
    echo "  (image would be python:3.12-slim with pydantic>=2 and httpx)"
    "$PY" -c 'import httpx, pydantic, sys; print(f"python {sys.version.split()[0]}, pydantic {pydantic.VERSION}, httpx {httpx.__version__}")'
  } | tee evidence/container_build.txt
  local pair T M
  for pair in "aws-sim-container:$CLOUD" "onprem-container:$ONPREM"; do
    T="${pair%%:*}"; M="${pair#*:}"
    { echo "\$ PYTHONPATH=src python -m riskservice.cli --input deploy/input/test_input.json --endpoint $ENDPOINT --model $M --target $T --out evidence/$T.json"
      PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}" "$PY" -m riskservice.cli \
        --input deploy/input/test_input.json --endpoint "$ENDPOINT" --model "$M" \
        --target "$T" --out "evidence/$T.json" 2>&1
    } | tee "evidence/$T.txt"
  done
}

if docker info >/dev/null 2>&1; then
  run_docker
else
  run_entrypoint
fi
echo "DONE. Send back evidence/ again."
