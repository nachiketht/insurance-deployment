"""Network placement validator for the VPC description in deploy/network.json."""

import ipaddress

WORLD = {"0.0.0.0/0", "::/0"}


def validate(net: dict, app_subnet: str, app_sg: str) -> list[str]:
    errs: list[str] = []
    subnets = {s["id"]: s for s in net["subnets"]}
    sgs = {g["id"]: g for g in net["security_groups"]}
    if app_subnet not in subnets or app_sg not in sgs:
        return [f"unknown subnet or security group ({app_subnet}, {app_sg})"]
    sub, sg = subnets[app_subnet], sgs[app_sg]
    if sub.get("public") or sub.get("internet_gateway_route") or sub.get("nat_route"):
        errs.append(f"subnet {app_subnet} is public or has an internet/NAT route")
    for rule in sg["ingress"]:
        errs.append(f"{app_sg} has an ingress rule {rule}: the task needs no inbound traffic")
    for rule in sg["ingress"] + sg["egress"]:
        if rule.get("cidr") in WORLD:
            errs.append(f"{app_sg} has a world-open rule {rule}")
    egress = sg["egress"]
    if len(egress) != 1:
        errs.append(f"{app_sg} must have exactly one egress rule, has {len(egress)}")
    else:
        r = egress[0]
        model_sub = subnets.get(net["model_subnet"])
        ok_dest = False
        if model_sub and r.get("cidr"):
            ok_dest = ipaddress.ip_network(r["cidr"]) == ipaddress.ip_network(model_sub["cidr"])
        if r.get("protocol") != "tcp" or r.get("port") != net["model_port"] or not ok_dest:
            errs.append(f"egress rule {r} must be tcp/{net['model_port']} to the model subnet only")
    model_sg = sgs.get(net["model_sg"])
    if model_sg:
        for r in model_sg["ingress"]:
            if r.get("source_sg") != app_sg or r.get("port") != net["model_port"]:
                errs.append(f"model SG ingress {r} must be tcp/{net['model_port']} from {app_sg}")
        if model_sg["egress"]:
            errs.append("model SG must have no egress (air-gapped model host)")
    if subnets[net["model_subnet"]].get("public"):
        errs.append("model subnet must be private")
    return errs
