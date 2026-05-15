"""
Quick test script — run this directly to verify your AWS credentials work
and Cost Explorer returns data, displayed as a colored terminal table.

Run from the backend/ folder (with venv active):
    python test_aws_cost.py
"""

from app.services.aws_cost import get_daily_costs
from app.utils.display import print_cost_table


def main():
    print("Fetching last 7 days of AWS costs...\n")

    try:
        costs = get_daily_costs(days=7)
    except (ValueError, PermissionError, RuntimeError) as e:
        print(f"ERROR: {e}")
        return

    # Hand off to the display utility — it handles empty lists too
    print_cost_table(costs)


if __name__ == "__main__":
    main()
