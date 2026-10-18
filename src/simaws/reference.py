"""Reference score computed straight from the rules written in the Week 8 risk prompt.
Used only to grade model output in the comparison; the agent itself is unchanged."""


def reference_factors(doc: dict) -> dict[str, int]:
    i, e = doc["intake"], doc["enrichment"]
    f: dict[str, int] = {}
    n = e["prior_claims_count"]
    if n >= 3:
        f["prior_claims"] = 30
    elif n >= 1:
        f["prior_claims"] = 15
    band = e["credit_band"]
    if band == "c":
        f["credit"] = 10
    elif band == "d":
        f["credit"] = 25
    if i.get("coverage_amount") and i.get("stated_income") and \
            i["coverage_amount"] > 5 * i["stated_income"]:
        f["coverage_income"] = 20
    if (e.get("asset_age_years") or 0) >= 30:
        f["asset_age"] = 15
    if band == "no_hit" or i.get("missing_fields"):
        f["missing_data"] = 20
    return f


def reference_score(doc: dict) -> int:
    return min(100, sum(reference_factors(doc).values()))
