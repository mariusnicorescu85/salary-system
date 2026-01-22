# Salary Calculation Dashboard

A comprehensive dashboard system for calculating employee salaries across multiple shops (PYT, Opatra, Silverburn). This system replicates the functionality of your n8n workflows in a user-friendly web interface.

## Features

- 📊 **Multi-Shop Support**: Calculate salaries for PYT, Opatra, and Silverburn
- 💰 **Flexible Payment Types**: Supports hourly, commission, tiered commission, and hybrid payment structures
- 📁 **Google Drive Integration**: Download reports directly from Google Drive
- 📤 **Airtable Integration**: Append daily breakdowns to Airtable automatically
- ⚙️ **Configurable**: Employee conditions and bonuses managed via YAML config files
- 📈 **Detailed Reports**: View monthly summaries and daily breakdowns for each employee

## Installation

1. **Clone or download this repository**

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up Google Drive API credentials**:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select an existing one
   - Enable the Google Drive API
   - Create OAuth 2.0 credentials (Desktop app)
   - Download the credentials JSON file
   - Save it as `credentials/google_drive_credentials.json`

4. **Configure Airtable** (optional):
   - Get your Airtable API key from [Airtable Account](https://airtable.com/account)
   - Set it as an environment variable or enter it in the dashboard

5. **Configure shops and employees**:
   - Edit `config/shops.yaml` to set Google Drive folder IDs and Airtable base IDs
   - Edit `config/employees_pyt.yaml`, `config/employees_silverburn.yaml`, and `config/employees_opatra.yaml` to configure employee payment conditions

## Usage

1. **Start the dashboard**:
   ```bash
   streamlit run app.py
   ```

2. **Access the dashboard**:
   - Open your browser to `http://localhost:8501`

3. **Run calculations**:
   - Select a shop from the sidebar
   - Choose data source (Google Drive or file upload)
   - Click "Run Calculation"
   - View results in the "Results" tab
   - Optionally append to Airtable

## Configuration Files

### `config/shops.yaml`
Configure shop-specific settings:
- Google Drive folder IDs
- Airtable base IDs and table names
- Employee config file paths

### `config/employees_*.yaml`
Configure employee payment conditions:
- Payment types (hourly_only, tiered_commission, molly_commission, etc.)
- Hourly rates
- Commission tiers
- Email addresses
- Bonuses (monthly totals)
- Manual hours, deductions, rent, advances

## Payment Types

### Hourly Only
Standard hourly payment with optional bonuses.

### Tiered Commission (Tuba)
Progressive commission structure with monthly max comparison (hourly vs commission).

### Molly Commission
Commission-only payment based on net sales (80% of total) with tiered rates.

### Net Commission Tiered (Rebecca)
Tiered commission based on total sales, applied to net sales (80% of total).

## Project Structure

```
salary_calculation_system/
├── app.py                      # Main Streamlit dashboard
├── requirements.txt            # Python dependencies
├── README.md                   # This file
├── config/
│   ├── shops.yaml              # Shop configuration
│   ├── employees_pyt.yaml      # PYT employee config
│   ├── employees_silverburn.yaml  # Silverburn employee config
│   └── employees_opatra.yaml   # Opatra employee config
├── src/
│   ├── calculation_engine.py   # Salary calculation logic
│   ├── data_processor.py       # CSV/Excel parsing
│   ├── google_drive_client.py  # Google Drive integration
│   └── airtable_client.py      # Airtable integration
└── credentials/                # API credentials (not in git)
    ├── google_drive_credentials.json
    └── google_drive_token.pickle
```

## Google Drive Setup

1. Upload your report files to Google Drive
2. Get the file ID from the Google Drive URL:
   - URL format: `https://drive.google.com/file/d/FILE_ID/view`
   - Copy the `FILE_ID` part
3. Enter the file ID in the dashboard or configure it in `config/shops.yaml`

## Airtable Setup

1. Create an Airtable base with a table for daily breakdowns
2. Create fields matching the output structure:
   - Employee (text)
   - Date (date)
   - Hours (number)
   - Sales (number)
   - AddlSales (number)
   - HrlyRate (number)
   - Base (number)
   - Commission (number)
   - PaymentType (text)
3. Get your API key and base ID
4. Configure in `config/shops.yaml` or enter in the dashboard

## Troubleshooting

### Google Drive Authentication
- First run will open a browser for OAuth authentication
- Token is saved for future use
- If token expires, delete `credentials/google_drive_token.pickle` and re-authenticate

### Airtable Errors
- Verify API key is correct
- Check base ID and table name match your Airtable setup
- Ensure field names in Airtable match the output structure

### Calculation Issues
- Check employee configuration files for correct payment types
- Verify CSV/Excel file format matches expected structure
- Check employee name mapping in data processor

## License

This project is for internal use only.

## Deployment

This application can be deployed to various cloud platforms. See `DEPLOYMENT.md` for detailed instructions.

**Recommended:** Streamlit Cloud (free, easy setup)
- Push to GitHub
- Deploy at [share.streamlit.io](https://share.streamlit.io)
- See `DEPLOY_STREAMLIT_CLOUD.md` for step-by-step guide

**Note:** Vercel is NOT recommended for Streamlit apps. See `VERCEL_WARNING.md` for details.

## Support

For issues or questions, please contact the development team.
