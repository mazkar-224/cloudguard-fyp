"""
Runnable module — prints a real AWS cost table in the terminal.

Run from the backend/ folder:
    python -m app.aws_client
    python -m app.aws_client --days 7
"""

import argparse

from app.services.aws_cost import get_daily_costs
from app.utils.display import print_cost_table


def main():
    # argparse lets us accept optional command-line arguments.
    # e.g. `python -m app.aws_client --days 7` fetches 7 days instead of 30.
    parser = argparse.ArgumentParser(description="Fetch and display AWS daily costs.")
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of past days to fetch (default: 30)",
    )
    args = parser.parse_args()

    print(f"Fetching last {args.days} days of AWS costs...\n")

    try:
        costs = get_daily_costs(days=args.days)
    except (ValueError, PermissionError, RuntimeError) as e:
        print(f"ERROR: {e}")
        return

    print_cost_table(costs)


# This block only runs when the file is executed directly,
# not when it is imported by another module.
if __name__ == "__main__":
    main()
