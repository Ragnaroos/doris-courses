#!/usr/bin/env python3
"""Generate the synthetic storefront events used by the AI Integrations course.

Usage (from the course directory):
    python datasets/generate_events.py

The script rewrites datasets/events.csv. The output depends only on the seed
below: it uses Random.random() and Random.randrange(), whose results for a
given seed are the same on every supported Python version. After a change,
update the numbers in datasets/events.yaml and in the lesson; the tests
compare them with the CSV file.

Each shopper has a few sessions during March 2026. A session views some
products, sometimes adds one to the cart, and sometimes buys it. Purchases
carry the product's price as revenue; other events carry 0.00.
"""

from __future__ import annotations

import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

OUTPUT = Path(__file__).with_name("events.csv")
SEED = 20260301
START = datetime(2026, 3, 1)
DAYS = 31
SHOPPERS = 800
FIRST_SHOPPER_ID = 50001
PRODUCTS = 200
FIRST_PRODUCT_ID = 1001
# Region and the cumulative share of shoppers up to and including it.
REGIONS = (("US", 0.35), ("EU", 0.65), ("APAC", 0.90), ("LATAM", 1.0))
COLUMNS = ("event_time", "event_id", "user_id", "event_type", "region", "product_id", "revenue")


def pick_region(rng: random.Random) -> str:
    draw = rng.random()
    return next(region for region, share in REGIONS if draw < share)


def generate() -> list[tuple]:
    rng = random.Random(SEED)
    prices = {
        FIRST_PRODUCT_ID + offset: (500 + rng.randrange(29500)) / 100
        for offset in range(PRODUCTS)
    }
    product_ids = sorted(prices)
    events = []
    for user_id in range(FIRST_SHOPPER_ID, FIRST_SHOPPER_ID + SHOPPERS):
        region = pick_region(rng)
        for _session in range(1 + rng.randrange(6)):
            moment = START + timedelta(seconds=rng.randrange(DAYS * 86400 - 3600))
            viewed = [product_ids[rng.randrange(PRODUCTS)] for _ in range(1 + rng.randrange(8))]
            for product_id in viewed:
                events.append((moment, user_id, "view", region, product_id, 0.0))
                moment += timedelta(seconds=5 + rng.randrange(120))
            if rng.random() < 0.35:
                product_id = viewed[rng.randrange(len(viewed))]
                events.append((moment, user_id, "cart", region, product_id, 0.0))
                moment += timedelta(seconds=10 + rng.randrange(300))
                if rng.random() < 0.45:
                    events.append((moment, user_id, "purchase", region, product_id, prices[product_id]))
    events.sort(key=lambda event: (event[0], event[1]))
    return [
        (moment.strftime("%Y-%m-%d %H:%M:%S"), event_id, user_id, event_type, region, product_id,
         f"{revenue:.2f}")
        for event_id, (moment, user_id, event_type, region, product_id, revenue)
        in enumerate(events, start=1)
    ]


def main() -> None:
    rows = generate()
    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(COLUMNS)
        writer.writerows(rows)
    print(f"Wrote {len(rows):,} events to {OUTPUT}")


if __name__ == "__main__":
    main()
