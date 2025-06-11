# Electric meter monitoring with a Raspberry Pi Zero and LDR.
This is a simple electricity monitor that uses an LDR and a 1uf capacitor to count pulses on an electric meter and display the data on a dashboard using Flask and chart.js

## LDR Energy Monitor (ldr.py)
A Python script that monitors electricity usage through a Light Dependent Resistor (LDR) connected to a Raspberry Pi's GPIO pins. It detects LED pulses from a smart meter and stores them in a SQLite database for analysis.

### Features
- Real-time monitoring of smart meter LED pulses
- Automatic pulse detection and storage
- SQLite database integration
- Configurable GPIO pin (default: BCM 24)
- Verbose mode for debugging
- Graceful shutdown with Ctrl+C

### Technical Details
- Uses `gpiozero` library for sensor input
- Stores timestamps in SQLite database
- Configurable sensor threshold (default: 0.01)
- Database schema:
  - `pulses` table with auto-incrementing ID and timestamp
- Automatic database creation if not exists

### Hardware Requirements
- Raspberry Pi
- LDR (Light Dependent Resistor)
- Electric meter with LED pulse output (this is configured for 3200 pulses/kWh)

### Installation
1. Connect LDR to GPIO Pin 24 (BCM) / Physical Pin 64
2. Install required packages:
   ```bash
   pip install gpiozero


## Energy Monitor Web Interface (webview.py)
This Flask application provides a web interface for monitoring and analyzing electrical energy usage data. It offers:

### Key Features
- Real-time energy usage monitoring
- Historical data visualization
- Multiple tariff comparisons:
  - Standard rate
  - EV Anytime rate
  - Peak/Off-peak split rate
- Interactive charts with zoom capabilities:
  - Minute-by-minute usage (24 hours)
  - Hourly usage (7 days)
  - Daily peak/off-peak split
- Cost calculations based on different tariff structures
- Date-based navigation

### Technical Details
- Built with Flask
- Uses SQLite for data storage
- Timezone aware (supports BST/GMT transitions)
- Data is sampled at 3200 pulses per kWh
- Interactive charts using Chart.js
- RESTful API endpoints for data retrieval

The application reads pulse data from a SQLite database (`energy.db`) and provides both visual and numerical analysis of energy consumption patterns.

## Energy Rate Configuration (energy_rates.py)
Configuration module that defines electricity tariff rates for different time periods. Supports multiple rate structures including:

### Supported Tariffs
- **Standard Rate**: Single unit rate with no standing charge
- **Peak/Off-peak Rate**: Different rates for peak and off-peak hours with standing charge
- **EV Anytime Rate**: Special electric vehicle rate with standing charge

### Features
- Date-based rate lookup
- Multiple tariff structure support
- Automatic selection of most recent applicable rate
- Easy configuration through Python dictionary structure

### Rate Structure Example
```python
{
    "standard": {
        "unit_rate": 29.44,      # pence per kWh
        "standing_charge": 0.0,   # pence per day
    },
    "peak_offpeak": {
        "peak_rate": 34.18,      # pence per kWh
        "offpeak_rate": 16.34,   # pence per kWh
        "standing_charge": 13.1,  # pence per day
    },
    "ev_anytime": {
        "unit_rate": 27.93,      # pence per kWh
        "standing_charge": 13.1,  # pence per day
    }
}
```

## Webpage render
![Alt text](https://github.com/geoawd/electricmonitor/blob/main/Energy%20Monitor%20-%20Detailed%20View.jpg "Electric Monitor Webpage")



