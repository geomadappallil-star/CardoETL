"""
Cardo Board Master ETL Runner
Coordinates extraction, validation, and loading into canonical database.
"""

import argparse
import os
import sys
from extractors.spices_board import generate_spices_board_auctions
from extractors.weather import generate_idukki_weather
from extractors.production import generate_production_data
from extractors.trade_consumption import generate_trade_and_consumption_data
from validation.quality_checks import DataQualityValidator, REQUIRED_PRICE_SIGNATURE
from loaders.db_loader import init_db, seed_dimensions, load_facts

def main():
    parser = argparse.ArgumentParser(description="Cardo Board ETL Pipeline")
    parser.add_argument("--all", action="store_true", help="Run full pipeline: schema, seeds, extract, validate, load")
    parser.add_argument("--extract", action="store_true", help="Extract raw datasets")
    parser.add_argument("--validate", action="store_true", help="Validate datasets")
    parser.add_argument("--load", action="store_true", help="Load into database")
    args = parser.parse_args()

    run_all = args.all or (not args.extract and not args.validate and not args.load)

    print("=" * 60)
    print("CARDO BOARD - SPICE INTELLIGENCE PIPELINE")
    print("=" * 60)

    # 1. Init DB & Seeds
    if run_all or args.load:
        print("\n[STEP 1/4] Initializing Database & Seeding Dimensions...")
        init_db()
        seed_dimensions()

    # 2. Extract
    print("\n[STEP 2/4] Extracting Data Sources (2016-01-01 to 2026-09-15)...")
    prices = generate_spices_board_auctions()
    print(f"  > Extracted {len(prices)} price observations (Spices Board Auctions & Spot)")

    weather = generate_idukki_weather()
    print(f"  > Extracted {len(weather)} daily weather observations (ERA5-Land Idukki)")

    production = generate_production_data()
    print(f"  > Extracted {len(production)} production/area/yield records (DES & FAOSTAT)")

    trade, consumption = generate_trade_and_consumption_data()
    print(f"  > Extracted {len(trade)} trade flow records and {len(consumption)} consumption records")

    # 3. Validate
    print("\n[STEP 3/4] Validating Quality & Signatures...")
    validator = DataQualityValidator()
    validator.verify_source_signature(REQUIRED_PRICE_SIGNATURE)
    valid_prices, rejected_prices = validator.validate_price_records(prices)
    valid_weather, rejected_weather = validator.validate_weather_records(weather)

    print(f"  > Quality Summary: {validator.stats['rows_loaded']} passed, {validator.stats['rows_rejected']} rejected")
    if validator.stats["rows_rejected"] > 0:
        print(f"  > WARNING: Quarantined {validator.stats['rows_rejected']} rejected records.")
    else:
        print("  > All assertions PASSED: non-negative prices, valid spreads, no duplicate keys.")

    # 4. Load
    if run_all or args.load:
        print("\n[STEP 4/4] Loading into Canonical Fact Tables...")
        load_facts(valid_prices, valid_weather, production, trade, consumption)

    print("\nETL Pipeline completed successfully!")
    print("=" * 60)

if __name__ == "__main__":
    main()
