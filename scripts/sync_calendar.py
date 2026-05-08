#!/usr/bin/env python3
"""
Sync holidayCal.ics with the Apple iCloud Chinese holiday calendar,
then inject custom international holidays (Valentine's Day, Mother's Day,
Father's Day) for every year covered by the iCloud data.

Usage:
    python3 scripts/sync_calendar.py [--icloud-url URL] [--output PATH]
"""

import argparse
import re
import sys
import urllib.request
from datetime import date, timedelta


ICLOUD_URL = "https://calendars.icloud.com/holidays/cn_zh.ics/"
DEFAULT_OUTPUT = "holidayCal.ics"

# UIDs for custom events – must be stable so we can de-duplicate on re-run
CUSTOM_UID_TEMPLATE = "{dtstr}_intl_{key}@custom"

CUSTOM_HOLIDAYS = [
    {
        "key": "valentines",
        "summary": "💕 情人节",
        "description": "Valentine's Day - 每年2月14日",
        "fn": lambda year: date(year, 2, 14),
    },
    {
        "key": "mothersday",
        "summary": "👩 母亲节",
        "description": "Mother's Day - 每年5月第2个周日",
        "fn": lambda year: _nth_weekday(year, 5, 6, 2),
    },
    {
        "key": "fathersday",
        "summary": "👨 父亲节",
        "description": "Father's Day - 每年6月第3个周日",
        "fn": lambda year: _nth_weekday(year, 6, 6, 3),
    },
]


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """Return the nth occurrence of *weekday* (0=Mon … 6=Sun) in month."""
    d = date(year, month, 1)
    days_ahead = weekday - d.weekday()
    if days_ahead < 0:
        days_ahead += 7
    return d + timedelta(days=days_ahead) + timedelta(weeks=n - 1)


def fetch_icloud(url: str) -> str:
    """Download and return the iCloud ICS file as a UTF-8 string."""
    req = urllib.request.Request(
        url,
        headers={
            "Accept-Encoding": "gzip, deflate",
            "User-Agent": "Mozilla/5.0 (calendar sync script)",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    # Handle gzip transparently (urllib does this when Content-Encoding is set,
    # but some servers omit the header – decode manually if needed)
    if data[:2] == b"\x1f\x8b":
        import gzip
        data = gzip.decompress(data)
    return data.decode("utf-8", errors="replace")


def extract_years(ics: str) -> list[int]:
    """Scan DTSTART lines to find which calendar years are present."""
    years = set()
    for match in re.finditer(r"DTSTART[^:]*:(\d{4})", ics):
        years.add(int(match.group(1)))
    return sorted(years)


def strip_custom_events(ics: str) -> str:
    """Remove previously injected custom VEVENT blocks (identified by UID suffix)."""
    # Match BEGIN:VEVENT ... END:VEVENT blocks that contain our custom UID
    pattern = re.compile(
        r"BEGIN:VEVENT\r?\n(?:(?!END:VEVENT)[\s\S])*?"
        r"UID:[^\r\n]*@custom[^\r\n]*\r?\n"
        r"(?:(?!END:VEVENT)[\s\S])*?END:VEVENT\r?\n?",
        re.MULTILINE,
    )
    return pattern.sub("", ics)


def build_vevent(d: date, summary: str, description: str, key: str) -> str:
    dtstr = d.strftime("%Y%m%d")
    dtend = (d + timedelta(days=1)).strftime("%Y%m%d")
    uid = CUSTOM_UID_TEMPLATE.format(dtstr=dtstr, key=key)
    return (
        "BEGIN:VEVENT\n"
        "DTSTAMP;VALUE=DATE:19760401\n"
        f"UID:{uid}\n"
        f"DTSTART;VALUE=DATE:{dtstr}\n"
        f"DTEND;VALUE=DATE:{dtend}\n"
        "CLASS:PUBLIC\n"
        f"SUMMARY;LANGUAGE=zh_CN:{summary}\n"
        f"DESCRIPTION:{description}\n"
        "TRANSP:TRANSPARENT\n"
        "CATEGORIES:節慶\n"
        "END:VEVENT"
    )


def inject_custom_events(ics: str, years: list[int]) -> str:
    """Append custom holiday VEVENTs before END:VCALENDAR."""
    events = []
    for year in years:
        for h in CUSTOM_HOLIDAYS:
            d = h["fn"](year)
            events.append(build_vevent(d, h["summary"], h["description"], h["key"]))

    block = "\n".join(events)
    # Insert before END:VCALENDAR
    ics = ics.rstrip()
    if ics.endswith("END:VCALENDAR"):
        ics = ics[: -len("END:VCALENDAR")].rstrip()
    return ics + "\n" + block + "\nEND:VCALENDAR\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync holidayCal.ics from iCloud")
    parser.add_argument("--icloud-url", default=ICLOUD_URL)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    print(f"Fetching iCloud calendar from {args.icloud_url} …")
    try:
        ics = fetch_icloud(args.icloud_url)
    except Exception as exc:
        print(f"ERROR: failed to fetch iCloud calendar: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Downloaded {len(ics)} bytes")

    years = extract_years(ics)
    print(f"Calendar covers years: {years}")

    ics = strip_custom_events(ics)
    ics = inject_custom_events(ics, years)

    total = ics.count("BEGIN:VEVENT")
    custom = sum(1 for h in CUSTOM_HOLIDAYS for _ in years)
    print(f"Total events: {total} ({custom} custom, {total - custom} from iCloud)")

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(ics)
    print(f"Written to {args.output}")


if __name__ == "__main__":
    main()
