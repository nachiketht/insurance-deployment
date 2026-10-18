#!/usr/bin/env python3
"""Deploy the risk service to the SIMULATED AWS account (simaws). Phases mirror the lab brief."""

import argparse
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from simaws import ACCOUNT, REGION, iam, network, registry, tasks  # noqa: E402
from simaws.deploy import (ROOT, SIM_BANNER, load_json, phase, print_agent_hashes,  # noqa: E402
                           require, say, sha256_file)
from simaws.store import Store  # noqa: E402

ROLE, POLICY, REPO, LOG_GROUP = "risk-service-task", "risk-service-least-privilege", \
    "risk-service", "/simaws/risk-service"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cloud-model", required=True, help="model id from `ollama list` (the larger)")
    ap.add_argument("--endpoint", default="http://127.0.0.1:11434")
    ap.add_argument("--state", default=str(ROOT / ".simaws/state.json"))
    ap.add_argument("--input", default=str(ROOT / "deploy/input/test_input.json"))
    ap.add_argument("--out", default=str(ROOT / "evidence/aws_result.json"))
    a = ap.parse_args()
    sp = Path(a.state)
    if sp.exists():
        sp.unlink()
    store = Store(sp)
    state = store.load()
    state["_blob_dir"] = str(sp.parent / "blobs")
    net = load_json(ROOT / "deploy/network.json")

    say(SIM_BANNER)
    say(f"account={ACCOUNT} region={REGION} cloud-model={a.cloud_model} endpoint={a.endpoint}")
    say(f"input: {a.input}\ninput sha256: {sha256_file(Path(a.input))}")

    phase(1, "validate network placement (before anything is deployed)")
    errs = network.validate(net, "subnet-app-private", "sg-risk-task")
    for s in net["subnets"]:
        say(f"  subnet {s['id']} {s['cidr']} public={s['public']} - {s['purpose']}")
    for g in net["security_groups"]:
        say(f"  {g['id']} ingress={json.dumps(g['ingress'])} egress={json.dumps(g['egress'])}")
    require(not errs, "network validation failed: " + "; ".join(errs))
    say("  network validator: PASS (private subnet, zero ingress, one egress tcp/11434 to model subnet)")

    phase(2, "IAM: create dedicated role, lint policy, attach, confirm")
    arn = iam.create_role(state, ROLE, load_json(ROOT / "deploy/trust-policy.json"))
    say(f"  created role {arn} (trust: ecs-tasks.amazonaws.com only)")
    policy = load_json(ROOT / "deploy/iam-policy.json")
    bad = copy.deepcopy(policy)
    bad["Statement"][1]["Action"] = ["ecr:*"]
    bad["Statement"][2].pop("justification")
    try:
        iam.put_role_policy(state, ROLE, "bad", bad)
    except iam.PolicyError as e:
        say(f"  linter correctly REJECTED a wildcard/unjustified variant:\n{e}")
    iam.put_role_policy(state, ROLE, POLICY, policy)
    say(f"  linter PASS; attached policy {POLICY} to {ROLE}")
    for st in state["roles"][ROLE]["AttachedPolicies"][POLICY]["Statement"]:
        say(f"    {st['Sid']}: {st['Action']} on {st['Resource']}")
    store.save(state)

    phase(3, "registry: create repository, build image archive, push")
    say("  docker not used: deterministic source archive with the same sha256 digest discipline")
    print_agent_hashes()
    registry.create_repo(state, REPO)
    blob = registry.build_archive(ROOT, ["src/underwriting", "src/riskservice", "Dockerfile"])
    blob2 = registry.build_archive(ROOT, ["src/underwriting", "src/riskservice", "Dockerfile"])
    require(blob == blob2, "archive build is not deterministic")
    digest = registry.push(state, REPO, blob, "week9")
    say(f"  pushed {registry.repo_arn(REPO)}:week9  size={len(blob)} bytes")
    say(f"  image digest {digest} (rebuild is byte-identical)")

    phase(4, "ECS: register task definition (role assigned explicitly), run task")
    td = {
        "family": "risk-service",
        "taskRoleArn": arn, "executionRoleArn": arn,
        "networkMode": "awsvpc", "cpu": "512", "memory": "1024",
        "containerDefinitions": [{
            "name": "risk-service",
            "image": f"{REPO}@{digest}",
            "logGroup": LOG_GROUP,
            "environment": {"MODEL_ENDPOINT": a.endpoint, "MODEL_ID": a.cloud_model,
                            "TARGET": "aws-sim"},
        }],
        "networkConfiguration": {"subnet": "subnet-app-private", "securityGroup": "sg-risk-task",
                                 "assignPublicIp": "DISABLED"},
    }
    td_arn = tasks.register_task_definition(state, td)
    say(f"  registered {td_arn}\n  taskRoleArn={arn}")
    say("  NOT enforced by simaws (real-deployment shape only): bedrock:InvokeModel")
    store.save(state)

    say("\n  -- run-task: negative checks first (each must be denied before anything runs) --")
    cases = {
        "policy missing logs permission": lambda s, t, n: s["roles"][ROLE]["AttachedPolicies"][
            POLICY]["Statement"].pop(2),
        "public subnet placement": lambda s, t, n: n["subnets"][0].update(public=True),
        "second egress rule": lambda s, t, n: n["security_groups"][0]["egress"].append(
            {"protocol": "tcp", "port": 443, "cidr": "0.0.0.0/0"}),
        "image referenced by tag": lambda s, t, n: t["containerDefinitions"][0].update(
            image=REPO + ":week9"),
        "wrong egress port": lambda s, t, n: t["containerDefinitions"][0]["environment"].update(
            MODEL_ENDPOINT="http://127.0.0.1:443"),
    }
    for name, mutate in cases.items():
        s2, n2 = copy.deepcopy(state), copy.deepcopy(net)
        mutate(s2, s2["task_definitions"]["risk-service"], n2)
        try:
            tasks.run_task(s2, "risk-service", a.input, n2, log=lambda m: None)
            say(f"  DENIAL TEST FAILED: {name} was allowed")
            return 1
        except tasks.RunDenied as e:
            say(f"  denied [{name}]: {e.reasons[0]}")

    say("\n  -- run-task: the real task --")
    out = tasks.run_task(state, "risk-service", a.input, net, log=say)
    store.save(state)
    phase(5, f"task log from {LOG_GROUP} (exit code {out['exit_code']})")
    say(out["stdout"].rstrip())
    if out["stderr"].strip():
        say("stderr:\n" + out["stderr"].rstrip())
    if out["exit_code"] != 0:
        return out["exit_code"]
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(out["stdout"])
    say(f"\nresult saved to {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
