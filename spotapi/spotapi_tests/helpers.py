import re
from pathlib import Path
from typing import Any, Dict

from rich.console import Console
from rich.table import Table

console: Console = Console(record=True)
REPORT_PATH: Path = Path("./spotapi_tests/reports/spotapi_tests_report.md")
REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)


def save_report() -> None:
    console.save_text(str(REPORT_PATH))


def log_table(title: str, data: Dict[str, Any]) -> None:
    table: Table = Table(title=title)
    table.add_column("Metric", style="cyan", justify="left")
    table.add_column("Value", style="magenta", justify="right")
    for k, v in data.items():
        table.add_row(str(k), str(v))
    console.print(table)
    with REPORT_PATH.open("a", encoding="utf-8") as f:
        f.write(f"### {title}\n\n")
        f.write("| Metric | Value |\n|--------|-------|\n")
        for k, v in data.items():
            f.write(f"| {k} | {v} |\n")
        f.write("\n")


def log_message(msg: str) -> None:
    console.print(msg)
    with REPORT_PATH.open("a", encoding="utf-8") as f:
        clean: str = re.sub(r"\[.*?\]", "", msg)
        f.write(f"{clean}\n\n")
