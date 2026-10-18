#!/usr/bin/env python3
"""Run the SAME risk service against a local Ollama inside the (simulated) on-prem boundary."""

import argparse
import ipaddress
import os
import socket
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from riskservice.cli import main as service_main  # noqa: E402
from simaws.deploy import ROOT, phase, print_agent_hashes, require, say, sha256_file  # noqa: E402
from underwriting.llm import OllamaClient  # noqa: E402


def _addresses(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        return [ipaddress.ip_address(host)]
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return []
    found = []
    for *_, sockaddr in infos:
        addr = sockaddr[0].split("%", 1)[0]
        found.append(ipaddress.ip_address(addr))
    return found


def _inside_boundary(host: str) -> bool:
    if host == "localhost":
        return True
    ips = _addresses(host)
    return bool(ips) and all(ip.is_private or ip.is_loopback for ip in ips)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--onprem-model", required=True, help="model id from `ollama list` (the smaller)")
    ap.add_argument("--endpoint", default="http://127.0.0.1:11434")
    ap.add_argument("--input", default=str(ROOT / "deploy/input/test_input.json"))
    ap.add_argument("--out", default=str(ROOT / "evidence/onprem_result.json"))
    a = ap.parse_args()
    say("SIMULATED ON-PREM: a local process plays 'our own data center'. The model runs on a "
        "local Ollama server; nothing leaves this machine.")
    say(f"on-prem-model={a.onprem_model} endpoint={a.endpoint}")
    say(f"input: {a.input}\ninput sha256: {sha256_file(Path(a.input))}")

    phase(1, "boundary check (air-gap posture)")
    host = urlparse(a.endpoint).hostname or ""
    require(_inside_boundary(host),
            f"endpoint host {host} is not loopback/private; refusing to leave the boundary")
    say(f"  endpoint host {host} is loopback/private: model calls stay inside the boundary")
    proxies = [k for k in os.environ if k.lower() in ("http_proxy", "https_proxy", "all_proxy")]
    say(f"  proxy variables set: {proxies or 'none'}")

    phase(2, "Ollama preflight")
    client = OllamaClient(model=a.onprem_model, host=a.endpoint)
    client.preflight()
    say(f"  model {a.onprem_model} is installed at {a.endpoint}")
    say(f"  warm-up (model load): {client.warm_up():.2f} s")
    client.close()

    phase(3, "same agent code as the AWS target (byte-identical)")
    print_agent_hashes()

    phase(4, "run the risk service on the test input")
    return service_main(["--input", a.input, "--endpoint", a.endpoint, "--model", a.onprem_model,
                         "--target", "onprem-sim", "--out", a.out])


if __name__ == "__main__":
    raise SystemExit(main())
