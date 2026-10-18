"""python -m simaws iam get-role --name X --state .simaws/state.json"""

import argparse
import json

from simaws.store import Store


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="simaws")
    ap.add_argument("service", choices=["iam"])
    ap.add_argument("verb", choices=["get-role"])
    ap.add_argument("--name", required=True)
    ap.add_argument("--state", default=".simaws/state.json")
    a = ap.parse_args(argv)
    role = Store(a.state).load()["roles"].get(a.name)
    if role is None:
        print(f"NoSuchEntity: role {a.name}")
        return 1
    print(json.dumps({"_simulated": "simaws local IAM, not AWS", "Role": role}, indent=2))
    return 0
