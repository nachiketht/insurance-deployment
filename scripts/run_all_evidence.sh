#!/usr/bin/env bash
# Usage: scripts/run_all_evidence.sh --cloud-model <id> --onprem-model <id> [--endpoint URL]
# Model ids must be exactly as shown by `ollama list`. Needs Python 3.11+ and a running Ollama.
set -euo pipefail
cd "$(dirname "$0")/.."
CLOUD=""; ONPREM=""; ENDPOINT="http://127.0.0.1:11434"
while [ $# -gt 0 ]; do case "$1" in
  --cloud-model) CLOUD="$2"; shift 2;; --onprem-model) ONPREM="$2"; shift 2;;
  --endpoint) ENDPOINT="$2"; shift 2;; *) echo "unknown arg $1"; exit 2;; esac; done
[ -n "$CLOUD" ] && [ -n "$ONPREM" ] || { echo "need --cloud-model and --onprem-model (see: ollama list)"; exit 2; }
command -v ollama >/dev/null || { echo "ollama CLI not found"; exit 2; }
curl -sf "$ENDPOINT/api/tags" >/dev/null || { echo "Ollama not reachable at $ENDPOINT (start it)"; exit 2; }

PY=python3
if [ ! -d .venv ]; then python3 -m venv .venv; .venv/bin/pip install -q -e ".[dev]"; fi
PY=.venv/bin/python
mkdir -p evidence

echo "== unit tests ==" | tee evidence/pytest.txt
$PY -m pytest -v 2>&1 | tee -a evidence/pytest.txt

$PY scripts/deploy_aws_sim.py --cloud-model "$CLOUD" --endpoint "$ENDPOINT" 2>&1 | tee evidence/aws_sim_run.txt

{ echo "\$ python -m simaws iam get-role --name risk-service-task --state .simaws/state.json"
  $PY -m simaws iam get-role --name risk-service-task --state .simaws/state.json; } | tee evidence/iam_role.txt

{ echo "\$ ollama --version"; ollama --version 2>&1
  echo; echo "\$ ollama list"; ollama list 2>&1
  echo; echo "# models used: cloud-stand-in=$CLOUD  on-prem=$ONPREM  endpoint=$ENDPOINT"
  echo; echo "\$ python -m simaws iam get-role --name risk-service-task"
  $PY -m simaws iam get-role --name risk-service-task --state .simaws/state.json
} 2>&1 | tee evidence/ollama_setup.txt

$PY scripts/deploy_onprem.py --onprem-model "$ONPREM" --endpoint "$ENDPOINT" 2>&1 | tee evidence/onprem_run.txt
$PY scripts/compare_runs.py | tee /dev/null
echo
echo "DONE. Send back the whole evidence/ folder (see README: Run on the work Mac)."
