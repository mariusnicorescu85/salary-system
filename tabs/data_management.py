"""Data Management tab content."""

import streamlit as st
from src.airtable_client import AirtableClient


def render(selected_shop: str, shop_config: dict, config: dict):
    """Render the Data Management tab."""
    from app import (
        load_config,
        _get_airtable_credentials,
        _render_employees_tab,
        _render_commission_tiers_tab,
        _render_name_mappings_tab,
        _render_sales_bonus_tab,
        _render_monthly_bonuses_tab,
        _render_wage_bracket_tab,
    )

    st.header("📋 Data Management")
    st.info("Manage all Airtable config tables. Add, edit, or delete records. Changes are saved directly to Airtable.")

    tables_cfg = (load_config() or {}).get("airtable_config_tables", {})
    base_id, api_key, _ = _get_airtable_credentials(selected_shop)
    shop_display = shop_config.get("shop_display_name") or shop_config.get("name", selected_shop)
    shop_options = [s.get("shop_display_name") or s.get("name", k) for k, s in config["shops"].items()]
    payment_types = [
        "hourly_only", "commission_only", "dave_package", "manager", "sales_only",
        "progressive_tiered_commission", "hybrid_daily_max",
        "flat_rate_tiered_commission", "flat_rate_tiered_commission_with_transport",
        "tiered_commission", "molly_commission", "alex_hybrid", "net_commission_tiered",
        "isaac_package",
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
            with dm_tab1:
                _render_employees_tab(client, base_id, tables_cfg, shop_display, shop_options, payment_types, config)
            with dm_tab2:
                _render_commission_tiers_tab(client, base_id, tables_cfg, shop_display, shop_options, config)
            with dm_tab3:
                _render_name_mappings_tab(client, base_id, tables_cfg, shop_display, shop_options, config)
            with dm_tab4:
                _render_sales_bonus_tab(client, base_id, tables_cfg, shop_display, shop_options, config)
            with dm_tab5:
                _render_monthly_bonuses_tab(client, base_id, tables_cfg, shop_display, shop_options, config)
            with dm_tab6:
                _render_wage_bracket_tab(client, base_id, tables_cfg)
