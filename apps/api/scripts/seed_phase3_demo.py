"""Seed LOCAL DEV demo search data so the Decision engine has opportunities.

Fills facts_gsc_query_pages / facts_gsc_pages for one client using that
client's own watchlist keywords, mapped to pages that already exist in the
crawl. Synthetic numbers; never run against production.

    cd apps/api && .venv/bin/python scripts/seed_phase3_demo.py
    cd apps/api && .venv/bin/python scripts/seed_phase3_demo.py --remove

Seeded rows are tagged by country='usa' and device='DESKTOP'-free grain:
they use device='SEEDDEMO' so --remove deletes exactly them.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import create_engine, text

CLIENT_ID = "709d6241-4f61-4983-abac-1f1449ffda83"  # Absolutely Natural
SITE = "https://www.absolutely-natural.com/"
BASE = "https://absolutely-natural.com"
TAG = "SEEDDEMO"

# keyword -> (path, avg position, weekly-ish impressions)
PLAN = {
    "aromatherapy gift set": ("/collections/gifts", 8.5, 140),
    "essential oil set": ("/collections/kinsley-oils", 12.0, 220),
    "aromatherapy products": ("/collections/home-collection", 15.0, 180),
    "aromatherapy oils": ("/collections/kinsley-oils", 6.2, 260),
    "face oil for dry skin": ("/collections/face-hydration", 4.4, 300),
    "organic moisturizer": ("/collections/moisturizers", 1.9, 240),
    "face cream for dry skin": ("/collections/moisturizers", 11.0, 330),
    "lotion for dry skin": ("/collections/moisturizers", 9.0, 410),
    "anti aging skincare": ("/collections/facial-anti-aging", 7.5, 380),
    "natural skincare": ("/", 14.0, 520),
    "organic skin care products": ("/collections/organic-beauty", 5.0, 290),
    "facial serum": ("/collections/facialcare", 18.0, 350),
    "is sunscreen fsa eligible": ("/collections/fsa-hsa-eligible-products-adults", 3.4, 200),
    "natural sunscreen": ("/collections/outdoor-care", 6.0, 450),
    "reef safe sunscreen": ("/collections/outdoor-care", 10.0, 520),
    "mineral sunscreen": ("/collections/outdoor-care", 13.0, 600),
    "tanning oil": ("/collections/after-sun", 8.0, 380),
    "after sun lotion": ("/collections/after-sun", 4.0, 270),
}


def jitter(seed: str, lo: float, hi: float) -> float:
    h = int(hashlib.md5(seed.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return lo + (hi - lo) * h


def ctr_for(pos: float) -> float:
    return max(0.004, 0.32 * (0.62 ** (pos - 1)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--remove", action="store_true")
    args = ap.parse_args()

    url = os.environ.get("DATABASE_URL")
    if not url:
        for line in (Path(__file__).resolve().parents[1] / ".env").read_text().splitlines():
            if line.startswith("DATABASE_URL="):
                url = line.split("=", 1)[1].strip()
    if not url or "localhost" not in url:
        print("Refusing: DATABASE_URL must be a local DB.")
        return 1
    eng = create_engine(url)

    with eng.begin() as c:
        if args.remove:
            for t in ("facts_gsc_query_pages", "facts_gsc_pages"):
                n = c.execute(
                    text(f"delete from {t} where client_id=:c and device=:d"),
                    {"c": CLIENT_ID, "d": TAG},
                ).rowcount
                print(f"removed {n} from {t}")
            return 0

        crawled = {
            r[0]
            for r in c.execute(
                text("select normalized_url from facts_crawl_page_snapshots where client_id=:c"),
                {"c": CLIENT_ID},
            )
        }
        end = date(2026, 11, 15)
        days = [end - timedelta(days=i) for i in range(0, 106, 3)]  # ~ Aug 1 -> Nov 15
        qp_rows, page_rows = [], {}
        for kw, (path, pos, imps) in PLAN.items():
            norm = BASE + path if path != "/" else BASE + "/"
            if norm not in crawled:
                print(f"skip {kw!r}: {norm} not in crawl")
                continue
            for d in days:
                s = f"{kw}{d}"
                p = max(1.0, pos + jitter(s, -0.8, 0.8))
                i = max(3, round(imps / 4 * jitter(s + "i", 0.6, 1.4)))
                k = round(i * ctr_for(p) * jitter(s + "c", 0.8, 1.2))
                qp_rows.append(dict(
                    id=str(uuid.uuid4()), c=CLIENT_ID, d=d, q=kw, u=norm,
                    i=i, k=k, ctr=(k / i), p=round(p, 2),
                ))
                a = page_rows.setdefault((norm, d), [0, 0, 0.0, 0])
                a[0] += i; a[1] += k; a[2] += p * i
        for r in qp_rows:
            c.execute(text(
                "insert into facts_gsc_query_pages (id, client_id, date, query, raw_url,"
                " normalized_url, country, device, impressions, clicks, ctr, average_position,"
                " gsc_site_url) values (:id,:c,:d,:q,:u,:u,'usa',:dev,:i,:k,:ctr,:p,:site)"
                " on conflict do nothing"), {**r, "dev": TAG, "site": SITE})
        for (norm, d), (i, k, wp, _) in page_rows.items():
            c.execute(text(
                "insert into facts_gsc_pages (id, client_id, date, raw_url, normalized_url,"
                " country, device, impressions, clicks, ctr, average_position, gsc_site_url)"
                " values (:id,:c,:d,:u,:u,'usa',:dev,:i,:k,:ctr,:p,:site) on conflict do nothing"),
                dict(id=str(uuid.uuid4()), c=CLIENT_ID, d=d, u=norm, dev=TAG, i=i, k=k,
                     ctr=(k / i if i else 0), p=round(wp / i, 2), site=SITE))
        print(f"seeded {len(qp_rows)} query-page rows, {len(page_rows)} page rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
