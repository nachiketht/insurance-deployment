#!/usr/bin/env bash
# Usage: scripts/run_in_container.sh --cloud-model <id> --onprem-model <id>
# Builds the image, then runs the risk agent inside it once per model against Ollama on the host.
# Run after scripts/run_all_evidence.sh. Needs Docker and a running Ollama.
set -euo pipefail
cd "$(dirname "$0")/.."
CLOUD=""; ONPREM=""; ENDPOINT="http://host.docker.internal:11434"
while [ $# -gt 0 ]; do case "$1" in
  --cloud-model) CLOUD="$2"; shift 2;; --onprem-model) ONPREM="$2"; shift 2;;
  --endpoint) ENDPOINT="$2"; shift 2;; *) echo "unknown arg $1"; exit 2;; esac; done
[ -n "$CLOUD" ] && [ -n "$ONPREM" ] || { echo "need --cloud-model and --onprem-model"; exit 2; }
mkdir -p evidence
{ echo "\$ docker build -t risk-agent ."; docker build -t risk-agent . 2>&1; } | tee evidence/container_build.txt
for pair in "aws-sim-container:$CLOUD" "onprem-container:$ONPREM"; do
  T="${pair%%:*}"; M="${pair#*:}"
  { echo "\$ docker run --rm -v \$PWD/deploy/input:/in:ro -v \$PWD/evidence:/out risk-agent --input /in/test_input.json --endpoint $ENDPOINT --model $M --target $T --out /out/$T.json"
    docker run --rm --add-host=host.docker.internal:host-gateway \
      -v "$PWD/deploy/input:/in:ro" -v "$PWD/evidence:/out" risk-agent \
      --input /in/test_input.json --endpoint "$ENDPOINT" --model "$M" --target "$T" --out "/out/$T.json" 2>&1
  } | tee "evidence/$T.txt"
done
echo "DONE. Send back evidence/ again."
