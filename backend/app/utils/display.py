from collections import defaultdict

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# One shared Console instance — handles color detection and output width automatically
console = Console()


def print_cost_table(costs: list[dict]) -> None:
    """
    Print the output of get_daily_costs() as a colored table in the terminal.

    Groups rows by date. Within each date, services are sorted by cost
    (most expensive first). A subtotal row appears after each date, and a
    grand total row appears at the bottom.

    Example output:
        ╭──────────────────────────────────────────────────────╮
        │              AWS Daily Cost Report                   │
        │  Date        Service                    Cost (USD)   │
        │  2026-04-15  Amazon EC2                    $18.00    │
        │              Amazon S3                      $4.50    │
        │              Day Total                     $22.50    │
        ├──────────────────────────────────────────────────────┤
        │              GRAND TOTAL                   $22.50    │
        ╰──────────────────────────────────────────────────────╯

    Args:
        costs: The list of dicts returned by get_daily_costs().
    """

    if not costs:
        console.print("\n[yellow]No cost data to display.[/yellow]\n")
        return

    # --- Group entries by date ---
    # defaultdict(list) automatically creates an empty list for any new key,
    # so we don't need to check "if date not in dict" before appending.
    costs_by_date: dict[str, list[dict]] = defaultdict(list)
    for entry in costs:
        costs_by_date[entry["date"]].append(entry)

    # Sort dates oldest → newest so the table reads chronologically
    sorted_dates = sorted(costs_by_date.keys())

    # --- Build the Rich table ---
    table = Table(
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        show_lines=False,   # no grid lines between rows — cleaner look
        expand=False,
    )

    table.add_column("Date",       style="yellow",        width=13,  no_wrap=True)
    table.add_column("Service",    style="white",         min_width=35, ratio=1)
    table.add_column("Cost (USD)", style="bright_green",  width=11,  justify="right", no_wrap=True)

    grand_total = 0.0

    for date in sorted_dates:
        day_entries = costs_by_date[date]

        # Sort services by cost descending — biggest spender at the top
        day_entries.sort(key=lambda e: e["cost"], reverse=True)

        day_total = sum(e["cost"] for e in day_entries)
        grand_total += day_total

        for i, entry in enumerate(day_entries):
            # Show the date only on the first row for that day.
            # Repeating it on every row is noisy and harder to scan.
            date_label = date if i == 0 else ""

            table.add_row(
                date_label,
                entry["service"],
                f"${entry['cost']:.2f}",
            )

        # Subtotal row — visually distinct with bold blue and a section divider
        table.add_row(
            "",
            "[bold blue]  └─ Day Total[/bold blue]",
            f"[bold blue]${day_total:.2f}[/bold blue]",
            end_section=True,   # rich draws a dividing line after this row
        )

    # Grand total row at the bottom
    table.add_row(
        "",
        "[bold magenta]  GRAND TOTAL[/bold magenta]",
        f"[bold magenta]${grand_total:.2f}[/bold magenta]",
    )

    # Wrap the table in a Panel so it gets a border and title
    date_range = f"{sorted_dates[0]}  →  {sorted_dates[-1]}"
    panel = Panel(
        table,
        title="[bold white]AWS Daily Cost Report[/bold white]",
        subtitle=f"[dim]{date_range}[/dim]",
        border_style="cyan",
        padding=(0, 1),
    )

    console.print()
    console.print(panel)
    console.print()
