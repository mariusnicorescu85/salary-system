# Monthly Adjustments Guide

## Overview

The **Monthly Adjustments** feature allows you to edit bonuses, deductions, rent, and advances for each employee on a month-by-month basis. These adjustments override the base values in the employee config files.

## How It Works

1. **Base Config**: Employee config files (`config/employees_*.yaml`) contain default values
2. **Monthly Adjustments**: Monthly adjustment files override base values for specific months
3. **Automatic Loading**: When you run calculations, the system automatically loads adjustments for the month in your data

## Using Monthly Adjustments

### Step 1: Navigate to Monthly Adjustments Tab

1. Go to the **"Monthly Adjustments"** tab in the dashboard
2. Select the **Year** and **Month** you want to edit
3. Select an **Employee** from the dropdown

### Step 2: Edit Values

You can edit:

**Bonuses:**
- Daily Sales Bonus
- First/Last Hour Bonus
- Social Media Bonus
- Management Bonus
- Management Consistency Bonus
- Transport/Fuel
- Personal Sales Bonus
- Extra Bonus
- Daily Allowance

**Other Adjustments:**
- Manual Hours
- Deductions
- Rent
- Advance

### Step 3: Save

1. Review the **Total Bonus**, **Total Deductions**, and **Advance** preview
2. Click **"💾 Save Adjustments"**
3. Adjustments are saved to: `config/monthly_adjustments_{shop}_{year}-{month}.yaml`

### Step 4: Run Calculations

1. Go to the **"Calculate"** tab
2. Upload your report file
3. The system will **automatically detect the month** from your data
4. Monthly adjustments will be loaded and applied automatically
5. You'll see a message: "📅 Loaded monthly adjustments for [Month Year]"

## File Structure

Monthly adjustment files are saved as:
```
config/monthly_adjustments_pyt_2025-12.yaml
config/monthly_adjustments_opatra_2025-12.yaml
config/monthly_adjustments_silverburn_2025-12.yaml
```

Example file content:
```yaml
Tuba:
  dailySalesBonus: 0
  firstLastHourBonus: 30
  managementBonus: 431.11
  transportFuel: 216
  deductions: 0
  rent: 0
  advance: 0
```

## Important Notes

1. **Overrides Base Config**: Monthly adjustments completely override base values for that month
2. **Per-Employee**: Each employee can have different adjustments
3. **Per-Month**: Each month has its own adjustment file
4. **Automatic Detection**: The system detects the month from your CSV data automatically
5. **Advance Handling**: Advance is stored in both employee config and monthly adjustments - monthly adjustments take priority

## Viewing All Adjustments

At the bottom of the Monthly Adjustments tab, you can:
- See a summary table of all adjustments for the selected month
- Clear all adjustments for a month using the "🗑️ Clear All Adjustments" button

## Workflow Example

1. **December 2025**: Edit bonuses for Tuba
   - Go to Monthly Adjustments → December 2025 → Select Tuba
   - Set First/Last Hour Bonus: 30
   - Set Management Bonus: 431.11
   - Set Transport/Fuel: 216
   - Save

2. **Run Calculations**: 
   - Upload December 2025 report
   - System automatically loads December adjustments
   - Calculations use adjusted values

3. **January 2026**: 
   - Create new adjustments for January
   - Different values for each employee
   - System will use January adjustments when processing January data

## Tips

- **Start with Base Config**: Set default values in employee config files
- **Override Monthly**: Use monthly adjustments to change values for specific months
- **Review Before Calculating**: Check the summary table to verify all adjustments
- **Clear When Needed**: Use "Clear All" to reset a month's adjustments
