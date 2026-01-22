# Local Testing Guide

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Up Streamlit Secrets (Optional but Recommended)

Create or edit `.streamlit/secrets.toml`:

```toml
[airtable]
api_key = "patYourActualTokenHere"
```

This way you won't have to enter the Airtable API key every time.

### 3. Run the Application

```bash
streamlit run app.py
```

The app will open automatically in your browser at `http://localhost:8501`

If it doesn't open automatically, navigate to that URL manually.

## Testing the Update Functionality

### Scenario: Update a Single Record

1. **Prepare your data:**
   - Run calculations for a month (e.g., December)
   - Export to Airtable using "Skip duplicates" mode (first time)

2. **Make an adjustment:**
   - Go to the "Monthly Adjustments" tab
   - Select the employee and month
   - Modify a bonus, deduction, or advance
   - Save the adjustment

3. **Re-run calculations:**
   - Go back to "Calculate" tab
   - Click "Run Calculation" again
   - The new adjustment will be included

4. **Update in Airtable:**
   - Go to "Export to Airtable" section
   - Select **"Update existing records"** mode
   - Click "✅ Confirm & Append to Airtable"
   - Only the existing records will be updated (no new ones created)

### Testing Different Export Modes

#### Mode 1: Skip Duplicates (Append Only New)
- **Use case:** First time exporting data
- **Behavior:** Only creates records that don't exist
- **Test:** Export same data twice → second time should skip all records

#### Mode 2: Update Existing Records
- **Use case:** You made adjustments and want to update only existing records
- **Behavior:** Updates records that exist, skips records not found (doesn't create)
- **Test:** 
  1. Export data first time
  2. Make an adjustment
  3. Re-calculate
  4. Export with "Update existing" → should only update, not create new ones

#### Mode 3: Upsert (Update + Create)
- **Use case:** Re-running calculations after adjustments, want both update and create
- **Behavior:** Updates existing records AND creates new ones
- **Test:**
  1. Export some data
  2. Add new employee/dates to your CSV
  3. Re-calculate
  4. Export with "Upsert" → should update old records and create new ones

## Testing Without Airtable

You can test calculations without Airtable:

1. **Skip Airtable setup:**
   - Just don't enter an API key
   - The app will work fine for calculations

2. **Test with file upload:**
   - Use "Upload File" option instead of Google Drive
   - Upload a CSV/Excel file
   - Run calculations
   - View results in the "Results" tab

## Testing Monthly Adjustments

1. **Navigate to "Monthly Adjustments" tab**
2. **Select:**
   - Shop (e.g., Opatra)
   - Year (e.g., 2025)
   - Month (e.g., December)
   - Employee (e.g., John)
3. **Modify values:**
   - Extra Bonus: 100
   - Deductions: 50
   - Advance: 200
4. **Click "Save Monthly Adjustments"**
5. **Go to "Calculate" tab and run calculations**
6. **Check results** - the adjustments should be reflected

## Common Testing Scenarios

### Test 1: First Time Export
```
1. Run calculations
2. Export with "Skip duplicates" mode
3. Check Airtable - all records should be created
```

### Test 2: Update After Adjustment
```
1. Export data (first time)
2. Make monthly adjustment
3. Re-run calculations
4. Export with "Update existing" mode
5. Check Airtable - only existing records updated, no duplicates
```

### Test 3: Add New Records
```
1. Export initial data
2. Add new dates/employees to CSV
3. Re-run calculations
4. Export with "Upsert" mode
5. Check Airtable - old records updated, new ones created
```

## Debugging Tips

### Clear Streamlit Cache
If you're seeing old data:
1. Click the hamburger menu (☰) in Streamlit
2. Click "Clear cache"
3. Or restart the app

### View Logs
The app logs to the console. Watch the terminal/command prompt for:
- Employee name mappings
- Calculation warnings
- Airtable API responses

### Check Airtable Directly
After exporting, verify in Airtable:
- Records were created/updated correctly
- Fields match expected values
- No duplicate records

## Stopping the App

- **Windows:** Press `Ctrl+C` in the terminal
- **Mac/Linux:** Press `Ctrl+C` in the terminal

The app will stop and you can restart it with `streamlit run app.py`

## Troubleshooting

### Port Already in Use
If port 8501 is busy:
```bash
streamlit run app.py --server.port 8502
```

### Module Not Found
Make sure you're in the project directory:
```bash
cd C:\Users\londo\salary_calculation_system
streamlit run app.py
```

### Airtable API Errors
- Check your API key in `.streamlit/secrets.toml`
- Verify base ID and table name match your Airtable setup
- Check field names match (case-sensitive)

### Calculation Issues
- Check employee config files (`config/employees_*.yaml`)
- Verify CSV format matches expected structure
- Check employee name mappings
