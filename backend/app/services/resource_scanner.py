import asyncio
import logging
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)


class ResourceScanner:
    """
    Wraps AWS EC2 + CloudWatch into a reusable service class — the resource-layer
    sibling of AwsCostService.

    Where AwsCostService talks to Cost Explorer (what you were billed), this
    service talks to the resources themselves: EC2 for instances/volumes and
    CloudWatch for the metrics that reveal whether those resources are actually
    being used. Later phases use it to flag idle/underused resources.

    Same conventions as AwsCostService:
      - Credentials are injected once in __init__; the boto3 clients are built
        once here and reused for every call.
      - Every public method is async. The blocking boto3 call is run inside
        asyncio.to_thread() so it never blocks the FastAPI event loop.

    IAM permissions required:
      - ec2:Describe*                   (describe_regions, describe_instances, ...)
      - cloudwatch:GetMetricStatistics
    Both are included in the AWS-managed `ReadOnlyAccess` policy, so a user that
    already has that policy needs nothing extra.
    """

    def __init__(
        self,
        aws_access_key_id: str,
        aws_secret_access_key: str,
        region: str = "us-east-1",
    ):
        if not aws_access_key_id or not aws_secret_access_key:
            raise ValueError(
                "AWS credentials are missing.\n"
                "Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in your .env file."
            )
        if not region:
            raise ValueError(
                "AWS region is missing.\n"
                "Set AWS_REGION in your .env file (e.g. 'us-east-1')."
            )

        self._region = region

        # Both clients are created once and reused. Unlike Cost Explorer (which
        # is us-east-1 only), EC2 and CloudWatch are regional, so they honor the
        # configured region.
        self._ec2 = boto3.client(
            "ec2",
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=region,
        )
        self._cloudwatch = boto3.client(
            "cloudwatch",
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=region,
        )

    # ── Public async API ──────────────────────────────────────────────────────

    async def healthcheck(self) -> dict:
        """
        Confirm the credentials work and the EC2 read permissions are present,
        using one cheap call (describe_regions).

        Returns a dict instead of raising — its whole job is to *report* status,
        so the Settings page can show a green/red indicator without a try/except:
            {"ok": True,  "detail": "EC2 reachable in us-east-1 — permissions OK"}
            {"ok": False, "detail": "Access denied — IAM user is missing ec2:Describe*"}
        """
        return await asyncio.to_thread(self._healthcheck)

    # ── Waste-detection finders (metadata-only, no CloudWatch) ─────────────────
    #
    # Every finder returns a list of findings sharing one shape:
    #     {resource_type, resource_id, region, reason, raw}
    # The consistent shape lets later steps (savings estimate, persistence)
    # handle one structure instead of four.

    async def find_unattached_ebs_volumes(self) -> list[dict]:
        """EBS volumes in the 'available' state — attached to nothing, but still
        billed for storage every month."""
        return await asyncio.to_thread(self._find_unattached_ebs_volumes)

    async def find_unassociated_elastic_ips(self) -> list[dict]:
        """Elastic IPs with no AssociationId — AWS bills idle (unassociated) EIPs."""
        return await asyncio.to_thread(self._find_unassociated_elastic_ips)

    async def find_stopped_instances(self) -> list[dict]:
        """Stopped EC2 instances. No compute charge while stopped, but their
        attached EBS volumes keep billing — easy to forget."""
        return await asyncio.to_thread(self._find_stopped_instances)

    async def find_old_snapshots(self, days: int = 90) -> list[dict]:
        """Self-owned EBS snapshots older than *days* that may no longer be needed."""
        return await asyncio.to_thread(self._find_old_snapshots, days)

    async def find_idle_running_instances(
        self, days: int = 14, cpu_threshold: float = 5.0
    ) -> list[dict]:
        """Running EC2 instances whose average CPU stayed below *cpu_threshold*
        percent over the last *days* — likely idle, paying for unused compute.

        Unlike the metadata checks, this reads CloudWatch CPUUtilization
        time-series. Instances with no datapoints (brand new, or without the
        CloudWatch agent) are skipped — we never flag on absence of evidence.
        """
        return await asyncio.to_thread(
            self._find_idle_running_instances, days, cpu_threshold
        )

    async def scan_all(self) -> list[dict]:
        """Run all five checks concurrently and merge their findings — the four
        metadata checks plus the CloudWatch-based idle-instance check.

        Each finding is tagged with the `check` that produced it, so callers can
        group/report by check without re-deriving it from resource_type.

        Resilient by design: if one check fails (e.g. a partial-permission user
        can read EBS but not Elastic IPs), it's logged and skipped rather than
        failing the whole scan — the other checks still return their findings.
        """
        checks = (
            ("unattached_ebs_volumes", self.find_unattached_ebs_volumes),
            ("unassociated_elastic_ips", self.find_unassociated_elastic_ips),
            ("stopped_instances", self.find_stopped_instances),
            ("old_snapshots", self.find_old_snapshots),
            ("idle_running_instances", self.find_idle_running_instances),
        )
        results = await asyncio.gather(
            *(check() for _, check in checks),
            return_exceptions=True,
        )

        combined: list[dict] = []
        for (name, _), result in zip(checks, results):
            if isinstance(result, Exception):
                logger.warning("resource_scanner: check '%s' failed — %s", name, result)
                continue
            for finding in result:
                combined.append({"check": name, **finding})
        return combined

    # ── Private sync methods (run inside threads) ─────────────────────────────

    def _healthcheck(self) -> dict:
        """Synchronous health probe — only call this via asyncio.to_thread."""
        try:
            self._ec2.describe_regions()
            return {
                "ok": True,
                "detail": f"EC2 reachable in {self._region} — credentials and "
                          f"ec2:DescribeRegions permission OK",
            }
        except ClientError as e:
            detail = self._explain_client_error(e)
        except BotoCoreError as e:
            # Network/endpoint problems (no internet, bad region, etc.).
            detail = f"Could not reach AWS: {e}"
        except Exception as e:  # noqa: BLE001
            # This backs a Settings-page status indicator, so it must never
            # raise — any unforeseen error becomes a failed (not broken) check.
            detail = f"Unexpected error during healthcheck: {e}"

        logger.warning("resource_scanner: healthcheck failed — %s", detail)
        return {"ok": False, "detail": detail}

    def _find_unattached_ebs_volumes(self) -> list[dict]:
        """Sync — only call via asyncio.to_thread."""
        findings = []
        # Paginate: an account can have more volumes than fit in one API page.
        paginator = self._ec2.get_paginator("describe_volumes")
        for page in paginator.paginate(
            Filters=[{"Name": "status", "Values": ["available"]}]
        ):
            for vol in page.get("Volumes", []):
                size = vol.get("Size")
                findings.append(self._finding(
                    resource_type="ebs_volume",
                    resource_id=vol["VolumeId"],
                    reason=(
                        f"Unattached EBS volume ({size} GiB) in 'available' state — "
                        "billed for storage while attached to nothing"
                    ),
                    raw=vol,
                ))
        return findings

    def _find_unassociated_elastic_ips(self) -> list[dict]:
        """Sync — only call via asyncio.to_thread."""
        # describe_addresses is not a paginated API (no NextToken / paginator) —
        # AWS caps Elastic IPs per region low enough to return in one response.
        resp = self._ec2.describe_addresses()
        findings = []
        for addr in resp.get("Addresses", []):
            # An EIP attached to a running instance has an AssociationId; absence
            # of one means it's idle and therefore billed.
            if addr.get("AssociationId"):
                continue
            public_ip = addr.get("PublicIp", "?")
            # AllocationId is the stable identifier (VPC EIPs); fall back to the
            # public IP for the rare classic-EIP case where it's absent.
            resource_id = addr.get("AllocationId") or addr.get("PublicIp")
            findings.append(self._finding(
                resource_type="elastic_ip",
                resource_id=resource_id,
                reason=(
                    f"Elastic IP {public_ip} is not associated with any instance "
                    "— AWS bills idle Elastic IPs"
                ),
                raw=addr,
            ))
        return findings

    def _find_stopped_instances(self) -> list[dict]:
        """Sync — only call via asyncio.to_thread."""
        instances = []
        volume_ids = []
        inst_paginator = self._ec2.get_paginator("describe_instances")
        for page in inst_paginator.paginate(
            Filters=[{"Name": "instance-state-name", "Values": ["stopped"]}]
        ):
            for reservation in page.get("Reservations", []):
                for inst in reservation.get("Instances", []):
                    instances.append(inst)
                    for bdm in inst.get("BlockDeviceMappings", []):
                        ebs = bdm.get("Ebs")
                        if ebs and ebs.get("VolumeId"):
                            volume_ids.append(ebs["VolumeId"])

        # Map every attached volume id → size in one paginated pass, instead of a
        # describe call per instance.
        sizes: dict[str, int] = {}
        if volume_ids:
            vol_paginator = self._ec2.get_paginator("describe_volumes")
            for page in vol_paginator.paginate(VolumeIds=volume_ids):
                for v in page.get("Volumes", []):
                    sizes[v["VolumeId"]] = v.get("Size")

        findings = []
        for inst in instances:
            attached = []
            for bdm in inst.get("BlockDeviceMappings", []):
                ebs = bdm.get("Ebs")
                if ebs and ebs.get("VolumeId"):
                    vid = ebs["VolumeId"]
                    attached.append({"volume_id": vid, "size_gib": sizes.get(vid)})
            total_gib = sum(a["size_gib"] for a in attached if a["size_gib"])

            # Surface the attached-volume detail in raw so the savings step (5.3)
            # can price the still-billing storage without re-querying.
            raw = {**inst, "attached_volumes": attached}
            findings.append(self._finding(
                resource_type="ec2_instance",
                resource_id=inst["InstanceId"],
                reason=(
                    f"Stopped EC2 instance with {len(attached)} attached EBS "
                    f"volume(s) totaling {total_gib} GiB — volumes keep billing "
                    "while the instance is stopped"
                ),
                raw=raw,
            ))
        return findings

    def _find_old_snapshots(self, days: int) -> list[dict]:
        """Sync — only call via asyncio.to_thread."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        findings = []
        # Paginate: a long-lived account accumulates many snapshots. OwnerIds=['self']
        # excludes the thousands of public/AWS-owned ones.
        paginator = self._ec2.get_paginator("describe_snapshots")
        for page in paginator.paginate(OwnerIds=["self"]):
            for snap in page.get("Snapshots", []):
                start = snap.get("StartTime")  # boto3 returns a tz-aware datetime
                if start is None or start >= cutoff:
                    continue
                age_days = (datetime.now(timezone.utc) - start).days
                findings.append(self._finding(
                    resource_type="ebs_snapshot",
                    resource_id=snap["SnapshotId"],
                    reason=(
                        f"EBS snapshot is {age_days} days old (older than {days}d) "
                        "— may no longer be needed"
                    ),
                    raw=snap,
                ))
        return findings

    def _find_idle_running_instances(self, days: int, cpu_threshold: float) -> list[dict]:
        """Sync — only call via asyncio.to_thread."""
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)

        findings = []
        paginator = self._ec2.get_paginator("describe_instances")
        for page in paginator.paginate(
            Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
        ):
            for reservation in page.get("Reservations", []):
                for inst in reservation.get("Instances", []):
                    instance_id = inst["InstanceId"]
                    resp = self._cloudwatch.get_metric_statistics(
                        Namespace="AWS/EC2",
                        MetricName="CPUUtilization",
                        Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
                        StartTime=start,
                        EndTime=end,
                        Period=86400,  # one day in seconds → one datapoint per day
                        Statistics=["Average"],
                    )
                    datapoints = resp.get("Datapoints", [])

                    # No metrics = no evidence. Skip — flagging on the absence of
                    # data is a classic false-positive bug (a brand-new instance,
                    # or one with no CloudWatch agent, would look "idle").
                    if not datapoints:
                        continue

                    avg_cpu = sum(d["Average"] for d in datapoints) / len(datapoints)
                    if avg_cpu >= cpu_threshold:
                        continue

                    findings.append(self._finding(
                        resource_type="ec2_instance_idle",
                        resource_id=instance_id,
                        reason=(
                            f"Running instance averaged {avg_cpu:.1f}% CPU over the "
                            f"last {days} days (idle threshold {cpu_threshold}%) — "
                            "likely paying for unused compute"
                        ),
                        raw={
                            **inst,
                            "avg_cpu_percent": round(avg_cpu, 1),
                            "cpu_datapoint_count": len(datapoints),
                        },
                    ))
        return findings

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _finding(self, resource_type: str, resource_id: str, reason: str, raw: dict) -> dict:
        """Build a finding in the standard shape shared by every check."""
        return {
            "resource_type": resource_type,
            "resource_id": resource_id,
            "region": self._region,
            "reason": reason,
            "raw": raw,
        }

    @staticmethod
    def _explain_client_error(e: ClientError) -> str:
        """Turn an AWS error code into a human-readable healthcheck detail."""
        code = e.response["Error"]["Code"]
        msg = e.response["Error"]["Message"]

        # EC2 reports authorization failures as UnauthorizedOperation; other
        # services use AccessDenied(Exception). Cover all three.
        if code in ("UnauthorizedOperation", "AccessDenied", "AccessDeniedException"):
            return (
                "Access denied — your IAM user is missing ec2:Describe* "
                "permissions. Attach the AWS-managed 'ReadOnlyAccess' policy. "
                f"AWS said: {msg}"
            )
        if code in ("AuthFailure", "InvalidClientTokenId"):
            return (
                "AWS credentials are invalid or expired. Check "
                "AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY in your .env file. "
                f"AWS said: {msg}"
            )
        if code == "SignatureDoesNotMatch":
            return (
                "AWS_SECRET_ACCESS_KEY does not match the access key. "
                f"AWS said: {msg}"
            )
        return f"Unexpected AWS error [{code}]: {msg}"
