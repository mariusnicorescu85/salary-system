"""
Salary Calculation Dashboard
Main Streamlit application for running salary calculations
"""

import streamlit as st
import pandas as pd
import yaml
import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
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
from src.airtable_client import AirtableClient
from src.email_client import EmailClient
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
    st.session_state.target_approved = 0.0
if 'target_total_reached' not in st.session_state:
    st.session_state.target_total_reached = 0.0
if 'target_current_date' not in st.session_state:
    st.session_state.target_current_date = datetime.today().date()
if 'daily_target_date' not in st.session_state:
    st.session_state.daily_target_date = datetime.today().date()
if 'selected_saved_report' not in st.session_state:
    st.session_state.selected_saved_report = None
if 'selected_gdrive_report' not in st.session_state:
    st.session_state.selected_gdrive_report = None  # {'id': str, 'name': str}

# Saved reports directory for persisting uploaded files
SAVED_REPORTS_DIR = Path("saved_reports")


def _ensure_saved_reports_dir():
    """Create saved_reports directory if it doesn't exist."""
    SAVED_REPORTS_DIR.mkdir(parents=True, exist_ok=True)


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


def _get_google_drive_client():
    """Get Google Drive client if configured (Service Account from secrets, or OAuth from credentials/)."""
    try:
        # Service Account (for Streamlit Cloud)
        sa_json = None
        if hasattr(st, 'secrets') and st.secrets.get('google_drive', {}).get('service_account_json'):
            sa_json = st.secrets.google_drive.service_account_json
        if sa_json:
            return GoogleDriveClient(service_account_json=sa_json)
        # OAuth (local - credentials in credentials/ folder)
        creds_path = Path('credentials/google_drive_credentials.json')
        if creds_path.exists():
            return GoogleDriveClient()
    except Exception as e:
        logger.debug(f"Google Drive not available: {e}")
    return None


def _get_saved_reports_folder_id(shop_key: str) -> str:
    """Get the folder ID for saved reports for a given shop from config."""
    config = load_config()
    if not config or not shop_key:
        return ""
    shop = config.get('shops', {}).get(shop_key, {})
    return (shop.get('saved_reports_folder_id') or "").strip()


def _save_report_to_gdrive(uploaded_file, folder_id: str) -> bool:
    """Save uploaded file to Google Drive. Returns True on success."""
    if not uploaded_file or not folder_id:
        return False
    client = _get_google_drive_client()
    if not client:
        return False
    try:
        uploaded_file.seek(0)
        content = uploaded_file.read()
        ext = Path(uploaded_file.name).suffix.lower()
        now = datetime.now()
        filename = f"report_{now.month:02d}_{now.year}{ext}"
        file_id = client.upload_file(content, filename, folder_id)
        return file_id is not None
    except Exception as e:
        logger.error(f"Failed to save report to Google Drive: {e}")
        return False


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


@st.cache_data
def load_config():
    """Load shop configuration"""
    config_path = Path('config/shops.yaml')
    if not config_path.exists():
        st.error("Configuration file not found. Please create config/shops.yaml")
        return None
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
        # Debug: log config to help diagnose caching issues
        return config


def _get_airtable_credentials(shop_key: str = None):
    """
    Get Airtable base_id, api_key, and table names. Used when system is Airtable-only.
    Returns (base_id, api_key, tables_dict) or (None, None, None) if credentials missing.
    """
    config = load_config()
    if not config or not config.get("shops"):
        return None, None, None
    shop = config["shops"].get(shop_key) if shop_key else list(config["shops"].values())[0]
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
        
        emp = {
            "payment_type": rec.get("Payment Type") or "hourly_only",
            "hourly_rate": hourly_rate,
            "email": rec.get("Email") or "",
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


def format_currency(value: float) -> str:
    """Format value as currency"""
    return f"£{value:,.2f}"


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


def save_monthly_bonuses(shop_key: str, year: int, month: int, bonuses: Dict, shop_filter_override: Optional[str] = None):
    """Save monthly bonuses to Airtable (Monthly Bonuses table)."""
    base_id, api_key, _ = _get_airtable_credentials(shop_key)
    if not base_id or not api_key:
        logger.warning("Cannot save monthly bonuses: missing Airtable credentials")
        return
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
    except Exception as e:
        logger.warning("Airtable save_monthly_bonuses failed: %s", e)


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


def save_shop_targets(targets: Dict):
    """Persist monthly sales targets per shop to Airtable."""
    base_id, api_key, tables = _get_airtable_credentials()
    if not base_id or not api_key or not tables:
        logger.warning("Cannot save shop targets: missing Airtable credentials")
        return
    try:
        client = AirtableClient(api_key=api_key)
        client.save_shop_targets(base_id, tables[0], targets)
    except Exception as e:
        logger.warning("Airtable save_shop_targets failed: %s", e)


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
    editable_cols = ["Name", "Shop", "Date of Birth", "Email", "Payment Type", "Hourly Rate Override", "Commission Rate", "Daily Transport", "Rent", "Advance", "Employment Status"]
    num_cols = ("Hourly Rate Override", "Commission Rate", "Daily Transport", "Rent", "Advance")
    if records:
        rows = []
        for r in records:
            row = {"_id": r.get("id", "")}
            for col in editable_cols:
                val = r.get(col)
                row[col] = "" if val is None else (", ".join(str(x) for x in val) if isinstance(val, list) else str(val).strip())
            rows.append(row)
        df = pd.DataFrame(rows)
        id_col, edit_df = df["_id"], df.drop(columns=["_id"])
        col_config = {
            "Name": st.column_config.TextColumn("Name", required=True),
            "Shop": st.column_config.SelectboxColumn("Shop", options=shop_options, required=True),
            "Date of Birth": st.column_config.TextColumn("Date of Birth"),
            "Email": st.column_config.TextColumn("Email"),
            "Payment Type": st.column_config.SelectboxColumn("Payment Type", options=payment_types),
            "Hourly Rate Override": st.column_config.NumberColumn("Hourly Rate", format="%.2f"),
            "Commission Rate": st.column_config.NumberColumn("Commission Rate", format="%.2f"),
            "Daily Transport": st.column_config.NumberColumn("Daily Transport", format="%.2f"),
            "Rent": st.column_config.NumberColumn("Rent", format="%.2f"),
            "Advance": st.column_config.NumberColumn("Advance", format="%.2f"),
            "Employment Status": st.column_config.SelectboxColumn("Employment Status", options=["Active", "Inactive"]),
        }
        edited = st.data_editor(edit_df, column_config=col_config, use_container_width=True, num_rows="fixed", key="dm_emp_editor")
        if st.button("💾 Save changes", type="primary", key="dm_emp_save"):
            changed, errors = 0, []
            for i in range(len(edited)):
                if edit_df.iloc[i].to_dict() != edited.iloc[i].to_dict():
                    fields = {}
                    for k, v in edited.iloc[i].items():
                        if k in editable_cols:
                            if v == "" or (isinstance(v, float) and pd.isna(v)):
                                fields[k] = None
                            elif k in num_cols:
                                try: fields[k] = float(v)
                                except (TypeError, ValueError): fields[k] = v
                            else:
                                fields[k] = str(v).strip()
                    try:
                        client.update_record(base_id, emp_table, id_col.iloc[i], fields)
                        changed += 1
                    except Exception as ex:
                        errors.append(f"{edited.iloc[i].get('Name', '?')}: {ex}")
            if changed:
                st.success(f"✅ Updated {changed}.")
                st.cache_data.clear()
                st.rerun()
            for e in errors:
                st.error(e)
        with st.expander("➕ Add employee"):
            with st.form("dm_add_emp"):
                n1, n2 = st.columns(2)
                with n1:
                    na = st.text_input("Name", key="dm_emp_na")
                    em = st.text_input("Email", key="dm_emp_em")
                    sh = st.selectbox("Shop", shop_options, key="dm_emp_sh")
                    pt = st.selectbox("Payment Type", payment_types, key="dm_emp_pt")
                    sts = st.selectbox("Employment Status", ["Active", "Inactive"], key="dm_emp_sts")
                with n2:
                    hr = st.number_input("Hourly Rate", value=0.0, step=0.01, format="%.2f", key="dm_emp_hr")
                    cr = st.number_input("Commission Rate", value=0.0, step=0.01, format="%.2f", key="dm_emp_cr")
                    dt = st.number_input("Daily Transport", value=0.0, step=0.01, format="%.2f", key="dm_emp_dt")
                if st.form_submit_button("Add"):
                    if na and na.strip():
                        flds = {"Name": na.strip(), "Shop": sh, "Payment Type": pt, "Employment Status": sts}
                        if em.strip(): flds["Email"] = em.strip()
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
            sh = st.selectbox("Shop", shop_options, key="dm_first_sh")
            if st.form_submit_button("Add"):
                if na and na.strip():
                    client.create_record(base_id, emp_table, {"Name": na.strip(), "Shop": sh, "Payment Type": "hourly_only"})
                    st.cache_data.clear()
                    st.rerun()


def _render_commission_tiers_tab(client, base_id, tables_cfg, shop_display, shop_options, config):
    tiers_table = tables_cfg.get("commission_tiers", "Commission Tiers")
    emp_table = tables_cfg.get("employees", "Employees")
    name_to_id = _emp_name_to_id_map(client, base_id, emp_table, shop_display)
    id_to_name = {v: k for k, v in name_to_id.items()}
    formula = f'{{Shop (from Employees)}} = "{shop_display}"' if shop_display else None
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
        edited = st.data_editor(edit_df, column_config=col_config, use_container_width=True, num_rows="fixed", key="dm_ct_editor")
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
    formula = f'{{Shop}} = "{shop_display}"' if shop_display else None
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
                shop_str = str(shop_val[0])
            else:
                shop_str = str(shop_val) if shop_val else (shop_display or "")
            rows.append({"_id": r.get("id"), "Report Name": r.get("Report Name") or "", "Employees": emp_name, "Shop": shop_str})
        df = pd.DataFrame(rows)
        id_col, edit_df = df["_id"], df.drop(columns=["_id"])
        edited = st.data_editor(edit_df, column_config={"Report Name": st.column_config.TextColumn("Report Name"), "Employees": st.column_config.SelectboxColumn("Employee", options=sorted(name_to_id.keys())), "Shop": st.column_config.SelectboxColumn("Shop", options=shop_options)}, use_container_width=True, num_rows="fixed", key="dm_nm_editor")
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
    formula = f'{{Shop}} = "{shop_display}"' if shop_display else None
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
        edited = st.data_editor(edit_df, column_config={"Month": st.column_config.SelectboxColumn("Month", options=months), "Employees": st.column_config.SelectboxColumn("Employee", options=sorted(name_to_id.keys())), "Sales Threshold": st.column_config.NumberColumn("Sales Threshold", format="%.2f"), "Bonus Amount": st.column_config.NumberColumn("Bonus Amount", format="%.2f")}, use_container_width=True, num_rows="fixed", key="dm_sb_editor")
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
    formula = f'{{Shop}} = "{shop_display}"' if shop_display else None
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
        edited = st.data_editor(edit_df, column_config=col_cfg, use_container_width=True, num_rows="fixed", key="dm_mb_editor")
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
        edited = st.data_editor(edit_df, column_config=col_config, use_container_width=True, num_rows="fixed", key="dm_wb_editor")
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
            if st.button("🚪 Logout", use_container_width=True):
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
        submitted = st.form_submit_button("Login", type="primary", use_container_width=True)
        
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
    
    shops = list(config['shops'].keys())
    
    # Sidebar for shop selection and settings
    with st.sidebar:
        st.header("Settings")
        
        selected_shop = st.selectbox("Select Shop", shops)
        shop_config = config['shops'][selected_shop]
        # Persist selected shop in session state for use in other tabs (e.g. email sending)
        st.session_state.selected_shop = selected_shop
        
        st.markdown("---")
        api_key_check = (hasattr(st, "secrets") and st.secrets.get("airtable", {}).get("api_key")) or os.getenv("AIRTABLE_API_KEY") or st.session_state.get("airtable_api_key", "")
        if not api_key_check:
            st.warning("⚠️ Airtable API key required")
            api_key_input = st.text_input("Airtable API key", type="password", key="airtable_api_key_sidebar", help="Set AIRTABLE_API_KEY env var or add to Streamlit secrets to skip")
            if api_key_input:
                st.session_state.airtable_api_key = api_key_input
                st.success("✅ API key saved for this session")
        else:
            st.success("✅ Airtable API key found")
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
                        if _save_report_to_gdrive(uploaded_file, gdrive_folder):
                            st.success("✅ Saved to Google Drive!")
                            st.rerun()
                        else:
                            st.error("Failed to save to Drive")
                elif gdrive_folder and not gdrive_client:
                    st.caption("⚠️ Configure Google Drive credentials to save")
        
        # Saved reports selector - use previously saved report instead of re-uploading
        saved_reports = _list_saved_reports()
        if saved_reports:
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
                if st.button("🗑️ Clear Selection", help="Clear saved report selection"):
                    st.session_state.selected_saved_report = None
                    st.rerun()
        else:
            st.session_state.selected_saved_report = None
        
        # Google Drive reports - load from Drive (persists on cloud, per-shop folder)
        gdrive_folder = _get_saved_reports_folder_id(selected_shop)
        gdrive_files = _list_gdrive_reports(gdrive_folder) if gdrive_folder else []
        if gdrive_files:
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
                if st.button("🗑️ Clear Drive Selection", key="clear_gdrive"):
                    st.session_state.selected_gdrive_report = None
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
        
        st.markdown("---")
        st.subheader("📤 Airtable Export (Optional)")
        
        st.info("💡 **Tip**: Run calculations first to review results, then enable Airtable export when ready.")
        
        append_to_airtable = st.checkbox(
            "Enable Airtable Export",
            help="Append results to Airtable after calculation (disabled by default for testing)"
        )
        
        if append_to_airtable:
            # Try to get API key from secrets, env var, or session state
            api_key_from_secrets = None
            try:
                if hasattr(st, 'secrets') and 'airtable' in st.secrets and 'api_key' in st.secrets.airtable:
                    api_key_from_secrets = st.secrets.airtable.api_key
            except:
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
    
    # Main content area – larger, easier-to-see tabs
    st.markdown(
        """
        <style>
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
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "Monthly Bonuses",
        "Calculate",
        "Results",
        "Airtable Preview",
        "Sales Target Tracker",
        "Data Management",
    ])
    
    with tab1:
        st.header("📝 Monthly Bonuses")
        st.info("💡 Add bonuses per employee for each month. **Save** them, then go to **Calculate** to run salary calculations.")
        
        # Load employee configuration from Airtable
        employees, bonuses, emp_config_full = load_employee_config(selected_shop)
        
        if not employees:
            st.error("⚠️ Failed to load from Airtable. Check Base ID, API key, and that Employees table has records for this shop.")
            st.stop()
        
        # Month/Year selector
        col1, col2 = st.columns(2)
        with col1:
            selected_year = st.selectbox("Year", range(2024, 2027), index=1 if datetime.now().year == 2025 else 0, key="bonus_year")
        with col2:
            selected_month = st.selectbox("Month", range(1, 13), index=datetime.now().month - 1, key="bonus_month")
        
        month_name = datetime(selected_year, selected_month, 1).strftime('%B %Y')
        month_key = f"{selected_year}-{selected_month:02d}"
        shop_display_adj = shop_config.get("shop_display_name") or shop_config.get("name", selected_shop)
        
        # Sub-tabs: Monthly Bonuses (used in calculations) and Import CSV
        sub_tab_bonus, sub_tab_import = st.tabs(["💰 Monthly Bonuses", "📤 Import CSV"])
        
        with sub_tab_bonus:
            st.subheader(f"Monthly Bonuses for {month_name}")
            st.caption("These bonuses are added to calculations when you run salary calculations.")
            
            # Load existing monthly bonuses
            month_bonuses_data = load_monthly_bonuses(selected_shop, selected_year, selected_month, shop_filter_override=shop_display_adj)
            
            # Show saved vs unsaved counts
            saved_employees = set(month_bonuses_data.keys())
            all_employees = set(employees.keys())
            unsaved = all_employees - saved_employees
            st.info(f"**Saved:** {len(saved_employees)} employee(s)  •  **Not yet saved:** {len(unsaved)} employee(s)")
            
            # Employee selector with ✓ for saved employees
            employee_options = [f"{name} ✓" if name in saved_employees else name for name in sorted(employees.keys())]
            selected_display = st.selectbox(
                "Select Employee",
                employee_options,
                key="bonus_employee_selector"
            )
            selected_employee_bonus = selected_display.replace(" ✓", "").strip() if selected_display else None
            
            if selected_employee_bonus:
                base_bonuses = bonuses.get(selected_employee_bonus, {})
                current_bonuses = month_bonuses_data.get(selected_employee_bonus, {})
                if not current_bonuses:
                    current_bonuses = base_bonuses.copy()
                
                st.markdown("---")
                saved_badge = " ✓ Saved" if selected_employee_bonus in saved_employees else " (not yet saved)"
                st.subheader(f"Bonuses for {selected_employee_bonus}{saved_badge}")
                
                with st.form(f"bonus_form_{selected_employee_bonus}"):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown("### 💰 Bonuses")
                        daily_sales_bonus = st.number_input("Daily Sales Bonus", value=float(current_bonuses.get('dailySalesBonus', 0)), step=1.0, key="b_daily_sales")
                        first_last_hour = st.number_input("First/Last Hour Bonus", value=float(current_bonuses.get('firstLastHourBonus', 0)), step=1.0, key="b_first_last")
                        social_media = st.number_input("Social Media Bonus", value=float(current_bonuses.get('socialMediaBonus', 0)), step=1.0, key="b_social_media")
                        management = st.number_input("Management Bonus", value=float(current_bonuses.get('managementBonus', 0)), step=1.0, key="b_management")
                        management_consistency = st.number_input("Management Consistency Bonus", value=float(current_bonuses.get('managementConsistencyBonus', 0)), step=1.0, key="b_mgmt_cons")
                        transport_fuel = st.number_input("Transport/Fuel", value=float(current_bonuses.get('transportFuel', 0)), step=1.0, key="b_transport")
                        personal_sales = st.number_input("Personal Sales Bonus", value=float(current_bonuses.get('personalSalesBonus', 0)), step=1.0, key="b_personal_sales")
                        extra_bonus = st.number_input("Extra Bonus", value=float(current_bonuses.get('extraBonus', 0)), step=1.0, key="b_extra")
                        daily_allowance = st.number_input("Daily Allowance", value=float(current_bonuses.get('dailyAllowance', 0)), step=1.0, key="b_daily_allowance")
                    with c2:
                        st.markdown("### 📊 Other")
                        manual_hours = st.number_input("Manual Hours", value=float(current_bonuses.get('manualHours', 0)), step=0.5, key="b_manual_hours")
                        deductions = st.number_input("Deductions", value=float(current_bonuses.get('deductions', 0)), step=1.0, key="b_deductions")
                        rent = st.number_input("Rent", value=float(current_bonuses.get('rent', 0)), step=1.0, key="b_rent")
                        base_advance = employees.get(selected_employee_bonus, {}).get('advance', 0)
                        advance = st.number_input("Advance", value=float(current_bonuses.get('advance', base_advance)), step=1.0, key="b_advance")
                    
                    total_bonus = daily_sales_bonus + first_last_hour + social_media + management + management_consistency + transport_fuel + personal_sales + extra_bonus + daily_allowance
                    st.markdown("---")
                    st.metric("Total Bonus", format_currency(total_bonus))
                    
                    st.caption("💡 Save one employee at a time. After saving, the employee will show ✓ in the list above.")
                    if st.form_submit_button("💾 Save to Monthly Bonuses"):
                        if selected_employee_bonus not in month_bonuses_data:
                            month_bonuses_data[selected_employee_bonus] = {}
                        month_bonuses_data[selected_employee_bonus] = {
                            'dailySalesBonus': daily_sales_bonus, 'firstLastHourBonus': first_last_hour,
                            'socialMediaBonus': social_media, 'managementBonus': management,
                            'managementConsistencyBonus': management_consistency, 'transportFuel': transport_fuel,
                            'personalSalesBonus': personal_sales, 'extraBonus': extra_bonus,
                            'dailyAllowance': daily_allowance, 'manualHours': manual_hours,
                            'deductions': deductions, 'rent': rent, 'advance': advance
                        }
                        save_monthly_bonuses(selected_shop, selected_year, selected_month, month_bonuses_data, shop_filter_override=shop_display_adj)
                        st.success(f"✅ Saved bonuses for {selected_employee_bonus} - {month_name}")
                        st.cache_data.clear()
                        st.rerun()
            
            if month_bonuses_data:
                st.markdown("---")
                st.subheader(f"All Bonuses for {month_name}")
                bonus_data = []
                for emp_name, emp_b in month_bonuses_data.items():
                    tb = sum([emp_b.get('dailySalesBonus', 0), emp_b.get('firstLastHourBonus', 0), emp_b.get('socialMediaBonus', 0),
                              emp_b.get('managementBonus', 0), emp_b.get('managementConsistencyBonus', 0), emp_b.get('transportFuel', 0),
                              emp_b.get('personalSalesBonus', 0), emp_b.get('extraBonus', 0), emp_b.get('dailyAllowance', 0)])
                    bonus_data.append({'Employee': emp_name, 'Total Bonus': format_currency(tb), 'Deductions': format_currency(emp_b.get('deductions', 0)),
                                       'Rent': format_currency(emp_b.get('rent', 0)), 'Advance': format_currency(emp_b.get('advance', 0)), 'Manual Hours': emp_b.get('manualHours', 0)})
                if bonus_data:
                    st.dataframe(pd.DataFrame(bonus_data), width='stretch', hide_index=True)
        
        with sub_tab_import:
            st.subheader("Import Monthly Bonuses from CSV")
            st.caption("Upload a CSV (e.g. Monthly Bonuses-Grid view.csv from Airtable) to populate the Monthly Bonuses table.")
            csv_file = st.file_uploader("Choose CSV file", type=["csv"], key="monthly_bonus_csv")
            if csv_file:
                csv_content = csv_file.read().decode("utf-8-sig")
                import_col1, import_col2 = st.columns(2)
                with import_col1:
                    import_month = st.text_input("Month (YYYY-MM)", value=month_key, key="import_bonus_month")
                with import_col2:
                    if st.button("Import to Airtable"):
                        base_id, api_key, _ = _get_airtable_credentials(selected_shop)
                        if base_id and api_key:
                            try:
                                client = AirtableClient(api_key=api_key)
                                tables = (load_config() or {}).get("airtable_config_tables", {})
                                bonus_table = tables.get("monthly_bonus", "Monthly Bonuses")
                                emp_table = tables.get("employees", "Employees")
                                id_to_name = client._get_employee_id_to_name(base_id, emp_table, shop_display_adj)
                                name_to_id = {v: k for k, v in id_to_name.items()}
                                result = client.import_monthly_bonuses_from_csv(
                                    base_id, bonus_table, csv_content, import_month,
                                    employee_name_to_id=name_to_id,
                                    shop_display_name=shop_display_adj,
                                )
                                if result.get("errors"):
                                    st.error("Import had errors: " + "; ".join(result["errors"]))
                                else:
                                    st.success(f"✅ Imported {result.get('created', 0)} records. Skipped {result.get('skipped', 0)}.")
                                    st.cache_data.clear()
                                    st.rerun()
                            except Exception as e:
                                st.error(f"Import failed: {e}")
                        else:
                            st.warning("Airtable credentials required.")
    
    with tab2:
        st.header(f"💰 Calculate Salaries - {shop_config['name']}")
        
        if report_file is not None:
            st.success(f"✅ File ready: **{report_file.name}** ({report_file.size:,} bytes)")
        else:
            st.info("📤 Please upload a report file or select a saved report using the sidebar")
        
        st.markdown("---")
        
        if st.button("🚀 Run Calculation", type="primary", use_container_width=False):
            with st.spinner("Processing..."):
                try:
                    # Load employee configuration from Airtable
                    employees, bonuses, emp_config_full = load_employee_config(selected_shop)
                    if employees is None:
                        st.error("❌ Failed to load from Airtable. Ensure Base ID is in config/shops.yaml and Airtable API key is set (env AIRTABLE_API_KEY, Streamlit secrets, or sidebar).")
                        st.stop()
                    
                    if not employees:
                        st.error("Failed to load employee configuration from Airtable. Check: Base ID in config/shops.yaml, API key (env/secrets/sidebar), and that Employees table has records for this shop.")
                        st.stop()
                    
                    # Load data (file upload or saved report)
                    if report_file is None:
                        st.error("❌ Please upload a file or select a saved report using the sidebar")
                        st.stop()
                    
                    st.info(f"📄 Processing file: **{report_file.name}**")
                    
                    try:
                        logger.info(f"Loading file: {report_file.name}")
                        if report_file.name.endswith('.csv'):
                            # Read CSV as text first to handle variable column structure
                            logger.info("Reading CSV as text to handle variable column structure...")
                            report_file.seek(0)
                            
                            # Read entire file as text
                            try:
                                content = report_file.read()
                                if isinstance(content, bytes):
                                    # Try different encodings
                                    for encoding in ['utf-8', 'latin-1', 'cp1252']:
                                        try:
                                            content = content.decode(encoding)
                                            logger.info(f"Successfully decoded with {encoding}")
                                            break
                                        except:
                                            continue
                                else:
                                    content = str(content)
                                
                                lines = content.split('\n')
                                logger.info(f"File has {len(lines)} lines")
                                logger.info(f"First 10 lines:\n" + '\n'.join(lines[:10]))
                                
                                # Parse manually into a list of lists
                                all_rows = []
                                max_cols = 0
                                for line_num, line in enumerate(lines):
                                    if not line.strip():
                                        continue
                                    # Split by comma, handling quoted fields
                                    row = []
                                    current_field = ""
                                    in_quotes = False
                                    
                                    for char in line:
                                        if char == '"':
                                            in_quotes = not in_quotes
                                        elif char == ',' and not in_quotes:
                                            row.append(current_field.strip())
                                            current_field = ""
                                        else:
                                            current_field += char
                                    
                                    if current_field or row:  # Add last field
                                        row.append(current_field.strip())
                                    
                                    if row:
                                        all_rows.append(row)
                                        max_cols = max(max_cols, len(row))
                                    
                                    if line_num < 5:
                                        logger.debug(f"Line {line_num}: {len(row)} columns - {row[:3]}")
                                
                                logger.info(f"Parsed {len(all_rows)} rows, max columns: {max_cols}")
                                
                                # Create DataFrame with consistent column count
                                # Pad rows to max_cols
                                for row in all_rows:
                                    while len(row) < max_cols:
                                        row.append('')
                                
                                df = pd.DataFrame(all_rows, columns=range(max_cols))
                                logger.info(f"Created DataFrame: {df.shape}")
                                logger.info(f"First 5 rows:\n{df.head()}")
                                
                            except Exception as e:
                                logger.error(f"Error reading CSV as text: {e}")
                                # Fallback to pandas
                                report_file.seek(0)
                                encodings = ['utf-8', 'latin-1', 'cp1252']
                                df = None
                                
                                for encoding in encodings:
                                    try:
                                        report_file.seek(0)
                                        try:
                                            df = pd.read_csv(
                                                report_file, 
                                                encoding=encoding, 
                                                header=None,
                                                on_bad_lines='skip',
                                                engine='python'
                                            )
                                            logger.info(f"Read CSV with {encoding} encoding (pandas 2.x): {df.shape}")
                                            break
                                        except TypeError:
                                            report_file.seek(0)
                                            df = pd.read_csv(
                                                report_file, 
                                                encoding=encoding, 
                                                header=None,
                                                error_bad_lines=False,
                                                warn_bad_lines=False,
                                                engine='python'
                                            )
                                            logger.info(f"Read CSV with {encoding} encoding (pandas 1.x): {df.shape}")
                                            break
                                    except Exception as e2:
                                        logger.warning(f"{encoding} failed: {e2}")
                                        continue
                                
                                if df is None:
                                    raise Exception("Failed to read CSV with any method")
                        else:
                            logger.info("Reading Excel file...")
                            df = pd.read_excel(report_file)
                            logger.info(f"Successfully read Excel: {df.shape}")
                        
                        logger.info(f"File loaded: {len(df)} rows, {len(df.columns)} columns")
                        logger.info(f"Column names: {list(df.columns)}")
                        logger.info(f"First row data: {df.iloc[0].tolist() if len(df) > 0 else 'Empty'}")
                        st.success(f"✅ File loaded successfully ({len(df)} rows, {len(df.columns)} columns)")
                        
                        # Show preview of the file
                        with st.expander("👀 Preview Raw File (First 10 Rows)", expanded=False):
                            st.dataframe(df.head(10), width='stretch')
                            st.write(f"**Columns:** {list(df.columns)}")
                    except Exception as e:
                        st.error(f"❌ Error reading file: {str(e)}")
                        st.stop()
                    
                    # Process data
                    with st.spinner("🔄 Parsing data..."):
                        # Load name mapping from employee config
                        name_mapping = emp_config_full.get('name_mapping', {}) if emp_config_full else {}
                        exclude_patterns = emp_config_full.get('exclude_patterns', []) if emp_config_full else []
                        
                        logger.info(f"Loaded {len(name_mapping)} name mappings")
                        logger.info(f"Loaded {len(exclude_patterns)} exclude patterns")
                        
                        if name_mapping:
                            st.info(f"📝 Using {len(name_mapping)} name mappings")
                        
                        logger.info("Initializing DataProcessor...")
                        processor = DataProcessor(
                            name_mapping=name_mapping,
                            exclude_patterns=exclude_patterns
                        )
                        
                        logger.info("Starting CSV parsing...")
                        records = processor.parse_csv(df)
                        logger.info(f"Parsing complete: {len(records)} records created")
                        
                        # Show name mapping summary
                        if hasattr(processor, 'mapping_stats') and processor.mapping_stats:
                            stats = processor.mapping_stats
                            if stats['mapped'] > 0 or stats['excluded'] > 0:
                                with st.expander("📝 Name Mapping Summary", expanded=False):
                                    st.write(f"**Total processed:** {stats['total_processed']}")
                                    st.write(f"**Names mapped:** {stats['mapped']}")
                                    st.write(f"**Names excluded:** {stats['excluded']}")
                                    if stats['mapping_details']:
                                        st.write("**Mappings applied:**")
                                        for original, mapped in stats['mapping_details'].items():
                                            st.write(f"  • `{original}` → `{mapped}`")
                    
                    if not records:
                        st.error("❌ No valid records found in the file. Please check the file format.")
                        st.info("💡 The file should contain employee data with Date, Hours, Sales columns")
                        
                        # Show debug info if available
                        if hasattr(processor, 'mapping_stats') and processor.mapping_stats.get('debug_info'):
                            with st.expander("🔍 Debug Information", expanded=True):
                                for info in processor.mapping_stats['debug_info']:
                                    st.write(f"• {info}")
                        
                        # Show file structure help
                        with st.expander("📋 Expected File Format", expanded=False):
                            st.write("""
                            Your CSV file should have one of these formats:
                            
                            **Option 1: Standard CSV with columns**
                            - Date, Employee, Hours, Sales, etc.
                            
                            **Option 2: Report format with employee sections**
                            - Rows starting with "Employee: [Name]"
                            - Followed by data rows with Date, Hours, Sales, etc.
                            
                            **Common column names accepted:**
                            - Date: "Date", "Dates"
                            - Employee: "Employee", "Employees", "Name", "Names"
                            - Hours: "Hours", "Hour", "Hrs"
                            - Sales: "Sales", "Sale", "Total Sales"
                            - Additional Sales: "Add'l Sales", "Addl Sales", "Additional Sales"
                            """)
                        
                        st.stop()
                    
                    st.success(f"✅ Parsed {len(records)} valid records")
                    
                    # Load monthly adjustments if available
                    # Use most common month from records (more reliable than first record)
                    month_adjustments = {}
                    if records:
                        try:
                            from collections import Counter
                            months = [datetime.strptime(r['Date'], '%Y-%m-%d') for r in records if r.get('Date')]
                            if months:
                                (year, month), _ = Counter((m.year, m.month) for m in months).most_common(1)[0]
                                month_key = f"{year}-{month:02d}"
                                shop_display = shop_config.get("shop_display_name") or shop_config.get("name", selected_shop)
                                month_bonuses = load_monthly_bonuses(
                                    selected_shop, year, month, shop_filter_override=shop_display
                                )
                                logger.info("Monthly bonuses load: shop=%s, month=%s, count=%d", selected_shop, month_key, len(month_bonuses or {}))
                                
                                # Merge monthly bonuses with base bonuses (case-insensitive employee match)
                                if month_bonuses:
                                    merged_bonuses = bonuses.copy()
                                    employees_lower_map = {e.lower(): e for e in employees.keys()}
                                    for emp_from_at, emp_bonus_data in month_bonuses.items():
                                        # Match employee (Airtable may have different casing)
                                        emp_key = employees_lower_map.get((emp_from_at or '').lower())
                                        if emp_key:
                                            merged_bonuses[emp_key].update(emp_bonus_data)
                                        else:
                                            merged_bonuses[emp_from_at] = emp_bonus_data
                                    bonuses = merged_bonuses
                                    
                                    for emp_from_at, emp_bonus_data in month_bonuses.items():
                                        emp_key = employees_lower_map.get((emp_from_at or '').lower())
                                        if emp_key and 'advance' in emp_bonus_data and emp_key in employees:
                                            employees[emp_key]['advance'] = emp_bonus_data['advance']
                                    
                                    st.info(f"📅 Loaded monthly bonuses for {datetime(year, month, 1).strftime('%B %Y')} ({len(month_bonuses)} employee(s))")
                                else:
                                    st.warning(f"⚠️ No monthly bonuses found for {datetime(year, month, 1).strftime('%B %Y')}. Add rows to the **Monthly Bonuses** table in Airtable with **Month** = `{month_key}` (and **Shop** if your table has it).")
                        except Exception as e:
                            logger.warning(f"Could not load monthly adjustments: {e}")
                            st.warning(f"⚠️ Could not load monthly adjustments: {e}")
                    
                    # Load UK wage brackets from Airtable (for employees with DOB, no hourly override)
                    wage_brackets = []
                    base_id, api_key, _ = _get_airtable_credentials(selected_shop)
                    if base_id and api_key:
                        tables = (load_config() or {}).get("airtable_config_tables", {})
                        bracket_table = tables.get("uk_wage_bracket", "UK Wage Bracket")
                        try:
                            at_client = AirtableClient(api_key=api_key)
                            wage_brackets = at_client.get_wage_brackets(base_id, bracket_table)
                            if wage_brackets:
                                logger.info(f"Loaded {len(wage_brackets)} UK wage bracket rules from Airtable ({bracket_table})")
                        except Exception as e:
                            logger.warning(f"Could not load wage brackets from Airtable: {e}")
                    
                    # Initialize calculation engine
                    engine = CalculationEngine(employees, bonuses, wage_brackets=wage_brackets)
                    
                    # Group records by employee
                    employee_records = {}
                    for record in records:
                        emp_name = record['Employee']
                        if emp_name not in employee_records:
                            employee_records[emp_name] = []
                        employee_records[emp_name].append(record)
                    
                    # Calculate for each employee
                    with st.spinner("🧮 Calculating salaries..."):
                        results = {}
                        all_daily_calculations = []
                        
                        progress_bar = st.progress(0)
                        total_employees = len(employee_records)
                        
                        missing_employees = []
                        zero_calc_employees = []
                        found_employees = []
                        
                        # Create case-insensitive lookup for employees
                        employees_lower = {k.lower(): k for k in employees.keys()}
                        
                        for idx, (emp_name, emp_records) in enumerate(employee_records.items()):
                            # Check if employee is in config (case-insensitive)
                            emp_name_lower = emp_name.lower()
                            if emp_name_lower not in employees_lower:
                                missing_employees.append(emp_name)
                                logger.warning(f"Employee '{emp_name}' not found in employee config (checked: {emp_name_lower})")
                                logger.info(f"Available employees: {list(employees.keys())[:10]}...")
                            else:
                                # Use the correctly-cased name from config
                                correct_name = employees_lower[emp_name_lower]
                                if correct_name != emp_name:
                                    logger.info(f"Employee name case mismatch: '{emp_name}' -> '{correct_name}'")
                                    emp_name = correct_name
                                found_employees.append(emp_name)
                            
                            daily_calcs = []
                            for record in emp_records:
                                daily_calc = engine.calculate_daily_payment(
                                    emp_name,
                                    record['Hours'],
                                    record['Sales'],
                                    record['AddlSales'],
                                    record['Date']
                                )
                                daily_calcs.append(daily_calc)
                                all_daily_calculations.append(daily_calc)
                            
                            summary = engine.calculate_monthly_summary(daily_calcs)
                            
                            # Check if employee has zero final payment
                            if summary.get('FinalPayment', 0) == 0 and summary.get('WorkedHours', 0) > 0:
                                zero_calc_employees.append(emp_name)
                                logger.warning(f"Employee '{emp_name}' has zero final payment but worked {summary.get('WorkedHours', 0)} hours")
                            
                            results[emp_name] = {
                                'summary': summary,
                                'daily': daily_calcs
                            }
                            
                            progress_bar.progress((idx + 1) / total_employees)
                        
                        progress_bar.empty()
                        
                        # Show summary of employee calculations
                        st.info(f"📊 **Calculation Summary:** {len(found_employees)} employees found in config, {len(missing_employees)} missing, {len(zero_calc_employees)} with zero calculations")
                        
                        # Show warnings for missing or zero-calculation employees
                        if missing_employees:
                            st.warning(f"⚠️ **{len(missing_employees)} employee(s) not found in config:** {', '.join(sorted(missing_employees))}")
                            st.info("💡 These employees will have zero calculations. Please add them to the employee config file.")
                            # Show available employee names for reference
                            with st.expander("📋 Available employee names in config"):
                                st.write(", ".join(sorted(employees.keys())))
                        
                        if zero_calc_employees:
                            st.warning(f"⚠️ **{len(zero_calc_employees)} employee(s) have zero calculations:** {', '.join(sorted(zero_calc_employees))}")
                            st.info("💡 Check their payment_type and hourly_rate in the employee config file.")
                            # Show details for zero-calculation employees
                            with st.expander("🔍 Details for zero-calculation employees"):
                                for emp in zero_calc_employees:
                                    if emp in results:
                                        summary = results[emp]['summary']
                                        emp_config = employees.get(emp, {})
                                        st.write(f"**{emp}:**")
                                        st.write(f"- Payment Type: {emp_config.get('payment_type', 'N/A')}")
                                        st.write(f"- Hourly Rate: {emp_config.get('hourly_rate', 0)}")
                                        st.write(f"- Worked Hours: {summary.get('WorkedHours', 0)}")
                                        st.write(f"- Total Sales: £{summary.get('TotalSales', 0):.2f}")
                                        st.write(f"- Final Payment: £{summary.get('FinalPayment', 0):.2f}")
                                        st.write("---")
                    
                    st.session_state.results = results
                    st.session_state.calculations_done = True
                    st.session_state.all_daily_calculations = all_daily_calculations
                    # Store employee configuration and shop key for later use (e.g. email sending)
                    st.session_state.employees_config = employees
                    st.session_state.results_shop_key = selected_shop
                    
                    # Always prepare Airtable records for preview (even if export is disabled)
                    # Include both daily records and monthly summary records with full breakdown
                    airtable_records = []
                    
                    # Add daily records
                    for calc in all_daily_calculations:
                        airtable_records.append({
                            'RecordType': 'Daily',
                            'Employee': calc['Employee'],
                            'Date': calc['Date'],
                            'Hours': calc['Hours'],
                            'Sales': calc['Sales'],
                            'AddlSales': calc['AddlSales'],
                            'HrlyRate': calc['HrlyRate'],
                            'Base': calc['Base'],
                            'Commission': calc['Commission'],
                            'PaymentType': calc['PaymentType']
                        })
                    
                    # Add monthly summary records with full bonus breakdown
                    for emp_name, emp_data in results.items():
                        summary = emp_data['summary']
                        bonus_breakdown = summary.get('BonusBreakdown', {})
                        
                        # Extract month/year from daily records for this employee
                        employee_daily_records = [calc for calc in all_daily_calculations if calc['Employee'] == emp_name]
                        month_period = ''
                        month_year = ''
                        if employee_daily_records:
                            try:
                                # Get first date from daily records
                                first_date = datetime.strptime(employee_daily_records[0]['Date'], '%Y-%m-%d')
                                # Format as "2024-11" for easy filtering
                                month_period = first_date.strftime('%Y-%m')
                                # Format as "November 2024" for display
                                month_year = first_date.strftime('%B %Y')
                            except Exception as e:
                                pass
                        
                        # Main summary record
                        airtable_records.append({
                            'RecordType': 'Monthly Summary',
                            'Employee': emp_name,
                            'Date': '',  # Empty for summary records
                            'Month': month_period,  # Format: "2024-11" for easy querying
                            'MonthYear': month_year,  # Format: "November 2024" for display
                            'WorkedDays': summary.get('WorkedDays', 0),
                            'WorkedHours': summary.get('WorkedHours', 0),
                            'Sales': summary.get('Sales', 0),
                            'AddlSales': summary.get('AddlSales', 0),
                            'AdjustedSales': summary.get('AdjustedSales', 0),
                            'AvgSalePerDay': summary.get('AvgSalePerDay', 0),
                            'RatePerHour': summary.get('RatePerHour', 0),
                            'HoursSalary': summary.get('HoursSalary', 0),
                            'TotalCommission': summary.get('TotalCommission', 0),
                            'TotalBonus': summary.get('TotalBonus', 0),
                            # Bonus breakdown
                            'DailySalesBonus': bonus_breakdown.get('DailySalesBonus', 0),
                            'FirstLastHourBonus': bonus_breakdown.get('FirstLastHourBonus', 0),
                            'SocialMediaBonus': bonus_breakdown.get('SocialMediaBonus', 0),
                            'ManagementBonus': bonus_breakdown.get('ManagementBonus', 0),
                            'ManagementConsistencyBonus': bonus_breakdown.get('ManagementConsistencyBonus', 0),
                            'TransportFuel': bonus_breakdown.get('TransportFuel', 0),
                            'PersonalSalesBonus': bonus_breakdown.get('PersonalSalesBonus', 0),
                            'ExtraBonus': bonus_breakdown.get('ExtraBonus', 0),
                            'DailyAllowance': bonus_breakdown.get('DailyAllowance', 0),
                            # Other fields
                            'ManualHours': summary.get('ManualHours', 0),
                            'ManualHoursPay': summary.get('ManualHoursPay', 0),
                            'Deductions': summary.get('Deductions', 0),
                            'Rent': summary.get('Rent', 0),
                            'Advance': summary.get('Advance', 0),
                            'FinalPayment': summary.get('FinalPayment', 0),
                            'PaymentType': summary.get('PaymentType', '')
                        })
                    
                    # Sort: Daily records first (by Date, then Employee), then Monthly Summary (by Employee)
                    def _sort_key(r):
                        rt = r.get('RecordType', '')
                        if rt == 'Daily':
                            return (0, r.get('Date', ''), r.get('Employee', ''))
                        return (1, '', r.get('Employee', ''))
                    airtable_records.sort(key=_sort_key)
                    
                    st.session_state.airtable_records = airtable_records
                    st.session_state.airtable_summaries = {emp: data['summary'] for emp, data in results.items()}
                    
                    # Show employee processing summary
                    all_csv_employees = set(record['Employee'] for record in records)
                    calculated_employees = set(results.keys())
                    unprocessed = all_csv_employees - calculated_employees
                    
                    if unprocessed:
                        st.warning(f"⚠️ **{len(unprocessed)} employee(s) from CSV were not processed:** {', '.join(sorted(unprocessed))}")
                    
                    st.success(f"✅ Calculations complete for {len(results)} employees!")
                    st.info(f"📤 **{len(airtable_records)} records** prepared for Airtable export (see 'Airtable Preview' tab)")
                    
                    # Show detailed summary
                    with st.expander("📋 Processing Summary"):
                        st.write(f"**Total employees in CSV:** {len(all_csv_employees)}")
                        st.write(f"**Employees with calculations:** {len(calculated_employees)}")
                        if missing_employees:
                            st.write(f"**Missing from config:** {len(missing_employees)} - {', '.join(missing_employees)}")
                        if zero_calc_employees:
                            st.write(f"**Zero calculations:** {len(zero_calc_employees)} - {', '.join(zero_calc_employees)}")
                        if unprocessed:
                            st.write(f"**Not processed:** {len(unprocessed)} - {', '.join(sorted(unprocessed))}")
                
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
                    import traceback
                    with st.expander("🔍 Error Details"):
                        st.code(traceback.format_exc())
        
        # Airtable export section - shown when calculations done (persists across reruns so Confirm & Append works)
        if st.session_state.calculations_done and append_to_airtable:
            st.markdown("---")
            st.subheader("📤 Quick Airtable Export")
            st.info("💡 For detailed preview and export, go to the **'Airtable Preview'** tab")
            
            # Use shop config for the results (may differ from current sidebar selection)
            export_shop_key = st.session_state.get('results_shop_key') or selected_shop
            export_shop_config = config['shops'].get(export_shop_key, shop_config)
            base_id = export_shop_config.get('airtable_base_id')
            table_name = export_shop_config.get('airtable_table_name')
            
            if base_id and table_name and airtable_api_key:
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Base ID:** {base_id}")
                with col2:
                    st.write(f"**Table:** {table_name}")
                
                export_mode = st.radio(
                    "📤 Export Mode",
                    ["Skip duplicates (append only new)", "Update existing records", "Upsert (update existing + create new)"],
                    index=0,
                    help="""
                    - **Skip duplicates**: Only append new records, skip existing ones (prevents duplicates)
                    - **Update existing**: Only update records that already exist, don't create new ones
                    - **Upsert**: Update existing records AND create new ones (recommended for re-runs after adjustments)
                    """,
                    key="export_mode_calculate"
                )
                
                skip_duplicates = export_mode == "Skip duplicates (append only new)"
                update_existing = export_mode == "Update existing records"
                upsert_mode = export_mode == "Upsert (update existing + create new)"
                
                if st.button("✅ Confirm & Append to Airtable", type="primary"):
                    airtable_records = st.session_state.get('airtable_records', [])
                    if not airtable_records:
                        st.error("❌ No records to export. Please run a calculation first.")
                    else:
                        try:
                            with st.spinner("📤 Appending to Airtable..."):
                                airtable = AirtableClient(api_key=airtable_api_key)
                                result = airtable.append_daily_breakdown(
                                    base_id,
                                    table_name,
                                    airtable_records,
                                    skip_duplicates=skip_duplicates,
                                    update_existing=update_existing,
                                    upsert_mode=upsert_mode
                                )
                                
                                if update_existing:
                                    updated_count = result.get('records_updated', 0)
                                    not_found = result.get('not_found', [])
                                    st.success(f"✅ Successfully updated {updated_count} records in Airtable!")
                                    if not_found:
                                        st.warning(f"⚠️ {len(not_found)} records not found in Airtable (not created): {', '.join(not_found[:5])}{'...' if len(not_found) > 5 else ''}")
                                elif upsert_mode:
                                    st.success(f"✅ Successfully updated {result.get('records_updated', 0)} records and created {result.get('records_created', 0)} new records!")
                                elif result.get('skipped', 0) > 0:
                                    if result.get('records_created', 0) > 0:
                                        st.success(f"✅ Successfully appended {result['records_created']} new records to Airtable!")
                                        st.info(f"⏭️ Skipped {result['skipped']} existing records (duplicates)")
                                    else:
                                        st.info(f"⏭️ All {result['skipped']} records already exist in Airtable. No new records appended.")
                                else:
                                    st.success(f"✅ Successfully appended {result['records_created']} records to Airtable!")
                                
                                if result.get('message'):
                                    st.info(result['message'])
                                
                                st.balloons()
                        except Exception as e:
                            st.error(f"❌ Error appending to Airtable: {str(e)}")
                            import traceback
                            with st.expander("🔍 Error Details"):
                                st.code(traceback.format_exc())
            else:
                if not airtable_api_key:
                    st.warning("⚠️ Please enter your Airtable API key in the sidebar")
                if not base_id or not table_name:
                    st.warning("⚠️ Please configure Base ID and Table name in config/shops.yaml")
    
    with tab3:
        st.header("📊 Calculation Results")
        
        if not st.session_state.calculations_done:
            st.info("👆 Go to the **Calculate** tab and run a calculation first to see results here")
        else:
            results = st.session_state.results
            employees_config = st.session_state.get('employees_config', {})
            # Resolve the shop that these results belong to (not just the current sidebar selection)
            results_shop_key = st.session_state.get('results_shop_key')
            if not results_shop_key:
                # Fallback to current sidebar selection or first configured shop
                results_shop_key = st.session_state.get('selected_shop') or list(config['shops'].keys())[0]
            current_shop_config = config['shops'].get(results_shop_key, {})
            email_config = current_shop_config.get('email', {})
            default_from_email = email_config.get('from_email', '')
            default_management_recipients = email_config.get('management_recipients', []) or []
            
            # Summary table
            st.subheader("Monthly Summary")
            summary_data = []
            for emp_name, data in results.items():
                summary = data['summary']
                summary_data.append({
                    'Employee': emp_name,
                    'Days Worked': summary.get('WorkedDays', 0),
                    'Hours': summary.get('WorkedHours', 0),
                    'Sales': format_currency(summary.get('Sales', 0)),
                    'Hours Salary': format_currency(summary.get('HoursSalary', 0)),
                    'Commission': format_currency(summary.get('TotalCommission', 0)),
                    'Bonus': format_currency(summary.get('TotalBonus', 0)),
                    'Final Payment': format_currency(summary.get('FinalPayment', 0))
                })
            
            summary_df = pd.DataFrame(summary_data)
            st.dataframe(summary_df, width='stretch')
            
            # Employee selector
            st.subheader("Employee Details")
            selected_employee = st.selectbox(
                "Select Employee",
                list(results.keys())
            )
            
            if selected_employee:
                emp_data = results[selected_employee]
                summary = emp_data['summary']
                daily = emp_data['daily']
                
                # Display summary
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Days Worked", summary.get('WorkedDays', 0))
                with col2:
                    st.metric("Total Hours", summary.get('WorkedHours', 0))
                with col3:
                    st.metric("Total Sales", format_currency(summary.get('Sales', 0)))
                with col4:
                    st.metric("Final Payment", format_currency(summary.get('FinalPayment', 0)))
                
                # Detailed breakdown
                st.subheader("Payment Breakdown")
                breakdown_cols = ['Field', 'Value']
                breakdown_data = [
                    ['Worked Days', summary.get('WorkedDays', 0)],
                    ['Worked Hours', f"{summary.get('WorkedHours', 0):.2f}"],
                    ['Sales', format_currency(summary.get('Sales', 0))],
                    ['Additional Sales', format_currency(summary.get('AddlSales', 0))],
                    ['Adjusted Sales', format_currency(summary.get('AdjustedSales', 0))],
                    ['Hours Salary', format_currency(summary.get('HoursSalary', 0))],
                ]
                wage_breakdown = summary.get('WageBracketBreakdown', [])
                if not wage_breakdown:
                    breakdown_data.insert(-1, ['Rate per Hour', format_currency(summary.get('RatePerHour', 0))])
                if wage_breakdown:
                    for i, period in enumerate(wage_breakdown, 1):
                        date_from = period.get('date_from', '')
                        date_to = period.get('date_to', '')
                        label = f"{date_from} to {date_to}" if date_from != date_to else date_from
                        breakdown_data.append([f"  Period {i} ({label})", f"{period.get('hours', 0):.2f} hrs × £{period.get('rate', 0):.2f} = {format_currency(period.get('pay', 0))}"])
                
                if summary.get('TotalCommission', 0) > 0:
                    breakdown_data.append(['Total Commission', format_currency(summary.get('TotalCommission', 0))])
                
                if summary.get('TotalBonus', 0) > 0:
                    breakdown_data.append(['Total Bonus', format_currency(summary.get('TotalBonus', 0))])
                
                if summary.get('ManualHours', 0) > 0:
                    breakdown_data.append(['Manual Hours', f"{summary.get('ManualHours', 0):.2f}"])
                    breakdown_data.append(['Manual Hours Pay', format_currency(summary.get('ManualHoursPay', 0))])
                
                if summary.get('Deductions', 0) > 0:
                    breakdown_data.append(['Deductions', format_currency(-summary.get('Deductions', 0))])
                
                if summary.get('Rent', 0) > 0:
                    breakdown_data.append(['Rent', format_currency(-summary.get('Rent', 0))])
                
                if summary.get('Advance', 0) > 0:
                    breakdown_data.append(['Advance', format_currency(-summary.get('Advance', 0))])
                
                breakdown_data.append(['Final Payment', format_currency(summary.get('FinalPayment', 0))])
                
                breakdown_df = pd.DataFrame(breakdown_data, columns=breakdown_cols)
                # Ensure Value column is string type to avoid PyArrow conversion issues
                breakdown_df['Value'] = breakdown_df['Value'].astype(str)
                st.dataframe(breakdown_df, width='stretch', hide_index=True)
                
                # Daily breakdown
                st.subheader("Daily Breakdown")
                daily_df = pd.DataFrame(daily)
                st.dataframe(daily_df, width='stretch')
                
                # Download button
                csv = daily_df.to_csv(index=False)
                st.download_button(
                    label="Download Daily Breakdown CSV",
                    data=csv,
                    file_name=f"{selected_employee}_daily_breakdown.csv",
                    mime="text/csv"
                )
                
                # Bulk send to all staff
                st.subheader("📤 Send Breakdowns to All Staff")
                staff_with_email = [
                    (emp_name, employees_config.get(emp_name, {}).get('email', ''))
                    for emp_name in results.keys()
                ]
                staff_with_email = [(n, e) for n, e in staff_with_email if e]
                staff_without_email = [n for n in results.keys() if not (employees_config.get(n, {}).get('email', ''))]
                if staff_without_email:
                    st.caption(f"Employees without email in config (will be skipped): {', '.join(staff_without_email)}")
                if st.button("Send to all staff (each gets their own breakdown)", key="send_all_staff"):
                    if not staff_with_email:
                        st.error("No employees have email addresses. Add Email field to employee records in Airtable.")
                    elif not default_from_email:
                        st.error("Please set from_email in config/shops.yaml under the shop's email section.")
                    else:
                        try:
                            email_client = get_email_client_for_shop(results_shop_key)
                        except ValueError as e:
                            st.error(f"Email not configured: {e}")
                        else:
                            sent, failed = 0, 0
                            shop_name = current_shop_config.get('name', 'Shop')
                            invoice_email = email_config.get('invoice_submission_email', default_from_email)
                            for emp_name, emp_email in staff_with_email:
                                emp_data = results[emp_name]
                                html_content = email_client.create_breakdown_email(
                                    emp_name, emp_data['summary'], emp_data['daily'], emp_email,
                                    shop_name=shop_name, invoice_submission_email=invoice_email
                                )
                                subject = f"{current_shop_config.get('name', 'Shop')} - Salary Breakdown for {emp_name}"
                                if email_client.send_email(
                                    to_email=emp_email,
                                    subject=subject,
                                    html_content=html_content,
                                    from_email=default_from_email,
                                ):
                                    sent += 1
                                else:
                                    failed += 1
                            if sent > 0:
                                st.success(f"Sent {sent} breakdown(s) to staff." + (f" {failed} failed." if failed else ""))
                            else:
                                st.error("Failed to send any emails. Check email configuration and server logs.")
                
                # Email breakdown to the selected employee
                st.subheader("✉️ Email Breakdown to Employee (single)")
                employee_info = employees_config.get(selected_employee, {}) if isinstance(employees_config, dict) else {}
                default_employee_email = employee_info.get('email', '')
                from_email_input = st.text_input(
                    "From email (sender)",
                    value=default_from_email,
                    help="This should normally be the shop's email address",
                    key=f"employee_from_email_{selected_employee}",
                )
                employee_email_input = st.text_input(
                    "Employee email",
                    value=default_employee_email,
                    help="Email address for the selected employee (loaded from employee config where available)",
                    key=f"employee_to_email_{selected_employee}",
                )
                
                if st.button("Send breakdown to this employee", key="send_employee_email"):
                    if not employee_email_input:
                        st.error("Please provide an employee email address.")
                    elif not from_email_input:
                        st.error("Please provide a sender email address.")
                    else:
                        try:
                            email_client = get_email_client_for_shop(results_shop_key)
                        except ValueError as e:
                            st.error(f"Email not configured: {e}")
                        else:
                            shop_name = current_shop_config.get('name', 'Shop')
                            invoice_email = email_config.get('invoice_submission_email', default_from_email)
                            html_content = email_client.create_breakdown_email(
                                selected_employee,
                                summary,
                                daily,
                                employee_email_input,
                                shop_name=shop_name, invoice_submission_email=invoice_email
                            )
                            subject = f"{current_shop_config.get('name', 'Shop')} - Salary Breakdown for {selected_employee}"
                            success = email_client.send_email(
                                to_email=employee_email_input,
                                subject=subject,
                                html_content=html_content,
                                from_email=from_email_input,
                            )
                            if success:
                                st.success(f"Salary breakdown sent to {employee_email_input}")
                            else:
                                st.error("Failed to send email to employee. Check server logs for details.")
            
            # Email to management
            st.subheader("📨 Send Breakdowns to Management (for Approval)")
            if not results:
                st.info("No calculation results available to send.")
            else:
                # First: sender address
                mgmt_from_email_input = st.text_input(
                    "From email (sender)",
                    value=default_from_email,
                    help="Sender address for management emails (usually the shop email).",
                    key="management_from_email",
                )
                # Second: management recipient list
                management_recipients_str = ", ".join(default_management_recipients)
                management_recipients_input = st.text_input(
                    "Management recipient emails (comma-separated)",
                    value=management_recipients_str,
                    help="Management will receive the breakdowns for review and approval.",
                    key="management_recipients",
                )
                
                col_mgmt1, col_mgmt2 = st.columns(2)
                with col_mgmt1:
                    if st.button("Send consolidated breakdown (one email for approval)", key="send_management_consolidated"):
                        recipients = [e.strip() for e in management_recipients_input.split(",") if e.strip()]
                        if not recipients:
                            st.error("Please provide at least one management recipient email.")
                        elif not mgmt_from_email_input:
                            st.error("Please provide a sender email address for management emails.")
                        else:
                            try:
                                email_client = get_email_client_for_shop(results_shop_key)
                            except ValueError as e:
                                st.error(f"Email not configured: {e}")
                            else:
                                html_content = email_client.create_management_approval_email(
                                    shop_name=current_shop_config.get('name', 'Shop'),
                                    results=results,
                                )
                                subject = f"{current_shop_config.get('name', 'Shop')} - Salary Breakdowns for Approval"
                                sent = 0
                                for r in recipients:
                                    if email_client.send_email(
                                        to_email=r,
                                        subject=subject,
                                        html_content=html_content,
                                        from_email=mgmt_from_email_input,
                                    ):
                                        sent += 1
                                if sent > 0:
                                    st.success(f"Sent consolidated breakdown to {sent} management recipient(s).")
                                else:
                                    st.error("Failed to send email. Check email configuration and server logs.")
                with col_mgmt2:
                    if st.button("Send each breakdown separately (one email per employee)", key="send_management_emails"):
                        recipients = [e.strip() for e in management_recipients_input.split(",") if e.strip()]
                        if not recipients:
                            st.error("Please provide at least one management recipient email.")
                        elif not mgmt_from_email_input:
                            st.error("Please provide a sender email address for management emails.")
                        else:
                            try:
                                email_client = get_email_client_for_shop(results_shop_key)
                            except ValueError as e:
                                st.error(f"Email not configured: {e}")
                            else:
                                total_sent = 0
                                total_attempts = 0
                                for emp_name, emp_data in results.items():
                                    emp_summary = emp_data['summary']
                                    emp_daily = emp_data['daily']
                                    emp_info = employees_config.get(emp_name, {}) if isinstance(employees_config, dict) else {}
                                    emp_email_addr = emp_info.get('email', '')
                                    mgmt_shop_name = current_shop_config.get('name', 'Shop')
                                    mgmt_invoice_email = email_config.get('invoice_submission_email', default_from_email)
                                    html_content = email_client.create_breakdown_email(
                                        emp_name,
                                        emp_summary,
                                        emp_daily,
                                        emp_email_addr,
                                        shop_name=mgmt_shop_name, invoice_submission_email=mgmt_invoice_email
                                    )
                                    subject = f"{current_shop_config.get('name', 'Shop')} - Salary Breakdown for {emp_name}"
                                    for r in recipients:
                                        total_attempts += 1
                                        if email_client.send_email(
                                            to_email=r,
                                            subject=subject,
                                            html_content=html_content,
                                            from_email=mgmt_from_email_input,
                                        ):
                                            total_sent += 1
                                if total_sent > 0:
                                    st.success(f"Sent {total_sent} management emails (out of {total_attempts} attempts).")
                                else:
                                    st.error("Failed to send any management emails. Check email configuration and server logs.")
    
    with tab4:
        st.header("📤 Airtable Export Preview")
        
        if not st.session_state.calculations_done:
            st.info("👆 Go to the **Calculate** tab and run a calculation first to see what will be exported to Airtable")
        else:
            if 'airtable_records' not in st.session_state or not st.session_state.airtable_records:
                st.warning("⚠️ No Airtable records prepared. Please run a calculation first.")
            else:
                airtable_records = st.session_state.airtable_records
                
                st.subheader(f"📊 Preview: {len(airtable_records)} Records Ready")
                st.info("👀 **Review the data below before exporting to Airtable**")
                
                # Show preview table
                preview_df = pd.DataFrame(airtable_records)
                st.dataframe(preview_df, width='stretch', height=400)
                
                # Statistics
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total Records", len(airtable_records))
                with col2:
                    unique_employees = preview_df['Employee'].nunique()
                    st.metric("Employees", unique_employees)
                with col3:
                    date_range = f"{preview_df['Date'].min()} to {preview_df['Date'].max()}"
                    st.metric("Date Range", date_range)
                
                st.markdown("---")
                
                # Export section
                st.subheader("🚀 Export to Airtable")
                
                base_id = shop_config.get('airtable_base_id', '').strip()
                table_name = shop_config.get('airtable_table_name', '').strip()
                
                # Check if base_id is empty or just whitespace
                base_id_clean = base_id.strip() if base_id else ''
                table_name_clean = table_name.strip() if table_name else ''
                
                if not base_id_clean or not table_name_clean:
                    st.warning("⚠️ Please configure Base ID and Table name in `config/shops.yaml`")
                    st.info("💡 **Tip**: If you just updated the config file, you need to clear Streamlit's cache:")
                    col1, col2 = st.columns([1, 1])
                    with col1:
                        if st.button("🔄 Clear Cache & Reload", help="Clears Streamlit cache and reloads config"):
                            st.cache_data.clear()
                            st.rerun()
                    with col2:
                        st.info("Or use the menu: ☰ → Clear cache → Rerun")
                    st.code(f"""
Current values being read:
Base ID: {repr(base_id)} (type: {type(base_id).__name__})
Table Name: {repr(table_name)} (type: {type(table_name).__name__})
                    """)
                else:
                    st.success(f"✅ **Base ID:** `{base_id}`")
                    st.success(f"✅ **Table:** `{table_name}`")
                    
                    # Try to get API key from secrets, env var, or session state
                    api_key_from_secrets = None
                    try:
                        if hasattr(st, 'secrets') and 'airtable' in st.secrets and 'api_key' in st.secrets.airtable:
                            api_key_from_secrets = st.secrets.airtable.api_key
                    except:
                        pass
                    
                    api_key_from_env = os.getenv('AIRTABLE_API_KEY')
                    api_key_from_session = st.session_state.get('airtable_api_key')
                    
                    # Use the first available key
                    default_api_key = api_key_from_secrets or api_key_from_env or api_key_from_session
                    
                    if default_api_key:
                        st.success("✅ Airtable API key found (from secrets/env/session)")
                        airtable_api_key_input = default_api_key
                        # Optionally allow override
                        if st.checkbox("🔑 Use different API key", help="Override the saved API key", key="override_key_preview"):
                            airtable_api_key_input = st.text_input(
                                "Airtable API Key",
                                type="password",
                                help="Enter your Airtable API key",
                                key="airtable_key_preview_override"
                            ) or default_api_key
                    else:
                        airtable_api_key_input = st.text_input(
                            "Airtable API Key",
                            type="password",
                            help="Enter your Airtable API key (or set AIRTABLE_API_KEY env var or use Streamlit secrets)",
                            key="airtable_key_preview"
                        )
                        # Save to session state for this session
                        if airtable_api_key_input:
                            st.session_state.airtable_api_key = airtable_api_key_input
                    
                    if airtable_api_key_input:
                        st.markdown("---")
                        
                        # Export mode selection
                        export_mode = st.radio(
                            "📤 Export Mode",
                            ["Skip duplicates (append only new)", "Update existing records", "Upsert (update existing + create new)"],
                            index=0,
                            help="""
                            - **Skip duplicates**: Only append new records, skip existing ones (prevents duplicates)
                            - **Update existing**: Only update records that already exist, don't create new ones
                            - **Upsert**: Update existing records AND create new ones (recommended for re-runs after adjustments)
                            """,
                            key="export_mode_preview"
                        )
                        
                        skip_duplicates = export_mode == "Skip duplicates (append only new)"
                        update_existing = export_mode == "Update existing records"
                        upsert_mode = export_mode == "Upsert (update existing + create new)"
                        
                        # Show warning for update-only mode
                        if update_existing:
                            st.warning("⚠️ **Update Mode**: Only existing records will be updated. Records not found in Airtable will be skipped (not created).")
                        
                        # Preview duplicate check if not in update-only mode
                        if skip_duplicates or upsert_mode:
                            if st.button("🔍 Check for Existing Records", help="Check which records already exist in Airtable", key="check_duplicates_preview"):
                                try:
                                    with st.spinner("🔍 Checking for existing records..."):
                                        airtable = AirtableClient(api_key=airtable_api_key_input)
                                        check_result = airtable.check_existing_records(
                                            base_id_clean,
                                            table_name_clean,
                                            airtable_records
                                        )
                                        
                                        col1, col2 = st.columns(2)
                                        with col1:
                                            st.info(f"📊 **New records:** {check_result['new_count']}")
                                        with col2:
                                            st.warning(f"⚠️ **Existing records:** {check_result['existing_count']}")
                                        
                                        if check_result['existing_count'] > 0:
                                            st.info(f"💡 {check_result['existing_count']} records already exist and will be skipped. Only {check_result['new_count']} new records will be appended.")
                                        else:
                                            st.success("✅ No duplicates found! All records are new.")
                                except Exception as e:
                                    st.error(f"❌ Error checking for duplicates: {str(e)}")
                        
                        st.info("💡 Click the button below to export the previewed data to Airtable")
                        
                        if st.button("✅ Confirm & Export to Airtable", type="primary", use_container_width=False):
                            try:
                                with st.spinner("📤 Exporting to Airtable..."):
                                    airtable = AirtableClient(api_key=airtable_api_key_input)
                                    result = airtable.append_daily_breakdown(
                                        base_id_clean,
                                        table_name_clean,
                                        airtable_records,
                                        skip_duplicates=skip_duplicates,
                                        update_existing=update_existing,
                                        upsert_mode=upsert_mode
                                    )
                                    
                                    # Show results based on mode
                                    if update_existing:
                                        st.success(f"✅ Successfully updated {result.get('records_updated', 0)} records in Airtable!")
                                    elif upsert_mode:
                                        st.success(f"✅ Successfully updated {result.get('records_updated', 0)} records and created {result.get('records_created', 0)} new records!")
                                    elif result.get('skipped', 0) > 0:
                                        st.success(f"✅ Successfully exported {result['records_created']} new records to Airtable!")
                                        st.info(f"⏭️ Skipped {result['skipped']} existing records (duplicates)")
                                    else:
                                        st.success(f"✅ Successfully exported {result['records_created']} records to Airtable!")
                                    
                                    if result.get('message'):
                                        st.info(result['message'])
                                    
                                    st.balloons()
                                    
                                    # Show summary
                                    summary = {
                                        'success': True,
                                        'base_id': base_id_clean,
                                        'table_name': table_name_clean
                                    }
                                    if update_existing or upsert_mode:
                                        summary['records_updated'] = result.get('records_updated', 0)
                                    if upsert_mode or not update_existing:
                                        summary['records_created'] = result.get('records_created', 0)
                                    if result.get('skipped', 0) > 0:
                                        summary['records_skipped'] = result['skipped']
                                    st.json(summary)
                            except Exception as e:
                                st.error(f"❌ Error exporting to Airtable: {str(e)}")
                                import traceback
                                with st.expander("🔍 Error Details"):
                                    st.code(traceback.format_exc())
                    else:
                        st.info("🔑 Enter your Airtable API key above to enable export")
    
    with tab5:
        st.header("🎯 Sales Target Tracker")
        st.info(
            "Set an approved monthly target and update the **Total reached** each day. "
            "The app works out how far through the month you are and whether you are ahead "
            "or behind where you should be by today."
        )

        # Sub-tabs for Sales Target Tracker (add new tab names here to extend)
        sub_tab_names = ["📋 Daily Target Manager", "🏪 Shop Target Monthly"]
        sales_sub_tabs = st.tabs(sub_tab_names)

        with sales_sub_tabs[0]:
            # --- Daily Target Manager ---
            if "_daily_target_saved_toast" in st.session_state:
                st.toast(st.session_state.pop("_daily_target_saved_toast"), icon="✅")

            with st.container(border=True):
                st.subheader("📋 Daily target (manager)")
                st.caption("Set who is working each day and each staff member’s individual sales target for that day.")
                shop_key_tracker = st.session_state.get("selected_shop", list(load_config().get("shops", {}).keys())[0])
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

                staff_working = st.multiselect(
                    "Staff working this day",
                    options=employee_names,
                    default=existing_staff,
                    key="daily_rubric_staff",
                    help="Select everyone who is working on this date. Individual target fields appear below.",
                )

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
                                    min_value=0.0,
                                    step=50.0,
                                    value=float(existing_sales.get(name, 0)),
                                    format="%.2f",
                                    key=f"daily_sales_{date_str}_{name}",
                                    help=f"Total sales achieved by {name} on this day.",
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
                    total = sum(staff_daily_targets_submitted.values())
                    st.session_state["_daily_target_saved_toast"] = f"Daily target saved for {date_str} (£{total:,.2f})"
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
                        elif target > 0 or sales > 0:
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

            # --- Shop target tracker ---
            # Pre-fill from stored targets BEFORE the form (cannot modify widget-bound session state after widget is created)
            shop_key = st.session_state.get("selected_shop", list(load_config().get("shops", {}).keys())[0])
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
            # When shop or month changes, reload from storage so we don't show another shop's values
            last_loaded_shop_month = st.session_state.get("_target_shop_month")
            if last_loaded_shop_month != current_shop_month:
                st.session_state.target_approved = float(stored_target_pre or 0)
                st.session_state.target_total_reached = float(stored_total_reached_pre or 0)
                st.session_state["_target_shop_month"] = current_shop_month
            else:
                # Same shop/month - only pre-fill if empty
                if (
                    float(st.session_state.get("target_approved", 0.0)) == 0.0
                    and stored_target_pre
                ):
                    st.session_state.target_approved = float(stored_target_pre)
                if (
                    float(st.session_state.get("target_total_reached", 0.0)) == 0.0
                    and stored_total_reached_pre
                ):
                    st.session_state.target_total_reached = float(stored_total_reached_pre)

            with st.container(border=True):
                st.subheader("🏪 Shop target (monthly)")
                st.caption("Monthly sales target and progress for this shop.")
                # Use a form so that pressing Enter submits ONLY this section
                with st.form("sales_target_tracker_form", clear_on_submit=False):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.number_input(
                            "Approved target (£)",
                            min_value=0.0,
                            step=500.0,
                            format="%.2f",
                            key="target_approved",
                        )
                        st.number_input(
                            "Total reached so far (£)",
                            min_value=0.0,
                            step=500.0,
                            format="%.2f",
                            key="target_total_reached",
                        )
                    with col2:
                        st.date_input(
                            "Current date (used to calculate days passed)",
                            value=st.session_state.target_current_date,
                            key="target_current_date",
                        )

                    sales_target_form_submitted = st.form_submit_button("Update calculations")

                # Read current values from session state for calculations
                approved_target = float(st.session_state.get("target_approved", 0.0))
                total_reached = float(st.session_state.get("target_total_reached", 0.0))
                current_date = st.session_state.get("target_current_date", datetime.today().date())

                # Load or update saved targets for this shop/month
                shop_key = st.session_state.get("selected_shop", list(load_config().get("shops", {}).keys())[0])
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
                    save_shop_targets(targets_config)
                    if sales_target_form_submitted:
                        st.toast(f"Shop target updated (£{approved_target:,.2f} for {month_key})", icon="✅")

                # Core calculations
                total_days = calendar.monthrange(year, month)[1]
                days_passed = min(current_date.day, total_days)
                days_left = max(total_days - days_passed, 0)

                average_so_far = total_reached / days_passed if days_passed > 0 else 0.0
                direction_of = total_reached

                # Expected sales by today if you were exactly on track
                expected_so_far = 0.0
                if approved_target > 0 and total_days > 0 and days_passed > 0:
                    expected_so_far = approved_target * (days_passed / total_days)

                # Compare actual progress against expected progress
                if expected_so_far > 0:
                    direction_vs_target_pct = (direction_of / expected_so_far) * 100.0
                    diff_vs_target_pct = direction_vs_target_pct - 100.0
                else:
                    direction_vs_target_pct = 0.0
                    diff_vs_target_pct = 0.0

                left_to_reach = max(approved_target - total_reached, 0.0)
                avg_needed = left_to_reach / days_left if days_left > 0 else None
                daily_target = approved_target / total_days if total_days > 0 else 0.0

                st.markdown("---")

                # High-level metrics
                m1, m2, m3, m4 = st.columns(4)
                with m1:
                    st.metric("Target", format_currency(approved_target))
                with m2:
                    st.metric("Total days (month)", total_days)
                with m3:
                    st.metric("Days passed", days_passed)
                with m4:
                    st.metric("Days left", days_left)

                st.markdown("### Progress Summary")
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.metric("Total reached", format_currency(total_reached))
                    st.metric("Average so far", format_currency(average_so_far))
                with c2:
                    st.metric("Direction of", format_currency(direction_of))
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

    with tab6:
        st.header("📋 Data Management")
        st.info("Manage all Airtable config tables. Add, edit, or delete records. Changes are saved directly to Airtable.")

        tables_cfg = (load_config() or {}).get("airtable_config_tables", {})
        base_id, api_key, _ = _get_airtable_credentials(selected_shop)
        shop_display = shop_config.get("shop_display_name") or shop_config.get("name", selected_shop)
        shop_options = [s.get("shop_display_name") or s.get("name", k) for k, s in config["shops"].items()]
        payment_types = [
            "hourly_only", "commission_only", "manager",
            "progressive_tiered_commission", "hybrid_daily_max",
            "flat_rate_tiered_commission", "flat_rate_tiered_commission_with_transport",
            "tiered_commission", "molly_commission", "alex_hybrid", "net_commission_tiered"
        ]

        if not base_id or not api_key:
            st.error("❌ Airtable credentials not configured. Set Base ID in config/shops.yaml and API key in sidebar or secrets.")
        else:
            try:
                client = AirtableClient(api_key=api_key)
            except Exception as e:
                st.error(f"❌ Failed to connect to Airtable: {e}")
                client = None

            if client:
                dm_tab1, dm_tab2, dm_tab3, dm_tab4, dm_tab5, dm_tab6 = st.tabs([
                    "Employees", "Commission Tiers", "Name Mappings",
                    "Sales Bonus Thresholds", "Monthly Bonuses", "UK Wage Bracket",
                ])

                # --- Employees ---
                with dm_tab1:
                    _render_employees_tab(client, base_id, tables_cfg, shop_display, shop_options, payment_types, config)

                # --- Commission Tiers ---
                with dm_tab2:
                    _render_commission_tiers_tab(client, base_id, tables_cfg, shop_display, shop_options, config)

                # --- Name Mappings ---
                with dm_tab3:
                    _render_name_mappings_tab(client, base_id, tables_cfg, shop_display, shop_options, config)

                # --- Sales Bonus Thresholds ---
                with dm_tab4:
                    _render_sales_bonus_tab(client, base_id, tables_cfg, shop_display, shop_options, config)

                # --- Monthly Bonuses ---
                with dm_tab5:
                    _render_monthly_bonuses_tab(client, base_id, tables_cfg, shop_display, shop_options, config)

                # --- UK Wage Bracket ---
                with dm_tab6:
                    _render_wage_bracket_tab(client, base_id, tables_cfg)

if __name__ == "__main__":
    main()
