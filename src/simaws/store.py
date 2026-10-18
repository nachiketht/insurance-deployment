"""JSON state store for the simulated account."""

import json
from pathlib import Path

EMPTY = {"roles": {}, "repos": {}, "task_definitions": {}, "logs": {}, "audit": []}


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> dict:
        if not self.path.exists():
            return json.loads(json.dumps(EMPTY))
        return json.loads(self.path.read_text())

    def save(self, state: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
