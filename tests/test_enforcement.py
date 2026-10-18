import pytest

from simaws import iam, registry, tasks
from tests.conftest import ROOT


def test_authorize_allows_shipped_setup(account, net):
    denied, passed = tasks.authorize(account, account["task_definitions"]["risk-service"], net)
    assert denied == []
    assert any("ALLOW ecr:BatchGetImage" in p for p in passed)


def test_denied_without_logs_permission(account, net):
    account["roles"]["risk-service-task"]["AttachedPolicies"]["p"]["Statement"].pop(2)
    with pytest.raises(tasks.RunDenied) as e:
        tasks.run_task(account, "risk-service", "x", net, log=lambda m: None)
    assert any("logs:PutLogEvents" in r for r in e.value.reasons)


def test_denied_without_pull_permission(account, net):
    account["roles"]["risk-service-task"]["AttachedPolicies"]["p"]["Statement"].pop(1)
    with pytest.raises(tasks.RunDenied):
        tasks.run_task(account, "risk-service", "x", net, log=lambda m: None)


def test_denied_wrong_resource(account, net):
    account["task_definitions"]["risk-service"]["containerDefinitions"][0]["logGroup"] = "/other"
    denied, _ = tasks.authorize(account, account["task_definitions"]["risk-service"], net)
    assert any("/other" in d for d in denied)


def test_denied_no_explicit_role(account, net):
    account["task_definitions"]["risk-service"]["taskRoleArn"] = None
    denied, _ = tasks.authorize(account, account["task_definitions"]["risk-service"], net)
    assert denied


def test_denied_unknown_digest_and_tag_reference(account, net):
    td = account["task_definitions"]["risk-service"]
    td["containerDefinitions"][0]["image"] = "risk-service@sha256:" + "0" * 64
    assert any("not found" in d for d in tasks.authorize(account, td, net)[0])
    td["containerDefinitions"][0]["image"] = "risk-service:latest"
    assert any("digest" in d for d in tasks.authorize(account, td, net)[0])


def test_denied_public_subnet_and_public_ip(account, net):
    net["subnets"][0]["public"] = True
    td = account["task_definitions"]["risk-service"]
    assert any("network" in d for d in tasks.authorize(account, td, net)[0])
    net["subnets"][0]["public"] = False
    td["networkConfiguration"]["assignPublicIp"] = "ENABLED"
    assert tasks.authorize(account, td, net)[0]


def test_denied_wrong_egress_port(account, net):
    td = account["task_definitions"]["risk-service"]
    td["containerDefinitions"][0]["environment"]["MODEL_ENDPOINT"] = "http://127.0.0.1:443"
    assert any("egress" in d for d in tasks.authorize(account, td, net)[0])


def test_registry_digest_is_deterministic_and_verified(account):
    inc = ["src/underwriting", "src/riskservice", "Dockerfile"]
    a, b = registry.build_archive(ROOT, inc), registry.build_archive(ROOT, inc)
    assert a == b and registry.digest(a) == registry.digest(b)
    d = next(iter(account["repos"]["risk-service"]["images"]))
    path = ROOT / ".simaws" / "test-blobs" / d.replace(":", "-")
    path.write_bytes(a + b"tamper")
    try:
        with pytest.raises(ValueError):
            registry.pull(account, "risk-service", d)
    finally:
        path.write_bytes(a)


def test_is_allowed_exact_match(account):
    role = account["roles"]["risk-service-task"]
    assert iam.is_allowed(role, "logs:PutLogEvents", tasks.log_group_arn("/simaws/risk-service"))
    assert not iam.is_allowed(role, "logs:DeleteLogGroup", tasks.log_group_arn("/simaws/risk-service"))


def test_run_task_end_to_end_with_fake_ollama(account, net, fake_ollama):
    """Runs the image contents in a subprocess against a test double of Ollama's API."""
    td = account["task_definitions"]["risk-service"]
    # the double listens on a random port, so bypass only the port check for this test
    td["containerDefinitions"][0]["environment"]["MODEL_ENDPOINT"] = fake_ollama
    td["containerDefinitions"][0]["environment"]["MODEL_ID"] = "fake:1b"
    net["model_port"] = int(fake_ollama.rsplit(":", 1)[1])
    net["security_groups"][0]["egress"][0]["port"] = net["model_port"]
    net["security_groups"][1]["ingress"][0]["port"] = net["model_port"]
    out = tasks.run_task(account, "risk-service", str(ROOT / "deploy/input/test_input.json"),
                         net, log=lambda m: None)
    assert out["exit_code"] == 0, out["stderr"]
    import json
    body = json.loads(out["stdout"])
    assert body["result"]["score"] == 30 and body["usage"]["input_tokens"] == 11
    assert account["logs"]["/simaws/risk-service"]
