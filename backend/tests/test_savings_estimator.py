"""
Tests for app/services/savings_estimator.py

Pure, offline math — no AWS, no moto. Each test feeds a finding with known
sizes and asserts the exact dollar figure (derived from the PRICING table, so
the tests stay correct if the rates are tuned) and a non-empty basis string.
"""

from app.services.savings_estimator import PRICING, estimate_monthly_savings


def _finding(resource_type: str, raw: dict) -> dict:
    """Build a finding in the standard ResourceScanner shape."""
    return {
        "resource_type": resource_type,
        "resource_id": "test-id",
        "region": "us-east-1",
        "reason": "test fixture",
        "raw": raw,
    }


def test_unattached_ebs_volume_priced_by_size():
    result = estimate_monthly_savings(_finding("ebs_volume", {"Size": 100}))

    assert result["estimated_monthly_usd"] == round(100 * PRICING["ebs_gb_month"], 2)
    assert result["basis"]


def test_elastic_ip_is_flat_rate():
    result = estimate_monthly_savings(_finding("elastic_ip", {"PublicIp": "1.2.3.4"}))

    assert result["estimated_monthly_usd"] == round(PRICING["elastic_ip_month"], 2)
    assert result["basis"]


def test_stopped_instance_prices_ebs_only():
    """Stopped instance = sum of attached EBS sizes × EBS rate, NO compute."""
    result = estimate_monthly_savings(_finding("ec2_instance", {
        "attached_volumes": [
            {"volume_id": "vol-1", "size_gib": 30},
            {"volume_id": "vol-2", "size_gib": 20},
        ],
    }))

    assert result["estimated_monthly_usd"] == round(50 * PRICING["ebs_gb_month"], 2)
    # The basis must explain why there's no compute charge — the defensible bit.
    assert "compute" in result["basis"].lower()


def test_old_snapshot_priced_by_volume_size():
    result = estimate_monthly_savings(_finding("ebs_snapshot", {"VolumeSize": 40}))

    assert result["estimated_monthly_usd"] == round(40 * PRICING["snapshot_gb_month"], 2)
    assert result["basis"]


def test_unknown_type_returns_zero_with_explanation():
    result = estimate_monthly_savings(_finding("mystery_resource", {}))

    assert result["estimated_monthly_usd"] == 0.0
    assert result["basis"]


def test_missing_size_does_not_crash():
    """A finding whose raw lacks a size should estimate $0, not raise."""
    result = estimate_monthly_savings(_finding("ebs_volume", {}))

    assert result["estimated_monthly_usd"] == 0.0
    assert result["basis"]
