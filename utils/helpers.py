"""Pure helper functions used across the Salary System app."""


def format_currency(value: float) -> str:
    """Format value as currency."""
    return f"£{value:,.2f}"


def parse_currency_input(raw) -> float:
    """Parse user input that may be a number or string like '5,000.00' or '5000'."""
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip().replace(",", "").replace(" ", "")
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0
