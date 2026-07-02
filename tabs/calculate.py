"""Calculate tab - Run salary calculations from report files."""

import streamlit as st
import pandas as pd
from datetime import datetime
from collections import Counter
import traceback


def render(report_file, selected_shop, shop_config, config, append_to_airtable, airtable_api_key):
    """Render the Calculate tab."""
    from app import (
        load_employee_config,
        load_config,
        load_monthly_bonuses,
        _get_airtable_credentials,
        _save_last_results,
        format_currency,
        logger,
    )
    from src.calculation_engine import CalculationEngine
    from src.data_processor import DataProcessor
    from src.airtable_client import AirtableClient, _normalize_date_for_key

    st.header(f"💰 Calculate Salaries - {shop_config['name']}")
    with st.container(border=True):
        st.info("💡 **Step 2 of 3:** Upload a report in the sidebar (Shop & Data Source), or pick a saved report. Then click **Run Calculation** below.")

    if report_file is not None:
        st.success(f"✅ File ready: **{report_file.name}** ({report_file.size:,} bytes)")
    else:
        st.warning("📤 No file selected — upload or pick a saved report in the sidebar")

    st.markdown("---")

    if st.button("🚀 Run Calculation", type="primary", width='content'):
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
                    with st.container(border=True):
                        st.markdown("### 📤 No report file selected")
                        st.info(
                            "**To run calculations:**\n\n"
                            "1. Open the **Shop & Data Source** section in the sidebar (left)\n"
                            "2. **Upload** a CSV or Excel report, **or**\n"
                            "3. Select a **Saved Report** or **Google Drive** file\n\n"
                            "Then click **Run Calculation** again."
                        )
                        st.caption("💡 Tip: Upload your salary report from the sidebar first.")
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
                                    except Exception:
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
                        if stats['mapped'] > 0 or stats['excluded'] > 0 or records:
                            with st.expander("📝 Name Mapping Summary", expanded=False):
                                st.write(f"**Total processed:** {stats['total_processed']}")
                                st.write(f"**Names mapped:** {stats['mapped']}")
                                unchanged = stats['total_processed'] - stats['mapped'] - stats['excluded']
                                if unchanged:
                                    st.write(f"**Unchanged (already config name or no alias):** {unchanged}")
                                st.write(f"**Names excluded:** {stats['excluded']}")
                                if stats['mapping_details']:
                                    st.write("**Mappings applied:**")
                                    for original, mapped in sorted(stats['mapping_details'].items()):
                                        st.write(f"  • `{original}` → `{mapped}`")
                                unique_in_file = sorted({r['Employee'] for r in records})
                                employees_lower_set = {e.lower() for e in employees.keys()}
                                not_in_config = [e for e in unique_in_file if e.lower() not in employees_lower_set]
                                if not_in_config:
                                    st.warning(
                                        f"**Report names not in employee config ({len(not_in_config)}):** "
                                        + ", ".join(f"`{n}`" for n in not_in_config)
                                    )

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

                shop_daily_sales_totals = CalculationEngine.build_shop_daily_sales_totals(records)

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
                        # Resolve via name mapping (report alias -> config name)
                        resolved_name = processor.map_employee_name(emp_name) or emp_name
                        if resolved_name != emp_name:
                            emp_name = resolved_name

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

                        summary = engine.calculate_monthly_summary(
                            daily_calcs,
                            shop_daily_sales_totals=shop_daily_sales_totals,
                        )

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
                # Persist so Results tab can show them after app restart (e.g. on Streamlit Cloud)
                _save_last_results(results, selected_shop, employees)
                st.session_state.calc_missing_employees = missing_employees
                st.session_state.calc_zero_calc_employees = zero_calc_employees

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
                        except Exception:
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
                        'PaymentType': summary.get('PaymentType', ''),
                    })
                    summary_row = airtable_records[-1]
                    if summary.get('PaymentType') == 'dave_package':
                        summary_row['ProratedBasePay'] = summary.get('ProratedBasePay', 0)
                        summary_row['ShopRangeSalesGross'] = summary.get('ShopRangeSalesGross', 0)
                        summary_row['ShopRangeCommission'] = summary.get('ShopRangeCommission', 0)
                        summary_row['PersonalCommission'] = summary.get('PersonalCommission', 0)
                        summary_row['ShopRangeFirstDate'] = summary.get('ShopRangeFirstDate', '') or ''
                        summary_row['ShopRangeLastDate'] = summary.get('ShopRangeLastDate', '') or ''
                    if summary.get('PaymentType') == 'isaac_package':
                        summary_row['IsaacTransportTotal'] = summary.get('IsaacTransportTotal', 0)
                        summary_row['SalesMilestoneBonus'] = summary.get('SalesMilestoneBonus', 0)

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
                with st.expander("🔍 Error Details"):
                    st.code(traceback.format_exc())

    # Airtable export section - shown when calculations done (persists across reruns so Confirm & Append works)
    if st.session_state.get("calculations_done", False) and append_to_airtable:
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
                        with st.expander("🔍 Error Details"):
                            st.code(traceback.format_exc())
        else:
            if not airtable_api_key:
                st.warning("⚠️ Please enter your Airtable API key in the sidebar")
            if not base_id or not table_name:
                st.warning("⚠️ Please configure Base ID and Table name in config/shops.yaml")
