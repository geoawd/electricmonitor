from datetime import date

ENERGY_RATES = {
    "2025-01-01": {
        "standard": {
            "unit_rate": 29.44,
            "standing_charge": 0.0,
        },
        "peak_offpeak": {
            "peak_rate": 34.18,
            "offpeak_rate": 16.34,
            "standing_charge": 13.1,
        },
        "ev_anytime": {
            "unit_rate": 27.93,
            "standing_charge": 13.1,
        }
    }
}

def get_rates_for_date(target_date: date) -> dict:
    """Get the applicable rates for a given date"""
    # Convert all keys to dates for comparison
    rate_dates = [date.fromisoformat(d) for d in ENERGY_RATES.keys()]
    # Find the most recent rate before or on the target date
    applicable_date = max([d for d in rate_dates if d <= target_date], default=None)
    
    if applicable_date:
        return ENERGY_RATES[applicable_date.isoformat()]
    return None