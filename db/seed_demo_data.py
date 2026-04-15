"""
Seed script for demo SQLite database.
Creates realistic synthetic data with intentional patterns:
- A signup dip in the last week
- Mobile performing worse than desktop
- Italy leading, followed by Germany
- Orders loosely correlated with signups
"""

import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "demo.db"

random.seed(42)  # Reproducible data


def create_schema(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS fact_signups")
    cursor.execute("DROP TABLE IF EXISTS fact_orders")
    cursor.execute("DROP TABLE IF EXISTS dim_country")
    cursor.execute("DROP TABLE IF EXISTS dim_device")

    cursor.execute("""
        CREATE TABLE dim_country (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE dim_device (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE fact_signups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            country_id INTEGER NOT NULL,
            device_id INTEGER NOT NULL,
            signups INTEGER NOT NULL,
            FOREIGN KEY(country_id) REFERENCES dim_country(id),
            FOREIGN KEY(device_id) REFERENCES dim_device(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE fact_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            country_id INTEGER NOT NULL,
            device_id INTEGER NOT NULL,
            orders INTEGER NOT NULL,
            revenue REAL NOT NULL,
            FOREIGN KEY(country_id) REFERENCES dim_country(id),
            FOREIGN KEY(device_id) REFERENCES dim_device(id)
        )
    """)
    conn.commit()


def seed_dimensions(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()
    countries = [(1, "Italia"), (2, "Germania"), (3, "Francia"), (4, "USA")]
    devices = [(1, "mobile"), (2, "desktop")]
    cursor.executemany("INSERT INTO dim_country(id, name) VALUES (?, ?)", countries)
    cursor.executemany("INSERT INTO dim_device(id, name) VALUES (?, ?)", devices)
    conn.commit()


def seed_facts(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()
    start_date = date.today() - timedelta(days=27)

    # Base signups per country (Italia highest)
    country_base = {1: 150, 2: 120, 3: 100, 4: 80}
    # Device multiplier (desktop > mobile)
    device_mult = {1: 0.7, 2: 1.0}  # 1=mobile, 2=desktop
    # Price per order by country
    country_price = {1: 55.0, 2: 60.0, 3: 50.0, 4: 65.0}

    for day_offset in range(28):
        current_date = (start_date + timedelta(days=day_offset)).isoformat()
        days_from_end = 27 - day_offset

        # Create a dip in the last 7 days
        if days_from_end < 7:
            dip_factor = 0.65 + (days_from_end / 7) * 0.15  # 65%-80%
        else:
            dip_factor = 1.0 + random.uniform(-0.05, 0.05)

        for country_id in [1, 2, 3, 4]:
            for device_id in [1, 2]:
                base = country_base[country_id]
                mult = device_mult[device_id]

                # Signups with noise and dip
                signups = int(
                    base * mult * dip_factor
                    + random.randint(-10, 10)
                )
                signups = max(0, signups)

                # Orders: ~40% conversion with some noise
                orders = int(signups * 0.4 + random.randint(-5, 5))
                orders = max(0, orders)

                # Revenue
                price = country_price[country_id] + random.uniform(-5, 5)
                revenue = round(orders * price, 2)

                cursor.execute(
                    "INSERT INTO fact_signups(date, country_id, device_id, signups) "
                    "VALUES (?, ?, ?, ?)",
                    (current_date, country_id, device_id, signups),
                )
                cursor.execute(
                    "INSERT INTO fact_orders(date, country_id, device_id, orders, revenue) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (current_date, country_id, device_id, orders, revenue),
                )

    conn.commit()


def main():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        create_schema(conn)
        seed_dimensions(conn)
        seed_facts(conn)

        # Verify
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM fact_signups")
        signup_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM fact_orders")
        order_count = cursor.fetchone()[0]
        cursor.execute("SELECT MIN(date), MAX(date) FROM fact_signups")
        date_range = cursor.fetchone()

        print(f"Database demo creato: {DB_PATH}")
        print(f"  fact_signups: {signup_count} righe")
        print(f"  fact_orders:  {order_count} righe")
        print(f"  Intervallo:   {date_range[0]} -> {date_range[1]}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
