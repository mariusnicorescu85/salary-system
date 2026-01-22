# Quick Start Guide

## 1. Install Dependencies

```bash
pip install -r requirements.txt
```

## 2. Set Up Google Drive (Optional)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable "Google Drive API"
4. Create OAuth 2.0 credentials (Desktop app)
5. Download credentials JSON
6. Save to `credentials/google_drive_credentials.json`

## 3. Configure Shops

Edit `config/shops.yaml` and set:
- Google Drive folder IDs (if using Google Drive)
- Airtable base IDs and table names (if using Airtable)

## 4. Configure Employees

Edit the employee config files:
- `config/employees_pyt.yaml`
- `config/employees_silverburn.yaml`
- `config/employees_opatra.yaml`

Add employee payment conditions, rates, and bonuses.

## 5. Run the Dashboard

```bash
streamlit run app.py
```

## 6. Use the Dashboard

1. Select a shop from the sidebar
2. Choose data source:
   - **Google Drive**: Enter file ID
   - **Upload File**: Upload CSV/Excel file
3. Click "Run Calculation"
4. View results in the "Results" tab
5. Optionally append to Airtable

## Testing Without Google Drive

You can test the system by:
1. Using the "Upload File" option
2. Uploading a CSV/Excel file with your report data
3. The system will process it and show results

## Example CSV Format

Your CSV should have columns like:
- Date
- Employee (or employee sections)
- Hours
- Sales
- Additional Sales
- Hourly Rate
- Base

The system will automatically detect the structure.

## Next Steps

- Configure all employee conditions in YAML files
- Set up Google Drive integration for automated processing
- Set up Airtable integration for data storage
- Customize bonus structures as needed
