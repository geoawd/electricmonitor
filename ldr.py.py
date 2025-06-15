from gpiozero import LightSensor
from datetime import datetime
import sqlite3
import os
import time

# Change GPIO Pin 24 to suit
sensor = LightSensor(24, queue_len=1, threshold=0.01)
verbose = 0
version = "0.4"

# Track current hour for hourly updates
current_hour = datetime.now().replace(minute=0, second=0, microsecond=0)

# Print startup information
print(f" LDR Energy Monitor v{version}", flush=True)
print(f" + Started [{datetime.now()}]", flush=True)
print(f" + Using GPIO Pin: {sensor.pin.number} (BCM) / Physical Pin {sensor.pin.number + 40}", flush=True)

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

def update_hourly_totals(conn, hour_timestamp):
    """Store hourly totals in hourly_pulses table"""
    try:
        curs = conn.cursor()
        
        # First check if we already have an entry for this hour
        curs.execute("""
            SELECT pulse_count FROM hourly_pulses 
            WHERE hour_timestamp = ?
        """, (hour_timestamp.strftime('%Y-%m-%d %H:00:00'),))
        
        existing_entry = curs.fetchone()
        
        if existing_entry:
            # Update existing entry
            curs.execute("""
                UPDATE hourly_pulses 
                SET pulse_count = (
                    SELECT COUNT(*) FROM pulses 
                    WHERE datetime(strftime('%Y-%m-%d %H:00:00', timestamp)) = ?
                )
                WHERE hour_timestamp = ?
            """, (hour_timestamp.strftime('%Y-%m-%d %H:00:00'),
                 hour_timestamp.strftime('%Y-%m-%d %H:00:00')))
        else:
            # Create new entry
            curs.execute("""
                INSERT INTO hourly_pulses (hour_timestamp, pulse_count)
                SELECT 
                    ?,
                    COUNT(*)
                FROM pulses 
                WHERE datetime(strftime('%Y-%m-%d %H:00:00', timestamp)) = ?
            """, (hour_timestamp.strftime('%Y-%m-%d %H:00:00'),
                 hour_timestamp.strftime('%Y-%m-%d %H:00:00')))
        
        conn.commit()
        print(f" + Hourly total updated for {hour_timestamp}", flush=True)
    except sqlite3.Error as e:
        print(f" - Error updating hourly totals: {e} [{datetime.now()}]", flush=True)

# Initialize database connection
conn = create_local_db()
if not conn:
    print(" - Failed to initialize database. Exiting.", flush=True)
    exit(1)

# Main loop
try:
    print(" + Monitoring light sensor (Ctrl+C to exit)...", flush=True)
    last_update_minute = -1  # Track last update minute
    
    while True:
        now = datetime.now()
        current_minute = now.minute
        current_hour_time = now.replace(minute=0, second=0, microsecond=0)
        
        # Only update if we haven't already updated in this minute
        if current_minute % 10 == 0 and current_minute != last_update_minute:
            update_hourly_totals(conn, current_hour_time)
            last_update_minute = current_minute
            
            # Check for hour change
            if current_hour_time > current_hour:
                update_hourly_totals(conn, current_hour)
                current_hour = current_hour_time

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
    # Update hourly totals one final time before shutting down
    update_hourly_totals(conn, current_hour)
    conn.close()