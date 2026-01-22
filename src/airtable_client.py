"""
Airtable Client
Handles appending data to Airtable
"""

from pyairtable import Api
from typing import List, Dict, Optional
import os


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
