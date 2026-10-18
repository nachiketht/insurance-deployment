"""Simulated IAM: roles, a least-privilege policy linter, and policy evaluation."""

from simaws import ACCOUNT

ECS_PRINCIPAL = "ecs-tasks.amazonaws.com"
MIN_JUSTIFICATION = 30


class PolicyError(Exception):
    pass


def role_arn(name: str) -> str:
    return f"arn:simaws:iam::{ACCOUNT}:role/{name}"


def lint_policy(doc: dict) -> list[str]:
    """Return a list of least-privilege violations. Empty list means the policy passes."""
    errors: list[str] = []
    statements = doc.get("Statement")
    if not isinstance(statements, list) or not statements:
        return ["policy has no statements"]
    sids: set[str] = set()
    for i, st in enumerate(statements):
        sid = st.get("Sid") or ""
        where = f"statement[{i}] ({sid or 'no Sid'})"
        if not sid:
            errors.append(f"{where}: missing Sid")
        elif sid in sids:
            errors.append(f"{where}: duplicate Sid")
        sids.add(sid)
        if st.get("Effect") != "Allow":
            errors.append(f"{where}: Effect must be Allow (least privilege is an allow-list)")
        for key in ("NotAction", "NotResource", "Principal"):
            if key in st:
                errors.append(f"{where}: {key} is not allowed in a role policy")
        actions = _as_list(st.get("Action"))
        resources = _as_list(st.get("Resource"))
        if not actions:
            errors.append(f"{where}: no Action")
        if not resources:
            errors.append(f"{where}: no Resource")
        for a in actions:
            if "*" in a:
                errors.append(f"{where}: wildcard action {a!r}")
        for r in resources:
            if "*" in r:
                errors.append(f"{where}: wildcard resource {r!r}")
            elif not r.startswith("arn:simaws:"):
                errors.append(f"{where}: resource {r!r} is not an arn:simaws: ARN")
        just = (st.get("justification") or "").strip()
        if len(just) < MIN_JUSTIFICATION:
            errors.append(
                f"{where}: justification missing or shorter than {MIN_JUSTIFICATION} characters"
            )
    return errors


def _as_list(v) -> list[str]:
    if v is None:
        return []
    return [v] if isinstance(v, str) else list(v)


def check_trust_policy(doc: dict) -> None:
    for st in doc.get("Statement", []):
        principal = st.get("Principal", {}).get("Service")
        if st.get("Effect") != "Allow" or st.get("Action") != "sts:AssumeRole":
            raise PolicyError("trust policy must Allow sts:AssumeRole only")
        if principal != ECS_PRINCIPAL:
            raise PolicyError(f"trust principal must be exactly {ECS_PRINCIPAL}, got {principal!r}")
    if not doc.get("Statement"):
        raise PolicyError("trust policy has no statements")


def create_role(state: dict, name: str, trust: dict) -> str:
    check_trust_policy(trust)
    if name in state["roles"]:
        raise PolicyError(f"role {name} already exists")
    state["roles"][name] = {"RoleName": name, "Arn": role_arn(name),
                            "AssumeRolePolicyDocument": trust, "AttachedPolicies": {}}
    return role_arn(name)


def put_role_policy(state: dict, name: str, policy_name: str, doc: dict) -> None:
    errors = lint_policy(doc)
    if errors:
        raise PolicyError("policy rejected by least-privilege linter:\n  - " + "\n  - ".join(errors))
    state["roles"][name]["AttachedPolicies"][policy_name] = doc


def is_allowed(role: dict, action: str, resource: str) -> bool:
    """Exact-match evaluation. The linter forbids wildcards, so exact match is complete."""
    for doc in role["AttachedPolicies"].values():
        for st in doc["Statement"]:
            if st["Effect"] == "Allow" and action in _as_list(st["Action"]) \
                    and resource in _as_list(st["Resource"]):
                return True
    return False
