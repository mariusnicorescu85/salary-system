"""
UK Wage Bracket - Resolve hourly rate from age and date.
Uses UK National Minimum Wage / Living Wage bands (21+, 18-20, 16-17).
"""

from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path
import csv


def _parse_date(s: str) -> Optional[datetime]:
    """Parse date from various formats: DD/MM/YYYY, YYYY-MM-DD."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s[:10], fmt)
        except ValueError:
            continue
    return None


def _age_at_date(dob: datetime, date: datetime) -> int:
    """Calculate age in full years at the given date."""
    age = date.year - dob.year
    if (date.month, date.day) < (dob.month, dob.day):
        age -= 1
    return age


def _age_band(age: int) -> Optional[str]:
    """Map age to UK wage band: 21+, 18-20, 16-17."""
    if age >= 21:
        return "21+"
    if 18 <= age < 21:
        return "18-20"
    if 16 <= age < 18:
        return "16-17"
    return None  # Under 16 - no standard band


def brackets_from_records(records: List[Dict]) -> List[Dict]:
    """
    Convert raw records (from CSV or Airtable) to normalized bracket format.
    Expected fields: Age Band, Hourly Rate, Effective From, Effective To
    Returns list of {age_band, hourly_rate, effective_from, effective_to}.
    """
    brackets = []
    for row in records:
        age_band = (row.get("Age Band") or "").strip()
        rate_val = row.get("Hourly Rate")
        if rate_val is None:
            rate_str = ""
        else:
            rate_str = str(rate_val).strip()
        eff_from = (row.get("Effective From") or "").strip()
        eff_to = (row.get("Effective To") or "").strip()
        if not age_band or not rate_str:
            continue
        try:
            rate = float(rate_str)
        except ValueError:
            continue
        from_dt = _parse_date(eff_from)
        to_dt = _parse_date(eff_to) if eff_to else None  # None = no end date
        brackets.append({
            "age_band": age_band,
            "hourly_rate": rate,
            "effective_from": from_dt,
            "effective_to": to_dt,
        })
    return brackets


def load_brackets_from_csv(path: str) -> List[Dict]:
    """
    Load UK wage brackets from CSV.
    Expected columns: Age Band, Hourly Rate, Effective From, Effective To
    Returns list of {age_band, hourly_rate, effective_from, effective_to}.
    """
    brackets = []
    p = Path(path)
    if not p.exists():
        return brackets
    with open(p, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        brackets = brackets_from_records(list(reader))
    return brackets


def get_rate_for_date(
    date_str: str,
    dob_str: str,
    brackets: List[Dict],
) -> Optional[float]:
    """
    Get the applicable hourly rate for an employee on a given date.
    
    Args:
        date_str: Date of the shift/payroll (YYYY-MM-DD)
        dob_str: Employee date of birth (DD/MM/YYYY or YYYY-MM-DD)
        brackets: List from load_brackets_from_csv
    
    Returns:
        Hourly rate or None if not determinable
    """
    if not brackets:
        return None
    date_dt = _parse_date(date_str)
    dob_dt = _parse_date(dob_str)
    if not date_dt or not dob_dt:
        return None
    age = _age_at_date(dob_dt, date_dt)
    band = _age_band(age)
    if not band:
        return None
    for b in brackets:
        if b["age_band"] != band:
            continue
        from_dt = b.get("effective_from")
        to_dt = b.get("effective_to")
        if from_dt and date_dt < from_dt:
            continue
        if to_dt and date_dt > to_dt:
            continue
        return b["hourly_rate"]
    return None
