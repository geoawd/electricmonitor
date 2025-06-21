from flask import Flask, render_template, request
import sqlite3
from datetime import datetime
import os
from config.energy_rates import get_rates_for_date
import re
import json

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

def pulses_to_kwh(pulses):
    return pulses / 3200

def get_daily_energy_split(cursor, start_date, days_back=7):
    """Get daily energy split between peak and off-peak hours"""
    cursor.execute("""
        SELECT 
            strftime('%Y-%m-%d', hour_timestamp, 'localtime') as day,
            SUM(CASE 
                WHEN strftime('%H', hour_timestamp, 'localtime') >= '02' 
                AND strftime('%H', hour_timestamp, 'localtime') < '09' 
                THEN pulse_count ELSE 0 END) as off_peak_pulses,
            SUM(CASE 
                WHEN strftime('%H', hour_timestamp, 'localtime') < '02' 
                OR strftime('%H', hour_timestamp, 'localtime') >= '09' 
                THEN pulse_count ELSE 0 END) as peak_pulses
        FROM hourly_pulses
        WHERE date(hour_timestamp, 'localtime') 
            BETWEEN date(?, ?) AND date(?)
        GROUP BY day
        ORDER BY day
    """, (start_date, f'-{days_back} days', start_date))
    
    # Convert pulse counts to kWh before returning
    raw_data = cursor.fetchall()
    return [(day, pulses_to_kwh(off_peak), pulses_to_kwh(peak)) 
            for day, off_peak, peak in raw_data]

def get_all_energy_data(start_date=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    if not start_date:
        start_date = datetime.now().strftime('%Y-%m-%d')

    # Get minute data, hourly data, date range, and daily split in one connection
    cursor.execute("""
        WITH minute_data AS (
            SELECT strftime('%Y-%m-%d %H:%M', timestamp, 'localtime') as minute,
                   COUNT(*) as pulse_count
            FROM pulses
            WHERE date(timestamp, 'localtime') = ?
            GROUP BY minute
        ),
        hourly_data AS (
            SELECT strftime('%Y-%m-%d %H:00', hour_timestamp, 'localtime') as hour,
                   pulse_count
            FROM hourly_pulses
            WHERE date(hour_timestamp, 'localtime') BETWEEN date(?, '-6 days') AND date(?)
        ),
        date_range AS (
            SELECT MIN(date(timestamp)) as min_date, 
                   MAX(date(timestamp)) as max_date 
            FROM pulses
        )
        SELECT 
            'minute' as type, minute as timestamp, pulse_count, NULL, NULL, NULL
        FROM minute_data
        UNION ALL
        SELECT 
            'hour' as type, hour, pulse_count, NULL, NULL, NULL
        FROM hourly_data
        UNION ALL
        SELECT 
            'range' as type, NULL, NULL, NULL, NULL, 
            json_object('min', min_date, 'max', max_date)
        FROM date_range;
    """, (start_date, start_date, start_date))
    
    results = cursor.fetchall()
    
    # Get daily split using shared function - but extend it to get 7 days for detailed data
    daily_split = get_daily_energy_split(cursor, start_date, 13)
    
    # Get detailed daily data with costs (7 days from start_date)
    cursor.execute("""
        SELECT 
            strftime('%Y-%m-%d', hour_timestamp, 'localtime') as day,
            SUM(CASE 
                WHEN strftime('%H', hour_timestamp, 'localtime') >= '02' 
                AND strftime('%H', hour_timestamp, 'localtime') < '09' 
                THEN pulse_count ELSE 0 END) as off_peak_pulses,
            SUM(CASE 
                WHEN strftime('%H', hour_timestamp, 'localtime') < '02' 
                OR strftime('%H', hour_timestamp, 'localtime') >= '09' 
                THEN pulse_count ELSE 0 END) as peak_pulses,
            SUM(pulse_count) as total_pulses
        FROM hourly_pulses
        WHERE date(hour_timestamp, 'localtime') 
            BETWEEN date(?, '-13 days') AND date(?)
        GROUP BY day
        ORDER BY day
    """, (start_date, start_date))
    
    detailed_daily_data = cursor.fetchall()
    conn.close()

    # Process results
    minute_data = []
    hourly_data = []
    date_range = None

    for row in results:
        if row[0] == 'minute':
            minute_data.append((row[1], row[2]))
        elif row[0] == 'hour':
            hourly_data.append((row[1], row[2]))
        elif row[0] == 'range':
            date_range = json.loads(row[5])

    # Process detailed daily data with cost calculations
    consolidated_data = []
    for day_data in detailed_daily_data:
        day, off_peak_pulses, peak_pulses, total_pulses = day_data
        
        # Get applicable rates for this day
        date_obj = datetime.strptime(day, '%Y-%m-%d').date()
        rates = get_rates_for_date(date_obj)
        
        # Calculate kWh values
        off_peak_kwh = pulses_to_kwh(off_peak_pulses)
        peak_kwh = pulses_to_kwh(peak_pulses)
        total_kwh = pulses_to_kwh(total_pulses)
        
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

    return {
        'minute_data': minute_data,
        'minute_kwh': [(m[0], pulses_to_kwh(m[1])) for m in minute_data],
        'hourly_data': hourly_data,
        'hourly_kwh': [(h[0], pulses_to_kwh(h[1])) for h in hourly_data],
        'daily_peak_split': daily_split,
        'date_range': (date_range['min'], date_range['max']),
        'consolidated_data': consolidated_data  # Add this to the return
    }

@app.route('/')
def detailed():
    # Get and validate date parameter
    date_param = request.args.get('date')
    if date_param is not None and not is_valid_date(date_param):
        return "Invalid date format. Use YYYY-MM-DD", 400
    
    selected_date = date_param or datetime.now().strftime('%Y-%m-%d')
    
    # Get all data in one query - now includes consolidated_data
    data = get_all_energy_data(selected_date)
    
    return render_template('detailed.html',
                         minute_data=data['minute_data'],
                         hourly_data=data['hourly_data'],
                         daily_peak_split=data['daily_peak_split'],
                         minute_kwh=data['minute_kwh'],
                         hourly_kwh=data['hourly_kwh'],
                         selected_date=selected_date,
                         date_range=data['date_range'],
                         consolidated_data=data['consolidated_data'])
    
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)