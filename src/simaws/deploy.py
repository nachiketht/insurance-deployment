"""Shared helpers for the deploy scripts."""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SIM_BANNER = ("SIMULATION: simaws is a local stand-in for AWS. No cloud API is called. "
              "The model runs on a local Ollama server.")
AGENT_FILES = ["src/underwriting/agents/risk.py", "src/underwriting/agents/_base.py",
               "src/underwriting/llm.py", "src/underwriting/models.py"]


def say(msg: str = "") -> None:
    print(msg, flush=True)


def phase(n: int, title: str) -> None:
    say(f"\n=== Phase {n}: {title} ===")


def sha256_file(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def print_agent_hashes() -> None:
    for f in AGENT_FILES:
        say(f"  sha256 {sha256_file(ROOT / f)}  {f}")


def load_json(p: Path) -> dict:
    return json.loads(Path(p).read_text())


def require(cond: bool, msg: str) -> None:
    if not cond:
        say(f"FATAL: {msg}")
        sys.exit(2)
