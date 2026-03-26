#!/usr/bin/env python3
import json
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


BASE_DIR = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = 8000
IMPERIAL_OFFSET = 1180
GREGORIAN_DAY_ACCUM = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)


def gregorian_to_jalali(year: int, month: int, day: int) -> tuple[int, int, int]:
    gy = year - 1600
    gm = month - 1
    gd = day - 1

    g_day_no = 365 * gy + (gy + 3) // 4 - (gy + 99) // 100 + (gy + 399) // 400
    g_day_no += GREGORIAN_DAY_ACCUM[gm] + gd
    if gm > 1 and is_gregorian_leap(year):
        g_day_no += 1

    j_day_no = g_day_no - 79
    j_np = j_day_no // 12053
    j_day_no %= 12053

    jy = 979 + 33 * j_np + 4 * (j_day_no // 1461)
    j_day_no %= 1461

    if j_day_no >= 366:
        jy += (j_day_no - 1) // 365
        j_day_no = (j_day_no - 1) % 365

    if j_day_no < 186:
        jm = 1 + j_day_no // 31
        jd = 1 + (j_day_no % 31)
    else:
        jm = 7 + (j_day_no - 186) // 30
        jd = 1 + ((j_day_no - 186) % 30)

    return jy, jm, jd


def jalali_to_gregorian(year: int, month: int, day: int) -> tuple[int, int, int]:
    jy = year - 979
    jm = month - 1
    jd = day - 1

    j_day_no = 365 * jy + (jy // 33) * 8 + ((jy % 33) + 3) // 4
    for index in range(jm):
        j_day_no += 31 if index < 6 else 30
    j_day_no += jd

    g_day_no = j_day_no + 79
    gy = 1600 + 400 * (g_day_no // 146097)
    g_day_no %= 146097

    leap = True
    if g_day_no >= 36525:
        g_day_no -= 1
        gy += 100 * (g_day_no // 36524)
        g_day_no %= 36524

        if g_day_no >= 365:
            g_day_no += 1
        else:
            leap = False

    if g_day_no >= 1461:
        gy += 4 * (g_day_no // 1461)
        g_day_no %= 1461

    if g_day_no >= 366:
        leap = False
        g_day_no -= 1
        gy += g_day_no // 365
        g_day_no %= 365

    gd = g_day_no + 1
    month_lengths = (0, 31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    gm = 1
    while gm <= 12 and gd > month_lengths[gm]:
        gd -= month_lengths[gm]
        gm += 1

    return gy, gm, gd


def is_gregorian_leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def is_jalali_leap(year: int) -> bool:
    next_year_start = jalali_to_gregorian(year + 1, 1, 1)
    this_year_start = jalali_to_gregorian(year, 1, 1)
    return (date(*next_year_start) - date(*this_year_start)).days == 366


def max_day(calendar_name: str, year: int, month: int) -> int:
    if month < 1 or month > 12:
        raise ValueError("Invalid month")

    if calendar_name == "gregorian":
        if month == 2:
            return 29 if is_gregorian_leap(year) else 28
        if month in {4, 6, 9, 11}:
            return 30
        return 31

    if month <= 6:
        return 31
    if month <= 11:
        return 30
    return 30 if is_jalali_leap(year) else 29


def validate_date(calendar_name: str, year: int, month: int, day: int) -> None:
    if day < 1 or day > max_day(calendar_name, year, month):
        raise ValueError("Invalid day")


def normalize_source(source_calendar: str, year: int, month: int, day: int) -> tuple[int, int, int]:
    if source_calendar == "gregorian":
        validate_date(source_calendar, year, month, day)
        return year, month, day

    if source_calendar == "solar_hijri":
        validate_date(source_calendar, year, month, day)
        return jalali_to_gregorian(year, month, day)

    if source_calendar == "imperial_iranian":
        jalali_year = year - IMPERIAL_OFFSET
        validate_date("solar_hijri", jalali_year, month, day)
        return jalali_to_gregorian(jalali_year, month, day)

    raise ValueError("Unsupported calendar")


def build_payload(gregorian_year: int, gregorian_month: int, gregorian_day: int, target_calendar: str) -> dict:
    jalali_year, jalali_month, jalali_day = gregorian_to_jalali(gregorian_year, gregorian_month, gregorian_day)
    imperial_year = jalali_year + IMPERIAL_OFFSET

    calendars = {
        "gregorian": {"year": gregorian_year, "month": gregorian_month, "day": gregorian_day},
        "solar_hijri": {"year": jalali_year, "month": jalali_month, "day": jalali_day},
        "imperial_iranian": {"year": imperial_year, "month": jalali_month, "day": jalali_day},
    }

    return {
        "result": calendars[target_calendar],
        "gregorian": calendars["gregorian"],
        "solar_hijri": calendars["solar_hijri"],
        "imperial_iranian": calendars["imperial_iranian"],
        "today": {"year": date.today().year, "month": date.today().month, "day": date.today().day},
    }


class AppHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            self.serve_file("index.html", "text/html; charset=utf-8")
            return

        if path == "/persian-version.html":
            self.serve_file("persian-version.html", "text/html; charset=utf-8")
            return

        self.send_error(404, "Not Found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/convert":
            self.send_error(404, "Not Found")
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(content_length)
            payload = json.loads(body.decode("utf-8"))

            source_calendar = payload["source_calendar"]
            target_calendar = payload["target_calendar"]
            year = int(payload["year"])
            month = int(payload["month"])
            day = int(payload["day"])

            if source_calendar not in {"gregorian", "solar_hijri", "imperial_iranian"}:
                raise ValueError("Unsupported source calendar")
            if target_calendar not in {"gregorian", "solar_hijri", "imperial_iranian"}:
                raise ValueError("Unsupported target calendar")

            gregorian_year, gregorian_month, gregorian_day = normalize_source(source_calendar, year, month, day)
            response = build_payload(gregorian_year, gregorian_month, gregorian_day, target_calendar)
            self.send_json(200, response)
        except (ValueError, KeyError, json.JSONDecodeError):
            self.send_json(400, {"error": "invalid_date"})

    def serve_file(self, filename: str, content_type: str) -> None:
        file_path = BASE_DIR / filename
        if not file_path.exists():
            self.send_error(404, "File not found")
            return

        content = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def send_json(self, status: int, payload: dict) -> None:
        content = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format: str, *args) -> None:
        return


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), AppHandler)
    print(f"Serving on http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
