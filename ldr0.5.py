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

Change log: Version: 0.5
-- Added automatic hourly pulse count updates
-- Added threading to handle pulse updates without interrupting monitoring
'''

from gpiozero import LightSensor
from datetime import datetime, timezone
import sqlite3
import os
import time
import threading
from apscheduler.schedulers.background import BackgroundScheduler

# Change GPIO Pin 24 to suit
sensor = LightSensor(24, queue_len=1, threshold=0.01)
verbose = 0
version = "0.5"

# Print startup information
print(f" LDR Energy Monitor v{version}", flush=True)
print(f" + Started [{datetime.now()}]", flush=True)
print(f" + Using GPIO Pin: {sensor.pin.number}", flush=True)

# Database path - store in same directory as script
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "energy_new.db")

def create_local_db():
    """Create SQLite Database if it doesn't exist"""
    try:
        conn = sqlite3.connect(DB_PATH)
        curs = conn.cursor()
        
        # Enable Write-Ahead Logging mode
        curs.execute("PRAGMA journal_mode=WAL")
        
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
            # Set timeout to 5 seconds
            conn = sqlite3.connect(DB_PATH, timeout=3)
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

def update_hourly_pulses(db_path, max_retries=3, retry_delay=0.1):
    """Updates the hourly_pulses table with total pulse counts using UTC/GMT timestamps"""
    retries = 0
    while retries < max_retries:
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            
            current_time = datetime.now(timezone.utc)
            current_hour = current_time.replace(minute=0, second=0, microsecond=0)
            
            # First, delete any existing entries for the current hour
            cur.execute("""
                DELETE FROM hourly_pulses 
                WHERE hour_timestamp = ?
            """, (current_hour.strftime('%Y-%m-%d %H:00:00'),))
            
            # Then insert the new count
            cur.execute("""
                INSERT INTO hourly_pulses (hour_timestamp, pulse_count)
                SELECT 
                    strftime('%Y-%m-%d %H:00:00', timestamp) as hour_timestamp,
                    COUNT(*) as pulse_count
                FROM pulses
                WHERE strftime('%Y-%m-%d %H:00:00', timestamp) = ?
                GROUP BY strftime('%Y-%m-%d %H:00:00', timestamp)
            """, (current_hour.strftime('%Y-%m-%d %H:00:00'),))
            
            conn.commit()
            
            if verbose > 0:
                print(f" + Updated hourly pulses at {current_time} UTC", flush=True)
            return True
            
        except sqlite3.Error as e:
            if "database is locked" in str(e):
                retries += 1
                if retries < max_retries:
                    time.sleep(retry_delay)
                    continue
            print(f" - Error updating hourly pulses: {e} [{datetime.now(timezone.utc)}]", flush=True)
            return False
        finally:
            if conn:
                conn.close()

def start_scheduler(db_path):
    """Starts the background scheduler for updating hourly pulses"""
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        lambda: update_hourly_pulses(db_path), 
        'cron',
        minute='15,30,45,59'
    )
    scheduler.start()
    print(f" + Hourly pulse update scheduler started [{datetime.now()}]", flush=True)
    return scheduler

# Initialize database connection
conn = create_local_db()
if not conn:
    print(" - Failed to initialize database. Exiting.", flush=True)
    exit(1)

# Start the scheduler
scheduler = start_scheduler(DB_PATH)

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
    scheduler.shutdown()
    conn.close()