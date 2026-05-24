"""
Tests for app/services/resource_scanner.py

Strategy
--------
moto's `mock_aws` intercepts every boto3 call to AWS, so the scanner builds
real boto3 clients and `healthcheck()` runs against a faked EC2 — no real AWS,
no credentials needed. We assert:
  - empty credentials are rejected at construction (no API call needed)
  - both clients build under the mock
  - healthcheck() returns {"ok": True, ...} when EC2 is reachable
  - healthcheck() reports {"ok": False, ...} (never raises) on access denied
"""

from datetime import datetime, timedelta, timezone

import boto3
import pytest
from moto import mock_aws
from moto.core import DEFAULT_ACCOUNT_ID
from moto.ec2 import ec2_backends

from app.services.resource_scanner import ResourceScanner

REGION = "us-east-1"

# moto accepts any non-empty credentials — these are throwaway test values.
CREDS = {
    "aws_access_key_id": "testing",
    "aws_secret_access_key": "testing",
    "region": REGION,
}


# ── Shared seeding helper for the waste-detection tests ────────────────────────

def _ec2_client():
    return boto3.client(
        "ec2",
        region_name=REGION,
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
    )


def _seed_wasteful_resources(ec2) -> dict:
    """Create exactly one of each wasteful resource type; return their ids.

    Note: moto's default AMIs ship with ~560 self-owned snapshots, but every one
    is dated 'now', so the 90-day age filter excludes them — only the backdated
    snapshot below is old enough to be flagged.
    """
    # 1. Unattached EBS volume (status 'available').
    unattached_vol = ec2.create_volume(AvailabilityZone=f"{REGION}a", Size=8)["VolumeId"]

    # 2. Unassociated Elastic IP (no AssociationId).
    eip_alloc = ec2.allocate_address(Domain="vpc")["AllocationId"]

    # 3. Stopped instance with an extra attached EBS volume.
    ami = ec2.describe_images()["Images"][0]["ImageId"]
    instance_id = ec2.run_instances(
        ImageId=ami, MinCount=1, MaxCount=1
    )["Instances"][0]["InstanceId"]
    attached_vol = ec2.create_volume(AvailabilityZone=f"{REGION}a", Size=20)["VolumeId"]
    ec2.attach_volume(VolumeId=attached_vol, InstanceId=instance_id, Device="/dev/sdf")
    ec2.stop_instances(InstanceIds=[instance_id])

    # 4. Old snapshot — create_snapshot always stamps StartTime=now, so backdate
    #    it in moto's backend to push it past the 90-day threshold.
    snap_id = ec2.create_snapshot(VolumeId=unattached_vol)["SnapshotId"]
    backend = ec2_backends[DEFAULT_ACCOUNT_ID][REGION]
    backend.snapshots[snap_id].start_time = (
        datetime.now(timezone.utc) - timedelta(days=200)
    ).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    return {
        "volume": unattached_vol,
        "eip": eip_alloc,
        "instance": instance_id,
        "snapshot": snap_id,
        "attached_vol": attached_vol,
    }


STANDARD_SHAPE = {"resource_type", "resource_id", "region", "reason", "raw"}


def _cpu_series(avg_value: float, days: int = 14) -> dict:
    """A fake GetMetricStatistics response: `days` daily averages all at avg_value."""
    base = datetime(2026, 5, 1, tzinfo=timezone.utc)
    return {
        "Datapoints": [
            {"Timestamp": base + timedelta(days=i), "Average": avg_value, "Unit": "Percent"}
            for i in range(days)
        ]
    }


def _run_instance(ec2) -> str:
    """Launch one running instance and return its id."""
    ami = ec2.describe_images()["Images"][0]["ImageId"]
    return ec2.run_instances(ImageId=ami, MinCount=1, MaxCount=1)["Instances"][0]["InstanceId"]


# ── Credential validation (sync, no API call) ─────────────────────────────────

def test_missing_access_key_raises_value_error():
    with pytest.raises(ValueError, match="missing"):
        ResourceScanner(aws_access_key_id="", aws_secret_access_key="secret")


def test_missing_secret_key_raises_value_error():
    with pytest.raises(ValueError, match="missing"):
        ResourceScanner(aws_access_key_id="AKIA...", aws_secret_access_key="")


def test_missing_region_raises_value_error():
    with pytest.raises(ValueError, match="region"):
        ResourceScanner(
            aws_access_key_id="AKIA...", aws_secret_access_key="secret", region=""
        )


# ── Clients build ──────────────────────────────────────────────────────────────

@mock_aws
def test_scanner_builds_ec2_and_cloudwatch_clients():
    scanner = ResourceScanner(**CREDS)

    assert scanner._ec2 is not None
    assert scanner._cloudwatch is not None
    # boto3 clients expose their service name via meta — confirms the right ones.
    assert scanner._ec2.meta.service_model.service_name == "ec2"
    assert scanner._cloudwatch.meta.service_model.service_name == "cloudwatch"


@mock_aws
def test_cloudwatch_client_makes_basic_call():
    """No scanner method uses CloudWatch yet, so verify the built client is
    actually functional with a cheap call. Empty account → empty metric list."""
    scanner = ResourceScanner(**CREDS)

    resp = scanner._cloudwatch.list_metrics()

    assert "Metrics" in resp
    assert isinstance(resp["Metrics"], list)


# ── healthcheck happy path ─────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_healthcheck_returns_ok():
    with mock_aws():
        scanner = ResourceScanner(**CREDS)
        result = await scanner.healthcheck()

    assert result["ok"] is True
    assert isinstance(result["detail"], str)
    assert "us-east-1" in result["detail"]


# ── healthcheck reports failure instead of raising ─────────────────────────────

@pytest.mark.anyio
async def test_healthcheck_reports_access_denied_without_raising():
    """
    When describe_regions raises an authorization error, healthcheck must return
    {"ok": False, ...} — never propagate the exception (the Settings page relies
    on a clean status object).
    """
    from unittest.mock import MagicMock
    from botocore.exceptions import ClientError

    with mock_aws():
        scanner = ResourceScanner(**CREDS)

    scanner._ec2 = MagicMock()
    scanner._ec2.describe_regions.side_effect = ClientError(
        {"Error": {"Code": "UnauthorizedOperation", "Message": "not authorized"}},
        "DescribeRegions",
    )

    result = await scanner.healthcheck()

    assert result["ok"] is False
    assert "Access denied" in result["detail"]


@pytest.mark.anyio
async def test_healthcheck_swallows_unexpected_errors():
    """A non-AWS error (bug, unexpected type) must still produce a clean
    {"ok": False} — healthcheck backs a UI status indicator and may never raise."""
    from unittest.mock import MagicMock

    with mock_aws():
        scanner = ResourceScanner(**CREDS)

    scanner._ec2 = MagicMock()
    scanner._ec2.describe_regions.side_effect = RuntimeError("something unexpected")

    result = await scanner.healthcheck()

    assert result["ok"] is False
    assert "Unexpected error" in result["detail"]


# ── Waste-detection finders ────────────────────────────────────────────────────
# Each test seeds ALL four wasteful resource types, then asserts the finder under
# test returns exactly its own target — proving it doesn't pick up the others.

@pytest.mark.anyio
async def test_find_unattached_ebs_volumes():
    with mock_aws():
        ids = _seed_wasteful_resources(_ec2_client())
        scanner = ResourceScanner(**CREDS)
        findings = await scanner.find_unattached_ebs_volumes()

    assert len(findings) == 1
    f = findings[0]
    assert f["resource_id"] == ids["volume"]
    assert f["resource_type"] == "ebs_volume"
    assert f["region"] == REGION
    assert set(f) == STANDARD_SHAPE


@pytest.mark.anyio
async def test_find_unassociated_elastic_ips():
    with mock_aws():
        ids = _seed_wasteful_resources(_ec2_client())
        scanner = ResourceScanner(**CREDS)
        findings = await scanner.find_unassociated_elastic_ips()

    assert len(findings) == 1
    f = findings[0]
    assert f["resource_id"] == ids["eip"]
    assert f["resource_type"] == "elastic_ip"
    assert set(f) == STANDARD_SHAPE


@pytest.mark.anyio
async def test_find_stopped_instances_includes_attached_volumes():
    with mock_aws():
        ids = _seed_wasteful_resources(_ec2_client())
        scanner = ResourceScanner(**CREDS)
        findings = await scanner.find_stopped_instances()

    assert len(findings) == 1
    f = findings[0]
    assert f["resource_id"] == ids["instance"]
    assert f["resource_type"] == "ec2_instance"
    assert set(f) == STANDARD_SHAPE

    # The attached volume id and its size must be surfaced in raw for step 5.3.
    attached = f["raw"]["attached_volumes"]
    assert ids["attached_vol"] in [v["volume_id"] for v in attached]
    assert any(v["size_gib"] == 20 for v in attached)


@pytest.mark.anyio
async def test_find_old_snapshots():
    with mock_aws():
        ids = _seed_wasteful_resources(_ec2_client())
        scanner = ResourceScanner(**CREDS)
        findings = await scanner.find_old_snapshots(days=90)

    # moto's ~560 default AMI snapshots are dated today, so only the backdated
    # one clears the 90-day threshold.
    assert len(findings) == 1
    f = findings[0]
    assert f["resource_id"] == ids["snapshot"]
    assert f["resource_type"] == "ebs_snapshot"
    assert set(f) == STANDARD_SHAPE


@pytest.mark.anyio
async def test_scan_all_returns_one_of_each_tagged():
    with mock_aws():
        ids = _seed_wasteful_resources(_ec2_client())
        scanner = ResourceScanner(**CREDS)
        findings = await scanner.scan_all()

    assert len(findings) == 4

    by_check = {f["check"]: f for f in findings}
    assert set(by_check) == {
        "unattached_ebs_volumes",
        "unassociated_elastic_ips",
        "stopped_instances",
        "old_snapshots",
    }
    assert by_check["unattached_ebs_volumes"]["resource_id"] == ids["volume"]
    assert by_check["unassociated_elastic_ips"]["resource_id"] == ids["eip"]
    assert by_check["stopped_instances"]["resource_id"] == ids["instance"]
    assert by_check["old_snapshots"]["resource_id"] == ids["snapshot"]

    # Tagged findings keep the standard shape plus the `check` key.
    for f in findings:
        assert STANDARD_SHAPE <= set(f)
        assert "check" in f


@pytest.mark.anyio
async def test_finders_return_empty_on_clean_account():
    """A tidy account (no created resources) must yield no findings — guards
    against false positives. moto's default AMI snapshots are recent, so the
    90-day filter excludes them too."""
    with mock_aws():
        scanner = ResourceScanner(**CREDS)
        assert await scanner.find_unattached_ebs_volumes() == []
        assert await scanner.find_unassociated_elastic_ips() == []
        assert await scanner.find_stopped_instances() == []
        assert await scanner.find_old_snapshots() == []
        assert await scanner.scan_all() == []


@pytest.mark.anyio
async def test_scan_all_resilient_to_one_failing_check(monkeypatch):
    """If one check raises (e.g. partial permissions), scan_all logs and skips it
    and still returns the other checks' findings — never an all-or-nothing 500."""
    with mock_aws():
        ids = _seed_wasteful_resources(_ec2_client())
        scanner = ResourceScanner(**CREDS)

        async def _boom():
            raise PermissionError("describe_addresses denied")

        monkeypatch.setattr(scanner, "find_unassociated_elastic_ips", _boom)

        findings = await scanner.scan_all()

    checks = {f["check"] for f in findings}
    assert "unassociated_elastic_ips" not in checks  # the failing check is skipped
    assert checks == {"unattached_ebs_volumes", "stopped_instances", "old_snapshots"}
    # the surviving checks still found their targets
    ids_found = {f["resource_id"] for f in findings}
    assert {ids["volume"], ids["instance"], ids["snapshot"]} <= ids_found


# ── Idle running instances (CloudWatch metrics) ────────────────────────────────
# We patch the scanner's cloudwatch client method directly instead of relying on
# moto: moto's GetMetricStatistics doesn't synthesize realistic CPU datapoints, so
# a moto-backed test couldn't distinguish an idle instance from a busy one.

@pytest.mark.anyio
async def test_find_idle_running_instances_flags_low_cpu_only(monkeypatch):
    with mock_aws():
        ec2 = _ec2_client()
        idle_id = _run_instance(ec2)
        busy_id = _run_instance(ec2)

        scanner = ResourceScanner(**CREDS)

        def fake_get_metric_statistics(**kwargs):
            instance_id = kwargs["Dimensions"][0]["Value"]
            return _cpu_series(1.5 if instance_id == idle_id else 65.0)

        monkeypatch.setattr(
            scanner._cloudwatch, "get_metric_statistics", fake_get_metric_statistics
        )

        findings = await scanner.find_idle_running_instances()

    ids = {f["resource_id"] for f in findings}
    assert idle_id in ids        # low-CPU instance flagged
    assert busy_id not in ids    # busy instance not flagged

    f = next(f for f in findings if f["resource_id"] == idle_id)
    assert f["resource_type"] == "ec2_instance_idle"
    assert set(f) == STANDARD_SHAPE
    assert "1.5%" in f["reason"]  # observed average CPU appears in the reason


@pytest.mark.anyio
async def test_find_idle_running_instances_skips_no_data(monkeypatch):
    """An instance with no CloudWatch datapoints must NOT be flagged — never flag
    on absence of evidence."""
    with mock_aws():
        ec2 = _ec2_client()
        _run_instance(ec2)

        scanner = ResourceScanner(**CREDS)
        monkeypatch.setattr(
            scanner._cloudwatch,
            "get_metric_statistics",
            lambda **kwargs: {"Datapoints": []},
        )

        findings = await scanner.find_idle_running_instances()

    assert findings == []
