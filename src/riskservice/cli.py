"""Container entrypoint. Reads MODEL_ENDPOINT / MODEL_ID from the environment (or flags)."""

import argparse
import json
import os
import sys

from riskservice.service import file_sha256, run_risk_service
from underwriting.llm import OllamaClient


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="riskservice")
    ap.add_argument("--input", required=True)
    ap.add_argument("--endpoint", default=os.environ.get("MODEL_ENDPOINT"))
    ap.add_argument("--model", default=os.environ.get("MODEL_ID"))
    ap.add_argument("--target", default=os.environ.get("TARGET", "unspecified"))
    ap.add_argument("--out", help="also write the JSON result here")
    a = ap.parse_args(argv)
    if not a.endpoint or not a.model:
        print("error: --endpoint and --model (or MODEL_ENDPOINT / MODEL_ID) are required; "
              "pass a model id exactly as shown by `ollama list`", file=sys.stderr)
        return 2
    doc = json.load(open(a.input))
    client = OllamaClient(model=a.model, host=a.endpoint)
    try:
        client.preflight()
        client.warm_up()
        out = run_risk_service(doc, client)
    finally:
        client.close()
    out = {"target": a.target, "input_sha256": file_sha256(a.input), "endpoint": a.endpoint, **out}
    text = json.dumps(out, indent=2)
    if a.out:
        open(a.out, "w").write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
