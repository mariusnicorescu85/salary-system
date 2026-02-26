"""
Data Processing Module
Handles CSV parsing and data transformation
"""

import pandas as pd
from typing import List, Dict, Optional
from datetime import datetime
import re
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DataProcessor:
    """Processes raw CSV data into structured format"""
    
    def __init__(self, name_mapping: Optional[Dict[str, str]] = None, 
                 exclude_patterns: Optional[List[str]] = None):
        self.name_mapping = name_mapping or {}
        self.exclude_patterns = exclude_patterns or []
        self._logged_mappings = set()  # Track which employees have been logged
    
    def excel_date_to_js_date(self, serial: float) -> str:
        """Convert Excel serial date to ISO date string"""
        try:
            utc_days = int(serial - 25569)
            utc_value = utc_days * 86400
            date_info = datetime.fromtimestamp(utc_value)
            return date_info.strftime('%Y-%m-%d')
        except:
            return None
    
    def excel_time_to_string(self, time: float) -> str:
        """Convert Excel time to HH:MM string"""
        try:
            total_seconds = round(time * 24 * 60 * 60)
            hours = str(int(total_seconds // 3600)).zfill(2)
            minutes = str(int((total_seconds % 3600) // 60)).zfill(2)
            return f"{hours}:{minutes}"
        except:
            return ""
    
    def smart_date_parser(self, value) -> Optional[str]:
        """Smart date parser for various formats"""
        if not value or value == "":
            return None
        
        # Excel serial date
        if isinstance(value, (int, float)) and 30000 < value < 60000:
            return self.excel_date_to_js_date(value)
        
        # String date formats
        if isinstance(value, str):
            value = value.strip()
            
            # Try ISO format YYYY-MM-DD first (most common in CSV exports)
            iso_match = re.match(r'^(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})$', value)
            if iso_match:
                year, month, day = iso_match.groups()
                year = int(year)
                month = int(month)
                day = int(day)
                
                if 2000 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31:
                    try:
                        date = datetime(year, month, day)
                        return date.strftime('%Y-%m-%d')
                    except Exception as e:
                        logger.debug(f"Date parsing error for ISO format '{value}': {e}")
                        pass
            
            # Try DD/MM/YYYY or DD-MM-YYYY
            date_match = re.match(r'^(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})$', value)
            if date_match:
                day, month, year = date_match.groups()
                year = int(year)
                if year < 100:
                    year += 2000 if year < 50 else 1900
                
                if 2000 <= year <= 2100 and 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
                    try:
                        date = datetime(year, int(month), int(day))
                        return date.strftime('%Y-%m-%d')
                    except Exception as e:
                        logger.debug(f"Date parsing error for DD/MM/YYYY format '{value}': {e}")
                        pass
        
        return None
    
    def map_employee_name(self, original_name: str) -> Optional[str]:
        """
        Map employee name using configured mapping
        Matches the n8n workflow logic exactly:
        1. Check direct mapping (case-sensitive)
        2. Check case-insensitive mapping
        3. Check if name contains any mapped key (only for keys > 3 chars)
        4. Return original if no mapping found
        Returns None if name should be excluded, otherwise returns mapped name
        """
        if not original_name or not isinstance(original_name, str):
            return None
        
        trimmed = original_name.strip()
        if not trimmed:
            return None
        
        lower_trimmed = trimmed.lower()
        
        # Check if name should be excluded (case-insensitive contains check)
        for pattern in self.exclude_patterns:
            if pattern.lower() in lower_trimmed:
                logger.debug(f"⚠️ EXCLUDING: '{trimmed}' - matches exclude pattern '{pattern}'")
                return None  # Exclude this name
        
        # Step 1: Check direct mapping (exact match, case-sensitive first)
        if trimmed in self.name_mapping:
            mapped = self.name_mapping[trimmed]
            if trimmed not in self._logged_mappings:
                logger.info(f"✅ MAPPED (direct): '{trimmed}' → '{mapped}'")
                self._logged_mappings.add(trimmed)
            return mapped
        
        
        # Step 2: Check case-insensitive mapping
        if lower_trimmed in self.name_mapping:
            mapped = self.name_mapping[lower_trimmed]
            if trimmed not in self._logged_mappings:
                logger.info(f"✅ MAPPED (case-insensitive): '{trimmed}' → '{mapped}'")
                self._logged_mappings.add(trimmed)
            return mapped
        
        # Step 3: Check if trimmed name contains any mapped keys (only for keys > 3 chars)
        # This matches the n8n logic: "if (key.length > 3 && trimmedName.toLowerCase().includes(key.toLowerCase()))"
        # We iterate through all keys and return the first match (n8n also returns first match)
        for key, value in self.name_mapping.items():
            key_lower = key.lower()
            # Only check for keys longer than 3 characters (matching n8n logic exactly)
            if len(key) > 3 and key_lower in lower_trimmed:
                if trimmed not in self._logged_mappings:
                    logger.info(f"✅ MAPPED (contains): '{trimmed}' → '{value}' (matched key '{key}')")
                    self._logged_mappings.add(trimmed)
                return value
            # Debug: log why "Dave" key isn't matching "Dave D"
            if trimmed == "Dave D" and key == "Dave":
                logger.info(f"🔍 DEBUG: key='{key}' (len={len(key)}), key_lower='{key_lower}', lower_trimmed='{lower_trimmed}', contains={key_lower in lower_trimmed}")
        
        # Split name into parts and check if first part (or any part) matches a mapping key
        # This handles cases like "Abbas Khizar" where "Abbas" should map to "Khizar"
        name_parts = trimmed.split()
        for part in name_parts:
            part_lower = part.lower()
            # Check exact match (case-sensitive)
            if part in self.name_mapping:
                mapped = self.name_mapping[part]
                if trimmed not in self._logged_mappings:
                    logger.info(f"✅ MAPPED (part): '{trimmed}' → '{mapped}' (matched part '{part}')")
                    self._logged_mappings.add(trimmed)
                return mapped
            # Check case-insensitive match
            if part_lower in self.name_mapping:
                mapped = self.name_mapping[part_lower]
                if trimmed not in self._logged_mappings:
                    logger.info(f"✅ MAPPED (part, case): '{trimmed}' → '{mapped}' (matched part '{part}')")
                    self._logged_mappings.add(trimmed)
                return mapped
        
        # For shorter keys (1-3 chars), check if they match as complete words
        for key, value in self.name_mapping.items():
            key_lower = key.lower()
            if len(key) <= 3:
                # Check if key matches as a complete word (with word boundaries)
                pattern = r'\b' + re.escape(key_lower) + r'\b'
                if re.search(pattern, lower_trimmed):
                    if trimmed not in self._logged_mappings:
                        logger.debug(f"✅ MAPPED (word boundary): '{trimmed}' → '{value}' (matched key '{key}')")
                        self._logged_mappings.add(trimmed)
                    return value
        
        # If no mapping found, return original (keep it)
        if trimmed not in self._logged_mappings:
            logger.info(f"❓ NO MAPPING: '{trimmed}' - keeping original (checked {len(self.name_mapping)} mappings)")
            self._logged_mappings.add(trimmed)
        return trimmed
    
    def parse_csv(self, df: pd.DataFrame) -> List[Dict]:
        """Parse CSV data into structured records"""
        logger.info(f"=== Starting CSV Parsing ===")
        logger.info(f"DataFrame shape: {df.shape} (rows x columns)")
        
        # Check if this is a raw CSV (no headers, numeric column indices)
        is_raw_csv = df.columns.dtype == 'int64' or all(isinstance(col, int) for col in df.columns)
        
        if is_raw_csv:
            logger.info("Detected raw CSV (no headers) - using section-based parsing")
            return self._parse_sectioned_csv(df)
        
        # Otherwise, check for standard columns
        df_columns_lower = [str(col).lower().strip() for col in df.columns]
        logger.info(f"Columns: {df_columns_lower}")
        
        has_standard_columns = any(col in df_columns_lower for col in ['date', 'employee', 'hours', 'sales'])
        logger.info(f"Has standard columns: {has_standard_columns}")
        
        if has_standard_columns:
            logger.info("Using standard CSV parsing approach")
            mapping_stats = {
                'total_processed': 0,
                'mapped': 0,
                'excluded': 0,
                'mapping_details': {},
                'debug_info': []
            }
            return self._parse_standard_csv(df, mapping_stats)
        
        # Fallback to row-by-row parsing
        logger.info("Using row-by-row parsing approach (looking for Employee: markers)")
        return self._parse_row_by_row(df)
    
    def _parse_sectioned_csv(self, df: pd.DataFrame) -> List[Dict]:
        """Parse CSV with employee sections (Employee: row, empty row, headers, data)"""
        logger.info("=== Parsing Sectioned CSV ===")
        cleaned = []
        mapping_stats = {
            'total_processed': 0,
            'mapped': 0,
            'excluded': 0,
            'mapping_details': {},
            'debug_info': []
        }
        
        current_employee = None
        column_headers = {}
        in_data_section = False
        
        for row_num, (idx, row) in enumerate(df.iterrows()):
            # Convert row to list, handling NaN values
            row_values = [str(val).strip() if pd.notna(val) else '' for val in row.values]
            
            if row_num < 10:
                logger.debug(f"Row {row_num}: {row_values[:5]}")
            
            # Check for employee header row (usually has "Employee:" in first column)
            if len(row_values) > 0 and row_values[0] and 'Employee:' in str(row_values[0]):
                # Extract employee name
                employee_part = str(row_values[0]).replace('Employee:', '').strip()
                if len(row_values) > 1 and row_values[1]:
                    # Combine first and second column for full name
                    new_employee = f"{employee_part} {row_values[1]}".strip()
                else:
                    new_employee = employee_part
                
                # If we were processing a previous employee, log it
                if current_employee and in_data_section:
                    logger.info(f"Row {row_num}: Ending section for previous employee '{current_employee}' (found new employee '{new_employee}')")
                
                current_employee = new_employee
                logger.info(f"Found employee section at row {row_num}: '{current_employee}'")
                in_data_section = False
                column_headers = {}
                continue
            
            # Skip empty rows
            if not any(row_values) or all(not val or str(val).strip() == '' for val in row_values):
                if in_data_section and current_employee:
                    # Empty row after data section - end of employee section
                    logger.debug(f"Row {row_num}: Empty row, ending section for {current_employee}")
                    current_employee = None
                    in_data_section = False
                continue
            
            # Check for header row (contains "Date" in first column, case-insensitive)
            first_val = str(row_values[0]).strip().lower() if row_values[0] else ''
            
            # Debug: Check if we should be processing this row (before header check)
            if row_num < 20 and first_val != 'date':
                logger.debug(f"Row {row_num}: in_data_section={in_data_section}, current_employee={current_employee}, has_headers={len(column_headers) > 0}, first_val='{row_values[0] if row_values else 'N/A'}'")
            
            if first_val == 'date':
                logger.info(f"Found header row at row {row_num}: {row_values[:5]}")
                logger.info(f"  Current employee: {current_employee}, in_data_section: {in_data_section}")
                # Map column positions to header names
                column_headers = {}
                for col_idx, header_val in enumerate(row_values):
                    if header_val and str(header_val).strip():
                        header_name = str(header_val).strip()
                        column_headers[header_name] = col_idx
                logger.info(f"Column headers detected ({len(column_headers)}): {list(column_headers.keys())[:8]}")
                in_data_section = True
                logger.info(f"  Set in_data_section=True, current_employee={current_employee}")
                continue
            
            # Debug: Log state for data rows
            if row_num < 20 and not (row_values[0] and 'Employee:' in str(row_values[0])) and first_val != 'date':
                logger.debug(f"Row {row_num}: Checking if data row - in_data_section={in_data_section}, current_employee={current_employee}, has_headers={len(column_headers) > 0}, first_val='{row_values[0] if row_values else 'N/A'}'")
            
            # If we have headers and an employee, process data row
            if in_data_section and current_employee and column_headers:
                if row_num < 10:
                    logger.info(f"Row {row_num}: Processing as data row for {current_employee}")
                    logger.info(f"  Row values: {row_values[:5]}")
                # Extract data using column headers
                try:
                    # Get date - try 'Date' header first, then first column
                    date_col_idx = column_headers.get('Date', 0)
                    if date_col_idx < len(row_values):
                        date_val = row_values[date_col_idx]
                    else:
                        date_val = row_values[0] if len(row_values) > 0 else None
                    
                    if row_num < 10:
                        logger.info(f"  Date extraction: date_col_idx={date_col_idx}, date_val='{date_val}'")
                    
                    if not date_val or str(date_val).strip() == '':
                        if row_num < 20:
                            logger.warning(f"Row {row_num}: No date value found (date_col_idx={date_col_idx}, row_values length={len(row_values)})")
                        continue
                    
                    parsed_date = self.smart_date_parser(date_val)
                    
                    if not parsed_date:
                        if row_num < 20:
                            logger.warning(f"Row {row_num}: Could not parse date '{date_val}' (type: {type(date_val)})")
                        continue
                    
                    if row_num < 10:
                        logger.info(f"  ✓ Parsed date = {parsed_date} from '{date_val}'")
                    
                    # Extract hours
                    hours_key = column_headers.get('Hours', 4)
                    hours = 0.0
                    if hours_key < len(row_values):
                        try:
                            hours_val = row_values[hours_key]
                            if row_num < 10:
                                logger.info(f"  Hours extraction: hours_key={hours_key}, hours_val='{hours_val}' (type: {type(hours_val)})")
                            if hours_val and str(hours_val).strip():
                                hours = float(hours_val)
                                if row_num < 10:
                                    logger.info(f"  ✓ Parsed hours = {hours}")
                        except (ValueError, TypeError) as e:
                            if row_num < 10:
                                logger.warning(f"Row {row_num}: Error parsing hours '{row_values[hours_key] if hours_key < len(row_values) else 'N/A'}': {e}")
                            pass
                    else:
                        if row_num < 10:
                            logger.warning(f"  Hours key {hours_key} >= row length {len(row_values)}")
                    
                    if hours <= 0:
                        if row_num < 20:
                            logger.warning(f"Row {row_num}: Hours <= 0 ({hours}), skipping. hours_key={hours_key}, value='{row_values[hours_key] if hours_key < len(row_values) else 'N/A'}'")
                        continue
                    
                    if row_num < 10:
                        logger.info(f"  ✓ Valid data row - Employee: {current_employee}, Date: {parsed_date}, Hours: {hours}")
                    
                    # Extract other fields
                    location = row_values[column_headers.get('Location', 1)] if 'Location' in column_headers and column_headers.get('Location', 1) < len(row_values) else ''
                    time_in = row_values[column_headers.get('Time In', 2)] if 'Time In' in column_headers and column_headers.get('Time In', 2) < len(row_values) else ''
                    time_out = row_values[column_headers.get('Time Out', 3)] if 'Time Out' in column_headers and column_headers.get('Time Out', 3) < len(row_values) else ''
                    
                    lunch_key = column_headers.get('Lunch', 5)
                    lunch = float(row_values[lunch_key]) if lunch_key < len(row_values) and row_values[lunch_key] else 0.0
                    
                    sales_goal_key = column_headers.get('Sales Goal', 6)
                    sales_goal = float(row_values[sales_goal_key]) if sales_goal_key < len(row_values) and row_values[sales_goal_key] else 0.0
                    
                    sales_key = column_headers.get('Sales', 7)
                    sales = float(row_values[sales_key]) if sales_key < len(row_values) and row_values[sales_key] else 0.0
                    
                    addl_sales_key = column_headers.get("Add'l Sales", column_headers.get('Addl Sales', 8))
                    addl_sales = float(row_values[addl_sales_key]) if addl_sales_key < len(row_values) and row_values[addl_sales_key] else 0.0
                    
                    hrly_rate_key = column_headers.get('Hrly Rate', column_headers.get('HrlyRate', 9))
                    hrly_rate = float(row_values[hrly_rate_key]) if hrly_rate_key < len(row_values) and row_values[hrly_rate_key] else 0.0
                    
                    base_key = column_headers.get('Base', 10)
                    base = float(row_values[base_key]) if base_key < len(row_values) and row_values[base_key] else 0.0
                    
                    # Map employee name
                    mapping_stats['total_processed'] += 1
                    mapped_name = self.map_employee_name(current_employee)
                    
                    if mapped_name is None:
                        mapping_stats['excluded'] += 1
                        continue
                    
                    if mapped_name != current_employee:
                        mapping_stats['mapped'] += 1
                        if current_employee not in mapping_stats['mapping_details']:
                            mapping_stats['mapping_details'][current_employee] = mapped_name
                    
                    record = {
                        'Employee': mapped_name,
                        'Date': parsed_date,
                        'TimeIn': time_in,
                        'TimeOut': time_out,
                        'Hours': hours,
                        'Lunch': lunch,
                        'SalesGoal': sales_goal,
                        'Sales': sales,
                        'AddlSales': addl_sales,
                        'HrlyRate': hrly_rate,
                        'Base': base
                    }
                    cleaned.append(record)
                    
                    if row_num < 10:
                        logger.info(f"  ✓ Record created: Employee={mapped_name}, Date={parsed_date}, Hours={hours}, Sales={sales}")
                
                except Exception as e:
                    if row_num < 10:
                        logger.error(f"Row {row_num}: Error processing row: {e}", exc_info=True)
                    continue
        
        logger.info(f"Sectioned CSV parsing complete: {len(cleaned)} records created")
        self.mapping_stats = mapping_stats
        return cleaned
    
    def _parse_row_by_row(self, df: pd.DataFrame) -> List[Dict]:
        """Original row-by-row parsing for CSV with headers"""
        cleaned = []
        current_employee = None
        column_headers = {}
        mapping_stats = {
            'total_processed': 0,
            'mapped': 0,
            'excluded': 0,
            'mapping_details': {},
            'debug_info': []
        }
        
        logger.info(f"Total rows to process: {len(df)}")
        
        for row_num, (idx, row) in enumerate(df.iterrows()):
            if row_num == 0:
                logger.info(f"Row 0 sample: {row.to_dict()}")
            
            row_dict = row.to_dict()
            keys = list(row_dict.keys())
            
            if len(keys) == 0:
                if row_num < 5:
                    logger.debug(f"Row {row_num}: Empty row, skipping")
                continue
            
            first_col = row_dict.get(keys[0])
            second_col = row_dict.get(keys[1]) if len(keys) > 1 else None
            
            if row_num < 5:
                logger.debug(f"Row {row_num}: first_col={first_col}, second_col={second_col}, keys={keys[:3]}")
            
            # Check for employee header in column name
            first_col_name = keys[0] if keys else None
            if first_col_name and 'Employee:' in first_col_name and not current_employee:
                employee_part = first_col_name.replace('Employee:', '').strip()
                if ',' in employee_part:
                    parts = employee_part.split(',')
                    current_employee = ' '.join([p.strip() for p in parts])
                else:
                    current_employee = employee_part
                logger.info(f"Found employee in column name (row {row_num}): '{current_employee}'")
                continue
            
            # Check for employee header in cell value
            if first_col and isinstance(first_col, str) and first_col.startswith('Employee:'):
                employee_part = first_col.replace('Employee:', '').strip()
                if ',' in employee_part:
                    parts = employee_part.split(',')
                    current_employee = ' '.join([p.strip() for p in parts])
                else:
                    current_employee = employee_part if second_col is None else f"{employee_part} {second_col}".strip()
                logger.info(f"Found employee in cell value (row {row_num}): '{current_employee}'")
                column_headers = {}
                continue
            
            if not current_employee:
                if row_num < 10:
                    logger.debug(f"Row {row_num}: No current employee set, skipping")
                continue
            
            # Check for column header row
            if first_col == 'Date' or (first_col and str(first_col).lower() == 'date'):
                logger.info(f"Found header row at row {row_num}")
                for key in keys:
                    header_value = row_dict.get(key)
                    if header_value and header_value != '':
                        column_headers[header_value] = key
                logger.info(f"Column headers detected: {list(column_headers.keys())[:5]}")
                continue
            
            # Skip empty rows
            if not first_col or first_col == '':
                continue
            
            # Parse date
            parsed_date = self.smart_date_parser(first_col)
            if not parsed_date:
                if row_num < 10:
                    logger.debug(f"Row {row_num}: Could not parse date from '{first_col}'")
                continue
            
            if row_num < 5:
                logger.debug(f"Row {row_num}: Parsed date = {parsed_date}")
            
            # Extract hours
            hours_key = column_headers.get('Hours', keys[4] if len(keys) > 4 else None)
            hours = 0.0
            if hours_key:
                try:
                    hours = float(row_dict.get(hours_key, 0))
                except Exception as e:
                    if row_num < 5:
                        logger.debug(f"Row {row_num}: Error parsing hours: {e}")
                    pass
            
            if hours <= 0:
                if row_num < 10:
                    logger.debug(f"Row {row_num}: Hours <= 0 ({hours}), skipping")
                continue
            
            # Extract other fields
            location = column_headers.get('Location', second_col)
            time_in_key = column_headers.get('Time In', keys[2] if len(keys) > 2 else None)
            time_out_key = column_headers.get('Time Out', keys[3] if len(keys) > 3 else None)
            lunch_key = column_headers.get('Lunch', keys[5] if len(keys) > 5 else None)
            sales_goal_key = column_headers.get('Sales Goal', keys[6] if len(keys) > 6 else None)
            sales_key = column_headers.get('Sales', keys[7] if len(keys) > 7 else None)
            addl_sales_key = column_headers.get("Add'l Sales", column_headers.get('Addl Sales', keys[8] if len(keys) > 8 else None))
            hrly_rate_key = column_headers.get('Hrly Rate', keys[9] if len(keys) > 9 else None)
            base_key = column_headers.get('Base', keys[10] if len(keys) > 10 else None)
            
            time_in = row_dict.get(time_in_key, '') if time_in_key else ''
            time_out = row_dict.get(time_out_key, '') if time_out_key else ''
            
            if isinstance(time_in, (int, float)):
                time_in = self.excel_time_to_string(time_in)
            if isinstance(time_out, (int, float)):
                time_out = self.excel_time_to_string(time_out)
            
            lunch = float(row_dict.get(lunch_key, 0)) if lunch_key else 0.0
            sales_goal = float(row_dict.get(sales_goal_key, 0)) if sales_goal_key else 0.0
            sales = float(row_dict.get(sales_key, 0)) if sales_key else 0.0
            addl_sales = float(row_dict.get(addl_sales_key, 0)) if addl_sales_key else 0.0
            hrly_rate = float(row_dict.get(hrly_rate_key, 0)) if hrly_rate_key else 0.0
            base = float(row_dict.get(base_key, 0)) if base_key else 0.0
            
            # Map employee name
            mapping_stats['total_processed'] += 1
            mapped_name = self.map_employee_name(current_employee)
            
            # Skip if name was excluded (returns None)
            if mapped_name is None:
                mapping_stats['excluded'] += 1
                if row_num < 10:
                    logger.debug(f"Row {row_num}: Employee '{current_employee}' excluded")
                continue
            
            # Track mapping if name changed
            if mapped_name != current_employee:
                mapping_stats['mapped'] += 1
                if current_employee not in mapping_stats['mapping_details']:
                    mapping_stats['mapping_details'][current_employee] = mapped_name
                if row_num < 5:
                    logger.info(f"Row {row_num}: Mapped '{current_employee}' → '{mapped_name}'")
            
            # Only add if we have a valid employee name
            if mapped_name:
                record = {
                    'Employee': mapped_name,
                    'Date': parsed_date,
                    'TimeIn': time_in,
                    'TimeOut': time_out,
                    'Hours': hours,
                    'Lunch': lunch,
                    'SalesGoal': sales_goal,
                    'Sales': sales,
                    'AddlSales': addl_sales,
                    'HrlyRate': hrly_rate,
                    'Base': base
                }
                cleaned.append(record)
                if len(cleaned) <= 5:
                    logger.info(f"Row {row_num}: Created record for {mapped_name} on {parsed_date} ({hours} hours, £{sales} sales)")
        
        logger.info(f"=== Row-by-row Parsing Complete ===")
        logger.info(f"Total records created: {len(cleaned)}")
        logger.info(f"Rows processed: {mapping_stats['total_processed']}")
        logger.info(f"Names mapped: {mapping_stats['mapped']}")
        logger.info(f"Names excluded: {mapping_stats['excluded']}")
        
        if len(cleaned) == 0 and len(df) > 0:
            logger.warning("No records created! Debugging...")
            mapping_stats['debug_info'].append(f"Processed {mapping_stats['total_processed']} rows but found 0 valid records")
            mapping_stats['debug_info'].append(f"CSV has {len(df)} rows and {len(df.columns)} columns")
            mapping_stats['debug_info'].append(f"Columns: {list(df.columns)}")
            if mapping_stats['total_processed'] == 0:
                mapping_stats['debug_info'].append("No employee headers found - check if file has 'Employee:' markers")
                logger.warning("No employee headers found in file")
        
        self.mapping_stats = mapping_stats
        return cleaned
    
    def _parse_standard_csv(self, df: pd.DataFrame, mapping_stats: Dict) -> List[Dict]:
        """Parse CSV with standard column structure"""
        logger.info("=== Using Standard CSV Parser ===")
        cleaned = []
        df_columns = {str(col).lower().strip(): col for col in df.columns}
        logger.info(f"Column mapping: {df_columns}")
        
        # Map column names (case-insensitive)
        date_col = None
        employee_col = None
        hours_col = None
        sales_col = None
        addl_sales_col = None
        hrly_rate_col = None
        
        # Find date column
        for key in ['date', 'dates']:
            if key in df_columns:
                date_col = df_columns[key]
                break
        
        # Find employee column
        for key in ['employee', 'employees', 'name', 'names', 'staff']:
            if key in df_columns:
                employee_col = df_columns[key]
                break
        
        # Find hours column
        for key in ['hours', 'hour', 'hrs', 'hr']:
            if key in df_columns:
                hours_col = df_columns[key]
                break
        
        # Find sales column
        for key in ['sales', 'sale', 'total sales']:
            if key in df_columns:
                sales_col = df_columns[key]
                break
        
        # Find additional sales column
        for key in ["add'l sales", "addl sales", "additional sales", "addl", "additional"]:
            if key in df_columns:
                addl_sales_col = df_columns[key]
                break
        
        # Find hourly rate column
        for key in ['hrly rate', 'hourly rate', 'rate', 'rate per hour']:
            if key in df_columns:
                hrly_rate_col = df_columns[key]
                break
        
        if not date_col or not hours_col:
            logger.warning(f"Standard CSV format not detected - missing date_col={date_col}, hours_col={hours_col}")
            mapping_stats['debug_info'].append("Standard CSV format not detected - using row-by-row parsing")
            return []
        
        logger.info(f"Detected columns - Date: {date_col}, Employee: {employee_col}, Hours: {hours_col}, Sales: {sales_col}")
        
        # Process each row
        logger.info(f"Processing {len(df)} rows...")
        for row_num, (idx, row) in enumerate(df.iterrows()):
            try:
                # Get date
                date_val = row[date_col] if date_col else None
                parsed_date = self.smart_date_parser(date_val)
                if not parsed_date:
                    if row_num < 5:
                        logger.debug(f"Row {row_num}: Could not parse date '{date_val}'")
                    continue
                
                # Get employee
                if employee_col:
                    employee_name = str(row[employee_col]).strip() if pd.notna(row[employee_col]) else None
                else:
                    # Try to find employee in other columns or use current_employee
                    employee_name = None
                    for col in df.columns:
                        val = str(row[col]).strip() if pd.notna(row[col]) else ""
                        if val and ("employee" in str(col).lower() or len(val) > 3):
                            # Check if it looks like a name
                            if not val.replace(" ", "").replace("-", "").isdigit():
                                employee_name = val
                                break
                
                if not employee_name:
                    continue
                
                # Map employee name
                mapping_stats['total_processed'] += 1
                mapped_name = self.map_employee_name(employee_name)
                
                if mapped_name is None:
                    mapping_stats['excluded'] += 1
                    continue
                
                if mapped_name != employee_name:
                    mapping_stats['mapped'] += 1
                    if employee_name not in mapping_stats['mapping_details']:
                        mapping_stats['mapping_details'][employee_name] = mapped_name
                
                # Get hours
                hours = 0.0
                if hours_col:
                    try:
                        hours = float(row[hours_col]) if pd.notna(row[hours_col]) else 0.0
                    except:
                        hours = 0.0
                
                if hours <= 0:
                    continue
                
                # Get sales
                sales = 0.0
                if sales_col:
                    try:
                        sales = float(row[sales_col]) if pd.notna(row[sales_col]) else 0.0
                    except:
                        sales = 0.0
                
                # Get additional sales
                addl_sales = 0.0
                if addl_sales_col:
                    try:
                        addl_sales = float(row[addl_sales_col]) if pd.notna(row[addl_sales_col]) else 0.0
                    except:
                        addl_sales = 0.0
                
                # Get hourly rate
                hrly_rate = 0.0
                if hrly_rate_col:
                    try:
                        hrly_rate = float(row[hrly_rate_col]) if pd.notna(row[hrly_rate_col]) else 0.0
                    except:
                        hrly_rate = 0.0
                
                cleaned.append({
                    'Employee': mapped_name,
                    'Date': parsed_date,
                    'TimeIn': '',
                    'TimeOut': '',
                    'Hours': hours,
                    'Lunch': 0.0,
                    'SalesGoal': 0.0,
                    'Sales': sales,
                    'AddlSales': addl_sales,
                    'HrlyRate': hrly_rate,
                    'Base': 0.0
                })
            except Exception as e:
                # Skip rows that cause errors
                continue
        
        logger.info(f"Standard CSV parser: Created {len(cleaned)} records")
        mapping_stats['debug_info'].append(f"Parsed {len(cleaned)} records using standard CSV format")
        self.mapping_stats = mapping_stats
        return cleaned
