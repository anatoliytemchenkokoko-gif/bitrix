#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = BASE_DIR / "docs"
CONFIG_PATH = BASE_DIR / "calendars.json"


def parse_basic_ics_datetime(value: str) -> datetime | None:
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%dT%H%M%S", "%Y%m%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def normalize_dtstamp(line: str) -> str:
    if not line.startswith("DTSTAMP:"):
        return line
    value = line.split(":", 1)[1]
    match = re.fullmatch(r"(\d{8}T\d{6})(\d{5})", value)
    if not match:
        return line
    dt_value, offset_seconds = match.groups()
    dt = datetime.strptime(dt_value, "%Y%m%dT%H%M%S")
    utc_dt = dt - timedelta(seconds=int(offset_seconds))
    return f"DTSTAMP:{utc_dt.replace(tzinfo=timezone.utc):%Y%m%dT%H%M%SZ}"


def split_ics_lines(raw_text: str) -> list[str]:
    normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    return normalized.split("\n")


def sanitize_ics_lines(lines: list[str]) -> list[str]:
    output: list[str] = []
    for line in lines:
        if not line.strip():
            continue
        output.append(normalize_dtstamp(line))
    return output


def split_components(lines: list[str]) -> list[list[str]]:
    components: list[list[str]] = []
    current: list[str] = []
    in_event = False
    for line in lines:
        if line == "BEGIN:VEVENT":
            in_event = True
            current = [line]
            continue
        if in_event:
            current.append(line)
            if line == "END:VEVENT":
                components.append(current)
                current = []
                in_event = False
    return components


def parse_component(component: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in component:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        parsed[key] = value
        base_key = key.split(";", 1)[0]
        parsed.setdefault(base_key, value)
    return parsed


def rrule_occurrence_dates(component: dict[str, str], limit: int = 64) -> set[str]:
    rrule = component.get("RRULE")
    dtstart_raw = component.get("DTSTART")
    if not rrule or not dtstart_raw:
        return set()

    dtstart = parse_basic_ics_datetime(dtstart_raw)
    if dtstart is None:
        return set()

    parts: dict[str, str] = {}
    for part in rrule.split(";"):
        if "=" in part:
            key, value = part.split("=", 1)
            parts[key] = value

    freq = parts.get("FREQ")
    if freq not in {"DAILY", "WEEKLY"}:
        return set()

    occurrences = {dtstart.strftime("%Y%m%d")}
    current = dtstart
    until = parts.get("UNTIL")
    count = int(parts["COUNT"]) if parts.get("COUNT", "").isdigit() else None
    until_dt = parse_basic_ics_datetime(until) if until else None
    byday = set(parts.get("BYDAY", "").split(",")) if parts.get("BYDAY") else None
    weekday_codes = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]

    generated = 1
    while generated < limit:
        current += timedelta(days=1 if freq == "DAILY" else 7)
        if until_dt and current > until_dt:
            break
        if count and generated >= count:
            break
        if byday and weekday_codes[current.weekday()] not in byday:
            continue
        occurrences.add(current.strftime("%Y%m%d"))
        generated += 1
    return occurrences


def drop_problematic_rrules(lines: list[str]) -> list[str]:
    components = split_components(lines)
    parsed_components = [parse_component(component) for component in components]

    standalone_dates_by_summary: dict[str, set[str]] = {}
    for parsed in parsed_components:
        summary = parsed.get("SUMMARY", "").strip()
        if not summary or "RRULE" in parsed:
            continue
        dtstart = parsed.get("DTSTART", "")
        if len(dtstart) < 8:
            continue
        standalone_dates_by_summary.setdefault(summary, set()).add(dtstart[:8])

    filtered: list[list[str]] = []
    for component, parsed in zip(components, parsed_components):
        summary = parsed.get("SUMMARY", "").strip()
        rrule = parsed.get("RRULE")
        if not summary or not rrule:
            filtered.append(component)
            continue
        recurrence_dates = rrule_occurrence_dates(parsed)
        standalone_dates = standalone_dates_by_summary.get(summary, set())
        overlap_dates = recurrence_dates & standalone_dates
        if overlap_dates:
            continue
        filtered.append(component)

    if not filtered:
        return lines

    output: list[str] = []
    component_iter = iter(filtered)
    current_component = next(component_iter, None)
    in_event = False
    for line in lines:
        if line == "BEGIN:VEVENT":
            in_event = True
            if current_component is not None:
                output.extend(current_component)
                current_component = next(component_iter, None)
            continue
        if in_event:
            if line == "END:VEVENT":
                in_event = False
            continue
        output.append(line)
    return output


def inject_calendar_metadata(lines: list[str], calendar_name: str) -> list[str]:
    has_name = any(line.startswith("X-WR-CALNAME:") for line in lines)
    has_tz = any(line.startswith("X-WR-TIMEZONE:") for line in lines)
    has_method = any(line.startswith("METHOD:") for line in lines)

    output: list[str] = []
    inserted = False
    for line in lines:
        output.append(line)
        if line == "VERSION:2.0" and not inserted:
            if not has_method:
                output.append("METHOD:PUBLISH")
            if not has_name:
                output.append(f"X-WR-CALNAME:{calendar_name}")
            if not has_tz:
                output.append("X-WR-TIMEZONE:Asia/Yekaterinburg")
            inserted = True
    return output


def normalize_ics(raw_text: str, calendar_name: str) -> str:
    text = raw_text.lstrip("\ufeff").strip()
    if "BEGIN:VCALENDAR" not in text:
        snippet = text[:200].replace("\n", " ")
        raise ValueError(f"Upstream did not return an ICS calendar. First bytes: {snippet}")
    lines = split_ics_lines(text)
    lines = sanitize_ics_lines(lines)
    lines = drop_problematic_rrules(lines)
    lines = inject_calendar_metadata(lines, calendar_name)
    return "\r\n".join(lines).strip() + "\r\n"


def fetch_text(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "BitrixStaticCalendarSync/1.0",
            "Accept": "text/calendar, text/plain, */*",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8-sig", errors="replace")


def render_index(calendars: list[dict[str, str]]) -> str:
    cards = []
    for calendar in calendars:
        href = f"./{calendar['filename']}"
        cards.append(
            f"""
      <section class="card">
        <p>Синхронизация календаря компании для Apple Calendar</p>
        <h1>{calendar['name']}</h1>
        <p>Это статическая ссылка на готовый `ics`, которую можно добавить в Apple Calendar как подписку.</p>
        <a class="url" href="{href}">{href}</a>
      </section>"""
        )

    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Bitrix Calendar Sync</title>
  <style>
    :root {{
      color-scheme: light;
      --text: #1c1917;
      --muted: #6b6258;
      --accent: #134e4a;
      --border: #d6d0c4;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "SF Pro Display", "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(15,118,110,.16), transparent 32%),
        linear-gradient(180deg, #f8f6f1 0%, #efe8da 100%);
      color: var(--text);
    }}
    main {{
      max-width: 760px;
      margin: 0 auto;
      padding: 48px 20px 80px;
      display: grid;
      gap: 18px;
    }}
    .card {{
      background: rgba(255,253,247,.92);
      border: 1px solid var(--border);
      border-radius: 24px;
      padding: 28px;
      box-shadow: 0 18px 60px rgba(28,25,23,.08);
    }}
    h1 {{
      margin: 0 0 12px;
      font-size: clamp(2rem, 5vw, 3.2rem);
      line-height: 1;
      letter-spacing: -.04em;
    }}
    p {{
      margin: 0 0 14px;
      font-size: 1rem;
      line-height: 1.6;
      color: var(--muted);
    }}
    .url {{
      display: block;
      margin-top: 18px;
      padding: 14px 16px;
      border-radius: 16px;
      background: #f1ece2;
      color: var(--accent);
      text-decoration: none;
      word-break: break-all;
      font-weight: 600;
    }}
  </style>
</head>
<body>
  <main>
    {''.join(cards)}
  </main>
</body>
</html>"""


def main() -> None:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)

    calendars_for_index = []
    for calendar in config["calendars"]:
        raw_text = fetch_text(calendar["url"])
        normalized = normalize_ics(raw_text, calendar["name"])
        filename = calendar["filename"]
        (PUBLIC_DIR / filename).write_text(normalized, encoding="utf-8", newline="")
        calendars_for_index.append({"name": calendar["name"], "filename": filename})

    (PUBLIC_DIR / "index.html").write_text(
        render_index(calendars_for_index),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
