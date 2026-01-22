# Email & Airtable Setup Guide

## ✅ What's New

The system now supports:
1. **Full Bonus Breakdown in Airtable** - Monthly summaries with all bonus details
2. **Email Functionality** - Send salary breakdown emails to employees (same as n8n workflows)

## 📊 Airtable Export Structure

The Airtable export now includes **two types of records**:

### 1. Daily Records
- One record per day per employee
- Fields: Employee, Date, Hours, Sales, AddlSales, HrlyRate, Base, Commission, PaymentType

### 2. Monthly Summary Records
- One record per employee per month
- Includes **full bonus breakdown**:
  - WorkedDays, WorkedHours, Sales, AddlSales, AdjustedSales
  - AvgSalePerDay, RatePerHour, HoursSalary
  - TotalCommission, TotalBonus
  - **Bonus Breakdown:**
    - DailySalesBonus
    - FirstLastHourBonus
    - SocialMediaBonus
    - ManagementBonus
    - ManagementConsistencyBonus
    - TransportFuel
    - PersonalSalesBonus
    - ExtraBonus
    - DailyAllowance
  - ManualHours, ManualHoursPay
  - Deductions, Rent, Advance
  - FinalPayment
  - PaymentType

**RecordType field** distinguishes between "Daily" and "Monthly Summary" records.

## 📧 Email Setup

### Step 1: Configure SMTP

Add to `.streamlit/secrets.toml`:
```toml
[smtp]
server = "smtp.gmail.com"
port = 587
user = "your_email@gmail.com"
password = "your_app_password"
```

**Or use environment variables:**
```bash
export SMTP_SERVER=smtp.gmail.com
export SMTP_PORT=587
export SMTP_USER=your_email@gmail.com
export SMTP_PASSWORD=your_app_password
```

### Step 2: Gmail App Password Setup

1. Go to your Google Account settings
2. Security → 2-Step Verification (must be enabled)
3. App passwords → Generate app password
4. Use this password (not your regular Gmail password)

### Step 3: Send Emails

1. Run calculations in the "Calculate" tab
2. Go to "Results" tab
3. Select an employee
4. Scroll to "📧 Send Email to Employee" section
5. Click "📧 Send Salary Breakdown Email"

## 📋 Email Content

The email includes:
- **Summary Section**: Worked Days, Hours, Sales, etc.
- **Bonus Breakdown Section**: All bonus types with amounts
- **Total Commission** (if applicable)
- **Manual Hours** (if applicable)
- **Deductions, Rent, Advance** (if applicable)
- **FINAL PAY**
- **Daily Breakdown Table**: All daily records

## 🎯 Airtable Table Structure

Your Airtable table should have these fields:

### Required Fields (for Daily Records):
- `RecordType` (Single line text: "Daily" or "Monthly Summary")
- `Employee` (Single line text)
- `Date` (Date)
- `Hours` (Number)
- `Sales` (Number)
- `AddlSales` (Number)
- `HrlyRate` (Number)
- `Base` (Number)
- `Commission` (Number)
- `PaymentType` (Single line text)

### Additional Fields (for Monthly Summary):
- `Month` (Single line text) - Format: "2024-11" for easy filtering
- `MonthYear` (Single line text) - Format: "November 2024" for display
- `WorkedDays` (Number)
- `WorkedHours` (Number)
- `AdjustedSales` (Number)
- `AvgSalePerDay` (Number)
- `RatePerHour` (Number)
- `HoursSalary` (Number)
- `TotalCommission` (Number)
- `TotalBonus` (Number)
- `DailySalesBonus` (Number)
- `FirstLastHourBonus` (Number)
- `SocialMediaBonus` (Number)
- `ManagementBonus` (Number)
- `ManagementConsistencyBonus` (Number)
- `TransportFuel` (Number)
- `PersonalSalesBonus` (Number)
- `ExtraBonus` (Number)
- `DailyAllowance` (Number)
- `ManualHours` (Number)
- `ManualHoursPay` (Number)
- `Deductions` (Number)
- `Rent` (Number)
- `Advance` (Number)
- `FinalPayment` (Number)

## 🔍 Viewing in Airtable

To see the breakdown like in your screenshot:

1. **Filter by RecordType = "Monthly Summary"** to see summary records
2. **Filter by Month = "2024-11"** to see a specific month (update as needed)
3. **Group by Employee** to see each employee's summary
4. **Sort by Month** (ascending or descending) to see chronological order

**Note:** The `Month` field (format: "2024-11") is automatically added to monthly summaries for easy filtering. See `AIRTABLE_DATA_RETRIEVAL.md` for detailed querying strategies.

You can also create a view that shows:
- Employee name
- All bonus breakdown fields
- Final payment
- Daily records linked or in a related table

## 💡 Tips

- **Email addresses** must be set in employee config files (`email` field)
- **SMTP credentials** are stored securely in secrets (not committed to git)
- **Monthly summaries** are created automatically when you export to Airtable
- **Daily records** and **monthly summaries** are exported together

## 🚀 Next Steps

1. Set up SMTP credentials in `.streamlit/secrets.toml`
2. Ensure all employees have email addresses in their config files
3. Run calculations and export to Airtable
4. Send test emails to verify everything works
5. Create Airtable views to match your screenshot layout
