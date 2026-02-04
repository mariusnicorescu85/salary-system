"""
Email Client
Handles sending salary breakdown emails to employees
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, List, Optional
import os
from datetime import datetime


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
    
    def format_currency(self, value: float) -> str:
        """Format value as currency"""
        return f"£{value:,.2f}"
    
    def create_breakdown_email(self, employee_name: str, summary: Dict, 
                              daily_records: List[Dict], employee_email: str) -> str:
        """
        Create HTML email with salary breakdown
        
        Args:
            employee_name: Employee name
            summary: Monthly summary dictionary
            daily_records: List of daily calculation records
            employee_email: Employee email address
            
        Returns:
            HTML email content
        """
        bonus_breakdown = summary.get('BonusBreakdown', {})
        
        # Get month name from first record
        month_name = "Month"
        if daily_records:
            try:
                date_obj = datetime.strptime(daily_records[0]['Date'], '%Y-%m-%d')
                month_name = date_obj.strftime('%B %Y')
            except:
                pass
        
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
                <h2>Salary Breakdown - {employee_name}</h2>
                <p><strong>Period:</strong> {month_name}</p>
                
                <div class="summary-section">
                    <h3>Summary</h3>
                    <table>
                        <tr><th>Field</th><th class="currency">Value</th></tr>
                        <tr><td>Worked Days</td><td class="currency">{summary.get('WorkedDays', 0)}</td></tr>
                        <tr><td>Worked Hours</td><td class="currency">{summary.get('WorkedHours', 0):.2f}</td></tr>
                        <tr><td>Sales</td><td class="currency">{self.format_currency(summary.get('Sales', 0))}</td></tr>
                        <tr><td>Additional Sales</td><td class="currency">{self.format_currency(summary.get('AddlSales', 0))}</td></tr>
                        <tr><td>Adjusted Sales</td><td class="currency">{self.format_currency(summary.get('AdjustedSales', 0))}</td></tr>
                        <tr><td>Average Sale per Day</td><td class="currency">{self.format_currency(summary.get('AvgSalePerDay', 0))}</td></tr>
                        <tr><td>Rate per Hour</td><td class="currency">{self.format_currency(summary.get('RatePerHour', 0))}</td></tr>
                        <tr><td>Hours Salary</td><td class="currency">{self.format_currency(summary.get('HoursSalary', 0))}</td></tr>
                    </table>
                </div>
                
                <div class="bonus-section">
                    <h3>--- BONUS BREAKDOWN ---</h3>
                    <table>
                        <tr><th>Bonus Type</th><th class="currency">Amount</th></tr>
        """
        
        # Add bonus breakdown rows
        if bonus_breakdown.get('FirstLastHourBonus', 0) > 0:
            html += f'<tr><td>First/Last Hour</td><td class="currency">{self.format_currency(bonus_breakdown["FirstLastHourBonus"])}</td></tr>'
        if bonus_breakdown.get('ManagementBonus', 0) > 0:
            html += f'<tr><td>Management Bonus</td><td class="currency">{self.format_currency(bonus_breakdown["ManagementBonus"])}</td></tr>'
        if bonus_breakdown.get('TransportFuel', 0) > 0:
            html += f'<tr><td>Transport/Fuel</td><td class="currency">{self.format_currency(bonus_breakdown["TransportFuel"])}</td></tr>'
        if bonus_breakdown.get('DailySalesBonus', 0) > 0:
            html += f'<tr><td>Daily Sales Bonus</td><td class="currency">{self.format_currency(bonus_breakdown["DailySalesBonus"])}</td></tr>'
        if bonus_breakdown.get('SocialMediaBonus', 0) > 0:
            html += f'<tr><td>Social Media Bonus</td><td class="currency">{self.format_currency(bonus_breakdown["SocialMediaBonus"])}</td></tr>'
        if bonus_breakdown.get('PersonalSalesBonus', 0) > 0:
            html += f'<tr><td>Personal Sales Bonus</td><td class="currency">{self.format_currency(bonus_breakdown["PersonalSalesBonus"])}</td></tr>'
        if bonus_breakdown.get('ExtraBonus', 0) > 0:
            html += f'<tr><td>Extra Bonus</td><td class="currency">{self.format_currency(bonus_breakdown["ExtraBonus"])}</td></tr>'
        if bonus_breakdown.get('DailyAllowance', 0) > 0:
            html += f'<tr><td>Daily Allowance</td><td class="currency">{self.format_currency(bonus_breakdown["DailyAllowance"])}</td></tr>'
        
        html += f"""
                        <tr class="total"><td>TOTAL BONUS</td><td class="currency">{self.format_currency(summary.get('TotalBonus', 0))}</td></tr>
                    </table>
                </div>
                
                <div class="summary-section">
                    <table>
        """
        
        if summary.get('TotalCommission', 0) > 0:
            html += f'<tr><td>Total Commission</td><td class="currency">{self.format_currency(summary.get("TotalCommission", 0))}</td></tr>'
        
        if summary.get('ManualHours', 0) > 0:
            html += f'<tr><td>Manual Hours</td><td class="currency">{summary.get("ManualHours", 0):.2f}</td></tr>'
            html += f'<tr><td>Manual Hours Pay</td><td class="currency">{self.format_currency(summary.get("ManualHoursPay", 0))}</td></tr>'
        
        if summary.get('Deductions', 0) > 0:
            html += f'<tr><td>Deductions</td><td class="currency">-{self.format_currency(summary.get("Deductions", 0))}</td></tr>'
        
        if summary.get('Rent', 0) > 0:
            html += f'<tr><td>Rent</td><td class="currency">-{self.format_currency(summary.get("Rent", 0))}</td></tr>'
        
        if summary.get('Advance', 0) > 0:
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
        
        # Add daily records
        for record in daily_records:
            html += f"""
                    <tr>
                        <td>{record.get('Date', '')}</td>
                        <td class="currency">{record.get('Hours', 0):.2f}</td>
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
