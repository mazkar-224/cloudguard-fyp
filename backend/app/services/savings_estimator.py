"""
Offline savings estimator.

Turns a waste finding (the {resource_type, resource_id, region, reason, raw}
shape produced by ResourceScanner) into an APPROXIMATE monthly dollar figure.

Deliberately offline: there is no call to the AWS Pricing API. We use a small
hard-coded table of rough rates instead. Every figure is an estimate, and the
returned `basis` string spells out the math so the UI can show its work — fake
precision helps no one, an honest estimate builds trust.
"""

# ── APPROXIMATE pricing ────────────────────────────────────────────────────────
# WARNING: these are ROUGH, region-agnostic estimates (roughly us-east-1) that
# change over time. They are intentionally simple and offline. Before relying on
# any number here, verify against current AWS pricing:
#   EBS / snapshots: https://aws.amazon.com/ebs/pricing/
#   Elastic IPs:     https://aws.amazon.com/vpc/pricing/
# To update, just change a value below — nothing else depends on the exact rate.
PRICING = {
    "ebs_gb_month": 0.08,       # EBS gp3 storage, USD per GB-month (approx)
    "elastic_ip_month": 3.60,   # idle Elastic IP, ~$0.005/hr × 730 hrs (approx)
    "snapshot_gb_month": 0.05,  # EBS snapshot storage, USD per GB-month (approx)
}


def estimate_monthly_savings(finding: dict) -> dict:
    """
    Estimate the monthly USD saved by cleaning up one finding.

    Returns {"estimated_monthly_usd": float, "basis": str} where `basis` is a
    short human-readable explanation of the calculation, e.g.
    "30 GB × $0.08/GB-month (approx)".
    """
    resource_type = finding["resource_type"]
    raw = finding.get("raw", {})

    if resource_type == "ebs_volume":
        size_gb = raw.get("Size", 0) or 0
        rate = PRICING["ebs_gb_month"]
        usd = size_gb * rate
        basis = f"{size_gb} GB × ${rate:.2f}/GB-month (approx)"

    elif resource_type == "elastic_ip":
        usd = PRICING["elastic_ip_month"]
        basis = f"1 idle Elastic IP × ${usd:.2f}/month (approx)"

    elif resource_type == "ec2_instance":
        # A stopped instance is NOT billed for compute — only its attached EBS
        # volumes keep costing money. So we price the storage and nothing else.
        sizes = [v.get("size_gib") or 0 for v in raw.get("attached_volumes", [])]
        total_gb = sum(sizes)
        rate = PRICING["ebs_gb_month"]
        usd = total_gb * rate
        basis = (
            f"{total_gb} GB attached EBS × ${rate:.2f}/GB-month (approx); "
            "no compute charge — instance is stopped"
        )

    elif resource_type == "ebs_snapshot":
        size_gb = raw.get("VolumeSize", 0) or 0
        rate = PRICING["snapshot_gb_month"]
        usd = size_gb * rate
        basis = f"{size_gb} GB × ${rate:.2f}/GB-month (approx)"

    else:
        return {
            "estimated_monthly_usd": 0.0,
            "basis": f"no estimate available for resource type '{resource_type}'",
        }

    return {"estimated_monthly_usd": round(usd, 2), "basis": basis}
