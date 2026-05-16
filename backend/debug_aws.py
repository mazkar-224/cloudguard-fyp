"""
Diagnostic script — run this to find out exactly why cost data is empty.

    python debug_aws.py
"""

import boto3
from datetime import datetime, timedelta
from app.config import settings

print("=" * 60)
print("STEP 1 — Checking credentials in .env")
print("=" * 60)

# Check if the values are still the placeholder text from .env.example
placeholder_key    = "your-access-key-id"
placeholder_secret = "your-secret-access-key"

if settings.aws_access_key_id == placeholder_key:
    print("ERROR: AWS_ACCESS_KEY_ID is still the placeholder value.")
    print("       Open .env and replace it with your real access key.")
    exit(1)

if settings.aws_secret_access_key == placeholder_secret:
    print("ERROR: AWS_SECRET_ACCESS_KEY is still the placeholder value.")
    print("       Open .env and replace it with your real secret key.")
    exit(1)

print(f"  Access Key ID : {settings.aws_access_key_id[:8]}... (loaded)")
print(f"  Region        : {settings.aws_region}")
print()

print("=" * 60)
print("STEP 2 — Verifying credentials with AWS STS")
print("=" * 60)
print("  (STS = Security Token Service — used to check who you are)")

try:
    sts = boto3.client(
        "sts",
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name="us-east-1",
    )
    identity = sts.get_caller_identity()
    print(f"  Account ID : {identity['Account']}")
    print(f"  User ARN   : {identity['Arn']}")
    print("  Credentials are VALID.")
except Exception as e:
    print(f"  ERROR: Credentials are invalid or expired.")
    print(f"  Detail: {e}")
    exit(1)

print()
print("=" * 60)
print("STEP 3 — Calling Cost Explorer directly (raw response)")
print("=" * 60)

end_date   = datetime.now().date()
start_date = end_date - timedelta(days=7)
print(f"  Date range: {start_date} → {end_date}")
print()

try:
    ce = boto3.client(
        "ce",
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name="us-east-1",
    )
    response = ce.get_cost_and_usage(
        TimePeriod={
            "Start": str(start_date),
            "End":   str(end_date),
        },
        Granularity="DAILY",
        Metrics=["UnblendedCost"],
        GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
    )
except Exception as e:
    print(f"  ERROR calling Cost Explorer: {e}")
    exit(1)

days = response["ResultsByTime"]
print(f"  Days returned by AWS: {len(days)}")
print()

total_cost = 0.0
non_zero_rows = 0

for day in days:
    date = day["TimePeriod"]["Start"]
    groups = day["Groups"]
    day_total = sum(float(g["Metrics"]["UnblendedCost"]["Amount"]) for g in groups)
    total_cost += day_total

    non_zero = [g for g in groups if float(g["Metrics"]["UnblendedCost"]["Amount"]) > 0]
    non_zero_rows += len(non_zero)

    status = f"${day_total:.4f}" if day_total > 0 else "  $0.00 (no spending)"
    print(f"  {date}  →  {status}  ({len(non_zero)} non-zero services)")

print()
print(f"  Total across all days : ${total_cost:.4f}")
print(f"  Non-zero service rows : {non_zero_rows}")
print()

print("=" * 60)
print("DIAGNOSIS")
print("=" * 60)

if total_cost == 0 and len(days) == 0:
    print("  Cost Explorer returned NO days at all.")
    print("  → Cost Explorer is probably not enabled on this account.")
    print("  → Go to: AWS Console → Billing → Cost Explorer → Enable")
    print("  → After enabling, wait up to 24 hours for data to appear.")

elif total_cost == 0 and len(days) > 0:
    print("  Cost Explorer returned days but all costs are $0.00.")
    print("  This means one of:")
    print("  a) This AWS account has genuinely had no spending in the last 7 days.")
    print("  b) Cost Explorer was just enabled — data takes up to 24h to appear.")
    print("  c) You are looking at a brand-new or unused AWS account.")
    print()
    print("  Try fetching 90 days to see if older data exists:")
    print("  Change days=7 to days=90 in test_aws_cost.py")

else:
    print(f"  Data looks fine — ${total_cost:.2f} in spending found.")
    print("  The display function filters out $0.00 rows.")
    print("  If all your costs round to $0.00, try this fix in aws_cost.py:")
    print("  Change:  if cost == 0.0: continue")
    print("  To:      if cost < 0.001: continue")
