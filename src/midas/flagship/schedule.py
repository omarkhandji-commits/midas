"""User-installed schedule recipes.

MIDAS never creates OS cron jobs silently. It stores an auditable recipe and prints
copy-paste commands that the operator can install deliberately.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class ScheduleRecipe:
    name: str
    command: str
    cadence: str
    at: str
    windows_task: str
    cron_line: str
    github_actions: str


class ScheduleStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def add(self, recipe: ScheduleRecipe) -> None:
        rows = [r for r in self.list() if r.name != recipe.name]
        rows.append(recipe)
        self.path.write_text(
            json.dumps([asdict(r) for r in rows], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def list(self) -> list[ScheduleRecipe]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8") or "[]")
        return [ScheduleRecipe(**row) for row in data]


def daily_scan_recipe(
    *,
    name: str,
    niche: str,
    at: str = "09:00",
    base_dir: str = ".",
    mode: str = "deep",
) -> ScheduleRecipe:
    _validate_name(name)
    hour, minute = _parse_time(at)
    command = (
        f'midas scan "{_escape_arg(niche)}" --mode {mode} '
        f'--live --base-dir "{_escape_arg(base_dir)}"'
    )
    task_name = f"MIDAS-{name}"
    windows_task = (
        f'schtasks /Create /SC DAILY /TN "{task_name}" /TR "{command}" '
        f"/ST {hour:02d}:{minute:02d}"
    )
    cron_line = f"{minute} {hour} * * * cd \"{_escape_arg(base_dir)}\" && {command}"
    github_actions = (
        "name: MIDAS Daily Scan\n"
        "on:\n"
        "  schedule:\n"
        f"    - cron: '{minute} {hour} * * *'\n"
        "  workflow_dispatch:\n"
        "jobs:\n"
        "  scan:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - uses: actions/checkout@v4\n"
        "      - uses: actions/setup-python@v5\n"
        "        with:\n"
        "          python-version: '3.11'\n"
        "      - run: pip install -e .[llm,web]\n"
        f"      - run: {command}\n"
    )
    return ScheduleRecipe(
        name=name,
        command=command,
        cadence="daily",
        at=f"{hour:02d}:{minute:02d}",
        windows_task=windows_task,
        cron_line=cron_line,
        github_actions=github_actions,
    )


def _parse_time(value: str) -> tuple[int, int]:
    if not re.fullmatch(r"\d{2}:\d{2}", value):
        raise ValueError("time must be HH:MM")
    hour_s, minute_s = value.split(":", 1)
    hour, minute = int(hour_s), int(minute_s)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("time must be HH:MM in 24h format")
    return hour, minute


def _validate_name(name: str) -> None:
    if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,64}", name):
        raise ValueError("schedule name must be 1-64 chars: letters, numbers, _.-")


def _escape_arg(value: str) -> str:
    return value.replace('"', "'")
