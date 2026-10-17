#!/usr/bin/env python3
"""Refresh the Market Trends data for milliekillpack.com.

Pulls the latest published figures from free, public sources and writes
site/data/market.json, which market.html reads in the browser.

Sources (all free; attribution required and shown on the page):
  * Freddie Mac Primary Mortgage Market Survey (PMMS): weekly 30- and 15-year
    fixed rates.  https://www.freddiemac.com/pmms
  * Redfin Data Center, Housing Market Tracker (monthly): median sale price,
    days on market, inventory, months of supply, sale-to-list, homes sold for
    Lehi (rolling 3 months), Utah County and Utah.  https://www.redfin.com/news/data-center/
  * Zillow Research, Zillow Home Value Index (ZHVI, mid-tier, smoothed, SA):
    typical home value for Lehi, Utah County and Utah.  https://www.zillow.com/research/data/
  * Realtor.com Economic Research, Housing Inventory Core Metrics: median and
    average listing price, active listings for Utah County and Utah.
    https://www.realtor.com/research/data/

Rules: numbers are only ever copied from the source files. Nothing is
estimated or filled in. If a source fails, the last good copy of that source
is kept (with its own dates) and marked stale; if a metric is missing it is
left out and the page hides it.

Usage:  python3 tools/update_market_data.py            (from the site folder)
Needs:  Python 3.9+, standard library only.  Takes ~1-3 minutes (the Redfin
city file is ~1.1 GB and is streamed, not saved).
"""
import csv, io, json, os, sys, time, datetime, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.dirname(HERE)
OUT = os.path.join(SITE, "data", "market.json")
UA = "milliekillpack.com market-trends updater (python urllib)"

PMMS_URL = "https://www.freddiemac.com/pmms/docs/PMMS_history.csv"
RF = "https://redfin-public-data.s3.us-west-2.amazonaws.com/redfin_data_center/housing_market/monthly/"
RF_STATE, RF_COUNTY, RF_CITY = RF + "all_states.csv", RF + "all_counties.csv", RF + "all_cities.csv"
ZV = "https://files.zillowstatic.com/research/public_csvs/zhvi/{}_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv"
RDC = "https://econdata.s3-us-west-2.amazonaws.com/Reports/Core/"
RDC_STATE, RDC_COUNTY = RDC + "RDC_Inventory_Core_Metrics_State_History.csv", RDC + "RDC_Inventory_Core_Metrics_County_History.csv"

AREAS = {  # key -> how each source names it
    "lehi":   {"label": "Lehi", "redfin": "Lehi, UT", "zillow": ("city", "Lehi", "UT")},
    "county": {"label": "Utah County", "redfin": "Utah County, UT", "zillow": ("county", "Utah County", "UT"), "rdc": "49049"},
    "utah":   {"label": "Utah", "redfin": "Utah", "zillow": ("state", "Utah", None), "rdc": "UT"},
}
SOURCES = {
    "freddie": {"name": "Freddie Mac Primary Mortgage Market Survey®", "url": "https://www.freddiemac.com/pmms",
                "credit": "Source: Freddie Mac, Primary Mortgage Market Survey®.",
                "terms": "Freddie Mac: information may be used with proper attribution; not altered."},
    "redfin": {"name": "Redfin Data Center", "url": "https://www.redfin.com/news/data-center/",
               "credit": "Data provided by Redfin, a national real estate brokerage.",
               "terms": "Redfin: free to use with citation and a link to Redfin on first reference."},
    "zillow": {"name": "Zillow Research (ZHVI)", "url": "https://www.zillow.com/research/data/",
               "credit": "Data provided by Zillow Group (Zillow Home Value Index).",
               "terms": "Zillow: aggregate research data may be displayed with attribution to Zillow Group; no implied relationship."},
    "realtor": {"name": "Realtor.com® Economic Research", "url": "https://www.realtor.com/research/data/",
                "credit": "Source: Realtor.com® Economic Research.",
                "terms": "Realtor.com: attribute to Realtor.com Economic Research and link to realtor.com/research."},
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

def stream_filter(url, needle, tries=3):
    """Stream a big CSV; return header + only lines containing needle."""
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            out = []
            with urllib.request.urlopen(req, timeout=300) as r:
                header = r.readline().decode("utf-8-sig")
                for raw in r:
                    if needle in raw:
                        out.append(raw.decode("utf-8"))
            return header + "".join(out)
        except Exception as e:
            log(f"  stream failed ({i+1}/{tries}) {url}: {e}")
            time.sleep(5 * (i + 1))
    raise RuntimeError("could not stream " + url)

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

# ---------------------------------------------------------------- Redfin
RF_COLS = {
    "median_sale_price": ("MEDIAN SALE PRICE NSA ($)", 20000, 10_000_000, 0),
    "median_sale_price_yoy": ("MEDIAN SALE PRICE NSA YOY (%)", -90, 500, 1),
    "homes_sold": ("HOMES SOLD", 0, 10_000_000, 0),
    "homes_sold_yoy": ("HOMES SOLD YOY (%)", -100, 1000, 1),
    "median_dom": ("MEDIAN DAYS ON MARKET (DAYS)", 0, 1000, 0),
    "median_dom_yoy": ("MEDIAN DAYS ON MARKET YOY (DAYS)", -1000, 1000, 0),
    "inventory": ("INVENTORY", 0, 10_000_000, 0),
    "inventory_yoy": ("INVENTORY YOY (%)", -100, 1000, 1),
    "months_supply": ("MONTHS OF SUPPLY", 0, 100, 1),
    "sale_to_list": ("AVERAGE SALE TO LIST RATIO (%)", 50, 200, 1),
    "sold_above_list": ("SHARE SOLD ABOVE ORIGINAL LIST (%)", 0, 100, 1),
    "pending": ("PENDING SALES", 0, 10_000_000, 0),
    "pending_yoy": ("PENDING SALES YOY (%)", -100, 1000, 1),
}

def redfin_region(text, region_name):
    rows = [r for r in csv.DictReader(io.StringIO(text)) if r.get("REGION NAME") == region_name]
    if not rows: raise RuntimeError("Redfin: no rows for " + region_name)
    rows.sort(key=lambda r: r["PERIOD BEGIN"])
    def pick(r):
        o = {}
        for k, (col, lo, hi, nd) in RF_COLS.items():
            v = sane(num(r.get(col)), lo, hi)
            if v is not None: o[k] = rnd(v, nd)
        return o
    last = rows[-1]
    latest = pick(last)
    latest.update({"period_begin": last["PERIOD BEGIN"], "period_end": last["PERIOD END"],
                   "frequency": last["FREQUENCY"], "published": last["LAST UPDATED"]})
    series = []
    for r in rows:
        if r["PERIOD BEGIN"] < "2016-01-01": continue
        p = sane(num(r.get("MEDIAN SALE PRICE NSA ($)")), 20000, 10_000_000)
        m = sane(num(r.get("MONTHS OF SUPPLY")), 0, 100)
        d = sane(num(r.get("MEDIAN DAYS ON MARKET (DAYS)")), 0, 1000)
        series.append([r["PERIOD END"][:7], rnd(p), rnd(m, 1), rnd(d)])
    return {"latest": latest, "series": series}

def get_redfin():
    out = {}
    log("  Redfin states"); st = fetch(RF_STATE)
    out["utah"] = redfin_region(st, AREAS["utah"]["redfin"])
    log("  Redfin counties"); co = stream_filter(RF_COUNTY, b'"Utah County, UT"')
    out["county"] = redfin_region(co, AREAS["county"]["redfin"])
    log("  Redfin cities (large file, streaming)"); ci = stream_filter(RF_CITY, b'"Lehi, UT"')
    out["lehi"] = redfin_region(ci, AREAS["lehi"]["redfin"])
    return out

# ---------------------------------------------------------------- Zillow
def get_zillow():
    out = {}
    cache = {}
    for key, a in AREAS.items():
        rtype, name, st = a["zillow"]
        fname = {"city": "City", "county": "County", "state": "State"}[rtype]
        if fname not in cache:
            log(f"  Zillow {fname}")
            cache[fname] = fetch(ZV.format(fname)) if fname != "City" else stream_filter(ZV.format("City"), b",Lehi,")
        rdr = csv.DictReader(io.StringIO(cache[fname]))
        row = None
        for r in rdr:
            if r.get("RegionName") == name and (st is None or r.get("State") == st or r.get("StateName") == st):
                row = r; break
        if row is None: continue
        dates = sorted(k for k in row if len(k) == 10 and k[4] == "-" and k[7] == "-")
        pts = [(d, sane(num(row[d]), 10000, 20_000_000)) for d in dates]
        pts = [(d, v) for d, v in pts if v is not None]
        if not pts: continue
        ld, lv = pts[-1]
        val = dict(pts)
        def back(years):
            y = int(ld[:4]) - years
            cands = [d for d in val if d.startswith(f"{y}-{ld[5:7]}")]
            return val[cands[0]] if cands else None
        out[key] = {"as_of": ld[:7], "value": rnd(lv), "yoy": pct_change(lv, back(1)),
                    "chg5y": pct_change(lv, back(5)), "chg10y": pct_change(lv, back(10)),
                    "series": [[d[:7], rnd(v)] for d, v in pts if d >= f"{int(ld[:4]) - 10}-01"]}
    if not out: raise RuntimeError("Zillow: no regions found")
    return out

# ---------------------------------------------------------------- Realtor.com
def get_realtor():
    out = {}
    for key, url, idcol in (("utah", RDC_STATE, "state_id"), ("county", RDC_COUNTY, "county_fips")):
        log(f"  Realtor.com {key}")
        want = AREAS[key]["rdc"]
        rows = [r for r in csv.DictReader(io.StringIO(fetch(url))) if (r.get(idcol) or "").strip() == want]
        rows = [r for r in rows if (r.get("month_date_yyyymm") or "").isdigit()]
        if not rows: continue
        rows.sort(key=lambda r: r["month_date_yyyymm"])
        last = rows[-1]
        flag = num(last.get("quality_flag"))
        latest = {"month": f'{last["month_date_yyyymm"][:4]}-{last["month_date_yyyymm"][4:]}', "quality_flag": flag}
        for k, col, lo, hi in (("median_list_price", "median_listing_price", 20000, 20_000_000),
                               ("avg_list_price", "average_listing_price", 20000, 50_000_000),
                               ("active_listings", "active_listing_count", 0, 10_000_000),
                               ("median_dom", "median_days_on_market", 0, 1000),
                               ("price_reduced_share", "price_reduced_share", 0, 1)):
            v = sane(num(last.get(col)), lo, hi)
            if v is not None:
                latest[k] = round(v * 100, 1) if k == "price_reduced_share" else rnd(v)
        yy = sane(num(last.get("active_listing_count_yy")), -1, 50)
        if yy is not None: latest["active_listings_yoy"] = round(yy * 100, 1)
        yy = sane(num(last.get("median_listing_price_yy")), -1, 50)
        if yy is not None: latest["median_list_price_yoy"] = round(yy * 100, 1)
        series = [[f'{r["month_date_yyyymm"][:4]}-{r["month_date_yyyymm"][4:]}',
                   rnd(sane(num(r.get("active_listing_count")), 0, 10_000_000))] for r in rows]
        out[key] = {"latest": latest, "series_active": series}
    if not out: raise RuntimeError("Realtor.com: no regions found")
    return out

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
    rf, zl, fm = d.get("redfin") or {}, d.get("zillow") or {}, d.get("freddie")
    L = (rf.get("lehi") or {}).get("latest") or {}
    C = (rf.get("county") or {}).get("latest") or {}
    if L.get("median_sale_price") and L.get("median_sale_price_yoy") is not None:
        t = (f"Lehi’s median sale price was {money(L['median_sale_price'])} for homes that closed in "
             f"{span(L['period_begin'], L['period_end'])}, {updown(L['median_sale_price_yoy'])} "
             f"{abs(L['median_sale_price_yoy'])}% from a year earlier.")
        z = zl.get("lehi") or {}
        if z.get("chg10y") is not None:
            t += (f" Over the longer run, Zillow’s typical Lehi home value is {updown(z['chg10y'])} "
                  f"{abs(z['chg10y'])}% over ten years.")
        ins.append({"title": "Prices", "text": t, "sources": ["redfin", "zillow"]})
    if fm and fm.get("rate30") is not None:
        t = f"The average 30-year fixed rate was {fm['rate30']:.2f}% in Freddie Mac’s survey released {day(fm['as_of'])}"
        if fm.get("rate30_year_ago") is not None:
            diff = round(fm["rate30"] - fm["rate30_year_ago"], 2)
            t += (f", {updown(diff)} {abs(diff):.2f} points from a year earlier ({fm['rate30_year_ago']:.2f}%)"
                  if diff != 0 else f", the same as a year earlier")
        t += (f". Over the past five years it has ranged from {fm['rate30_5y_low']:.2f}% to {fm['rate30_5y_high']:.2f}%. "
              "Rates are reported weekly and can move in either direction, so a current pre-approval is the clearest "
              "way to see what today’s rate means for your budget.")
        ins.append({"title": "Mortgage rates", "text": t, "sources": ["freddie"]})
    if C.get("months_supply") is not None:
        t = f"Utah County had {C['months_supply']} months of supply in {ym(C['period_end'][:7])}"
        inv = C.get("inventory_yoy")
        if inv is not None:
            t += f", with the number of homes for sale {updown(inv)} {abs(inv)}% from a year earlier"
        t += "."
        if C.get("median_dom") is not None:
            t += f" The median home went under contract after {C['median_dom']} days on the market."
        if inv is not None and inv > 0:
            t += (" More homes to choose from can give buyers more room to negotiate, while sellers benefit "
                  "from pricing and preparing a home well from day one.")
        elif inv is not None and inv < 0:
            t += (" Fewer homes to choose from means buyers who are ready, with financing lined up, are in "
                  "the best position when the right home comes along.")
        ins.append({"title": "Supply & speed", "text": t, "sources": ["redfin"]})
    ins.append({"title": "What it means for you",
                "text": ("Every move is personal. These figures describe the whole market, not your home or your budget. "
                         "If you’re weighing a move in the next year, a short conversation about your neighborhood, "
                         "your price range and today’s rates can help you decide when the timing is right for you."),
                "sources": []})
    return ins

# ---------------------------------------------------------------- main
def main():
    prev = {}
    if os.path.exists(OUT):
        try: prev = json.load(open(OUT))
        except Exception: prev = {}
    data = {"generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "areas": {k: v["label"] for k, v in AREAS.items()}, "sources": SOURCES, "stale": []}
    for key, fn in (("freddie", get_pmms), ("redfin", get_redfin), ("zillow", get_zillow), ("realtor", get_realtor)):
        log(f"Updating {key} ...")
        try:
            data[key] = fn()
        except Exception as e:
            log(f"  !! {key} failed: {e}")
            if prev.get(key):
                data[key] = prev[key]; data["stale"].append(key)
                log("  kept previous copy (marked stale)")
    data["insights"] = build_insights(data)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f: json.dump(data, f, separators=(",", ":"))
    os.replace(tmp, OUT)
    log(f"Wrote {OUT} ({os.path.getsize(OUT)//1024} KB); stale: {data['stale'] or 'none'}")
    missing = [k for k in ("freddie", "redfin", "zillow", "realtor") if k not in data]
    if missing:
        log("Missing sources with no previous copy: " + ", ".join(missing)); sys.exit(1)

if __name__ == "__main__":
    main()
