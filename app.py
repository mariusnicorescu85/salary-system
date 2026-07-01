"""
Salary Calculation Dashboard
Main Streamlit application for running salary calculations
"""

import streamlit as st
import pandas as pd
import yaml
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import date, datetime, timedelta
import io
import logging
import sys
import os
import hashlib
import secrets
import calendar

# Set up console logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Import our modules
from src.calculation_engine import CalculationEngine
from src.data_processor import DataProcessor
from src.airtable_client import AirtableClient, _normalize_date_for_key
from src.email_client import EmailClient
from googleapiclient.errors import HttpError
from src.google_drive_client import GoogleDriveClient


def _parse_dob_for_bracket(dob_raw) -> Optional[str]:
    """Normalize DOB from Airtable to string parseable by wage_bracket (YYYY-MM-DD or DD/MM/YYYY)."""
    if not dob_raw:
        return None
    if isinstance(dob_raw, datetime):
        return dob_raw.strftime("%Y-%m-%d")
    s = str(dob_raw).strip()
    if not s:
        return None
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    return s


# Page configuration
st.set_page_config(
    page_title="Salary Calculation Dashboard",
    page_icon="💰",
    layout="wide"
)

def inject_rota_theme():
    st.html(
        """
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@fontsource/geist-sans@5.2.8/index.css">
        <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0,0">
        <style>
          :root {
            --background: #f4f4f5;
            --foreground: #18181b;
            --text-muted: #71717a;
            --accent: #4f46e5;
            --accent-hover: #6366f1;
            --accent-muted: #eef2ff;
            --surface: #ffffff;
            --border: #e4e4e7;
            --font-sans: "Geist Sans", ui-sans-serif, system-ui, sans-serif;
          }
          .stApp {
            font-family: var(--font-sans);
            background-color: var(--background) !important;
            color: var(--foreground) !important;
          }
          .stApp h1, .stApp h2, .stApp h3,
          .stApp p, .stApp label,
          .stApp [data-testid="stMarkdown"],
          .stApp [data-testid="stMetric"] {
            font-family: var(--font-sans) !important;
          }
          .stApp .stMarkdown span:not([data-testid="stIconMaterial"]):not([data-testid="stExpanderIcon"]):not([data-testid="stExpanderIconCheck"]):not([data-testid="stExpanderIconError"]):not([data-testid="stExpanderIconSpinner"]),
          .stApp [data-testid="stMetric"] span:not([data-testid="stIconMaterial"]):not([data-testid="stExpanderIcon"]) {
            font-family: var(--font-sans) !important;
          }
          .stApp [data-testid="stIconMaterial"],
          .stApp [data-testid="stExpanderIcon"],
          .stApp [data-testid="stExpanderIconCheck"],
          .stApp [data-testid="stExpanderIconError"],
          .stApp [data-testid="stExpanderIconSpinner"] {
            font-family: "Material Symbols Outlined" !important;
            font-weight: normal !important;
            font-style: normal !important;
            font-feature-settings: "liga" !important;
            font-variation-settings: "FILL" 0, "wght" 400, "GRAD" 0, "opsz" 24 !important;
            letter-spacing: normal !important;
            text-transform: none !important;
            line-height: 1 !important;
            -webkit-font-smoothing: antialiased !important;
          }
          .stApp [data-testid="stExpanderIcon"],
          .stExpander [data-testid="stIconMaterial"],
          [data-testid="stExpander"] [data-testid="stIconMaterial"],
          [data-testid="stSidebarCollapseButton"] [data-testid="stIconMaterial"],
          [data-testid="stExpandSidebarButton"] [data-testid="stIconMaterial"] {
            font-size: 0 !important;
            line-height: 0 !important;
            color: transparent !important;
            position: relative !important;
            display: inline-block !important;
            width: 1.15rem !important;
            height: 1.15rem !important;
            overflow: hidden !important;
            vertical-align: middle !important;
          }
          .stApp [data-testid="stExpanderIcon"]::after,
          .stExpander [data-testid="stIconMaterial"]::after,
          [data-testid="stExpander"] [data-testid="stIconMaterial"]::after,
          [data-testid="stSidebarCollapseButton"] [data-testid="stIconMaterial"]::after,
          [data-testid="stExpandSidebarButton"] [data-testid="stIconMaterial"]::after {
            position: absolute !important;
            left: 0 !important;
            top: 0 !important;
            color: #71717a !important;
            font-family: var(--font-sans) !important;
            font-weight: 700 !important;
            font-size: 1.1rem !important;
            line-height: 1.15rem !important;
            display: block !important;
          }
          .stExpander summary[aria-expanded="false"] [data-testid="stIconMaterial"]::after,
          [data-testid="stExpander"] summary[aria-expanded="false"] [data-testid="stIconMaterial"]::after,
          .stExpander details:not([open]) > summary [data-testid="stIconMaterial"]::after,
          [data-testid="stExpander"] details:not([open]) > summary [data-testid="stIconMaterial"]::after,
          .stApp [data-testid="stExpanderIcon"]::after {
            content: "›" !important;
          }
          .stExpander summary[aria-expanded="true"] [data-testid="stIconMaterial"]::after,
          [data-testid="stExpander"] summary[aria-expanded="true"] [data-testid="stIconMaterial"]::after,
          .stExpander details[open] > summary [data-testid="stIconMaterial"]::after,
          [data-testid="stExpander"] details[open] > summary [data-testid="stIconMaterial"]::after,
          .stExpander details[open] > summary [data-testid="stExpanderIcon"]::after {
            content: "⌄" !important;
          }
          [data-testid="stSidebarCollapseButton"] [data-testid="stIconMaterial"]::after {
            content: "‹" !important;
            font-size: 1.25rem !important;
          }
          [data-testid="stExpandSidebarButton"] [data-testid="stIconMaterial"]::after {
            content: "›" !important;
            font-size: 1.25rem !important;
          }
          /* st.file_uploader "Upload" button: icon ligature can render as plain
             "upload" text on top of the "Upload" label (uploadUpload overlap). */
          [data-testid="stFileUploader"] button [data-testid="stIconMaterial"] {
            font-size: 0 !important;
            line-height: 0 !important;
            color: transparent !important;
            position: relative !important;
            display: inline-block !important;
            width: 1.125rem !important;
            height: 1.125rem !important;
            overflow: hidden !important;
            vertical-align: middle !important;
            flex-shrink: 0 !important;
          }
          [data-testid="stFileUploader"] button [data-testid="stIconMaterial"]::after {
            content: "upload" !important;
            position: absolute !important;
            left: 0 !important;
            top: 0 !important;
            color: inherit !important;
            font-family: "Material Symbols Outlined" !important;
            font-weight: normal !important;
            font-size: 1.125rem !important;
            line-height: 1.125rem !important;
            font-feature-settings: "liga" !important;
            font-variation-settings: "FILL" 0, "wght" 400, "GRAD" 0, "opsz" 24 !important;
          }
          [data-testid="stSidebar"] {
            background-color: var(--surface) !important;
            border-right: 1px solid var(--border) !important;
          }
          [data-testid="stSidebar"] .stMarkdown,
          [data-testid="stSidebar"] label {
            color: var(--foreground) !important;
          }
          .stButton > button[kind="primary"] {
            background-color: var(--accent) !important;
            border-color: var(--accent) !important;
            color: #ffffff !important;
            border-radius: 12px !important;
            font-weight: 600 !important;
          }
          .stButton > button[kind="primary"]:hover {
            background-color: var(--accent-hover) !important;
            border-color: var(--accent-hover) !important;
          }
          .stButton > button[kind="secondary"] {
            border-radius: 12px !important;
            border-color: var(--border) !important;
          }
          div[data-baseweb="tab-highlight"] {
            background-color: var(--accent) !important;
          }
          div[data-baseweb="tab"] {
            color: var(--text-muted) !important;
          }
          div[data-baseweb="tab"][aria-selected="true"] {
            color: var(--accent) !important;
          }
        </style>
        """
    )


inject_rota_theme()

# Initialize session state
if 'calculations_done' not in st.session_state:
    st.session_state.calculations_done = False
if 'results' not in st.session_state:
    st.session_state.results = {}
if 'authentication_status' not in st.session_state:
    st.session_state.authentication_status = None
if 'name' not in st.session_state:
    st.session_state.name = None
if 'username' not in st.session_state:
    st.session_state.username = None
if 'target_approved' not in st.session_state:
    st.session_state.target_approved = "0"
if 'target_total_reached' not in st.session_state:
    st.session_state.target_total_reached = "0"
if 'target_current_date' not in st.session_state:
    st.session_state.target_current_date = datetime.today().date()
if 'daily_target_date' not in st.session_state:
    st.session_state.daily_target_date = datetime.today().date()
if 'wage_vs_sales_date' not in st.session_state:
    st.session_state.wage_vs_sales_date = datetime.today().date()
if 'wvs_range_start' not in st.session_state:
    st.session_state.wvs_range_start = datetime.today().date()
if 'wvs_range_end' not in st.session_state:
    st.session_state.wvs_range_end = datetime.today().date()
if 'selected_saved_report' not in st.session_state:
    st.session_state.selected_saved_report = None
if 'selected_gdrive_report' not in st.session_state:
    st.session_state.selected_gdrive_report = None  # {'id': str, 'name': str}

# Saved reports directory for persisting uploaded files
SAVED_REPORTS_DIR = Path("saved_reports")
def _last_results_file(shop_key: str) -> Path:
    """Path to last results file for a given shop."""
    return SAVED_REPORTS_DIR / f"last_calculation_results_{shop_key}.json"


def _ensure_saved_reports_dir():
    """Create saved_reports directory if it doesn't exist."""
    SAVED_REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def _save_last_results(results: Dict, results_shop_key: str, employees_config: Dict) -> None:
    """Persist last calculation results per shop so Results tab can show them after app restart."""
    try:
        _ensure_saved_reports_dir()
        def _serialize(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            if isinstance(obj, dict):
                return {k: _serialize(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [_serialize(x) for x in obj]
            return obj
        data = {
            "results": _serialize(results),
            "results_shop_key": results_shop_key,
            "employees_config": _serialize(employees_config),
            "saved_at": datetime.now().isoformat(),
        }
        path = _last_results_file(results_shop_key)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not save last results: {e}")


def _load_last_results_from_file(shop_key: str) -> Optional[Dict]:
    """Load last calculation results from file for a given shop. Returns None if not found or invalid."""
    try:
        path = _last_results_file(shop_key)
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        results = data.get("results", {})
        if not results:
            return None
        return {
            "results": results,
            "results_shop_key": data.get("results_shop_key", ""),
            "employees_config": data.get("employees_config", {}),
        }
    except Exception as e:
        logger.warning(f"Could not load last results: {e}")
        return None


def _get_field(rec: Dict, *keys: str, default=0):
    """Get field from Airtable record, trying multiple key names. Returns float for numeric fields."""
    for k in keys:
        v = rec.get(k)
        if v is not None and v != "":
            if isinstance(v, (int, float)):
                return float(v)
            if isinstance(v, str):
                try:
                    return float(v.replace(",", ""))
                except (ValueError, TypeError):
                    return v
            return v
    return default


@st.cache_data(ttl=60)
def _load_results_from_airtable(shop_key: str) -> Optional[Dict]:
    """
    Load calculation results from Airtable for a given shop.
    Fetches from the shop's Daily Breakdowns table and converts to our results format.
    Returns None if fetch fails or no data.
    """
    config = load_config()
    shop_config = config.get("shops", {}).get(shop_key)
    if not shop_config:
        return None
    base_id = shop_config.get("airtable_base_id")
    table_name = shop_config.get("airtable_table_name")
    if not base_id or not table_name:
        return None
    _, api_key, _ = _get_airtable_credentials(shop_key)
    if not api_key:
        logger.warning("_load_results_from_airtable: No Airtable API key (set in Streamlit secrets or sidebar)")
        return None
    try:
        client = AirtableClient(api_key=api_key)
        records = client.get_daily_breakdown_records(base_id, table_name)
    except Exception as e:
        logger.warning(f"Could not fetch from Airtable: {e}")
        return None
    if not records:
        logger.warning(f"_load_results_from_airtable: No records in {table_name} (base {base_id})")
        return None

    def _record_type(r):
        return (r.get("RecordType") or r.get("recordtype") or r.get("Record Type") or "").strip()

    # Split into Daily and Monthly Summary (Airtable may use "Record Type" with space)
    daily_rows = [r for r in records if _record_type(r) == "Daily"]
    summary_rows = [r for r in records if _record_type(r) == "Monthly Summary"]
    summary_by_emp = {}
    for rec in summary_rows:
        emp = (rec.get("Employee") or rec.get("employee") or "").strip()
        if not emp:
            continue
        summary_by_emp[emp] = {
            "WorkedDays": _get_field(rec, "WorkedDays", "Worked Days", "worked_days"),
            "WorkedHours": _get_field(rec, "WorkedHours", "Worked Hours", "worked_hours"),
            "Sales": _get_field(rec, "Sales", "sales"),
            "AddlSales": _get_field(rec, "AddlSales", "Addl Sales", "addl_sales"),
            "AdjustedSales": _get_field(rec, "AdjustedSales", "Adjusted Sales", "adjusted_sales"),
            "AvgSalePerDay": _get_field(rec, "AvgSalePerDay", "Avg Sale Per Day"),
            "RatePerHour": _get_field(rec, "RatePerHour", "Rate Per Hour", "rate_per_hour"),
            "HoursSalary": _get_field(rec, "HoursSalary", "Hours Salary", "hours_salary"),
            "TotalCommission": _get_field(rec, "TotalCommission", "Total Commission", "total_commission"),
            "TotalBonus": _get_field(rec, "TotalBonus", "Total Bonus", "total_bonus"),
            "FinalPayment": _get_field(rec, "FinalPayment", "Final Payment", "final_payment"),
            "PaymentType": rec.get("PaymentType") or rec.get("payment_type") or "",
            "ManualHours": _get_field(rec, "ManualHours", "Manual Hours"),
            "ManualHoursPay": _get_field(rec, "ManualHoursPay", "Manual Hours Pay"),
            "Deductions": _get_field(rec, "Deductions", "deductions"),
            "Rent": _get_field(rec, "Rent", "rent"),
            "Advance": _get_field(rec, "Advance", "advance"),
            "BonusBreakdown": {},
            "ProratedBasePay": _get_field(rec, "ProratedBasePay", "Prorated Base Pay", "prorated_base_pay"),
            "ShopRangeSalesGross": _get_field(rec, "ShopRangeSalesGross", "Shop Range Sales Gross", "shop_range_sales_gross"),
            "ShopRangeCommission": _get_field(rec, "ShopRangeCommission", "Shop Range Commission", "shop_range_commission"),
            "PersonalCommission": _get_field(rec, "PersonalCommission", "Personal Commission", "personal_commission"),
            "ShopRangeFirstDate": (rec.get("ShopRangeFirstDate") or rec.get("Shop Range First Date") or "") or "",
            "ShopRangeLastDate": (rec.get("ShopRangeLastDate") or rec.get("Shop Range Last Date") or "") or "",
        }
    # Build daily by employee
    daily_by_emp = {}
    for rec in daily_rows:
        emp = (rec.get("Employee") or rec.get("employee") or "").strip()
        if not emp:
            continue
        date_val = rec.get("Date") or rec.get("date")
        if not date_val:
            continue
        date_str = date_val[:10] if isinstance(date_val, str) and len(date_val) >= 10 else str(date_val)[:10]
        daily_by_emp.setdefault(emp, []).append({
            "Employee": emp,
            "Date": date_str,
            "Hours": _get_field(rec, "Hours", "hours"),
            "Sales": _get_field(rec, "Sales", "sales"),
            "AddlSales": _get_field(rec, "AddlSales", "Addl Sales", "addl_sales"),
            "HrlyRate": _get_field(rec, "HrlyRate", "Hrly Rate", "hrly_rate"),
            "Base": _get_field(rec, "Base", "base"),
            "Commission": _get_field(rec, "Commission", "commission"),
            "PaymentType": rec.get("PaymentType") or rec.get("payment_type") or "",
        })
    for emp, daily_list in daily_by_emp.items():
        daily_list.sort(key=lambda x: x.get("Date", ""))
    # Build results: need both summary and daily for each employee
    results = {}
    for emp in set(summary_by_emp.keys()) | set(daily_by_emp.keys()):
        summary = summary_by_emp.get(emp, {})
        daily = daily_by_emp.get(emp, [])
        if not summary and not daily:
            continue
        if not summary:
            summary = {
                "WorkedDays": 0, "WorkedHours": 0, "Sales": 0, "AddlSales": 0, "AdjustedSales": 0,
                "FinalPayment": 0, "HoursSalary": 0, "TotalCommission": 0, "TotalBonus": 0,
                "RatePerHour": 0, "PaymentType": "", "BonusBreakdown": {},
            }
        results[emp] = {"summary": summary, "daily": daily}
    if not results:
        return None
    return {
        "results": results,
        "results_shop_key": shop_key,
        "employees_config": {},
    }


def _list_saved_reports() -> List[str]:
    """Return list of saved report filenames (paths as strings)."""
    _ensure_saved_reports_dir()
    if not SAVED_REPORTS_DIR.exists():
        return []
    files = sorted(
        [f.name for f in SAVED_REPORTS_DIR.iterdir() if f.suffix.lower() in ('.csv', '.xlsx')],
        reverse=True
    )
    return files


def _save_report(uploaded_file) -> bool:
    """Save uploaded file to saved_reports. Returns True on success."""
    if uploaded_file is None:
        return False
    try:
        _ensure_saved_reports_dir()
        base = Path(uploaded_file.name).stem
        ext = Path(uploaded_file.name).suffix.lower()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{base}_{timestamp}{ext}"
        path = SAVED_REPORTS_DIR / filename
        uploaded_file.seek(0)
        path.write_bytes(uploaded_file.read())
        return True
    except Exception as e:
        logger.error(f"Failed to save report: {e}")
        return False


def _load_saved_report(filename: str):
    """Load a saved report into a file-like object (BytesIO with name/size)."""
    path = SAVED_REPORTS_DIR / filename
    if not path.exists():
        return None
    try:
        data = path.read_bytes()
        bio = io.BytesIO(data)
        bio.name = filename
        bio.size = len(data)
        return bio
    except Exception as e:
        logger.error(f"Failed to load saved report: {e}")
        return None


def _get_service_account_json_from_secrets():
    """Read [google_drive] service_account_json from Streamlit secrets (Cloud) or secrets.toml (local)."""
    if not hasattr(st, "secrets"):
        return None
    try:
        section = st.secrets["google_drive"]
    except (KeyError, TypeError):
        return None
    raw = None
    if isinstance(section, dict):
        raw = section.get("service_account_json")
    else:
        raw = getattr(section, "service_account_json", None)
    if raw is None and isinstance(section, dict):
        try:
            raw = section["service_account_json"]
        except KeyError:
            pass
    if raw is None:
        return None
    if isinstance(raw, str) and not raw.strip():
        return None
    return raw


def _try_google_drive_client() -> Tuple[Optional[GoogleDriveClient], Optional[str]]:
    """
    Build a Drive client (service account from Secrets on Cloud, or OAuth files locally).
    Returns (client, None) on success, (None, user-facing error) on failure.
    """
    try:
        sa_json = _get_service_account_json_from_secrets()
        if sa_json:
            try:
                return GoogleDriveClient(service_account_json=sa_json), None
            except Exception as e:
                logger.exception("Google Drive service account init failed")
                return None, f"Service account in Secrets is invalid or incomplete: {e}"

        creds_path = Path('credentials/google_drive_credentials.json')
        if creds_path.exists():
            try:
                return GoogleDriveClient(), None
            except Exception as e:
                logger.exception("Google Drive OAuth init failed")
                return None, str(e)

        return None, (
            "Streamlit Cloud has no credentials/google_drive_credentials.json (it is not deployed). "
            "Add [google_drive] with service_account_json in App settings → Secrets, then share your "
            "reports folder with the JSON's client_email (Editor). For Shared Drives, the folder must "
            "live in a drive the service account can access."
        )
    except Exception as e:
        logger.exception("Google Drive client setup failed")
        return None, str(e)


def _get_google_drive_client() -> Optional[GoogleDriveClient]:
    """Get Google Drive client if configured (Service Account from secrets, or OAuth from credentials/)."""
    client, _ = _try_google_drive_client()
    return client


def _get_saved_reports_folder_id(shop_key: str) -> str:
    """Get the folder ID for saved reports for a given shop from config."""
    config = load_config()
    if not config or not shop_key:
        return ""
    shop = config.get('shops', {}).get(shop_key, {})
    for key in ("saved_reports_folder_id", "google_drive_folder_id"):
        folder = (shop.get(key) or "").strip()
        if folder:
            return folder
    return ""


def _format_gdrive_error(exc: Exception) -> str:
    """Short user-facing message for Google Drive API failures."""
    if isinstance(exc, HttpError):
        try:
            payload = json.loads(exc.content.decode() if exc.content else "{}")
            msg = (payload.get("error") or {}).get("message") or str(exc)
        except (json.JSONDecodeError, TypeError, AttributeError):
            msg = str(exc)
        if exc.resp is not None and exc.resp.status:
            return f"{exc.resp.status} — {msg}"
        return msg
    return str(exc)


def _save_report_to_gdrive(uploaded_file, folder_id: str) -> Tuple[bool, Optional[str]]:
    """
    Save uploaded file to Google Drive.
    Returns (True, None) on success, (False, error_message) on failure.
    """
    if not uploaded_file or not folder_id:
        return False, "Missing upload or folder ID in configuration."
    client, init_err = _try_google_drive_client()
    if not client:
        return False, init_err or "Google Drive credentials are missing or invalid."
    try:
        uploaded_file.seek(0)
        content = uploaded_file.read()
        ext = Path(uploaded_file.name).suffix.lower()
        now = datetime.now()
        filename = f"report_{now.month:02d}_{now.year}{ext}"
        client.upload_file(content, filename, folder_id)
        return True, None
    except Exception as e:
        detail = _format_gdrive_error(e)
        logger.error(f"Failed to save report to Google Drive: {detail}")
        return False, detail


def _list_gdrive_reports(folder_id: str) -> List[dict]:
    """List report files (csv, xlsx) in a Google Drive folder."""
    if not folder_id:
        return []
    client = _get_google_drive_client()
    if not client:
        return []
    try:
        files = client.list_files_in_folder(folder_id)
        return [f for f in files if f.get('name', '').lower().endswith(('.csv', '.xlsx'))]
    except Exception as e:
        logger.error(f"Failed to list Google Drive reports: {e}")
        return []


def _load_gdrive_report(file_id: str, filename: str):
    """Load a report from Google Drive into a file-like object."""
    client = _get_google_drive_client()
    if not client:
        return None
    try:
        data = client.download_file(file_id)
        bio = io.BytesIO(data)
        bio.name = filename
        bio.size = len(data)
        return bio
    except Exception as e:
        logger.error(f"Failed to load report from Google Drive: {e}")
        return None


def _parse_shop_config_yaml(yaml_text: str, source: str) -> Tuple[Optional[Dict], Optional[str]]:
    """Parse shops YAML text. Returns (config, error_message)."""
    if not yaml_text or not str(yaml_text).strip():
        return None, f"{source}: YAML content is empty."
    try:
        config = yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        return None, f"{source}: invalid YAML — {e}"
    if not isinstance(config, dict):
        return None, f"{source}: YAML must be a mapping (dict), not {type(config).__name__}."
    shops = config.get("shops")
    if not isinstance(shops, dict) or not shops:
        hint = ""
        if isinstance(config.get("westfield"), dict):
            hint = " Found `westfield` at the top level — indent it under `shops:` (same level as `pyt:` and `opatra:`)."
        return None, f"{source}: missing or empty `shops:` key.{hint}"
    return config, None


def _load_config_from_secrets() -> Tuple[Optional[Dict], Optional[str]]:
    """Load shop config from Streamlit secrets [app_config] yaml = '''...'''."""
    if not hasattr(st, "secrets"):
        return None, "Streamlit secrets are not available in this environment."
    try:
        app_cfg = st.secrets.get("app_config")
    except Exception as e:
        return None, f"Could not read Streamlit secrets (check TOML syntax in Settings → Secrets): {e}"
    if app_cfg is None:
        return None, "No `[app_config]` section in Streamlit secrets."
    yaml_text = None
    if isinstance(app_cfg, dict):
        yaml_text = app_cfg.get("yaml")
    else:
        yaml_text = getattr(app_cfg, "yaml", None)
    if yaml_text is None:
        return None, "`[app_config]` exists but `yaml` key is missing. Use: yaml = '''...'''"
    return _parse_shop_config_yaml(str(yaml_text), "Streamlit secrets [app_config]")


@st.cache_data(ttl=60)
def load_config():
    """Load shop configuration from config/shops.yaml (local) or st.secrets (Streamlit Cloud)."""
    base = Path(__file__).resolve().parent
    for config_path in [base / 'config' / 'shops.yaml', Path('config/shops.yaml')]:
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config, err = _parse_shop_config_yaml(f.read(), str(config_path))
                if config:
                    return config
                logger.warning("Shop config file invalid: %s", err)
            except OSError as e:
                logger.warning("Could not read %s: %s", config_path, e)

    config, err = _load_config_from_secrets()
    if config:
        return config

    st.error(
        "Configuration not found. **Local:** create `config/shops.yaml` (copy from `config/shops.yaml.example`). "
        "**Streamlit Cloud:** add `[app_config]` with `yaml = '''...'''` (your shops.yaml content) in Settings → Secrets."
    )
    if err:
        st.warning(f"**Details:** {err}")
    st.info(
        "After updating Secrets on Streamlit Cloud: **☰ → Clear cache → Rerun**, or reboot the app from Manage app."
    )
    return None


def _get_airtable_credentials(shop_key: str = None):
    """
    Get Airtable base_id, api_key, and table names. Used when system is Airtable-only.
    Returns (base_id, api_key, tables_dict) or (None, None, None) if credentials missing.
    """
    config = load_config()
    if not config or not config.get("shops"):
        return None, None, None
    shops_list = list(config["shops"].values())
    shop = config["shops"].get(shop_key) if shop_key else (shops_list[0] if shops_list else None)
    if not shop:
        return None, None, None
    base_id = (shop.get("airtable_base_id") or "").strip()
    if not base_id:
        return None, None, None
    api_key = None
    try:
        if hasattr(st, "secrets") and st.secrets.get("airtable", {}).get("api_key"):
            api_key = st.secrets.airtable.api_key
    except Exception:
        pass
    api_key = api_key or os.getenv("AIRTABLE_API_KEY") or st.session_state.get("airtable_api_key", "")
    if not api_key:
        return base_id, None, None
    tables = config.get("airtable_config_tables", {})
    tables_tuple = (
        tables.get("shop_targets", "Shop Targets"),
        tables.get("daily_targets", "Daily Targets"),
    )
    return base_id, api_key, tables_tuple


@st.cache_data(ttl=60)
def load_employee_config(shop_key: str):
    """Load employee configuration for a shop from Airtable (Employees, Commission Tiers, Name Mappings, Sales Bonus Thresholds)."""
    config = load_config()
    if not config:
        return None, None, None
    
    shop_config = config['shops'].get(shop_key)
    if not shop_config:
        return None, None, None
    
    base_id = (shop_config.get("airtable_base_id") or "").strip()
    api_key = None
    try:
        if hasattr(st, "secrets") and st.secrets.get("airtable", {}).get("api_key"):
            api_key = st.secrets.airtable.api_key
    except Exception:
        pass
    api_key = api_key or os.getenv("AIRTABLE_API_KEY") or st.session_state.get("airtable_api_key", "")
    
    if not base_id or not api_key:
        return None, None, None
    
    return _load_employee_config_from_airtable(shop_key, base_id, api_key)


def _load_employee_config_from_airtable(
    shop_key: str,
    base_id: str,
    api_key: str,
) -> tuple:
    """
    Load employee configuration from Airtable (Employees, Commission Tiers, Name Mappings, Sales Bonus Thresholds).
    Returns (employees_dict, bonuses_dict, emp_config_full) - same shape as load_employee_config.
    Bonuses are loaded separately per month - call load_monthly_bonuses for that.
    """
    config = load_config()
    if not config:
        return None, None, None
    
    shop_config = config['shops'].get(shop_key)
    if not shop_config:
        return None, None, None
    
    tables = config.get('airtable_config_tables', {})
    emp_table = tables.get('employees', 'Employees')
    tiers_table = tables.get('commission_tiers', 'Commission Tiers')
    mappings_table = tables.get('name_mappings', 'Name Mappings')
    bonus_table = tables.get('sales_bonus_thresholds', 'Sales Bonus Thresholds')
    
    shop_display_name = shop_config.get('shop_display_name') or shop_config.get('name', shop_key)
    
    try:
        client = AirtableClient(api_key=api_key)
    except Exception as e:
        logger.error(f"Airtable client init failed: {e}")
        return None, None, None
    
    # Fetch employees
    emp_records = client.get_employees_for_shop(base_id, emp_table, shop_display_name)
    if not emp_records:
        logger.warning(f"No employees found for shop {shop_display_name} in Airtable")
        return {}, {}, {}
    
    # Fetch commission tiers
    tiers_by_emp = client.get_commission_tiers_for_shop(
        base_id, tiers_table, emp_table, shop_display_name
    )
    
    # Fetch name mappings
    name_mapping = client.get_name_mappings_for_shop(
        base_id, mappings_table, emp_table, shop_display_name
    )
    
    # Fetch sales bonus thresholds
    sales_bonus_by_emp = client.get_sales_bonus_thresholds_for_shop(
        base_id, bonus_table, emp_table, shop_display_name
    )
    
    
    # Build employees dict
    employees = {}
    for rec in emp_records:
        name = rec.get("Name", "").strip()
        if not name:
            continue
        
        hourly = rec.get("Hourly Rate Override")
        if hourly is not None and hourly != "":
            try:
                hourly_rate = float(hourly)
            except (TypeError, ValueError):
                hourly_rate = 0
        else:
            hourly_rate = 0
        
        emp_eng = rec.get("Employment") or rec.get("employment")
        emp = {
            "payment_type": rec.get("Payment Type") or "hourly_only",
            "hourly_rate": hourly_rate,
            "email": (rec.get("Email") or rec.get("email") or ""),
            "employment": str(emp_eng).strip() if emp_eng not in (None, "") else "",
        }
        
        # Date of Birth - used for UK wage bracket when no hourly rate override
        dob_raw = rec.get("Date of Birth")
        if dob_raw:
            emp["date_of_birth"] = _parse_dob_for_bracket(dob_raw)
        
        if rec.get("Commission Rate") is not None and rec.get("Commission Rate") != "":
            try:
                emp["commission_rate"] = float(rec.get("Commission Rate"))
            except (TypeError, ValueError):
                pass

        if rec.get("Base Monthly Amount") is not None and rec.get("Base Monthly Amount") != "":
            try:
                emp["monthly_base"] = float(rec.get("Base Monthly Amount"))
            except (TypeError, ValueError):
                pass
        if rec.get("Base Reference Days") is not None and rec.get("Base Reference Days") != "":
            try:
                emp["base_reference_days"] = float(rec.get("Base Reference Days"))
            except (TypeError, ValueError):
                pass
        if rec.get("Shop Commission Rate") is not None and rec.get("Shop Commission Rate") != "":
            try:
                emp["shop_commission_rate"] = float(rec.get("Shop Commission Rate"))
            except (TypeError, ValueError):
                pass
        
        if rec.get("Daily Transport") is not None and rec.get("Daily Transport") != "":
            try:
                emp["daily_transport"] = float(rec.get("Daily Transport"))
            except (TypeError, ValueError):
                pass
        
        if rec.get("Rent") is not None and rec.get("Rent") != "":
            try:
                emp["rent"] = float(rec.get("Rent"))
            except (TypeError, ValueError):
                pass
        
        if rec.get("Advance") is not None and rec.get("Advance") != "":
            try:
                emp["advance"] = float(rec.get("Advance"))
            except (TypeError, ValueError):
                pass
        
        # Commission tiers
        if name in tiers_by_emp and tiers_by_emp[name]:
            emp["commission_tiers"] = tiers_by_emp[name]
        
        # Sales bonus thresholds (november_bonuses, december_bonuses, etc.)
        if name in sales_bonus_by_emp:
            for mon, bonuses_list in sales_bonus_by_emp[name].items():
                key = f"{mon}_bonuses"
                emp[key] = bonuses_list
        
        # Special config (e.g. Alex)
        if rec.get("Special Config JSON"):
            try:
                sc = rec.get("Special Config JSON")
                if isinstance(sc, str):
                    sc = json.loads(sc)
                emp.update(sc)
            except Exception:
                pass
        
        employees[name] = emp
    
    # Bonuses (monthly adjustments) are loaded separately per month
    bonuses = {name: {} for name in employees}
    
    emp_config_full = {
        "employees": employees,
        "bonuses": bonuses,
        "name_mapping": name_mapping,
        "exclude_patterns": ["test", "TEST", "admin", "ADMIN", "manager", "MANAGER", "demo", "DEMO"],
    }
    
    return employees, bonuses, emp_config_full


from utils.helpers import format_currency, parse_currency_input as _parse_currency_input


def _format_date_for_chart(date_val) -> str:
    """Normalize date to YYYY-MM-DD then format as 'DD Mon' for chart labels. Avoids month/day swap (e.g. 1/3 vs 3/1)."""
    normalized = _normalize_date_for_key(date_val)
    if not normalized:
        return str(date_val)[:10] if date_val else ""
    try:
        dt = pd.to_datetime(normalized)
        return dt.strftime("%d %b")
    except Exception:
        return str(date_val)[:10] if date_val else ""


def _render_wage_vs_sales_charts(detail_rows: list, total_wages: float, total_sales: float, target_pct: float = 25.0):
    """Render gauge chart (wage % vs target) and horizontal bar (employee comparison) for Wage vs Sales data."""
    from collections import defaultdict
    import plotly.graph_objects as go

    wage_pct = (total_wages / total_sales * 100) if total_sales > 0 else 0.0

    # Gauge chart
    fig_gauge = go.Figure(go.Indicator(
        mode="gauge+number",
        value=wage_pct,
        number={"suffix": "%"},
        title={"text": "Wage % of Sales"},
        gauge={
            "axis": {"range": [0, 50], "tickwidth": 1},
            "bar": {"color": "#1f77b4"},
            "bgcolor": "white",
            "borderwidth": 2,
            "bordercolor": "gray",
            "steps": [
                {"range": [0, target_pct - 1], "color": "#90EE90"},
                {"range": [target_pct - 1, target_pct + 1], "color": "#FFD700"},
                {"range": [target_pct + 1, 50], "color": "#FFB6C1"},
            ],
            "threshold": {
                "line": {"color": "red", "width": 3},
                "thickness": 0.75,
                "value": target_pct,
            },
        },
    ))
    fig_gauge.update_layout(
        height=220,
        margin=dict(l=20, r=20, t=50, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(size=14),
    )

    # Horizontal bar: employee wage % comparison
    by_emp = defaultdict(lambda: {"wages": 0.0, "sales": 0.0})
    for r in detail_rows:
        emp = r.get("Employee", "")
        by_emp[emp]["wages"] += r.get("_wages_raw", 0)
        by_emp[emp]["sales"] += r.get("_sales_raw", 0)
    emp_data = []
    for emp, data in by_emp.items():
        pct = (data["wages"] / data["sales"] * 100) if data["sales"] > 0 else 0.0
        emp_data.append({"Employee": emp, "Wage %": round(pct, 2), "Total Wages": data["wages"], "Total Sales": data["sales"]})
    emp_data.sort(key=lambda x: x["Wage %"], reverse=True)

    fig_bar = None
    if emp_data:
        fig_bar = go.Figure(go.Bar(
            x=[d["Wage %"] for d in emp_data],
            y=[d["Employee"] for d in emp_data],
            orientation="h",
            marker_color=["#90EE90" if d["Wage %"] < target_pct - 1 else "#FFD700" if d["Wage %"] <= target_pct + 1 else "#FFB6C1" for d in emp_data],
            text=[f"{d['Wage %']:.1f}%" for d in emp_data],
            textposition="outside",
        ))
        fig_bar.add_vline(x=target_pct, line_dash="dash", line_color="red", annotation_text="Target 25%")
        fig_bar.update_layout(
            title="Wage % by Employee",
            xaxis_title="Wage %",
            yaxis_title="",
            height=200 + len(emp_data) * 28,
            margin=dict(l=10, r=60),
            showlegend=False,
            xaxis=dict(range=[0, max((d["Wage %"] for d in emp_data), default=30) * 1.2]),
            paper_bgcolor="rgba(0,0,0,0)",
        )
        fig_bar.update_yaxes(autorange="reversed")

    # Side-by-side layout
    col_gauge, col_bar = st.columns([1, 1])
    with col_gauge:
        st.plotly_chart(fig_gauge, width="stretch")
    with col_bar:
        if fig_bar is not None:
            st.plotly_chart(fig_bar, width="stretch")


@st.cache_data(ttl=60)
def load_monthly_bonuses(shop_key: str, year: int, month: int, shop_filter_override: Optional[str] = None) -> Dict:
    """Load monthly bonuses from Airtable (Monthly Bonuses table) for a specific month."""
    base_id, api_key, _ = _get_airtable_credentials(shop_key)
    if not base_id or not api_key:
        return {}
    config = load_config()
    shop_config = (config or {}).get("shops", {}).get(shop_key, {})
    shop_display = shop_filter_override or shop_config.get("shop_display_name") or shop_config.get("name", shop_key)
    tables = (config or {}).get("airtable_config_tables", {})
    bonus_table = tables.get("monthly_bonus", "Monthly Bonuses")
    emp_table = tables.get("employees", "Employees")
    try:
        client = AirtableClient(api_key=api_key)
        id_to_name = client._get_employee_id_to_name(base_id, emp_table, shop_display)
        return client.get_monthly_bonuses(
            base_id, bonus_table, year, month,
            shop_display_name=shop_display,
            employee_id_to_name=id_to_name,
        )
    except Exception as e:
        logger.warning("Airtable load_monthly_bonuses failed: %s", e)
        return {}


def save_monthly_bonuses(shop_key: str, year: int, month: int, bonuses: Dict, shop_filter_override: Optional[str] = None) -> tuple[bool, Optional[str]]:
    """
    Save monthly bonuses to Airtable (Monthly Bonuses table).
    Returns (success: bool, error_message: Optional[str]).
    """
    base_id, api_key, _ = _get_airtable_credentials(shop_key)
    if not base_id or not api_key:
        msg = "Cannot save to Airtable: missing credentials. Add [airtable] api_key to .streamlit/secrets.toml or set AIRTABLE_API_KEY."
        logger.warning("Cannot save monthly bonuses: %s", msg)
        return False, msg
    config = load_config()
    shop_config = (config or {}).get("shops", {}).get(shop_key, {})
    shop_display = shop_filter_override or shop_config.get("shop_display_name") or shop_config.get("name", shop_key)
    tables = (config or {}).get("airtable_config_tables", {})
    bonus_table = tables.get("monthly_bonus", "Monthly Bonuses")
    emp_table = tables.get("employees", "Employees")
    try:
        client = AirtableClient(api_key=api_key)
        id_to_name = client._get_employee_id_to_name(base_id, emp_table, shop_display)
        name_to_id = {v: k for k, v in id_to_name.items()}
        client.save_monthly_bonuses(
            base_id, bonus_table, year, month, bonuses,
            employee_name_to_id=name_to_id,
            shop_display_name=shop_display,
        )
        return True, None
    except Exception as e:
        msg = str(e)
        logger.warning("Airtable save_monthly_bonuses failed: %s", msg)
        return False, msg


@st.cache_data(ttl=60)
def load_shop_targets() -> Dict:
    """Load saved monthly sales targets per shop from Airtable."""
    base_id, api_key, tables = _get_airtable_credentials()
    if not base_id or not api_key or not tables:
        return {}
    try:
        client = AirtableClient(api_key=api_key)
        return client.get_shop_targets(base_id, tables[0])
    except Exception as e:
        logger.warning("Airtable load_shop_targets failed: %s", e)
        return {}


def save_shop_targets(targets: Dict) -> Tuple[bool, Optional[str]]:
    """
    Persist monthly sales targets per shop to Airtable.
    Returns (success, error_message). error_message is None on success.
    """
    base_id, api_key, tables = _get_airtable_credentials()
    if not base_id or not api_key or not tables:
        msg = "Cannot save shop targets: missing Airtable credentials"
        logger.warning(msg)
        return False, msg
    try:
        client = AirtableClient(api_key=api_key)
        client.save_shop_targets(base_id, tables[0], targets)
        return True, None
    except Exception as e:
        msg = str(e)
        logger.warning("Airtable save_shop_targets failed: %s", msg)
        return False, msg


@st.cache_data(ttl=60)
def _load_wage_vs_sales_for_month(shop_key: str, year: int, month: int, current_date) -> tuple:
    """
    Load wage vs sales totals for the current month (1st to current_date) from Airtable.
    Returns (total_wages, total_sales) or (None, None) if not available.
    """
    base_id, api_key, _ = _get_airtable_credentials(shop_key)
    if not base_id or not api_key:
        return None, None
    config = load_config() or {}
    shop_config = config.get("shops", {}).get(shop_key, {})
    tables_cfg = config.get("airtable_config_tables", {})
    table_name = shop_config.get("wage_vs_sales_table") or tables_cfg.get("wage_vs_sales") or ""
    shop_display = shop_config.get("shop_display_name") or shop_config.get("name", shop_key)
    if not table_name:
        return None, None
    try:
        from datetime import date
        first_of_month = date(year, month, 1)
        date_from = first_of_month.strftime("%Y-%m-%d")
        date_to = current_date.strftime("%Y-%m-%d") if hasattr(current_date, "strftime") else str(current_date)[:10]
        client = AirtableClient(api_key=api_key)
        records = client.get_wage_vs_sales(base_id, table_name, shop=shop_display, date_from=date_from, date_to=date_to)
        total_wages = 0.0
        total_sales = 0.0

        def _safe_float(val):
            if val is None or val == "":
                return 0.0
            try:
                return float(val)
            except (ValueError, TypeError):
                return 0.0

        for r in records:
            base_val = _safe_float(r.get("Base") or r.get("base"))
            commission_val = _safe_float(r.get("Commission") or r.get("commission"))
            total_wages_val = _safe_float(r.get("Total Wages") or r.get("total_wages")) or (base_val + commission_val)
            sales_val = _safe_float(r.get("Sales") or r.get("sales"))
            addl_val = _safe_float(r.get("Add'l Sales") or r.get("AddlSales") or r.get("addl_sales"))
            total_sales_val = _safe_float(r.get("Total Sales") or r.get("total_sales")) or (sales_val + addl_val)
            total_wages += total_wages_val
            total_sales += total_sales_val
        return total_wages, total_sales
    except Exception as e:
        logger.warning("_load_wage_vs_sales_for_month failed: %s", e)
        return None, None


@st.cache_data(ttl=60)
def load_daily_targets() -> Dict:
    """Load saved daily targets per shop from Airtable."""
    base_id, api_key, tables = _get_airtable_credentials()
    if not base_id or not api_key or not tables:
        return {}
    try:
        client = AirtableClient(api_key=api_key)
        return client.get_daily_targets(base_id, tables[1])
    except Exception as e:
        logger.warning("Airtable load_daily_targets failed: %s", e)
        return {}


def save_daily_targets(targets: Dict):
    """Persist daily targets per shop to Airtable."""
    base_id, api_key, tables = _get_airtable_credentials()
    if not base_id or not api_key or not tables:
        logger.warning("Cannot save daily targets: missing Airtable credentials")
        return
    try:
        client = AirtableClient(api_key=api_key)
        client.save_daily_targets(base_id, tables[1], targets)
    except Exception as e:
        logger.warning("Airtable save_daily_targets failed: %s", e)


def get_email_client_for_shop(shop_key: str) -> EmailClient:
    """
    Create an EmailClient using per-shop SMTP credentials when available.
    
    Expected Streamlit secrets layout (examples):
    
    ```toml
    [email_pyt]
    SMTP_USER = "pythairstyleco@gmail.com"
    SMTP_PASSWORD = "app_password_for_pyt"
    
    [email_opatra]
    SMTP_USER = "invoices.opulent@gmail.com"
    SMTP_PASSWORD = "app_password_for_opatra"
    ```
    
    If a section for the given shop key (e.g. `email_pyt`, `email_opatra`)
    is not found, falls back to global SMTP_* env vars.
    """
    smtp_user = None
    smtp_password = None
    
    # Try per-shop Streamlit secrets: [email_pyt], [email_opatra], etc.
    try:
        if hasattr(st, "secrets"):
            section_name = f"email_{shop_key}"
            if section_name in st.secrets:
                sect = st.secrets[section_name]
                # Support either upper- or lower-case keys
                smtp_user = sect.get("SMTP_USER") or sect.get("smtp_user")
                smtp_password = sect.get("SMTP_PASSWORD") or sect.get("smtp_password")
    except Exception:
        # If anything goes wrong with reading secrets, we just fall back to defaults
        smtp_user = None
        smtp_password = None
    
    if smtp_user and smtp_password:
        return EmailClient(smtp_user=smtp_user, smtp_password=smtp_password)
    
    # Fall back to global env-based configuration
    return EmailClient()


def hash_password(password: str, salt: str = None) -> tuple:
    """Hash a password using SHA-256 with salt. Returns (hash, salt)"""
    if salt is None:
        salt = secrets.token_hex(16)
    password_bytes = password.encode('utf-8')
    salt_bytes = salt.encode('utf-8')
    hash_obj = hashlib.sha256(salt_bytes + password_bytes)
    return hash_obj.hexdigest(), salt


def verify_password(password: str, stored_hash: str, salt: str = None) -> bool:
    """Verify a password against a stored hash"""
    try:
        # If stored_hash contains salt (format: "hash:salt"), split it
        if ':' in stored_hash:
            stored_hash, salt = stored_hash.split(':', 1)
        
        if salt is None:
            # Try to extract salt from stored_hash if it's in a different format
            # For backward compatibility, if no salt, use empty salt
            salt = ''
        
        # Hash the provided password with the salt
        computed_hash, _ = hash_password(password, salt)
        return computed_hash == stored_hash
    except Exception as e:
        logger.error(f"Password verification error: {e}")
        return False


def _emp_name_to_id_map(client, base_id, emp_table, shop_display) -> Dict[str, str]:
    """Build {employee_name: record_id} for linked record fields."""
    records = client.get_employee_records_with_ids(base_id, emp_table, shop_display_name=shop_display, active_only=False)
    return {r.get("Name", ""): r.get("id") for r in records if r.get("Name")}


def _render_employees_tab(client, base_id, tables_cfg, shop_display, shop_options, payment_types, config):
    emp_table = tables_cfg.get("employees", "Employees")
    try:
        records = client.get_employee_records_with_ids(base_id, emp_table, shop_display_name=shop_display, active_only=False)
    except Exception as e:
        st.error(f"❌ Failed to load: {e}")
        records = []
    editable_cols = ["Name", "Shop", "Date of Birth", "Email", "Payment Type", "Hourly Rate Override", "Commission Rate", "Base Monthly Amount", "Base Reference Days", "Shop Commission Rate", "Daily Transport", "Rent", "Advance", "Employment", "Employment Status"]
    num_cols = ("Hourly Rate Override", "Commission Rate", "Daily Transport", "Rent", "Advance")
    # Build canonical -> actual Airtable field name mapping (Airtable is case-sensitive)
    col_to_airtable = {}
    if records:
        all_keys = set()
        for r in records:
            all_keys.update(k for k in r.keys() if k != "id")
        for col in editable_cols:
            if col in all_keys:
                col_to_airtable[col] = col
            else:
                low = col.lower()
                match = next((k for k in all_keys if k.lower() == low), col)
                col_to_airtable[col] = match
    if records:
        rows = []
        for r in records:
            row = {"_id": r.get("id", "")}
            for col in editable_cols:
                airtable_key = col_to_airtable.get(col, col)
                val = r.get(airtable_key)
                raw = "" if val is None else (", ".join(str(x) for x in val) if isinstance(val, list) else str(val).strip())
                # Employment Status must be in SelectboxColumn options or edits won't save
                if col == "Employment Status":
                    row[col] = raw if raw in ("Active", "Inactive") else ("Inactive" if raw.lower() == "inactive" else "Active")
                elif col == "Employment":
                    row[col] = raw if raw in ("", "Consultancy", "Payroll") else raw
                else:
                    row[col] = raw
            rows.append(row)
        df = pd.DataFrame(rows)
        id_col, edit_df = df["_id"], df.drop(columns=["_id"])
        col_config = {
            "Name": st.column_config.TextColumn("Name", required=True),
            "Shop": st.column_config.TextColumn("Shop", help="Comma-separated shops, e.g. PYT, Opatra", required=True),
            "Date of Birth": st.column_config.TextColumn("Date of Birth"),
            "Email": st.column_config.TextColumn("Email"),
            "Payment Type": st.column_config.SelectboxColumn("Payment Type", options=payment_types),
            "Hourly Rate Override": st.column_config.NumberColumn("Hourly Rate", format="%.2f"),
            "Commission Rate": st.column_config.NumberColumn("Commission Rate", format="%.2f"),
            "Daily Transport": st.column_config.NumberColumn("Daily Transport", format="%.2f"),
            "Rent": st.column_config.NumberColumn("Rent", format="%.2f"),
            "Advance": st.column_config.NumberColumn("Advance", format="%.2f"),
            "Employment": st.column_config.SelectboxColumn(
                "Employment",
                options=["", "Consultancy", "Payroll"],
                help="Consultancy / Payroll (invoice emails); blank = same as Consultancy",
            ),
            "Employment Status": st.column_config.SelectboxColumn("Employment Status", options=["Active", "Inactive"]),
        }
        edited = st.data_editor(edit_df, column_config=col_config, width="stretch", num_rows="fixed", key="dm_emp_editor")
        if st.button("💾 Save changes", type="primary", key="dm_emp_save"):
            changed, errors = 0, []
            for i in range(len(edited)):
                row = edited.iloc[i]
                orig_row = edit_df.iloc[i]  # Same row order as edited
                if orig_row.to_dict() != row.to_dict():
                    record_id = id_col.iloc[i] if i < len(id_col) else None
                    if not record_id:
                        errors.append(f"{row.get('Name', '?')}: Could not find record ID")
                        continue
                    fields = {}
                    for k, v in row.items():
                        if k in editable_cols:
                            airtable_key = col_to_airtable.get(k, k)
                            if v == "" or (isinstance(v, float) and pd.isna(v)):
                                fields[airtable_key] = None
                            elif k == "Shop":
                                # Multi-select: parse "PYT, Opatra" -> ["PYT", "Opatra"]
                                parts = [x.strip() for x in str(v).split(",") if x.strip()]
                                fields[airtable_key] = [p for p in parts if p in shop_options] if parts else None
                            elif k in num_cols:
                                try: fields[airtable_key] = float(v)
                                except (TypeError, ValueError): fields[airtable_key] = v
                            else:
                                fields[airtable_key] = str(v).strip()
                    try:
                        client.update_record(base_id, emp_table, record_id, fields)
                        changed += 1
                    except Exception as ex:
                        errors.append(f"{row.get('Name', '?')}: {ex}")
            for e in errors:
                st.error(e)
            if changed:
                st.success(f"✅ Updated {changed}.")
                st.cache_data.clear()
                st.rerun()
        with st.expander("➕ Add employee"):
            with st.form("dm_add_emp"):
                n1, n2 = st.columns(2)
                with n1:
                    na = st.text_input("Name", key="dm_emp_na")
                    em = st.text_input("Email", key="dm_emp_em")
                    dob = st.date_input(
                        "Date of Birth",
                        value=None,
                        min_value=date(1900, 1, 1),
                        max_value=date.today(),
                        key="dm_emp_dob",
                    )
                    sh = st.multiselect("Shop", shop_options, key="dm_emp_sh")
                    pt = st.selectbox("Payment Type", payment_types, key="dm_emp_pt")
                    sts = st.selectbox("Employment Status", ["Active", "Inactive"], key="dm_emp_sts")
                    eng = st.selectbox(
                        "Employment (invoice vs payroll email)",
                        ["", "Consultancy", "Payroll"],
                        format_func=lambda x: "—" if x == "" else x,
                        key="dm_emp_eng",
                    )
                with n2:
                    hr = st.number_input("Hourly Rate", value=0.0, step=0.01, format="%.2f", key="dm_emp_hr")
                    cr = st.number_input("Commission Rate", value=0.0, step=0.01, format="%.2f", key="dm_emp_cr")
                    dt = st.number_input("Daily Transport", value=0.0, step=0.01, format="%.2f", key="dm_emp_dt")
                if st.form_submit_button("Add"):
                    if na and na.strip() and sh:
                        flds = {"Name": na.strip(), "Shop": sh, "Payment Type": pt, "Employment Status": sts}
                        if eng:
                            flds["Employment"] = eng
                        if em.strip(): flds["Email"] = em.strip()
                        if dob: flds["Date of Birth"] = dob.strftime("%Y-%m-%d")
                        if hr: flds["Hourly Rate Override"] = hr
                        if cr: flds["Commission Rate"] = cr
                        if dt: flds["Daily Transport"] = dt
                        try:
                            client.create_record(base_id, emp_table, flds)
                            st.success("✅ Added.")
                            st.cache_data.clear()
                            st.rerun()
                        except Exception as ex:
                            st.error(str(ex))
        to_del = st.multiselect("Delete", options=[r.get("Name", "?") for r in records], key="dm_emp_del")
        if to_del and st.button("🗑️ Delete selected", key="dm_emp_del_btn"):
            ids = [r["id"] for r in records if r.get("Name") in to_del]
            if ids:
                client.batch_delete_records(base_id, emp_table, ids)
                st.success(f"✅ Deleted {len(ids)}.")
                st.cache_data.clear()
                st.rerun()
    else:
        st.warning("No employees. Add one:")
        with st.form("dm_add_first_emp"):
            na = st.text_input("Name", key="dm_first_na")
            sh = st.multiselect("Shop", shop_options, key="dm_first_sh")
            if st.form_submit_button("Add"):
                if na and na.strip() and sh:
                    client.create_record(base_id, emp_table, {"Name": na.strip(), "Shop": sh, "Payment Type": "hourly_only"})
                    st.cache_data.clear()
                    st.rerun()


def _render_commission_tiers_tab(client, base_id, tables_cfg, shop_display, shop_options, config):
    tiers_table = tables_cfg.get("commission_tiers", "Commission Tiers")
    emp_table = tables_cfg.get("employees", "Employees")
    name_to_id = _emp_name_to_id_map(client, base_id, emp_table, shop_display)
    id_to_name = {v: k for k, v in name_to_id.items()}
    shop_esc = (shop_display or "").replace('\\', '\\\\').replace('"', '\\"')
    formula = client._shop_filter_formula("Shop (from Employees)", shop_esc) if shop_display else None
    try:
        records = client.get_records_with_ids(base_id, tiers_table, formula=formula)
    except Exception:
        records = client.get_records_with_ids(base_id, tiers_table)
    editable_cols = ["Tier Order", "Threshold", "Rate", "Max", "Net Sales Percentage", "Employees"]
    num_cols = ("Tier Order", "Threshold", "Rate", "Max", "Net Sales Percentage")
    if records:
        rows = []
        for r in records:
            emp_ids = r.get("Employees") or []
            emp_name = id_to_name.get(emp_ids[0]) if isinstance(emp_ids, list) and emp_ids else (emp_ids if isinstance(emp_ids, str) else "")
            row = {"_id": r.get("id", ""), "Employees": emp_name or ""}
            for c in ["Tier Order", "Threshold", "Rate", "Max", "Net Sales Percentage"]:
                v = r.get(c)
                row[c] = v if v is not None and v != "" else ("" if c != "Tier Order" else "1")
            rows.append(row)
        df = pd.DataFrame(rows)
        id_col, edit_df = df["_id"], df.drop(columns=["_id"])
        col_config = {
            "Tier Order": st.column_config.NumberColumn("Tier Order", format="%.0f"),
            "Threshold": st.column_config.NumberColumn("Threshold", format="%.2f"),
            "Rate": st.column_config.NumberColumn("Rate", format="%.2f"),
            "Max": st.column_config.NumberColumn("Max", format="%.2f"),
            "Net Sales Percentage": st.column_config.NumberColumn("Net %", format="%.2f"),
            "Employees": st.column_config.SelectboxColumn("Employee", options=sorted(name_to_id.keys())),
        }
        edited = st.data_editor(edit_df, column_config=col_config, width="stretch", num_rows="fixed", key="dm_ct_editor")
        if st.button("💾 Save changes", type="primary", key="dm_ct_save"):
            changed = 0
            for i in range(len(edited)):
                new = edited.iloc[i]
                emp_name = str(new.get("Employees", "")).strip()
                emp_id = name_to_id.get(emp_name)
                fields = {"Tier Order": float(new.get("Tier Order") or 1), "Threshold": float(new.get("Threshold") or 0), "Rate": float(new.get("Rate") or 0)}
                if new.get("Max") not in (None, "", float("nan")):
                    try: fields["Max"] = float(new["Max"])
                    except (TypeError, ValueError): pass
                if new.get("Net Sales Percentage") not in (None, "", float("nan")):
                    try: fields["Net Sales Percentage"] = float(new["Net Sales Percentage"])
                    except (TypeError, ValueError): pass
                if emp_id:
                    fields["Employees"] = [emp_id]
                try:
                    client.update_record(base_id, tiers_table, id_col.iloc[i], fields)
                    changed += 1
                except Exception as ex:
                    st.error(str(ex))
            if changed:
                st.cache_data.clear()
                st.rerun()
        with st.expander("➕ Add tier"):
            with st.form("dm_add_ct"):
                emp = st.selectbox("Employee", sorted(name_to_id.keys()), key="dm_ct_emp")
                to = st.number_input("Tier Order", value=1, min_value=1, key="dm_ct_to")
                th = st.number_input("Threshold", value=0.0, step=0.01, format="%.2f", key="dm_ct_th")
                rt = st.number_input("Rate", value=0.0, step=0.01, format="%.2f", key="dm_ct_rt")
                mx = st.number_input("Max (optional)", value=0.0, step=0.01, format="%.2f", key="dm_ct_mx")
                if st.form_submit_button("Add"):
                    flds = {"Tier Order": to, "Threshold": th, "Rate": rt, "Employees": [name_to_id[emp]]}
                    if mx: flds["Max"] = mx
                    client.create_record(base_id, tiers_table, flds)
                    st.cache_data.clear()
                    st.rerun()
        to_del = st.multiselect("Delete rows by index", options=list(range(len(records))), key="dm_ct_del")
        if to_del and st.button("🗑️ Delete selected", key="dm_ct_del_btn"):
            ids = [id_col.iloc[i] for i in to_del]
            client.batch_delete_records(base_id, tiers_table, ids)
            st.cache_data.clear()
            st.rerun()
    else:
        st.warning("No commission tiers. Add one:")
        with st.form("dm_add_first_ct"):
            emp = st.selectbox("Employee", sorted(name_to_id.keys()) if name_to_id else ["(No employees)"], key="dm_first_ct_emp")
            if st.form_submit_button("Add") and emp and emp != "(No employees)":
                client.create_record(base_id, tiers_table, {"Tier Order": 1, "Threshold": 0, "Rate": 0.2, "Employees": [name_to_id[emp]]})
                st.cache_data.clear()
                st.rerun()


def _render_name_mappings_tab(client, base_id, tables_cfg, shop_display, shop_options, config):
    mappings_table = tables_cfg.get("name_mappings", "Name Mappings")
    emp_table = tables_cfg.get("employees", "Employees")
    name_to_id = _emp_name_to_id_map(client, base_id, emp_table, shop_display)
    emp_recs = client.get_employee_records_with_ids(base_id, emp_table, shop_display_name=None, active_only=False)
    id_to_name = {r["id"]: r.get("Name", "") for r in emp_recs if r.get("Name")}
    shop_esc = (shop_display or "").replace('\\', '\\\\').replace('"', '\\"')
    formula = client._shop_filter_formula("Shop", shop_esc) if shop_display else None
    records = client.get_records_with_ids(base_id, mappings_table, formula=formula)
    editable_cols = ["Report Name", "Employees", "Shop"]
    if records:
        rows = []
        for r in records:
            emp_ids = r.get("Employees") or []
            emp_id = emp_ids[0] if isinstance(emp_ids, list) and emp_ids else (emp_ids if isinstance(emp_ids, str) else None)
            emp_name = id_to_name.get(emp_id, "") if emp_id else ""
            shop_val = r.get("Shop")
            if isinstance(shop_val, list) and shop_val:
                shop_str = ", ".join(str(x) for x in shop_val)
            else:
                shop_str = str(shop_val) if shop_val else (shop_display or "")
            rows.append({"_id": r.get("id"), "Report Name": r.get("Report Name") or "", "Employees": emp_name, "Shop": shop_str})
        df = pd.DataFrame(rows)
        id_col, edit_df = df["_id"], df.drop(columns=["_id"])
        edited = st.data_editor(edit_df, column_config={"Report Name": st.column_config.TextColumn("Report Name"), "Employees": st.column_config.SelectboxColumn("Employee", options=sorted(name_to_id.keys())), "Shop": st.column_config.SelectboxColumn("Shop", options=shop_options)}, width="stretch", num_rows="fixed", key="dm_nm_editor")
        if st.button("💾 Save changes", key="dm_nm_save"):
            for i in range(len(edited)):
                new = edited.iloc[i]
                emp_id = name_to_id.get(str(new.get("Employees", "")).strip())
                flds = {"Report Name": str(new.get("Report Name", "")).strip(), "Shop": new.get("Shop") or shop_display}
                if emp_id:
                    flds["Employees"] = [emp_id]
                client.update_record(base_id, mappings_table, id_col.iloc[i], flds)
            st.cache_data.clear()
            st.rerun()
        with st.expander("➕ Add mapping"):
            with st.form("dm_add_nm"):
                rn = st.text_input("Report Name", key="dm_nm_rn")
                emp = st.selectbox("Employee", sorted(name_to_id.keys()), key="dm_nm_emp")
                sh = st.selectbox("Shop", shop_options, key="dm_nm_sh")
                if st.form_submit_button("Add") and rn and rn.strip():
                    client.create_record(base_id, mappings_table, {"Report Name": rn.strip(), "Employees": [name_to_id[emp]], "Shop": sh})
                    st.cache_data.clear()
                    st.rerun()
        to_del = st.multiselect("Delete", options=[r.get("Report Name", "?") for r in records], key="dm_nm_del")
        if to_del and st.button("🗑️ Delete selected", key="dm_nm_del_btn"):
            ids = [r["id"] for r in records if r.get("Report Name") in to_del]
            if ids:
                client.batch_delete_records(base_id, mappings_table, ids)
                st.cache_data.clear()
                st.rerun()
    else:
        st.warning("No name mappings.")
        with st.form("dm_add_first_nm"):
            rn = st.text_input("Report Name", key="dm_first_nm_rn")
            emp = st.selectbox("Employee", sorted(name_to_id.keys()) if name_to_id else ["(None)"], key="dm_first_nm_emp")
            if st.form_submit_button("Add") and rn and emp != "(None)":
                client.create_record(base_id, mappings_table, {"Report Name": rn.strip(), "Employees": [name_to_id[emp]], "Shop": shop_display})
                st.cache_data.clear()
                st.rerun()


def _render_sales_bonus_tab(client, base_id, tables_cfg, shop_display, shop_options, config):
    bonus_table = tables_cfg.get("sales_bonus_thresholds", "Sales Bonus Thresholds")
    emp_table = tables_cfg.get("employees", "Employees")
    name_to_id = _emp_name_to_id_map(client, base_id, emp_table, shop_display)
    emp_recs = client.get_employee_records_with_ids(base_id, emp_table, active_only=False)
    id_to_name = {x["id"]: x.get("Name", "") for x in emp_recs}
    shop_esc = (shop_display or "").replace('\\', '\\\\').replace('"', '\\"')
    formula = client._shop_filter_formula("Shop", shop_esc) if shop_display else None
    records = client.get_records_with_ids(base_id, bonus_table, formula=formula)
    months = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
    if records:
        rows = []
        for r in records:
            emp_ids = r.get("Employees") or r.get("Employee")
            emp_name = ""
            if isinstance(emp_ids, list) and emp_ids:
                emp_name = id_to_name.get(emp_ids[0], "")
            elif isinstance(emp_ids, str):
                emp_name = emp_ids
            rows.append({"_id": r.get("id"), "Month": r.get("Month") or "", "Employees": emp_name, "Sales Threshold": r.get("Sales Threshold") or 0, "Bonus Amount": r.get("Bonus Amount") or 0})
        df = pd.DataFrame(rows)
        id_col, edit_df = df["_id"], df.drop(columns=["_id"])
        edited = st.data_editor(edit_df, column_config={"Month": st.column_config.SelectboxColumn("Month", options=months), "Employees": st.column_config.SelectboxColumn("Employee", options=sorted(name_to_id.keys())), "Sales Threshold": st.column_config.NumberColumn("Sales Threshold", format="%.2f"), "Bonus Amount": st.column_config.NumberColumn("Bonus Amount", format="%.2f")}, width="stretch", num_rows="fixed", key="dm_sb_editor")
        if st.button("💾 Save changes", key="dm_sb_save"):
            for i in range(len(edited)):
                new = edited.iloc[i]
                emp_id = name_to_id.get(str(new.get("Employees", "")).strip())
                flds = {"Month": str(new.get("Month", "")).strip().lower(), "Shop": shop_display, "Sales Threshold": float(new.get("Sales Threshold") or 0), "Bonus Amount": float(new.get("Bonus Amount") or 0)}
                if emp_id:
                    flds["Employees"] = [emp_id]
                client.update_record(base_id, bonus_table, id_col.iloc[i], flds)
            st.cache_data.clear()
            st.rerun()
        with st.expander("➕ Add threshold"):
            with st.form("dm_add_sb"):
                mon = st.selectbox("Month", months, key="dm_sb_mon")
                emp = st.selectbox("Employee", sorted(name_to_id.keys()), key="dm_sb_emp")
                st_val = st.number_input("Sales Threshold", value=0.0, step=100.0, format="%.2f", key="dm_sb_st")
                ba_val = st.number_input("Bonus Amount", value=0.0, step=10.0, format="%.2f", key="dm_sb_ba")
                if st.form_submit_button("Add"):
                    client.create_record(base_id, bonus_table, {"Month": mon, "Shop": shop_display, "Employees": [name_to_id[emp]], "Sales Threshold": st_val, "Bonus Amount": ba_val})
                    st.cache_data.clear()
                    st.rerun()
        del_opts = [f"{row['Month']}-{row['Employees']}-{row['Sales Threshold']}" for row in rows]
        to_del = st.multiselect("Delete", options=del_opts, key="dm_sb_del")
        if to_del and st.button("🗑️ Delete selected", key="dm_sb_del_btn"):
            keys = {f"{row['Month']}-{row['Employees']}-{row['Sales Threshold']}": row["_id"] for row in rows}
            ids = [keys[k] for k in to_del if k in keys]
            if ids:
                client.batch_delete_records(base_id, bonus_table, ids)
                st.cache_data.clear()
                st.rerun()
    else:
        st.warning("No sales bonus thresholds.")


def _render_monthly_bonuses_tab(client, base_id, tables_cfg, shop_display, shop_options, config):
    bonus_table = tables_cfg.get("monthly_bonus", "Monthly Bonuses")
    emp_table = tables_cfg.get("employees", "Employees")
    name_to_id = _emp_name_to_id_map(client, base_id, emp_table, shop_display)
    emp_recs = client.get_employee_records_with_ids(base_id, emp_table, active_only=False)
    id_to_name = {x["id"]: x.get("Name", "") for x in emp_recs}
    shop_esc = (shop_display or "").replace('\\', '\\\\').replace('"', '\\"')
    formula = client._shop_filter_formula("Shop", shop_esc) if shop_display else None
    records = client.get_records_with_ids(base_id, bonus_table, formula=formula)
    bonus_fields = ["Daily Sales Bonus", "First Last Hour Bonus", "Social Media Bonus", "Management Bonus", "Management Consistency Bonus", "Transport Fuel", "Personal Sales Bonus", "Extra Bonus", "Daily Allowance", "Manual Hours", "Deductions", "Rent", "Advance"]
    if records:
        rows = []
        for r in records:
            emp_ids = r.get("Employees") or r.get("Employee")
            emp_name = ""
            if isinstance(emp_ids, list) and emp_ids:
                emp_name = id_to_name.get(emp_ids[0], r.get("Employee", ""))
            else:
                emp_name = emp_ids or r.get("Employee", "")
            row = {"_id": r.get("id"), "Month": r.get("Month") or "", "Employees": emp_name}
            for bf in bonus_fields:
                row[bf] = r.get(bf) or 0
            rows.append(row)
        df = pd.DataFrame(rows)
        id_col, edit_df = df["_id"], df.drop(columns=["_id"])
        col_cfg = {"Month": st.column_config.TextColumn("Month (YYYY-MM)"), "Employees": st.column_config.SelectboxColumn("Employee", options=sorted(name_to_id.keys()))}
        for bf in bonus_fields:
            col_cfg[bf] = st.column_config.NumberColumn(bf, format="%.2f")
        edited = st.data_editor(edit_df, column_config=col_cfg, width="stretch", num_rows="fixed", key="dm_mb_editor")
        if st.button("💾 Save changes", key="dm_mb_save"):
            for i in range(len(edited)):
                new = edited.iloc[i]
                emp_id = name_to_id.get(str(new.get("Employees", "")).strip())
                flds = {"Month": str(new.get("Month", "")).strip(), "Shop": shop_display}
                if emp_id:
                    flds["Employees"] = [emp_id]
                for bf in bonus_fields:
                    v = new.get(bf)
                    flds[bf] = float(v) if v is not None and v != "" and not (isinstance(v, float) and pd.isna(v)) else 0
                client.update_record(base_id, bonus_table, id_col.iloc[i], flds)
            st.cache_data.clear()
            st.rerun()
        with st.expander("➕ Add monthly bonus"):
            with st.form("dm_add_mb"):
                mon = st.text_input("Month (YYYY-MM)", value=datetime.now().strftime("%Y-%m"), key="dm_mb_mon")
                emp = st.selectbox("Employee", sorted(name_to_id.keys()), key="dm_mb_emp")
                if st.form_submit_button("Add"):
                    client.create_record(base_id, bonus_table, {"Month": mon, "Shop": shop_display, "Employees": [name_to_id[emp]]})
                    st.cache_data.clear()
                    st.rerun()
        del_opts = [f"{row['Month']}-{row['Employees']}" for row in rows]
        to_del = st.multiselect("Delete", options=del_opts, key="dm_mb_del")
        if to_del and st.button("🗑️ Delete selected", key="dm_mb_del_btn"):
            keys = {f"{row['Month']}-{row['Employees']}": row["_id"] for row in rows}
            ids = [keys[k] for k in to_del if k in keys]
            if ids:
                client.batch_delete_records(base_id, bonus_table, ids)
                st.cache_data.clear()
                st.rerun()
    else:
        st.warning("No monthly bonuses.")


def _render_wage_bracket_tab(client, base_id, tables_cfg):
    wb_table = tables_cfg.get("uk_wage_bracket", "UK Wage Bracket")
    records = client.get_records_with_ids(base_id, wb_table)
    editable_cols = ["Age Band", "Hourly Rate", "Effective From", "Effective To"]
    text_cols = ["Age Band", "Effective From", "Effective To"]
    if records:
        rows = []
        for r in records:
            row = {"_id": r.get("id")}
            for c in editable_cols:
                v = r.get(c)
                if c == "Hourly Rate":
                    row[c] = float(v) if v is not None and v != "" else 0.0
                else:
                    row[c] = v if v is not None and v != "" else ""
            rows.append(row)
        df = pd.DataFrame(rows)
        id_col, edit_df = df["_id"], df.drop(columns=["_id"])
        col_config = {c: st.column_config.TextColumn(c) for c in text_cols}
        col_config["Hourly Rate"] = st.column_config.NumberColumn("Hourly Rate", format="%.2f")
        edited = st.data_editor(edit_df, column_config=col_config, width="stretch", num_rows="fixed", key="dm_wb_editor")
        if st.button("💾 Save changes", key="dm_wb_save"):
            for i in range(len(edited)):
                flds = {}
                for c in editable_cols:
                    v = edited.iloc[i][c]
                    if c == "Hourly Rate":
                        flds[c] = float(v) if v is not None and not (isinstance(v, float) and pd.isna(v)) else 0.0
                    else:
                        s = str(v).strip() if v is not None else ""
                        flds[c] = s or None
                client.update_record(base_id, wb_table, id_col.iloc[i], flds)
            st.cache_data.clear()
            st.rerun()
        with st.expander("➕ Add bracket"):
            with st.form("dm_add_wb"):
                ab = st.text_input("Age Band (e.g. 21+)", key="dm_wb_ab")
                hr = st.number_input("Hourly Rate", value=0.0, step=0.01, format="%.2f", key="dm_wb_hr")
                ef = st.text_input("Effective From (YYYY-MM-DD)", key="dm_wb_ef")
                et = st.text_input("Effective To (optional)", key="dm_wb_et")
                if st.form_submit_button("Add") and ab and ab.strip():
                    flds = {"Age Band": ab.strip(), "Hourly Rate": hr}
                    if ef.strip(): flds["Effective From"] = ef.strip()
                    if et.strip(): flds["Effective To"] = et.strip()
                    client.create_record(base_id, wb_table, flds)
                    st.cache_data.clear()
                    st.rerun()
        to_del = st.multiselect("Delete", options=[f"{r.get('Age Band')}-{r.get('Effective From')}" for r in records], key="dm_wb_del")
        if to_del and st.button("🗑️ Delete selected", key="dm_wb_del_btn"):
            keys = {f"{r.get('Age Band')}-{r.get('Effective From')}": r["id"] for r in records}
            ids = [keys[k] for k in to_del if k in keys]
            if ids:
                client.batch_delete_records(base_id, wb_table, ids)
                st.cache_data.clear()
                st.rerun()
    else:
        st.warning("No wage brackets. Add one:")
        with st.form("dm_add_first_wb"):
            ab = st.text_input("Age Band", key="dm_first_wb_ab")
            hr = st.number_input("Hourly Rate", value=11.44, step=0.01, format="%.2f", key="dm_first_wb_hr")
            if st.form_submit_button("Add") and ab and ab.strip():
                client.create_record(base_id, wb_table, {"Age Band": ab.strip(), "Hourly Rate": hr})
                st.cache_data.clear()
                st.rerun()


def setup_authentication():
    """
    Set up and handle user authentication.
    Returns True if user is authenticated, False otherwise.
    """
    # Check if already authenticated in this session
    if st.session_state.get('authentication_status') == True:
        # Show logout button
        with st.sidebar:
            st.markdown("---")
            if st.button("🚪 Logout", width="stretch"):
                st.session_state.authentication_status = None
                st.session_state.name = None
                st.session_state.username = None
                st.rerun()
        return True
    
    # Try to get credentials from Streamlit secrets
    try:
        if hasattr(st, 'secrets') and 'credentials' in st.secrets:
            credentials = st.secrets['credentials']
            usernames = credentials.get('usernames', {})
        else:
            # Fallback: use environment variables or default credentials
            logger.warning("No credentials found in secrets. Using default/fallback authentication.")
            default_username = os.getenv('ADMIN_USERNAME', 'admin')
            default_password = os.getenv('ADMIN_PASSWORD', '')
            
            if not default_password:
                st.error("⚠️ **Authentication not configured!**")
                st.info("""
                Please configure authentication by adding credentials to `.streamlit/secrets.toml`:
                
                ```toml
                [credentials]
                usernames = { "admin" = { "name" = "Administrator", "password" = "$2b$12$..." } }
                ```
                
                Or set environment variables:
                - `ADMIN_USERNAME` (default: 'admin')
                - `ADMIN_PASSWORD` (hashed password)
                
                To generate a password hash, run:
                ```python
                python setup_auth.py
                ```
                Or manually:
                ```python
                import hashlib, secrets
                password = "your_password"
                salt = secrets.token_hex(16)
                hash_obj = hashlib.sha256(salt.encode() + password.encode())
                print(f"{hash_obj.hexdigest()}:{salt}")
                ```
                """)
                return False
            
            # Create credentials dict from environment variables
            # Check if password is already hashed (format: "hash:salt" or just "hash")
            if ':' in default_password or len(default_password) == 64:
                # Password is already hashed, use as-is
                hashed_password = default_password
            else:
                # Password is plain text, hash it (for development convenience only)
                logger.warning("Using plain text password from environment - this is less secure. Use a hashed password in production.")
                hashed_password, salt = hash_password(default_password)
                hashed_password = f"{hashed_password}:{salt}"
            
            usernames = {
                default_username: {
                    'name': 'Administrator',
                    'password': hashed_password
                }
            }
    except Exception as e:
        logger.error(f"Error loading authentication credentials: {e}")
        st.error(f"❌ Error loading authentication: {str(e)}")
        return False
    
    # Show login form
    st.title("🔐 Login Required")
    st.markdown("Please enter your credentials to access the Salary Calculation Dashboard")
    
    with st.form("login_form"):
        username = st.text_input("Username", key="login_username")
        password = st.text_input("Password", type="password", key="login_password")
        submitted = st.form_submit_button("Login", type="primary", width="stretch")
        
        if submitted:
            if username in usernames:
                user_data = usernames[username]
                stored_hash = user_data['password']
                
                # Verify password (stored_hash may contain salt in format "hash:salt")
                if verify_password(password, stored_hash):
                    # Authentication successful
                    st.session_state.authentication_status = True
                    st.session_state.name = user_data.get('name', username)
                    st.session_state.username = username
                    st.success(f"✅ Welcome, {st.session_state.name}!")
                    st.rerun()
                else:
                    st.error("❌ Incorrect password")
            else:
                st.error("❌ Username not found")
    
    return False


def main():
    # Check authentication first
    if not setup_authentication():
        st.stop()
    
    st.title("💰 Salary Calculation Dashboard")
    st.markdown("Calculate employee salaries for each shop based on uploaded reports")

    # Make sidebar wider (Report Upload, Shop Select, etc.)
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"][aria-expanded="true"] {
            min-width: 380px !important;
            max-width: 680px !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    
    # Load configuration
    config = load_config()
    if not config:
        st.stop()

    shops = list(config.get('shops', {}).keys())
    if not shops:
        st.error("No shops configured in `config/shops.yaml`. Add at least one shop under the `shops:` key.")
        st.stop()

    # Ensure selected_shop is valid (first load or config changed)
    if 'selected_shop' not in st.session_state or st.session_state.selected_shop not in shops:
        st.session_state.selected_shop = shops[0]

    # Sidebar for shop selection and settings (grouped with expanders)
    with st.sidebar:
        st.header("Settings")

        with st.expander("🏪 Shop & Data Source", expanded=True):
            selected_shop = st.selectbox("Select Shop", shops)
            shop_config = config['shops'][selected_shop]
            # Persist selected shop in session state for use in other tabs (e.g. email sending)
            st.session_state.selected_shop = selected_shop

            st.markdown("---")
            st.subheader("📁 Report Upload")

            # Only support file upload as the data source
            uploaded_file = st.file_uploader(
                "Upload Report File",
                type=['csv', 'xlsx'],
                help="Upload the salary report file from your computer"
            )

            # Save report buttons - persist to local disk or Google Drive
            if uploaded_file is not None:
                save_col1, save_col2 = st.columns(2)
                with save_col1:
                    if st.button("💾 Save Locally", help="Save to this computer (lost on cloud restart)"):
                        if _save_report(uploaded_file):
                            st.success("✅ Saved locally!")
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error("Failed to save")
                with save_col2:
                    gdrive_folder = _get_saved_reports_folder_id(selected_shop)
                    gdrive_client = _get_google_drive_client()
                    if gdrive_folder and gdrive_client:
                        if st.button("☁️ Save to Google Drive", help="Save to Google Drive (persists on cloud)"):
                            ok, err = _save_report_to_gdrive(uploaded_file, gdrive_folder)
                            if ok:
                                st.success("✅ Saved to Google Drive!")
                                st.rerun()
                            else:
                                st.error(f"Failed to save to Drive: {err or 'Unknown error'}")
                                st.caption(
                                    "Typical fixes: share the Drive folder with your Google account "
                                    "(OAuth) or with the service account email (Streamlit Cloud / API key JSON). "
                                    "Confirm `saved_reports_folder_id` or `google_drive_folder_id` in shops config is the folder ID, not a file link."
                                )
                    elif gdrive_folder and not gdrive_client:
                        st.caption("⚠️ Configure Google Drive credentials to save")

            # Saved reports selector - use previously saved report instead of re-uploading
            saved_reports = _list_saved_reports()
            if saved_reports:
                if st.session_state.pop("_clear_saved_report", False):
                    st.session_state.selected_saved_report = None
                    st.session_state.pop("saved_report_selector", None)
                    st.session_state.pop("_confirm_clear_saved", None)
                st.caption("Or use a saved report:")
                saved_options = ["(None - use upload above)"] + saved_reports
                selected_idx = 0
                if st.session_state.selected_saved_report and st.session_state.selected_saved_report in saved_reports:
                    selected_idx = saved_reports.index(st.session_state.selected_saved_report) + 1
                chosen = st.selectbox(
                    "Saved Reports",
                    saved_options,
                    index=selected_idx,
                    key="saved_report_selector"
                )
                if chosen != "(None - use upload above)":
                    st.session_state.selected_saved_report = chosen
                else:
                    st.session_state.selected_saved_report = None
                if st.session_state.selected_saved_report:
                    if st.session_state.get("_confirm_clear_saved"):
                        st.warning("⚠️ Click again to confirm clearing selection")
                        if st.button("✅ Yes, clear selection", key="confirm_clear_saved"):
                            st.session_state._clear_saved_report = True
                            st.session_state._confirm_clear_saved = False
                            st.rerun()
                        if st.button("❌ Cancel", key="cancel_clear_saved"):
                            st.session_state._confirm_clear_saved = False
                            st.rerun()
                    elif st.button("🗑️ Clear Selection", help="Clear saved report selection"):
                        st.session_state._confirm_clear_saved = True
                        st.rerun()
            else:
                st.session_state.selected_saved_report = None

            # Google Drive reports - load from Drive (persists on cloud, per-shop folder)
            gdrive_folder = _get_saved_reports_folder_id(selected_shop)
            gdrive_files = _list_gdrive_reports(gdrive_folder) if gdrive_folder else []
            if gdrive_files:
                if st.session_state.pop("_clear_gdrive", False):
                    st.session_state.selected_gdrive_report = None
                    st.session_state.pop("gdrive_report_selector", None)
                    st.session_state.pop("_confirm_clear_gdrive", None)
                st.caption(f"Or load from Google Drive ({shop_config.get('name', selected_shop)} folder):")
                gdrive_options = ["(None)"] + [f["name"] for f in sorted(gdrive_files, key=lambda x: x.get("name", ""), reverse=True)]
                gdrive_selected_idx = 0
                if st.session_state.selected_gdrive_report:
                    names = [f["name"] for f in gdrive_files]
                    if st.session_state.selected_gdrive_report.get("name") in names:
                        gdrive_selected_idx = names.index(st.session_state.selected_gdrive_report["name"]) + 1
                gdrive_chosen = st.selectbox("Google Drive Reports", gdrive_options, index=gdrive_selected_idx, key="gdrive_report_selector")
                if gdrive_chosen != "(None)":
                    match = next((f for f in gdrive_files if f["name"] == gdrive_chosen), None)
                    st.session_state.selected_gdrive_report = {"id": match["id"], "name": match["name"]} if match else None
                else:
                    st.session_state.selected_gdrive_report = None
                if st.session_state.selected_gdrive_report:
                    if st.session_state.get("_confirm_clear_gdrive"):
                        st.warning("⚠️ Click again to confirm clearing Drive selection")
                        if st.button("✅ Yes, clear", key="confirm_clear_gdrive"):
                            st.session_state._clear_gdrive = True
                            st.session_state._confirm_clear_gdrive = False
                            st.rerun()
                        if st.button("❌ Cancel", key="cancel_clear_gdrive"):
                            st.session_state._confirm_clear_gdrive = False
                            st.rerun()
                    elif st.button("🗑️ Clear Drive Selection", key="clear_gdrive"):
                        st.session_state._confirm_clear_gdrive = True
                        st.rerun()
            else:
                st.session_state.selected_gdrive_report = None

            # Effective file: uploaded > local saved > Google Drive saved
            if uploaded_file is not None:
                report_file = uploaded_file
            elif st.session_state.selected_saved_report:
                report_file = _load_saved_report(st.session_state.selected_saved_report)
            elif st.session_state.selected_gdrive_report:
                gdr = st.session_state.selected_gdrive_report
                report_file = _load_gdrive_report(gdr["id"], gdr["name"])
            else:
                report_file = None

        with st.expander("⚙️ Settings", expanded=True):
            api_key_check = (hasattr(st, "secrets") and st.secrets.get("airtable", {}).get("api_key")) or os.getenv("AIRTABLE_API_KEY") or st.session_state.get("airtable_api_key", "")
            if not api_key_check:
                st.warning("⚠️ Airtable API key required")
                api_key_input = st.text_input("Airtable API key", type="password", key="airtable_api_key_sidebar", help="Set AIRTABLE_API_KEY env var or add to Streamlit secrets to skip")
                if api_key_input:
                    if api_key_input != st.session_state.get("airtable_api_key"):
                        st.cache_data.clear()
                    st.session_state.airtable_api_key = api_key_input
                    st.success("✅ API key saved for this session")
            else:
                st.success("✅ Airtable API key found")

        st.markdown("---")
        st.subheader("📤 Airtable Export (Optional)")
        
        st.info("💡 **Tip**: Run calculations first to review results, then enable Airtable export when ready.")
        
        append_to_airtable = st.checkbox(
            "Enable Airtable Export",
            help="Append results to Airtable after calculation (disabled by default for testing)"
        )
        
        airtable_api_key = None  # Set below when append_to_airtable is True
        if append_to_airtable:
            # Try to get API key from secrets, env var, or session state
            api_key_from_secrets = None
            try:
                if hasattr(st, 'secrets') and 'airtable' in st.secrets and 'api_key' in st.secrets.airtable:
                    api_key_from_secrets = st.secrets.airtable.api_key
            except Exception:
                pass
            
            api_key_from_env = os.getenv('AIRTABLE_API_KEY')
            api_key_from_session = st.session_state.get('airtable_api_key')
            
            # Use the first available key
            default_api_key = api_key_from_secrets or api_key_from_env or api_key_from_session or ''
            
            if default_api_key:
                st.success("✅ Airtable API key found (from secrets/env/session)")
                airtable_api_key = default_api_key
                # Optionally allow override
                if st.checkbox("🔑 Use different API key", help="Override the saved API key"):
                    airtable_api_key = st.text_input(
                        "Airtable API Key",
                        type="password",
                        help="Enter your Airtable API key",
                        key="airtable_key_override"
                    ) or default_api_key
            else:
                airtable_api_key = st.text_input(
                    "Airtable API Key",
                    type="password",
                    help="Enter your Airtable API key (or set AIRTABLE_API_KEY env var or use Streamlit secrets)",
                    key="airtable_key_input"
                )
                # Save to session state for this session
                if airtable_api_key:
                    st.session_state.airtable_api_key = airtable_api_key
            base_id = shop_config.get('airtable_base_id', '')
            table_name = shop_config.get('airtable_table_name', '')
            
            if base_id and table_name:
                st.success(f"✅ Base ID: {base_id}")
                st.success(f"✅ Table: {table_name}")
            else:
                st.warning("⚠️ Base ID or table name not configured in config/shops.yaml")
    
    # Main content area – workflow step indicator + larger tabs
    current_tab = st.session_state.get("main_tabs", "Monthly Bonuses")
    workflow_steps = ["Monthly Bonuses", "Calculate", "Results"]
    current_step_idx = workflow_steps.index(current_tab) if current_tab in workflow_steps else -1

    st.markdown(
        """
        <style>
        /* Workflow step indicator */
        .workflow-steps {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            margin-bottom: 1.25rem;
            padding: 0.75rem 1rem;
            background: linear-gradient(135deg, #eef2ff 0%, #f4f4f5 100%);
            border-radius: 12px;
            border: 1px solid #e4e4e7;
        }
        .workflow-step {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            font-size: 0.9rem;
            color: #64748b;
        }
        .workflow-step.active {
            color: #4f46e5;
            font-weight: 600;
        }
        .workflow-step.completed {
            color: #6366f1;
        }
        .workflow-arrow {
            color: #94a3b8;
            font-size: 1rem;
        }
        /* Bigger tab labels (works across Streamlit versions) */
        .stTabs [data-baseweb="tab"],
        .stTabs [data-baseweb="tab-list"] button,
        button[data-baseweb="tab"] {
            font-size: 1.15rem !important;
            padding: 0.65rem 1.4rem !important;
            font-weight: 500 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Workflow step indicator (highlights current step when on workflow tabs)
    step_html = '<div class="workflow-steps">'
    for i, step in enumerate(workflow_steps):
        cls = "workflow-step"
        if i == current_step_idx:
            cls += " active"
        elif current_step_idx >= 0 and i < current_step_idx:
            cls += " completed"
        prefix = "✓ " if (current_step_idx >= 0 and i < current_step_idx) else ""
        step_html += f'<span class="{cls}">{prefix}{step}</span>'
        if i < len(workflow_steps) - 1:
            step_html += '<span class="workflow-arrow">→</span>'
    step_html += "</div>"
    st.markdown(step_html, unsafe_allow_html=True)
    # Apply pending tab selections (set by form submits) before widgets are created
    if "_pending_main_tab" in st.session_state:
        st.session_state["main_tabs"] = st.session_state.pop("_pending_main_tab")
    if "_pending_sales_sub_tab" in st.session_state:
        st.session_state["sales_sub_tabs"] = st.session_state.pop("_pending_sales_sub_tab")
    main_tab_names = [
        "Monthly Bonuses",
        "Calculate",
        "Results",
        "Airtable Preview",
        "Sales Target Tracker",
        "Data Management",
        "Shop Analytics",
        "Employee Evolution",
    ]
    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs(
        main_tab_names,
        key="main_tabs",
        on_change="rerun",
        default=st.session_state.get("main_tabs", "Monthly Bonuses"),
    )
    
    with tab1:
        from tabs.monthly_bonuses import render as render_monthly_bonuses
        render_monthly_bonuses(selected_shop, shop_config)
    
    with tab2:
        from tabs.calculate import render as render_calculate
        render_calculate(report_file, selected_shop, shop_config, config, append_to_airtable, airtable_api_key)
    
    with tab3:
        from tabs.results import render as render_results
        render_results(config)
    
    with tab4:
        from tabs.airtable_preview import render as render_airtable_preview
        render_airtable_preview(shop_config)
    
    with tab5:
        st.header("🎯 Sales Target Tracker")
        st.info(
            "Set an approved monthly target and update the **Total reached** each day. "
            "The app works out how far through the month you are and whether you are ahead "
            "or behind where you should be by today."
        )

        # Sub-tabs for Sales Target Tracker (add new tab names here to extend)
        sub_tab_names = ["📋 Daily Target Manager", "🏪 Shop Target Monthly", "📊 Wage vs Sales"]
        sales_sub_tabs = st.tabs(
            sub_tab_names,
            key="sales_sub_tabs",
            on_change="rerun",
            default=st.session_state.get("sales_sub_tabs", sub_tab_names[0]),
        )

        with sales_sub_tabs[0]:
            # --- Daily Target Manager ---
            if "_daily_target_saved_toast" in st.session_state:
                st.toast(st.session_state.pop("_daily_target_saved_toast"), icon="✅")

            @st.fragment
            def _daily_target_manager_fragment():
                with st.container(border=True):
                    st.subheader("📋 Daily target (manager)")
                    st.caption("Set who is working each day and each staff member’s individual sales target for that day.")
                shop_key_tracker = st.session_state.get("selected_shop") or selected_shop
                employees_tracker, _, _ = load_employee_config(shop_key_tracker) or ({}, {}, {})
                employee_names = list(employees_tracker.keys()) if employees_tracker else []

                daily_targets_config = load_daily_targets()
                shop_daily = daily_targets_config.get(shop_key_tracker, {})

                # Date and staff selection OUTSIDE the form so they update immediately and per-staff inputs appear
                rubric_date = st.date_input(
                    "Date",
                    value=st.session_state.get("daily_target_date", datetime.today().date()),
                    key="daily_target_date",
                    help="The day you are setting the target for.",
                )
                date_str = rubric_date.strftime("%Y-%m-%d")
                existing = shop_daily.get(date_str, {"staff_working": [], "staff_daily_targets": {}, "staff_daily_sales": {}})
                existing_staff = existing.get("staff_working") or []
                existing_targets = existing.get("staff_daily_targets") or {}
                existing_sales = existing.get("staff_daily_sales") or {}

                # Show ✓ for staff already saved for this date (same as Monthly Bonuses)
                staff_options = [f"{name} ✓" if name in existing_staff else name for name in employee_names]
                staff_working_raw = st.multiselect(
                    "Staff working this day",
                    options=staff_options,
                    default=[opt for opt in staff_options if opt.replace(" ✓", "").strip() in existing_staff],
                    key="daily_rubric_staff",
                    help="Select everyone who is working on this date. ✓ = already saved for this day.",
                )
                staff_working = [opt.replace(" ✓", "").strip() for opt in staff_working_raw]

                st.markdown("**Daily target & sales per staff (£)**")
                with st.form("daily_target_rubric_form", clear_on_submit=False):
                    staff_daily_targets = {}
                    staff_daily_sales = {}
                    for name in staff_working:
                        with st.expander(f"**{name}**", expanded=True):
                            c1, c2 = st.columns(2)
                            with c1:
                                staff_daily_targets[name] = st.number_input(
                                    "Target (£)",
                                    min_value=0.0,
                                    step=50.0,
                                    value=float(existing_targets.get(name, 0)),
                                    format="%.2f",
                                    key=f"daily_target_{date_str}_{name}",
                                    help=f"Sales target for {name} on this day.",
                                )
                            with c2:
                                staff_daily_sales[name] = st.number_input(
                                    "Actual sales (£)",
                                    min_value=None,
                                    step=50.0,
                                    value=float(existing_sales.get(name, 0)),
                                    format="%.2f",
                                    key=f"daily_sales_{date_str}_{name}",
                                    help=f"Total sales achieved by {name} on this day. Use negative values for refunds (e.g. -100).",
                                )
                    submitted_rubric = st.form_submit_button("Save daily target")

                if submitted_rubric:
                    staff_working_submitted = staff_working  # current selection (outside form)
                    staff_daily_targets_submitted = {}
                    staff_daily_sales_submitted = {}
                    for name in staff_working_submitted:
                        key_t = f"daily_target_{date_str}_{name}"
                        key_s = f"daily_sales_{date_str}_{name}"
                        staff_daily_targets_submitted[name] = float(st.session_state.get(key_t, 0))
                        staff_daily_sales_submitted[name] = float(st.session_state.get(key_s, 0))
                    if shop_key_tracker not in daily_targets_config:
                        daily_targets_config[shop_key_tracker] = {}
                    daily_targets_config[shop_key_tracker][date_str] = {
                        "staff_working": staff_working_submitted,
                        "staff_daily_targets": staff_daily_targets_submitted,
                        "staff_daily_sales": staff_daily_sales_submitted,
                    }
                    save_daily_targets(daily_targets_config)
                    st.cache_data.clear()
                    total = sum(staff_daily_targets_submitted.values())
                    st.session_state["_daily_target_saved_toast"] = f"Daily target saved for {date_str} (£{total:,.2f})"
                    st.session_state._pending_main_tab = "Sales Target Tracker"
                    st.session_state._pending_sales_sub_tab = "📋 Daily Target Manager"
                    st.rerun()

                # Performance vs target (for selected date)
                date_targets = shop_daily.get(date_str, {})
                date_targets_dict = date_targets.get("staff_daily_targets") or {}
                date_sales_dict = date_targets.get("staff_daily_sales") or {}
                staff_with_data = [n for n in (set(date_targets_dict.keys()) | set(date_sales_dict.keys()))]
                if staff_with_data:
                    st.markdown("**Performance vs target**")
                    for name in sorted(staff_with_data):
                        target = float(date_targets_dict.get(name, 0) or 0)
                        sales = float(date_sales_dict.get(name, 0) or 0)
                        if target > 0 and sales > 0:
                            diff = sales - target
                            pct = (diff / target) * 100
                            if diff >= 0:
                                st.success(f"**{name}:** Target {format_currency(target)} → Sales {format_currency(sales)} ({pct:+.1f}% above)")
                            else:
                                st.warning(f"**{name}:** Target {format_currency(target)} → Sales {format_currency(sales)} ({pct:.1f}% below)")
                        elif target > 0 or sales != 0:
                            # Include refunds (sales < 0) and day-off staff with no target
                            st.info(f"**{name}:** Target {format_currency(target)} | Sales {format_currency(sales)}")

                # Show today's manager-set daily targets (per staff and total)
                today_str = datetime.today().date().strftime("%Y-%m-%d")
                today_rubric = shop_daily.get(today_str, {})
                today_staff = today_rubric.get("staff_working") or []
                today_targets = today_rubric.get("staff_daily_targets") or {}
                if today_staff or today_targets:
                    with st.expander("Today’s daily target (manager)", expanded=True):
                        if today_targets:
                            for name, target in today_targets.items():
                                if target > 0:
                                    st.write(f"**{name}:** {format_currency(target)}")
                            st.metric("Total daily target", format_currency(sum(today_targets.values())))
                        if today_staff and not today_targets:
                            st.write("**Staff working:**", ", ".join(today_staff))

            _daily_target_manager_fragment()

        with sales_sub_tabs[1]:
            # --- Shop Target Monthly ---
            with st.expander("ℹ️ How this tracker works", expanded=False):
                st.markdown(
                    """
                    **Workflow**
                    - Use the **sidebar** to choose the shop (e.g. Opatra or PYT). This page always shows data for the selected shop.
                    - Set the **Approved target (£)** once per month; it is saved automatically for that shop and month.
                    - Each day, update **Total reached so far (£)** with the cumulative sales to date, then click **Update calculations** (or press Enter).
                    - **Current date** is used only to work out how many days have passed in the month; change it if you are entering data for a different day.

                    **What each metric means**
                    - **Target**: Your approved sales target for the *whole* month (e.g. £60,000).
                    - **Total days**: Number of days in the selected month (e.g. 28 for February, 31 for March).
                    - **Days passed / Days left**: How far through the month we are, based on the **Current date** you chose.
                    - **Total reached**: The cumulative sales you entered; this is the only number you edit daily.
                    - **Average so far**: Total reached ÷ Days passed — your average daily sales so far.
                    - **Expected sales so far**: What you *should* have sold by today if you were exactly on track:  
                      `Target × (Days passed ÷ Total days)`.  
                      This is the benchmark we compare against.
                    - **Direction of**: Same as Total reached; the amount we are comparing to the expected.
                    - **Direction vs target**: `(Total reached ÷ Expected sales so far) × 100%`.  
                      - **100%** = on track.  
                      - **Above 100%** = ahead of schedule.  
                      - **Below 100%** = behind schedule.  
                      The delta (e.g. +41.67%) shows how far ahead or behind you are.
                    - **Left to reach**: Target − Total reached — how much more you need to hit the target.
                    - **Avg needed per day**: Left to reach ÷ Days left — the average you need to sell *each remaining day* to still hit the target. Shown as N/A when there are no days left.
                    - **Daily target**: Target ÷ Total days — the average daily sales needed over the *entire* month to hit the target.

                    **Traffic‑light status**
                    - 🔴 **Below target**: You are more than 10% behind expected sales (Direction vs target &lt; 90%).
                    - 🟡 **Around target**: You are within ±10% of expected sales (90%–110%).
                    - 🟢 **Above target**: You are more than 10% ahead of expected sales (Direction vs target &gt; 110%).
                    """
                )

            # --- Wage vs sales badge (corner) ---
            shop_key_wvs = st.session_state.get("selected_shop") or selected_shop
            current_date_wvs = st.session_state.get("target_current_date", datetime.today().date())
            year_wvs, month_wvs = current_date_wvs.year, current_date_wvs.month
            month_key_wvs = f"{year_wvs}-{month_wvs:02d}"
            cache_key = ("wvs_shop_target", shop_key_wvs, month_key_wvs)
            if st.session_state.get("_wvs_cache_key") != cache_key:
                tw, ts = _load_wage_vs_sales_for_month(shop_key_wvs, year_wvs, month_wvs, current_date_wvs)
                st.session_state["_wvs_shop_target_totals"] = (tw, ts)
                st.session_state["_wvs_cache_key"] = cache_key
            tw_cached, ts_cached = st.session_state.get("_wvs_shop_target_totals", (None, None))
            wage_pct_badge = (tw_cached / ts_cached * 100) if (tw_cached is not None and ts_cached and ts_cached > 0) else None

            # --- Shop target tracker ---
            # Pre-fill from stored targets BEFORE the form (cannot modify widget-bound session state after widget is created)
            shop_key = st.session_state.get("selected_shop") or selected_shop
            current_date_pre = st.session_state.get("target_current_date", datetime.today().date())
            year_pre, month_pre = current_date_pre.year, current_date_pre.month
            month_key_pre = f"{year_pre}-{month_pre:02d}"
            current_shop_month = (shop_key, month_key_pre)
            targets_config_pre = load_shop_targets()
            stored_target_pre = (
                targets_config_pre.get(shop_key, {}).get(month_key_pre, {}).get("approved_target")
            )
            stored_total_reached_pre = (
                targets_config_pre.get(shop_key, {}).get(month_key_pre, {}).get("total_reached")
            )
            # When shop or month changes, reload from storage so we don't show another shop's values.
            # Do NOT overwrite when same shop/month: the form may have just been submitted with new
            # values that aren't in session state yet (form widgets write after this block runs).
            last_loaded_shop_month = st.session_state.get("_target_shop_month")
            if last_loaded_shop_month != current_shop_month:
                v_approved = float(stored_target_pre or 0)
                v_reached = float(stored_total_reached_pre or 0)
                st.session_state.target_approved = f"{v_approved:,.2f}" if v_approved else "0"
                st.session_state.target_total_reached = f"{v_reached:,.2f}" if v_reached else "0"
                st.session_state["_target_shop_month"] = current_shop_month

            with st.container(border=True):
                st.subheader("🏪 Shop target (monthly)")
                st.caption("Monthly sales target and progress for this shop.")
                st.caption("**Click *Update calculations* to save changes to Airtable.**")
                # Use a form so that pressing Enter submits ONLY this section
                with st.form("sales_target_tracker_form", clear_on_submit=False):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.text_input(
                            "Approved target (£)",
                            key="target_approved",
                            placeholder="e.g. 5000 or 5,000.00",
                        )
                        st.text_input(
                            "Total reached so far (£)",
                            key="target_total_reached",
                            placeholder="e.g. 5000 or 5,000.00",
                        )
                    with col2:
                        st.date_input(
                            "Current date (used to calculate days passed)",
                            value=st.session_state.target_current_date,
                            key="target_current_date",
                        )

                    sales_target_form_submitted = st.form_submit_button("Update calculations")

                # Read current values from session state for calculations (parse strings like "5,000.00")
                approved_target = _parse_currency_input(st.session_state.get("target_approved", "0"))
                total_reached = _parse_currency_input(st.session_state.get("target_total_reached", "0"))
                current_date = st.session_state.get("target_current_date", datetime.today().date())

                # Load or update saved targets for this shop/month
                shop_key = st.session_state.get("selected_shop") or selected_shop
                targets_config = load_shop_targets()
                year = current_date.year
                month = current_date.month
                month_key = f"{year}-{month:02d}"

                # Pre-fill is done before the form; use approved_target from session state (already set above)
                stored_target = (
                    targets_config.get(shop_key, {})
                    .get(month_key, {})
                    .get("approved_target")
                )
                if approved_target == 0.0 and stored_target:
                    approved_target = float(stored_target)
                if approved_target > 0 or total_reached > 0:
                    # Persist targets and total reached
                    if shop_key not in targets_config:
                        targets_config[shop_key] = {}
                    if month_key not in targets_config[shop_key]:
                        targets_config[shop_key][month_key] = {}
                    targets_config[shop_key][month_key]["approved_target"] = float(approved_target)
                    targets_config[shop_key][month_key]["total_reached"] = float(total_reached)
                    save_ok, save_error = save_shop_targets(targets_config)
                    if save_ok:
                        st.cache_data.clear()
                    if sales_target_form_submitted:
                        st.session_state._pending_main_tab = "Sales Target Tracker"
                        st.session_state._pending_sales_sub_tab = "🏪 Shop Target Monthly"
                        if save_ok:
                            st.toast("New total reached values saved to Airtable. Updated calculations are on the way, along with the rest of the changes.", icon="✅")
                        else:
                            st.toast(f"Failed to save to Airtable: {save_error}", icon="❌")

                # Core calculations
                total_days = calendar.monthrange(year, month)[1]
                days_passed = min(current_date.day, total_days)
                days_left = max(total_days - days_passed, 0)

                average_so_far = total_reached / days_passed if days_passed > 0 else 0.0
                direction_of = days_left * average_so_far  # Projected sales for remaining days

                # Expected sales by today if you were exactly on track
                expected_so_far = 0.0
                if approved_target > 0 and total_days > 0 and days_passed > 0:
                    expected_so_far = approved_target * (days_passed / total_days)

                # Compare projected end-of-month total (total reached + projected remaining) vs target
                projected_total = total_reached + direction_of
                if approved_target > 0:
                    direction_vs_target_pct = (projected_total / approved_target) * 100.0
                    diff_vs_target_pct = direction_vs_target_pct - 100.0
                else:
                    direction_vs_target_pct = 0.0
                    diff_vs_target_pct = 0.0

                left_to_reach = max(approved_target - total_reached, 0.0)
                avg_needed = left_to_reach / days_left if days_left > 0 else None
                daily_target = approved_target / total_days if total_days > 0 else 0.0

                st.markdown("---")

                # High-level metrics
                m1, m2, m3, m4, m5 = st.columns(5)
                with m1:
                    st.metric("Target", format_currency(approved_target))
                with m2:
                    st.metric("Total days (month)", total_days)
                with m3:
                    st.metric("Days passed", days_passed)
                with m4:
                    st.metric("Days left", days_left)
                with m5:
                    if st.button("🔄 Refresh wage %", key="wvs_shop_target_refresh"):
                        st.session_state["_wvs_cache_key"] = None
                        st.rerun()
                    if wage_pct_badge is not None:
                        target_pct_badge = 25.0
                        delta = wage_pct_badge - target_pct_badge
                        st.metric(
                            "Wage % of sales",
                            f"{wage_pct_badge:.1f}%",
                            f"{delta:+.1f}% vs 25%",
                            delta_color="inverse",
                        )
                    else:
                        st.metric("Wage % of sales", "—", "configure wage_vs_sales_table")

                st.markdown("### Progress Summary")
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.metric("Total reached", format_currency(total_reached))
                    st.metric("Average so far", format_currency(average_so_far))
                with c2:
                    st.metric("Projected total", format_currency(projected_total))
                    st.metric("Expected sales so far", format_currency(expected_so_far))
                with c3:
                    st.metric(
                        "Direction vs target",
                        f"{direction_vs_target_pct:.2f}%",
                        f"{diff_vs_target_pct:+.2f}%",
                    )
                    st.metric("Left to reach", format_currency(left_to_reach))
                    if avg_needed is None:
                        st.metric("Avg needed per day", "N/A")
                    else:
                        st.metric("Avg needed per day", format_currency(avg_needed))
                    st.metric("Daily target", format_currency(daily_target))

                # Traffic-light style status
                if approved_target > 0:
                    st.markdown("---")
                    status_col = st.columns(1)[0]
                    if diff_vs_target_pct < -10:
                        with status_col:
                            st.error("🔴 **Below target** – consider increasing daily sales.")
                    elif diff_vs_target_pct <= 10:
                        with status_col:
                            st.warning("🟡 **Around target** – keep an eye on performance.")
                    else:
                        with status_col:
                            st.success("🟢 **Above target** – great progress!")

        with sales_sub_tabs[2]:
            # --- Wage vs Sales (daily or interval) ---
            st.subheader("📊 Wage vs Sales Ratio")
            st.caption(
                "Enter hours worked and sales per staff. The system calculates wages using wage brackets, "
                "hourly overrides, and commission structures, then shows the wage % of total sales. Target: 25%."
            )

            shop_key_wvs = st.session_state.get("selected_shop") or selected_shop
            emp_config_result = load_employee_config(shop_key_wvs)
            employees_wvs, bonuses_wvs, emp_config_full = emp_config_result or ({}, {}, {})
            if emp_config_full is None:
                emp_config_full = {}
            employee_names_wvs = list(employees_wvs.keys()) if employees_wvs else []

            if not employees_wvs:
                st.warning("No employees loaded for this shop. Check Airtable configuration.")
            else:
                wvs_data_source = st.radio(
                    "Data source",
                    options=["Load from Airtable", "Import from report", "Manual entry"],
                    key="wvs_data_source",
                    horizontal=True,
                    help="Load existing data from Airtable, import from a report file, or enter hours and sales manually.",
                )

                if wvs_data_source == "Load from Airtable":
                    # --- Load from Airtable path ---
                    from collections import defaultdict
                    base_id_wvs_load, api_key_wvs_load, _ = _get_airtable_credentials(shop_key_wvs)
                    config_load = load_config() or {}
                    shop_config_load = config_load.get("shops", {}).get(shop_key_wvs, {})
                    tables_cfg_load = config_load.get("airtable_config_tables", {})
                    table_name_wvs_load = shop_config_load.get("wage_vs_sales_table") or tables_cfg_load.get("wage_vs_sales") or ""
                    shop_display_load = shop_config_load.get("shop_display_name") or shop_config_load.get("name", "")

                    if not base_id_wvs_load or not api_key_wvs_load or not table_name_wvs_load:
                        st.warning("Airtable base ID, API key, and wage_vs_sales_table must be configured for this shop.")
                    else:
                        today_wvs = datetime.today().date()
                        first_of_month_wvs = today_wvs.replace(day=1)
                        col_from, col_to = st.columns(2)
                        with col_from:
                            wvs_load_from = st.date_input(
                                "From date",
                                value=first_of_month_wvs,
                                key="wvs_load_from",
                                help="Start of date range (inclusive). Defaults to 1st of current month.",
                            )
                        with col_to:
                            wvs_load_to = st.date_input(
                                "To date",
                                value=today_wvs,
                                key="wvs_load_to",
                                help="End of date range (inclusive). Defaults to today.",
                            )
                        if st.button("Load from Airtable", key="wvs_load_btn"):
                            try:
                                with st.spinner("Loading from Airtable..."):
                                    at_client_load = AirtableClient(api_key=api_key_wvs_load)
                                    date_from_str = wvs_load_from.strftime("%Y-%m-%d")
                                    date_to_str = wvs_load_to.strftime("%Y-%m-%d")
                                    raw_records = at_client_load.get_wage_vs_sales(
                                        base_id_wvs_load, table_name_wvs_load,
                                        shop=shop_display_load,
                                        date_from=date_from_str,
                                        date_to=date_to_str,
                                    )
                                    emp_table_load = tables_cfg_load.get("employees", "Employees")
                                    emp_recs_load = at_client_load.get_employee_records_with_ids(
                                        base_id_wvs_load, emp_table_load,
                                        shop_display_name=shop_display_load,
                                        active_only=False,
                                    )
                                    id_to_name_load = {r["id"]: str(r.get("Name", "")).strip() for r in emp_recs_load if r.get("Name")}

                                    def _safe_float(val):
                                        if val is None or val == "":
                                            return 0.0
                                        try:
                                            return float(val)
                                        except (ValueError, TypeError):
                                            return 0.0

                                    def _emp_from_record(r):
                                        emp_val = r.get("Employee") or r.get("employee")
                                        if isinstance(emp_val, list) and emp_val:
                                            return id_to_name_load.get(emp_val[0], emp_val[0]) or ""
                                        return str(emp_val or "").strip()

                                    def _date_from_record(r):
                                        d = r.get("Date") or r.get("date")
                                        normalized = _normalize_date_for_key(d)
                                        return normalized or ""

                                    detail_rows_load = []
                                    total_wages_load = 0.0
                                    total_sales_load = 0.0
                                    for rec in raw_records:
                                        emp_name = _emp_from_record(rec) or "Unknown"
                                        date_str = _date_from_record(rec)
                                        if not date_str:
                                            continue
                                        hours = _safe_float(rec.get("Hours") or rec.get("hours"))
                                        sales = _safe_float(rec.get("Sales") or rec.get("sales"))
                                        addl = _safe_float(rec.get("Add'l Sales") or rec.get("AddlSales") or rec.get("addl_sales"))
                                        total_sales_val = _safe_float(rec.get("Total Sales") or rec.get("total_sales")) or (sales + addl)
                                        base_val = _safe_float(rec.get("Base") or rec.get("base"))
                                        commission_val = _safe_float(rec.get("Commission") or rec.get("commission"))
                                        total_wages_val = _safe_float(rec.get("Total Wages") or rec.get("total_wages")) or (base_val + commission_val)
                                        wage_pct_val = rec.get("Wage %") or rec.get("wage_pct")
                                        if wage_pct_val is not None:
                                            try:
                                                wage_pct_val = float(wage_pct_val)
                                            except (ValueError, TypeError):
                                                wage_pct_val = (total_wages_val / total_sales_val * 100) if total_sales_val > 0 else None
                                        else:
                                            wage_pct_val = (total_wages_val / total_sales_val * 100) if total_sales_val > 0 else None

                                        total_wages_load += total_wages_val
                                        total_sales_load += total_sales_val
                                        detail_rows_load.append({
                                            "Employee": emp_name,
                                            "Date": date_str,
                                            "Hours": hours,
                                            "Sales": format_currency(sales),
                                            "Add'l Sales": format_currency(addl),
                                            "Total Sales": format_currency(total_sales_val),
                                            "Base": format_currency(base_val),
                                            "Commission": format_currency(commission_val),
                                            "Total Wages": format_currency(total_wages_val),
                                            "Wage %": "N/A" if wage_pct_val is None else f"{wage_pct_val:.2f}%",
                                            "_sales_raw": total_sales_val,
                                            "_wages_raw": total_wages_val,
                                            "_wage_pct_raw": float("nan") if wage_pct_val is None else round(wage_pct_val, 2),
                                            "_base_raw": base_val,
                                            "_commission_raw": commission_val,
                                            "_hrly_rate_raw": 0.0,
                                            "_sales_only_raw": sales,
                                            "_addl_raw": addl,
                                            "_payment_type_raw": "",
                                        })
                                    st.session_state["wvs_loaded_detail_rows"] = detail_rows_load
                                    st.session_state["wvs_loaded_totals"] = (total_wages_load, total_sales_load)
                                    st.rerun()
                            except Exception as e:
                                st.error(f"Failed to load: {e}")
                                with st.expander("Details"):
                                    import traceback
                                    st.code(traceback.format_exc())

                        if "wvs_loaded_detail_rows" in st.session_state:
                            detail_rows_load = st.session_state["wvs_loaded_detail_rows"]
                            total_wages_load, total_sales_load = st.session_state["wvs_loaded_totals"]
                            wage_pct_load = (total_wages_load / total_sales_load * 100) if total_sales_load > 0 else 0.0
                            target_pct = 25.0
                            st.success(f"Loaded {len(detail_rows_load)} records from Airtable")
                            st.markdown("---")
                            st.markdown("### Result")
                            col_a, col_b, col_c = st.columns(3)
                            with col_a:
                                st.metric("Total wages", format_currency(total_wages_load))
                            with col_b:
                                st.metric("Total sales", format_currency(total_sales_load))
                            with col_c:
                                st.metric("Wage % of sales", f"{wage_pct_load:.2f}%")
                            if total_sales_load > 0:
                                if wage_pct_load < target_pct - 1:
                                    st.success("🟢 **Under target** – wages are below 25% of sales.")
                                elif wage_pct_load <= target_pct + 1:
                                    st.info("🟡 **On target** – wages are around 25% of sales.")
                                else:
                                    st.error("🔴 **Over target** – wages are above 25% of sales.")

                            if detail_rows_load:
                                st.markdown("#### Charts")
                                _render_wage_vs_sales_charts(
                                    detail_rows_load, total_wages_load, total_sales_load, target_pct
                                )
                                st.markdown("---")

                            if detail_rows_load:
                                by_employee_load = defaultdict(list)
                                for r in detail_rows_load:
                                    by_employee_load[r["Employee"]].append(r)
                                for emp_name in sorted(by_employee_load.keys()):
                                    emp_rows = by_employee_load[emp_name]
                                    emp_rows.sort(key=lambda x: x["Date"])
                                    days_count = len(emp_rows)
                                    emp_total_sales = sum(r["_sales_raw"] for r in emp_rows)
                                    emp_total_wages = sum(r["_wages_raw"] for r in emp_rows)
                                    emp_avg_pct_str = "N/A" if emp_total_sales <= 0 else f"{(emp_total_wages / emp_total_sales * 100):.2f}%"
                                    with st.expander(f"**{emp_name}** — {days_count} days worked · Avg wage %: {emp_avg_pct_str}", expanded=True):
                                        table_rows = [{k: v for k, v in r.items() if not k.startswith("_")} for r in emp_rows]
                                        st.dataframe(
                                            pd.DataFrame(table_rows),
                                            width="stretch",
                                            hide_index=True,
                                        )
                                        dates_fmt = [_format_date_for_chart(r["Date"]) for r in emp_rows]
                                        st.caption("Wage % over time (target: 25%)")
                                        pct_df = pd.DataFrame(
                                            {"Wage %": [r["_wage_pct_raw"] for r in emp_rows]},
                                            index=dates_fmt,
                                        )
                                        st.line_chart(pct_df)
                                        st.caption("Wages vs Sales per day (£)")
                                        amounts_df = pd.DataFrame(
                                            {
                                                "Wages (£)": [r["_wages_raw"] for r in emp_rows],
                                                "Sales (£)": [r["_sales_raw"] for r in emp_rows],
                                            },
                                            index=dates_fmt,
                                        )
                                        st.bar_chart(amounts_df)
                            if st.button("Clear loaded data", key="wvs_clear_loaded"):
                                del st.session_state["wvs_loaded_detail_rows"]
                                del st.session_state["wvs_loaded_totals"]
                                st.rerun()
                        else:
                            st.info("Select a date range and click **Load from Airtable** to view existing data.")

                elif wvs_data_source == "Import from report":
                    # --- Import from report path ---
                    wvs_uploaded = st.file_uploader(
                        "Upload report (CSV)",
                        type=["csv"],
                        key="wvs_report_upload",
                        help="Upload a report file with Employee sections, Date, Hours, Sales columns (e.g. report_pyt.csv).",
                    )
                    st.caption("💡 Or pick a report from the **sidebar** (Saved Reports or Google Drive).")
                    # Use: tab upload first, then sidebar selection (saved or Google Drive)
                    wvs_report_file = wvs_uploaded
                    if not wvs_report_file and report_file is not None:
                        fname = getattr(report_file, "name", "") or ""
                        if fname.lower().endswith(".csv"):
                            wvs_report_file = report_file
                            if hasattr(report_file, "seek"):
                                report_file.seek(0)
                        else:
                            st.info("Sidebar report is not CSV. Upload a CSV above or select a CSV from the sidebar.")
                    if wvs_report_file:
                        if wvs_report_file is not wvs_uploaded:
                            st.caption(f"📂 Using: **{getattr(wvs_report_file, 'name', 'report')}** (from sidebar)")
                        try:
                            if hasattr(wvs_report_file, "seek"):
                                wvs_report_file.seek(0)
                            raw = wvs_report_file.read()
                            if isinstance(raw, bytes):
                                try:
                                    content = raw.decode("utf-8")
                                except UnicodeDecodeError:
                                    content = raw.decode("latin-1")
                            else:
                                content = str(raw)
                            lines = content.split("\n")
                            all_rows = []
                            max_cols = 0
                            for line in lines:
                                if not line.strip():
                                    continue
                                row = []
                                current_field = ""
                                in_quotes = False
                                for char in line:
                                    if char == '"':
                                        in_quotes = not in_quotes
                                    elif char == "," and not in_quotes:
                                        row.append(current_field.strip())
                                        current_field = ""
                                    else:
                                        current_field += char
                                if current_field or row:
                                    row.append(current_field.strip())
                                if row:
                                    all_rows.append(row)
                                    max_cols = max(max_cols, len(row))
                            for row in all_rows:
                                while len(row) < max_cols:
                                    row.append("")
                            df = pd.DataFrame(all_rows, columns=range(max_cols))
                        except Exception as e:
                            st.error(f"Could not read file: {e}")
                        else:
                            name_mapping = emp_config_full.get("name_mapping", {}) or {}
                            exclude_patterns = emp_config_full.get("exclude_patterns", []) or []
                            processor = DataProcessor(name_mapping=name_mapping, exclude_patterns=exclude_patterns)
                            records = processor.parse_csv(df)
                            if not records:
                                st.warning("No valid records found. Check file format and name mappings.")
                            else:
                                # Aggregate by (Employee, Date): sum Hours, sum Sales, sum AddlSales
                                from collections import defaultdict
                                agg = defaultdict(lambda: {"hours": 0.0, "sales": 0.0, "addl_sales": 0.0})
                                for r in records:
                                    emp = r.get("Employee", "").strip()
                                    date = r.get("Date")
                                    if not emp or not date:
                                        continue
                                    key = (emp, date)
                                    agg[key]["hours"] += float(r.get("Hours", 0) or 0)
                                    agg[key]["sales"] += float(r.get("Sales", 0) or 0)
                                    agg[key]["addl_sales"] += float(r.get("AddlSales", 0) or 0)

                                # Load wage brackets and engine
                                wage_brackets_wvs = []
                                base_id_wvs, api_key_wvs, _ = _get_airtable_credentials(shop_key_wvs)
                                if base_id_wvs and api_key_wvs:
                                    tables_cfg_wvs = (load_config() or {}).get("airtable_config_tables", {})
                                    bracket_table = tables_cfg_wvs.get("uk_wage_bracket", "UK Wage Bracket")
                                    try:
                                        at_client_wvs = AirtableClient(api_key=api_key_wvs)
                                        wage_brackets_wvs = at_client_wvs.get_wage_brackets(base_id_wvs, bracket_table)
                                    except Exception:
                                        pass
                                engine_wvs = CalculationEngine(employees_wvs, bonuses_wvs or {}, wage_brackets=wage_brackets_wvs)

                                total_wages_wvs = 0.0
                                total_sales_wvs = 0.0
                                detail_rows = []
                                for (emp_name, date_str), data in agg.items():
                                    hours = data["hours"]
                                    sales = data["sales"]
                                    addl = data["addl_sales"]
                                    day_sales_total = sales + addl
                                    if hours > 0 or sales > 0 or addl > 0:
                                        daily_calc = engine_wvs.calculate_daily_payment(emp_name, hours, sales, addl, date_str)
                                        base_pay = daily_calc.get("Base", 0)
                                        commission = daily_calc.get("Commission", 0)
                                        emp_config = employees_wvs.get(emp_name)
                                        if not emp_config:
                                            emp_name_lower = emp_name.lower()
                                            for k, v in employees_wvs.items():
                                                if k.lower() == emp_name_lower:
                                                    emp_config = v
                                                    break
                                        payment_type = (emp_config or {}).get("payment_type", "")
                                        if payment_type in ("tiered_commission", "hybrid_daily_max"):
                                            day_wages = max(base_pay, commission)
                                        else:
                                            day_wages = base_pay + commission
                                        total_wages_wvs += day_wages
                                        total_sales_wvs += day_sales_total
                                        day_pct = (day_wages / day_sales_total * 100) if day_sales_total > 0 else None
                                        detail_rows.append({
                                            "Employee": emp_name,
                                            "Date": date_str,
                                            "Hours": hours,
                                            "Sales": format_currency(sales),
                                            "Add'l Sales": format_currency(addl),
                                            "Total Sales": format_currency(day_sales_total),
                                            "Base": format_currency(base_pay),
                                            "Commission": format_currency(commission),
                                            "Total Wages": format_currency(day_wages),
                                            "Wage %": "N/A" if day_pct is None else f"{day_pct:.2f}%",
                                            "_sales_raw": day_sales_total,
                                            "_wages_raw": day_wages,
                                            "_wage_pct_raw": float("nan") if day_pct is None else round(day_pct, 2),
                                            "_base_raw": base_pay,
                                            "_commission_raw": commission,
                                            "_hrly_rate_raw": daily_calc.get("HrlyRate", 0),
                                            "_sales_only_raw": sales,
                                            "_addl_raw": addl,
                                            "_payment_type_raw": payment_type,
                                        })

                                st.success(f"Imported {len(records)} records from report")
                                wage_pct = (total_wages_wvs / total_sales_wvs * 100) if total_sales_wvs > 0 else 0.0
                                target_pct = 25.0
                                st.markdown("---")
                                st.markdown("### Result")
                                col_a, col_b, col_c = st.columns(3)
                                with col_a:
                                    st.metric("Total wages (from report)", format_currency(total_wages_wvs))
                                with col_b:
                                    st.metric("Total sales", format_currency(total_sales_wvs))
                                with col_c:
                                    st.metric("Wage % of sales", f"{wage_pct:.2f}%")
                                if total_sales_wvs > 0:
                                    if wage_pct < target_pct - 1:
                                        st.success("🟢 **Under target** – wages are below 25% of sales.")
                                    elif wage_pct <= target_pct + 1:
                                        st.info("🟡 **On target** – wages are around 25% of sales.")
                                    else:
                                        st.error("🔴 **Over target** – wages are above 25% of sales.")

                                if detail_rows:
                                    st.markdown("#### Charts")
                                    _render_wage_vs_sales_charts(
                                        detail_rows, total_wages_wvs, total_sales_wvs, target_pct
                                    )
                                    st.markdown("---")

                                if detail_rows:
                                    by_employee = defaultdict(list)
                                    for r in detail_rows:
                                        by_employee[r["Employee"]].append(r)
                                    for emp_name in sorted(by_employee.keys()):
                                        emp_rows = by_employee[emp_name]
                                        emp_rows.sort(key=lambda x: x["Date"])
                                        days_count = len(emp_rows)
                                        emp_total_sales = sum(r["_sales_raw"] for r in emp_rows)
                                        emp_total_wages = sum(r["_wages_raw"] for r in emp_rows)
                                        emp_avg_pct_str = "N/A" if emp_total_sales <= 0 else f"{(emp_total_wages / emp_total_sales * 100):.2f}%"
                                        with st.expander(f"**{emp_name}** — {days_count} days worked · Avg wage %: {emp_avg_pct_str}", expanded=True):
                                            table_rows = [{k: v for k, v in r.items() if not k.startswith("_")} for r in emp_rows]
                                            st.dataframe(
                                                pd.DataFrame(table_rows),
                                                width="stretch",
                                                hide_index=True,
                                            )
                                            dates_fmt = [_format_date_for_chart(r["Date"]) for r in emp_rows]
                                            st.caption("Wage % over time (target: 25%)")
                                            pct_df = pd.DataFrame(
                                                {"Wage %": [r["_wage_pct_raw"] for r in emp_rows]},
                                                index=dates_fmt,
                                            )
                                            st.line_chart(pct_df)
                                            st.caption("Wages vs Sales per day (£)")
                                            amounts_df = pd.DataFrame(
                                                {
                                                    "Wages (£)": [r["_wages_raw"] for r in emp_rows],
                                                    "Sales (£)": [r["_sales_raw"] for r in emp_rows],
                                                },
                                                index=dates_fmt,
                                            )
                                            st.bar_chart(amounts_df)

                                # Save to Airtable (import path)
                                if detail_rows and base_id_wvs and api_key_wvs:
                                    st.markdown("---")
                                    st.subheader("Save to Airtable")
                                    config_full = load_config() or {}
                                    shop_config_wvs = config_full.get("shops", {}).get(shop_key_wvs, {})
                                    tables_cfg_wvs_save = config_full.get("airtable_config_tables", {})
                                    table_name_wvs = shop_config_wvs.get("wage_vs_sales_table") or tables_cfg_wvs_save.get("wage_vs_sales") or ""
                                    if table_name_wvs and st.button("Save wage vs sales to Airtable", key="wvs_save_import_btn"):
                                        wage_vs_sales_table_name = shop_config_wvs.get("wage_vs_sales_table") or tables_cfg_wvs_save.get("wage_vs_sales") or ""
                                        is_wage_vs_sales_table = bool(wage_vs_sales_table_name) and table_name_wvs == wage_vs_sales_table_name
                                        shop_display_wvs = shop_config_wvs.get("shop_display_name") or shop_config_wvs.get("name", "")
                                        # Resolve employee names to record IDs if Wage vs Sales has linked record fields
                                        emp_name_to_id = {}
                                        if is_wage_vs_sales_table and base_id_wvs and api_key_wvs:
                                            try:
                                                at_resolve = AirtableClient(api_key=api_key_wvs)
                                                emp_table = tables_cfg_wvs_save.get("employees", "Employees")
                                                emp_recs = at_resolve.get_employee_records_with_ids(base_id_wvs, emp_table, shop_display_name=shop_display_wvs, active_only=False)
                                                emp_name_to_id = {str(r.get("Name", "")).strip(): r["id"] for r in emp_recs if r.get("Name")}
                                            except Exception:
                                                pass
                                        airtable_records_wvs = []
                                        for r in detail_rows:
                                            pct = r.get("_wage_pct_raw")
                                            wage_pct_val = round(pct, 2) if pct is not None and pct == pct else None  # exclude NaN
                                            emp_name = r["Employee"]
                                            sales_val = r.get("_sales_only_raw", 0)
                                            addl_val = r.get("_addl_raw", 0)
                                            base_val = r.get("_base_raw", 0)
                                            commission_val = r.get("_commission_raw", 0)
                                            if is_wage_vs_sales_table:
                                                rec = {
                                                    "Shop": shop_display_wvs,
                                                    "Date": r["Date"],
                                                    "Hours": r["Hours"],
                                                    "Sales": sales_val,
                                                    "Add'l Sales": addl_val,
                                                    "Total Sales": r.get("_sales_raw", sales_val + addl_val),
                                                    "Base": base_val,
                                                    "Commission": commission_val,
                                                    "Total Wages": r.get("_wages_raw", base_val + commission_val),
                                                }
                                                emp_link_field = tables_cfg_wvs_save.get("wage_vs_sales_employee_link_field") or shop_config_wvs.get("wage_vs_sales_employee_link_field") or "Employee"
                                                emp_id = emp_name_to_id.get(emp_name) or emp_name_to_id.get(emp_name.strip())
                                                if emp_id:
                                                    rec[emp_link_field] = [emp_id]
                                                else:
                                                    rec[emp_link_field] = emp_name
                                                if wage_pct_val is not None:
                                                    rec["Wage %"] = wage_pct_val
                                            else:
                                                rec = {
                                                    "RecordType": "Daily",
                                                    "Employee": emp_name,
                                                    "Date": r["Date"],
                                                    "Hours": r["Hours"],
                                                    "Sales": sales_val,
                                                    "AddlSales": addl_val,
                                                    "HrlyRate": r.get("_hrly_rate_raw", 0),
                                                    "Base": base_val,
                                                    "Commission": commission_val,
                                                    "PaymentType": r.get("_payment_type_raw", ""),
                                                }
                                            airtable_records_wvs.append(rec)
                                        try:
                                            with st.spinner("Saving to Airtable..."):
                                                at_client_save = AirtableClient(api_key=api_key_wvs)
                                                result = at_client_save.append_daily_breakdown(
                                                    base_id_wvs, table_name_wvs, airtable_records_wvs,
                                                    skip_duplicates=True,
                                                )
                                            st.success(f"Saved {result.get('records_created', 0)} records to Airtable.")
                                            if result.get("skipped", 0) > 0:
                                                st.info(f"Skipped {result['skipped']} existing records (duplicates).")
                                            if result.get("message"):
                                                st.caption(result["message"])
                                        except Exception as e:
                                            st.error(f"Failed to save: {e}")
                                            with st.expander("Details"):
                                                import traceback
                                                st.code(traceback.format_exc())
                                    elif not table_name_wvs:
                                        st.caption("Configure wage_vs_sales_table per shop or wage_vs_sales in airtable_config_tables (config/shops.yaml) to save.")
                                        with st.expander("Debug: config values"):
                                            st.code(f"shop_key: {shop_key_wvs}")
                                            st.code(f"wage_vs_sales_table (shop): {shop_config_wvs.get('wage_vs_sales_table')}")
                                            st.code(f"wage_vs_sales (tables): {tables_cfg_wvs_save.get('wage_vs_sales')}")
                                        if st.button("🔄 Clear cache & reload", key="wvs_clear_cache_import"):
                                            st.cache_data.clear()
                                            st.rerun()
                    else:
                        st.info("Upload a report file above, or pick one from the sidebar (Saved Reports / Google Drive).")

                else:
                    # --- Manual entry path ---
                    wvs_mode = st.radio(
                        "Period",
                        options=["Single day", "Date range"],
                        key="wvs_mode",
                        horizontal=True,
                        help="Choose a single day or a date range (interval) to enter data for.",
                    )

                    wvs_dates = []
                    if wvs_mode == "Single day":
                        wvs_start = st.date_input(
                            "Date",
                            value=st.session_state.get("wage_vs_sales_date", datetime.today().date()),
                            key="wage_vs_sales_date",
                            help="The day you are entering data for.",
                        )
                        wvs_dates = [wvs_start]
                    else:
                        col_start, col_end = st.columns(2)
                        with col_start:
                            wvs_start = st.date_input(
                                "Start date",
                                value=st.session_state.get("wvs_range_start", datetime.today().date()),
                                key="wvs_range_start",
                            )
                        with col_end:
                            wvs_end = st.date_input(
                                "End date",
                                value=st.session_state.get("wvs_range_end", datetime.today().date()),
                                key="wvs_range_end",
                            )
                        if wvs_end < wvs_start:
                            st.warning("End date must be on or after start date.")
                            wvs_dates = []
                        else:
                            num_days = (wvs_end - wvs_start).days + 1
                            if num_days > 31:
                                st.warning("Maximum 31 days per range. Please shorten the interval.")
                                wvs_dates = []
                            else:
                                wvs_dates = [wvs_start + timedelta(days=i) for i in range(num_days)]

                    # Load wage brackets and engine once (manual entry only)
                    wage_brackets_wvs = []
                    base_id_wvs, api_key_wvs, _ = _get_airtable_credentials(shop_key_wvs)
                    if base_id_wvs and api_key_wvs:
                        tables_cfg_wvs = (load_config() or {}).get("airtable_config_tables", {})
                        bracket_table = tables_cfg_wvs.get("uk_wage_bracket", "UK Wage Bracket")
                        try:
                            at_client_wvs = AirtableClient(api_key=api_key_wvs)
                            wage_brackets_wvs = at_client_wvs.get_wage_brackets(base_id_wvs, bracket_table)
                        except Exception:
                            pass
                    engine_wvs = CalculationEngine(employees_wvs, bonuses_wvs or {}, wage_brackets=wage_brackets_wvs)

                    total_wages_wvs = 0.0
                    total_sales_wvs = 0.0
                    manual_detail_rows = []

                    for d in wvs_dates:
                        date_str_wvs = d.strftime("%Y-%m-%d")
                        day_label = d.strftime("%a %d %b") if wvs_mode == "Date range" else "Hours & sales per staff"
                        with st.expander(f"**{day_label}** ({date_str_wvs})", expanded=(wvs_mode == "Single day" or len(wvs_dates) <= 7)):
                            staff_working_wvs = st.multiselect(
                                "Staff working",
                                options=employee_names_wvs,
                                default=[],
                                key=f"wvs_staff_{date_str_wvs}",
                                help="Select everyone who worked on this date.",
                            )
                            wvs_data = {}
                            for name in staff_working_wvs:
                                c1, c2 = st.columns(2)
                                with c1:
                                    hours_val = st.number_input(
                                        f"Hours – {name}",
                                        min_value=0.0,
                                        step=0.5,
                                        value=0.0,
                                        format="%.1f",
                                        key=f"wvs_hours_{date_str_wvs}_{name}",
                                    )
                                with c2:
                                    sales_val = st.number_input(
                                        f"Sales (£) – {name}",
                                        min_value=0.0,
                                        step=50.0,
                                        value=0.0,
                                        format="%.2f",
                                        key=f"wvs_sales_{date_str_wvs}_{name}",
                                    )
                                wvs_data[name] = {"hours": hours_val, "sales": sales_val}

                            for name, data in wvs_data.items():
                                hours = data["hours"]
                                sales = data["sales"]
                                if hours > 0 or sales > 0:
                                    daily_calc = engine_wvs.calculate_daily_payment(
                                        name, hours, sales, 0.0, date_str_wvs
                                    )
                                    base_pay = daily_calc.get("Base", 0)
                                    commission = daily_calc.get("Commission", 0)
                                    emp_cfg = employees_wvs.get(name)
                                    if not emp_cfg:
                                        for k, v in employees_wvs.items():
                                            if k.lower() == name.lower():
                                                emp_cfg = v
                                                break
                                    pt = (emp_cfg or {}).get("payment_type", "")
                                    if pt in ("tiered_commission", "hybrid_daily_max"):
                                        day_wages = max(base_pay, commission)
                                    else:
                                        day_wages = base_pay + commission
                                    total_wages_wvs += day_wages
                                    total_sales_wvs += sales
                                    day_pct = (day_wages / sales * 100) if sales > 0 else None
                                    manual_detail_rows.append({
                                        "Employee": name,
                                        "Date": date_str_wvs,
                                        "Hours": hours,
                                        "_sales_raw": sales,
                                        "_wages_raw": day_wages,
                                        "_sales_only_raw": sales,
                                        "_addl_raw": 0.0,
                                        "_base_raw": base_pay,
                                        "_commission_raw": commission,
                                        "_hrly_rate_raw": daily_calc.get("HrlyRate", 0),
                                        "_payment_type_raw": pt,
                                        "_wage_pct_raw": round(day_pct, 2) if day_pct is not None else None,
                                    })

                    wage_pct = (total_wages_wvs / total_sales_wvs * 100) if total_sales_wvs > 0 else 0.0
                    target_pct = 25.0

                    st.markdown("---")
                    st.markdown("### Result")
                    period_label = "period" if wvs_mode == "Date range" else "daily"
                    col_a, col_b, col_c = st.columns(3)
                    with col_a:
                        st.metric(f"Total wages ({period_label})", format_currency(total_wages_wvs))
                    with col_b:
                        st.metric("Total sales", format_currency(total_sales_wvs))
                    with col_c:
                        st.metric("Wage % of sales", f"{wage_pct:.2f}%")

                    if total_sales_wvs > 0:
                        if wage_pct < target_pct - 1:
                            st.success("🟢 **Under target** – wages are below 25% of sales.")
                        elif wage_pct <= target_pct + 1:
                            st.info("🟡 **On target** – wages are around 25% of sales.")
                        else:
                            st.error("🔴 **Over target** – wages are above 25% of sales.")
                    else:
                        st.info("Enter hours and sales above to see the wage % and target indicator.")

                    if manual_detail_rows:
                        st.markdown("#### Charts")
                        _render_wage_vs_sales_charts(
                            manual_detail_rows, total_wages_wvs, total_sales_wvs, target_pct
                        )
                        st.markdown("---")

                    # Save to Airtable (manual entry path)
                    if manual_detail_rows and base_id_wvs and api_key_wvs:
                        st.markdown("---")
                        st.subheader("Save to Airtable")
                        config_full_manual = load_config() or {}
                        shop_config_wvs_manual = config_full_manual.get("shops", {}).get(shop_key_wvs, {})
                        tables_cfg_wvs_manual = config_full_manual.get("airtable_config_tables", {})
                        table_name_wvs_manual = shop_config_wvs_manual.get("wage_vs_sales_table") or tables_cfg_wvs_manual.get("wage_vs_sales") or ""
                        if table_name_wvs_manual and st.button("Save wage vs sales to Airtable", key="wvs_save_manual_btn"):
                            wage_vs_sales_table_name_manual = shop_config_wvs_manual.get("wage_vs_sales_table") or tables_cfg_wvs_manual.get("wage_vs_sales") or ""
                            is_wage_vs_sales_table_manual = bool(wage_vs_sales_table_name_manual) and table_name_wvs_manual == wage_vs_sales_table_name_manual
                            shop_display_wvs_manual = shop_config_wvs_manual.get("shop_display_name") or shop_config_wvs_manual.get("name", "")
                            emp_name_to_id_manual = {}
                            if is_wage_vs_sales_table_manual and base_id_wvs and api_key_wvs:
                                try:
                                    at_resolve_manual = AirtableClient(api_key=api_key_wvs)
                                    emp_table_manual = tables_cfg_wvs_manual.get("employees", "Employees")
                                    emp_recs_manual = at_resolve_manual.get_employee_records_with_ids(base_id_wvs, emp_table_manual, shop_display_name=shop_display_wvs_manual, active_only=False)
                                    emp_name_to_id_manual = {str(r.get("Name", "")).strip(): r["id"] for r in emp_recs_manual if r.get("Name")}
                                except Exception:
                                    pass
                            airtable_records_wvs_manual = []
                            for r in manual_detail_rows:
                                pct = r.get("_wage_pct_raw")
                                wage_pct_val = round(pct, 2) if pct is not None and pct == pct else None  # exclude NaN
                                emp_name = r["Employee"]
                                sales_val = r.get("_sales_only_raw", 0)
                                addl_val = r.get("_addl_raw", 0)
                                base_val = r.get("_base_raw", 0)
                                commission_val = r.get("_commission_raw", 0)
                                if is_wage_vs_sales_table_manual:
                                    rec = {
                                        "Shop": shop_display_wvs_manual,
                                        "Date": r["Date"],
                                        "Hours": r["Hours"],
                                        "Sales": sales_val,
                                        "Add'l Sales": addl_val,
                                        "Total Sales": sales_val + addl_val,
                                        "Base": base_val,
                                        "Commission": commission_val,
                                        "Total Wages": base_val + commission_val,
                                    }
                                    emp_link_field_manual = tables_cfg_wvs_manual.get("wage_vs_sales_employee_link_field") or shop_config_wvs_manual.get("wage_vs_sales_employee_link_field") or "Employee"
                                    emp_id = emp_name_to_id_manual.get(emp_name) or emp_name_to_id_manual.get(emp_name.strip())
                                    if emp_id:
                                        rec[emp_link_field_manual] = [emp_id]
                                    else:
                                        rec[emp_link_field_manual] = emp_name
                                    if wage_pct_val is not None:
                                        rec["Wage %"] = wage_pct_val
                                else:
                                    rec = {
                                        "RecordType": "Daily",
                                        "Employee": emp_name,
                                        "Date": r["Date"],
                                        "Hours": r["Hours"],
                                        "Sales": sales_val,
                                        "AddlSales": addl_val,
                                        "HrlyRate": r.get("_hrly_rate_raw", 0),
                                        "Base": base_val,
                                        "Commission": commission_val,
                                        "PaymentType": r.get("_payment_type_raw", ""),
                                    }
                                airtable_records_wvs_manual.append(rec)
                            try:
                                with st.spinner("Saving to Airtable..."):
                                    at_client_save_manual = AirtableClient(api_key=api_key_wvs)
                                    result = at_client_save_manual.append_daily_breakdown(
                                        base_id_wvs, table_name_wvs_manual, airtable_records_wvs_manual,
                                        skip_duplicates=True,
                                    )
                                st.success(f"Saved {result.get('records_created', 0)} records to Airtable.")
                                if result.get("skipped", 0) > 0:
                                    st.info(f"Skipped {result['skipped']} existing records (duplicates).")
                                if result.get("message"):
                                    st.caption(result["message"])
                            except Exception as e:
                                st.error(f"Failed to save: {e}")
                                with st.expander("Details"):
                                    import traceback
                                    st.code(traceback.format_exc())
                        elif not table_name_wvs_manual:
                            st.caption("Configure wage_vs_sales_table per shop or wage_vs_sales in airtable_config_tables (config/shops.yaml) to save.")
                            with st.expander("Debug: config values"):
                                st.code(f"shop_key: {shop_key_wvs}")
                                st.code(f"wage_vs_sales_table (shop): {shop_config_wvs_manual.get('wage_vs_sales_table')}")
                                st.code(f"wage_vs_sales (tables): {tables_cfg_wvs_manual.get('wage_vs_sales')}")
                            if st.button("🔄 Clear cache & reload", key="wvs_clear_cache_manual"):
                                st.cache_data.clear()
                                st.rerun()

    with tab6:
        from tabs.data_management import render as render_data_management
        render_data_management(selected_shop, shop_config, config)

    with tab7:
        from tabs.shop_analytics import render as render_shop_analytics
        render_shop_analytics(selected_shop, shop_config, config)

    with tab8:
        from tabs.employee_evolution import render as render_employee_evolution
        render_employee_evolution(selected_shop, shop_config, config, report_file)


if __name__ == "__main__":
    main()
