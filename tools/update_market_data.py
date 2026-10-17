#!/usr/bin/env python3
"""Refresh the Mortgage Rates data for milliekillpack.com.

Pulls Freddie Mac's Primary Mortgage Market Survey (PMMS) history and writes
site/data/market.json, which rates.html reads in the browser:
latest 30- and 15-year fixed rates, the prior week, a year ago, the 5-year
range and a weekly 5-year series.  https://www.freddiemac.com/pmms
Terms: Freddie Mac information may be used with proper attribution, unaltered.

Rules: numbers are only copied from the source file and range-checked. If the
fetch fails, the last good copy is kept (with its own dates) and marked stale.

Usage:  python3 tools/update_market_data.py   (standard library only, ~2 s)
"""
import csv, io, json, os, sys, time, datetime, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.dirname(HERE)
OUT = os.path.join(SITE, "data", "market.json")
UA = "milliekillpack.com market-trends updater (python urllib)"

PMMS_URL = "https://www.freddiemac.com/pmms/docs/PMMS_history.csv"

SOURCES = {
    "freddie": {"name": "Freddie Mac Primary Mortgage Market Survey®", "url": "https://www.freddiemac.com/pmms",
                "credit": "Source: Freddie Mac, Primary Mortgage Market Survey®.",
                "terms": "Freddie Mac: information may be used with proper attribution; not altered."},
}

def log(*a): print(*a, file=sys.stderr, flush=True)

def fetch(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read().decode("utf-8-sig")
        except Exception as e:
            log(f"  fetch failed ({i+1}/{tries}) {url}: {e}")
            time.sleep(5 * (i + 1))
    raise RuntimeError("could not fetch " + url)

def num(v):
    if v is None: return None
    v = str(v).strip().replace(",", "")
    if v in ("", "NA", "NaN", "nan", "None", "."): return None
    try: return float(v)
    except ValueError: return None

def sane(v, lo, hi):
    return v if (v is not None and lo <= v <= hi) else None

def rnd(v, n=0):
    if v is None: return None
    return round(v, n) if n else int(round(v))

def pct_change(new, old):
    if new is None or old in (None, 0): return None
    return round((new / old - 1) * 100, 1)

# ---------------------------------------------------------------- Freddie Mac
def get_pmms():
    rows = list(csv.DictReader(io.StringIO(fetch(PMMS_URL))))
    pts = []
    for r in rows:
        try: d = datetime.datetime.strptime(r["date"].strip(), "%m/%d/%Y").date()
        except Exception: continue
        r30, r15 = sane(num(r.get("pmms30")), 0.5, 25), sane(num(r.get("pmms15")), 0.5, 25)
        if r30 is not None: pts.append((d, r30, r15))
    pts.sort()
    if not pts: raise RuntimeError("PMMS: no rows")
    last = pts[-1]
    def at_or_before(target):
        c = [p for p in pts if p[0] <= target]
        return c[-1] if c else None
    wk = pts[-2] if len(pts) > 1 else None
    yr = at_or_before(last[0] - datetime.timedelta(days=364))
    start = last[0] - datetime.timedelta(days=365 * 5 + 7)
    series = [[p[0].isoformat(), p[1]] for p in pts if p[0] >= start]
    five = [p[1] for p in pts if p[0] >= start]
    return {
        "as_of": last[0].isoformat(), "rate30": last[1], "rate15": last[2],
        "rate30_prev_week": wk[1] if wk else None, "prev_week_date": wk[0].isoformat() if wk else None,
        "rate30_year_ago": yr[1] if yr else None, "year_ago_date": yr[0].isoformat() if yr else None,
        "rate30_5y_low": min(five), "rate30_5y_high": max(five),
        "series30": series,
    }

# ---------------------------------------------------------------- insights
MONTHS = "January February March April May June July August September October November December".split()
def ym(s):  # "2026-09" -> "September 2026"
    return f"{MONTHS[int(s[5:7]) - 1]} {s[:4]}"
def span(b, e):  # "2026-07-01","2026-09-30" -> "July–September 2026"
    if b[:7] == e[:7]: return ym(b)
    if b[:4] == e[:4]: return f"{MONTHS[int(b[5:7]) - 1]}–{MONTHS[int(e[5:7]) - 1]} {e[:4]}"
    return f"{ym(b)}–{ym(e)}"
def day(s):  # "2026-10-15" -> "Oct 15, 2026"
    d = datetime.date.fromisoformat(s); return f"{MONTHS[d.month - 1][:3]} {d.day}, {d.year}"
def money(v): return "${:,.0f}".format(v)
def updown(p, up="up", down="down"): return up if p >= 0 else down

def build_insights(d):
    """Plain sentences built only from the numbers above (no forecasts)."""
    ins = []
    fm = d.get("freddie")
    if fm and fm.get("rate30") is not None:
        t = f"The average 30-year fixed rate was {fm['rate30']:.2f}% in Freddie Mac’s survey released {day(fm['as_of'])}"
        if fm.get("rate30_year_ago") is not None:
            diff = round(fm["rate30"] - fm["rate30_year_ago"], 2)
            t += (f", {updown(diff)} {abs(diff):.2f} points from a year earlier ({fm['rate30_year_ago']:.2f}%)"
                  if diff != 0 else ", the same as a year earlier")
        t += (f". Over the past five years it has ranged from {fm['rate30_5y_low']:.2f}% to {fm['rate30_5y_high']:.2f}%.")
        ins.append({"title": "Where rates are", "text": t, "sources": ["freddie"]})
    ins.append({"title": "What it means for you",
                "text": ("Rates are reported weekly and can move in either direction. These are national averages, and your own "
                         "rate depends on your credit, loan and lender, so a current pre-approval is the clearest way to see "
                         "what today’s rate means for your budget. If you’re weighing a move, let’s talk about your timing."),
                "sources": []})
    return ins

# ---------------------------------------------------------------- main
def main():
    prev = {}
    if os.path.exists(OUT):
        try: prev = json.load(open(OUT))
        except Exception: prev = {}
    data = {"generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "sources": SOURCES, "stale": []}
    log("Updating freddie ...")
    try:
        data["freddie"] = get_pmms()
    except Exception as e:
        log(f"  !! freddie failed: {e}")
        if prev.get("freddie"):
            data["freddie"] = prev["freddie"]; data["stale"].append("freddie")
        else:
            sys.exit(1)
    data["insights"] = build_insights(data)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f: json.dump(data, f, separators=(",", ":"))
    os.replace(tmp, OUT)
    log(f"Wrote {OUT} ({os.path.getsize(OUT)//1024} KB); stale: {data['stale'] or 'none'}")

if __name__ == "__main__":
    main()
