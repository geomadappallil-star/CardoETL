"""
Spices Board of India - Live Daily E-Auction Scraper
Target Portal: https://www.indianspices.com/marketing/price/domestic/daily-price-small.html
Alternative Archive: https://www.indianspices.com/dailyprice-auctiondetails.html

Extracts official verified small cardamom auction prices, arrivals, sales, and auctioneer details.
"""

import re
import ssl
import urllib.request
from datetime import datetime
from typing import List, Dict, Any
from bs4 import BeautifulSoup

SPICES_BOARD_DAILY_URL = "https://www.indianspices.com/marketing/price/domestic/daily-price-small.html"

# Known market mappings for licensed e-auctioneers
AUCTIONEER_MARKET_MAP = {
    "spice more trading company": {"market_id": 3, "market_name": "Kumily", "region_id": 2},
    "idukki dist.traditional": {"market_id": 2, "market_name": "Vandanmettu", "region_id": 2},
    "cardamom planters marketing co-operative": {"market_id": 1, "market_name": "Bodinayakanur", "region_id": 6},
    "cpmc": {"market_id": 1, "market_name": "Bodinayakanur", "region_id": 6},
    "climate natural spices": {"market_id": 2, "market_name": "Vandanmettu", "region_id": 2},
    "sugandhagiri spices": {"market_id": 1, "market_name": "Bodinayakanur", "region_id": 6},
    "south indian cardamom online": {"market_id": 2, "market_name": "Vandanmettu", "region_id": 2},
    "cardamom growersforever": {"market_id": 1, "market_name": "Bodinayakanur", "region_id": 6},
    "speciality indian food parks": {"market_id": 2, "market_name": "Vandanmettu", "region_id": 2},
    "rns spices": {"market_id": 1, "market_name": "Bodinayakanur", "region_id": 6},
    "idukki mahila cardamom": {"market_id": 2, "market_name": "Vandanmettu", "region_id": 2},
    "green house cardamom": {"market_id": 1, "market_name": "Bodinayakanur", "region_id": 6},
    "mas enterprises": {"market_id": 2, "market_name": "Vandanmettu", "region_id": 2},
    "south indian green cardamom": {"market_id": 2, "market_name": "Vandanmettu", "region_id": 2},
    "sigc": {"market_id": 2, "market_name": "Vandanmettu", "region_id": 2},
    "spice planters consortium": {"market_id": 1, "market_name": "Bodinayakanur", "region_id": 6},
    "spcl": {"market_id": 1, "market_name": "Bodinayakanur", "region_id": 6},
}

def resolve_market(auctioneer_name: str) -> Dict[str, Any]:
    clean = auctioneer_name.lower()
    for key, val in AUCTIONEER_MARKET_MAP.items():
        if key in clean:
            return val
    if "bodinayakanur" in clean or "theni" in clean:
        return {"market_id": 1, "market_name": "Bodinayakanur", "region_id": 6}
    return {"market_id": 2, "market_name": "Vandanmettu", "region_id": 2}


def parse_spices_board_date(date_str: str) -> str:
    """Converts strings like '23-Sep-2026' or '23/09/2026' to 'YYYY-MM-DD'"""
    date_str = date_str.strip()
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return date_str


def parse_number(val: str, default: float = 0.0) -> float:
    if not val:
        return default
    cleaned = re.sub(r"[^\d.]", "", val)
    try:
        return float(cleaned)
    except ValueError:
        return default


def scrape_spices_board_auctions() -> List[Dict[str, Any]]:
    """
    Scrapes the official Spices Board daily small cardamom auction table.
    Returns list of parsed records formatted for fact_price.
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(
        SPICES_BOARD_DAILY_URL,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    )

    with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
        html = resp.read().decode("utf-8", errors="ignore")

    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        raise ValueError("No tables found on Spices Board daily price page.")

    target_table = tables[0]
    for tbl in tables:
        if "Auctioneer" in tbl.get_text():
            target_table = tbl
            break

    records = []
    rows = target_table.find_all("tr")
    header_col_indices = {}

    for row in rows:
        th_cells = row.find_all("th")
        if th_cells:
            for idx, th in enumerate(th_cells):
                txt = th.get_text(strip=True).lower()
                if "date" in txt:
                    header_col_indices["date"] = idx
                elif "auctioneer" in txt:
                    header_col_indices["auctioneer"] = idx
                elif "lots" in txt:
                    header_col_indices["lots"] = idx
                elif "arrived" in txt:
                    header_col_indices["arrived"] = idx
                elif "sold" in txt:
                    header_col_indices["sold"] = idx
                elif "max" in txt:
                    header_col_indices["max"] = idx
                elif "min" in txt:
                    header_col_indices["min"] = idx
                elif "avg" in txt:
                    header_col_indices["avg"] = idx
            continue

        td_cells = row.find_all("td")
        if len(td_cells) < 7:
            continue

        d_idx = header_col_indices.get("date", 1)
        a_idx = header_col_indices.get("auctioneer", 2)
        arr_idx = header_col_indices.get("arrived", 4)
        sold_idx = header_col_indices.get("sold", 5)
        max_idx = header_col_indices.get("max", 6)
        min_idx = header_col_indices.get("min", 7)
        avg_idx = header_col_indices.get("avg", 8)

        raw_date = td_cells[d_idx].get_text(strip=True) if d_idx < len(td_cells) else ""
        raw_auctioneer = td_cells[a_idx].get_text(strip=True) if a_idx < len(td_cells) else ""
        if not raw_date or not raw_auctioneer or "Date" in raw_date:
            continue

        iso_date = parse_spices_board_date(raw_date)
        market_info = resolve_market(raw_auctioneer)

        arrived_kg = parse_number(td_cells[arr_idx].get_text(strip=True)) if arr_idx < len(td_cells) else 0.0
        sold_kg = parse_number(td_cells[sold_idx].get_text(strip=True)) if sold_idx < len(td_cells) else 0.0
        max_price = parse_number(td_cells[max_idx].get_text(strip=True)) if max_idx < len(td_cells) else 0.0
        min_price = parse_number(td_cells[min_idx].get_text(strip=True)) if min_idx < len(td_cells) else 0.0
        avg_price = parse_number(td_cells[avg_idx].get_text(strip=True)) if avg_idx < len(td_cells) else 0.0

        if avg_price <= 0:
            continue

        record_id_slug = re.sub(r"[^A-Za-z0-9]", "", raw_auctioneer[:10]).upper()
        records.append({
            "spice_code": "small_cardamom",
            "date": iso_date,
            "seller_or_auctioneer": raw_auctioneer,
            "market_id": market_info["market_id"],
            "market_name": market_info["market_name"],
            "price_type": "AUCTION",
            "min_price": min_price,
            "max_price": max_price,
            "avg_price": avg_price,
            "currency": "INR",
            "unit": "INR/kg",
            "quantity": arrived_kg,
            "quantity_sold": sold_kg,
            "quantity_unit": "kg",
            "source_id": 1,
            "source_record_id": f"SB-AUCTION-{iso_date.replace('-', '')}-{record_id_slug}",
            "quality_status": "VERIFIED"
        })

    return records
