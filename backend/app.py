import os
import sys
import pickle
import pandas as pd
import numpy as np
from fastapi import FastAPI, HTTPException, Query, Depends, status
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import List, Optional

# Add the project root to sys.path to ensure modular imports work from anywhere
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from backend.auth import (
    require_auth, 
    create_session, 
    delete_session, 
    get_user_by_badge, 
    check_password, 
    security
)

from backend.analysis.patrol_routing import plan_patrols
from backend.analysis.clean_data import clean_single_record
from backend.analysis.congestion_score import run_congestion_scoring
from backend.analysis.recurrence_mining import run_recurrence_mining
from backend.analysis.fines_engine import generate_fines, get_db_connection

app = FastAPI(
    title="GridWatch API Service",
    description="Backend API serving traffic violation, hotspots, patrol planning, and camera analytics.",
    version="0.2.0"
)

# Enable CORS for local frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount the frontend directory to serve static assets
app.mount("/frontend", StaticFiles(directory=os.path.join(project_root, "frontend"), html=True), name="frontend")

@app.get("/")
def redirect_to_frontend():
    return RedirectResponse(url="/frontend/index.html")

# Global cache for triage model statistics loaded at startup
triage_stats_cache = {}

VIOLATION_CODE_MAP = {
    '2W/3W - USING MOBILE PHONE': 237,
    'AGAINST ONE WAY/NO ENTRY': 135,
    'CARRYING LENGHTY MATERIAL': 123,
    'DEFECTIVE NUMBER PLATE': 116,
    'DEMANDING EXCESS FARE': 125,
    'DOUBLE PARKING': 109,
    'FAIL TO USE SAFETY BELTS': 110,
    'H T V PROHIBITED': 147,
    'JUMPING TRAFFIC SIGNAL': 115,
    'NO PARKING': 113,
    'OBSTRUCTING DRIVER': 136,
    'OTHER - USING MOBILE PHONE': 437,
    'PARKING IN A MAIN ROAD': 107,
    'PARKING NEAR BUSTOP/SCHOOL/HOSPITAL ETC': 111,
    'PARKING NEAR ROAD CROSSING': 104,
    'PARKING NEAR TRAFFIC LIGHT OR ZEBRA CROSS': 106,
    'PARKING ON FOOTPATH': 105,
    'PARKING OPPOSITE TO ANOTHER PARKED VEHICLE': 108,
    'PARKING OTHER THAN BUS STOP': 139,
    'REFUSE TO GO FOR HIRE': 124,
    'RIDER NOT WEARING HELMET': 140,
    'STOPING ON WHITE/STOP LINE': 146,
    'U TURN PROHIBITED': 134,
    'USING BLACK FILM/OTHER MATERIALS': 133,
    'VIOLATING LANE DISIPLINE': 130,
    'WITHOUT SIDE MIRROR': 144,
    'WRONG PARKING': 112
}

DATA_CACHE = {
    "clean_df": None,
    "hotspots_df": None,
    "calendar_df": None,
    "camera_recs_df": None,
    "long_df": None
}

violation_types_cache = []
hotspots_lookup_df = None

@app.on_event("startup")
def load_data_cache():
    global DATA_CACHE, violation_types_cache, hotspots_lookup_df
    import pandas as pd
    
    clean_path = os.path.join(project_root, "data", "violations_clean.parquet")
    hotspots_path = os.path.join(project_root, "data", "hotspots_scored.parquet")
    calendar_path = os.path.join(project_root, "data", "predictive_calendar.parquet")
    recs_path = os.path.join(project_root, "data", "camera_recommendations.parquet")
    long_parquet = os.path.join(project_root, "data", "violations_tags_long.parquet")
    
    # 1. Load clean violations
    if os.path.exists(clean_path):
        try:
            DATA_CACHE["clean_df"] = pd.read_parquet(clean_path)
            print(f"Successfully cached violations_clean.parquet: {len(DATA_CACHE['clean_df'])} rows")
        except Exception as e:
            print(f"Error caching clean parquet: {e}")
            
    # 2. Load hotspots
    if os.path.exists(hotspots_path):
        try:
            DATA_CACHE["hotspots_df"] = pd.read_parquet(hotspots_path)
            hotspots_lookup_df = DATA_CACHE["hotspots_df"][['representative_lat', 'representative_lon', 'police_station']].dropna()
            print(f"Successfully cached hotspots_scored.parquet: {len(DATA_CACHE['hotspots_df'])} rows")
        except Exception as e:
            print(f"Error caching hotspots parquet: {e}")

    # 3. Load calendar
    if os.path.exists(calendar_path):
        try:
            DATA_CACHE["calendar_df"] = pd.read_parquet(calendar_path)
            print(f"Successfully cached predictive_calendar.parquet: {len(DATA_CACHE['calendar_df'])} rows")
        except Exception as e:
            print(f"Error caching calendar parquet: {e}")

    # 4. Load camera recommendations
    if os.path.exists(recs_path):
        try:
            DATA_CACHE["camera_recs_df"] = pd.read_parquet(recs_path)
            print(f"Successfully cached camera_recommendations.parquet: {len(DATA_CACHE['camera_recs_df'])} rows")
        except Exception as e:
            print(f"Error caching camera recs parquet: {e}")

    # 5. Load long format violations
    if os.path.exists(long_parquet):
        try:
            DATA_CACHE["long_df"] = pd.read_parquet(long_parquet)
            violation_types_cache = sorted([str(x) for x in DATA_CACHE["long_df"]['violation_type'].dropna().unique() if str(x).strip() != ''])
            print(f"Successfully cached violations_tags_long.parquet: {len(DATA_CACHE['long_df'])} rows")
        except Exception as e:
            print(f"Error caching long format parquet: {e}")
            violation_types_cache = sorted(list(VIOLATION_CODE_MAP.keys()))
    else:
        violation_types_cache = sorted(list(VIOLATION_CODE_MAP.keys()))

@app.on_event("startup")
def load_triage_stats():
    global triage_stats_cache
    model_path = os.path.join(project_root, "backend", "analysis", "triage_model.pkl")
    if os.path.exists(model_path):
        try:
            with open(model_path, 'rb') as f:
                model_data = pickle.load(f)
                triage_stats_cache = model_data.get('metrics', {})
            print(f"Successfully loaded and cached triage model metrics from {model_path}")
        except Exception as e:
            print(f"Warning: Failed to load triage model metrics. Error: {e}")
            triage_stats_cache = {
                "error": "Failed to load triage metrics from pickle file."
            }
    else:
        print(f"Warning: Triage model file not found at {model_path}. Run triage_classifier.py first.")
        triage_stats_cache = {
            "error": "Triage model pkl file not found. Model has not been trained."
        }

class LoginRequest(BaseModel):
    badge_id: str
    password: str

@app.post("/api/login")
def login(req: LoginRequest):
    user = get_user_by_badge(req.badge_id)
    if not user or not check_password(req.password, user["password"]):
        raise HTTPException(
            status_code=401,
            detail="Invalid Badge ID or Password"
        )
    token = create_session(user)
    return {
        "session_token": token,
        "name": user["name"],
        "station": user["station"]
    }

@app.post("/api/logout")
def logout(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if credentials:
        delete_session(credentials.credentials)
    return {"status": "success"}

@app.get("/api/me")
def get_me(current_user: dict = Depends(require_auth)):
    return current_user

@app.get("/api/hotspots")
def get_hotspots(current_user: dict = Depends(require_auth)):
    """Lists all clustered hotspots along with their congestion scores."""
    hotspots_path = os.path.join(project_root, "data", "hotspots_scored.parquet")
    df = DATA_CACHE["hotspots_df"]
    if df is None:
        if not os.path.exists(hotspots_path):
            raise HTTPException(status_code=404, detail="Hotspots scored data not found. Run congestion_score.py first.")
        try:
            df = pd.read_parquet(hotspots_path)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error reading hotspots data: {e}")
    try:
        # Convert NaN/NaT values to None to ensure valid JSON serialization
        df = df.replace({pd.NA: None, np.nan: None})
        
        # Convert each row's numpy arrays/values to standard python lists/types
        records = []
        for r in df.to_dict(orient="records"):
            clean_r = {}
            for k, v in r.items():
                if isinstance(v, (np.ndarray, list)):
                    # Convert to list and sanitize elements
                    lst = v.tolist() if isinstance(v, np.ndarray) else v
                    clean_lst = []
                    for x in lst:
                        if isinstance(x, (np.integer, int)):
                            clean_lst.append(int(x))
                        elif isinstance(x, (np.floating, float)):
                            clean_lst.append(float(x))
                        elif pd.isna(x):
                            clean_lst.append(None)
                        else:
                            clean_lst.append(x)
                    clean_r[k] = clean_lst
                elif isinstance(v, (np.integer, int)):
                    clean_r[k] = int(v)
                elif isinstance(v, (np.floating, float)):
                    clean_r[k] = float(v)
                elif pd.isna(v):
                    clean_r[k] = None
                else:
                    clean_r[k] = v
            records.append(clean_r)
        return records
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing hotspots data: {e}")

@app.get("/api/predictive-calendar")
def get_predictive_calendar(
    day_of_week: str = Query(None, description="Day of week to filter by (e.g. Monday)"),
    hour: int = Query(None, description="Hour of day to filter by (0-23)"),
    current_user: dict = Depends(require_auth)
):
    """Retrieves predicted enforcement windows, optionally filtered by day of week and hour."""
    calendar_path = os.path.join(project_root, "data", "predictive_calendar.parquet")
    df = DATA_CACHE["calendar_df"]
    if df is None:
        if not os.path.exists(calendar_path):
            raise HTTPException(status_code=404, detail="Predictive calendar data not found. Run recurrence_mining.py first.")
        try:
            df = pd.read_parquet(calendar_path)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error reading predictive calendar: {e}")
    try:
        if day_of_week:
            df = df[df['day_of_week'].str.lower() == day_of_week.lower()]
        if hour is not None:
            df = df[(df['start_hour'] <= hour) & (df['end_hour'] > hour)]
        df = df.replace({pd.NA: None, np.nan: None})
        return df.to_dict(orient="records")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing predictive calendar: {e}")

@app.get("/api/patrol-plan")
def get_patrol_plan(
    day_of_week: str = Query(..., description="Day of week (e.g. Monday)"),
    hour: int = Query(..., description="Hour of day (0-23)"),
    num_units: int = Query(3, description="Number of available patrol units"),
    current_user: dict = Depends(require_auth)
):
    """Generates an optimized patrol routing plan for a given day, hour, and number of units."""
    try:
        routes = plan_patrols(day_of_week, hour, num_units)
        # Convert any potential numpy values in the routes to standard python types
        serializable_routes = {}
        for unit, stops in routes.items():
            serializable_stops = []
            for stop in stops:
                clean_stop = {}
                for k, v in stop.items():
                    if isinstance(v, (np.integer, np.floating)):
                        clean_stop[k] = v.item()
                    elif isinstance(v, pd.Timestamp):
                        clean_stop[k] = v.isoformat()
                    elif pd.isna(v):
                        clean_stop[k] = None
                    else:
                        clean_stop[k] = v
                serializable_stops.append(clean_stop)
            serializable_routes[int(unit)] = serializable_stops
        return serializable_routes
    except FileNotFoundError as fnf:
        raise HTTPException(status_code=404, detail=str(fnf))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error generating patrol plan: {e}")

@app.get("/api/camera-recommendations")
def get_camera_recommendations(current_user: dict = Depends(require_auth)):
    """Lists camera recommendations for monitored coverage gaps."""
    recs_path = os.path.join(project_root, "data", "camera_recommendations.parquet")
    df = DATA_CACHE["camera_recs_df"]
    if df is None:
        if not os.path.exists(recs_path):
            raise HTTPException(status_code=404, detail="Camera recommendations data not found. Run camera_placement.py first.")
        try:
            df = pd.read_parquet(recs_path)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error reading camera recommendations: {e}")
    try:
        df = df.replace({pd.NA: None, np.nan: None})
        return df.to_dict(orient="records")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing camera recommendations: {e}")

@app.get("/api/triage-stats")
def get_triage_stats(current_user: dict = Depends(require_auth)):
    """Retrieves cached performance metrics and feature importances for the triage ML classifier."""
    return triage_stats_cache

@app.get("/api/kpi-summary")
def get_kpi_summary(
    congestion_threshold: float = Query(20.0, description="Congestion score threshold for hotspots count"),
    current_user: dict = Depends(require_auth)
):
    """Retrieves headline KPI metrics for the analytics dashboard."""
    clean_path = os.path.join(project_root, "data", "violations_clean.parquet")
    hotspots_path = os.path.join(project_root, "data", "hotspots_scored.parquet")
    
    df_clean = DATA_CACHE["clean_df"]
    df_hot = DATA_CACHE["hotspots_df"]
    
    if df_clean is None or df_hot is None:
        if not os.path.exists(clean_path) or not os.path.exists(hotspots_path):
            raise HTTPException(status_code=404, detail="Cleaned violations or hotspots scored data not found.")
        try:
            if df_clean is None:
                df_clean = pd.read_parquet(clean_path)
            if df_hot is None:
                df_hot = pd.read_parquet(hotspots_path)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error reading datasets: {e}")
        
    try:
        
        # 1. Total violations analyzed (Cleaned records count)
        total_violations = len(df_clean)
        
        # 2. Hotspots count above the congestion_cost_score threshold
        hotspots_above = int((df_hot['congestion_cost_score'] >= congestion_threshold).sum())
        
        # 3. Estimated total daily delay-minutes saved if top 10 hotspots were fully enforced
        top_10 = df_hot.sort_values('congestion_cost_score', ascending=False).head(10)
        delay_saved_min = float((top_10['violation_count'] * (top_10['peak_delay_factor'] - 1.0) * 0.1).sum())
        
        # 4. Triage model backlog reduction percentage
        backlog_red_pct = triage_stats_cache.get("backlog_reduction_pct", 0.0)
        
        return {
            "total_violations_analyzed": total_violations,
            "hotspots_above_threshold": hotspots_above,
            "estimated_daily_delay_saved_min": round(delay_saved_min, 1),
            "backlog_reduction_pct": round(float(backlog_red_pct), 1)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error computing KPI summary: {e}")

@app.get("/api/offender-network")
def get_offender_network(current_user: dict = Depends(require_auth)):
    """Serves the pre-computed d3-force graph of repeat offenders and their associated clusters."""
    import json as _json
    network_path = os.path.join(project_root, "data", "offender_network.json")
    if not os.path.exists(network_path):
        raise HTTPException(status_code=404, detail="Offender network data not found. Run offender_network.py first.")
    try:
        with open(network_path, "r", encoding="utf-8") as f:
            return _json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading offender network: {e}")

@app.get("/api/top-offenders")
def get_top_offenders(current_user: dict = Depends(require_auth)):
    """Serves the ranked table of top repeat offenders."""
    import json as _json
    table_path = os.path.join(project_root, "data", "top_offenders.json")
    if not os.path.exists(table_path):
        raise HTTPException(status_code=404, detail="Top offenders data not found. Run offender_network.py first.")
    try:
        with open(table_path, "r", encoding="utf-8") as f:
            return _json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading top offenders: {e}")


class ViolationReportRequest(BaseModel):
    latitude: float
    longitude: float
    location: Optional[str] = "Unknown"
    vehicle_number: str
    vehicle_type: str
    violation_types: List[str]
    description: Optional[str] = ""
    junction_name: Optional[str] = "No Junction"
    photo_filename: Optional[str] = None


@app.get("/api/violation-types")
def get_violation_types(current_user: dict = Depends(require_auth)):
    """Returns cached unique list of violation types."""
    return violation_types_cache


@app.post("/api/report-violation")
def report_violation(req: ViolationReportRequest, current_user: dict = Depends(require_auth)):
    """Logs a manual violation from the enforcer, appends to parquet and csv, and runs recompute."""
    global hotspots_lookup_df
    
    if not req.violation_types:
        raise HTTPException(status_code=400, detail="At least one violation type must be selected.")
        
    # Resolve police station using nearest neighbor lookup
    resolved_station = "No Police Station"
    if hotspots_lookup_df is not None and not hotspots_lookup_df.empty:
        try:
            dists = (hotspots_lookup_df['representative_lat'] - req.latitude) ** 2 + \
                    (hotspots_lookup_df['representative_lon'] - req.longitude) ** 2
            nearest_idx = dists.idxmin()
            resolved_station = hotspots_lookup_df.loc[nearest_idx, 'police_station']
        except Exception as e:
            print(f"Warning: Failed spatial police station lookup: {e}")
            
    import secrets
    from datetime import datetime
    import json as _json
    
    # Get current timestamp in UTC and format
    now_ts = pd.Timestamp.now(tz='UTC')
    now_str = now_ts.isoformat()
    
    raw_record = {
        "id": "FKID" + secrets.token_hex(6).upper(),
        "latitude": req.latitude,
        "longitude": req.longitude,
        "location": req.location or "Unknown",
        "vehicle_number": req.vehicle_number,
        "vehicle_type": req.vehicle_type,
        "description": req.description or "",
        "violation_type": req.violation_types,
        "offence_code": [VIOLATION_CODE_MAP.get(vt, 999) for vt in req.violation_types],
        "created_datetime": now_str,
        "closed_datetime": None,
        "modified_datetime": now_str,
        "device_id": "MANUAL-REPORT",
        "created_by_id": current_user['badge_id'],
        "center_code": 9.0,
        "police_station": resolved_station,
        "data_sent_to_scita": True,
        "junction_name": req.junction_name or "No Junction",
        "action_taken_timestamp": None,
        "data_sent_to_scita_timestamp": None,
        "updated_vehicle_number": req.vehicle_number,
        "updated_vehicle_type": req.vehicle_type,
        "validation_status": "approved",
        "validation_timestamp": now_str
    }
    
    # Run raw dict through clean_single_record
    try:
        cleaned_record = clean_single_record(raw_record)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Data cleaning failed: {e}")
        
    # Append to data/violations_clean.parquet
    clean_parquet_path = os.path.join(project_root, "data", "violations_clean.parquet")
    try:
        df_clean = DATA_CACHE["clean_df"]
        if df_clean is None:
            df_clean = pd.read_parquet(clean_parquet_path)
        new_row_df = pd.DataFrame([cleaned_record])
        # Ensure identical column ordering
        new_row_df = new_row_df[df_clean.columns]
        df_combined = pd.concat([df_clean, new_row_df], ignore_index=True)
        df_combined.to_parquet(clean_parquet_path, engine='pyarrow', index=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to append to clean Parquet: {e}")
        
    # Append to data/violations_tags_long.parquet
    long_parquet_path = os.path.join(project_root, "data", "violations_tags_long.parquet")
    if os.path.exists(long_parquet_path):
        try:
            df_long = DATA_CACHE["long_df"]
            if df_long is None:
                df_long = pd.read_parquet(long_parquet_path)
            new_row_exploded = new_row_df.explode(['violation_type', 'offence_code'])
            new_row_exploded = new_row_exploded[df_long.columns]
            df_combined_long = pd.concat([df_long, new_row_exploded], ignore_index=True)
            df_combined_long.to_parquet(long_parquet_path, engine='pyarrow', index=False)
        except Exception as e:
            print(f"Warning: Failed to append to exploded Parquet: {e}")
            
    # Append to running CSV backup
    csv_backup_path = os.path.join(project_root, "data", "violations_clean.csv")
    try:
        csv_row = cleaned_record.copy()
        csv_row['violation_type'] = _json.dumps(csv_row['violation_type'])
        csv_row['offence_code'] = _json.dumps(csv_row['offence_code'])
        if isinstance(csv_row['created_datetime'], pd.Timestamp):
            csv_row['created_datetime'] = csv_row['created_datetime'].isoformat()
        
        df_csv_row = pd.DataFrame([csv_row])
        header = not os.path.exists(csv_backup_path)
        df_csv_row.to_csv(csv_backup_path, mode='a', header=header, index=False)
    except Exception as e:
        print(f"Warning: Failed to append to CSV backup: {e}")
        
    # Trigger recompute
    recomputed = False
    scored_parquet_path = os.path.join(project_root, "data", "hotspots_scored.parquet")
    calendar_parquet_path = os.path.join(project_root, "data", "predictive_calendar.parquet")
    
    try:
        run_congestion_scoring(clean_parquet_path, scored_parquet_path)
        run_recurrence_mining(clean_parquet_path, scored_parquet_path, calendar_parquet_path)
        
        # Reload cache to update in-memory tables
        load_data_cache()
        recomputed = True
    except Exception as e:
        print(f"Warning: Failed to run analysis recompute: {e}")
        
    # Convert Timestamp values for JSON response
    res_record = cleaned_record.copy()
    if isinstance(res_record['created_datetime'], pd.Timestamp):
        res_record['created_datetime'] = res_record['created_datetime'].isoformat()
        
    res_record['violation_type'] = list(res_record['violation_type'])
    res_record['offence_code'] = list(res_record['offence_code'])
    
    return {
        "status": "success",
        "cleaned_record": res_record,
        "recomputed": recomputed
    }


@app.post("/api/fines/generate")
def api_generate_fines(current_user: dict = Depends(require_auth)):
    """Scans clean parquet data and generates fines in the SQLite DB."""
    res = generate_fines()
    if res.get("status") == "error":
        raise HTTPException(status_code=500, detail=res.get("message", "Fines generation engine failed."))
    return res


@app.get("/api/fines")
def api_get_fines(current_user: dict = Depends(require_auth)):
    """Retrieves all fines from the SQLite DB sorted by fine_amount DESC."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM fines ORDER BY fine_amount DESC, violation_count DESC")
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query failed: {e}")


@app.post("/api/fines/{fine_id}/send-reminder")
def api_send_reminder(fine_id: int, current_user: dict = Depends(require_auth)):
    """Simulates sending an SMS reminder for unpaid fines, increments reminder count and timestamp."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM fines WHERE fine_id = ?", (fine_id,))
        row = cursor.fetchone()
        
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="Fine record not found.")
            
        if row['status'] == 'paid':
            conn.close()
            raise HTTPException(status_code=400, detail="Cannot send reminder for a paid fine.")
            
        now_str = pd.Timestamp.now(tz='UTC').isoformat()
        new_count = row['reminder_count'] + 1
        
        cursor.execute("""
            UPDATE fines 
            SET reminder_count = ?, 
                last_reminder_at = ? 
            WHERE fine_id = ?
        """, (new_count, now_str, fine_id))
        
        conn.commit()
        conn.close()
        
        # Simulated log output
        print(f"[SIMULATED SMS] Sent to {row['phone_number_simulated']}: '{row['message_text']}'")
        
        return {
            "status": "success",
            "fine_id": fine_id,
            "phone_number": row['phone_number_simulated'],
            "message_text": row['message_text'],
            "reminder_count": new_count,
            "last_reminder_at": now_str
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update reminder: {e}")


class BulkReminderRequest(BaseModel):
    fine_ids: Optional[List[int]] = None


@app.post("/api/fines/send-reminders")
def api_send_reminders_bulk(payload: BulkReminderRequest, current_user: dict = Depends(require_auth)):
    """Bulk sends simulated reminders for unpaid fine records."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        fine_ids = payload.fine_ids
        if fine_ids is not None:
            if not fine_ids:
                conn.close()
                return {"status": "success", "sent_count": 0, "message": "No fine IDs provided."}
            placeholders = ",".join("?" for _ in fine_ids)
            cursor.execute(f"SELECT * FROM fines WHERE status = 'unpaid' AND fine_id IN ({placeholders})", fine_ids)
        else:
            cursor.execute("SELECT * FROM fines WHERE status = 'unpaid'")
            
        rows = cursor.fetchall()
        if not rows:
            conn.close()
            return {"status": "success", "sent_count": 0, "message": "No eligible unpaid fines found for reminders."}
            
        now_str = pd.Timestamp.now(tz='UTC').isoformat()
        updated_ids = []
        for row in rows:
            new_count = row['reminder_count'] + 1
            cursor.execute("""
                UPDATE fines 
                SET reminder_count = ?, 
                    last_reminder_at = ? 
                WHERE fine_id = ?
            """, (new_count, now_str, row['fine_id']))
            updated_ids.append(row['fine_id'])
            print(f"[SIMULATED SMS BULK] Sent to {row['phone_number_simulated']}: '{row['message_text']}'")
            
        conn.commit()
        conn.close()
        
        return {
            "status": "success",
            "sent_count": len(updated_ids),
            "message": f"Successfully sent simulated reminders to {len(updated_ids)} offenders.",
            "last_reminder_at": now_str
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send bulk reminders: {e}")


@app.post("/api/fines/{fine_id}/mark-paid")

def api_mark_paid(fine_id: int, current_user: dict = Depends(require_auth)):
    """Demo endpoint to manually flag a fine status as paid."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM fines WHERE fine_id = ?", (fine_id,))
        row = cursor.fetchone()
        
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="Fine record not found.")
            
        cursor.execute("UPDATE fines SET status = 'paid' WHERE fine_id = ?", (fine_id,))
        conn.commit()
        conn.close()
        
        return {
            "status": "success",
            "fine_id": fine_id,
            "new_status": "paid"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to mark as paid: {e}")


@app.get("/api/fines/{vehicle_number}/history")
def get_vehicle_history(vehicle_number: str, current_user: dict = Depends(require_auth)):
    """Retrieves violation history timeline for a specific vehicle number."""
    clean_parquet_path = os.path.join(project_root, "data", "violations_clean.parquet")
    df = DATA_CACHE["clean_df"]
    if df is None:
        if not os.path.exists(clean_parquet_path):
            raise HTTPException(status_code=404, detail="Clean violations data not found.")
        try:
            df = pd.read_parquet(clean_parquet_path)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error reading history: {e}")
    try:
        # Resolve vehicle id column checking fallback
        df['veh_id'] = df['updated_vehicle_number'].fillna(df['vehicle_number']).astype(str).str.strip().str.upper()
        
        # Filter matching vehicle
        matches = df[df['veh_id'] == vehicle_number.strip().upper()]
        
        if matches.empty:
            return []
            
        # Select timeline columns and sort by date descending
        timeline = matches[[
            'id', 'created_datetime', 'latitude', 'longitude', 
            'location', 'junction_name', 'police_station', 
            'violation_type', 'validation_status'
        ]].sort_values('created_datetime', ascending=False).copy()
        
        # Convert Datetime to ISO string
        timeline['created_datetime'] = timeline['created_datetime'].apply(
            lambda x: x.isoformat() if hasattr(x, 'isoformat') else str(x)
        )
        
        # Convert violation lists to standard lists
        timeline['violation_type'] = timeline['violation_type'].apply(
            lambda x: list(x) if isinstance(x, (list, np.ndarray)) else [x]
        )
        
        # Clean null values for json compatibility
        timeline = timeline.replace({pd.NA: None, np.nan: None})
        
        return timeline.to_dict(orient="records")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading history: {e}")


@app.get("/api/reports/monthly-data")
def get_monthly_report_data(
    year: int = Query(..., description="Target Year"),
    month: int = Query(..., description="Target Month (1-12)"),
    current_user: dict = Depends(require_auth)
):
    """Generates and returns the monthly report data for the specified year and month."""
    from backend.analysis.monthly_report import build_report_data
    
    if not (1 <= month <= 12):
        raise HTTPException(status_code=400, detail="Invalid month. Must be between 1 and 12.")
        
    try:
        data = build_report_data(year, month)
        return data
    except FileNotFoundError as fnf:
        raise HTTPException(status_code=404, detail=str(fnf))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to gather report data: {e}")


