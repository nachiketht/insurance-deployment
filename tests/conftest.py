import copy
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(rel):
    return json.loads((ROOT / rel).read_text())


@pytest.fixture
def net():
    return load("deploy/network.json")


@pytest.fixture
def policy():
    return load("deploy/iam-policy.json")


@pytest.fixture
def test_input():
    return load("deploy/input/test_input.json")


@pytest.fixture
def account(policy):
    """A simulated account with the role, policy, repo and image in place."""
    from simaws import iam, registry, tasks

    state = {"roles": {}, "repos": {}, "task_definitions": {}, "logs": {}, "audit": [],
             "_blob_dir": str(ROOT / ".simaws" / "test-blobs")}
    arn = iam.create_role(state, "risk-service-task", load("deploy/trust-policy.json"))
    iam.put_role_policy(state, "risk-service-task", "p", policy)
    registry.create_repo(state, "risk-service")
    blob = registry.build_archive(ROOT, ["src/underwriting", "src/riskservice", "Dockerfile"])
    d = registry.push(state, "risk-service", blob, "t")
    td = {"family": "risk-service", "taskRoleArn": arn,
          "containerDefinitions": [{"name": "x", "image": f"risk-service@{d}",
                                    "logGroup": "/simaws/risk-service",
                                    "environment": {"MODEL_ENDPOINT": "http://127.0.0.1:11434",
                                                    "MODEL_ID": "m", "TARGET": "t"}}],
          "networkConfiguration": {"subnet": "subnet-app-private", "securityGroup": "sg-risk-task",
                                   "assignPublicIp": "DISABLED"}}
    tasks.register_task_definition(state, td)
    return copy.deepcopy(state)


class FakeOllama(BaseHTTPRequestHandler):
    """Test double speaking just enough of Ollama's API. Used only by unit tests."""

    reply = {"factors": [{"name": "prior_claims", "points": 30, "detail": "d"}],
             "score": 0, "rationale": "r"}

    def log_message(self, *a):
        pass

    def _send(self, obj):
        b = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        self._send({"models": [{"name": "fake:1b"}]})

    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        self._send({"model": "fake:1b", "message": {"content": json.dumps(self.reply)},
                    "prompt_eval_count": 11, "eval_count": 7, "done_reason": "stop"})


@pytest.fixture
def fake_ollama():
    srv = HTTPServer(("127.0.0.1", 0), FakeOllama)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()
