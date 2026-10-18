#!/usr/bin/env python3
"""Build week9-defense-sheet.pdf (1-2 pages). Embeds measured numbers if evidence/ exists."""

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EV = ROOT / "evidence"

measured = ""
if (EV / "aws_result.json").exists() and (EV / "onprem_result.json").exists():
    rows = ""
    for f in ("aws_result.json", "onprem_result.json"):
        r = json.loads((EV / f).read_text())
        u = r["usage"]
        rows += (f"<tr><td>{r['target']}</td><td>{u['model']}</td><td>{r['result']['score']}</td>"
                 f"<td>{u['input_tokens']}/{u['output_tokens']}</td><td>{u['duration_ms']} ms</td></tr>")
    measured = ("<h3>Measured (from evidence/)</h3><table><tr><th>target</th><th>model</th><th>score</th>"
                f"<th>tokens in/out</th><th>agent time</th></tr>{rows}</table>")
else:
    measured = ("<p><i>Measured token and latency numbers come from evidence/comparison_numbers.txt "
                "after the run; rebuild this sheet then to embed them.</i></p>")

HTML = f"""<html><head><meta charset='utf-8'><style>
@page {{ size: A4; margin: 13mm 14mm; }}
body {{ font-family: Helvetica, Arial, sans-serif; font-size: 9.6pt; color: #111; line-height: 1.32; }}
h1 {{ font-size: 16pt; margin: 0 0 2px; }} h3 {{ font-size: 11pt; color: #1f6feb; margin: 10px 0 3px; }}
.two {{ display: flex; gap: 12px; }} .two > div {{ flex: 1; }}
.real {{ background: #eef9f0; border: 1px solid #b7e0bf; padding: 6px 9px; border-radius: 5px; }}
.sim {{ background: #fff8e1; border: 1px solid #e6c76a; padding: 6px 9px; border-radius: 5px; }}
ul {{ margin: 3px 0 3px 16px; padding: 0; }} table {{ border-collapse: collapse; font-size: 9pt; }}
td, th {{ border: 1px solid #ccc; padding: 2px 6px; text-align: left; }}
.q {{ font-weight: 600; margin-top: 6px; }}
</style></head><body>
<h1>Week 9 defense sheet: risk scoring agent, AWS-sim vs on-prem</h1>
<div>One agent, deployed twice, same unchanged code, same frozen input (sha256 5b5917e1...a121).</div>
<h3>What is real vs simulated</h3>
<div class="two"><div class="real"><b>REAL</b><ul>
<li>The Week 8 agent code, byte-identical (tested against commit 924d9c2)</li>
<li>Local Ollama running both models; tokens and ms come from Ollama's counters</li>
<li>Least-privilege linter and policy evaluation (exact match, no wildcards)</li>
<li>run-task enforcement: denies before executing; 5 denial cases in the transcript, more in unit tests</li>
<li>Digest discipline: deterministic archive, digest verified on pull, run by digest only</li>
</ul></div><div class="sim"><b>SIMULATED</b><ul>
<li>AWS itself: simaws is my own local control plane, arn:simaws: ARNs, JSON state</li>
<li>No Docker image: a deterministic source archive stands in (Dockerfile shows the real shape)</li>
<li>bedrock:InvokeModel is in the policy as the real-deployment shape; NOT enforced</li>
<li>VPC: rules are validated, no actual routing; "model subnet" maps to local Ollama</li>
<li>"On-prem" is a local process; the boundary check is a loopback/private-address check</li>
</ul></div></div>
<h3>Three tough questions</h3>
<div class="q">1. "If it is a simulation, what did you actually demonstrate?"</div>
Design and enforcement logic, not AWS behavior: a role scoped to exact resources, a gate that
refuses to run anything the role or network doesn't allow (shown by denials), and an agent that
runs identically on a managed-style and a boundary-style target. I say plainly it is a simulation
on every artifact; a real deployment changes the control plane, not the agent or the policy shape.
<div class="q">2. "Is the policy really least privilege? What about the exceptions?"</div>
Four statements, each with a written reason, no wildcards, no write or read on logs beyond append,
pull-only on one repo. Honest exceptions: real AWS requires Resource * for GetAuthorizationToken
(I scope it in the sim and say so); InvokeModel is documented but unenforced because the model call
is local Ollama; and a real private subnet needs VPC endpoints for ECR/S3/CloudWatch.
<div class="q">3. "The two models differ. Can you say the smaller model is worse?"</div>
Only for this input and this run: one case, temperature 0, fixed seed. I graded both against a
reference computed from the prompt's own rules, and compare tokens and latency. The Week 8 code
recomputes the sum but does not fix wrong per-factor points, so a wrong factor is a wrong score,
which is why on-prem would add human review near thresholds. It is evidence, not a ranking.
<h3>Recommendation in one breath</h3>
Strict residency: on-prem Ollama, pinned model version, accept lower quality, human review near
thresholds. No residency constraint: AWS with managed model, dedicated role, private subnets plus
endpoints. Same agent code either way; the model sits behind the LLMClient interface.
<h3>Key numbers</h3>
<ul><li>4 IAM statements, 0 wildcards; trust principal ecs-tasks.amazonaws.com only</li>
<li>Network: 1 private app subnet 10.0.1.0/24, 0 ingress, exactly 1 egress tcp/11434 to 10.0.2.0/24;
model SG: ingress only from task SG, no egress</li>
<li>Unit tests: pytest, all green without Ollama (MockTransport and a local API test double)</li></ul>
{measured}
</body></html>"""

p = ROOT / "week9-defense-sheet.html"
p.write_text(HTML)
chrome = shutil.which("google-chrome") or shutil.which("chromium")
subprocess.run([chrome, "--headless", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
                f"--print-to-pdf={ROOT / 'week9-defense-sheet.pdf'}", p.as_uri()],
               check=True, capture_output=True)
p.unlink()
print("wrote week9-defense-sheet.pdf")
