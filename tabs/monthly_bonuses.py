"""Monthly Bonuses tab content."""

import streamlit as st
import pandas as pd
from datetime import datetime


def render(selected_shop: str, shop_config: dict):
    """Render the Monthly Bonuses tab."""
    # Import here to avoid circular import (app is fully loaded when main() runs)
    from app import (
        load_employee_config,
        load_monthly_bonuses,
        save_monthly_bonuses,
        load_config,
        _get_airtable_credentials,
        format_currency,
    )
    from src.airtable_client import AirtableClient

    st.header("📝 Monthly Bonuses")
    with st.container(border=True):
        st.info("💡 **Step 1 of 3:** Add bonuses per employee for this month. **Save** each employee, then go to **Calculate** → **Run Calculation**.")

    # Load employee configuration from Airtable
    employees, bonuses, emp_config_full = load_employee_config(selected_shop)

    if not employees:
        st.error("⚠️ Failed to load from Airtable. Check Base ID, API key, and that Employees table has records for this shop.")
        st.stop()

    # Month/Year selector (default to current year and month)
    col1, col2 = st.columns(2)
    with col1:
        years = list(range(datetime.now().year - 2, datetime.now().year + 3))
        default_year_index = years.index(datetime.now().year)
        selected_year = st.selectbox("Year", years, index=default_year_index, key="bonus_year")
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

        # Check Airtable credentials
        base_id, api_key, _ = _get_airtable_credentials(selected_shop)
        if not base_id or not api_key:
            st.warning("⚠️ Airtable not configured. Add `[airtable] api_key = \"...\"` to `.streamlit/secrets.toml` (or set AIRTABLE_API_KEY) to save bonuses to Airtable.")

        # Load existing monthly bonuses
        month_bonuses_data = load_monthly_bonuses(selected_shop, selected_year, selected_month, shop_filter_override=shop_display_adj)

        # Show saved vs unsaved counts
        saved_employees = set(month_bonuses_data.keys())
        all_employees = set(employees.keys())
        unsaved = all_employees - saved_employees
        st.info(f"**Saved:** {len(saved_employees)} employee(s)  •  **Not yet saved:** {len(unsaved)} employee(s)")

        # Employee selector + form in a fragment for partial reruns
        @st.fragment
        def _employee_bonus_form():
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
                found_in_airtable = bool(current_bonuses)
                if not current_bonuses:
                    norm = selected_employee_bonus.strip().lower()
                    for k, v in month_bonuses_data.items():
                        if k and (k.strip().lower() == norm):
                            current_bonuses = v
                            found_in_airtable = True
                            break
                if not current_bonuses:
                    current_bonuses = base_bonuses.copy()

                st.markdown("---")
                saved_badge = " ✓ Saved" if (selected_employee_bonus in saved_employees or found_in_airtable) else " (not yet saved)"
                st.subheader(f"Bonuses for {selected_employee_bonus}{saved_badge}")

                ke = selected_employee_bonus.replace(" ", "_")
                with st.form(f"bonus_form_{ke}"):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown("### 💰 Bonuses")
                        daily_sales_bonus = st.number_input("Daily Sales Bonus", value=float(current_bonuses.get('dailySalesBonus', 0)), step=1.0, key=f"b_daily_sales_{ke}")
                        first_last_hour = st.number_input("First/Last Hour Bonus", value=float(current_bonuses.get('firstLastHourBonus', 0)), step=1.0, key=f"b_first_last_{ke}")
                        social_media = st.number_input("Social Media Bonus", value=float(current_bonuses.get('socialMediaBonus', 0)), step=1.0, key=f"b_social_media_{ke}")
                        management = st.number_input("Management Bonus", value=float(current_bonuses.get('managementBonus', 0)), step=1.0, key=f"b_management_{ke}")
                        management_consistency = st.number_input("Management Consistency Bonus", value=float(current_bonuses.get('managementConsistencyBonus', 0)), step=1.0, key=f"b_mgmt_cons_{ke}")
                        transport_fuel = st.number_input("Transport/Fuel", value=float(current_bonuses.get('transportFuel', 0)), step=1.0, key=f"b_transport_{ke}")
                        personal_sales = st.number_input("Personal Sales Bonus", value=float(current_bonuses.get('personalSalesBonus', 0)), step=1.0, key=f"b_personal_sales_{ke}")
                        extra_bonus = st.number_input("Extra Bonus", value=float(current_bonuses.get('extraBonus', 0)), step=1.0, key=f"b_extra_{ke}")
                        daily_allowance = st.number_input("Daily Allowance", value=float(current_bonuses.get('dailyAllowance', 0)), step=1.0, key=f"b_daily_allowance_{ke}")
                    with c2:
                        st.markdown("### 📊 Other")
                        manual_hours = st.number_input("Manual Hours", value=float(current_bonuses.get('manualHours', 0)), step=0.5, key=f"b_manual_hours_{ke}")
                        deductions = st.number_input("Deductions", value=float(current_bonuses.get('deductions', 0)), step=1.0, key=f"b_deductions_{ke}")
                        rent = st.number_input("Rent", value=float(current_bonuses.get('rent', 0)), step=1.0, key=f"b_rent_{ke}")
                        base_advance = employees.get(selected_employee_bonus, {}).get('advance', 0)
                        advance = st.number_input("Advance", value=float(current_bonuses.get('advance', base_advance)), step=1.0, key=f"b_advance_{ke}")

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
                        ok, err = save_monthly_bonuses(selected_shop, selected_year, selected_month, month_bonuses_data, shop_filter_override=shop_display_adj)
                        if ok:
                            st.success(f"✅ Saved bonuses for {selected_employee_bonus} - {month_name}")
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error(f"❌ Failed to save to Airtable: {err}")

        _employee_bonus_form()

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
