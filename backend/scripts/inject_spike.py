"""
Inject a synthetic cost spike for a live demo of the anomaly pipeline.

What it does
------------
Writes ~14 days of a steady baseline plus one large spike on the most recent
completed day, all under a chosen service, into cost_records. Then trigger a
sync ("Sync now" in the UI, or POST /api/v1/admin/sync) — detection sees the
spike, creates an Alert, and (if SendGrid is configured) emails it.

Why a dedicated demo service by default?
  AWS never returns "Anomaly Demo Service", so a normal sync won't overwrite
  these rows and the spike survives for detection to find. The high baseline
  also guarantees the service lands in detection's top-5 service list.

Usage (from the backend/ directory, with the venv active):
    python scripts/inject_spike.py
    python scripts/inject_spike.py --amount 1200 --baseline 90
    python scripts/inject_spike.py --service "Amazon EC2"
    python scripts/inject_spike.py --undo            # remove what was injected

Re-running the inject is safe: rows are upserted, so the same demo replays.
"""

import argparse
import asyncio
import os
import sys
from datetime import date, timedelta
from decimal import Decimal

# Allow running as a plain script (python scripts/inject_spike.py) by putting
# the backend/ root on the import path so `app.*` resolves.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import delete, select  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.alert import Alert  # noqa: E402
from app.models.cost import AwsAccount, CostRecord  # noqa: E402

DEFAULT_SERVICE = "Anomaly Demo Service"
BASELINE_DAYS = 14


async def _first_account(db) -> AwsAccount:
    """Return the first account, creating a placeholder one if the DB is empty."""
    account = (
        await db.execute(select(AwsAccount).order_by(AwsAccount.id))
    ).scalars().first()
    if account is None:
        account = AwsAccount(account_id="000000000000")
        db.add(account)
        await db.flush()
    return account


async def inject(spike_amount: float, baseline: float, service: str) -> None:
    if service != DEFAULT_SERVICE:
        print(f"WARNING: '{service}' may be a real AWS service. If AWS returns "
              f"data for it, the next sync's upsert will overwrite this spike "
              f"before detection runs, and no alert will fire. The default "
              f"'{DEFAULT_SERVICE}' avoids this.\n")

    async with AsyncSessionLocal() as db:
        account = await _first_account(db)

        today = date.today()
        # Detection only evaluates days strictly before today, so the spike goes
        # on the most recent completed day (yesterday).
        spike_day = today - timedelta(days=1)

        rows = []
        # Baseline: BASELINE_DAYS days ending the day before the spike. Alternate
        # +/- $2 so the standard deviation is non-zero (otherwise z is undefined).
        for i in range(BASELINE_DAYS, 0, -1):
            day = spike_day - timedelta(days=i)
            amount = baseline + (2.0 if i % 2 == 0 else -2.0)
            rows.append({
                "aws_account_id": account.id,
                "date": day,
                "service_name": service,
                "amount_usd": Decimal(str(round(amount, 2))),
            })
        # The spike itself.
        rows.append({
            "aws_account_id": account.id,
            "date": spike_day,
            "service_name": service,
            "amount_usd": Decimal(str(round(spike_amount, 2))),
        })

        stmt = pg_insert(CostRecord).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_cost_record_account_date_service",
            set_={"amount_usd": stmt.excluded.amount_usd},
        )
        await db.execute(stmt)
        await db.commit()

        baseline_start = spike_day - timedelta(days=BASELINE_DAYS)
        baseline_end = spike_day - timedelta(days=1)
        print(f"Injected demo spike for account {account.account_id}")
        print(f"  service:  {service}")
        print(f"  baseline: ~${baseline:.2f}/day, {baseline_start} -> {baseline_end} ({BASELINE_DAYS} rows)")
        print(f"  spike:    ${spike_amount:.2f} on {spike_day} (1 row)")
        print()
        print("Next: trigger a sync (UI 'Sync now' or POST /api/v1/admin/sync),")
        print("then open /alerts — a high-severity alert should appear, plus an")
        print("email if SendGrid is configured in .env.")
        print()
        print("To undo everything this created (cost rows + any alert it raised):")
        print(f'  python scripts/inject_spike.py --undo --service "{service}"')


async def undo(service: str) -> None:
    """Remove the injected cost rows and any alerts raised for *service*."""
    async with AsyncSessionLocal() as db:
        alert_result = await db.execute(
            delete(Alert).where(Alert.service_name == service)
        )
        cost_result = await db.execute(
            delete(CostRecord).where(CostRecord.service_name == service)
        )
        await db.commit()
        print(f"Removed {cost_result.rowcount} cost row(s) and "
              f"{alert_result.rowcount} alert(s) for service '{service}'.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Inject (or undo) a demo cost spike.")
    parser.add_argument("--amount", type=float, default=900.0,
                        help="Spike amount in USD (default: 900)")
    parser.add_argument("--baseline", type=float, default=80.0,
                        help="Baseline daily amount in USD (default: 80)")
    parser.add_argument("--service", default=DEFAULT_SERVICE,
                        help=f'Service name to spike (default: "{DEFAULT_SERVICE}")')
    parser.add_argument("--undo", action="store_true",
                        help="Remove the injected rows and alerts for --service")
    args = parser.parse_args()

    if args.undo:
        asyncio.run(undo(args.service))
    else:
        asyncio.run(inject(args.amount, args.baseline, args.service))


if __name__ == "__main__":
    main()
