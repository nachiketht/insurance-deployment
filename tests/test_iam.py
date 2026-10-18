import copy

import pytest

from simaws import iam


def test_shipped_policy_passes_linter(policy):
    assert iam.lint_policy(policy) == []


def test_every_statement_has_justification(policy):
    assert all(len(s["justification"]) >= 30 for s in policy["Statement"])


@pytest.mark.parametrize("mutate,needle", [
    (lambda p: p["Statement"][1].update(Action=["ecr:*"]), "wildcard action"),
    (lambda p: p["Statement"][1].update(Action=["*"]), "wildcard action"),
    (lambda p: p["Statement"][1].update(Resource=["*"]), "wildcard resource"),
    (lambda p: p["Statement"][1].pop("justification"), "justification"),
    (lambda p: p["Statement"][1].update(justification="because"), "justification"),
    (lambda p: p["Statement"][1].update(Effect="Deny"), "Effect must be Allow"),
    (lambda p: p["Statement"][1].pop("Sid"), "missing Sid"),
    (lambda p: p["Statement"][1].update(Resource=["arn:aws:s3:::b"]), "not an arn:simaws"),
])
def test_linter_rejects(policy, mutate, needle):
    bad = copy.deepcopy(policy)
    mutate(bad)
    assert any(needle in e for e in iam.lint_policy(bad))


def test_put_role_policy_refuses_bad_policy(policy):
    state = {"roles": {}}
    iam.create_role(state, "r", {"Statement": [{"Effect": "Allow", "Action": "sts:AssumeRole",
                                                "Principal": {"Service": iam.ECS_PRINCIPAL}}]})
    policy["Statement"][0]["Action"] = ["ecr:*"]
    with pytest.raises(iam.PolicyError):
        iam.put_role_policy(state, "r", "p", policy)
    assert state["roles"]["r"]["AttachedPolicies"] == {}


def test_trust_policy_must_be_ecs_tasks():
    with pytest.raises(iam.PolicyError):
        iam.create_role({"roles": {}}, "r", {"Statement": [
            {"Effect": "Allow", "Action": "sts:AssumeRole",
             "Principal": {"Service": "ec2.amazonaws.com"}}]})
