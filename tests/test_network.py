import copy

from simaws import network


def v(net):
    return network.validate(net, "subnet-app-private", "sg-risk-task")


def test_shipped_network_passes(net):
    assert v(net) == []


def test_rejects_public_subnet(net):
    net["subnets"][0]["public"] = True
    assert any("public" in e for e in v(net))


def test_rejects_nat_route(net):
    net["subnets"][0]["nat_route"] = True
    assert v(net)


def test_rejects_any_ingress(net):
    net["security_groups"][0]["ingress"].append({"protocol": "tcp", "port": 80, "cidr": "10.0.0.0/8"})
    assert any("ingress" in e for e in v(net))


def test_rejects_world_open(net):
    net["security_groups"][0]["ingress"].append({"protocol": "tcp", "port": 22, "cidr": "0.0.0.0/0"})
    assert any("world-open" in e for e in v(net))


def test_rejects_second_egress(net):
    net["security_groups"][0]["egress"].append({"protocol": "tcp", "port": 443, "cidr": "10.0.2.0/24"})
    assert any("exactly one egress" in e for e in v(net))


def test_rejects_wrong_port_or_dest(net):
    a = copy.deepcopy(net)
    a["security_groups"][0]["egress"][0]["port"] = 8080
    b = copy.deepcopy(net)
    b["security_groups"][0]["egress"][0]["cidr"] = "10.0.1.0/24"
    assert v(a) and v(b)


def test_model_sg_has_no_egress(net):
    net["security_groups"][1]["egress"].append({"protocol": "tcp", "port": 443, "cidr": "10.0.0.0/8"})
    assert any("no egress" in e for e in v(net))
