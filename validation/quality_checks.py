"""
Cardo Board Data Quality and Validation Engine
Enforces:
- Schema signature check
- Non-negative assertions (price, quantity, rainfall)
- Spread logic (min_price <= max_price, quantity_sold <= quantity_arrived)
- Quarantining rejected records without silent dropping
"""

import sys
from typing import List, Dict, Any, Tuple

REQUIRED_PRICE_SIGNATURE = "date|auctioneer|lots|arrived|sold|min|max|avg"

class DataQualityValidator:
    def __init__(self):
        self.rejected_records: List[Dict[str, Any]] = []
        self.stats = {
            "rows_read": 0,
            "rows_loaded": 0,
            "rows_rejected": 0,
            "negative_price_count": 0,
            "invalid_spread_count": 0,
            "invalid_quantity_count": 0,
            "duplicate_count": 0,
        }

    def verify_source_signature(self, signature: str, expected: str = REQUIRED_PRICE_SIGNATURE) -> bool:
        if signature != expected:
            raise ValueError(f"CRITICAL: Source signature mismatch! Expected: {expected}, Got: {signature}")
        return True

    def validate_price_records(self, records: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        valid = []
        rejected = []
        seen = set()

        for rec in records:
            self.stats["rows_read"] += 1
            key = (rec.get("spice_code"), rec.get("date"), rec.get("seller_or_auctioneer"), rec.get("market_id"))
            
            # Check duplicates
            if key in seen:
                self.stats["duplicate_count"] += 1
                self.stats["rows_rejected"] += 1
                entry = {"record": rec, "reason": "Duplicate key observation"}
                self.rejected_records.append(entry)
                rejected.append(entry)
                continue
            seen.add(key)

            avg_price = rec.get("avg_price")
            min_price = rec.get("min_price")
            max_price = rec.get("max_price")
            arrived = rec.get("quantity", 0)
            sold = rec.get("quantity_sold", 0)

            # Price assertions
            if avg_price is None or avg_price <= 0:
                self.stats["negative_price_count"] += 1
                self.stats["rows_rejected"] += 1
                entry = {"record": rec, "reason": "Non-positive average price"}
                self.rejected_records.append(entry)
                rejected.append(entry)
                continue

            if min_price is not None and max_price is not None:
                if min_price > max_price:
                    self.stats["invalid_spread_count"] += 1
                    self.stats["rows_rejected"] += 1
                    entry = {"record": rec, "reason": f"min_price ({min_price}) > max_price ({max_price})"}
                    self.rejected_records.append(entry)
                    rejected.append(entry)
                    continue

            # Quantity assertions
            if arrived is not None and sold is not None:
                if sold > arrived:
                    self.stats["invalid_quantity_count"] += 1
                    self.stats["rows_rejected"] += 1
                    entry = {"record": rec, "reason": f"quantity_sold ({sold}) > quantity_arrived ({arrived})"}
                    self.rejected_records.append(entry)
                    rejected.append(entry)
                    continue

            valid.append(rec)
            self.stats["rows_loaded"] += 1

        return valid, rejected

    def validate_weather_records(self, records: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        valid = []
        rejected = []
        for rec in records:
            self.stats["rows_read"] += 1
            rainfall = rec.get("rainfall_mm", 0)
            tmin = rec.get("tmin_c")
            tmax = rec.get("tmax_c")

            if rainfall < 0:
                self.stats["rows_rejected"] += 1
                entry = {"record": rec, "reason": "Negative rainfall value"}
                self.rejected_records.append(entry)
                rejected.append(entry)
                continue

            if tmin is not None and tmax is not None and tmin > tmax:
                self.stats["rows_rejected"] += 1
                entry = {"record": rec, "reason": f"tmin ({tmin}) > tmax ({tmax})"}
                self.rejected_records.append(entry)
                rejected.append(entry)
                continue

            valid.append(rec)
            self.stats["rows_loaded"] += 1

        return valid, rejected
