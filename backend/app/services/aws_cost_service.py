import asyncio
import boto3
from botocore.exceptions import ClientError
from datetime import date, datetime, timedelta
from typing import NoReturn


class AwsCostService:
    """
    Wraps AWS Cost Explorer into a reusable service class.

    Why a class instead of standalone functions?
      - Credentials are injected once in __init__ and reused for every call.
      - The boto3 client is created once, not on every request.
      - FastAPI's dependency injection can hand this class to any route that needs it.

    Why async methods?
      - FastAPI is async. If we call boto3 (which is synchronous) directly inside
        an async route, it blocks the event loop and slows down every other request.
      - asyncio.to_thread() runs the boto3 call in a separate thread, so the
        event loop stays free to handle other requests while we wait for AWS.
    """

    def __init__(
        self,
        aws_access_key_id: str,
        aws_secret_access_key: str,
    ):
        if not aws_access_key_id or not aws_secret_access_key:
            raise ValueError(
                "AWS credentials are missing.\n"
                "Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in your .env file."
            )

        # boto3 client is created once here and reused for every method call.
        # Cost Explorer only works in us-east-1 regardless of your account's region.
        self._client = boto3.client(
            "ce",
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name="us-east-1",
        )

    # ── Public async API ──────────────────────────────────────────────────────

    async def get_daily_costs(self, days: int = 30) -> list[dict]:
        """
        Fetch daily AWS costs for the last N days, broken down by service.

        Returns a list of dicts, one per (day, service) pair:
            [
                {"date": "2026-05-08", "cost": 18.50, "service": "Amazon EC2"},
                {"date": "2026-05-08", "cost":  4.25, "service": "Amazon S3"},
                ...
            ]

        Zero-cost entries are excluded.
        """
        # asyncio.to_thread runs _fetch_daily_costs in a background thread.
        # This prevents the synchronous boto3 call from blocking the event loop.
        return await asyncio.to_thread(self._fetch_daily_costs, days)

    async def get_cost_by_service(
        self, start_date: date, end_date: date
    ) -> list[dict]:
        """
        Fetch total cost per service for an explicit date range.

        Aggregates across all days in the range and returns one entry per service,
        sorted by cost descending (most expensive first):
            [
                {"service": "Amazon EC2", "cost": 450.00},
                {"service": "Amazon S3", "cost":  38.50},
                ...
            ]

        Useful for pie charts and service-breakdown views on the dashboard.
        """
        return await asyncio.to_thread(self._fetch_cost_by_service, start_date, end_date)

    # ── Private sync methods (run inside threads) ─────────────────────────────

    def _fetch_daily_costs(self, days: int) -> list[dict]:
        """Synchronous boto3 call — only call this via asyncio.to_thread."""
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)

        response = self._call_cost_explorer(
            start=start_date.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d"),
            granularity="DAILY",
        )
        return self._parse_response(response)

    def _fetch_cost_by_service(self, start_date: date, end_date: date) -> list[dict]:
        """Synchronous boto3 call — only call this via asyncio.to_thread."""
        response = self._call_cost_explorer(
            start=start_date.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d"),
            granularity="MONTHLY",
        )

        # Aggregate costs across all months in the range, grouped by service.
        totals: dict[str, float] = {}
        for period in response["ResultsByTime"]:
            for group in period["Groups"]:
                service = group["Keys"][0]
                amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
                if amount > 0.0:
                    totals[service] = totals.get(service, 0.0) + amount

        # Sort most expensive first — matches what a dashboard pie chart expects.
        return [
            {"service": svc, "cost": round(cost, 2)}
            for svc, cost in sorted(totals.items(), key=lambda x: x[1], reverse=True)
        ]

    # ── Shared helpers ────────────────────────────────────────────────────────

    def _call_cost_explorer(
        self, start: str, end: str, granularity: str
    ) -> dict:
        """
        Calls GetCostAndUsage and handles AWS errors with clear messages.
        Used by both _fetch_daily_costs and _fetch_cost_by_service.
        """
        try:
            return self._client.get_cost_and_usage(
                TimePeriod={"Start": start, "End": end},
                Granularity=granularity,
                # UnblendedCost = what you actually pay (not averaged across accounts)
                Metrics=["UnblendedCost"],
                GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
            )
        except ClientError as e:
            self._raise_friendly_error(e)

    @staticmethod
    def _parse_response(response: dict) -> list[dict]:
        """
        Flattens the AWS response into a simple list of dicts.

        Raw AWS shape:
            {"ResultsByTime": [{"TimePeriod": {"Start": "..."}, "Groups": [...]}]}

        Output shape:
            [{"date": "2026-05-08", "cost": 18.50, "service": "Amazon EC2"}, ...]
        """
        results = []
        for day_entry in response["ResultsByTime"]:
            date_str = day_entry["TimePeriod"]["Start"]
            for group in day_entry["Groups"]:
                service_name = group["Keys"][0]
                cost_amount = float(group["Metrics"]["UnblendedCost"]["Amount"])

                # Skip exact zero — means the service had no activity that day.
                # Keep sub-cent charges because they are real charges.
                if cost_amount == 0.0:
                    continue

                results.append({
                    "date": date_str,
                    "cost": round(cost_amount, 2),
                    "service": service_name,
                })
        return results

    @staticmethod
    def _raise_friendly_error(e: ClientError) -> NoReturn:
        """Converts AWS error codes into human-readable Python exceptions."""
        code = e.response["Error"]["Code"]
        msg = e.response["Error"]["Message"]

        if code == "AccessDeniedException":
            raise PermissionError(
                "Your AWS credentials don't have permission to use Cost Explorer.\n"
                "Fix: IAM → your user → Attach policies → 'AWSBillingReadOnlyAccess'.\n"
                f"AWS said: {msg}"
            )
        if code == "InvalidClientTokenId":
            raise ValueError(
                "Your AWS_ACCESS_KEY_ID is invalid or has been deleted.\n"
                "Check the value in your .env file."
            )
        if code == "SignatureDoesNotMatch":
            raise ValueError(
                "Your AWS_SECRET_ACCESS_KEY is wrong.\n"
                "It must match the access key exactly."
            )
        if code == "OptInRequired":
            raise PermissionError(
                "Cost Explorer is not enabled on this AWS account.\n"
                "Fix: AWS Console → Billing → Cost Explorer → Enable it (free, takes ~24h)."
            )
        raise RuntimeError(f"Unexpected AWS error [{code}]: {msg}")
