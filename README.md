# risk-agent-deploy (Week 9 lab)

The Week 8 risk scoring agent deployed two ways, both LOCAL SIMULATIONS (no cloud calls anywhere):

- **simulated AWS**: `simaws` (IAM role + linter, ECR-like registry, task definition, enforcing
  run-task, network validator). The model sits behind a managed-endpoint stand-in: a local Ollama
  serving the larger model.
- **simulated on-prem**: the same service pointed at local Ollama with the smaller model.

Source agent: `github.com/nachiketht/insurance-orchestrator @ 924d9c2` (ported unchanged).

```
src/underwriting/   ported Week 8 code (risk agent, OllamaClient, models, errors)
src/riskservice/    run_risk_service + CLI (the deployable unit)
src/simaws/         local AWS simulation
deploy/             iam-policy.json, trust-policy.json, network.json, input/test_input.json
scripts/            deploy_aws_sim.py, deploy_onprem.py, run_all_evidence.sh, build_pdf.py, ...
docs/               deployment.md, comparison.md
evidence/           transcripts written by run_all_evidence.sh
tests/              pytest (no Ollama needed)
```

## Run on the work Mac

Needs Python 3.11+ and Ollama running with two models already installed. No pulls happen.

```bash
unzip risk-agent-deploy.zip && cd risk-agent-deploy
ollama list                      # note the two exact model ids
scripts/run_all_evidence.sh --cloud-model <larger-id> --onprem-model <smaller-id>
```

It creates `.venv`, installs the package, runs the tests, then runs both deployments and writes
`evidence/`. Zip the `evidence/` folder and send it back. The ids are never defaulted.
`--endpoint` defaults to `http://127.0.0.1:11434`.

Then build the PDF (refuses if evidence is missing): `python scripts/build_pdf.py`.

## Tests

`pip install -e ".[dev]" && pytest` (linter, enforcement allow/deny, network validator,
OllamaClient via httpx.MockTransport, service, byte-identity with Week 8).
