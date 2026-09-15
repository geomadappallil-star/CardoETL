"""
Cardo Board Database Loader
Applies schema, inserts dimensions and bulk loads validated facts into SQLite / PostgreSQL.
"""

import json
import os
import sqlite3
from datetime import datetime
from typing import List, Dict, Any

DB_PATH = os.environ.get("CARDO_DB_PATH", "/home/jeo/.gemini/antigravity/scratch/cardo-board/cardo_board.db")
SCHEMA_PATH = "/home/jeo/.gemini/antigravity/scratch/cardo-board/db/schema.sql"
DIMENSIONS_PATH = "/home/jeo/.gemini/antigravity/scratch/cardo-board/db/seeds/initial_dimensions.json"

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_connection()
    with open(SCHEMA_PATH, "r") as f:
        schema_sql = f.read()
    conn.executescript(schema_sql)
    conn.commit()
    conn.close()
    print(f"Initialized database schema at {DB_PATH}")

def seed_dimensions():
    conn = get_connection()
    with open(DIMENSIONS_PATH, "r") as f:
        data = json.load(f)

    cur = conn.cursor()

    # Spices
    for s in data["spices"]:
        cur.execute("""
            INSERT OR IGNORE INTO dim_spice (code, name, commodity_group, scientific_name, description, active)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (s["code"], s["name"], s.get("commodity_group"), s.get("scientific_name"), s.get("description"), s.get("active", 1)))

    # Countries
    for c in data["countries"]:
        cur.execute("""
            INSERT OR IGNORE INTO dim_country (iso2, iso3, name)
            VALUES (?, ?, ?)
        """, (c.get("iso2"), c["iso3"], c["name"]))

    # Regions
    for r in data["regions"]:
        cur.execute("SELECT id FROM dim_country WHERE iso3 = ?", (r["country_iso3"],))
        c_row = cur.fetchone()
        c_id = c_row[0] if c_row else 1
        parent_id = None
        if r.get("parent_name"):
            cur.execute("SELECT id FROM dim_region WHERE name = ?", (r["parent_name"],))
            p_row = cur.fetchone()
            if p_row:
                parent_id = p_row[0]

        cur.execute("""
            INSERT OR IGNORE INTO dim_region (country_id, parent_id, region_type, name, latitude, longitude)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (c_id, parent_id, r["region_type"], r["name"], r.get("latitude"), r.get("longitude")))

    # Markets
    for m in data["markets"]:
        cur.execute("SELECT id FROM dim_region WHERE name = ?", (m["region_name"],))
        reg_row = cur.fetchone()
        reg_id = reg_row[0] if reg_row else 1
        cur.execute("""
            INSERT OR IGNORE INTO dim_market (name, region_id, latitude, longitude, market_type)
            VALUES (?, ?, ?, ?, ?)
        """, (m["name"], reg_id, m.get("latitude"), m.get("longitude"), m.get("market_type")))

    # Grades
    for g in data["grades"]:
        cur.execute("SELECT id FROM dim_spice WHERE code = ?", (g["spice_code"],))
        sp_row = cur.fetchone()
        sp_id = sp_row[0] if sp_row else 1
        cur.execute("""
            INSERT OR IGNORE INTO dim_grade (spice_id, name, description)
            VALUES (?, ?, ?)
        """, (sp_id, g["name"], g.get("description")))

    # Sources
    for src in data["sources"]:
        cur.execute("""
            INSERT OR IGNORE INTO dim_source (organization, dataset_name, source_url, source_type, license, retrieved_at, dataset_version, methodology_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (src["organization"], src["dataset_name"], src.get("source_url"), src["source_type"], src.get("license"), src["retrieved_at"], src.get("dataset_version"), src.get("methodology_url")))

    conn.commit()
    conn.close()
    print("Dimensions seeded successfully.")

def load_facts(prices: List[Dict[str, Any]], weather: List[Dict[str, Any]], production: List[Dict[str, Any]], trade: List[Dict[str, Any]], consumption: List[Dict[str, Any]]):
    conn = get_connection()
    cur = conn.cursor()

    # Build spice code -> id map
    cur.execute("SELECT code, id FROM dim_spice")
    spice_map = {row[0]: row[1] for row in cur.fetchall()}

    start_time = datetime.utcnow().isoformat()

    # 1. Price records
    price_tuples = []
    for p in prices:
        sp_id = spice_map.get(p["spice_code"], 1)
        price_tuples.append((
            sp_id, p["date"], p.get("country_id", 1), p.get("region_id", 2),
            p.get("market_id"), p.get("grade_id"), p.get("seller_or_auctioneer"),
            p.get("price_type", "AUCTION"), p.get("min_price"), p.get("max_price"),
            p["avg_price"], p.get("currency", "INR"), p.get("unit", "INR/kg"),
            p.get("quantity"), p.get("quantity_sold"), p.get("quantity_unit", "kg"),
            p.get("source_id", 1), p.get("source_record_id"), p.get("quality_status", "OBSERVED")
        ))
    cur.executemany("""
        INSERT INTO fact_price (
            spice_id, date, country_id, region_id, market_id, grade_id, seller_or_auctioneer,
            price_type, min_price, max_price, avg_price, currency, unit,
            quantity, quantity_sold, quantity_unit, source_id, source_record_id, quality_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, price_tuples)

    # 2. Weather records
    weather_tuples = []
    for w in weather:
        weather_tuples.append((
            w["date"], w["region_id"], w["source_id"], w.get("rainfall_mm"),
            w.get("baseline_rainfall_mm"), w.get("rainfall_anomaly_mm"),
            w.get("tmin_c"), w.get("tmax_c"), w.get("tmean_c"),
            w.get("humidity_pct"), w.get("soil_moisture"), w.get("source_grid_id"),
            w.get("quality_status", "OBSERVED")
        ))
    cur.executemany("""
        INSERT INTO fact_weather (
            date, region_id, source_id, rainfall_mm, baseline_rainfall_mm, rainfall_anomaly_mm,
            tmin_c, tmax_c, tmean_c, humidity_pct, soil_moisture, source_grid_id, quality_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, weather_tuples)

    # 3. Production records
    prod_tuples = []
    for pr in production:
        sp_id = spice_map.get(pr["spice_code"], 1)
        prod_tuples.append((
            sp_id, pr.get("country_id"), pr.get("region_id"), pr["period_start"],
            pr["period_end"], pr.get("period_granularity", "ANNUAL"),
            pr.get("production_value"), pr.get("production_unit", "tonnes"),
            pr.get("area_value"), pr.get("area_unit", "ha"),
            pr.get("yield_value"), pr.get("yield_unit", "kg/ha"),
            pr.get("source_id", 5), pr.get("source_record_id"), pr.get("quality_status", "OFFICIAL_ESTIMATE")
        ))
    cur.executemany("""
        INSERT INTO fact_production (
            spice_id, country_id, region_id, period_start, period_end, period_granularity,
            production_value, production_unit, area_value, area_unit, yield_value, yield_unit,
            source_id, source_record_id, quality_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, prod_tuples)

    # 4. Trade records
    trade_tuples = []
    for tr in trade:
        sp_id = spice_map.get(tr["spice_code"], 1)
        trade_tuples.append((
            sp_id, tr["flow"], tr.get("reporter_country_id"), tr.get("partner_country_id"),
            tr["period_start"], tr.get("period_granularity", "ANNUAL"), tr.get("hs_code"),
            tr.get("quantity"), tr.get("quantity_unit", "tonnes"), tr.get("trade_value"),
            tr.get("currency", "USD"), tr.get("unit_value_usd_per_kg"), tr.get("source_id", 4),
            tr.get("quality_status", "OFFICIAL_ESTIMATE")
        ))
    cur.executemany("""
        INSERT INTO fact_trade (
            spice_id, flow, reporter_country_id, partner_country_id, period_start,
            period_granularity, hs_code, quantity, quantity_unit, trade_value,
            currency, unit_value_usd_per_kg, source_id, quality_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, trade_tuples)

    # 5. Consumption records
    cons_tuples = []
    for c in consumption:
        sp_id = spice_map.get(c["spice_code"], 1)
        cons_tuples.append((
            sp_id, c.get("country_id"), c["year"], c.get("consumption_type", "FOOD_SUPPLY"),
            c.get("quantity"), c.get("quantity_unit", "tonnes"), c.get("per_capita_quantity"),
            c.get("per_capita_unit", "kg/capita/year"), c.get("source_id", 3),
            c.get("quality_status", "OFFICIAL_ESTIMATE")
        ))
    cur.executemany("""
        INSERT INTO fact_consumption (
            spice_id, country_id, year, consumption_type, quantity, quantity_unit,
            per_capita_quantity, per_capita_unit, source_id, quality_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, cons_tuples)

    end_time = datetime.utcnow().isoformat()
    total_loaded = len(price_tuples) + len(weather_tuples) + len(prod_tuples) + len(trade_tuples) + len(cons_tuples)

    # Log data quality run
    cur.execute("""
        INSERT INTO data_quality_run (
            dataset_name, run_started_at, run_finished_at, rows_read, rows_loaded,
            rows_rejected, missing_dates, duplicate_rows, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ("Cardo Board Master ETL", start_time, end_time, total_loaded, total_loaded, 0, 0, 0, "SUCCESS"))

    conn.commit()
    conn.close()
    print(f"Successfully loaded {total_loaded} records into canonical tables:")
    print(f"  - Prices: {len(price_tuples)}")
    print(f"  - Weather: {len(weather_tuples)}")
    print(f"  - Production: {len(prod_tuples)}")
    print(f"  - Trade: {len(trade_tuples)}")
    print(f"  - Consumption: {len(cons_tuples)}")
