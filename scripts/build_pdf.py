#!/usr/bin/env python3
"""Build week9-submission.pdf from the repo and evidence/. Refuses if evidence is missing."""

import html
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EV = ROOT / "evidence"
REQUIRED = ["iam_role.txt", "aws_sim_run.txt", "ollama_setup.txt", "onprem_run.txt",
            "aws_result.json", "onprem_result.json", "comparison_numbers.txt"]

CSS = """
@page { size: A4; margin: 16mm 15mm; }
* { box-sizing: border-box; }
body { font-family: 'Helvetica Neue', Arial, sans-serif; color: #111; margin: 0; }
.cover { height: 252mm; display: flex; flex-direction: column; justify-content: center; }
.cover h1 { font-size: 27pt; margin: 0 0 8px; }
.cover .sub { font-size: 13pt; color: #555; margin-bottom: 24px; }
.cover .line { font-size: 11pt; color: #333; margin: 0 0 10px; max-width: 170mm; }
.cover .repo { font-family: monospace; color: #1f6feb; margin-bottom: 30px; }
.cover .toc-title { font-size: 13pt; font-weight: 600; color: #1f6feb; margin: 0 0 6px; }
.cover table { border-collapse: collapse; font-size: 10pt; }
.cover td { padding: 3px 14px 3px 0; vertical-align: top; } .cover td:last-child { color: #555; }
h2 { font-size: 15pt; border-bottom: 2.5px solid #1f6feb; padding-bottom: 5px; margin: 0 0 12px; }
section { page-break-before: always; }
pre { margin: 6px 0 12px; padding: 9px 11px; border-radius: 6px; font-size: 7.4pt; line-height: 1.28;
      white-space: pre-wrap; word-break: break-word; font-family: Menlo, 'DejaVu Sans Mono', monospace; }
pre.term { background: #0d1117; color: #e6edf3; }
pre.code { background: #f6f8fa; border: 1px solid #d0d7de; }
pre.doc { background: #fffdf5; border: 1px solid #e3dcc3; font-size: 7.8pt; }
.file { font-family: monospace; font-size: 8.6pt; color: #1f6feb; margin: 10px 0 0; break-after: avoid; }
.note { font-size: 9.5pt; color: #444; margin: 6px 0 2px; }
"""


def esc(t: str) -> str:
    return html.escape(t)


def term(title: str, text: str) -> str:
    return f'<div class="file">{esc(title)}</div><pre class="term">{esc(text.rstrip())}</pre>'


def code(title: str, text: str) -> str:
    return f'<div class="file">{esc(title)}</div><pre class="code">{esc(text.rstrip())}</pre>'


def doc(title: str, text: str) -> str:
    return f'<div class="file">{esc(title)}</div><pre class="doc">{esc(text.rstrip())}</pre>'


def read(rel: str) -> str:
    return (ROOT / rel).read_text()


def phases(text: str, first: int, last: int) -> str:
    parts = re.split(r"(?m)^(?==== Phase \d+:)", text)
    keep = [p for p in parts if (m := re.match(r"=== Phase (\d+):", p)) and first <= int(m[1]) <= last]
    return "".join(keep)


def excerpt(rel: str, start: str, stop: str | None = None) -> str:
    t = read(rel)
    a = t.index(start)
    b = t.index(stop, a + 1) if stop else len(t)
    return t[a:b]


def check_evidence() -> None:
    missing = [f for f in REQUIRED if not (EV / f).exists() or not (EV / f).read_text().strip()]
    if missing:
        sys.exit("Refusing to build: missing or empty evidence files in evidence/:\n  "
                 + "\n  ".join(missing)
                 + "\nProduce them with: scripts/run_all_evidence.sh --cloud-model <id> "
                   "--onprem-model <id>")
    aws = json.loads((EV / "aws_result.json").read_text())
    onp = json.loads((EV / "onprem_result.json").read_text())
    problems = []
    if "fake" in json.dumps([aws["usage"], onp["usage"]]).lower():
        problems.append("results name a 'fake' model (test double), not real Ollama output")
    want = subprocess.run(["sha256sum", str(ROOT / "deploy/input/test_input.json")],
                          capture_output=True, text=True).stdout.split()[0]
    if aws["input_sha256"] != want or onp["input_sha256"] != want:
        problems.append("input sha256 in results does not match deploy/input/test_input.json")
    if not (EV / "aws_sim_run.txt").read_text().count(want) or \
            not (EV / "onprem_run.txt").read_text().count(want):
        problems.append("input sha256 is not printed in both run transcripts")
    if not aws["usage"].get("input_tokens") or not onp["usage"].get("input_tokens"):
        problems.append("a result has zero input tokens (no real model call)")
    if problems:
        sys.exit("Refusing to build: " + "; ".join(problems))


def build() -> Path:
    check_evidence()
    aws_run, on_run = read("evidence/aws_sim_run.txt"), read("evidence/onprem_run.txt")
    aws = json.loads((EV / "aws_result.json").read_text())
    onp = json.loads((EV / "onprem_result.json").read_text())
    models = f"{aws['usage']['model']} (cloud stand-in), {onp['usage']['model']} (on-prem)"
    toc = [
        ("1. IAM role and attached policy", "evidence/iam_role.txt, deploy/iam-policy.json, linter"),
        ("2. Building, pushing, deploying under the role", "deploy transcript phases 3-4"),
        ("3. Deployment running, correct output", "deploy transcript phase 5, input hash"),
        ("4. Networking configuration", "deploy/network.json, deploy transcript phase 1"),
        ("5. Ollama setup and the service code", "evidence/ollama_setup.txt, src/riskservice, llm.py"),
        ("6. On-prem run on the same input", "evidence/onprem_run.txt"),
        ("7. Deployment, networking, access control doc", "docs/deployment.md"),
        ("8. Cost / complexity / quality comparison", "docs/comparison.md + measured numbers"),
    ]
    out = [f"<html><head><meta charset='utf-8'><style>{CSS}</style></head><body>"]
    out.append(
        '<div class="cover"><h1>Deploying the Risk Scoring Agent</h1>'
        '<div class="sub">Week 9 Lab Submission</div>'
        '<div class="line">One agent from the Week 8 underwriting pipeline (risk scoring), deployed '
        'two ways on the same frozen test input: a simulated AWS environment (local simaws control '
        'plane: IAM, registry, ECS-style tasks, network placement) and a simulated on-prem '
        'environment (local Ollama).</div>'
        '<div class="line">No cloud service is used or called anywhere. Both targets are local '
        'simulations, labeled as such in every artifact. Every transcript here was produced by '
        f'running the scripts in the repository. Models that produced the evidence: {esc(models)}.'
        '</div><div class="line repo">repo: risk-agent-deploy (local; source agent '
        'nachiketht/insurance-orchestrator @ 924d9c2)</div>'
        '<div class="toc-title">Contents</div><table>'
        + "".join(f"<tr><td>{esc(a)}</td><td>{esc(b)}</td></tr>" for a, b in toc)
        + "</table></div>")

    def sec(n: int, intro: str, *blocks: str) -> None:
        out.append(f'<section><h2>{esc(toc[n-1][0])}</h2><div class="note">{esc(intro)}</div>'
                   + "".join(blocks) + "</section>")

    lint = excerpt("src/simaws/iam.py", "def lint_policy", "def _as_list")
    sec(1, "The dedicated task role, every permission justified, the linter that refuses wildcard "
           "or unjustified policies, and the get-role transcript from the simulated account.",
        term("evidence/iam_role.txt", read("evidence/iam_role.txt")),
        code("deploy/iam-policy.json", read("deploy/iam-policy.json")),
        term("linter rejecting a bad variant (evidence/aws_sim_run.txt, phase 2)",
             phases(aws_run, 2, 2)),
        code("src/simaws/iam.py: lint_policy", lint))
    sec(2, "Registry push and ECS-style deployment with the role assigned explicitly. The image is "
           "a deterministic source archive (no Docker daemon in the sandbox) with sha256 digest "
           "discipline; run-task enforces the role before executing.",
        term("evidence/aws_sim_run.txt (phases 3-4)", phases(aws_run, 3, 4)))
    sec(3, "The task ran from the pulled image under the role and produced a risk score for the "
           "frozen input. The input sha256 is printed in the transcript header and in the result.",
        term("evidence/aws_sim_run.txt (header)", aws_run.split("=== Phase 1")[0]),
        term("evidence/aws_sim_run.txt (phase 5: task log)", phases(aws_run, 5, 5)))
    sec(4, "Private app subnet, zero ingress, one egress rule tcp/11434 to the private model "
           "subnet; the validator ran before anything was deployed and denial tests cover violations.",
        code("deploy/network.json", read("deploy/network.json")),
        term("evidence/aws_sim_run.txt (phase 1)", phases(aws_run, 1, 1)),
        code("src/simaws/network.py", read("src/simaws/network.py")))
    sec(5, "Ollama version and installed models, plus the code that calls it: the service wrapper "
           "and the unchanged OllamaClient.",
        term("evidence/ollama_setup.txt", read("evidence/ollama_setup.txt")),
        code("src/riskservice/service.py", read("src/riskservice/service.py")),
        code("src/riskservice/cli.py", read("src/riskservice/cli.py")),
        code("src/underwriting/llm.py: OllamaClient.complete",
             excerpt("src/underwriting/llm.py", "    def complete(\n        self,\n        *,\n"
                     "        agent", "    def preflight")))
    sec(6, "The same service, same input hash, same agent code hashes, run against local Ollama "
           "with the on-prem model inside the boundary check.",
        term("evidence/onprem_run.txt", on_run))
    sec(7, "Full deployment, networking and access-control documentation.",
        doc("docs/deployment.md", read("docs/deployment.md")))
    sec(8, "Comparison from the measured runs, then the written recommendation.",
        term("evidence/comparison_numbers.txt", read("evidence/comparison_numbers.txt")),
        doc("docs/comparison.md", read("docs/comparison.md")))
    out.append("</body></html>")
    html_path = ROOT / "week9-submission.html"
    html_path.write_text("".join(out))
    pdf = ROOT / "week9-submission.pdf"
    chrome = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chrome")
    if not chrome:
        sys.exit(f"No Chrome/Chromium found. Open {html_path} and print to PDF.")
    subprocess.run([chrome, "--headless", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={pdf}", html_path.as_uri()], check=True, capture_output=True)
    print(f"wrote {pdf}")
    return pdf


if __name__ == "__main__":
    build()
