# 📊 Airtable Data Retrieval Guide

## Problem: Monthly Summaries Without Dates

Monthly summary records don't have a `Date` field (it's empty), which makes it difficult to:
- Query summaries by month/year
- Filter records for a specific period
- Link summaries to their corresponding month
- Group and sort by time period

## ✅ Solution: Month Fields

The system now automatically adds **two month fields** to monthly summary records:

### 1. `Month` Field (Format: "2024-11")
- **Type**: Single line text
- **Format**: `YYYY-MM` (e.g., "2024-11", "2024-12")
- **Purpose**: Easy filtering and querying
- **Example**: "2024-11" for November 2024

### 2. `MonthYear` Field (Format: "November 2024")
- **Type**: Single line text
- **Format**: `MonthName YYYY` (e.g., "November 2024", "December 2024")
- **Purpose**: Human-readable display
- **Example**: "November 2024"

## 🔍 How to Query Data Consistently

### Option 1: Filter by Month Field

**In Airtable:**
1. Create a view filtered by `Month = "2024-11"`
2. Group by `Employee`
3. Sort by `FinalPayment` (descending)

**Using Airtable API:**
```python
# Filter monthly summaries for November 2024
filter_formula = "AND({RecordType} = 'Monthly Summary', {Month} = '2024-11')"
records = table.all(formula=filter_formula)
```

**Using Airtable Formula:**
```
AND({RecordType} = "Monthly Summary", {Month} = "2024-11")
```

### Option 2: Filter by MonthYear Field

**In Airtable:**
1. Create a view filtered by `MonthYear = "November 2024"`
2. Group by `Employee`

**Using Airtable API:**
```python
# Filter monthly summaries for November 2024
filter_formula = "AND({RecordType} = 'Monthly Summary', {MonthYear} = 'November 2024')"
records = table.all(formula=filter_formula)
```

### Option 3: Filter by Employee and Month

**In Airtable:**
```
AND(
  {RecordType} = "Monthly Summary",
  {Employee} = "John Smith",
  {Month} = "2024-11"
)
```

**Using Airtable API:**
```python
filter_formula = """
AND(
  {RecordType} = "Monthly Summary",
  {Employee} = "John Smith",
  {Month} = "2024-11"
)
"""
records = table.all(formula=filter_formula)
```

## 📅 Linking Daily Records to Monthly Summaries

### Strategy 1: Use Month Field to Match

1. **Get monthly summary:**
   - Filter: `RecordType = "Monthly Summary"` AND `Employee = "John"` AND `Month = "2024-11"`

2. **Get corresponding daily records:**
   - Filter: `RecordType = "Daily"` AND `Employee = "John"` AND `Date >= "2024-11-01"` AND `Date <= "2024-11-30"`

### Strategy 2: Use Date Range

```python
from datetime import datetime

# Get month from summary
month_str = "2024-11"  # From monthly summary
year, month = month_str.split('-')

# Get daily records for that month
start_date = f"{year}-{month}-01"
# Calculate last day of month
if month == '12':
    end_date = f"{int(year)+1}-01-01"
else:
    next_month = int(month) + 1
    end_date = f"{year}-{next_month:02d}-01"

# Query daily records
daily_filter = f"""
AND(
  {{RecordType}} = "Daily",
  {{Employee}} = "John Smith",
  IS_AFTER({{Date}}, "{start_date}"),
  IS_BEFORE({{Date}}, "{end_date}")
)
"""
```

## 🎯 Recommended Airtable Views

### View 1: Monthly Summaries by Period
- **Filter**: `RecordType = "Monthly Summary"`
- **Group by**: `Month` (or `MonthYear`)
- **Sort by**: `Month` (ascending), then `Employee` (ascending)
- **Fields**: Employee, MonthYear, FinalPayment, TotalBonus, etc.

### View 2: Employee Monthly History
- **Filter**: `RecordType = "Monthly Summary"` AND `Employee = "[Selected Employee]"`
- **Sort by**: `Month` (descending)
- **Fields**: MonthYear, WorkedDays, WorkedHours, Sales, FinalPayment

### View 3: Current Month Summary
- **Filter**: `RecordType = "Monthly Summary"` AND `Month = "2024-11"` (update monthly)
- **Group by**: `Employee`
- **Fields**: All summary fields

### View 4: Daily + Summary Combined
- **Filter**: `Employee = "[Selected Employee]"` AND `Month = "2024-11"`
- **Group by**: `RecordType`
- **Fields**: Date (for daily), MonthYear (for summary), Hours, Sales, FinalPayment

## 📋 Airtable Table Structure Update

Add these fields to your Airtable table:

### New Fields for Monthly Summaries:
- **`Month`** (Single line text)
  - Format: "2024-11"
  - Used for filtering and querying
  
- **`MonthYear`** (Single line text)
  - Format: "November 2024"
  - Used for display

### Example Record Structure:

**Daily Record:**
```
RecordType: "Daily"
Employee: "John Smith"
Date: "2024-11-15"
Hours: 8.0
Sales: 550.00
...
```

**Monthly Summary Record:**
```
RecordType: "Monthly Summary"
Employee: "John Smith"
Date: (empty)
Month: "2024-11"
MonthYear: "November 2024"
WorkedDays: 22
WorkedHours: 176.50
FinalPayment: 5154.25
...
```

## 🔄 Data Retrieval Patterns

### Pattern 1: Get All Summaries for a Month
```python
def get_monthly_summaries(table, month="2024-11"):
    """Get all monthly summaries for a specific month"""
    formula = f'AND({{RecordType}} = "Monthly Summary", {{Month}} = "{month}")'
    return table.all(formula=formula)
```

### Pattern 2: Get Employee Summary for a Month
```python
def get_employee_monthly_summary(table, employee, month="2024-11"):
    """Get a specific employee's monthly summary"""
    formula = f'AND({{RecordType}} = "Monthly Summary", {{Employee}} = "{employee}", {{Month}} = "{month}")'
    records = table.all(formula=formula)
    return records[0] if records else None
```

### Pattern 3: Get Employee's Monthly History
```python
def get_employee_history(table, employee):
    """Get all monthly summaries for an employee, sorted by month"""
    formula = f'AND({{RecordType}} = "Monthly Summary", {{Employee}} = "{employee}")'
    records = table.all(formula=formula, sort=[("Month", "desc")])
    return records
```

### Pattern 4: Get Daily Records for a Month
```python
def get_daily_records_for_month(table, employee, month="2024-11"):
    """Get all daily records for an employee in a specific month"""
    year, month_num = month.split('-')
    start_date = f"{year}-{month_num}-01"
    
    # Calculate end date (first day of next month)
    if month_num == '12':
        end_date = f"{int(year)+1}-01-01"
    else:
        next_month = int(month_num) + 1
        end_date = f"{year}-{next_month:02d}-01"
    
    formula = f'AND({{RecordType}} = "Daily", {{Employee}} = "{employee}", IS_AFTER({{Date}}, "{start_date}"), IS_BEFORE({{Date}}, "{end_date}"))'
    return table.all(formula=formula, sort=[("Date", "asc")])
```

## 💡 Best Practices

1. **Always use `Month` field for filtering** - It's consistent and sortable
2. **Use `MonthYear` for display** - More user-friendly
3. **Combine filters** - Use `RecordType`, `Employee`, and `Month` together
4. **Create views in Airtable** - Pre-configured filters are easier than formulas
5. **Use date ranges for daily records** - More reliable than month matching
6. **Index the Month field** - If Airtable supports it, for faster queries

## 🚨 Important Notes

- **Month field is automatically populated** from the first daily record's date
- **Format is consistent**: Always `YYYY-MM` (e.g., "2024-11")
- **Empty if no daily records**: If an employee has no daily records, Month will be empty
- **One summary per employee per month**: The system creates one monthly summary per employee per calculation run

## 📝 Example Queries

### Get November 2024 summaries for all employees:
```
{RecordType} = "Monthly Summary" AND {Month} = "2024-11"
```

### Get John's summary for November:
```
{RecordType} = "Monthly Summary" AND {Employee} = "John Smith" AND {Month} = "2024-11"
```

### Get all summaries sorted by month:
```
{RecordType} = "Monthly Summary"
```
Then sort by `Month` field (ascending or descending)

### Get summaries for last 3 months:
```
{RecordType} = "Monthly Summary" AND (
  {Month} = "2024-11" OR 
  {Month} = "2024-10" OR 
  {Month} = "2024-09"
)
```

---

*This guide ensures consistent data retrieval from Airtable using the Month and MonthYear fields.*
