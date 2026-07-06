"""
Salary Calculation Engine
Handles all payment calculations based on employee conditions
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import pandas as pd

# Optional import for UK wage bracket
try:
    from src.wage_bracket import get_rate_for_date
except ImportError:
    get_rate_for_date = None


class CalculationEngine:
    """Main calculation engine for salary calculations"""
    
    def __init__(self, employee_config: Dict, bonus_config: Dict, wage_brackets: Optional[List[Dict]] = None):
        self.employee_config = employee_config
        self.bonus_config = bonus_config
        self.wage_brackets = wage_brackets or []
    
    @staticmethod
    def build_shop_daily_sales_totals(records: List[Dict[str, Any]]) -> Dict[str, float]:
        """
        Sum Sales + AddlSales per calendar date across all rows in the report.
        Used for shop-wide commissions (one shop per report file).
        """
        totals: Dict[str, float] = {}
        for r in records or []:
            d = r.get("Date")
            if not d:
                continue
            day = str(d)[:10]
            sales = float(r.get("Sales", 0) or 0)
            addl = float(r.get("AddlSales", 0) or 0)
            totals[day] = totals.get(day, 0.0) + sales + addl
        return totals

    @staticmethod
    def _dates_inclusive(first: str, last: str) -> List[str]:
        """Every calendar date from first through last (YYYY-MM-DD), inclusive."""
        a = datetime.strptime(first[:10], "%Y-%m-%d")
        b = datetime.strptime(last[:10], "%Y-%m-%d")
        out: List[str] = []
        cur = a
        while cur <= b:
            out.append(cur.strftime("%Y-%m-%d"))
            cur += timedelta(days=1)
        return out

    def _resolve_hourly_rate(self, employee: Dict, date_str: str) -> float:
        """Get hourly rate: use override if set, else UK wage bracket from DOB."""
        rate = employee.get("hourly_rate") or 0
        if rate > 0:
            return rate
        dob = employee.get("date_of_birth")
        if not dob or not self.wage_brackets or not get_rate_for_date:
            return 0
        resolved = get_rate_for_date(date_str, dob, self.wage_brackets)
        return float(resolved) if resolved is not None else 0
    
    def calculate_tiered_commission(self, total_sales: float, tiers: List[Dict]) -> float:
        """Calculate tiered commission based on sales tiers"""
        commission = 0.0
        
        for tier in tiers:
            threshold = tier.get('threshold', 0)
            rate = tier.get('rate', 0)
            max_sales = tier.get('max', float('inf'))
            
            if total_sales <= threshold:
                break
            
            sales_in_tier = min(total_sales, max_sales) - threshold
            if sales_in_tier > 0:
                commission += sales_in_tier * rate
        
        return commission
    
    def calculate_molly_commission(self, total_sales: float) -> float:
        """Calculate Molly's commission (30% or 35% of net sales based on threshold)"""
        if total_sales <= 0:
            return 0.0
        
        # Net sales = 80% of total
        net_sales = total_sales * 0.80
        
        # Determine rate based on total sales threshold
        rate = 0.30 if total_sales <= 1500 else 0.35
        
        return net_sales * rate
    
    def calculate_rebecca_commission(self, total_sales: float, tiers: List[Dict]) -> float:
        """Calculate Rebecca's NET commission (tiered based on total, applied to net)"""
        if total_sales <= 0:
            return 0.0
        
        # Determine tier rate based on total sales
        tier_rate = 0.30
        for tier in sorted(tiers, key=lambda x: x.get('threshold', 0), reverse=True):
            if total_sales >= tier.get('threshold', 0):
                tier_rate = tier.get('rate', 0.30)
                break
        
        # Apply rate to net sales (80% of total)
        net_sales = total_sales * 0.80
        return net_sales * tier_rate
    
    def calculate_progressive_tiered_commission(self, total_sales: float, tiers: List[Dict]) -> float:
        """Calculate progressive tiered commission (like tax brackets) - Andreea"""
        if total_sales <= 0:
            return 0.0
        
        # Sort tiers by threshold
        sorted_tiers = sorted(tiers, key=lambda x: x.get('threshold', 0))
        commission = 0.0
        remaining_sales = total_sales
        
        for i, tier in enumerate(sorted_tiers):
            if remaining_sales <= 0:
                break
            
            threshold = tier.get('threshold', 0)
            rate = tier.get('rate', 0)
            
            # Get next tier threshold
            next_threshold = sorted_tiers[i + 1].get('threshold', float('inf')) if i + 1 < len(sorted_tiers) else float('inf')
            
            # Only calculate if total sales reached this tier
            if total_sales >= threshold:
                tier_sales = min(remaining_sales, next_threshold - threshold)
                if tier_sales > 0:
                    commission += tier_sales * rate
                    remaining_sales -= tier_sales
        
        return commission
    
    def calculate_flat_rate_tiered_commission(self, total_sales: float, tiers: List[Dict]) -> float:
        """Calculate flat rate tiered commission (entire sale at tier rate) - Nili, Mayu"""
        if total_sales <= 0:
            return 0.0
        
        # Find the highest tier that applies
        applicable_tier = tiers[0] if tiers else {}
        for tier in sorted(tiers, key=lambda x: x.get('threshold', 0), reverse=True):
            if total_sales >= tier.get('threshold', 0):
                applicable_tier = tier
                break
        
        rate = applicable_tier.get('rate', 0)
        return total_sales * rate
    
    def calculate_eddie_commission(self, total_sales: float, tiers: List[Dict]) -> float:
        """Calculate Eddie's commission (tier determined by TOTAL, applied to NET sales)"""
        if total_sales <= 0:
            return 0.0
        
        # Determine tier rate based on TOTAL sales
        tier_rate = 0.30
        for tier in sorted(tiers, key=lambda x: x.get('threshold', 0), reverse=True):
            if total_sales >= tier.get('threshold', 0):
                tier_rate = tier.get('rate', 0.30)
                break
        
        # Apply rate to NET sales (80% of total)
        net_sales = total_sales * 0.80
        return net_sales * tier_rate

    def _isaac_daily_transport(self, employee: Dict, sales: float, addl_sales: float) -> float:
        """
        Daily transport when Sales + positive Add'l Sales >= threshold.
        Negative Add'l Sales (refunds) are ignored for the threshold — they do not reduce eligibility.
        """
        daily_transport = float(employee.get('daily_transport', 0) or 0)
        if daily_transport <= 0:
            return 0.0
        min_sales_raw = employee.get('transport_min_daily_sales', 400)
        try:
            min_sales = float(min_sales_raw)
        except (TypeError, ValueError):
            min_sales = 400.0
        positive_addl = max(0.0, float(addl_sales or 0))
        qualifying_sales = float(sales or 0) + positive_addl
        if qualifying_sales < min_sales:
            return 0.0
        return daily_transport

    @staticmethod
    def _sales_milestone_bonus(employee: Dict, adjusted_sales: float, month_name: str) -> float:
        """Highest non-cumulative sales bonus tier for the month (from Sales Bonus Thresholds)."""
        bonuses = employee.get(f"{month_name}_bonuses", [])
        if not bonuses:
            return 0.0
        for bonus_tier in sorted(bonuses, key=lambda x: x.get('sales_threshold', 0), reverse=True):
            if adjusted_sales >= bonus_tier.get('sales_threshold', 0):
                return float(bonus_tier.get('bonus_amount', 0) or 0)
        return 0.0
    
    def calculate_alex_commission(self, total_sales: float, date: str, employee: Dict) -> float:
        """Calculate Alex's commission based on date (old vs new structure)"""
        if total_sales <= 0:
            return 0.0
        
        record_date = datetime.strptime(date, '%Y-%m-%d')
        old_structure_date = datetime.strptime(employee.get('old_structure', {}).get('effective_date', '2025-11-01'), '%Y-%m-%d')
        new_structure_date = datetime.strptime(employee.get('new_structure', {}).get('effective_date', '2025-11-04'), '%Y-%m-%d')
        
        if record_date < new_structure_date:
            # Old structure: Flat 27% commission
            old_structure = employee.get('old_structure', {})
            commission_rate = old_structure.get('commission_rate', 0.27)
            return total_sales * commission_rate
        else:
            # New structure: Tiered commission
            new_structure = employee.get('new_structure', {})
            tiers = new_structure.get('commission_tiers', [])
            if total_sales > 1500:
                # Find tier 2 (27% for £1,501+)
                for tier in tiers:
                    if tier.get('threshold', 0) == 1500:
                        return total_sales * tier.get('rate', 0.27)
            else:
                # Tier 1 (25% for £0-£1,500)
                for tier in tiers:
                    if tier.get('threshold', 0) == 0:
                        return total_sales * tier.get('rate', 0.25)
        
        return 0.0
    
    def calculate_daily_payment(self, employee_name: str, hours: float, sales: float, 
                               addl_sales: float, date: str) -> Dict:
        """Calculate payment for a single day"""
        # Try case-insensitive lookup
        employee = self.employee_config.get(employee_name, {})
        if not employee:
            # Try case-insensitive match
            emp_name_lower = employee_name.lower()
            for key, value in self.employee_config.items():
                if key.lower() == emp_name_lower:
                    employee = value
                    break
        
        # Warn if employee not found in config
        if not employee:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Employee '{employee_name}' not found in config - using defaults (hourly_only, rate=0)")
            logger.debug(f"Available employees: {list(self.employee_config.keys())[:10]}...")
        
        payment_type = employee.get('payment_type', 'hourly_only')
        payment_type = (payment_type or "").lower().replace(" ", "_") if isinstance(payment_type, str) else payment_type
        hourly_rate = self._resolve_hourly_rate(employee, date)
        
        total_sales = sales + addl_sales
        
        result = {
            'Employee': employee_name,
            'Date': date,
            'Hours': hours,
            'Sales': sales,
            'AddlSales': addl_sales,
            'HrlyRate': hourly_rate,
            'Base': 0.0,
            'Commission': 0.0,
            'PaymentType': payment_type
        }
        
        if payment_type == 'hourly_only' or payment_type == 'manager':
            result['Base'] = hours * hourly_rate
            result['Commission'] = 0.0
            result['PaymentType'] = 'HourlyOnly'
        
        elif payment_type == 'sales_only':
            # Sales count toward shop totals; pay is external/not calculated here (e.g. manager with special arrangement)
            result['Base'] = 0.0
            result['Commission'] = 0.0
            result['PaymentType'] = 'SalesOnly'
        
        elif payment_type == 'tiered_commission':
            # Tuba's case - calculate both hourly and commission
            hourly_pay = hours * hourly_rate
            commission = self.calculate_tiered_commission(
                total_sales, 
                employee.get('commission_tiers', [])
            )
            
            result['Base'] = hourly_pay
            result['Commission'] = commission
            result['PaymentType'] = 'MonthlyMaxLater'
        
        elif payment_type == 'molly_commission':
            # Molly's case - commission only
            commission = self.calculate_molly_commission(total_sales)
            result['Base'] = 0.0
            result['Commission'] = commission
            result['PaymentType'] = 'MollyCommission'
        
        elif payment_type == 'net_commission_tiered':
            # Rebecca's case - NET commission tiered
            commission = self.calculate_rebecca_commission(
                total_sales,
                employee.get('commission_tiers', [])
            )
            result['Base'] = 0.0
            result['Commission'] = commission
            result['PaymentType'] = 'NetCommissionTiered'

        elif payment_type == 'isaac_package':
            # Isaac: tiered commission on gross sales + conditional daily transport
            commission = self.calculate_flat_rate_tiered_commission(
                total_sales,
                employee.get('commission_tiers', [])
            )
            result['Base'] = self._isaac_daily_transport(employee, sales, addl_sales)
            result['Commission'] = commission
            result['PaymentType'] = 'IsaacPackage'
        
        elif payment_type == 'commission_only':
            # Simple commission only (Codruta, Isaac, Shany)
            commission_rate = employee.get('commission_rate', 0)
            commission = total_sales * commission_rate
            result['Base'] = 0.0
            result['Commission'] = commission
            result['PaymentType'] = 'CommissionOnly'

        elif payment_type == 'dave_package':
            # Daily: personal sales % only; prorated base + shop % on range are monthly
            commission_rate = employee.get('commission_rate')
            if commission_rate is None or commission_rate == '':
                commission_rate = 0.10
            commission_rate = float(commission_rate)
            commission = total_sales * commission_rate
            result['Base'] = 0.0
            result['Commission'] = commission
            result['PaymentType'] = 'DavePackage'
        
        elif payment_type == 'progressive_tiered_commission':
            # Progressive tiered commission (Andreea)
            commission = self.calculate_progressive_tiered_commission(
                total_sales,
                employee.get('commission_tiers', [])
            )
            result['Base'] = 0.0
            result['Commission'] = commission
            result['PaymentType'] = 'ProgressiveTieredCommission'
        
        elif payment_type == 'hybrid_daily_max':
            # Hybrid: Calculate both hourly and commission (Roim, Esmaya, Shahar, Bir-ra)
            hourly_pay = hours * hourly_rate
            commission = self.calculate_progressive_tiered_commission(
                total_sales,
                employee.get('commission_tiers', [])
            )
            result['Base'] = hourly_pay
            result['Commission'] = commission
            result['PaymentType'] = 'HybridDailyMax'
        
        elif payment_type == 'flat_rate_tiered_commission':
            # Flat rate tiered commission (Nili)
            commission = self.calculate_flat_rate_tiered_commission(
                total_sales,
                employee.get('commission_tiers', [])
            )
            result['Base'] = 0.0
            result['Commission'] = commission
            result['PaymentType'] = 'FlatRateTieredCommission'
        
        elif payment_type == 'flat_rate_tiered_commission_with_transport':
            # Flat rate tiered with transport (Mayu, Eddie)
            employee_name_lower = employee_name.lower()
            
            if employee_name_lower == 'eddie':
                # Eddie: Special NET sales calculation
                commission = self.calculate_eddie_commission(
                    total_sales,
                    employee.get('commission_tiers', [])
                )
                # Transport is calculated monthly, not daily
                result['Base'] = 0.0
            else:
                # Mayu: Standard flat rate + daily transport
                commission = self.calculate_flat_rate_tiered_commission(
                    total_sales,
                    employee.get('commission_tiers', [])
                )
                daily_transport = employee.get('daily_transport', 0)
                result['Base'] = daily_transport
            
            result['Commission'] = commission
            result['PaymentType'] = 'FlatRateTieredWithTransport'
        
        elif payment_type == 'alex_hybrid':
            # Alex's hybrid structure (date-based)
            commission = self.calculate_alex_commission(total_sales, date, employee)
            result['Base'] = 0.0  # Transport and rent calculated monthly
            result['Commission'] = commission
            # Determine which structure based on date
            record_date = datetime.strptime(date, '%Y-%m-%d')
            new_structure_date = datetime.strptime(employee.get('new_structure', {}).get('effective_date', '2025-11-04'), '%Y-%m-%d')
            if record_date < new_structure_date:
                result['PaymentType'] = 'AlexOldStructure'
            else:
                result['PaymentType'] = 'AlexNewStructure'
        
        # Round all monetary/numeric values to 2 decimal places
        for key in ('Hours', 'Sales', 'AddlSales', 'HrlyRate', 'Base', 'Commission'):
            if key in result and isinstance(result[key], (int, float)):
                result[key] = round(float(result[key]), 2)
        return result
    
    def calculate_monthly_summary(
        self,
        daily_records: List[Dict],
        shop_daily_sales_totals: Optional[Dict[str, float]] = None,
    ) -> Dict:
        """Calculate monthly summary for an employee.

        shop_daily_sales_totals: date (YYYY-MM-DD) -> sum of Sales+AddlSales for that day across
        the whole report. For dave_package: shop % applies to **total shop sales on every calendar day**
        from Dave's first clock-in through last clock-in (inclusive), including days he did not work
        (missing days in the file count as 0 for that day).
        """
        if not daily_records:
            return {}
        
        employee_name = daily_records[0]['Employee']
        employee = self.employee_config.get(employee_name, {})
        bonus_info = self.bonus_config.get(employee_name, {})
        payment_type = employee.get('payment_type', 'hourly_only')
        payment_type = (payment_type or "").lower().replace(" ", "_") if isinstance(payment_type, str) else payment_type
        first_date = daily_records[0].get('Date', '')
        advance = employee.get('advance', 0)
        
        # Calculate totals
        total_hours = sum(r.get('Hours', 0) for r in daily_records)
        total_sales = sum(r.get('Sales', 0) for r in daily_records)
        total_addl_sales = sum(r.get('AddlSales', 0) for r in daily_records)
        total_commission = sum(r.get('Commission', 0) for r in daily_records)
        adjusted_sales = total_sales + total_addl_sales
        
        # Hours salary: sum (hours × rate) per day so mid-month wage bracket changes are correct
        hours_salary = sum(
            r.get('Hours', 0) * (r.get('HrlyRate', 0) or 0)
            for r in daily_records
        )
        # Effective rate for display and manual hours (weighted avg when rate varies by day)
        effective_hourly_rate = hours_salary / total_hours if total_hours > 0 else self._resolve_hourly_rate(employee, first_date)
        
        # Worked days (days with hours > 0)
        worked_days = len([r for r in daily_records if r.get('Hours', 0) > 0.001])
        avg_sales_per_day = total_sales / worked_days if worked_days > 0 else 0
        
        # Calculate bonuses
        total_bonus = sum([
            bonus_info.get('dailySalesBonus', 0),
            bonus_info.get('firstLastHourBonus', 0),
            bonus_info.get('socialMediaBonus', 0),
            bonus_info.get('managementBonus', 0),
            bonus_info.get('managementConsistencyBonus', 0),
            bonus_info.get('transportFuel', 0),
            bonus_info.get('personalSalesBonus', 0),
            bonus_info.get('extraBonus', 0),
            bonus_info.get('dailyAllowance', 0)
        ])
        
        manual_hours = bonus_info.get('manualHours', 0)
        manual_hours_pay = manual_hours * effective_hourly_rate if effective_hourly_rate > 0 else 0
        deductions = bonus_info.get('deductions', 0)
        rent = bonus_info.get('rent', 0)
        
        # Initialize variables that may be used in summary
        monthly_max = 0.0
        method = None
        alex_transport = 0.0
        alex_rent = 0.0
        isaac_transport_total = 0.0
        isaac_sales_bonus = 0.0

        # Optional breakdown for payment_type dave_package (filled in that branch)
        dave_shop_range_sales = 0.0
        dave_shop_commission = 0.0
        dave_personal_commission = 0.0
        dave_range_first = ''
        dave_range_last = ''
        
        if payment_type == 'molly_commission':
            # Molly: Commission + manual hours + bonus - deductions - rent
            base_payment = total_commission + manual_hours_pay + total_bonus
            final_payment = base_payment - deductions - rent - advance
        
        elif payment_type == 'tiered_commission':
            # Tuba: Monthly max of Hourly vs Commission + bonus + manual hours - deductions - rent
            monthly_max = max(hours_salary, total_commission)
            base_payment = monthly_max + total_bonus + manual_hours_pay
            final_payment = base_payment - deductions - rent - advance
            method = 'Hourly' if monthly_max == hours_salary else 'Commission'
        
        elif payment_type == 'net_commission_tiered':
            # Rebecca: Commission + manual hours + bonus - deductions
            base_payment = total_commission + manual_hours_pay + total_bonus
            final_payment = base_payment - deductions - advance

        elif payment_type == 'isaac_package':
            # Isaac: Commission + daily transport + sales milestone + bonus + manual hours - deductions
            isaac_transport_total = sum(r.get('Base', 0) or 0 for r in daily_records)
            record_date = datetime.strptime(daily_records[0]['Date'], '%Y-%m-%d')
            month_name = record_date.strftime('%B').lower()
            isaac_sales_bonus = self._sales_milestone_bonus(employee, adjusted_sales, month_name)
            base_payment = (
                total_commission + isaac_transport_total + isaac_sales_bonus
                + total_bonus + manual_hours_pay
            )
            final_payment = base_payment - deductions - advance
        
        elif payment_type == 'dave_package':
            # Prorated base + personal % + shop % on sum of shop daily totals for every calendar day
            # from first clock-in through last clock-in (inclusive), even if Dave had days off in between.
            monthly_base = float(employee.get('monthly_base', 2250))
            base_ref_days = float(employee.get('base_reference_days', 24))
            if base_ref_days <= 0:
                base_ref_days = 24
            shop_rate_raw = employee.get('shop_commission_rate')
            if shop_rate_raw is None or shop_rate_raw == '':
                shop_rate = 0.01
            else:
                shop_rate = float(shop_rate_raw)

            prorated_base = (monthly_base / base_ref_days) * worked_days
            dave_personal_commission = total_commission
            dates_worked = sorted({
                str(r.get('Date', ''))[:10]
                for r in daily_records
                if r.get('Hours', 0) > 0.001 and r.get('Date')
            })
            shop_sales_in_range = 0.0
            if len(dates_worked) >= 1:
                dave_range_first = dates_worked[0]
                dave_range_last = dates_worked[-1]
                totals_map = shop_daily_sales_totals or {}
                for d in self._dates_inclusive(dave_range_first, dave_range_last):
                    shop_sales_in_range += float(totals_map.get(d, 0) or 0)
            dave_shop_range_sales = shop_sales_in_range
            dave_shop_commission = shop_sales_in_range * shop_rate
            total_commission = dave_personal_commission + dave_shop_commission
            hours_salary = prorated_base
            base_payment = prorated_base + total_commission + total_bonus + manual_hours_pay
            final_payment = base_payment - deductions - rent - advance

        elif payment_type == 'commission_only':
            # Commission only: Commission + bonus + manual hours - deductions - rent
            base_payment = total_commission + total_bonus + manual_hours_pay
            final_payment = base_payment - deductions - rent - advance
        
        elif payment_type == 'progressive_tiered_commission':
            # Progressive tiered: Commission + bonus + manual hours - deductions - rent
            base_payment = total_commission + total_bonus + manual_hours_pay
            final_payment = base_payment - deductions - rent - advance
        
        elif payment_type == 'hybrid_daily_max':
            # Hybrid daily max: Monthly max of Hourly vs Commission + bonus + manual hours - deductions - rent
            monthly_max = max(hours_salary, total_commission)
            base_payment = monthly_max + total_bonus + manual_hours_pay
            final_payment = base_payment - deductions - rent - advance
            method = 'Hourly' if monthly_max == hours_salary else 'Commission'
        
        elif payment_type == 'flat_rate_tiered_commission':
            # Flat rate tiered: Commission + bonus + manual hours - deductions - rent
            base_payment = total_commission + total_bonus + manual_hours_pay
            final_payment = base_payment - deductions - rent - advance
        
        elif payment_type == 'flat_rate_tiered_commission_with_transport':
            # Flat rate with transport: Commission + transport + bonus + manual hours - deductions - rent
            employee_name_lower = employee_name.lower()
            if employee_name_lower == 'eddie':
                # Eddie: Commission + transport (calculated monthly) + sales bonus + bonus + manual hours - deductions
                # Transport is calculated as daily_transport * worked_days
                daily_transport = employee.get('daily_transport', 0)
                transport_total = daily_transport * worked_days
                
                # Calculate Eddie's sales bonus based on month
                record_date = datetime.strptime(daily_records[0]['Date'], '%Y-%m-%d')
                month_name = record_date.strftime('%B').lower()
                
                sales_bonus = 0.0
                if month_name == 'november':
                    bonuses = employee.get('november_bonuses', [])
                    for bonus_tier in sorted(bonuses, key=lambda x: x.get('sales_threshold', 0), reverse=True):
                        if adjusted_sales >= bonus_tier.get('sales_threshold', 0):
                            sales_bonus = bonus_tier.get('bonus_amount', 0)
                            break
                elif month_name == 'december':
                    bonuses = employee.get('december_bonuses', [])
                    for bonus_tier in sorted(bonuses, key=lambda x: x.get('sales_threshold', 0), reverse=True):
                        if adjusted_sales >= bonus_tier.get('sales_threshold', 0):
                            sales_bonus = bonus_tier.get('bonus_amount', 0)
                            break
                
                base_payment = total_commission + transport_total + sales_bonus + total_bonus + manual_hours_pay
                final_payment = base_payment - deductions - advance
            else:
                # Mayu: Commission + transport + bonus + manual hours - deductions - rent
                daily_transport = employee.get('daily_transport', 0)
                transport_total = daily_transport * worked_days
                base_payment = total_commission + transport_total + total_bonus + manual_hours_pay
                final_payment = base_payment - deductions - rent - advance
        
        elif payment_type == 'alex_hybrid':
            # Alex: Transport + Commission + Base (rent) + bonus + manual hours - deductions
            transport = employee.get('transport', 0)
            alex_transport = transport
            
            # Check if any days use new structure
            new_structure_date = datetime.strptime(employee.get('new_structure', {}).get('effective_date', '2025-11-04'), '%Y-%m-%d')
            has_new_structure = any(
                datetime.strptime(r['Date'], '%Y-%m-%d') >= new_structure_date 
                for r in daily_records
            )
            
            rent_amount = 0.0
            if has_new_structure:
                # Calculate rent based on total sales
                rent_tiers = employee.get('new_structure', {}).get('rent_tiers', [])
                for rent_tier in sorted(rent_tiers, key=lambda x: x.get('sales_threshold', 0), reverse=True):
                    if adjusted_sales >= rent_tier.get('sales_threshold', 0):
                        rent_amount = rent_tier.get('rent_amount', 0)
                        break
            alex_rent = rent_amount
            
            base_payment = transport + total_commission + rent_amount + total_bonus + manual_hours_pay
            final_payment = base_payment - deductions - advance
        
        elif payment_type == 'sales_only':
            # Pay is external/not calculated here; sales still count toward shop totals
            base_payment = 0.0
            final_payment = 0.0
        
        else:
            # All other staff: Hourly + Bonus + Manual Hours - Deductions - Rent
            base_payment = hours_salary + total_bonus + manual_hours_pay
            final_payment = base_payment - deductions - rent - advance
        
        # Wage bracket breakdown: when rate varies mid-month (e.g. employee turns 18)
        summary_wage_breakdown = []
        rate_to_days = {}  # rate -> [(date, hours), ...]
        for r in daily_records:
            rate = r.get('HrlyRate', 0) or 0
            hrs = r.get('Hours', 0)
            if hrs <= 0 or rate <= 0:
                continue
            date = r.get('Date', '')
            if rate not in rate_to_days:
                rate_to_days[rate] = []
            rate_to_days[rate].append((date, hrs))
        if len(rate_to_days) >= 2:
            for rate in sorted(rate_to_days.keys()):
                days = rate_to_days[rate]
                dates = sorted([d[0] for d in days])
                period_hours = sum(d[1] for d in days)
                period_pay = period_hours * rate
                summary_wage_breakdown.append({
                    'date_from': dates[0],
                    'date_to': dates[-1],
                    'hours': round(period_hours, 2),
                    'rate': rate,
                    'pay': round(period_pay, 2),
                })
            # Sort by date_from so periods appear in chronological order
            summary_wage_breakdown.sort(key=lambda x: x['date_from'])
        
        # Individual bonus breakdown for detailed view
        if payment_type == 'alex_hybrid':
            transport_for_breakdown = alex_transport
        elif payment_type == 'isaac_package':
            transport_for_breakdown = isaac_transport_total
        else:
            transport_for_breakdown = bonus_info.get('transportFuel', 0)
        bonus_breakdown = {
            'DailySalesBonus': bonus_info.get('dailySalesBonus', 0),
            'FirstLastHourBonus': bonus_info.get('firstLastHourBonus', 0),
            'SocialMediaBonus': bonus_info.get('socialMediaBonus', 0),
            'ManagementBonus': bonus_info.get('managementBonus', 0),
            'ManagementConsistencyBonus': bonus_info.get('managementConsistencyBonus', 0),
            'TransportFuel': transport_for_breakdown,
            'PersonalSalesBonus': bonus_info.get('personalSalesBonus', 0),
            'ExtraBonus': bonus_info.get('extraBonus', 0),
            'DailyAllowance': bonus_info.get('dailyAllowance', 0)
        }
        
        # For alex_hybrid, use rent from sales tiers; otherwise use bonus_info
        rent_for_summary = alex_rent if payment_type == 'alex_hybrid' else rent
        summary = {
            'Employee': employee_name,
            'WorkedDays': worked_days,
            'WorkedHours': round(total_hours, 2),
            'Sales': round(total_sales, 2),
            'AddlSales': round(total_addl_sales, 2),
            'AdjustedSales': round(adjusted_sales, 2),
            'AvgSalePerDay': round(avg_sales_per_day, 2),
            'RatePerHour': effective_hourly_rate,
            'HoursSalary': round(hours_salary, 2),
            'TotalCommission': round(total_commission, 2),
            'TotalBonus': round(total_bonus, 2),
            'ManualHours': manual_hours,
            'ManualHoursPay': round(manual_hours_pay, 2),
            'Deductions': deductions,
            'Rent': rent_for_summary,
            'Advance': advance,
            'FinalPayment': round(final_payment, 2),
            'PaymentType': payment_type,
            'BonusBreakdown': bonus_breakdown,  # Include detailed bonus breakdown
            'WageBracketBreakdown': summary_wage_breakdown,  # When rate varies mid-month
        }
        
        if payment_type == 'tiered_commission':
            summary['MonthlyMaxMethod'] = method
            summary['MonthlyMaxAmount'] = round(monthly_max, 2)
        
        if payment_type == 'hybrid_daily_max':
            summary['MonthlyMaxMethod'] = method
            summary['MonthlyMaxAmount'] = round(monthly_max, 2)

        if payment_type == 'dave_package':
            summary['ProratedBasePay'] = summary['HoursSalary']
            summary['ShopRangeSalesGross'] = round(dave_shop_range_sales, 2)
            summary['ShopRangeCommission'] = round(dave_shop_commission, 2)
            summary['PersonalCommission'] = round(dave_personal_commission, 2)
            summary['ShopRangeFirstDate'] = dave_range_first
            summary['ShopRangeLastDate'] = dave_range_last

        if payment_type == 'isaac_package':
            summary['IsaacTransportTotal'] = round(isaac_transport_total, 2)
            summary['SalesMilestoneBonus'] = round(isaac_sales_bonus, 2)
        
        return summary
