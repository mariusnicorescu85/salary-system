"""Results tab - View calculation results and send emails."""

import streamlit as st
import pandas as pd


def render(config):
    """Render the Results tab."""
    from app import (
        _load_last_results_from_file,
        _load_results_from_airtable,
        _get_airtable_credentials,
        get_email_client_for_shop,
    )
    from src.airtable_client import AirtableClient
    from utils.helpers import format_currency

    st.header("📊 Calculation Results")
    shop_keys = list(config.get("shops", {}).keys())
    selected_shop = st.session_state.get("selected_shop") or (shop_keys[0] if shop_keys else None)
    if not selected_shop:
        st.warning("No shop selected. Configure shops in config/shops.yaml.")
        return

    # Show results for the currently selected shop (like monthly target)
    if (st.session_state.calculations_done and st.session_state.results and
            st.session_state.get("results_shop_key") == selected_shop):
        results = st.session_state.results
        results_source = "session"
    else:
        cached = _load_last_results_from_file(selected_shop)
        if cached:
            results = cached["results"]
            st.session_state.results = results
            st.session_state.results_shop_key = cached.get("results_shop_key", "")
            st.session_state.employees_config = cached.get("employees_config", {})
            results_source = "file"
        else:
            airtable_data = _load_results_from_airtable(selected_shop)
            if airtable_data:
                results = airtable_data["results"]
                st.session_state.results = results
                st.session_state.results_shop_key = airtable_data.get("results_shop_key", selected_shop)
                st.session_state.employees_config = airtable_data.get("employees_config", {})
                results_source = "airtable"
            else:
                results = {}
                results_source = None

    if not results:
        with st.container(border=True):
            st.markdown("### 📊 No results yet")
            st.info(
                "**Next step:** Go to the **Calculate** tab and run a calculation for this shop.\n\n"
                "1. Upload or select a report in the sidebar\n"
                "2. Click **Run Calculation**\n"
                "3. Results will appear here"
            )
        # Help diagnose when Airtable has data but Results tab is empty
        with st.expander("🔍 Troubleshooting: I have data in Airtable but it's not showing"):
            shop_config = config.get("shops", {}).get(selected_shop, {})
            base_id = shop_config.get("airtable_base_id", "")
            table_name = shop_config.get("airtable_table_name", "")
            _, api_key, _ = _get_airtable_credentials(selected_shop)
            st.write(f"**Shop:** {selected_shop} | **Base ID:** {base_id or '(not set)'} | **Table:** {table_name or '(not set)'}")
            st.write(f"**Airtable API key:** {'✅ Found' if api_key else '❌ Missing (add to Streamlit Cloud Settings → Secrets)'}")
            if api_key and base_id and table_name:
                try:
                    client = AirtableClient(api_key=api_key)
                    records = client.get_daily_breakdown_records(base_id, table_name)
                    st.write(f"**Records in Airtable:** {len(records)}")
                    if records:
                        sample = records[0]
                        rt = sample.get("RecordType") or sample.get("Record Type") or sample.get("recordtype")
                        st.write(f"**Sample field names:** {list(sample.keys())[:10]}...")
                        st.write(f"**RecordType in first record:** {repr(rt)}")
                        if not rt:
                            st.warning("Records lack a RecordType/Record Type field. Ensure your Airtable table has Daily and Monthly Summary rows with that field set.")
                    else:
                        st.warning("Table is empty. Run a calculation and click 'Confirm & Append to Airtable' to populate it.")
                except Exception as e:
                    st.error(f"Airtable fetch error: {e}")
    else:
        if results_source == "file":
            st.caption("📂 Showing last saved results (from previous run)")
        elif results_source == "airtable":
            st.caption("📂 Loaded from Airtable (last exported data for this shop)")
        employees_config = st.session_state.get('employees_config', {})
        # Resolve the shop that these results belong to (not just the current sidebar selection)
        results_shop_key = st.session_state.get('results_shop_key')
        if not results_shop_key:
            # Fallback to current sidebar selection or first configured shop
            shop_keys = list(config.get('shops', {}).keys())
            results_shop_key = st.session_state.get('selected_shop') or (shop_keys[0] if shop_keys else None)
        current_shop_config = config['shops'].get(results_shop_key, {})
        email_config = current_shop_config.get('email', {})
        default_from_email = email_config.get('from_email', '')
        default_management_recipients = email_config.get('management_recipients', []) or []

        # Step 3 hint (only when we have results)
        with st.container(border=True):
            st.info("💡 **Step 3 of 3:** Review results below. Export to Airtable from the **Calculate** or **Airtable Preview** tab when ready.")

        # Metric cards at top for quick insights
        total_payroll = sum(d["summary"].get("FinalPayment", 0) for d in results.values())
        total_sales = sum(d["summary"].get("Sales", 0) for d in results.values())
        wage_pct = (total_payroll / total_sales * 100) if total_sales > 0 else 0
        with st.container(border=True):
            m1, m2, m3, m4 = st.columns(4)
            with m1:
                st.metric("Total Payroll", format_currency(total_payroll))
            with m2:
                st.metric("Employees", len(results))
            with m3:
                st.metric("Total Sales", format_currency(total_sales))
            with m4:
                st.metric("Wage % of Sales", f"{wage_pct:.1f}%")
        st.divider()

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
        if results_source == "airtable":
            st.caption(
                "Figures are read from **Airtable** (latest **Monthly Summary** rows there). "
                "If pay looks wrong after changing rules (e.g. **dave_package**), run **Calculate** again and **export to Airtable** so summaries update."
            )
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
            pt_norm = (summary.get('PaymentType') or '').lower().replace(' ', '_')
            hs0 = float(summary.get('HoursSalary') or 0) == 0
            tc0 = float(summary.get('TotalCommission') or 0) == 0
            sales_pos = float(summary.get('Sales') or 0) > 0
            days_pos = float(summary.get('WorkedDays') or 0) > 0
            if sales_pos and days_pos and hs0 and tc0 and (
                pt_norm == 'dave_package'
                or (results_source == 'airtable' and float(summary.get('FinalPayment') or 0) < 0)
            ):
                st.warning(
                    "**This summary looks incomplete:** prorated base and total commission are **£0** but there are worked days and sales. "
                    "That usually means **Airtable** still has an **old Monthly Summary** (e.g. before **dave_package** or a failed export). "
                    "Open **Calculate**, run for this shop with Dave on **dave_package**, then **export to Airtable** again—or rely on the saved results file from that run."
                )
            breakdown_cols = ['Field', 'Value']
            hours_salary_label = (
                'Prorated base (monthly ÷ reference days × days worked)'
                if pt_norm == 'dave_package'
                else 'Hours Salary'
            )
            breakdown_data = [
                ['Worked Days', summary.get('WorkedDays', 0)],
                ['Worked Hours', f"{summary.get('WorkedHours', 0):.2f}"],
                ['Sales', format_currency(summary.get('Sales', 0))],
                ['Additional Sales', format_currency(summary.get('AddlSales', 0))],
                ['Adjusted Sales', format_currency(summary.get('AdjustedSales', 0))],
                [hours_salary_label, format_currency(summary.get('HoursSalary', 0))],
            ]
            if pt_norm == 'dave_package':
                pb = summary.get('ProratedBasePay')
                if pb is not None and pb != '':
                    try:
                        if abs(float(pb) - float(summary.get('HoursSalary') or 0)) > 0.005:
                            breakdown_data.append(['Prorated base (detail)', format_currency(float(pb))])
                    except (TypeError, ValueError):
                        pass
                if summary.get('PersonalCommission') not in (None, '', 0):
                    try:
                        breakdown_data.append(['Personal commission (10%)', format_currency(float(summary.get('PersonalCommission')))])
                    except (TypeError, ValueError):
                        pass
                if summary.get('ShopRangeSalesGross') not in (None, '', 0):
                    try:
                        breakdown_data.append(['Shop sales (first–last clock-in dates)', format_currency(float(summary.get('ShopRangeSalesGross')))])
                    except (TypeError, ValueError):
                        pass
                if summary.get('ShopRangeCommission') not in (None, '', 0):
                    try:
                        breakdown_data.append(['Shop commission (1% of range)', format_currency(float(summary.get('ShopRangeCommission')))])
                    except (TypeError, ValueError):
                        pass
                d0, d1 = summary.get('ShopRangeFirstDate') or '', summary.get('ShopRangeLastDate') or ''
                if d0 and d1:
                    breakdown_data.append(['Shop range (dates)', f"{d0} → {d1}"])
            wage_breakdown = summary.get('WageBracketBreakdown', [])
            if not wage_breakdown and pt_norm != 'dave_package':
                breakdown_data.insert(-1, ['Rate per Hour', format_currency(summary.get('RatePerHour', 0))])
            if wage_breakdown:
                for i, period in enumerate(wage_breakdown, 1):
                    date_from = period.get('date_from', '')
                    date_to = period.get('date_to', '')
                    label = f"{date_from} to {date_to}" if date_from != date_to else date_from
                    breakdown_data.append([f"  Period {i} ({label})", f"{period.get('hours', 0):.2f} hrs × £{period.get('rate', 0):.2f} = {format_currency(period.get('pay', 0))}"])

            total_comm = float(summary.get('TotalCommission') or 0)
            if total_comm > 0 or pt_norm in (
                'dave_package', 'commission_only', 'tiered_commission', 'hybrid_daily_max',
                'molly_commission', 'progressive_tiered_commission', 'flat_rate_tiered_commission',
                'flat_rate_tiered_commission_with_transport', 'alex_hybrid', 'net_commission_tiered',
            ):
                breakdown_data.append(['Total Commission', format_currency(total_comm)])

            bonus_breakdown = summary.get('BonusBreakdown', {})
            transport_val = bonus_breakdown.get('TransportFuel', 0) or 0
            if transport_val > 0:
                breakdown_data.append(['Transport', format_currency(transport_val)])

            if summary.get('TotalBonus', 0) > 0:
                breakdown_data.append(['Total Bonus', format_currency(summary.get('TotalBonus', 0))])

            if summary.get('ManualHours', 0) > 0:
                breakdown_data.append(['Manual Hours', f"{summary.get('ManualHours', 0):.2f}"])
                breakdown_data.append(['Manual Hours Pay', format_currency(summary.get('ManualHoursPay', 0))])

            ded = float(summary.get('Deductions') or 0)
            if ded != 0:
                breakdown_data.append(['Deductions', format_currency(-ded)])

            if summary.get('Rent', 0) > 0:
                pt = (summary.get('PaymentType') or '').lower()
                # For alex_hybrid, rent is added to pay (chair rent); for others it's a deduction
                rent_display = format_currency(summary.get('Rent', 0)) if pt == 'alex_hybrid' else format_currency(-summary.get('Rent', 0))
                breakdown_data.append(['Rent', rent_display])

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
            num_cols_config = {c: st.column_config.NumberColumn(c, format="%.2f") for c in ('Hours', 'Sales', 'AddlSales', 'HrlyRate', 'Base', 'Commission') if c in daily_df.columns}
            st.dataframe(daily_df, width='stretch', column_config=num_cols_config)

            # Download button
            csv = daily_df.to_csv(index=False, float_format="%.2f")
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
                            emp_cfg = employees_config.get(emp_name, {}) if isinstance(employees_config, dict) else {}
                            html_content = email_client.create_breakdown_email(
                                emp_name, emp_data['summary'], emp_data['daily'], emp_email,
                                shop_name=shop_name, invoice_submission_email=invoice_email,
                                employment=emp_cfg.get("employment", ""),
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
                            shop_name=shop_name, invoice_submission_email=invoice_email,
                            employment=employee_info.get("employment", ""),
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
            # First: sender address (key includes shop so values update when switching shops)
            mgmt_from_email_input = st.text_input(
                "From email (sender)",
                value=default_from_email,
                help="Sender address for management emails (usually the shop email).",
                key=f"management_from_email_{results_shop_key}",
            )
            # Second: management recipient list (key includes shop so values update when switching shops)
            management_recipients_str = ", ".join(default_management_recipients)
            management_recipients_input = st.text_input(
                "Management recipient emails (comma-separated)",
                value=management_recipients_str,
                help="Management will receive the breakdowns for review and approval.",
                key=f"management_recipients_{results_shop_key}",
            )

            col_mgmt1, col_mgmt2 = st.columns(2)
            with col_mgmt1:
                if st.button(
                    "Send consolidated breakdown (one email for approval)",
                    key="send_management_consolidated",
                    help="One email to management with each employee's full staff-style breakdown (same as they will receive).",
                ):
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
                            mgmt_shop_name = current_shop_config.get('name', 'Shop')
                            mgmt_invoice_email = email_config.get('invoice_submission_email', default_from_email)
                            try:
                                html_content = email_client.create_management_approval_email(
                                    shop_name=mgmt_shop_name,
                                    results=results,
                                    employees_config=employees_config,
                                    invoice_submission_email=mgmt_invoice_email,
                                )
                            except (TypeError, ValueError) as build_err:
                                st.error(
                                    "Could not build the management approval email. "
                                    "Re-run **Calculate** and try again, or check Streamlit logs for the employee name in the error."
                                )
                                st.exception(build_err)
                                html_content = None
                            if html_content:
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
                if st.button(
                    "Send each breakdown separately (one email per employee)",
                    key="send_management_emails",
                    help="Same staff-style breakdown as above, but one email per employee per management recipient.",
                ):
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
                                    shop_name=mgmt_shop_name, invoice_submission_email=mgmt_invoice_email,
                                    employment=emp_info.get("employment", ""),
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
