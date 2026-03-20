"""Airtable Export Preview tab content."""

import os
import streamlit as st
import pandas as pd
from src.airtable_client import AirtableClient


def render(shop_config: dict):
    """Render the Airtable Export Preview tab."""
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

            preview_df = pd.DataFrame(airtable_records)
            st.dataframe(preview_df, width='stretch', height=400)

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
            st.subheader("🚀 Export to Airtable")

            base_id = shop_config.get('airtable_base_id', '').strip()
            table_name = shop_config.get('airtable_table_name', '').strip()
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

                api_key_from_secrets = None
                try:
                    if hasattr(st, 'secrets') and 'airtable' in st.secrets and 'api_key' in st.secrets.airtable:
                        api_key_from_secrets = st.secrets.airtable.api_key
                except Exception:
                    pass

                api_key_from_env = os.getenv('AIRTABLE_API_KEY')
                api_key_from_session = st.session_state.get('airtable_api_key')
                default_api_key = api_key_from_secrets or api_key_from_env or api_key_from_session

                if default_api_key:
                    st.success("✅ Airtable API key found (from secrets/env/session)")
                    airtable_api_key_input = default_api_key
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
                    if airtable_api_key_input:
                        st.session_state.airtable_api_key = airtable_api_key_input

                if airtable_api_key_input:
                    st.markdown("---")
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

                    if update_existing:
                        st.warning("⚠️ **Update Mode**: Only existing records will be updated. Records not found in Airtable will be skipped (not created).")

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
                    if st.button("✅ Confirm & Export to Airtable", type="primary", width='content'):
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
