# Deployment, networking and access control: risk scoring agent

HONEST SIMULATION STATEMENT. No cloud service is used or called anywhere in this project.
The "AWS" target is `simaws`, a local control plane written for this lab (IAM, registry, task
definitions, run-task, network validator, JSON state). The "on-prem" target is a local process
talking to a local Ollama server. Both targets run the same unchanged Week 8 agent
(`src/underwriting/agents/risk.py`) on the same frozen input, and every transcript in
`evidence/` was produced by running the scripts in this repo. The exact model ids used are
recorded in `evidence/ollama_setup.txt` and in each result's `usage.model`.

## 1. The agent

The Week 8 risk scoring agent takes the intake and enrichment results, asks a model to assign
factor points from fixed rules, and then CODE (not the model) drops unknown or duplicate factor
names and recomputes the score as the sum, capped at 100. That validation is ported unchanged;
the unit tests assert the files are byte-identical to the Week 8 commit 924d9c2.
`riskservice` wraps it (`run_risk_service`) and returns the result plus usage (tokens, calls,
milliseconds). The same wrapper is the container entrypoint and the on-prem entrypoint.

## 2. IAM: one dedicated role, least privilege

Role `risk-service-task`, trust policy: `ecs-tasks.amazonaws.com` may assume it, nothing else.
It is created BEFORE anything is deployed, the policy is linted and attached, and the run-task
verb refuses to start a task whose definition does not name this role explicitly.

| Permission | Resource | Why it is necessary | Why nothing broader |
|---|---|---|---|
| ecr:GetAuthorizationToken | the one registry | image pull must authenticate | real AWS only accepts `*` here; simaws scopes it, a real deployment would carry this single documented exception |
| ecr:BatchGetImage, ecr:GetDownloadUrlForLayer | repository/risk-service | read-only pull of the service's own image | no push, no other repository: a compromised task cannot tamper with or read other images |
| logs:CreateLogStream, logs:PutLogEvents | log-group /simaws/risk-service | append-only audit output | no read or delete: the workload cannot erase its trail |
| bedrock:InvokeModel | one named model | real-deployment shape for the managed model call | NOT enforced by the simulator (the model call goes to local Ollama); documented so the real policy is not forgotten |

The linter (`simaws.iam.lint_policy`) rejects: wildcard actions, wildcard resources, non-Allow
effects, NotAction/NotResource/Principal, missing or duplicate Sid, resources that are not
arn:simaws ARNs, and any statement whose `justification` is missing or under 30 characters. The
deploy transcript shows a deliberately bad variant being rejected.

Enforcement is real inside the simulator: `run_task` checks, before executing anything, that the
role exists with a valid trust policy and an attached policy, the image is referenced by sha256
digest and exists in the repository, each needed action is allowed on its exact resource, the
network placement is valid, and the model endpoint port matches the single egress rule. Denial
tests (unit tests and the deploy transcript) cover: missing logs permission, missing pull
permission, wrong resource, no explicit role, unknown digest, tag reference, public subnet,
public IP, second/world-open egress, wrong port.

## 3. Networking

| Item | Setting | Reason |
|---|---|---|
| App subnet 10.0.1.0/24 | private, no internet gateway route, no NAT route | the task is never called from outside; it only makes one outbound call |
| Task security group | ingress: none. egress: exactly one rule, tcp/11434 to 10.0.2.0/24 | zero attack surface inbound; a compromised task can reach the model and nothing else (no exfiltration path) |
| Model subnet 10.0.2.0/24 | private, no routes out | the model host holds prompts containing applicant data |
| Model security group | ingress tcp/11434 from the task SG only; no egress | only the service may call the model; the model host cannot phone home |
| assignPublicIp | DISABLED | belt and braces with the private subnet |

Consequence worth stating in the defense: with no NAT route, a real Fargate task could not reach
ECR or CloudWatch over the internet. A real deployment would add VPC interface/gateway endpoints
for ECR, S3 (layers) and CloudWatch Logs inside the private subnet. The simulator models the
placement rules, not that routing.

## 4. Deployment flow (scripts/deploy_aws_sim.py)

1. Validate the network. 2. Create the role, lint the policy, attach, print it. 3. Create the
repository, build the image, push, record the digest. 4. Register the task definition with the
role set explicitly, run the negative checks, run the task. 5. Print the task log.
`docker` is not used; simaws pushes a deterministic source archive (sorted entries, zeroed
timestamps and ownership) with the same digest discipline as an image. A `Dockerfile` shows the
real-deployment shape but was not built. The task executes the contents of the pulled archive in
a subprocess, so what runs is what was pushed, verified by digest on pull.

## 5. What changes for on-prem (scripts/deploy_onprem.py)

| Concern | AWS shape | On-prem / air-gapped |
|---|---|---|
| Model | managed endpoint, vendor operates it | Ollama on our hardware, open weights we choose |
| Identity | IAM role per workload | local service account / OS and network policy; IAM concepts become firewall rules and file permissions |
| Image/packages | pulled from ECR | everything pre-staged: images, Python packages, model weights |
| Egress | allowed to the model endpoint | none beyond the model host; boundary check refuses non-private endpoints |
| Updates | continuous, vendor-paced | at audit pace: a model or package change is a reviewed, versioned release |
| Observability | CloudWatch | local logs only |

What breaks in an air-gapped environment: anything that assumes the internet. `pip install`,
`ollama pull`, container pulls, telemetry, hosted APIs and license checks all fail, so every
dependency must be mirrored and hash-verified before the boundary is closed, and updates become
a deliberate import process.

Why a client demands it: data residency and sovereignty (applicant data may not leave a
jurisdiction or facility), vendor and third-party risk (no dependence on a provider's
availability, retention or training policies), and model risk management (a pinned, auditable
model version that cannot change silently underneath a regulated decision). Underwriting data is
personal and financial, so these apply directly.

The code change for on-prem is one flag: the same `OllamaClient` is pointed at a loopback or
private endpoint and a different model id. The agent code is byte-identical.
