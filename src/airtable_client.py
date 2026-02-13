"""
Airtable Client
Handles appending data to Airtable and persisting targets/adjustments for Streamlit Cloud.
"""

from pyairtable import Api
from typing import List, Dict, Optional, Any
import os
import json


class AirtableClient:
    """Client for interacting with Airtable"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Airtable client
        
        Args:
            api_key: Airtable API key. If not provided, will use AIRTABLE_API_KEY env var
        """
        self.api_key = api_key or os.getenv('AIRTABLE_API_KEY')
        if not self.api_key:
            raise ValueError(
                "Airtable API key not provided. Set AIRTABLE_API_KEY environment variable "
                "or pass api_key parameter."
            )
        self.api = Api(self.api_key)
    
    def append_records(self, base_id: str, table_name: str, records: List[Dict]) -> Dict:
        """
        Append records to an Airtable table
        
        Args:
            base_id: Airtable base ID
            table_name: Name of the table
            records: List of record dictionaries to append
        
        Returns:
            Response from Airtable API
        """
        table = self.api.table(base_id, table_name)
        
        # Transform records to Airtable format
        airtable_records = []
        for record in records:
            airtable_record = {}
            for key, value in record.items():
                # Skip empty Date fields (Airtable Date fields don't accept empty strings)
                if key == 'Date' and (value == '' or value is None):
                    continue  # Don't include empty Date field
                # Airtable field names should match your table schema
                # You may need to adjust field names based on your Airtable setup
                airtable_record[key] = value
            airtable_records.append(airtable_record)
        
        # Batch create records (Airtable allows up to 10 records per batch)
        results = []
        batch_size = 10
        for i in range(0, len(airtable_records), batch_size):
            batch = airtable_records[i:i + batch_size]
            result = table.batch_create(batch)
            results.extend(result)
        
        return {
            'success': True,
            'records_created': len(results),
            'records': results
        }
    
    def check_existing_records(self, base_id: str, table_name: str, 
                              records: List[Dict]) -> Dict:
        """
        Check which records already exist in Airtable
        
        Args:
            base_id: Airtable base ID
            table_name: Name of the table
            records: List of records to check
        
        Returns:
            Dictionary with 'existing' and 'new' record lists
        """
        table = self.api.table(base_id, table_name)
        
        existing_records = []
        new_records = []
        
        # Group records by type for efficient checking
        daily_records = [r for r in records if r.get('RecordType') == 'Daily']
        summary_records = [r for r in records if r.get('RecordType') == 'Monthly Summary']
        
        # Check daily records (by Employee + Date)
        if daily_records:
            # Get all existing daily records for the date range
            dates = [r.get('Date') for r in daily_records if r.get('Date')]
            if dates:
                min_date = min(dates)
                max_date = max(dates)
                employees = list(set(r.get('Employee') for r in daily_records))
                
                # Build filter formula
                # Airtable OR syntax: OR({Field} = "value1", {Field} = "value2", ...)
                employee_conditions = ', '.join([f'{{Employee}} = "{emp}"' for emp in employees])
                if len(employees) > 1:
                    formula = f'AND({{RecordType}} = "Daily", {{Date}} >= "{min_date}", {{Date}} <= "{max_date}", OR({employee_conditions}))'
                else:
                    formula = f'AND({{RecordType}} = "Daily", {{Date}} >= "{min_date}", {{Date}} <= "{max_date}", {{Employee}} = "{employees[0]}")'
                
                try:
                    existing_daily = table.all(formula=formula)
                    existing_keys = set()
                    for rec in existing_daily:
                        emp = rec['fields'].get('Employee', '')
                        date = rec['fields'].get('Date', '')
                        if date:
                            # Airtable returns dates in various formats, normalize
                            if isinstance(date, str):
                                date_str = date[:10]  # Take YYYY-MM-DD part
                            else:
                                date_str = str(date)[:10]
                            existing_keys.add((emp, date_str))
                    
                    for record in daily_records:
                        emp = record.get('Employee', '')
                        date = record.get('Date', '')
                        if date and (emp, date) in existing_keys:
                            existing_records.append(record)
                        else:
                            new_records.append(record)
                except Exception as e:
                    # If query fails, assume all are new (safer)
                    new_records.extend(daily_records)
        
        # Check monthly summary records (by Employee + Month)
        if summary_records:
            # Get all existing monthly summaries for the months in question
            months = list(set(r.get('Month') for r in summary_records if r.get('Month')))
            if months:
                employees = list(set(r.get('Employee') for r in summary_records))
                
                # Build filter formula
                # Airtable OR syntax: OR({Field} = "value1", {Field} = "value2", ...)
                month_conditions = ', '.join([f'{{Month}} = "{m}"' for m in months])
                employee_conditions = ', '.join([f'{{Employee}} = "{emp}"' for emp in employees])
                
                # Build combined OR conditions
                if len(months) > 1 and len(employees) > 1:
                    formula = f'AND({{RecordType}} = "Monthly Summary", OR({month_conditions}), OR({employee_conditions}))'
                elif len(months) > 1:
                    formula = f'AND({{RecordType}} = "Monthly Summary", OR({month_conditions}), {{Employee}} = "{employees[0]}")'
                elif len(employees) > 1:
                    formula = f'AND({{RecordType}} = "Monthly Summary", {{Month}} = "{months[0]}", OR({employee_conditions}))'
                else:
                    formula = f'AND({{RecordType}} = "Monthly Summary", {{Month}} = "{months[0]}", {{Employee}} = "{employees[0]}")'
                
                try:
                    existing_summaries = table.all(formula=formula)
                    existing_keys = set()
                    for rec in existing_summaries:
                        emp = rec['fields'].get('Employee', '')
                        month = rec['fields'].get('Month', '')
                        if month:
                            existing_keys.add((emp, month))
                    
                    for record in summary_records:
                        emp = record.get('Employee', '')
                        month = record.get('Month', '')
                        if month and (emp, month) in existing_keys:
                            existing_records.append(record)
                        else:
                            new_records.append(record)
                except Exception as e:
                    # If query fails, assume all are new (safer)
                    new_records.extend(summary_records)
        
        return {
            'existing': existing_records,
            'new': new_records,
            'existing_count': len(existing_records),
            'new_count': len(new_records)
        }
    
    def find_record_ids(self, base_id: str, table_name: str, 
                       records: List[Dict]) -> Dict:
        """
        Find Airtable record IDs for given records
        
        Args:
            base_id: Airtable base ID
            table_name: Name of the table
            records: List of records to find IDs for
        
        Returns:
            Dictionary mapping (Employee, Date/Month) to Airtable record ID
        """
        table = self.api.table(base_id, table_name)
        record_id_map = {}
        
        # Group records by type
        daily_records = [r for r in records if r.get('RecordType') == 'Daily']
        summary_records = [r for r in records if r.get('RecordType') == 'Monthly Summary']
        
        # Find daily record IDs
        if daily_records:
            dates = [r.get('Date') for r in daily_records if r.get('Date')]
            if dates:
                min_date = min(dates)
                max_date = max(dates)
                employees = list(set(r.get('Employee') for r in daily_records))
                
                employee_conditions = ', '.join([f'{{Employee}} = "{emp}"' for emp in employees])
                if len(employees) > 1:
                    formula = f'AND({{RecordType}} = "Daily", {{Date}} >= "{min_date}", {{Date}} <= "{max_date}", OR({employee_conditions}))'
                else:
                    formula = f'AND({{RecordType}} = "Daily", {{Date}} >= "{min_date}", {{Date}} <= "{max_date}", {{Employee}} = "{employees[0]}")'
                
                try:
                    existing_daily = table.all(formula=formula)
                    for rec in existing_daily:
                        emp = rec['fields'].get('Employee', '')
                        date = rec['fields'].get('Date', '')
                        if date:
                            if isinstance(date, str):
                                date_str = date[:10]
                            else:
                                date_str = str(date)[:10]
                            record_id_map[('Daily', emp, date_str)] = rec['id']
                except Exception as e:
                    pass
        
        # Find monthly summary record IDs
        if summary_records:
            months = list(set(r.get('Month') for r in summary_records if r.get('Month')))
            if months:
                employees = list(set(r.get('Employee') for r in summary_records))
                
                month_conditions = ', '.join([f'{{Month}} = "{m}"' for m in months])
                employee_conditions = ', '.join([f'{{Employee}} = "{emp}"' for emp in employees])
                
                if len(months) > 1 and len(employees) > 1:
                    formula = f'AND({{RecordType}} = "Monthly Summary", OR({month_conditions}), OR({employee_conditions}))'
                elif len(months) > 1:
                    formula = f'AND({{RecordType}} = "Monthly Summary", OR({month_conditions}), {{Employee}} = "{employees[0]}")'
                elif len(employees) > 1:
                    formula = f'AND({{RecordType}} = "Monthly Summary", {{Month}} = "{months[0]}", OR({employee_conditions}))'
                else:
                    formula = f'AND({{RecordType}} = "Monthly Summary", {{Month}} = "{months[0]}", {{Employee}} = "{employees[0]}")'
                
                try:
                    existing_summaries = table.all(formula=formula)
                    for rec in existing_summaries:
                        emp = rec['fields'].get('Employee', '')
                        month = rec['fields'].get('Month', '')
                        if month:
                            record_id_map[('Monthly Summary', emp, month)] = rec['id']
                except Exception as e:
                    pass
        
        return record_id_map
    
    def update_records(self, base_id: str, table_name: str, 
                      records: List[Dict], record_id_map: Dict) -> Dict:
        """
        Update existing records in Airtable
        
        Args:
            base_id: Airtable base ID
            table_name: Name of the table
            records: List of records to update
            record_id_map: Dictionary mapping (RecordType, Employee, Date/Month) to Airtable record ID
        
        Returns:
            Response from Airtable API
        """
        table = self.api.table(base_id, table_name)
        
        # Prepare update records with IDs
        update_batch = []
        for record in records:
            record_type = record.get('RecordType', '')
            emp = record.get('Employee', '')
            
            # Get the key for this record
            if record_type == 'Daily':
                date = record.get('Date', '')
                if date:
                    key = ('Daily', emp, date)
                    record_id = record_id_map.get(key)
                    if record_id:
                        # Prepare update record
                        update_record = {'id': record_id}
                        fields = {}
                        for k, v in record.items():
                            if k != 'RecordType' and k != 'Employee' and k != 'Date':
                                # Skip empty Date fields
                                if k == 'Date' and (v == '' or v is None):
                                    continue
                                fields[k] = v
                        update_record['fields'] = fields
                        update_batch.append(update_record)
            elif record_type == 'Monthly Summary':
                month = record.get('Month', '')
                if month:
                    key = ('Monthly Summary', emp, month)
                    record_id = record_id_map.get(key)
                    if record_id:
                        # Prepare update record
                        update_record = {'id': record_id}
                        fields = {}
                        for k, v in record.items():
                            if k != 'RecordType' and k != 'Employee' and k != 'Month':
                                # Skip empty Date fields
                                if k == 'Date' and (v == '' or v is None):
                                    continue
                                fields[k] = v
                        update_record['fields'] = fields
                        update_batch.append(update_record)
        
        if not update_batch:
            return {
                'success': True,
                'records_updated': 0,
                'records': [],
                'message': 'No records found to update.'
            }
        
        # Deduplicate by record ID - Airtable rejects "update same record multiple times in one request"
        seen_ids = set()
        deduped_batch = []
        for rec in reversed(update_batch):
            rec_id = rec['id']
            if rec_id not in seen_ids:
                seen_ids.add(rec_id)
                deduped_batch.append(rec)
        deduped_batch.reverse()
        update_batch = deduped_batch
        
        # Batch update records (Airtable allows up to 10 records per batch)
        results = []
        batch_size = 10
        for i in range(0, len(update_batch), batch_size):
            batch = update_batch[i:i + batch_size]
            result = table.batch_update(batch)
            results.extend(result)
        
        return {
            'success': True,
            'records_updated': len(results),
            'records': results,
            'message': f'Successfully updated {len(results)} records.'
        }
    
    def upsert_records(self, base_id: str, table_name: str, 
                      breakdown_data: List[Dict]) -> Dict:
        """
        Upsert records: Update if exists, create if not
        
        Args:
            base_id: Airtable base ID
            table_name: Name of the table
            breakdown_data: List of records to upsert
        
        Returns:
            Response from Airtable API
        """
        # Find existing record IDs
        record_id_map = self.find_record_ids(base_id, table_name, breakdown_data)
        
        # Separate into records to update and records to create
        records_to_update = []
        records_to_create = []
        
        for record in breakdown_data:
            record_type = record.get('RecordType', '')
            emp = record.get('Employee', '')
            
            if record_type == 'Daily':
                date = record.get('Date', '')
                if date:
                    key = ('Daily', emp, date)
                    if key in record_id_map:
                        records_to_update.append(record)
                    else:
                        records_to_create.append(record)
            elif record_type == 'Monthly Summary':
                month = record.get('Month', '')
                if month:
                    key = ('Monthly Summary', emp, month)
                    if key in record_id_map:
                        records_to_update.append(record)
                    else:
                        records_to_create.append(record)
        
        # Update existing records
        update_result = {'records_updated': 0, 'records': []}
        if records_to_update:
            update_result = self.update_records(base_id, table_name, records_to_update, record_id_map)
        
        # Create new records
        create_result = {'records_created': 0, 'records': []}
        if records_to_create:
            create_result = self.append_records(base_id, table_name, records_to_create)
        
        return {
            'success': True,
            'records_updated': update_result.get('records_updated', 0),
            'records_created': create_result.get('records_created', 0),
            'records': update_result.get('records', []) + create_result.get('records', []),
            'message': f"Updated {update_result.get('records_updated', 0)} existing records and created {create_result.get('records_created', 0)} new records."
        }
    
    def update_only_records(self, base_id: str, table_name: str, 
                           breakdown_data: List[Dict]) -> Dict:
        """
        Update ONLY existing records, do not create new ones
        
        Args:
            base_id: Airtable base ID
            table_name: Name of the table
            breakdown_data: List of records to update
        
        Returns:
            Response from Airtable API
        """
        # Find existing record IDs
        record_id_map = self.find_record_ids(base_id, table_name, breakdown_data)
        
        # Only update records that exist
        records_to_update = []
        records_not_found = []
        
        for record in breakdown_data:
            record_type = record.get('RecordType', '')
            emp = record.get('Employee', '')
            
            if record_type == 'Daily':
                date = record.get('Date', '')
                if date:
                    key = ('Daily', emp, date)
                    if key in record_id_map:
                        records_to_update.append(record)
                    else:
                        records_not_found.append(f"{emp} - {date}")
            elif record_type == 'Monthly Summary':
                month = record.get('Month', '')
                if month:
                    key = ('Monthly Summary', emp, month)
                    if key in record_id_map:
                        records_to_update.append(record)
                    else:
                        records_not_found.append(f"{emp} - {month}")
        
        # Update existing records
        if records_to_update:
            update_result = self.update_records(base_id, table_name, records_to_update, record_id_map)
            if records_not_found:
                update_result['not_found'] = records_not_found
                update_result['message'] = f"Updated {update_result.get('records_updated', 0)} records. {len(records_not_found)} records not found in Airtable (not created)."
            return update_result
        else:
            return {
                'success': True,
                'records_updated': 0,
                'records': [],
                'not_found': records_not_found,
                'message': f'No existing records found to update. {len(records_not_found)} records not found in Airtable.'
            }
    
    def append_daily_breakdown(self, base_id: str, table_name: str, 
                              breakdown_data: List[Dict], skip_duplicates: bool = True,
                              update_existing: bool = False, upsert_mode: bool = False) -> Dict:
        """
        Append daily breakdown data to Airtable
        
        Args:
            base_id: Airtable base ID
            table_name: Name of the table
            breakdown_data: List of daily breakdown records
            skip_duplicates: If True, skip records that already exist
            update_existing: If True, update existing records only (no creation)
            upsert_mode: If True, update existing and create new (both)
        
        Returns:
            Response from Airtable API
        """
        if update_existing and not upsert_mode:
            # Update ONLY existing records, don't create new ones
            return self.update_only_records(base_id, table_name, breakdown_data)
        elif upsert_mode:
            # Upsert: update existing, create new
            return self.upsert_records(base_id, table_name, breakdown_data)
        elif skip_duplicates:
            # Check for existing records
            check_result = self.check_existing_records(base_id, table_name, breakdown_data)
            new_records = check_result['new']
            existing_count = check_result['existing_count']
            
            if not new_records:
                return {
                    'success': True,
                    'records_created': 0,
                    'records': [],
                    'skipped': existing_count,
                    'message': f'All {existing_count} records already exist in Airtable. No new records to append.'
                }
            
            # Only append new records
            result = self.append_records(base_id, table_name, new_records)
            result['skipped'] = existing_count
            result['message'] = f"Appended {result['records_created']} new records. Skipped {existing_count} existing records."
            return result
        else:
            # Append all records (original behavior)
            return self.append_records(base_id, table_name, breakdown_data)

    # --- Persistence for Streamlit Cloud: shop targets, daily targets, monthly adjustments ---

    def get_shop_targets(self, base_id: str, table_name: str) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """
        Load shop targets from Airtable. Table must have: Shop, Month, Approved Target.
        Optional: Total Reached. Returns { shop_key: { "YYYY-MM": { "approved_target": float, "total_reached": float } } }.
        """
        table = self.api.table(base_id, table_name)
        try:
            rows = table.all()
        except Exception:
            return {}
        out = {}
        for rec in rows:
            fields = rec.get("fields", {})
            shop = fields.get("Shop") or fields.get("shop")
            month = fields.get("Month") or fields.get("month")
            val = fields.get("Approved Target") or fields.get("approved_target") or 0
            total_reached = fields.get("Total Reached") or fields.get("total_reached") or 0
            if shop and month:
                if shop not in out:
                    out[shop] = {}
                out[shop][str(month)] = {
                    "approved_target": float(val),
                    "total_reached": float(total_reached),
                }
        return out

    def save_shop_targets(self, base_id: str, table_name: str, targets: Dict[str, Dict[str, Dict[str, Any]]]) -> None:
        """
        Save shop targets to Airtable. Table must have: Shop, Month, Approved Target.
        Optional: Total Reached. Upserts by (Shop, Month).
        """
        table = self.api.table(base_id, table_name)
        try:
            existing = table.all()
        except Exception:
            existing = []
        by_key = {
            (r["fields"].get("Shop") or r["fields"].get("shop"), str(r["fields"].get("Month") or r["fields"].get("month") or "")): r
            for r in existing
            if (r["fields"].get("Shop") or r["fields"].get("shop")) and (r["fields"].get("Month") or r["fields"].get("month"))
        }
        to_update = []
        to_create = []
        for shop_key, months in (targets or {}).items():
            for month_key, data in (months or {}).items():
                approved = float((data or {}).get("approved_target") or 0)
                total_reached = float((data or {}).get("total_reached") or 0)
                if approved <= 0 and total_reached <= 0:
                    continue
                key = (shop_key, str(month_key))
                fields = {"Shop": shop_key, "Month": str(month_key), "Approved Target": approved, "Total Reached": total_reached}
                if key in by_key:
                    to_update.append({"id": by_key[key]["id"], "fields": fields})
                else:
                    to_create.append(fields)
        for i in range(0, len(to_update), 10):
            table.batch_update(to_update[i : i + 10])
        for i in range(0, len(to_create), 10):
            table.batch_create(to_create[i : i + 10])

    def get_daily_targets(self, base_id: str, table_name: str) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """
        Load daily targets from Airtable. Table must have: Shop, Date, Staff Working, Staff Targets.
        Staff Working = comma-separated names; Staff Targets = JSON object string.
        Returns same shape as load_daily_targets(): { shop: { "YYYY-MM-DD": { staff_working: [], staff_daily_targets: {} } } }.
        """
        table = self.api.table(base_id, table_name)
        try:
            rows = table.all()
        except Exception:
            return {}
        out = {}
        for rec in rows:
            fields = rec.get("fields", {})
            shop = fields.get("Shop") or fields.get("shop")
            date_str = fields.get("Date") or fields.get("date")
            if isinstance(date_str, str) and len(date_str) >= 10:
                date_str = date_str[:10]
            else:
                date_str = str(date_str)[:10] if date_str else ""
            staff_str = fields.get("Staff Working") or fields.get("staff_working") or ""
            targets_str = fields.get("Staff Targets") or fields.get("staff_targets") or "{}"
            if not shop or not date_str:
                continue
            try:
                staff_list = [s.strip() for s in staff_str.split(",") if s.strip()]
            except Exception:
                staff_list = []
            try:
                targets_dict = json.loads(targets_str) if targets_str else {}
                targets_dict = {k: float(v) for k, v in targets_dict.items()}
            except Exception:
                targets_dict = {}
            sales_str = fields.get("Staff Sales") or fields.get("staff_sales") or "{}"
            try:
                sales_dict = json.loads(sales_str) if sales_str else {}
                sales_dict = {k: float(v) for k, v in sales_dict.items()}
            except Exception:
                sales_dict = {}
            if shop not in out:
                out[shop] = {}
            out[shop][date_str] = {
                "staff_working": staff_list,
                "staff_daily_targets": targets_dict,
                "staff_daily_sales": sales_dict,
            }
        return out

    def save_daily_targets(self, base_id: str, table_name: str, targets: Dict[str, Dict[str, Dict[str, Any]]]) -> None:
        """
        Save daily targets to Airtable. Upserts by (Shop, Date).
        """
        table = self.api.table(base_id, table_name)
        try:
            existing = table.all()
        except Exception:
            existing = []
        by_key = {}
        for r in existing:
            shop = r["fields"].get("Shop") or r["fields"].get("shop")
            d = r["fields"].get("Date") or r["fields"].get("date")
            if d and isinstance(d, str) and len(d) >= 10:
                d = d[:10]
            elif d:
                d = str(d)[:10]
            if shop and d:
                by_key[(shop, d)] = r
        to_update = []
        to_create = []
        for shop_key, dates in (targets or {}).items():
            for date_str, data in (dates or {}).items():
                staff_working = (data or {}).get("staff_working") or []
                staff_targets = (data or {}).get("staff_daily_targets") or {}
                staff_sales = (data or {}).get("staff_daily_sales") or {}
                staff_str = ", ".join(staff_working)
                targets_str = json.dumps(staff_targets)
                sales_str = json.dumps(staff_sales)
                key = (shop_key, date_str)
                fields = {
                    "Shop": shop_key,
                    "Date": date_str,
                    "Staff Working": staff_str,
                    "Staff Targets": targets_str,
                    "Staff Sales": sales_str,
                }
                if key in by_key:
                    to_update.append({"id": by_key[key]["id"], "fields": fields})
                else:
                    to_create.append(fields)
        for i in range(0, len(to_update), 10):
            table.batch_update(to_update[i : i + 10])
        for i in range(0, len(to_create), 10):
            table.batch_create(to_create[i : i + 10])

    def get_monthly_adjustments(
        self, base_id: str, table_name: str, shop_key: str, year: int, month: int
    ) -> Dict[str, Dict[str, Any]]:
        """
        Load monthly adjustments from Airtable. Table must have: Shop, Month, Employee, plus bonus/deduction fields.
        Returns { employee_name: { dailySalesBonus: 0, ... } }.
        """
        table = self.api.table(base_id, table_name)
        month_key = f"{year}-{month:02d}"
        shop_esc = (shop_key or "").replace('\\', '\\\\').replace('"', '\\"')
        month_esc = (month_key or "").replace('\\', '\\\\').replace('"', '\\"')
        try:
            rows = table.all(formula=f'AND({{Shop}} = "{shop_esc}", {{Month}} = "{month_esc}")')
        except Exception:
            return {}
        out = {}
        for rec in rows:
            fields = rec.get("fields", {})
            emp = fields.get("Employee") or fields.get("employee")
            if not emp:
                continue
            out[emp] = {
                "dailySalesBonus": fields.get("Daily Sales Bonus") or fields.get("dailySalesBonus") or 0,
                "firstLastHourBonus": fields.get("First Last Hour Bonus") or fields.get("firstLastHourBonus") or 0,
                "socialMediaBonus": fields.get("Social Media Bonus") or fields.get("socialMediaBonus") or 0,
                "managementBonus": fields.get("Management Bonus") or fields.get("managementBonus") or 0,
                "managementConsistencyBonus": fields.get("Management Consistency Bonus") or fields.get("managementConsistencyBonus") or 0,
                "transportFuel": fields.get("Transport Fuel") or fields.get("transportFuel") or 0,
                "personalSalesBonus": fields.get("Personal Sales Bonus") or fields.get("personalSalesBonus") or 0,
                "extraBonus": fields.get("Extra Bonus") or fields.get("extraBonus") or 0,
                "dailyAllowance": fields.get("Daily Allowance") or fields.get("dailyAllowance") or 0,
                "manualHours": fields.get("Manual Hours") or fields.get("manualHours") or 0,
                "deductions": fields.get("Deductions") or fields.get("deductions") or 0,
                "rent": fields.get("Rent") or fields.get("rent") or 0,
                "advance": fields.get("Advance") or fields.get("advance") or 0,
            }
        return out

    def save_monthly_adjustments(
        self,
        base_id: str,
        table_name: str,
        shop_key: str,
        year: int,
        month: int,
        adjustments: Dict[str, Dict[str, Any]],
    ) -> None:
        """
        Save monthly adjustments to Airtable. Upserts by (Shop, Month, Employee).
        """
        table = self.api.table(base_id, table_name)
        month_key = f"{year}-{month:02d}"
        shop_esc = (shop_key or "").replace('\\', '\\\\').replace('"', '\\"')
        month_esc = (month_key or "").replace('\\', '\\\\').replace('"', '\\"')
        try:
            existing = table.all(formula=f'AND({{Shop}} = "{shop_esc}", {{Month}} = "{month_esc}")')
        except Exception:
            existing = []
        by_emp = {r["fields"].get("Employee") or r["fields"].get("employee"): r for r in existing}
        to_update = []
        to_create = []
        for emp, data in (adjustments or {}).items():
            fields = {
                "Shop": shop_key,
                "Month": month_key,
                "Employee": emp,
                "Daily Sales Bonus": data.get("dailySalesBonus", 0),
                "First Last Hour Bonus": data.get("firstLastHourBonus", 0),
                "Social Media Bonus": data.get("socialMediaBonus", 0),
                "Management Bonus": data.get("managementBonus", 0),
                "Management Consistency Bonus": data.get("managementConsistencyBonus", 0),
                "Transport Fuel": data.get("transportFuel", 0),
                "Personal Sales Bonus": data.get("personalSalesBonus", 0),
                "Extra Bonus": data.get("extraBonus", 0),
                "Daily Allowance": data.get("dailyAllowance", 0),
                "Manual Hours": data.get("manualHours", 0),
                "Deductions": data.get("deductions", 0),
                "Rent": data.get("rent", 0),
                "Advance": data.get("advance", 0),
            }
            if emp in by_emp:
                to_update.append({"id": by_emp[emp]["id"], "fields": fields})
            else:
                to_create.append(fields)
        for i in range(0, len(to_update), 10):
            table.batch_update(to_update[i : i + 10])
        for i in range(0, len(to_create), 10):
            table.batch_create(to_create[i : i + 10])
