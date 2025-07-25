'''
LDR Energy Monitor
A simple script to monitor light sensor pulses using GPIO on a Raspberry Pi.
and store them in a local SQLite database.

This script uses the gpiozero library to read from a light sensor connected to GPIO pin 24.
It records the time of each pulse and stores it in a SQLite database.

Change log: Version: 0.3
-- Inserts a new pulse into the database each time light is detected.

Change log: Version: 0.4
-- added retry logic for database locking issues
-- added creation of hourly_pulses table
'''

from gpiozero import LightSensor
from datetime import datetime
import sqlite3
import os
import time

# Change GPIO Pin 24 to suit
sensor = LightSensor(24, queue_len=1, threshold=0.01)
verbose = 0
version = "0.4"

# Print startup information
print(f" LDR Energy Monitor v{version}", flush=True)
print(f" + Started [{datetime.now()}]", flush=True)
print(f" + Using GPIO Pin: {sensor.pin.number}", flush=True)

# Database path - store in same directory as script
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "energy.db")

def create_local_db():
    """Create SQLite Database if it doesn't exist"""
    try:
        conn = sqlite3.connect(DB_PATH)
        curs = conn.cursor()
        curs.execute("""
            CREATE TABLE IF NOT EXISTS pulses(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )""")
        curs.execute("""
            CREATE TABLE IF NOT EXISTS hourly_pulses(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hour_timestamp DATETIME,
                pulse_count INTEGER
            )""")
        conn.commit()
        print(f" + Database ready at {DB_PATH} [{datetime.now()}]", flush=True)
        return conn
    except sqlite3.Error as e:
        print(f" - Database Error: {e} [{datetime.now()}]", flush=True)
        return None

def store_pulse(conn, max_retries=3, retry_delay=0.1):
    """Store a single pulse with retry logic for locked database"""
    retries = 0
    while retries < max_retries:
        try:
            curs = conn.cursor()
            curs.execute("INSERT INTO pulses DEFAULT VALUES")
            conn.commit()
            if verbose > 0:
                print(f" + Pulse recorded at {datetime.now()}", flush=True)
            return True
        except sqlite3.Error as e:
            if "database is locked" in str(e):
                retries += 1
                if retries < max_retries:
                    time.sleep(retry_delay)
                    continue
            print(f" - Error storing pulse: {e} [{datetime.now()}]", flush=True)
            return False

# Initialize database connection
conn = create_local_db()
if not conn:
    print(" - Failed to initialize database. Exiting.", flush=True)
    exit(1)

# Main loop
try:
    print(" + Monitoring light sensor (Ctrl+C to exit)...", flush=True)
    
    while True:
        current_value = sensor.value
        if verbose > 0:
            print(f" + Current sensor value: {current_value:.3f}", flush=True)
        
        if current_value > sensor.threshold:
            print(f" + Light detected! Value: {current_value:.3f}", flush=True)
            store_pulse(conn)
            
            # Wait for light to go dark
            sensor.wait_for_dark()
            print(f" + Light ended. Value: {sensor.value:.3f}", flush=True)
        else:
            # Small delay to prevent CPU overload
            sensor.wait_for_light()

except KeyboardInterrupt:
    print(f"\n + Shutting down [{datetime.now()}]", flush=True)
    conn.close()