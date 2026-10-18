"""Task definitions and run-task. run_task ENFORCES the role before executing anything."""

import json
import os
import subprocess
import sys
import tarfile
import tempfile
from urllib.parse import urlparse

from simaws import ACCOUNT, REGION, iam, network, registry


class RunDenied(Exception):
    def __init__(self, reasons: list[str]):
        super().__init__("; ".join(reasons))
        self.reasons = reasons


def log_group_arn(name: str) -> str:
    return f"arn:simaws:logs:{REGION}:{ACCOUNT}:log-group:{name}"


def register_task_definition(state: dict, td: dict) -> str:
    arn = f"arn:simaws:ecs:{REGION}:{ACCOUNT}:task-definition/{td['family']}:1"
    state["task_definitions"][td["family"]] = {**td, "taskDefinitionArn": arn}
    return arn


def authorize(state: dict, td: dict, net: dict) -> tuple[list[str], list[str]]:
    """Return (denial reasons, allowed checks). Nothing runs unless reasons is empty."""
    denied: list[str] = []
    passed: list[str] = []
    role_name = td["taskRoleArn"].rsplit("/", 1)[-1] if td.get("taskRoleArn") else None
    role = state["roles"].get(role_name or "")
    if not role or role["Arn"] != td.get("taskRoleArn"):
        return ["task definition has no valid explicit taskRoleArn"], passed
    try:
        iam.check_trust_policy(role["AssumeRolePolicyDocument"])
        passed.append("role trust policy allows ecs-tasks.amazonaws.com only")
    except iam.PolicyError as e:
        denied.append(str(e))
    if not role["AttachedPolicies"]:
        denied.append("role has no attached policy")
    c = td["containerDefinitions"][0]
    repo_name, _, image_digest = c["image"].partition("@")
    repo_name = repo_name.rsplit("/", 1)[-1]
    repo = state["repos"].get(repo_name)
    if not image_digest.startswith("sha256:"):
        denied.append("image must be referenced by sha256 digest, not by tag")
    elif not repo or image_digest not in repo["images"]:
        denied.append(f"image {image_digest} not found in repository {repo_name}")
    needed = [
        ("ecr:GetAuthorizationToken", f"arn:simaws:ecr:{REGION}:{ACCOUNT}:registry/default"),
        ("ecr:BatchGetImage", registry.repo_arn(repo_name)),
        ("ecr:GetDownloadUrlForLayer", registry.repo_arn(repo_name)),
        ("logs:CreateLogStream", log_group_arn(c["logGroup"])),
        ("logs:PutLogEvents", log_group_arn(c["logGroup"])),
    ]
    for action, res in needed:
        if iam.is_allowed(role, action, res):
            passed.append(f"ALLOW {action} on {res}")
        else:
            denied.append(f"DENY {action} on {res}: not granted by the attached policy")
    nc = td["networkConfiguration"]
    nerrs = network.validate(net, nc["subnet"], nc["securityGroup"])
    if nc.get("assignPublicIp") != "DISABLED":
        nerrs.append("assignPublicIp must be DISABLED")
    denied += [f"network: {e}" for e in nerrs]
    if not nerrs:
        passed.append(f"network placement ok: {nc['subnet']} / {nc['securityGroup']}")
    port = urlparse(c["environment"].get("MODEL_ENDPOINT", "")).port
    if port != net["model_port"]:
        denied.append(f"egress: endpoint port {port} is not the single allowed tcp/{net['model_port']}")
    else:
        passed.append(f"egress: model endpoint port {port} matches the single allowed rule")
    return denied, passed


def run_task(state: dict, family: str, input_path: str, net: dict, log=print) -> dict:
    td = state["task_definitions"][family]
    denied, passed = authorize(state, td, net)
    for p in passed:
        log(f"  [enforce] {p}")
    if denied:
        for d in denied:
            log(f"  [enforce] {d}")
        raise RunDenied(denied)
    c = td["containerDefinitions"][0]
    repo_name, _, d = c["image"].partition("@")
    blob = registry.pull(state, repo_name.rsplit("/", 1)[-1], d)
    log(f"  [enforce] image digest verified on pull: {d}")
    with tempfile.TemporaryDirectory() as root:
        blob_path = os.path.join(root, "image.tar")
        open(blob_path, "wb").write(blob)
        fs = os.path.join(root, "rootfs")
        with tarfile.open(blob_path) as tar:
            tar.extractall(fs, filter="data")
        env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": os.path.join(fs, "src"),
               "PYTHONDONTWRITEBYTECODE": "1", **c["environment"]}
        proc = subprocess.run(
            [sys.executable, "-m", "riskservice.cli", "--input", input_path],
            env=env, capture_output=True, text=True, cwd=fs)
    state["logs"].setdefault(c["logGroup"], []).append(
        {"taskDefinition": td["taskDefinitionArn"], "exit_code": proc.returncode,
         "stdout": proc.stdout, "stderr": proc.stderr})
    return {"exit_code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}
