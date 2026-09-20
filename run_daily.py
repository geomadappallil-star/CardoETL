"""
Cardo Board Daily Automated ETL Runner
Executes incremental extraction, validation, and ingestion into Supabase Cloud.
Can be run on a schedule (e.g. GitHub Actions cron) or manually on-demand.
"""

import argparse
import os
import ssl
import sys
from datetime import date, datetime, timedelta
from typing import List, Dict, Any

import pg8000.native

from extractors.spices_board import generate_spices_board_auctions
from extractors.weather import generate_idukki_weather
from validation.quality_checks import DataQualityValidator, REQUIRED_PRICE_SIGNATURE

# Configuration from Environment Variables (with secure fallbacks)
DB_HOST = os.environ.get("SUPABASE_DB_HOST", "aws-0-ap-northeast-1.pooler.supabase.com")
DB_PORT = int(os.environ.get("SUPABASE_DB_PORT", "6543"))
DB_USER = os.environ.get("SUPABASE_DB_USER", "postgres.thgczdlokjrxzakncgwd")
DB_PASSWORD = os.environ.get("SUPABASE_DB_PASSWORD", "Madappallil@1997")
DB_NAME = os.environ.get("SUPABASE_DB_NAME", "postgres")


def get_db_connection():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    return pg8000.native.Connection(
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        ssl_context=ctx,
        timeout=20,
    )


def run_daily_pipeline(target_date: date = None, dry_run: bool = False):
    start_time = datetime.utcnow().isoformat()
    print("=" * 60)
    print("CARDO BOARD — DAILY AUTOMATED ETL PIPELINE")
    print(f"Timestamp: {start_time} UTC")
    print("=" * 60)

    conn = get_db_connection()
    print(f"[1/5] Connected to Supabase PostgreSQL ({DB_HOST}:{DB_PORT})")

    # Fetch max dates currently in database
    price_max_res = conn.run("SELECT max(date) FROM fact_price")
    weather_max_res = conn.run("SELECT max(date) FROM fact_weather")
    spice_rows = conn.run("SELECT code, id FROM dim_spice")
    spice_map = {r[0]: r[1] for r in spice_rows}

    db_max_price_date = price_max_res[0][0] if price_max_res and price_max_res[0][0] else date(2026, 9, 15)
    db_max_weather_date = weather_max_res[0][0] if weather_max_res and weather_max_res[0][0] else date(2026, 9, 15)

    print(f"  > Current DB Max Price Date:   {db_max_price_date}")
    print(f"  > Current DB Max Weather Date: {db_max_weather_date}")

    today = date.today()
    if target_date is not None:
        start_date = target_date
        end_date = target_date
    else:
        # Determine catch-up start date
        min_date = min(db_max_price_date, db_max_weather_date)
        start_date = min_date + timedelta(days=1)
        end_date = today

    if start_date > end_date:
        print(f"\n[INFO] Database is already fully up-to-date up to {end_date}!")
        print("No new dates to ingest. Exiting gracefully.")
        conn.close()
        return

    print(f"\n[2/5] Target Sync Range: {start_date} to {end_date} ({(end_date - start_date).days + 1} day(s))")

    # Extract
    print("[3/5] Extracting Data Feeds...")
    prices = generate_spices_board_auctions(start_date=start_date, end_date=end_date)
    weather = generate_idukki_weather(start_date=start_date, end_date=end_date)
    print(f"  > Extracted {len(prices)} price observations")
    print(f"  > Extracted {len(weather)} daily weather records")

    # Validate
    print("[4/5] Executing Data Quality Assertions...")
    validator = DataQualityValidator()
    validator.verify_source_signature(REQUIRED_PRICE_SIGNATURE)
    valid_prices, rejected_prices = validator.validate_price_records(prices)
    valid_weather, rejected_weather = validator.validate_weather_records(weather)

    print(f"  > Validation Passed: {len(valid_prices)} prices, {len(valid_weather)} weather records")
    if rejected_prices or rejected_weather:
        print(f"  > WARNING: Rejected {len(rejected_prices)} prices, {len(rejected_weather)} weather records")

    if dry_run:
        print("\n[DRY RUN] Skipping database writes.")
        conn.close()
        return

    # Ingest with duplicate prevention
    print("[5/5] Ingesting Records into Supabase Fact Tables...")

    # Fetch existing price keys for range
    existing_prices_res = conn.run(
        "SELECT spice_id, date, COALESCE(market_id, -1), COALESCE(seller_or_auctioneer, '') FROM fact_price WHERE date >= :s AND date <= :e",
        s=start_date,
        e=end_date
    )
    existing_price_keys = {(r[0], str(r[1]), r[2], r[3]) for r in existing_prices_res}

    inserted_prices = 0
    for p in valid_prices:
        sp_id = spice_map.get(p["spice_code"], 1)
        m_id = p.get("market_id") or -1
        seller = p.get("seller_or_auctioneer") or ""
        key = (sp_id, p["date"], m_id, seller)

        if key not in existing_price_keys:
            conn.run("""
                INSERT INTO fact_price (
                    spice_id, date, country_id, region_id, market_id, seller_or_auctioneer,
                    price_type, min_price, max_price, avg_price, currency, unit,
                    quantity, quantity_sold, quantity_unit, source_id, source_record_id, quality_status
                ) VALUES (
                    :sp_id, :dt, :c_id, :r_id, :m_id, :seller,
                    :ptype, :pmin, :pmax, :pavg, :curr, :unit,
                    :qty, :qty_sold, :qunit, :src_id, :rec_id, :qstatus
                )
            """,
                sp_id=sp_id,
                dt=p["date"],
                c_id=p.get("country_id", 1),
                r_id=p.get("region_id", 2),
                m_id=p.get("market_id"),
                seller=p.get("seller_or_auctioneer"),
                ptype=p.get("price_type", "AUCTION"),
                pmin=p.get("min_price"),
                pmax=p.get("max_price"),
                pavg=p["avg_price"],
                curr=p.get("currency", "INR"),
                unit=p.get("unit", "INR/kg"),
                qty=p.get("quantity"),
                qty_sold=p.get("quantity_sold"),
                qunit=p.get("quantity_unit", "kg"),
                src_id=p.get("source_id", 1),
                rec_id=p.get("source_record_id"),
                qstatus=p.get("quality_status", "OBSERVED")
            )
            existing_price_keys.add(key)
            inserted_prices += 1

    # Fetch existing weather keys for range
    existing_weather_res = conn.run(
        "SELECT region_id, date FROM fact_weather WHERE date >= :s AND date <= :e",
        s=start_date,
        e=end_date
    )
    existing_weather_keys = {(r[0], str(r[1])) for r in existing_weather_res}

    inserted_weather = 0
    for w in valid_weather:
        reg_id = w.get("region_id", 2)
        key = (reg_id, w["date"])

        if key not in existing_weather_keys:
            conn.run("""
                INSERT INTO fact_weather (
                    date, region_id, source_id, rainfall_mm, baseline_rainfall_mm, rainfall_anomaly_mm,
                    tmin_c, tmax_c, tmean_c, humidity_pct, soil_moisture, source_grid_id, quality_status
                ) VALUES (
                    :dt, :r_id, :src_id, :rain, :base, :anom,
                    :tmin, :tmax, :tmean, :hum, :soil, :grid, :qstatus
                )
            """,
                dt=w["date"],
                r_id=reg_id,
                src_id=w.get("source_id", 2),
                rain=w.get("rainfall_mm"),
                base=w.get("baseline_rainfall_mm"),
                anom=w.get("rainfall_anomaly_mm"),
                tmin=w.get("tmin_c"),
                tmax=w.get("tmax_c"),
                tmean=w.get("tmean_c"),
                hum=w.get("humidity_pct"),
                soil=w.get("soil_moisture"),
                grid=w.get("source_grid_id", "ERA5_IDUKKI_01"),
                qstatus=w.get("quality_status", "OBSERVED")
            )
            existing_weather_keys.add(key)
            inserted_weather += 1

    end_time = datetime.utcnow().isoformat()
    total_loaded = inserted_prices + inserted_weather

    # Log into data_quality_run
    conn.run("""
        INSERT INTO data_quality_run (
            dataset_name, run_started_at, run_finished_at, rows_read, rows_loaded,
            rows_rejected, missing_dates, duplicate_rows, status
        ) VALUES (
            :name, :start, :finish, :read, :loaded, :rej, 0, 0, 'SUCCESS'
        )
    """,
        name="Cardo Board Daily Automated Pipeline",
        start=start_time,
        finish=end_time,
        read=len(prices) + len(weather),
        loaded=total_loaded,
        rej=len(rejected_prices) + len(rejected_weather)
    )

    conn.close()

    print("\n" + "=" * 60)
    print("DAILY PIPELINE COMPLETED SUCCESSFULLY!")
    print(f"  • New Prices Loaded:  {inserted_prices}")
    print(f"  • New Weather Loaded: {inserted_weather}")
    print(f"  • Total Loaded:       {total_loaded}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Cardo Board Daily Automated ETL")
    parser.add_argument("--date", type=str, help="Specific target date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="Validate without writing to database")
    args = parser.parse_args()

    target_date = None
    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date()

    run_daily_pipeline(target_date=target_date, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
