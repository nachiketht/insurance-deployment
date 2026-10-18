#!/usr/bin/env python3
"""Compare the two real run results against each other and against the rule-based reference."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from simaws.reference import reference_factors, reference_score  # noqa: E402


def main() -> int:
    ev = ROOT / "evidence"
    aws = json.loads((ev / "aws_result.json").read_text())
    onp = json.loads((ev / "onprem_result.json").read_text())
    doc = json.loads((ROOT / "deploy/input/test_input.json").read_text())
    ref_f, ref_s = reference_factors(doc), reference_score(doc)
    lines = ["Measured comparison (values copied from evidence/aws_result.json and "
             "evidence/onprem_result.json)", ""]
    lines.append(f"same input sha256: {aws['input_sha256'] == onp['input_sha256']} "
                 f"({aws['input_sha256']})")
    lines.append(f"reference (from the prompt's rules): score {ref_s}, factors {ref_f}")
    lines.append("")
    lines.append(f"{'target':<12}{'model':<22}{'score':>6}{'calls':>7}{'in_tok':>8}"
                 f"{'out_tok':>9}{'ms':>10}  matches_reference")
    for r in (aws, onp):
        res, u = r["result"], r["usage"]
        got = {f["name"]: f["points"] for f in res["factors"] if f["points"] > 0}
        lines.append(f"{r['target']:<12}{str(u['model']):<22}{res['score']:>6}{u['model_calls']:>7}"
                     f"{u['input_tokens']:>8}{u['output_tokens']:>9}{u['duration_ms']:>10}  "
                     f"{got == ref_f}")
    lines.append("")
    lines.append(f"scores equal across targets: {aws['result']['score'] == onp['result']['score']}")
    for r in (aws, onp):
        lines.append(f"{r['target']} rationale: {r['result']['rationale']}")
    out = "\n".join(lines) + "\n"
    (ev / "comparison_numbers.txt").write_text(out)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
