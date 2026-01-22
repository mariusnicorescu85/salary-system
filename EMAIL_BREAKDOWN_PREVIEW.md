# 📧 Email Breakdown Preview

This document shows how the salary breakdown email would look when sent to employees.

---

## Email Subject
**Salary Breakdown - [Employee Name] - [Month Year]**

Example: `Salary Breakdown - John Smith - November 2024`

---

## Email Content Structure

### Header Section
```
Salary Breakdown - [Employee Name]
Period: [Month Year]
```

---

## 📊 Summary Section

| Field | Value |
|-------|-------|
| **Worked Days** | 22 |
| **Worked Hours** | 176.50 |
| **Sales** | £12,450.00 |
| **Additional Sales** | £850.00 |
| **Adjusted Sales** | £13,300.00 |
| **Average Sale per Day** | £604.55 |
| **Rate per Hour** | £12.50 |
| **Hours Salary** | £2,206.25 |

---

## 💰 BONUS BREAKDOWN

| Bonus Type | Amount |
|------------|--------|
| First/Last Hour | £220.00 |
| Management Bonus | £150.00 |
| Transport/Fuel | £88.00 |
| Daily Sales Bonus | £440.00 |
| Social Media Bonus | £50.00 |
| Personal Sales Bonus | £120.00 |
| Extra Bonus | £75.00 |
| Daily Allowance | £110.00 |
| **TOTAL BONUS** | **£1,253.00** |

---

## 💵 Additional Payments & Deductions

| Item | Amount |
|------|--------|
| **Total Commission** | £1,995.00 |
| **Manual Hours** | 8.00 |
| **Manual Hours Pay** | £100.00 |
| **Deductions** | -£50.00 |
| **Rent** | -£200.00 |
| **Advance** | -£150.00 |

---

## ✅ FINAL PAY

| **FINAL PAY** | **£5,154.25** |
|--------------|---------------|

---

## 📅 Daily Breakdown

| Date | Hours | Sales | Add'l Sales | Base | Commission |
|------|-------|-------|------------|------|------------|
| 2024-11-01 | 8.00 | £550.00 | £50.00 | £100.00 | £82.50 |
| 2024-11-02 | 8.00 | £620.00 | £40.00 | £100.00 | £93.00 |
| 2024-11-03 | 7.50 | £480.00 | £30.00 | £93.75 | £72.00 |
| 2024-11-04 | 8.00 | £710.00 | £60.00 | £100.00 | £106.50 |
| 2024-11-05 | 8.00 | £590.00 | £45.00 | £100.00 | £88.50 |
| ... | ... | ... | ... | ... | ... |
| 2024-11-30 | 8.00 | £650.00 | £55.00 | £100.00 | £97.50 |

---

## 📝 Notes

### Conditional Display Rules:

1. **Bonus Types**: Only shown if amount > 0
   - First/Last Hour Bonus
   - Management Bonus
   - Transport/Fuel
   - Daily Sales Bonus
   - Social Media Bonus
   - Personal Sales Bonus
   - Extra Bonus
   - Daily Allowance

2. **Commission**: Only shown if `TotalCommission > 0`

3. **Manual Hours**: Only shown if `ManualHours > 0`
   - Shows both hours and pay amount

4. **Deductions**: Only shown if `Deductions > 0`
   - Displayed as negative amount

5. **Rent**: Only shown if `Rent > 0`
   - Displayed as negative amount

6. **Advance**: Only shown if `Advance > 0`
   - Displayed as negative amount

---

## 🎨 Visual Styling

The email uses:
- **Clean, professional layout** with tables
- **Color-coded sections**:
  - Summary section: Light gray background with blue border
  - Bonus section: Light green background with green border
- **Currency formatting**: All amounts in £ with 2 decimal places
- **Bold totals**: Final pay and total bonus are emphasized
- **Responsive design**: Works on desktop and mobile email clients

---

## 📋 Complete Field List

### Summary Fields:
- Worked Days
- Worked Hours
- Sales
- Additional Sales
- Adjusted Sales
- Average Sale per Day
- Rate per Hour
- Hours Salary

### Bonus Breakdown Fields:
- First/Last Hour Bonus
- Management Bonus
- Management Consistency Bonus (if applicable)
- Transport/Fuel
- Daily Sales Bonus
- Social Media Bonus
- Personal Sales Bonus
- Extra Bonus
- Daily Allowance
- **Total Bonus**

### Additional Fields:
- Total Commission (if applicable)
- Manual Hours (if applicable)
- Manual Hours Pay (if applicable)
- Deductions (if applicable)
- Rent (if applicable)
- Advance (if applicable)
- **Final Payment**

### Daily Breakdown Fields:
- Date
- Hours
- Sales
- Additional Sales
- Base
- Commission

---

## 💡 Example Scenarios

### Scenario 1: Hourly Employee with Bonuses
- Worked 20 days, 160 hours
- Hourly rate: £12.00
- Sales: £8,000.00
- Bonuses: Daily Sales (£200), Transport (£80)
- No commission, no deductions
- **Final Pay: £2,480.00**

### Scenario 2: Commission-Based Employee
- Worked 22 days, 176 hours
- Sales: £15,000.00
- Commission: £2,250.00 (15%)
- Bonuses: Management (£150), Personal Sales (£200)
- Deductions: £50.00
- **Final Pay: £2,550.00**

### Scenario 3: Employee with Rent & Advance
- Worked 18 days, 144 hours
- Hourly rate: £15.00
- Sales: £6,000.00
- Bonuses: £300.00
- Rent: £200.00
- Advance: £150.00
- **Final Pay: £2,110.00**

---

## 🔄 Integration with System

This email format matches:
- ✅ The calculation engine output structure
- ✅ The Airtable export fields
- ✅ The monthly adjustments system
- ✅ The n8n workflow email format (for consistency)

---

*This preview shows the structure and format of the salary breakdown emails that would be sent to employees.*
