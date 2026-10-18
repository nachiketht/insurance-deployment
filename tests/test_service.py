import json

import httpx
import pytest

from riskservice.cli import main
from riskservice.service import file_sha256, run_risk_service
from simaws.reference import reference_factors, reference_score
from underwriting.errors import LLMTimeoutError, LLMTransientError, ModelNotFoundError
from underwriting.llm import OllamaClient


def client_for(handler, model="m:1"):
    return OllamaClient(model=model, host="http://ollama.test",
                        http=httpx.Client(transport=httpx.MockTransport(handler)))


def chat_ok(content):
    def h(req):
        if req.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "m:1"}]})
        return httpx.Response(200, json={"model": "m:1", "message": {"content": json.dumps(content)},
                                         "prompt_eval_count": 100, "eval_count": 40,
                                         "done_reason": "stop"})
    return h


def test_service_sums_points_in_code_and_reports_usage(test_input):
    c = client_for(chat_ok({"factors": [
        {"name": "prior_claims", "points": 30, "detail": "a"},
        {"name": "credit", "points": 25, "detail": "b"},
        {"name": "bogus", "points": 40, "detail": "dropped"}], "score": 1, "rationale": "r"}))
    out = run_risk_service(test_input, c)
    assert out["result"]["score"] == 55  # model said 1; code recomputes, unknown factor dropped
    assert [f["name"] for f in out["result"]["factors"]] == ["prior_claims", "credit"]
    assert out["usage"]["input_tokens"] == 100 and out["usage"]["output_tokens"] == 40
    assert out["usage"]["model_calls"] == 1 and out["usage"]["duration_ms"] >= 0


def test_service_repair_call_counts_tokens(test_input):
    calls = []

    def h(req):
        calls.append(1)
        bad = {"factors": [{"name": "credit", "points": 99, "detail": "x"}], "score": 0,
               "rationale": "r"}
        good = {"factors": [], "score": 0, "rationale": "r"}
        return httpx.Response(200, json={"model": "m:1", "done_reason": "stop",
                                         "message": {"content": json.dumps(bad if len(calls) == 1
                                                                           else good)},
                                         "prompt_eval_count": 10, "eval_count": 5})
    out = run_risk_service(test_input, client_for(h))
    assert out["usage"]["model_calls"] == 2 and out["usage"]["input_tokens"] == 20


def test_ollama_request_shape():
    seen = {}

    def h(req):
        seen.update(json.loads(req.content))
        return httpx.Response(200, json={"message": {"content": "{}"}, "done_reason": "stop"})
    client_for(h).complete(agent="a", system="s", user="u",
                           schema=__import__("underwriting.models", fromlist=["RiskResult"]).RiskResult,
                           max_tokens=7)
    assert seen["model"] == "m:1" and seen["think"] is False and seen["stream"] is False
    assert seen["options"]["temperature"] == 0 and seen["options"]["num_predict"] == 7
    assert "properties" in seen["format"]


@pytest.mark.parametrize("exc,err", [(httpx.ReadTimeout("t"), LLMTimeoutError),
                                     (httpx.ConnectError("c"), LLMTransientError)])
def test_ollama_error_mapping(exc, err):
    def h(req):
        raise exc
    with pytest.raises(err):
        client_for(h).warm_up()


def test_ollama_404_is_model_not_found_and_preflight_missing():
    with pytest.raises(ModelNotFoundError):
        client_for(lambda r: httpx.Response(404, text="nope")).warm_up()
    c = client_for(lambda r: httpx.Response(200, json={"models": [{"name": "other:1"}]}))
    with pytest.raises(ModelNotFoundError):
        c.preflight()


def test_cli_requires_model_and_endpoint(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("MODEL_ID", raising=False)
    monkeypatch.delenv("MODEL_ENDPOINT", raising=False)
    assert main(["--input", "deploy/input/test_input.json"]) == 2
    assert "ollama list" in capsys.readouterr().err


def test_cli_end_to_end_with_fake_ollama(fake_ollama, tmp_path, capsys):
    out = tmp_path / "o.json"
    rc = main(["--input", "deploy/input/test_input.json", "--endpoint", fake_ollama,
               "--model", "fake:1b", "--target", "t", "--out", str(out)])
    assert rc == 0
    body = json.loads(out.read_text())
    assert body["input_sha256"] == file_sha256("deploy/input/test_input.json")
    assert body["usage"]["output_tokens"] == 7


def test_reference_score_for_frozen_input(test_input):
    assert reference_factors(test_input) == {"prior_claims": 30, "credit": 25,
                                             "coverage_income": 20, "asset_age": 15}
    assert reference_score(test_input) == 90


def test_agent_files_are_byte_identical_to_week8():
    import hashlib
    import pathlib
    src = pathlib.Path("/workspace/insurance-orchestrator/src/underwriting")
    if not src.exists():
        pytest.skip("Week 8 checkout not present")
    for rel in ["agents/risk.py", "agents/_base.py", "llm.py", "models.py", "errors.py"]:
        a = hashlib.sha256((src / rel).read_bytes()).hexdigest()
        b = hashlib.sha256(pathlib.Path("src/underwriting", rel).read_bytes()).hexdigest()
        assert a == b, rel
