"""Shop Analytics tab - View and save analytics from report calculations."""

import streamlit as st
import pandas as pd
from datetime import datetime


def render(selected_shop, shop_config, config):
    """Render the Shop Analytics tab."""
    from app import load_config, _get_airtable_credentials, format_currency
    from src.airtable_client import AirtableClient

    st.header("📊 Shop Analytics")
    st.info(
        "View analytics from report calculations (Employee, Period, Payment Type, wages, sales, etc.) "
        "and save to Airtable to track progress over time."
    )
    with st.expander("ℹ️ Airtable setup", expanded=False):
        st.markdown(
            "Create a **Shop Analytics** table in your Airtable base with columns: "
            "Employee, Shop, Period, PaymentType, WorkedDays, WorkedHours, HourlyRate, SalesPercentage, "
            "BasePayment, TotalSales, AddlSales, AdjustedSales, SalesCommission, BonusPayment, FinalTotal, "
            "AvgSalesPerDay, AvgSalesPerHour, Description, ConfigVersion, DataIssues, "
            "SalaryToSalesPct, SalesShareOfShop, SalaryShareOfShop. "
            "Table name is set in config (shop_analytics). A SHOP_METRICS summary row is included."
        )

    # CSS for analytics cards (matches Aleeza-style design)
    st.markdown("""
    <style>
    .emp-card {
        background: #fff;
        border-radius: 12px;
        overflow: hidden;
        box-shadow: 0 2px 12px rgba(0,0,0,0.08);
        margin-bottom: 1.25rem;
    }
    .emp-card-header {
        background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
        color: white;
        padding: 0.75rem 1.25rem;
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 0.5rem;
    }
    .emp-card-header-left { font-weight: 600; font-size: 1.1rem; }
    .emp-card-header-right { font-size: 0.9rem; opacity: 0.95; }
    .emp-card-body { padding: 1rem 1.25rem; }
    .emp-card-section { margin-bottom: 1rem; }
    .emp-card-section:last-child { margin-bottom: 0; }
    .emp-card-section-title { font-weight: 700; font-size: 0.85rem; color: #1e293b; margin-bottom: 0.5rem; }
    .emp-card-table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
    .emp-card-table td { padding: 0.35rem 0.5rem; vertical-align: top; }
    .emp-card-table .col-metric { font-weight: 500; color: #475569; width: 28%; }
    .emp-card-table .col-value { font-weight: 600; color: #1e293b; width: 22%; }
    .emp-card-table .col-details { font-size: 0.8rem; color: #64748b; }
    .emp-card-table tr.row-highlight-green { background: #dcfce7 !important; }
    .emp-card-table tr.row-highlight-orange { background: #fff7ed !important; }
    .emp-card-table tr.row-highlight-yellow { background: #fefce8 !important; }
    </style>
    """, unsafe_allow_html=True)

    def _salary_pct_color(pct: float) -> str:
        """Green when under 25%, gradient through yellow to red the further from 25%."""
        target = 25.0
        if pct <= target:
            t = pct / target if target > 0 else 0
            r = int(22 + (234 - 22) * t)
            g = int(163 + (179 - 163) * t)
            b = int(74 + (8 - 74) * t)
            return f"rgb({r},{g},{b})"
        else:
            excess = min((pct - target) / 25.0, 1.0)
            r = int(234 + (220 - 234) * excess)
            g = int(179 + (38 - 179) * excess)
            b = int(8 + (38 - 8) * excess)
            return f"rgb({r},{g},{b})"

    def _efficiency_rating(pct: float) -> tuple:
        """Return (label, row_class) for efficiency rating. Lower % = better."""
        if pct < 23:
            return ("✓ Good", "row-highlight-green")
        if pct <= 27:
            return ("✓ On target", "row-highlight-yellow")
        return ("▲ Needs Improvement", "row-highlight-orange")

    def _cost_efficiency_row_class(pct: float) -> str:
        """Row background for Cost Efficiency based on value."""
        if pct < 23:
            return "row-highlight-green"
        if pct <= 27:
            return "row-highlight-yellow"
        return "row-highlight-orange"

    analytics_sub1, analytics_sub2 = st.tabs(["Current Report", "Historical (from Airtable)"])

    with analytics_sub1:
        if not st.session_state.calculations_done:
            st.info("👆 Run a calculation in the **Calculate** tab first. The analytics table will be built from those results.")
        else:
            results = st.session_state.results
            results_shop_key = st.session_state.get("results_shop_key") or selected_shop
            shop_config_analytics = config["shops"].get(results_shop_key, shop_config)
            shop_display_analytics = shop_config_analytics.get("shop_display_name") or shop_config_analytics.get("name", results_shop_key)

            # Compute shop totals for share metrics
            shop_total_sales = sum(d["summary"].get("Sales", 0) for d in results.values())
            shop_total_salary = sum(d["summary"].get("FinalPayment", 0) for d in results.values())
            employees_config_analytics = st.session_state.get("employees_config", {})
            missing_emp = st.session_state.get("calc_missing_employees", [])
            zero_calc_emp = st.session_state.get("calc_zero_calc_employees", [])

            def _sales_percentage(emp_name: str, payment_type: str) -> str:
                """Human-readable sales % from payment config (matches n8n workflow)."""
                cfg = employees_config_analytics.get(emp_name, {})
                pt_norm = (payment_type or "").lower().replace(" ", "_")
                if pt_norm == "sales_only":
                    return "0% (external pay)"
                if payment_type == "commission_only" or payment_type == "CommissionOnly":
                    rate = cfg.get("commission_rate") or 0
                    return f"{rate * 100:.1f}%" if rate > 0 else "N/A"
                if payment_type in ("progressive_tiered_commission", "ProgressiveTieredCommission"):
                    return "Progressive 20-25%"
                if payment_type in ("flat_rate_tiered_commission", "FlatRateTieredCommission"):
                    return "Flat 32-33%"
                if payment_type in ("flat_rate_tiered_commission_with_transport", "FlatRateTieredWithTransport"):
                    return "30-35% + Transport"
                if payment_type in ("net_commission_tiered", "NetCommissionTiered"):
                    return "NET 30-33%"
                if payment_type in ("alex_hybrid", "AlexOldStructure", "AlexNewStructure"):
                    return "25-27% + Rent"
                if payment_type in ("hybrid_daily_max", "HybridDailyMax"):
                    return "Progressive/Hourly Max"
                if payment_type in ("tiered_commission", "MonthlyMaxLater"):
                    return "Tiered/Hourly Max"
                if payment_type in ("molly_commission", "MollyCommission"):
                    return "30-35% NET"
                if payment_type in ("hourly_only", "manager", "HourlyOnly"):
                    return "Hourly"
                return payment_type or "N/A"

            def _pay_description(emp_name: str, payment_type: str) -> str:
                """Human-readable pay structure description."""
                cfg = employees_config_analytics.get(emp_name, {})
                if cfg.get("description"):
                    return str(cfg["description"])
                return _sales_percentage(emp_name, payment_type)

            # Build analytics rows
            analytics_rows = []
            for emp_name, emp_data in results.items():
                summary = emp_data["summary"]
                emp_sales = summary.get("Sales", 0) or 0
                emp_final = summary.get("FinalPayment", 0) or 0
                worked_hours = summary.get("WorkedHours", 0) or 0

                # Period from first daily record
                employee_daily = [c for c in st.session_state.get("all_daily_calculations", []) if c.get("Employee") == emp_name]
                month_period = ""
                if employee_daily:
                    try:
                        first_date = datetime.strptime(employee_daily[0]["Date"], "%Y-%m-%d")
                        month_period = first_date.strftime("%Y-%m")
                    except Exception:
                        pass

                salary_to_sales_pct = (emp_final / emp_sales * 100) if emp_sales > 0 else 0
                sales_share = (emp_sales / shop_total_sales * 100) if shop_total_sales > 0 else 0
                salary_share = (emp_final / shop_total_salary * 100) if shop_total_salary > 0 else 0
                avg_sales_per_hour = (emp_sales / worked_hours) if worked_hours > 0 else 0

                payment_type = summary.get("PaymentType", "")
                data_issues = []
                if emp_name in missing_emp:
                    data_issues.append("Missing from config")
                if emp_name in zero_calc_emp:
                    data_issues.append("Zero calculation")
                data_issues_str = "; ".join(data_issues) if data_issues else "None"

                analytics_rows.append({
                    "Employee": emp_name,
                    "Shop": shop_display_analytics,
                    "Period": month_period,
                    "PaymentType": payment_type,
                    "WorkedDays": summary.get("WorkedDays", 0),
                    "WorkedHours": round(worked_hours, 2),
                    "HourlyRate": round(summary.get("RatePerHour", 0), 2),
                    "SalesPercentage": _sales_percentage(emp_name, payment_type),
                    "BasePayment": round(summary.get("HoursSalary", 0), 2),
                    "TotalSales": round(emp_sales, 2),
                    "AddlSales": round(summary.get("AddlSales", 0), 2),
                    "AdjustedSales": round(summary.get("AdjustedSales", 0), 2),
                    "SalesCommission": round(summary.get("TotalCommission", 0), 2),
                    "BonusPayment": round(summary.get("TotalBonus", 0), 2),
                    "FinalTotal": round(emp_final, 2),
                    "AvgSalesPerDay": round(summary.get("AvgSalePerDay", 0), 2),
                    "AvgSalesPerHour": round(avg_sales_per_hour, 2),
                    "Description": _pay_description(emp_name, payment_type),
                    "ConfigVersion": f"{datetime.now().year}-v1",
                    "DataIssues": data_issues_str,
                    "SalaryToSalesPct": round(salary_to_sales_pct, 2),
                    "SalesShareOfShop": round(sales_share, 2),
                    "SalaryShareOfShop": round(salary_share, 2),
                })

            # Add SHOP_METRICS summary row (matches n8n workflow)
            total_worked_days = sum(d["summary"].get("WorkedDays", 0) for d in results.values())
            total_worked_hours = sum(d["summary"].get("WorkedHours", 0) for d in results.values())
            shop_total_sales_only = sum(d["summary"].get("Sales", 0) for d in results.values())
            shop_total_addl = sum(d["summary"].get("AddlSales", 0) for d in results.values())
            shop_efficiency = (shop_total_salary / shop_total_sales * 100) if shop_total_sales > 0 else 0
            month_period_shop = (analytics_rows[0]["Period"] if analytics_rows else "") or datetime.now().strftime("%Y-%m")

            analytics_rows.append({
                "Employee": "SHOP_METRICS",
                "Shop": shop_display_analytics,
                "Period": month_period_shop,
                "PaymentType": "ALL_TYPES",
                "WorkedDays": total_worked_days,
                "WorkedHours": round(total_worked_hours, 2),
                "HourlyRate": 0,
                "SalesPercentage": "N/A",
                "BasePayment": 0,
                "TotalSales": round(shop_total_sales_only, 2),
                "AddlSales": round(shop_total_addl, 2),
                "AdjustedSales": round(shop_total_sales, 2),
                "SalesCommission": 0,
                "BonusPayment": 0,
                "FinalTotal": round(shop_total_salary, 2),
                "AvgSalesPerDay": round(shop_total_sales / total_worked_days, 2) if total_worked_days > 0 else 0,
                "AvgSalesPerHour": round(shop_total_sales / total_worked_hours, 2) if total_worked_hours > 0 else 0,
                "Description": f"Shop efficiency: {shop_efficiency:.2f}%",
                "ConfigVersion": "SHOP-v1",
                "DataIssues": "None",
                "SalaryToSalesPct": round(shop_efficiency, 2),
                "SalesShareOfShop": 100.0,
                "SalaryShareOfShop": 100.0,
            })

            # Split employee rows from SHOP_METRICS for prettier display
            employee_rows = [r for r in analytics_rows if r.get("Employee") != "SHOP_METRICS"]
            shop_row = next((r for r in analytics_rows if r.get("Employee") == "SHOP_METRICS"), None)

            # Key metrics at top
            if shop_row:
                m1, m2, m3, m4 = st.columns(4)
                with m1:
                    st.metric("Shop total sales", format_currency(shop_row.get("AdjustedSales", 0)))
                with m2:
                    st.metric("Shop total salary", format_currency(shop_row.get("FinalTotal", 0)))
                with m3:
                    st.metric("Shop efficiency", f"{shop_row.get('SalaryToSalesPct', 0):.1f}%")
                with m4:
                    st.metric("Employees", len(employee_rows))

            # Employee cards - 2 per row (Aleeza-style design)
            st.markdown("### Employee cards")
            for i in range(0, len(employee_rows), 2):
                card_cols = st.columns(2)
                for j, col in enumerate(card_cols):
                    idx = i + j
                    if idx >= len(employee_rows):
                        break
                    r = employee_rows[idx]
                    pct = r.get("SalaryToSalesPct", 0) or 0
                    sal_color = _salary_pct_color(pct)
                    eff_label, eff_class = _efficiency_rating(pct)
                    cost_row_class = _cost_efficiency_row_class(pct)
                    pt = (r.get("PaymentType") or "").replace("_", " ").upper()
                    emp = r.get("Employee", "")
                    period = r.get("Period", "")
                    final = r.get("FinalTotal", 0)
                    days = int(r.get("WorkedDays", 0))
                    earnings_per_day = final / days if days > 0 else 0
                    issues = r.get("DataIssues", "") or ""
                    data_quality = f"⚠️ {issues}" if (issues and issues != "None") else "None"
                    card_html = f"""
                    <div class="emp-card">
                        <div class="emp-card-header">
                            <span class="emp-card-header-left">{emp} – {period}</span>
                            <span class="emp-card-header-right">{pt} | Total: {format_currency(final)} | <span style="font-weight:700;">{pct:.1f}%</span></span>
                        </div>
                        <div class="emp-card-body">
                            <div class="emp-card-section">
                                <div class="emp-card-section-title">Payment Structure</div>
                                <table class="emp-card-table">
                                    <tr><td class="col-metric">Payment Type</td><td class="col-value">{pt}</td><td class="col-details">{r.get('SalesPercentage', '')}</td></tr>
                                    <tr><td class="col-metric">Config Version</td><td class="col-value">{r.get('ConfigVersion', '')}</td><td class="col-details">Configuration tracking</td></tr>
                                    <tr><td class="col-metric">Data Quality</td><td class="col-value">{data_quality}</td><td class="col-details">Data validation results</td></tr>
                                </table>
                            </div>
                            <div class="emp-card-section">
                                <div class="emp-card-section-title">Work Summary</div>
                                <table class="emp-card-table">
                                    <tr><td class="col-metric">Worked Days</td><td class="col-value">{days}</td><td class="col-details">Total working days in period</td></tr>
                                    <tr><td class="col-metric">Worked Hours</td><td class="col-value">{r.get('WorkedHours', 0):.2f}</td><td class="col-details">Total hours logged</td></tr>
                                    <tr><td class="col-metric">Hourly Rate</td><td class="col-value">{format_currency(r.get("HourlyRate", 0))}</td><td class="col-details">Base hourly payment rate</td></tr>
                                </table>
                            </div>
                            <div class="emp-card-section">
                                <div class="emp-card-section-title">Sales & Commission</div>
                                <table class="emp-card-table">
                                    <tr><td class="col-metric">Sales Commission Rate</td><td class="col-value">{r.get('SalesPercentage', 'N/A')}</td><td class="col-details">Commission % on sales</td></tr>
                                    <tr><td class="col-metric">Total Sales</td><td class="col-value">{format_currency(r.get("TotalSales", 0))}</td><td class="col-details">Regular sales amount</td></tr>
                                    <tr><td class="col-metric">Additional Sales</td><td class="col-value">{format_currency(r.get("AddlSales", 0))}</td><td class="col-details">Extra sales/bonuses</td></tr>
                                    <tr><td class="col-metric">Adjusted Sales</td><td class="col-value">{format_currency(r.get("AdjustedSales", 0))}</td><td class="col-details">Total + Additional sales</td></tr>
                                </table>
                            </div>
                            <div class="emp-card-section">
                                <div class="emp-card-section-title">Payment Calculation</div>
                                <table class="emp-card-table">
                                    <tr><td class="col-metric">Base Payment</td><td class="col-value">{format_currency(r.get("BasePayment", 0))}</td><td class="col-details">Hours × hourly rate</td></tr>
                                    <tr><td class="col-metric">Sales Commission</td><td class="col-value">{format_currency(r.get("SalesCommission", 0))}</td><td class="col-details">From commission structure</td></tr>
                                    <tr><td class="col-metric">Bonus Payment</td><td class="col-value">{format_currency(r.get("BonusPayment", 0))}</td><td class="col-details">Additional bonuses/guarantees</td></tr>
                                    <tr class="row-highlight-green"><td class="col-metric">Final Total Payment</td><td class="col-value">{format_currency(final)}</td><td class="col-details">Base + Commission + Bonuses</td></tr>
                                </table>
                            </div>
                            <div class="emp-card-section">
                                <div class="emp-card-section-title">Performance Metrics</div>
                                <table class="emp-card-table">
                                    <tr><td class="col-metric">Average Sales per Day</td><td class="col-value">{format_currency(r.get('AvgSalesPerDay', 0))}</td><td class="col-details">Total sales ÷ {days} days</td></tr>
                                    <tr><td class="col-metric">Average Sales per Hour</td><td class="col-value">{format_currency(r.get('AvgSalesPerHour', 0))}</td><td class="col-details">Total sales ÷ hours</td></tr>
                                    <tr><td class="col-metric">Earnings per Day</td><td class="col-value">{format_currency(earnings_per_day)}</td><td class="col-details">Total payment ÷ working days</td></tr>
                                </table>
                            </div>
                            <div class="emp-card-section">
                                <div class="emp-card-section-title">Business Efficiency Metrics</div>
                                <table class="emp-card-table">
                                    <tr class="{cost_row_class}"><td class="col-metric">Cost Efficiency</td><td class="col-value" style="color:{sal_color};font-weight:700;">{pct:.1f}%</td><td class="col-details">Salary cost per £1 of sales (lower = better)</td></tr>
                                    <tr><td class="col-metric">Sales Share of Shop</td><td class="col-value">{r.get('SalesShareOfShop', 0):.1f}%</td><td class="col-details">Contribution to total shop sales</td></tr>
                                    <tr><td class="col-metric">Salary Share of Shop</td><td class="col-value">{r.get('SalaryShareOfShop', 0):.1f}%</td><td class="col-details">Proportion of total shop payroll</td></tr>
                                    <tr class="{eff_class}"><td class="col-metric">Efficiency Rating</td><td class="col-value">{eff_label}</td><td class="col-details">Overall performance assessment</td></tr>
                                </table>
                            </div>
                        </div>
                    </div>
                    """
                    with col:
                        st.markdown(card_html, unsafe_allow_html=True)

            # Optional: full table in expander
            with st.expander("📋 View full table"):
                emp_df = pd.DataFrame(employee_rows)
                if not emp_df.empty:
                    st.dataframe(emp_df, width="stretch", height=300, hide_index=True)

            # Shop summary in a highlighted card
            if shop_row:
                st.markdown("---")
                with st.container(border=True):
                    st.subheader("🏪 Shop summary")
                    st.caption(shop_row.get("Description", ""))
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.metric("Total sales", format_currency(shop_row.get("AdjustedSales", 0)))
                        st.metric("Avg per day", format_currency(shop_row.get("AvgSalesPerDay", 0)))
                    with c2:
                        st.metric("Total salary", format_currency(shop_row.get("FinalTotal", 0)))
                        st.metric("Avg per hour", format_currency(shop_row.get("AvgSalesPerHour", 0)))
                    with c3:
                        shop_eff = shop_row.get("SalaryToSalesPct", 0) or 0
                        eff_color = _salary_pct_color(shop_eff)
                        st.markdown(f'<div class="metric-label">Efficiency</div><div class="salary-pct-badge" style="color:{eff_color};">{shop_eff:.1f}%</div>', unsafe_allow_html=True)
                        st.metric("Days worked", int(shop_row.get("WorkedDays", 0)))

            # Save to Airtable
            st.markdown("---")
            st.subheader("Save to Airtable")
            tables_cfg_analytics = (load_config() or {}).get("airtable_config_tables", {})
            analytics_table = tables_cfg_analytics.get("shop_analytics", "Shop Analytics")
            base_id_analytics = shop_config_analytics.get("airtable_base_id", "")
            base_id, api_key_analytics, _ = _get_airtable_credentials(results_shop_key)

            if base_id_analytics and api_key_analytics:
                save_col, update_col = st.columns(2)
                with save_col:
                    if st.button("Save all (append new)", key="save_analytics_btn", help="Append all records to Airtable. Use for first-time save or when adding new employees."):
                        try:
                            at_client_analytics = AirtableClient(api_key=api_key_analytics)
                            result = at_client_analytics.save_shop_analytics(
                                base_id_analytics, analytics_table, analytics_rows
                            )
                            st.success(f"Saved {result.get('records_created', 0)} analytics records to Airtable.")
                        except Exception as e:
                            st.error(f"Failed to save: {e}")
                            import traceback
                            with st.expander("Details"):
                                st.code(traceback.format_exc())
                with update_col:
                    if st.button("Update existing", key="update_analytics_btn", help="Update records already in Airtable (e.g. after bonus adjustments). Creates new records only for employees not yet saved."):
                        try:
                            at_client_analytics = AirtableClient(api_key=api_key_analytics)
                            result = at_client_analytics.upsert_shop_analytics(
                                base_id_analytics, analytics_table, analytics_rows,
                                shop=shop_display_analytics,
                                period=analytics_rows[0].get("Period", "") if analytics_rows else "",
                            )
                            st.success(result.get("message", f"Updated {result.get('records_updated', 0)}, created {result.get('records_created', 0)}."))
                        except Exception as e:
                            st.error(f"Failed to update: {e}")
                            import traceback
                            with st.expander("Details"):
                                st.code(traceback.format_exc())
            else:
                st.warning("Configure Airtable Base ID and API key for this shop to save analytics.")

    with analytics_sub2:
        st.subheader("Historical analytics from Airtable")
        base_id_hist, api_key_hist, _ = _get_airtable_credentials(selected_shop)
        shop_display_hist = shop_config.get("shop_display_name") or shop_config.get("name", selected_shop)
        tables_cfg_hist = (load_config() or {}).get("airtable_config_tables", {})
        analytics_table_hist = tables_cfg_hist.get("shop_analytics", "Shop Analytics")

        if not base_id_hist or not api_key_hist:
            st.warning("Configure Airtable credentials to load historical analytics.")
        else:
            period_filter = st.text_input("Period (e.g. 2025-02)", key="analytics_period_filter", placeholder="Leave empty for all")
            if st.button("Load analytics", key="load_analytics_btn"):
                try:
                    at_client_hist = AirtableClient(api_key=api_key_hist)
                    records = at_client_hist.get_shop_analytics(
                        base_id_hist, analytics_table_hist,
                        shop=shop_display_hist,
                        period=period_filter.strip() if period_filter else None,
                    )
                    if records:
                        def _num(v, default=0):
                            if v is None: return default
                            if isinstance(v, (int, float)): return float(v)
                            s = str(v).replace("£", "").replace(",", "").replace("%", "").strip()
                            return float(s) if s else default

                        hist_employees = [r for r in records if r.get("Employee") != "SHOP_METRICS"]
                        hist_shop = next((r for r in records if r.get("Employee") == "SHOP_METRICS"), None)

                        if hist_shop:
                            m1, m2, m3 = st.columns(3)
                            with m1:
                                st.metric("Shop sales", format_currency(_num(hist_shop.get("AdjustedSales"))))
                            with m2:
                                st.metric("Shop salary", format_currency(_num(hist_shop.get("FinalTotal"))))
                            with m3:
                                st.metric("Efficiency", f"{_num(hist_shop.get('SalaryToSalesPct')):.1f}%")

                        st.markdown("### Employee cards")
                        for i in range(0, len(hist_employees), 2):
                            card_cols = st.columns(2)
                            for j, col in enumerate(card_cols):
                                idx = i + j
                                if idx >= len(hist_employees):
                                    break
                                r = hist_employees[idx]
                                pct = _num(r.get("SalaryToSalesPct"))
                                sal_color = _salary_pct_color(pct)
                                eff_label, eff_class = _efficiency_rating(pct)
                                cost_row_class = _cost_efficiency_row_class(pct)
                                pt = (str(r.get("PaymentType", "") or "").replace("_", " ").upper())
                                emp = r.get("Employee", "")
                                period = r.get("Period", "")
                                final = _num(r.get("FinalTotal"))
                                days = int(_num(r.get("WorkedDays")))
                                earnings_per_day = final / days if days > 0 else 0
                                issues = str(r.get("DataIssues", "") or "")
                                data_quality = f"⚠️ {issues}" if (issues and issues.lower() != "none") else "None"
                                card_html = f"""
                                <div class="emp-card">
                                    <div class="emp-card-header">
                                        <span class="emp-card-header-left">{emp} – {period}</span>
                                        <span class="emp-card-header-right">{pt} | Total: {format_currency(final)} | <span style="font-weight:700;">{pct:.1f}%</span></span>
                                    </div>
                                    <div class="emp-card-body">
                                        <div class="emp-card-section">
                                            <div class="emp-card-section-title">Payment Structure</div>
                                            <table class="emp-card-table">
                                                <tr><td class="col-metric">Payment Type</td><td class="col-value">{pt}</td><td class="col-details">{r.get('SalesPercentage', '')}</td></tr>
                                                <tr><td class="col-metric">Config Version</td><td class="col-value">{r.get('ConfigVersion', '')}</td><td class="col-details">Configuration tracking</td></tr>
                                                <tr><td class="col-metric">Data Quality</td><td class="col-value">{data_quality}</td><td class="col-details">Data validation results</td></tr>
                                            </table>
                                        </div>
                                        <div class="emp-card-section">
                                            <div class="emp-card-section-title">Work Summary</div>
                                            <table class="emp-card-table">
                                                <tr><td class="col-metric">Worked Days</td><td class="col-value">{days}</td><td class="col-details">Total working days in period</td></tr>
                                                <tr><td class="col-metric">Worked Hours</td><td class="col-value">{_num(r.get('WorkedHours')):.2f}</td><td class="col-details">Total hours logged</td></tr>
                                                <tr><td class="col-metric">Hourly Rate</td><td class="col-value">{format_currency(_num(r.get("HourlyRate")))}</td><td class="col-details">Base hourly payment rate</td></tr>
                                            </table>
                                        </div>
                                        <div class="emp-card-section">
                                            <div class="emp-card-section-title">Sales & Commission</div>
                                            <table class="emp-card-table">
                                                <tr><td class="col-metric">Sales Commission Rate</td><td class="col-value">{r.get('SalesPercentage', 'N/A')}</td><td class="col-details">Commission % on sales</td></tr>
                                                <tr><td class="col-metric">Total Sales</td><td class="col-value">{format_currency(_num(r.get("TotalSales")))}</td><td class="col-details">Regular sales amount</td></tr>
                                                <tr><td class="col-metric">Additional Sales</td><td class="col-value">{format_currency(_num(r.get("AddlSales")))}</td><td class="col-details">Extra sales/bonuses</td></tr>
                                                <tr><td class="col-metric">Adjusted Sales</td><td class="col-value">{format_currency(_num(r.get("AdjustedSales")))}</td><td class="col-details">Total + Additional sales</td></tr>
                                            </table>
                                        </div>
                                        <div class="emp-card-section">
                                            <div class="emp-card-section-title">Payment Calculation</div>
                                            <table class="emp-card-table">
                                                <tr><td class="col-metric">Base Payment</td><td class="col-value">{format_currency(_num(r.get("BasePayment")))}</td><td class="col-details">Hours × hourly rate</td></tr>
                                                <tr><td class="col-metric">Sales Commission</td><td class="col-value">{format_currency(_num(r.get("SalesCommission")))}</td><td class="col-details">From commission structure</td></tr>
                                                <tr><td class="col-metric">Bonus Payment</td><td class="col-value">{format_currency(_num(r.get("BonusPayment")))}</td><td class="col-details">Additional bonuses/guarantees</td></tr>
                                                <tr class="row-highlight-green"><td class="col-metric">Final Total Payment</td><td class="col-value">{format_currency(final)}</td><td class="col-details">Base + Commission + Bonuses</td></tr>
                                            </table>
                                        </div>
                                        <div class="emp-card-section">
                                            <div class="emp-card-section-title">Performance Metrics</div>
                                            <table class="emp-card-table">
                                                <tr><td class="col-metric">Average Sales per Day</td><td class="col-value">{format_currency(_num(r.get('AvgSalesPerDay')))}</td><td class="col-details">Total sales ÷ {days} days</td></tr>
                                                <tr><td class="col-metric">Average Sales per Hour</td><td class="col-value">{format_currency(_num(r.get('AvgSalesPerHour')))}</td><td class="col-details">Total sales ÷ hours</td></tr>
                                                <tr><td class="col-metric">Earnings per Day</td><td class="col-value">{format_currency(earnings_per_day)}</td><td class="col-details">Total payment ÷ working days</td></tr>
                                            </table>
                                        </div>
                                        <div class="emp-card-section">
                                            <div class="emp-card-section-title">Business Efficiency Metrics</div>
                                            <table class="emp-card-table">
                                                <tr class="{cost_row_class}"><td class="col-metric">Cost Efficiency</td><td class="col-value" style="color:{sal_color};font-weight:700;">{pct:.1f}%</td><td class="col-details">Salary cost per £1 of sales (lower = better)</td></tr>
                                                <tr><td class="col-metric">Sales Share of Shop</td><td class="col-value">{_num(r.get('SalesShareOfShop')):.1f}%</td><td class="col-details">Contribution to total shop sales</td></tr>
                                                <tr><td class="col-metric">Salary Share of Shop</td><td class="col-value">{_num(r.get('SalaryShareOfShop')):.1f}%</td><td class="col-details">Proportion of total shop payroll</td></tr>
                                                <tr class="{eff_class}"><td class="col-metric">Efficiency Rating</td><td class="col-value">{eff_label}</td><td class="col-details">Overall performance assessment</td></tr>
                                            </table>
                                        </div>
                                    </div>
                                </div>
                                """
                                with col:
                                    st.markdown(card_html, unsafe_allow_html=True)
                        st.success(f"Loaded {len(records)} records.")
                    else:
                        st.info("No analytics records found. Save from Current Report first.")
                except Exception as e:
                    st.error(f"Failed to load: {e}")
