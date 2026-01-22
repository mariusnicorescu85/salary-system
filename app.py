"""
Salary Calculation Dashboard
Main Streamlit application for running salary calculations
"""

import streamlit as st
import pandas as pd
import yaml
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import io
import logging
import sys
import os

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
from src.google_drive_client import GoogleDriveClient
from src.airtable_client import AirtableClient


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


@st.cache_data
def load_employee_config(shop_key: str):
    """Load employee configuration for a shop"""
    config = load_config()
    if not config:
        return None, None, None
    
    shop_config = config['shops'].get(shop_key)
    if not shop_config:
        return None, None, None
    
    employee_config_path = Path(shop_config['employee_config'])
    if not employee_config_path.exists():
        st.error(f"Employee config not found: {employee_config_path}")
        return None, None, None
    
    with open(employee_config_path, 'r') as f:
        emp_config = yaml.safe_load(f)
    
    return (
        emp_config.get('employees', {}), 
        emp_config.get('bonuses', {}),
        emp_config  # Return full config for name_mapping access
    )


def format_currency(value: float) -> str:
    """Format value as currency"""
    return f"£{value:,.2f}"


def load_monthly_adjustments(shop_key: str, year: int, month: int) -> Dict:
    """
    Load monthly adjustments (bonuses, deductions, advances) for a specific month
    Returns empty dict if file doesn't exist
    """
    adjustments_path = Path(f"config/monthly_adjustments_{shop_key}_{year}-{month:02d}.yaml")
    if adjustments_path.exists():
        with open(adjustments_path, 'r') as f:
            return yaml.safe_load(f) or {}
    return {}


def save_monthly_adjustments(shop_key: str, year: int, month: int, adjustments: Dict):
    """Save monthly adjustments to YAML file"""
    adjustments_path = Path(f"config/monthly_adjustments_{shop_key}_{year}-{month:02d}.yaml")
    adjustments_path.parent.mkdir(parents=True, exist_ok=True)
    with open(adjustments_path, 'w') as f:
        yaml.dump(adjustments, f, default_flow_style=False, sort_keys=False)


def main():
    st.title("💰 Salary Calculation Dashboard")
    st.markdown("Calculate employee salaries for each shop based on uploaded reports")
    
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
        
        st.markdown("---")
        st.subheader("📁 Data Source")
        
        # Default to file upload, make it more prominent
        data_source = st.radio(
            "Choose data source",
            ["📤 Upload File", "☁️ Google Drive"],
            index=0  # Default to file upload
        )
        
        if data_source == "☁️ Google Drive":
            st.info("Configure Google Drive folder in config/shops.yaml")
            file_id = st.text_input("Google Drive File ID", help="Enter the file ID from Google Drive URL")
        else:
            uploaded_file = st.file_uploader(
                "Upload Report File",
                type=['csv', 'xlsx'],
                help="Upload the salary report file from your computer"
            )
        
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
    
    # Main content area
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Calculate", "Results", "Airtable Preview", "Monthly Adjustments", "Configuration"])
    
    with tab1:
        st.header(f"💰 Calculate Salaries - {shop_config['name']}")
        
        # Show current data source status
        if data_source == "📤 Upload File":
            if uploaded_file is not None:
                st.success(f"✅ File ready: **{uploaded_file.name}** ({uploaded_file.size:,} bytes)")
            else:
                st.info("📤 Please upload a report file using the sidebar")
        else:
            if file_id:
                st.info(f"☁️ Google Drive file ID: `{file_id}`")
            else:
                st.info("☁️ Please enter a Google Drive file ID in the sidebar")
        
        st.markdown("---")
        
        if st.button("🚀 Run Calculation", type="primary", use_container_width=False):
            with st.spinner("Processing..."):
                try:
                    # Load employee configuration
                    employees, bonuses, emp_config_full = load_employee_config(selected_shop)
                    if not employees:
                        st.error("Failed to load employee configuration")
                        st.stop()
                    
                    # Load data
                    if data_source == "☁️ Google Drive":
                        if not file_id:
                            st.error("Please enter a Google Drive file ID")
                            st.stop()
                        
                        try:
                            drive_client = GoogleDriveClient()
                            if file_id.endswith('.csv'):
                                df = drive_client.download_csv_as_dataframe(file_id)
                            else:
                                df = drive_client.download_excel_as_dataframe(file_id)
                        except Exception as e:
                            st.error(f"Error downloading from Google Drive: {str(e)}")
                            st.stop()
                    else:  # File upload
                        if uploaded_file is None:
                            st.error("❌ Please upload a file from your computer using the sidebar")
                            st.stop()
                        
                        st.info(f"📄 Processing file: **{uploaded_file.name}**")
                        
                        try:
                            logger.info(f"Loading file: {uploaded_file.name}")
                            if uploaded_file.name.endswith('.csv'):
                                # Read CSV as text first to handle variable column structure
                                logger.info("Reading CSV as text to handle variable column structure...")
                                uploaded_file.seek(0)
                                
                                # Read entire file as text
                                try:
                                    content = uploaded_file.read()
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
                                    uploaded_file.seek(0)
                                    encodings = ['utf-8', 'latin-1', 'cp1252']
                                    df = None
                                    
                                    for encoding in encodings:
                                        try:
                                            uploaded_file.seek(0)
                                            try:
                                                df = pd.read_csv(
                                                    uploaded_file, 
                                                    encoding=encoding, 
                                                    header=None,
                                                    on_bad_lines='skip',
                                                    engine='python'
                                                )
                                                logger.info(f"Read CSV with {encoding} encoding (pandas 2.x): {df.shape}")
                                                break
                                            except TypeError:
                                                uploaded_file.seek(0)
                                                df = pd.read_csv(
                                                    uploaded_file, 
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
                                df = pd.read_excel(uploaded_file)
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
                    # Try to detect month from records
                    month_adjustments = {}
                    if records:
                        try:
                            first_date = datetime.strptime(records[0]['Date'], '%Y-%m-%d')
                            year = first_date.year
                            month = first_date.month
                            month_adjustments = load_monthly_adjustments(selected_shop, year, month)
                            
                            # Merge monthly adjustments with base bonuses
                            if month_adjustments:
                                # Deep merge: monthly adjustments override base bonuses
                                merged_bonuses = bonuses.copy()
                                for emp_name, emp_adjustments in month_adjustments.items():
                                    if emp_name in merged_bonuses:
                                        merged_bonuses[emp_name].update(emp_adjustments)
                                    else:
                                        merged_bonuses[emp_name] = emp_adjustments
                                bonuses = merged_bonuses
                                
                                # Also update advance in employee config if specified in monthly adjustments
                                for emp_name, emp_adjustments in month_adjustments.items():
                                    if 'advance' in emp_adjustments and emp_name in employees:
                                        employees[emp_name]['advance'] = emp_adjustments['advance']
                                
                                st.info(f"📅 Loaded monthly adjustments for {first_date.strftime('%B %Y')}")
                        except Exception as e:
                            logger.warning(f"Could not load monthly adjustments: {e}")
                    
                    # Initialize calculation engine
                    engine = CalculationEngine(employees, bonuses)
                    
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
                    
                    # Show Airtable preview if enabled
                    if append_to_airtable:
                        st.markdown("---")
                        st.subheader("📤 Quick Airtable Export")
                        st.info("💡 For detailed preview and export, go to the **'Airtable Preview'** tab")
                        
                        # Show configuration
                        base_id = shop_config.get('airtable_base_id')
                        table_name = shop_config.get('airtable_table_name')
                        
                        if base_id and table_name and airtable_api_key:
                            col1, col2 = st.columns(2)
                            with col1:
                                st.write(f"**Base ID:** {base_id}")
                            with col2:
                                st.write(f"**Table:** {table_name}")
                            
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
                                key="export_mode_calculate"
                            )
                            
                            skip_duplicates = export_mode == "Skip duplicates (append only new)"
                            update_existing = export_mode == "Update existing records"
                            upsert_mode = export_mode == "Upsert (update existing + create new)"
                            
                            # Confirmation button
                            if st.button("✅ Confirm & Append to Airtable", type="primary"):
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
                                        
                                        # Show results based on mode
                                        if update_existing:
                                            updated_count = result.get('records_updated', 0)
                                            not_found = result.get('not_found', [])
                                            st.success(f"✅ Successfully updated {updated_count} records in Airtable!")
                                            if not_found:
                                                st.warning(f"⚠️ {len(not_found)} records not found in Airtable (not created): {', '.join(not_found[:5])}{'...' if len(not_found) > 5 else ''}")
                                        elif upsert_mode:
                                            st.success(f"✅ Successfully updated {result.get('records_updated', 0)} records and created {result.get('records_created', 0)} new records!")
                                        elif result.get('skipped', 0) > 0:
                                            st.success(f"✅ Successfully appended {result['records_created']} new records to Airtable!")
                                            st.info(f"⏭️ Skipped {result['skipped']} existing records (duplicates)")
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
                
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
                    import traceback
                    with st.expander("🔍 Error Details"):
                        st.code(traceback.format_exc())
    
    with tab2:
        st.header("📊 Calculation Results")
        
        if not st.session_state.calculations_done:
            st.info("👆 Go to the 'Calculate' tab and run a calculation first to see results here")
        else:
            results = st.session_state.results
            
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
                    ['Rate per Hour', format_currency(summary.get('RatePerHour', 0))],
                    ['Hours Salary', format_currency(summary.get('HoursSalary', 0))],
                ]
                
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
                
    
    with tab3:
        st.header("📤 Airtable Export Preview")
        
        if not st.session_state.calculations_done:
            st.info("👆 Go to the 'Calculate' tab and run a calculation first to see what will be exported to Airtable")
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
    
    with tab4:
        st.header("📝 Monthly Adjustments")
        st.info("💡 Edit bonuses, deductions, rent, and advances for each employee for a specific month")
        
        # Load employee configuration
        employees, bonuses, emp_config_full = load_employee_config(selected_shop)
        
        if not employees:
            st.error("⚠️ Failed to load employee configuration. Please check the config files.")
            st.stop()
        
        # Month/Year selector
        col1, col2 = st.columns(2)
        with col1:
            selected_year = st.selectbox("Year", range(2024, 2027), index=1 if datetime.now().year == 2025 else 0)
        with col2:
            selected_month = st.selectbox("Month", range(1, 13), index=datetime.now().month - 1)
        
        month_name = datetime(selected_year, selected_month, 1).strftime('%B %Y')
        st.subheader(f"Adjustments for {month_name}")
        
        # Load existing adjustments
        adjustments = load_monthly_adjustments(selected_shop, selected_year, selected_month)
        
        # Get list of employees
        if not employees:
            st.warning("⚠️ Please load employee configuration first (go to Calculate tab)")
        else:
            # Employee selector
            selected_employee_adj = st.selectbox(
                "Select Employee",
                list(employees.keys()),
                key="adj_employee_selector"
            )
            
            if selected_employee_adj:
                # Get base bonuses for this employee
                base_bonuses = bonuses.get(selected_employee_adj, {})
                current_adjustments = adjustments.get(selected_employee_adj, {})
                
                # Initialize with base values if no adjustments exist
                if not current_adjustments:
                    current_adjustments = base_bonuses.copy()
                
                st.markdown("---")
                st.subheader(f"Adjustments for {selected_employee_adj}")
                
                # Create form for editing
                with st.form(f"adjustments_form_{selected_employee_adj}"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.markdown("### 💰 Bonuses")
                        daily_sales_bonus = st.number_input(
                            "Daily Sales Bonus",
                            value=float(current_adjustments.get('dailySalesBonus', 0)),
                            step=1.0,
                            key="daily_sales"
                        )
                        first_last_hour = st.number_input(
                            "First/Last Hour Bonus",
                            value=float(current_adjustments.get('firstLastHourBonus', 0)),
                            step=1.0,
                            key="first_last"
                        )
                        social_media = st.number_input(
                            "Social Media Bonus",
                            value=float(current_adjustments.get('socialMediaBonus', 0)),
                            step=1.0,
                            key="social_media"
                        )
                        management = st.number_input(
                            "Management Bonus",
                            value=float(current_adjustments.get('managementBonus', 0)),
                            step=1.0,
                            key="management"
                        )
                        management_consistency = st.number_input(
                            "Management Consistency Bonus",
                            value=float(current_adjustments.get('managementConsistencyBonus', 0)),
                            step=1.0,
                            key="management_consistency"
                        )
                        transport_fuel = st.number_input(
                            "Transport/Fuel",
                            value=float(current_adjustments.get('transportFuel', 0)),
                            step=1.0,
                            key="transport"
                        )
                        personal_sales = st.number_input(
                            "Personal Sales Bonus",
                            value=float(current_adjustments.get('personalSalesBonus', 0)),
                            step=1.0,
                            key="personal_sales"
                        )
                        extra_bonus = st.number_input(
                            "Extra Bonus",
                            value=float(current_adjustments.get('extraBonus', 0)),
                            step=1.0,
                            key="extra"
                        )
                        daily_allowance = st.number_input(
                            "Daily Allowance",
                            value=float(current_adjustments.get('dailyAllowance', 0)),
                            step=1.0,
                            key="daily_allowance"
                        )
                    
                    with col2:
                        st.markdown("### 📊 Other Adjustments")
                        manual_hours = st.number_input(
                            "Manual Hours",
                            value=float(current_adjustments.get('manualHours', 0)),
                            step=0.5,
                            key="manual_hours"
                        )
                        deductions = st.number_input(
                            "Deductions",
                            value=float(current_adjustments.get('deductions', 0)),
                            step=1.0,
                            key="deductions"
                        )
                        rent = st.number_input(
                            "Rent",
                            value=float(current_adjustments.get('rent', 0)),
                            step=1.0,
                            key="rent"
                        )
                        # Get advance from adjustments or base config
                        base_advance = employees.get(selected_employee_adj, {}).get('advance', 0)
                        current_advance = current_adjustments.get('advance', base_advance)
                        
                        advance = st.number_input(
                            "Advance",
                            value=float(current_advance),
                            step=1.0,
                            key="advance"
                        )
                        
                        # Show employee's advance from base config if different
                        if base_advance != advance and base_advance > 0:
                            st.info(f"💡 Base config has advance: £{base_advance:.2f}")
                    
                    # Calculate total bonus preview
                    total_bonus = (
                        daily_sales_bonus + first_last_hour + social_media + management +
                        management_consistency + transport_fuel + personal_sales +
                        extra_bonus + daily_allowance
                    )
                    
                    st.markdown("---")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Total Bonus", format_currency(total_bonus))
                    with col2:
                        st.metric("Total Deductions", format_currency(deductions + rent))
                    with col3:
                        st.metric("Advance", format_currency(advance))
                    
                    submitted = st.form_submit_button("💾 Save Adjustments", type="primary")
                    
                    if submitted:
                        # Prepare adjustments dict
                        if selected_employee_adj not in adjustments:
                            adjustments[selected_employee_adj] = {}
                        
                        adjustments[selected_employee_adj] = {
                            'dailySalesBonus': daily_sales_bonus,
                            'firstLastHourBonus': first_last_hour,
                            'socialMediaBonus': social_media,
                            'managementBonus': management,
                            'managementConsistencyBonus': management_consistency,
                            'transportFuel': transport_fuel,
                            'personalSalesBonus': personal_sales,
                            'extraBonus': extra_bonus,
                            'dailyAllowance': daily_allowance,
                            'manualHours': manual_hours,
                            'deductions': deductions,
                            'rent': rent,
                            'advance': advance
                        }
                        
                        # Save to file
                        save_monthly_adjustments(selected_shop, selected_year, selected_month, adjustments)
                        st.success(f"✅ Adjustments saved for {selected_employee_adj} - {month_name}")
                        st.cache_data.clear()  # Clear cache to reload on next calculation
                        st.rerun()
            
            # Show all adjustments for the month
            if adjustments:
                st.markdown("---")
                st.subheader(f"All Adjustments for {month_name}")
                
                # Create summary table
                adj_data = []
                for emp_name, emp_adj in adjustments.items():
                    total_bonus = sum([
                        emp_adj.get('dailySalesBonus', 0),
                        emp_adj.get('firstLastHourBonus', 0),
                        emp_adj.get('socialMediaBonus', 0),
                        emp_adj.get('managementBonus', 0),
                        emp_adj.get('managementConsistencyBonus', 0),
                        emp_adj.get('transportFuel', 0),
                        emp_adj.get('personalSalesBonus', 0),
                        emp_adj.get('extraBonus', 0),
                        emp_adj.get('dailyAllowance', 0)
                    ])
                    adj_data.append({
                        'Employee': emp_name,
                        'Total Bonus': format_currency(total_bonus),
                        'Deductions': format_currency(emp_adj.get('deductions', 0)),
                        'Rent': format_currency(emp_adj.get('rent', 0)),
                        'Advance': format_currency(emp_adj.get('advance', 0)),
                        'Manual Hours': emp_adj.get('manualHours', 0)
                    })
                
                if adj_data:
                    adj_df = pd.DataFrame(adj_data)
                    st.dataframe(adj_df, width='stretch', hide_index=True)
                    
                    # Delete button
                    if st.button("🗑️ Clear All Adjustments for This Month", type="secondary"):
                        adjustments_path = Path(f"config/monthly_adjustments_{selected_shop}_{selected_year}-{selected_month:02d}.yaml")
                        if adjustments_path.exists():
                            adjustments_path.unlink()
                            st.success("✅ All adjustments cleared")
                            st.cache_data.clear()
                            st.rerun()
    
    with tab5:
        st.header("Configuration")
        st.info("Edit configuration files in the `config/` directory")
        
        st.subheader("Shop Configuration")
        st.code(Path('config/shops.yaml').read_text() if Path('config/shops.yaml').exists() else "Not found")
        
        st.subheader(f"Employee Configuration - {selected_shop}")
        emp_config_path = Path(shop_config['employee_config'])
        if emp_config_path.exists():
            st.code(emp_config_path.read_text())
        else:
            st.error(f"Configuration file not found: {emp_config_path}")


if __name__ == "__main__":
    main()
