"""Employee Evolution tab - Weekly evolution analysis: cost vs profit, sales vs wages, wage %."""

import io
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd
import streamlit as st


def _compute_employee_evolution(
    records: List[Dict],
    engine,
    employee_filter: Optional[str] = None,
) -> List[Dict]:
    """Aggregate records by week per employee: Sales, Wages, Profit, Wage_vs_Sales_%."""
    out = []
    for r in records:
        date_str = r.get("Date")
        if not date_str:
            continue
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            continue
        payment = engine.calculate_daily_payment(
            r["Employee"],
            r.get("Hours", 0),
            r.get("Sales", 0),
            r.get("AddlSales", 0),
            date_str,
        )
        base_pay = payment.get("Base", 0) or 0
        commission_pay = payment.get("Commission", 0) or 0
        pt = (payment.get("PaymentType") or "").lower()
        if "hybrid" in pt or "monthlymax" in pt:
            wages = max(base_pay, commission_pay)
        else:
            wages = base_pay + commission_pay
        out.append({**r, "_wages": wages})

    by_emp_week = defaultdict(lambda: {"sales": 0, "wages": 0, "hours": 0, "days": 0})
    for r in out:
        emp = r.get("Employee", "")
        if employee_filter and employee_filter.lower() not in emp.lower():
            continue
        date_str = r.get("Date")
        if not date_str:
            continue
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            continue
        week_start = dt - timedelta(days=dt.weekday())
        week_key = (emp, week_start.strftime("%Y-%m-%d"))
        sales = (r.get("Sales", 0) or 0) + (r.get("AddlSales", 0) or 0)
        wages = r.get("_wages", 0) or 0
        hours = r.get("Hours", 0) or 0
        by_emp_week[week_key]["sales"] += sales
        by_emp_week[week_key]["wages"] += wages
        by_emp_week[week_key]["hours"] += hours
        by_emp_week[week_key]["days"] += 1

    rows = []
    for (emp, week_start), data in sorted(by_emp_week.items(), key=lambda x: (x[0][0], x[0][1])):
        sales = data["sales"]
        wages = data["wages"]
        profit = sales - wages
        wage_pct = (wages / sales * 100) if sales > 0 else 0
        rows.append({
            "Employee": emp,
            "Week_Start": week_start,
            "Sales": round(sales, 2),
            "Wages": round(wages, 2),
            "Profit": round(profit, 2),
            "Wage_vs_Sales_%": round(wage_pct, 2),
            "Hours": round(data["hours"], 2),
            "Days": data["days"],
        })
    return rows


def render(selected_shop, shop_config, config, report_file):
    """Render the Employee Evolution tab."""
    from app import load_config, load_employee_config, _get_airtable_credentials
    from src.airtable_client import AirtableClient
    from src.calculation_engine import CalculationEngine
    from src.data_processor import DataProcessor

    st.header("📈 Employee Evolution")
    st.info(
        "Upload a report CSV to see weekly evolution: **cost vs profit**, **sales vs wages**, and **wage vs sales %** "
        "for each employee since they joined."
    )
    shop_keys = list((load_config() or {}).get("shops", {}).keys())
    selected_shop_ev = st.session_state.get("selected_shop") or (shop_keys[0] if shop_keys else None) or selected_shop
    shop_config_ev = (load_config() or {}).get("shops", {}).get(selected_shop_ev, {})
    employees_ev, _, emp_config_ev = load_employee_config(selected_shop_ev) or ({}, {}, {})
    emp_config_full_ev = emp_config_ev if isinstance(emp_config_ev, dict) else {}

    ev_uploaded = st.file_uploader(
        "Upload report (CSV)",
        type=["csv"],
        key="ev_report_upload",
        help="Same format as Calculate tab: Employee sections, Date, Hours, Sales, Add'l Sales.",
    )
    st.caption("💡 Or pick a report from the **sidebar** (Saved Reports or Google Drive).")
    ev_report_file = ev_uploaded
    if not ev_report_file and report_file is not None:
        fname = getattr(report_file, "name", "") or ""
        if fname.lower().endswith(".csv"):
            ev_report_file = report_file

    use_simple_mode = st.checkbox(
        "Simple mode (hourly rate only, no Airtable)",
        value=not bool(employees_ev),
        key="ev_simple_mode",
        help="Use when Airtable is not configured. Assumes hourly-only pay for all employees.",
    )
    simple_hourly_rate = 11.44
    if use_simple_mode:
        simple_hourly_rate = st.number_input(
            "Hourly rate (£)",
            min_value=0.0,
            step=0.5,
            value=11.44,
            format="%.2f",
            key="ev_hourly_rate",
        )

    employee_options = ["All employees"]
    if ev_report_file:
        try:
            if hasattr(ev_report_file, "seek"):
                ev_report_file.seek(0)
            raw = ev_report_file.read()
            content = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
            df_ev = pd.read_csv(io.StringIO(content), header=None)
            name_mapping_ev = emp_config_full_ev.get("name_mapping", {}) or {}
            exclude_ev = emp_config_full_ev.get("exclude_patterns", []) or []
            processor_ev = DataProcessor(name_mapping=name_mapping_ev, exclude_patterns=exclude_ev)
            records_preview = processor_ev.parse_csv(df_ev)
            emp_names = sorted(set(r.get("Employee", "") for r in records_preview if r.get("Employee")))
            employee_options = ["All employees"] + emp_names
        except Exception as e:
            st.warning(f"Could not parse file to list employees: {e}")

    selected_employee = st.selectbox(
        "Filter by employee",
        options=employee_options,
        key="ev_employee_filter",
    )
    employee_filter_ev = None if selected_employee == "All employees" else selected_employee

    if ev_report_file and st.button("Run evolution analysis", key="ev_run_btn"):
        try:
            if hasattr(ev_report_file, "seek"):
                ev_report_file.seek(0)
            raw = ev_report_file.read()
            content = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
            df_ev = pd.read_csv(io.StringIO(content), header=None)
            name_mapping_ev = emp_config_full_ev.get("name_mapping", {}) or {}
            exclude_ev = emp_config_full_ev.get("exclude_patterns", []) or []
            processor_ev = DataProcessor(name_mapping=name_mapping_ev, exclude_patterns=exclude_ev)
            records_ev = processor_ev.parse_csv(df_ev)
            if not records_ev:
                st.warning("No valid records found. Check file format.")
            else:
                if use_simple_mode:
                    employees_ev = {
                        emp: {"payment_type": "hourly_only", "hourly_rate": simple_hourly_rate}
                        for emp in {r["Employee"] for r in records_ev}
                    }
                wage_brackets_ev = []
                base_id_ev, api_key_ev, _ = _get_airtable_credentials(selected_shop_ev)
                if base_id_ev and api_key_ev and not use_simple_mode:
                    tables_ev = (load_config() or {}).get("airtable_config_tables", {})
                    bracket_table = tables_ev.get("uk_wage_bracket", "UK Wage Bracket")
                    try:
                        at_client_ev = AirtableClient(api_key=api_key_ev)
                        wage_brackets_ev = at_client_ev.get_wage_brackets(base_id_ev, bracket_table)
                    except Exception:
                        pass
                engine_ev = CalculationEngine(employees_ev, {}, wage_brackets=wage_brackets_ev)
                evolution_rows = _compute_employee_evolution(records_ev, engine_ev, employee_filter_ev)
                if not evolution_rows:
                    st.info("No data for selected employee filter.")
                else:
                    import plotly.graph_objects as go
                    df_evolution = pd.DataFrame(evolution_rows)

                    # --- Graphs (shown first) ---
                    st.subheader("📊 Charts")
                    emp_rows = evolution_rows  # filtered by selection

                    if employee_filter_ev:
                        # Single employee: multiple charts
                        emp_rows = [r for r in evolution_rows if employee_filter_ev.lower() in r["Employee"].lower()]
                    if emp_rows:
                        weeks = [r["Week_Start"] for r in emp_rows]
                        emp_label = emp_rows[0]["Employee"] if employee_filter_ev else "All"

                        # Combined chart: Weekly Wages (£) vs Sales (£) with Wage % as secondary axis
                        st.markdown("**Weekly wages vs sales** — Wages are calculated from hours or commission; the % shows salary as % of sales for that week.")
                        from plotly.subplots import make_subplots
                        fig_combined = make_subplots(specs=[[{"secondary_y": True}]])
                        fig_combined.add_trace(
                            go.Bar(x=weeks, y=[r["Wages"] for r in emp_rows], name="Wages (£)", marker_color="#ef4444"),
                            secondary_y=False,
                        )
                        fig_combined.add_trace(
                            go.Bar(x=weeks, y=[r["Sales"] for r in emp_rows], name="Sales (£)", marker_color="#22c55e"),
                            secondary_y=False,
                        )
                        fig_combined.add_trace(
                            go.Scatter(
                                x=weeks, y=[r["Wage_vs_Sales_%"] for r in emp_rows],
                                mode="lines+markers+text", name="Wage %",
                                text=[f"{r['Wage_vs_Sales_%']:.1f}%" for r in emp_rows],
                                textposition="top center", line=dict(color="#2563eb", width=2),
                            ),
                            secondary_y=True,
                        )
                        fig_combined.add_hline(y=25, line_dash="dash", line_color="gray", secondary_y=True, annotation_text="25% target")
                        fig_combined.update_layout(
                            title="Weekly Wages (£) vs Sales (£) — Salary % of Sales",
                            barmode="group", height=400, margin=dict(l=50, r=50, t=50, b=50),
                        )
                        fig_combined.update_yaxes(title_text="£", secondary_y=False)
                        max_pct = max((r["Wage_vs_Sales_%"] for r in emp_rows), default=50)
                        fig_combined.update_yaxes(title_text="Wage %", secondary_y=True, range=[0, max(50, max_pct * 1.2)])
                        st.plotly_chart(fig_combined, width="stretch")

                        col_chart1, col_chart2 = st.columns(2)
                        with col_chart1:
                            fig_pct = go.Figure()
                            fig_pct.add_trace(go.Scatter(
                                x=weeks, y=[r["Wage_vs_Sales_%"] for r in emp_rows],
                                mode="lines+markers", name="Wage %", line=dict(color="#2563eb"),
                            ))
                            fig_pct.add_hline(y=25, line_dash="dash", line_color="gray", annotation_text="25% target")
                            fig_pct.update_layout(
                                title="Wage vs Sales %",
                                xaxis_title="Week", yaxis_title="Wage %",
                                height=300, margin=dict(l=40, r=20, t=40, b=40),
                            )
                            st.plotly_chart(fig_pct, width="stretch")

                        with col_chart2:
                            fig_sales_wages = go.Figure()
                            fig_sales_wages.add_trace(go.Scatter(
                                x=weeks, y=[r["Sales"] for r in emp_rows],
                                mode="lines+markers", name="Sales", line=dict(color="#22c55e"),
                            ))
                            fig_sales_wages.add_trace(go.Scatter(
                                x=weeks, y=[r["Wages"] for r in emp_rows],
                                mode="lines+markers", name="Wages", line=dict(color="#ef4444"),
                            ))
                            fig_sales_wages.update_layout(
                                title="Sales vs Wages (£)",
                                xaxis_title="Week", yaxis_title="£",
                                height=300, margin=dict(l=40, r=20, t=40, b=40),
                            )
                            st.plotly_chart(fig_sales_wages, width="stretch")

                        if not employee_filter_ev and len(set(r["Employee"] for r in emp_rows)) > 1:
                            # All employees: add Wage % comparison bar chart
                            by_emp = defaultdict(lambda: {"sales": 0, "wages": 0})
                            for r in emp_rows:
                                by_emp[r["Employee"]]["sales"] += r["Sales"]
                                by_emp[r["Employee"]]["wages"] += r["Wages"]
                            emp_names = list(by_emp.keys())
                            pcts = [(by_emp[e]["wages"] / by_emp[e]["sales"] * 100) if by_emp[e]["sales"] > 0 else 0 for e in emp_names]
                            fig_bar = go.Figure(go.Bar(
                                x=pcts, y=emp_names, orientation="h",
                                marker_color=["#22c55e" if p < 25 else "#eab308" if p <= 30 else "#ef4444" for p in pcts],
                            ))
                            fig_bar.add_vline(x=25, line_dash="dash", line_color="gray", annotation_text="25%")
                            fig_bar.update_layout(
                                title="Wage % by Employee (total period)",
                                xaxis_title="Wage %", height=200 + len(emp_names) * 25,
                                margin=dict(l=10, r=40), yaxis=dict(autorange="reversed"),
                            )
                            st.plotly_chart(fig_bar, width="stretch")

                    # --- Table (collapsible): weekly breakdown by days worked ---
                    daily_rows = []
                    for r in records_ev:
                        emp = r.get("Employee", "")
                        if employee_filter_ev and employee_filter_ev.lower() not in emp.lower():
                            continue
                        date_str = r.get("Date")
                        if not date_str:
                            continue
                        try:
                            dt = datetime.strptime(date_str, "%Y-%m-%d")
                        except ValueError:
                            continue
                        week_start = dt - timedelta(days=dt.weekday())
                        payment = engine_ev.calculate_daily_payment(
                            emp, r.get("Hours", 0), r.get("Sales", 0), r.get("AddlSales", 0), date_str
                        )
                        base_pay = payment.get("Base", 0) or 0
                        commission_pay = payment.get("Commission", 0) or 0
                        pt = (payment.get("PaymentType") or "").lower()
                        if "hybrid" in pt or "monthlymax" in pt:
                            wages = max(base_pay, commission_pay)
                        else:
                            wages = base_pay + commission_pay
                        sales = (r.get("Sales", 0) or 0) + (r.get("AddlSales", 0) or 0)
                        wage_pct = (wages / sales * 100) if sales > 0 else 0
                        if base_pay > 0 and commission_pay > 0:
                            paid_via = "Hours" if base_pay >= commission_pay else "Commission"
                        elif base_pay > 0:
                            paid_via = "Hours"
                        else:
                            paid_via = "Commission"
                        daily_rows.append({
                            "Week_Start": week_start.strftime("%Y-%m-%d"),
                            "Date": date_str,
                            "Hours": round(r.get("Hours", 0) or 0, 2),
                            "Sales": round(r.get("Sales", 0) or 0, 2),
                            "Add'l Sales": round(r.get("AddlSales", 0) or 0, 2),
                            "Total Sales": round(sales, 2),
                            "Base (Hours)": round(base_pay, 2),
                            "Commission": round(commission_pay, 2),
                            "Wages": round(wages, 2),
                            "Paid via": paid_via,
                            "Wage_%": round(wage_pct, 2),
                        })
                    daily_rows.sort(key=lambda x: (x["Week_Start"], x["Date"]))
                    by_week = defaultdict(list)
                    for row in daily_rows:
                        by_week[row["Week_Start"]].append(row)
                    with st.expander("📋 View data table", expanded=False):
                        for week_start in sorted(by_week.keys()):
                            days = by_week[week_start]
                            week_sales = sum(d["Total Sales"] for d in days)
                            week_wages = sum(d["Wages"] for d in days)
                            week_pct = (week_wages / week_sales * 100) if week_sales > 0 else 0
                            hours_days = sum(1 for d in days if d.get("Paid via") == "Hours")
                            comm_days = sum(1 for d in days if d.get("Paid via") == "Commission")
                            pay_breakdown = f" | {hours_days}d Hours, {comm_days}d Commission" if (hours_days or comm_days) else ""
                            week_label = f"Week of {week_start} — Sales: £{week_sales:,.2f} | Wages: £{week_wages:,.2f} | Wage %: {week_pct:.1f}%{pay_breakdown}"
                            with st.expander(week_label, expanded=False):
                                df_week = pd.DataFrame(days)
                                cols = ["Date", "Hours", "Sales", "Add'l Sales", "Total Sales", "Base (Hours)", "Commission", "Paid via", "Wages", "Wage_%"]
                                st.dataframe(df_week[[c for c in cols if c in df_week.columns]], width="stretch", hide_index=True)
                    df_daily = pd.DataFrame(daily_rows)
                    csv_ev = df_daily.to_csv(index=False)
                    st.download_button(
                        "Download CSV",
                        data=csv_ev,
                        file_name="employee_evolution.csv",
                        mime="text/csv",
                        key="ev_download",
                    )
        except Exception as e:
            st.error(f"Analysis failed: {e}")
    elif not ev_report_file:
        st.caption("Upload a report or select one from the sidebar to run the analysis.")
