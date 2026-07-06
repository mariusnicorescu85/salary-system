"""
Email Client
Handles sending salary breakdown emails to employees
"""

import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Any, Dict, List, Optional
import os
from datetime import datetime


def _normalize_payment_type_key(payment_type) -> str:
    """Canonical snake_case payment type for branching (handles CommissionOnly, DavePackage, etc.)."""
    if payment_type is None:
        return ""
    s = str(payment_type).strip()
    if not s:
        return ""
    key = s.lower().replace(" ", "_").replace("-", "_")
    # Daily export / Airtable PascalCase → snake_case
    pascal = {
        "commissiononly": "commission_only",
        "davepackage": "dave_package",
        "hourlyonly": "hourly_only",
        "hybriddailymax": "hybrid_daily_max",
        "monthlymaxlater": "tiered_commission",
        "mollycommission": "molly_commission",
        "progressivetieredcommission": "progressive_tiered_commission",
        "flatratetieredcommission": "flat_rate_tiered_commission",
        "flatratetieredwithtransport": "flat_rate_tiered_commission_with_transport",
        "netcommissiontiered": "net_commission_tiered",
        "isaacpackage": "isaac_package",
        "alexoldstructure": "alex_hybrid",
        "alexnewstructure": "alex_hybrid",
        "salesonly": "sales_only",
    }
    return pascal.get(key, key)


def _invoice_company_name(shop_name: str) -> str:
    """Legal entity name staff should put on invoices (shop display name may differ)."""
    key = (shop_name or "").strip().lower()
    if "pyt" in key:
        return "PYT HAIRSTYLE COLLAB LTD"
    if "westfield" in key:
        return "BEAUTY SHADES LONDON LTD"
    if "opatra" in key:
        return "OPULENT BEAUTY LTD"
    return (shop_name or "").strip()


def _invoice_company_address(shop_name: str) -> str:
    """Registered business address for the invoice addressee."""
    key = (shop_name or "").strip().lower()
    if "pyt" in key:
        return "20 Wenlock Road, London, England, N1 7GU"
    if "westfield" in key:
        return "129 Station Road, Hendon, London, England, NW4 4NJ"
    if "opatra" in key:
        return "129 Station Road, London, England, NW4 4NJ"
    return ""


def employment_requires_invoice_instructions(employment: Optional[str]) -> bool:
    """Consultancy and unassigned need invoice/PDF instructions; Payroll does not."""
    if employment is None:
        return True
    v = str(employment).strip().lower()
    if not v:
        return True
    return v != "payroll"


def _extract_html_body(html: str) -> str:
    """Return inner HTML of the first <body> (for combining multiple breakdowns in one email)."""
    match = re.search(r"<body[^>]*>(.*)</body>", html, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else html


def _to_float(value, default: float = 0.0) -> float:
    """Coerce Airtable/JSON values (often strings) to float for email math and comparisons."""
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "").strip())
        except (ValueError, TypeError):
            return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _is_positive(value) -> bool:
    return _to_float(value) > 0


def _normalize_summary(summary: Optional[Dict]) -> Dict:
    """Ensure summary dict for email templates (Airtable/JSON may omit keys or use null)."""
    if not isinstance(summary, dict):
        return {}
    out = dict(summary)
    bb = out.get("BonusBreakdown")
    if not isinstance(bb, dict):
        out["BonusBreakdown"] = {}
    return out


def _normalize_daily_records(daily_records) -> List[Dict]:
    """Ensure daily rows are a list (key present with null breaks .get('daily', []))."""
    if daily_records is None:
        return []
    if isinstance(daily_records, list):
        return daily_records
    return []


def _lookup_employee_config(employees_config: Optional[Dict], emp_name: str) -> Dict:
    """Resolve per-employee config (flat or nested under 'employees')."""
    if not isinstance(employees_config, dict):
        return {}
    info = employees_config.get(emp_name)
    if isinstance(info, dict):
        return info
    nested = employees_config.get("employees")
    if isinstance(nested, dict):
        info = nested.get(emp_name)
        if isinstance(info, dict):
            return info
    return {}


_STAFF_BREAKDOWN_EMAIL_STYLES = """
  body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; }
  .header { background: linear-gradient(135deg,#ff6b6b 0%,#ff8e53 100%); color: #fff; padding: 20px; border-radius: 8px 8px 0 0; }
  .content { background: #f9f9f9; padding: 20px; }
  .summary-box { background: #fff; border-radius: 8px; padding: 15px; margin: 15px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.08); }
  .highlight { background: #e8f5e8; padding: 10px; border-left: 4px solid #4caf50; margin: 10px 0; border-radius: 4px; }
  .footer { background: #f1f1f1; padding: 15px; text-align: center; border-radius: 0 0 8px 8px; font-size: 12px; color: #666; }
  .pdf-notice { background: #fff3cd; border: 2px solid #ffc107; padding: 15px; border-radius: 8px; margin: 15px 0; }
  .pdf-notice strong { color: #d32f2f; }
  table { width: 100%; border-collapse: collapse; margin: 12px 0; }
  th, td { padding: 8px; border-bottom: 1px solid #eee; text-align: center; }
  th { background: #f2f2f2; font-weight: bold; }
  .left { text-align: left; }
  .amount { font-weight: bold; color: #2e7d32; }
  .employee-name { font-size: 22px; margin: 0; }
  .month-title { font-size: 16px; margin: 5px 0 0 0; opacity: 0.9; }
  .commission-badge { display: inline-block; background: #ff6b6b; color: white; padding: 4px 8px; border-radius: 12px; font-size: 12px; margin-left: 10px; }
  .summary-box table td:first-child { text-align: left; }
  .mgmt-approval-banner { background: #e3f2fd; border: 2px solid #2196f3; padding: 16px; border-radius: 8px; margin: 0 0 24px 0; }
  .mgmt-all-employees-summary { background: #fff; border: 1px solid #ddd; border-radius: 8px; padding: 16px; margin: 0 0 28px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.06); }
  .mgmt-all-employees-summary h3 { margin: 0 0 12px 0; font-size: 18px; }
  .mgmt-summary-table { font-size: 13px; }
  .mgmt-summary-table th { font-size: 12px; white-space: nowrap; }
  .mgmt-summary-table td:first-child, .mgmt-summary-table th:first-child { text-align: left; }
  .mgmt-summary-table .final-pay { font-weight: bold; color: #2e7d32; }
  .mgmt-summary-table tr.total-row td { background: #f5f5f5; font-weight: bold; border-top: 2px solid #ccc; }
  .mgmt-employee-breakdown { margin: 32px 0; padding-top: 8px; border-top: 3px solid #ff8e53; }
"""

_PAYMENT_DATE_LINE = "Payment is made on the <strong>10th of each month</strong>."
_PAYMENT_DATE_LINE_AFTER_INVOICE = (
    "Payment is made on the <strong>10th of each month</strong>, after you submit your invoice."
)


class EmailClient:
    """Client for sending emails"""
    
    def __init__(self, smtp_server: str = None, smtp_port: int = None, 
                 smtp_user: str = None, smtp_password: str = None):
        """
        Initialize email client
        
        Args:
            smtp_server: SMTP server (default: from env or Gmail)
            smtp_port: SMTP port (default: 587)
            smtp_user: SMTP username/email (default: from env)
            smtp_password: SMTP password/app password (default: from env)
        """
        self.smtp_server = smtp_server or os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = smtp_port or int(os.getenv('SMTP_PORT', '587'))
        self.smtp_user = smtp_user or os.getenv('SMTP_USER')
        self.smtp_password = smtp_password or os.getenv('SMTP_PASSWORD')
        
        if not self.smtp_user or not self.smtp_password:
            raise ValueError(
                "SMTP credentials not provided. Set SMTP_USER and SMTP_PASSWORD environment variables "
                "or pass smtp_user and smtp_password parameters."
            )
    
    def format_currency(self, value) -> str:
        """Format value as currency"""
        return f"£{_to_float(value):,.2f}"
    
    def create_breakdown_email(self, employee_name: str, summary: Dict, 
                              daily_records: List[Dict], employee_email: str,
                              shop_name: str = None, invoice_submission_email: str = None,
                              employment: Optional[str] = None) -> str:
        """
        Create HTML email with salary breakdown.
        When shop_name is provided, uses Opatra-style template with gradient header,
        general sign-off, optional PDF invoice notice, and invoice amount / advance / remaining flow.
        
        Args:
            employee_name: Employee name
            summary: Monthly summary dictionary
            daily_records: List of daily calculation records
            employee_email: Employee email address
            shop_name: Optional shop name (e.g. "Opatra") for styled template
            invoice_submission_email: Where staff send PDF invoices (e.g. invoices.opulent@gmail.com)
            employment: Airtable \"Employment\" single select (Consultancy / Payroll); blank treats as Consultancy
            
        Returns:
            HTML email content
        """
        summary = _normalize_summary(summary)
        daily_records = _normalize_daily_records(daily_records)
        bonus_breakdown = summary.get("BonusBreakdown") or {}
        
        # Get month name from first record
        month_name = "Month"
        if daily_records:
            try:
                date_raw = str(daily_records[0].get('Date', ''))[:10]
                date_obj = datetime.strptime(date_raw, '%Y-%m-%d')
                month_name = date_obj.strftime('%B %Y')
            except Exception:
                pass
        
        # Use Opatra-style template when shop_name provided
        if shop_name:
            return self._create_opatra_style_email(
                employee_name, summary, daily_records, bonus_breakdown,
                month_name, shop_name, invoice_submission_email or "",
                include_invoice_instructions=employment_requires_invoice_instructions(employment),
            )
        
        # Legacy simple template
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
                h2 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
                table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
                th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
                th {{ background-color: #3498db; color: white; font-weight: bold; }}
                tr:hover {{ background-color: #f5f5f5; }}
                .summary-section {{ background-color: #f9f9f9; padding: 15px; margin: 20px 0; border-left: 4px solid #3498db; }}
                .bonus-section {{ background-color: #e8f5e9; padding: 15px; margin: 20px 0; border-left: 4px solid #4caf50; }}
                .total {{ font-weight: bold; font-size: 1.2em; color: #2c3e50; }}
                .currency {{ text-align: right; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h2>Payment Breakdown - {employee_name}</h2>
                <p><strong>Period:</strong> {month_name}</p>
                
                <div class="summary-section">
                    <h3>Summary</h3>
                    <table>
                        <tr><th>Field</th><th class="currency">Value</th></tr>
                        <tr><td>Worked Days</td><td class="currency">{summary.get('WorkedDays', 0)}</td></tr>
                        <tr><td>Worked Hours</td><td class="currency">{_to_float(summary.get('WorkedHours', 0)):.2f}</td></tr>
                        <tr><td>Sales</td><td class="currency">{self.format_currency(summary.get('Sales', 0))}</td></tr>
                        <tr><td>Additional Sales</td><td class="currency">{self.format_currency(summary.get('AddlSales', 0))}</td></tr>
                        <tr><td>Adjusted Sales</td><td class="currency">{self.format_currency(summary.get('AdjustedSales', 0))}</td></tr>
                        <tr><td>Average Sale per Day</td><td class="currency">{self.format_currency(summary.get('AvgSalePerDay', 0))}</td></tr>
        """
        wage_breakdown = summary.get('WageBracketBreakdown', [])
        if not wage_breakdown:
            html += f"""
                        <tr><td>Rate per Hour</td><td class="currency">{self.format_currency(summary.get('RatePerHour', 0))}</td></tr>
        """
        html += f"""
                        <tr><td>Hours Pay</td><td class="currency">{self.format_currency(summary.get('HoursSalary', 0))}</td></tr>
        """
        if wage_breakdown:
            for i, period in enumerate(wage_breakdown, 1):
                date_from = period.get('date_from', '')
                date_to = period.get('date_to', '')
                label = f"{date_from} to {date_to}" if date_from != date_to else date_from
                html += f"""
                        <tr><td style="padding-left: 12px;">Period {i} ({label})</td><td class="currency">{_to_float(period.get('hours', 0)):.2f} hrs × {self.format_currency(period.get('rate', 0))} = {self.format_currency(period.get('pay', 0))}</td></tr>
        """
        html += """
                    </table>
                </div>
                
                <div class="bonus-section">
                    <h3>--- BONUS BREAKDOWN ---</h3>
                    <table>
                        <tr><th>Bonus Type</th><th class="currency">Amount</th></tr>
        """
        
        for key, label in [
            ('FirstLastHourBonus', 'First/Last Hour'),
            ('ManagementBonus', 'Management Bonus'),
            ('ManagementConsistencyBonus', 'Management Consistency Bonus'),
            ('TransportFuel', 'Transport/Fuel'),
            ('DailySalesBonus', 'Daily Sales Bonus'),
            ('SocialMediaBonus', 'Social Media Bonus'),
            ('PersonalSalesBonus', 'Personal Sales Bonus'),
            ('ExtraBonus', 'Extra Bonus'),
            ('DailyAllowance', 'Daily Allowance'),
        ]:
            if _is_positive(bonus_breakdown.get(key, 0)):
                html += f'<tr><td>{label}</td><td class="currency">{self.format_currency(bonus_breakdown[key])}</td></tr>'
        
        html += f"""
                        <tr class="total"><td>TOTAL BONUS</td><td class="currency">{self.format_currency(summary.get('TotalBonus', 0))}</td></tr>
                    </table>
                </div>
                
                <div class="summary-section">
                    <table>
        """
        
        if _is_positive(summary.get('TotalCommission', 0)):
            html += f'<tr><td>Total Commission</td><td class="currency">{self.format_currency(summary.get("TotalCommission", 0))}</td></tr>'
        
        if _is_positive(summary.get('ManualHours', 0)):
            html += f'<tr><td>Manual Hours</td><td class="currency">{_to_float(summary.get("ManualHours", 0)):.2f}</td></tr>'
            html += f'<tr><td>Manual Hours Pay</td><td class="currency">{self.format_currency(summary.get("ManualHoursPay", 0))}</td></tr>'
        
        if _is_positive(summary.get('Deductions', 0)):
            html += f'<tr><td>Deductions</td><td class="currency">-{self.format_currency(summary.get("Deductions", 0))}</td></tr>'
        
        if _is_positive(summary.get('Rent', 0)):
            pt = (summary.get('PaymentType') or '').lower()
            rent_fmt = self.format_currency(summary.get("Rent", 0))
            html += f'<tr><td>Rent</td><td class="currency">{"" if pt == "alex_hybrid" else "-"}{rent_fmt}</td></tr>'
        
        if _is_positive(summary.get('Advance', 0)):
            html += f'<tr><td>Advance</td><td class="currency">-{self.format_currency(summary.get("Advance", 0))}</td></tr>'
        
        html += f"""
                        <tr class="total"><td>FINAL PAY</td><td class="currency">{self.format_currency(summary.get("FinalPayment", 0))}</td></tr>
                    </table>
                </div>
                
                <h3>Daily Breakdown</h3>
                <table>
                    <tr>
                        <th>Date</th>
                        <th class="currency">Hours</th>
                        <th class="currency">Sales</th>
                        <th class="currency">Add'l Sales</th>
                        <th class="currency">Base</th>
                        <th class="currency">Commission</th>
                    </tr>
        """
        
        for record in daily_records:
            html += f"""
                    <tr>
                        <td>{record.get('Date', '')}</td>
                        <td class="currency">{_to_float(record.get('Hours', 0)):.2f}</td>
                        <td class="currency">{self.format_currency(record.get('Sales', 0))}</td>
                        <td class="currency">{self.format_currency(record.get('AddlSales', 0))}</td>
                        <td class="currency">{self.format_currency(record.get('Base', 0))}</td>
                        <td class="currency">{self.format_currency(record.get('Commission', 0))}</td>
                    </tr>
            """
        
        html += """
                </table>
            </div>
        </body>
        </html>
        """
        
        return html

    def _html_dave_package_breakdown_rows(self, summary: Dict[str, Any], daily_records: List[Dict]) -> str:
        """Monthly Overview HTML rows for dave_package. Fills gaps when summary JSON omits breakdown keys."""
        daily_records = _normalize_daily_records(daily_records)

        def _fkey(key: str):
            v = summary.get(key)
            if v is None or v == "":
                return None
            try:
                return _to_float(v)
            except (TypeError, ValueError):
                return None

        personal = _fkey("PersonalCommission")
        if personal is None:
            personal = sum(_to_float(r.get("Commission", 0)) for r in daily_records)

        tc = _fkey("TotalCommission")
        if tc is None:
            tc = 0.0
        shop_comm = _fkey("ShopRangeCommission")
        if shop_comm is None:
            shop_comm = max(0.0, round(tc - personal, 2))

        shop_gross = _fkey("ShopRangeSalesGross")
        if shop_gross is None and shop_comm:
            shop_gross = round(shop_comm / 0.01, 2)
        elif shop_gross is None:
            shop_gross = 0.0

        d0 = (summary.get("ShopRangeFirstDate") or "").strip()
        d1 = (summary.get("ShopRangeLastDate") or "").strip()
        if not d0 or not d1:
            dates = sorted({
                str(r.get("Date", ""))[:10]
                for r in daily_records
                if _to_float(r.get("Hours", 0)) > 0.001 and r.get("Date")
            })
            if dates:
                d0, d1 = dates[0], dates[-1]

        parts = []
        if personal:
            parts.append(
                f'<tr><td><strong>Personal commission (10%):</strong></td>'
                f'<td class="amount">{self.format_currency(personal)}</td></tr>'
            )
        if shop_gross or shop_comm:
            parts.append(
                f'<tr><td><strong>Shop sales (first–last clock-in dates):</strong></td>'
                f'<td class="amount">{self.format_currency(shop_gross)}</td></tr>'
            )
            parts.append(
                f'<tr><td><strong>Shop commission (1% of range):</strong></td>'
                f'<td class="amount">{self.format_currency(shop_comm)}</td></tr>'
            )
        if d0 and d1:
            parts.append(
                f'<tr><td><strong>Shop range (dates):</strong></td>'
                f'<td class="amount">{d0} → {d1}</td></tr>'
            )
        return "".join(parts)
    
    def _create_opatra_style_email(self, employee_name: str, summary: Dict,
                                   daily_records: List[Dict], bonus_breakdown: Dict,
                                   month_name: str, shop_name: str,
                                   invoice_submission_email: str,
                                   include_invoice_instructions: bool = True) -> str:
        """Opatra-style email: gradient header; invoice/PDF blocks only when include_invoice_instructions."""
        pt_key = _normalize_payment_type_key(summary.get("PaymentType"))
        if not pt_key and daily_records:
            pt_key = _normalize_payment_type_key(daily_records[0].get("PaymentType"))
        if not pt_key and daily_records:
            for r in daily_records:
                pk = _normalize_payment_type_key(r.get("PaymentType"))
                if pk == "dave_package":
                    pt_key = "dave_package"
                    break
        is_commission = pt_key in (
            "commission_only", "dave_package", "tiered_commission", "progressive_tiered_commission",
            "hybrid_daily_max", "molly_commission", "flat_rate_tiered_commission",
            "flat_rate_tiered_commission_with_transport", "net_commission_tiered", "alex_hybrid",
            "isaac_package",
        )
        
        advance = abs(_to_float(summary.get('Advance', 0)))
        final_pay = _to_float(summary.get('FinalPayment', 0))
        total_before_advance = final_pay + advance
        
        hours_salary = _to_float(summary.get('HoursSalary', 0))
        total_bonus = _to_float(summary.get('TotalBonus', 0))
        total_commission = _to_float(summary.get('TotalCommission', 0))
        hours_plus_bonus = hours_salary + total_bonus
        
        # Build bonus breakdown rows
        bonus_detail_rows = ""
        for key, label in [
            ('DailySalesBonus', 'Daily Sales Bonus'),
            ('FirstLastHourBonus', 'First/Last Hour Bonus'),
            ('SocialMediaBonus', 'Social Media Bonus'),
            ('ManagementBonus', 'Management Bonus'),
            ('ManagementConsistencyBonus', 'Mgmt Consistency Bonus'),
            ('TransportFuel', 'Transport/Fuel'),
            ('PersonalSalesBonus', 'Personal Sales Bonus'),
            ('ExtraBonus', 'Extra Bonus'),
            ('DailyAllowance', 'Daily Allowance'),
        ]:
            if _is_positive(bonus_breakdown.get(key, 0)):
                bonus_detail_rows += f'<tr><td style="padding-left: 20px;"><em>{label}:</em></td><td class="amount">{self.format_currency(bonus_breakdown[key])}</td></tr>'
        
        if _is_positive(summary.get('ManualHours', 0)):
            bonus_detail_rows += f'<tr><td style="padding-left: 20px;"><em>Manual Hours:</em></td><td class="amount">{self.format_currency(summary.get("ManualHoursPay", 0))}</td></tr>'
        
        if bonus_detail_rows:
            bonus_detail_rows += f'<tr style="background: #e8f5e8; font-weight: bold;"><td><strong>TOTAL BONUS:</strong></td><td class="amount">{self.format_currency(total_bonus)}</td></tr>'
        
        bonus_section_html = ""
        if bonus_detail_rows:
            bonus_section_html = f'<tr style="background: #f0f8ff; font-weight: bold; border-top: 2px solid #4caf50;"><td colspan="2" style="padding: 12px 8px;">🎁 BONUS BREAKDOWN</td></tr>{bonus_detail_rows}'
        
        # Wage bracket breakdown (when rate varied mid-month, e.g. employee turned 18)
        wage_breakdown_html = ""
        wage_breakdown = summary.get('WageBracketBreakdown', [])
        if wage_breakdown:
            rows = "".join(
                f'<tr><td style="padding-left: 20px;"><em>{p.get("date_from", "")} to {p.get("date_to", "")}:</em></td>'
                f'<td class="amount">{_to_float(p.get("hours", 0)):.2f} hrs × {self.format_currency(p.get("rate", 0))} = {self.format_currency(p.get("pay", 0))}</td></tr>'
                for p in wage_breakdown
            )
            wage_breakdown_html = f'<tr style="background: #f5f5f5; font-weight: bold; border-top: 2px solid #9e9e9e;"><td colspan="2" style="padding: 12px 8px;">📋 Wage Bracket Breakdown (rate varied mid-month)</td></tr>{rows}'
        hourly_rate_row = "" if wage_breakdown else f'<tr><td><strong>Hourly Rate:</strong></td><td class="amount">{self.format_currency(summary.get("RatePerHour", 0))}</td></tr>'
        if pt_key == "dave_package":
            hourly_rate_row = ""

        salary_row_label = "Prorated base (package ÷ reference days × days worked):" if pt_key == "dave_package" else "Hours Pay:"
        dave_detail_rows = ""
        if pt_key == "dave_package":
            dave_detail_rows = self._html_dave_package_breakdown_rows(summary, daily_records)
        isaac_detail_rows = ""
        if pt_key == "isaac_package":
            transport_total = _to_float(
                summary.get("IsaacTransportTotal", 0) or bonus_breakdown.get("TransportFuel", 0)
            )
            milestone_bonus = _to_float(summary.get("SalesMilestoneBonus", 0))
            if transport_total > 0:
                isaac_detail_rows += (
                    f'<tr><td><strong>Transport (qualifying days):</strong></td>'
                    f'<td class="amount">{self.format_currency(transport_total)}</td></tr>'
                )
            if milestone_bonus > 0:
                isaac_detail_rows += (
                    f'<tr><td><strong>Sales milestone bonus:</strong></td>'
                    f'<td class="amount">{self.format_currency(milestone_bonus)}</td></tr>'
                )
        
        # Deductions row
        deductions = _to_float(summary.get('Deductions', 0))
        deductions_html = ""
        if deductions != 0:
            deductions_html = f"""<tr style="background: #fff3e0; font-weight: bold; border-top: 2px solid #ff9800;">
                <td colspan="2" style="padding: 12px 8px;">⚠️ DEDUCTIONS</td>
            </tr>
            <tr><td style="padding-left: 20px;"><em>Deductions:</em></td><td class="amount" style="color: #d32f2f;">-{self.format_currency(abs(deductions))}</td></tr>"""

        rent_amt = _to_float(summary.get("Rent", 0))
        rent_html = ""
        if rent_amt != 0:
            if pt_key == "alex_hybrid":
                rent_html = (
                    f'<tr><td><strong>Rent (chair / structure):</strong></td>'
                    f'<td class="amount">{self.format_currency(abs(rent_amt))}</td></tr>'
                )
            else:
                rent_html = (
                    f'<tr><td><strong>Rent:</strong></td>'
                    f'<td class="amount" style="color: #d32f2f;">-{self.format_currency(abs(rent_amt))}</td></tr>'
                )
        
        # Hours + Bonus or Commission + Bonus row (feeds invoice amount when advance was paid)
        if is_commission:
            mid_row = f'<tr><td><strong>Total commission{(" (personal + shop)" if pt_key == "dave_package" else "")}:</strong></td><td class="amount">{self.format_currency(total_commission)}</td></tr>'
        else:
            mid_row = f'<tr><td><strong>Hours + Bonus:</strong></td><td class="amount">{self.format_currency(hours_plus_bonus)}</td></tr>' if _is_positive(total_bonus) else ''
        
        # Daily table - hourly: Date, Hours, Sales, Daily Pay (Base); commission: Date, Hours, Sales, Addl Sales, Commission
        if is_commission and pt_key == "isaac_package":
            daily_rows = "".join(
                f'<tr><td class="left">{r.get("Date", "")}</td><td>{_to_float(r.get("Hours", 0)):.2f}</td>'
                f'<td>{self.format_currency(r.get("Sales", 0))}</td><td>{self.format_currency(r.get("AddlSales", 0))}</td>'
                f'<td class="amount">{self.format_currency(r.get("Base", 0))}</td>'
                f'<td class="amount">{self.format_currency(r.get("Commission", 0))}</td></tr>'
                for r in daily_records
            )
            daily_header = (
                '<tr><th class="left">Date</th><th>Hours</th><th>Sales</th>'
                '<th>Addl Sales</th><th>Transport</th><th>Commission</th></tr>'
            )
            header_title = "Commission Breakdown"
            commission_badge = '<span class="commission-badge">ISAAC PACKAGE</span>'
        elif is_commission:
            daily_rows = "".join(
                f'<tr><td class="left">{r.get("Date", "")}</td><td>{_to_float(r.get("Hours", 0)):.2f}</td>'
                f'<td>{self.format_currency(r.get("Sales", 0))}</td><td>{self.format_currency(r.get("AddlSales", 0))}</td>'
                f'<td class="amount">{self.format_currency(r.get("Commission", 0))}</td></tr>'
                for r in daily_records
            )
            comm_header = "Personal commission (day)" if pt_key == "dave_package" else "Commission"
            daily_header = (
                f"<tr><th class=\"left\">Date</th><th>Hours</th><th>Sales</th><th>Addl Sales</th><th>{comm_header}</th></tr>"
            )
            header_title = "Commission Breakdown"
            commission_badge = '<span class="commission-badge">COMMISSION</span>' if pt_key != "dave_package" else '<span class="commission-badge">PACKAGE PAY</span>'
        else:
            daily_rows = "".join(
                f'<tr><td class="left">{r.get("Date", "")}</td><td>{_to_float(r.get("Hours", 0)):.2f}</td>'
                f'<td>{self.format_currency(r.get("Sales", 0))}</td><td class="amount">{self.format_currency(r.get("Base", 0))}</td></tr>'
                for r in daily_records
            )
            daily_header = "<tr><th class=\"left\">Date</th><th>Hours</th><th>Sales</th><th>Daily Pay</th></tr>"
            header_title = "Breakdown Summary"
            commission_badge = ""
        
        invoice_email = invoice_submission_email or "invoices.opulent@gmail.com"
        invoice_company = _invoice_company_name(shop_name)
        invoice_address = _invoice_company_address(shop_name)
        invoice_addressee_html = (
            f"<strong>{invoice_company}</strong><br>{invoice_address}"
            if invoice_address
            else f"<strong>{invoice_company}</strong>"
        )
        if include_invoice_instructions:
            intro_html = f"""  <p>Hi {employee_name},</p>
  <p>
    Please see below your breakdown, kindly send your invoice <strong>in PDF format</strong> as soon as possible.<br><br>
    No chasing email will be sent, please be responsible.<br><br>
    Many thanks.
  </p>"""
            if _is_positive(advance):
                advance_rows_html = (
                    f'<tr><td><strong>Invoice amount:</strong></td>'
                    f'<td class="amount">{self.format_currency(total_before_advance)}</td></tr>'
                    f'<tr><td><strong>Advance already paid:</strong></td>'
                    f'<td class="amount">- {self.format_currency(advance)}</td></tr>'
                )
            else:
                advance_rows_html = ""
            pdf_notice_html = f"""    <div class="pdf-notice">
      <h3 style="margin-top: 0;">📄 IMPORTANT: Invoice Submission Requirements</h3>
      <ul style="margin: 10px 0;">
        <li><strong style="color: #d32f2f;">Your invoice MUST be submitted in PDF format</strong></li>
        <li>Address your invoice to:<br>{invoice_addressee_html}</li>
        <li>Invoice amount: <strong>{self.format_currency(total_before_advance)}</strong></li>
        <li>Send to: <strong>{invoice_email}</strong></li>
        <li>You do <strong>not</strong> need to attach or copy this full breakdown on your invoice — one line with the total amount is enough.</li>
        <li>Please ensure your invoice is a PDF file before sending</li>
        <li>{_PAYMENT_DATE_LINE_AFTER_INVOICE}</li>
      </ul>
    </div>"""
            important_notes_html = f"""    <div class="summary-box">
      <h3>📝 Important Notes</h3>
      <ul>
        <li>This summary covers {month_name}.</li>
        <li>Please issue your invoice to {invoice_addressee_html} for <strong>{self.format_currency(total_before_advance)}</strong>.</li>
        <li><strong>Invoice must be in PDF format</strong> when submitting to <strong>{invoice_email}</strong>.</li>
        <li>The detailed breakdown in this email is for your records only — you do <strong>not</strong> need to reproduce it on your invoice.</li>
        <li>{_PAYMENT_DATE_LINE_AFTER_INVOICE}</li>
        <li>If you have questions about your payment, please contact the Management Team before submitting the invoice.</li>
      </ul>
    </div>"""
        else:
            intro_html = f"""  <p>Hi {employee_name},</p>
  <p>
    Please see below your breakdown for {month_name}.<br><br>
    Many thanks.
  </p>"""
            if _is_positive(advance):
                advance_rows_html = (
                    f'<tr><td><strong>Total earned:</strong></td>'
                    f'<td class="amount">{self.format_currency(total_before_advance)}</td></tr>'
                    f'<tr><td><strong>Advance already paid:</strong></td>'
                    f'<td class="amount">- {self.format_currency(advance)}</td></tr>'
                )
            else:
                advance_rows_html = ""
            pdf_notice_html = ""
            important_notes_html = f"""    <div class="summary-box">
      <h3>📝 Important Notes</h3>
      <ul>
        <li>This summary covers {month_name}.</li>
        <li>{_PAYMENT_DATE_LINE}</li>
        <li>If you have questions about your payment, please contact the Management Team.</li>
      </ul>
    </div>"""

        html = f"""
<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Monthly Breakdown - {shop_name}</title>
<style>
  body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; }}
  .header {{ background: linear-gradient(135deg,#ff6b6b 0%,#ff8e53 100%); color: #fff; padding: 20px; border-radius: 8px 8px 0 0; }}
  .content {{ background: #f9f9f9; padding: 20px; }}
  .summary-box {{ background: #fff; border-radius: 8px; padding: 15px; margin: 15px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.08); }}
  .highlight {{ background: #e8f5e8; padding: 10px; border-left: 4px solid #4caf50; margin: 10px 0; border-radius: 4px; }}
  .footer {{ background: #f1f1f1; padding: 15px; text-align: center; border-radius: 0 0 8px 8px; font-size: 12px; color: #666; }}
  .pdf-notice {{ background: #fff3cd; border: 2px solid #ffc107; padding: 15px; border-radius: 8px; margin: 15px 0; }}
  .pdf-notice strong {{ color: #d32f2f; }}
  table {{ width: 100%; border-collapse: collapse; margin: 12px 0; }}
  th, td {{ padding: 8px; border-bottom: 1px solid #eee; text-align: center; }}
  th {{ background: #f2f2f2; font-weight: bold; }}
  .left {{ text-align: left; }}
  .amount {{ font-weight: bold; color: #2e7d32; }}
  .employee-name {{ font-size: 22px; margin: 0; }}
  .month-title {{ font-size: 16px; margin: 5px 0 0 0; opacity: 0.9; }}
  .commission-badge {{ display: inline-block; background: #ff6b6b; color: white; padding: 4px 8px; border-radius: 12px; font-size: 12px; margin-left: 10px; }}
  .summary-box table td:first-child {{ text-align: left; }}
</style></head>
<body>
{intro_html}

  <div class="header">
    <h1 class="employee-name">{employee_name} – {header_title} {commission_badge}</h1>
    <p class="month-title">{month_name} - {shop_name}</p>
  </div>

  <div class="content">
    <div class="highlight">
      <h3>💰 Your Total Payment (remaining after any advance): <span class="amount">{self.format_currency(final_pay)}</span></h3>
    </div>

    <div class="summary-box">
      <h3>📊 Monthly Overview</h3>
      <table>
        <tr><td><strong>Days Worked:</strong></td><td class="amount">{summary.get('WorkedDays', 0)} days</td></tr>
        <tr><td><strong>Total Hours:</strong></td><td class="amount">{_to_float(summary.get('WorkedHours', 0)):.2f} hours</td></tr>
        {hourly_rate_row}
        <tr><td><strong>{salary_row_label}</strong></td><td class="amount">{self.format_currency(hours_salary)}</td></tr>
        {dave_detail_rows}
        {isaac_detail_rows}
        {wage_breakdown_html}
        {bonus_section_html}
        {mid_row}
        {deductions_html}
        {rent_html}
        {advance_rows_html}
        <tr><td><strong>Remaining To Pay:</strong></td><td class="amount">{self.format_currency(final_pay)}</td></tr>
      </table>
    </div>

    <div class="summary-box">
      <h3>🛍️ Sales Performance</h3>
      <table>
        <tr><td><strong>Total Sales:</strong></td><td class="amount">{self.format_currency(summary.get('Sales', 0))}</td></tr>
        <tr><td><strong>Additional Sales:</strong></td><td class="amount">{self.format_currency(summary.get('AddlSales', 0))}</td></tr>
        <tr><td><strong>Adjusted Sales:</strong></td><td class="amount">{self.format_currency(summary.get('AdjustedSales', 0))}</td></tr>
        <tr><td><strong>Average per Day:</strong></td><td class="amount">{self.format_currency(summary.get('AvgSalePerDay', 0))}</td></tr>
      </table>
    </div>

    <div class="summary-box">
      <h3>📅 Daily Breakdown</h3>
      <table>
        <thead>{daily_header}</thead>
        <tbody>{daily_rows}</tbody>
      </table>
    </div>

{pdf_notice_html}

{important_notes_html}

    <p>Thank you for your hard work and dedication! 🌟</p>
  </div>

  <div class="footer">
    <p><strong>{shop_name}</strong></p>
    <p><em>This is an automated breakdown summary. Please keep for your records.</em></p>
  </div>
</body></html>
        """.strip()
        
        return html

    def _build_management_all_employees_summary_html(self, results: Dict[str, Dict]) -> str:
        """HTML table: one row per employee (same columns as Results → Monthly Summary)."""
        rows: List[str] = []
        totals = {
            "hours": 0.0,
            "sales": 0.0,
            "hours_salary": 0.0,
            "commission": 0.0,
            "bonus": 0.0,
            "final_pay": 0.0,
        }
        for emp_name in sorted(results.keys(), key=lambda n: str(n or "")):
            emp_data = results[emp_name] or {}
            summary = _normalize_summary(emp_data.get("summary"))
            days = summary.get("WorkedDays", 0)
            hours = _to_float(summary.get("WorkedHours", 0))
            sales = _to_float(summary.get("Sales", 0))
            hours_salary = _to_float(summary.get("HoursSalary", 0))
            commission = _to_float(summary.get("TotalCommission", 0))
            bonus = _to_float(summary.get("TotalBonus", 0))
            final_pay = _to_float(summary.get("FinalPayment", 0))
            totals["hours"] += hours
            totals["sales"] += sales
            totals["hours_salary"] += hours_salary
            totals["commission"] += commission
            totals["bonus"] += bonus
            totals["final_pay"] += final_pay
            rows.append(
                f"<tr>"
                f"<td>{emp_name}</td>"
                f"<td>{days}</td>"
                f"<td>{hours:.2f}</td>"
                f"<td>{self.format_currency(sales)}</td>"
                f"<td>{self.format_currency(hours_salary)}</td>"
                f"<td>{self.format_currency(commission)}</td>"
                f"<td>{self.format_currency(bonus)}</td>"
                f'<td class="final-pay">{self.format_currency(final_pay)}</td>'
                f"</tr>"
            )
        total_row = (
            f'<tr class="total-row">'
            f"<td>Total</td>"
            f"<td>—</td>"
            f"<td>{totals['hours']:.2f}</td>"
            f"<td>{self.format_currency(totals['sales'])}</td>"
            f"<td>{self.format_currency(totals['hours_salary'])}</td>"
            f"<td>{self.format_currency(totals['commission'])}</td>"
            f"<td>{self.format_currency(totals['bonus'])}</td>"
            f'<td class="final-pay">{self.format_currency(totals["final_pay"])}</td>'
            f"</tr>"
        )
        body_rows = "\n".join(rows) + "\n" + total_row
        return f"""<div class="mgmt-all-employees-summary">
    <h3>Summary (All Employees)</h3>
    <table class="mgmt-summary-table">
      <thead>
        <tr>
          <th>Employee</th>
          <th>Days</th>
          <th>Hours</th>
          <th>Sales</th>
          <th>Hours Salary</th>
          <th>Commission</th>
          <th>Bonus</th>
          <th>Final Pay</th>
        </tr>
      </thead>
      <tbody>
{body_rows}
      </tbody>
    </table>
  </div>"""
    
    def create_management_approval_email(
        self,
        shop_name: str,
        results: Dict[str, Dict],
        month_name: str = None,
        employees_config: Optional[Dict[str, Dict]] = None,
        invoice_submission_email: str = None,
    ) -> str:
        """
        Consolidated management approval email: same HTML breakdown each staff member receives,
        stacked in one message (Consultancy/Payroll invoice rules applied per employee).
        """
        if not results:
            return ""

        first_emp_data = next(iter(results.values())) or {}
        daily_records = _normalize_daily_records(first_emp_data.get("daily"))
        if not month_name and daily_records:
            try:
                date_raw = str(daily_records[0].get('Date', ''))[:10]
                date_obj = datetime.strptime(date_raw, '%Y-%m-%d')
                month_name = date_obj.strftime('%B %Y')
            except Exception:
                month_name = "Month"
        month_name = month_name or "Month"

        invoice_email = str(invoice_submission_email or "")
        staff_shop_name = shop_name or None

        breakdown_sections = []
        for emp_name in sorted(results.keys(), key=lambda n: str(n or "")):
            emp_data = results[emp_name] or {}
            summary = _normalize_summary(emp_data.get("summary"))
            daily = _normalize_daily_records(emp_data.get("daily"))
            emp_info = _lookup_employee_config(employees_config, emp_name)
            try:
                staff_html = self.create_breakdown_email(
                    emp_name,
                    summary,
                    daily,
                    str(emp_info.get("email") or ""),
                    shop_name=staff_shop_name,
                    invoice_submission_email=invoice_email,
                    employment=emp_info.get("employment", ""),
                )
            except Exception as e:
                raise TypeError(f"Could not build breakdown for {emp_name!r}: {e}") from e
            body_inner = _extract_html_body(staff_html)
            breakdown_sections.append(
                f'<div class="mgmt-employee-breakdown">{body_inner}</div>'
            )

        sections_html = "\n".join(breakdown_sections)
        n_staff = len(breakdown_sections)
        summary_html = self._build_management_all_employees_summary_html(results)

        return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Salary Breakdowns for Approval - {shop_name}</title>
<style>{_STAFF_BREAKDOWN_EMAIL_STYLES}</style></head>
<body>
  <div class="mgmt-approval-banner">
    <h2 style="margin:0 0 8px 0;">Salary breakdowns for approval — {shop_name}</h2>
    <p style="margin:0;"><strong>Period:</strong> {month_name} · <strong>{n_staff}</strong> employee(s)</p>
    <p style="margin:12px 0 0 0;">Review the summary table below, then each employee section (the same breakdown they will receive).
    Approve before using <em>Send to all staff</em>.</p>
  </div>
{summary_html}
{sections_html}
</body></html>""".strip()
    
    def send_email(self, to_email: str, subject: str, html_content: str, 
                   from_email: str = None, reply_to: str = None) -> bool:
        """
        Send email
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML email content
            from_email: Sender email (default: smtp_user)
            reply_to: Optional reply-to address (where replies should go)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            from_email = from_email or self.smtp_user
            
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = from_email
            msg['To'] = to_email
            
            # Attach HTML content
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)
            
            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            
            return True
        except Exception as e:
            print(f"Error sending email: {e}")
            return False
