# CardoETL — Spice Intelligence Data Pipeline

Python-based ETL pipeline for **Cardo Board**. Ingests, validates, and loads historical spice intelligence data for **Small Cardamom, Black Pepper, Nutmeg, and Cloves** (2016-01-01 to 2026-09-15).

## Data Sources
- **Spices Board of India**: Certified e-auctions & market spot terminals
- **ECMWF ERA5-Land & IMD**: Idukki daily weather & 1991–2020 baseline climatology
- **Directorate of Economics & Statistics (DES India)**: Area, Production, Yield
- **FAOSTAT & UN Comtrade**: Global production & bilateral trade flows

## How to Run
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run full pipeline (Extract, Validate, Load)
python3 run.py --all
```

## Loading into Supabase / PostgreSQL
Set `DATABASE_URL` environment variable:
```bash
export DATABASE_URL="postgresql://postgres:[PASSWORD]@db.thgczdlokjrxzakncgwd.supabase.co:5432/postgres"
python3 run.py --all
```
