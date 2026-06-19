# fines_engine.py - Automated Fine Engine for Repeat Offenders
import os
import sqlite3
import hashlib
import random
from datetime import datetime
import pandas as pd

# Project configuration
DB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
DB_PATH = os.path.join(DB_DIR, "fines.db")

# Config constants (INR)
REPEAT_OFFENDER_THRESHOLD = 5  # Violation count strictly greater than this triggers a fine
BASE_FINE_INR = 500
PER_EXTRA_OFFENSE_INR = 100

def get_db_connection():
    """Establishes and returns a connection to the SQLite database."""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the fines table in SQLite database if it does not exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fines (
            fine_id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_number TEXT UNIQUE,
            vehicle_type TEXT,
            violation_count INTEGER,
            first_violation_date TEXT,
            last_violation_date TEXT,
            fine_amount INTEGER,
            phone_number_simulated TEXT,
            message_text TEXT,
            status TEXT DEFAULT 'unpaid',
            created_at TEXT,
            last_reminder_at TEXT DEFAULT NULL,
            reminder_count INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

# Initialize on import
init_db()

def compute_fine_amount(violation_count: int) -> int:
    """Computes fine amount based on repeating violations count."""
    extra = max(0, violation_count - REPEAT_OFFENDER_THRESHOLD)
    amount = BASE_FINE_INR + (PER_EXTRA_OFFENSE_INR * extra)
    return amount

def generate_deterministic_phone(vehicle_number: str) -> str:
    """Generates a consistent fake +91-9XXXXXXXX phone number from the vehicle number hash."""
    h = hashlib.sha256(vehicle_number.encode('utf-8')).hexdigest()
    # Convert first 8 hex characters into an integer
    val = int(h[:8], 16)
    # Generate 9-digit sequence between 900000000 and 999999999
    digits = 900000000 + (val % 100000000)
    return f"+91-{digits}"

def compose_message(vehicle_number: str, violation_count: int, fine_amount: int) -> str:
    """Composes the violation notification SMS text template."""
    return (
        f"Dear vehicle owner ({vehicle_number}), you have been recorded for {violation_count} "
        f"parking violations. A fine of INR {fine_amount} has been issued. Please pay within "
        f"7 days to avoid further action. - Traffic Enforcement Dept."
    )

def generate_fines() -> dict:
    """
    Reads data/violations_clean.parquet, aggregates violations by vehicle_number,
    and upserts offenders who exceed the REPEAT_OFFENDER_THRESHOLD into the SQLite database.
    """
    clean_parquet_path = os.path.join(DB_DIR, "violations_clean.parquet")
    if not os.path.exists(clean_parquet_path):
        return {"new_records": 0, "updated_records": 0, "status": "error", "message": "violations_clean.parquet not found"}

    try:
        # Load and filter out placeholders
        df = pd.read_parquet(clean_parquet_path)
        
        # Determine updated_vehicle_number or fallback to vehicle_number
        df['veh_id'] = df['updated_vehicle_number'].fillna(df['vehicle_number'])
        df['veh_id'] = df['veh_id'].astype(str).str.strip().str.upper()
        
        # Filter out obvious invalid registration shapes
        invalid_placeholders = {'UNKNOWN', 'NULL', 'NAN', 'NONE', ''}
        df = df[
            (~df['veh_id'].isin(invalid_placeholders)) & 
            (df['veh_id'].str.len() >= 4)
        ]

        if df.empty:
            return {"new_records": 0, "updated_records": 0, "status": "success"}

        # Group and compute metrics
        agg = df.groupby('veh_id').agg(
            violation_count=('id', 'count'),
            first_violation_date=('created_datetime', 'min'),
            last_violation_date=('created_datetime', 'max'),
            vehicle_type=('vehicle_type', lambda x: x.mode().iloc[0] if not x.empty else 'CAR')
        ).reset_index()

        # Keep strictly greater than threshold
        offenders = agg[agg['violation_count'] > REPEAT_OFFENDER_THRESHOLD]

        conn = get_db_connection()
        cursor = conn.cursor()
        
        new_count = 0
        updated_count = 0
        now_str = datetime.utcnow().isoformat() + "Z"

        for _, row in offenders.iterrows():
            veh_num = row['veh_id']
            v_count = int(row['violation_count'])
            v_type = row['vehicle_type']
            
            # Format dates (handling pd.Timestamp values)
            first_date = row['first_violation_date']
            last_date = row['last_violation_date']
            first_date_str = first_date.isoformat() if hasattr(first_date, 'isoformat') else str(first_date)
            last_date_str = last_date.isoformat() if hasattr(last_date, 'isoformat') else str(last_date)

            fine_amount = compute_fine_amount(v_count)
            phone = generate_deterministic_phone(veh_num)
            msg = compose_message(veh_num, v_count, fine_amount)

            # Check if record exists
            cursor.execute("SELECT fine_id, violation_count, status FROM fines WHERE vehicle_number = ?", (veh_num,))
            existing = cursor.fetchone()

            if not existing:
                # Seeding initial payment status (~30% paid, ~70% unpaid)
                # Seed deterministically using vehicle number hash so demo runs are reproducible
                h_val = int(hashlib.sha256(veh_num.encode('utf-8')).hexdigest()[:8], 16)
                status = "paid" if (h_val % 10) < 3 else "unpaid"

                cursor.execute("""
                    INSERT INTO fines (
                        vehicle_number, vehicle_type, violation_count, first_violation_date, 
                        last_violation_date, fine_amount, phone_number_simulated, 
                        message_text, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    veh_num, v_type, v_count, first_date_str, last_date_str, 
                    fine_amount, phone, msg, status, now_str
                ))
                new_count += 1
            else:
                existing_fine_id = existing['fine_id']
                existing_count = existing['violation_count']

                # Always update fine details (fine_amount, message_text, violation_count) to apply potential logic changes
                cursor.execute("""
                    UPDATE fines 
                    SET violation_count = ?, 
                        last_violation_date = ?, 
                        fine_amount = ?, 
                        message_text = ?
                    WHERE fine_id = ?
                """, (max(v_count, existing_count), last_date_str, fine_amount, msg, existing_fine_id))
                updated_count += 1

        conn.commit()
        conn.close()
        return {"new_records": new_count, "updated_records": updated_count, "status": "success"}

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"new_records": 0, "updated_records": 0, "status": "error", "message": str(e)}
