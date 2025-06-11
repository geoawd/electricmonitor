from flask import Flask, render_template, request
import sqlite3
from datetime import datetime, timedelta, timezone
import os
from collections import defaultdict
from config.energy_rates import get_rates_for_date
import re
import pytz

app = Flask(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "energy.db")

def is_valid_date(date_string):
    """Validate that string matches YYYY-MM-DD format and is a valid date"""
    if not isinstance(date_string, str):
        return False
    
    # Check format matches YYYY-MM-DD
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_string):
        return False
    
    # Verify it's a valid date
    try:
        datetime.strptime(date_string, '%Y-%m-%d')
        return True
    except ValueError:
        return False

def get_pulse_data():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT strftime('%Y-%m-%d %H:00:00', timestamp, 'localtime') as hour,
               COUNT(*) as pulse_count
        FROM pulses
        WHERE timestamp >= datetime('now', '-24 hours')
        GROUP BY hour
        ORDER BY hour
    """)
    hourly_data = cursor.fetchall()
    
    cursor.execute("""
        SELECT strftime('%Y-%m-%d', timestamp, 'localtime') as day,
               COUNT(*) as pulse_count
        FROM pulses
        WHERE timestamp >= datetime('now', '-7 days')
        GROUP BY day
        ORDER BY day
    """)
    daily_data = cursor.fetchall()
    
    conn.close()
    return hourly_data, daily_data

def get_detailed_data():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Single query to get all the peak/off-peak data
    cursor.execute("""
        SELECT 
            strftime('%Y-%m-%d', timestamp, 'localtime') as day,
            SUM(CASE 
                WHEN strftime('%H', timestamp, 'localtime') >= '02' 
                AND strftime('%H', timestamp, 'localtime') < '09' 
                THEN 1 ELSE 0 END) as off_peak_pulses,
            SUM(CASE 
                WHEN strftime('%H', timestamp, 'localtime') < '02' 
                OR strftime('%H', timestamp, 'localtime') >= '09' 
                THEN 1 ELSE 0 END) as peak_pulses,
            COUNT(*) as total_pulses
        FROM pulses
        WHERE timestamp >= datetime('now', '-7 days')
        GROUP BY day
        ORDER BY day
    """)
    
    data = cursor.fetchall()
    conn.close()
    
    # Process data for display
    consolidated_data = []
    
    for day_data in data:
        day, off_peak_pulses, peak_pulses, total_pulses = day_data
        
        # Get applicable rates for this day
        date_obj = datetime.strptime(day, '%Y-%m-%d').date()
        rates = get_rates_for_date(date_obj)
        
        # Calculate kWh values
        off_peak_kwh = off_peak_pulses / 3200
        peak_kwh = peak_pulses / 3200
        total_kwh = total_pulses / 3200
        
        # Standard rate calculations
        standard_cost = (total_kwh * rates['standard']['unit_rate']/100) + (rates['standard']['standing_charge']/100)
        
        # EV Anytime calculations
        ev_anytime_cost = (total_kwh * rates['ev_anytime']['unit_rate']/100) + (rates['ev_anytime']['standing_charge']/100)
        
        # Peak/Off-peak calculations
        off_peak_cost = off_peak_kwh * rates['peak_offpeak']['offpeak_rate']/100
        peak_cost = peak_kwh * rates['peak_offpeak']['peak_rate']/100
        ev_day_night_cost = off_peak_cost + peak_cost + (rates['peak_offpeak']['standing_charge']/100)
        
        consolidated_data.append({
            'date': day,
            'off_peak_kwh': off_peak_kwh,
            'peak_kwh': peak_kwh,
            'standard_cost': standard_cost,
            'ev_anytime_cost': ev_anytime_cost,
            'ev_day_night_cost': ev_day_night_cost
        })
    
    return consolidated_data

def get_local_timezone():
    """Get the local timezone"""
    return pytz.timezone('Europe/London')

def get_minute_data(start_date=None):
    """Get minute data for a specific day, defaults to last 24 hours"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    if start_date:
        cursor.execute("""
            SELECT strftime('%Y-%m-%d %H:%M', timestamp, 'localtime') as minute,
                   COUNT(*) as pulse_count
            FROM pulses
            WHERE date(timestamp, 'localtime') = ?
            GROUP BY minute
            ORDER BY minute
        """, (start_date,))
    else:
        cursor.execute("""
            SELECT strftime('%Y-%m-%d %H:%M', timestamp) as minute,
                   COUNT(*) as pulse_count
            FROM pulses
            WHERE timestamp >= datetime('now', '-24 hours')
            GROUP BY minute
            ORDER BY minute
        """)
    
    data = cursor.fetchall()
    conn.close()
    return data

def get_hourly_data(start_date=None, days=7):
    """Get hourly data for a specific period"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    if start_date:
        cursor.execute("""
            SELECT strftime('%Y-%m-%d %H:00', timestamp, 'localtime') as hour,
                   COUNT(*) as pulse_count
            FROM pulses
            WHERE date(timestamp, 'localtime') BETWEEN date(?, '-6 days') AND date(?)
            GROUP BY hour
            ORDER BY hour
        """, (start_date, start_date))
    else:
        cursor.execute("""
            SELECT strftime('%Y-%m-%d %H:00', timestamp, 'localtime') as hour,
                   COUNT(*) as pulse_count
            FROM pulses
            WHERE timestamp >= datetime('now', '-7 days')
            GROUP BY hour
            ORDER BY hour
        """)
    
    data = cursor.fetchall()
    conn.close()
    return data

def get_daily_peak_split(start_date=None, days=7):
    """Get daily peak/off-peak split for stacked bar chart"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    if start_date:
        query_date = start_date
    else:
        query_date = datetime.now().strftime('%Y-%m-%d')
    
    cursor.execute("""
        SELECT 
            strftime('%Y-%m-%d', timestamp) as day,
            SUM(CASE 
                WHEN strftime('%H', timestamp) >= '02' 
                AND strftime('%H', timestamp) < '09' 
                THEN 1 ELSE 0 END) / 3200.0 as off_peak_kwh,
            SUM(CASE 
                WHEN strftime('%H', timestamp) < '02' 
                OR strftime('%H', timestamp) >= '09' 
                THEN 1 ELSE 0 END) / 3200.0 as peak_kwh
        FROM pulses
        WHERE date(timestamp) BETWEEN date(?, '-6 days') AND date(?)
        GROUP BY day
        ORDER BY day
    """, (query_date, query_date))
    
    data = cursor.fetchall()
    conn.close()
    return data

@app.route('/')
def detailed():
    # Get and validate date parameter
    date_param = request.args.get('date')
    if date_param is not None and not is_valid_date(date_param):
        return "Invalid date format. Use YYYY-MM-DD", 400
    
    selected_date = date_param or datetime.now().strftime('%Y-%m-%d')
    
    # Get all the required data
    minute_data = get_minute_data(selected_date)
    hourly_data = get_hourly_data(selected_date)
    daily_peak_split = get_daily_peak_split(selected_date)
    consolidated_data = get_detailed_data()
    
    # Process data for charts
    minute_kwh = [(minute, count/3200) for minute, count in minute_data]
    hourly_kwh = [(hour, count/3200) for hour, count in hourly_data]
    
    # Get date range for datepicker min/max
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT MIN(date(timestamp)), MAX(date(timestamp)) FROM pulses")
    date_range = cursor.fetchone()
    conn.close()
    
    return render_template('detailed.html',
                         minute_data=minute_data,
                         hourly_data=hourly_data,
                         daily_peak_split=daily_peak_split,
                         minute_kwh=minute_kwh,
                         hourly_kwh=hourly_kwh,
                         selected_date=selected_date,
                         date_range=date_range,
                         consolidated_data=consolidated_data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)