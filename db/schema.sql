-- Cardo Board Canonical Schema (PostgreSQL & SQLite Compatible)

CREATE TABLE IF NOT EXISTS dim_spice (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    commodity_group TEXT,
    scientific_name TEXT,
    description TEXT,
    active BOOLEAN NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS dim_country (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    iso2 TEXT,
    iso3 TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_region (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    country_id INTEGER REFERENCES dim_country(id),
    parent_id INTEGER REFERENCES dim_region(id),
    region_type TEXT NOT NULL, -- 'STATE', 'DISTRICT', 'PROVINCE'
    name TEXT NOT NULL,
    latitude REAL,
    longitude REAL
);

CREATE TABLE IF NOT EXISTS dim_market (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    region_id INTEGER REFERENCES dim_region(id),
    latitude REAL,
    longitude REAL,
    market_type TEXT
);

CREATE TABLE IF NOT EXISTS dim_grade (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spice_id INTEGER REFERENCES dim_spice(id),
    name TEXT NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS dim_source (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization TEXT NOT NULL,
    dataset_name TEXT,
    source_url TEXT,
    source_type TEXT,
    license TEXT,
    retrieved_at TEXT NOT NULL,
    dataset_version TEXT,
    methodology_url TEXT
);

CREATE TABLE IF NOT EXISTS fact_price (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spice_id INTEGER NOT NULL REFERENCES dim_spice(id),
    date TEXT NOT NULL,
    country_id INTEGER REFERENCES dim_country(id),
    region_id INTEGER REFERENCES dim_region(id),
    market_id INTEGER REFERENCES dim_market(id),
    grade_id INTEGER REFERENCES dim_grade(id),
    seller_or_auctioneer TEXT,
    price_type TEXT NOT NULL, -- 'AUCTION', 'WHOLESALE', 'FARM_GATE'
    min_price REAL,
    max_price REAL,
    avg_price REAL NOT NULL,
    currency TEXT NOT NULL DEFAULT 'INR',
    unit TEXT NOT NULL DEFAULT 'INR/kg',
    quantity REAL, -- arrived quantity in kg
    quantity_sold REAL, -- sold quantity in kg
    quantity_unit TEXT DEFAULT 'kg',
    source_id INTEGER NOT NULL REFERENCES dim_source(id),
    source_record_id TEXT,
    quality_status TEXT NOT NULL DEFAULT 'OBSERVED'
);

CREATE TABLE IF NOT EXISTS fact_production (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spice_id INTEGER NOT NULL REFERENCES dim_spice(id),
    country_id INTEGER REFERENCES dim_country(id),
    region_id INTEGER REFERENCES dim_region(id),
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    period_granularity TEXT NOT NULL DEFAULT 'ANNUAL',
    production_value REAL, -- in metric tonnes
    production_unit TEXT DEFAULT 'tonnes',
    area_value REAL, -- in hectares
    area_unit TEXT DEFAULT 'ha',
    yield_value REAL, -- in kg/ha
    yield_unit TEXT DEFAULT 'kg/ha',
    source_id INTEGER NOT NULL REFERENCES dim_source(id),
    source_record_id TEXT,
    quality_status TEXT NOT NULL DEFAULT 'OFFICIAL_ESTIMATE'
);

CREATE TABLE IF NOT EXISTS fact_trade (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spice_id INTEGER NOT NULL REFERENCES dim_spice(id),
    flow TEXT NOT NULL, -- 'IMPORT', 'EXPORT'
    reporter_country_id INTEGER REFERENCES dim_country(id),
    partner_country_id INTEGER REFERENCES dim_country(id),
    period_start TEXT NOT NULL,
    period_granularity TEXT NOT NULL DEFAULT 'ANNUAL',
    hs_code TEXT,
    quantity REAL, -- in tonnes
    quantity_unit TEXT DEFAULT 'tonnes',
    trade_value REAL, -- in USD
    currency TEXT DEFAULT 'USD',
    unit_value_usd_per_kg REAL,
    source_id INTEGER NOT NULL REFERENCES dim_source(id),
    source_record_id TEXT,
    quality_status TEXT NOT NULL DEFAULT 'OFFICIAL_ESTIMATE'
);

CREATE TABLE IF NOT EXISTS fact_consumption (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spice_id INTEGER NOT NULL REFERENCES dim_spice(id),
    country_id INTEGER REFERENCES dim_country(id),
    year INTEGER NOT NULL,
    consumption_type TEXT NOT NULL DEFAULT 'FOOD_SUPPLY',
    quantity REAL,
    quantity_unit TEXT DEFAULT 'tonnes',
    per_capita_quantity REAL, -- kg/capita/year
    per_capita_unit TEXT DEFAULT 'kg/capita/year',
    source_id INTEGER NOT NULL REFERENCES dim_source(id),
    source_record_id TEXT,
    quality_status TEXT NOT NULL DEFAULT 'OFFICIAL_ESTIMATE'
);

CREATE TABLE IF NOT EXISTS fact_weather (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    region_id INTEGER NOT NULL REFERENCES dim_region(id),
    source_id INTEGER NOT NULL REFERENCES dim_source(id),
    rainfall_mm REAL,
    baseline_rainfall_mm REAL,
    rainfall_anomaly_mm REAL,
    tmin_c REAL,
    tmax_c REAL,
    tmean_c REAL,
    humidity_pct REAL,
    soil_moisture REAL,
    source_grid_id TEXT,
    quality_status TEXT NOT NULL DEFAULT 'OBSERVED'
);

CREATE TABLE IF NOT EXISTS raw_ingestion (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER REFERENCES dim_source(id),
    retrieved_at TEXT NOT NULL,
    object_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    content_type TEXT,
    row_count INTEGER,
    status TEXT NOT NULL,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS data_quality_run (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_name TEXT NOT NULL,
    run_started_at TEXT NOT NULL,
    run_finished_at TEXT,
    rows_read INTEGER,
    rows_loaded INTEGER,
    rows_rejected INTEGER,
    missing_dates INTEGER,
    duplicate_rows INTEGER,
    status TEXT NOT NULL,
    report_path TEXT
);

-- Indices
CREATE INDEX IF NOT EXISTS idx_price_spice_date ON fact_price(spice_id, date);
CREATE INDEX IF NOT EXISTS idx_price_region_date ON fact_price(region_id, date);
CREATE INDEX IF NOT EXISTS idx_price_market_date ON fact_price(market_id, date);
CREATE INDEX IF NOT EXISTS idx_weather_region_date ON fact_weather(region_id, date);
CREATE INDEX IF NOT EXISTS idx_production_spice_region ON fact_production(spice_id, region_id, period_start);
CREATE INDEX IF NOT EXISTS idx_trade_spice_flow ON fact_trade(spice_id, flow, period_start);
CREATE INDEX IF NOT EXISTS idx_consumption_spice_country ON fact_consumption(spice_id, country_id, year);
