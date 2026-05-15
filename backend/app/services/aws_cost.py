import boto3
from botocore.exceptions import ClientError
from datetime import datetime, timedelta

from app.config import settings


def _create_cost_explorer_client():
    """
    Create a boto3 Cost Explorer client using credentials from our .env file.
    pydantic-settings (in config.py) already loaded the .env file for us,
    so we just read from `settings` — no need to call dotenv manually.

    Cost Explorer is a special AWS service: it ONLY works in us-east-1,
    regardless of where your other AWS resources live.
    """

    # Fail early with a clear message if credentials weren't set in .env
    if not settings.aws_access_key_id or not settings.aws_secret_access_key:
        raise ValueError(
            "AWS credentials are missing.\n"
            "Open your .env file and set:\n"
            "  AWS_ACCESS_KEY_ID=your-key-here\n"
            "  AWS_SECRET_ACCESS_KEY=your-secret-here"
        )

    client = boto3.client(
        "ce",  # "ce" is boto3's identifier for Cost Explorer
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name="us-east-1",  # Cost Explorer only accepts us-east-1
    )
    return client


def get_daily_costs(days: int = 30) -> list[dict]:
    """
    Fetch daily AWS costs for the last N days, broken down by service.

    Returns a flat list of dicts — one entry per (day, service) pair:
        [
            {"date": "2026-04-15", "cost": 12.34, "service": "Amazon EC2"},
            {"date": "2026-04-15", "cost":  0.89, "service": "AWS Lambda"},
            {"date": "2026-04-16", "cost": 13.10, "service": "Amazon EC2"},
            ...
        ]

    Days with zero cost for a service are skipped (to keep data clean).
    Costs are in USD, rounded to 2 decimal places.

    Args:
        days: How many past days to fetch. Default is 30.

    Raises:
        ValueError: If credentials are missing or invalid.
        PermissionError: If the IAM user lacks Cost Explorer access.
        RuntimeError: For unexpected AWS API errors.
    """

    client = _create_cost_explorer_client()

    # Build the date range.
    # Cost Explorer's End date is EXCLUSIVE — meaning "up to but not including".
    # So End=today gives us data through yesterday (which is fine, since
    # today's costs usually aren't available yet anyway — AWS delays by ~24h).
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days)

    try:
        response = client.get_cost_and_usage(
            TimePeriod={
                "Start": start_date.strftime("%Y-%m-%d"),
                "End": end_date.strftime("%Y-%m-%d"),
            },
            # DAILY gives one row per day. Other options: MONTHLY, HOURLY.
            Granularity="DAILY",
            # UnblendedCost = what you actually pay (not averaged across accounts).
            # This is the most straightforward metric for single-account setups.
            Metrics=["UnblendedCost"],
            # Group results by AWS service (EC2, S3, Lambda, etc.)
            GroupBy=[
                {
                    "Type": "DIMENSION",
                    "Key": "SERVICE",
                }
            ],
        )

    except ClientError as e:
        # ClientError is boto3's way of wrapping HTTP errors from AWS.
        # We inspect the error code to give the user a useful message.
        error_code = e.response["Error"]["Code"]
        error_message = e.response["Error"]["Message"]

        if error_code == "AccessDeniedException":
            raise PermissionError(
                "Your AWS credentials don't have permission to use Cost Explorer.\n"
                "Fix: Go to IAM → your user → Attach policies → add 'AWSBillingReadOnlyAccess'.\n"
                f"AWS said: {error_message}"
            )

        elif error_code == "InvalidClientTokenId":
            raise ValueError(
                "Your AWS_ACCESS_KEY_ID is invalid or has been deleted.\n"
                "Check the value in your .env file."
            )

        elif error_code == "SignatureDoesNotMatch":
            raise ValueError(
                "Your AWS_SECRET_ACCESS_KEY is wrong.\n"
                "Check the value in your .env file — it must match the access key exactly."
            )

        elif error_code == "OptInRequired":
            raise PermissionError(
                "Cost Explorer is not enabled on this AWS account.\n"
                "Fix: Go to AWS Console → Billing → Cost Explorer → Enable it (free, takes ~24h)."
            )

        else:
            # Re-raise anything unexpected so we don't silently swallow errors
            raise RuntimeError(f"Unexpected AWS error [{error_code}]: {error_message}")

    # --- Parse the response ---
    #
    # The raw AWS response looks like this:
    #
    # {
    #   "ResultsByTime": [
    #     {
    #       "TimePeriod": {"Start": "2026-04-15", "End": "2026-04-16"},
    #       "Groups": [
    #         {
    #           "Keys": ["Amazon EC2"],
    #           "Metrics": {
    #             "UnblendedCost": {"Amount": "12.345678", "Unit": "USD"}
    #           }
    #         }
    #       ]
    #     },
    #     ...
    #   ]
    # }
    #
    # We flatten this into a simple list of dicts.

    results = []

    for day_entry in response["ResultsByTime"]:
        # "Start" is the date for this row, e.g. "2026-04-15"
        date = day_entry["TimePeriod"]["Start"]

        for group in day_entry["Groups"]:
            service_name = group["Keys"][0]  # e.g. "Amazon Elastic Compute Cloud - Compute"

            # Amount comes back as a string like "12.345678" — convert to float
            cost_amount = float(group["Metrics"]["UnblendedCost"]["Amount"])

            # Round to 2 decimal places (cents precision is enough for a dashboard)
            cost = round(cost_amount, 2)

            # Skip only entries where AWS literally returned "0" —
            # meaning that service had absolutely no activity that day.
            # We intentionally keep sub-cent charges (e.g. $0.000001)
            # because they are real charges and filtering by a fixed
            # threshold would silently hide legitimate low-cost activity.
            if cost_amount == 0.0:
                continue

            results.append({
                "date": date,
                "cost": cost,
                "service": service_name,
            })

    return results
