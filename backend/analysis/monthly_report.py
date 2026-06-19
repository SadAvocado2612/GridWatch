# monthly_report.py - Monthly Enforcement Report Generator
import os
import calendar
import sqlite3
from datetime import datetime
import pandas as pd
import numpy as np

# Configuration constants
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
DB_PATH = os.path.join(DATA_DIR, "fines.db")

def get_previous_month(year: int, month: int) -> tuple:
    """Returns the (year, month) of the previous month."""
    if month == 1:
        return year - 1, 12
    return year, month - 1

def build_report_data(year: int, month: int) -> dict:
    """
    Pulls data for the selected month/year from violations, hotspots, fines and predictive calendar.
    Also computes the previous month's baseline metrics for comparisons.
    """
    # 1. Load Parquet Data
    clean_parquet_path = os.path.join(DATA_DIR, "violations_clean.parquet")
    if not os.path.exists(clean_parquet_path):
        raise FileNotFoundError(f"Clean violations parquet not found at {clean_parquet_path}")
        
    df_all = pd.read_parquet(clean_parquet_path)
    
    # Normalize created_datetime to pd.Datetime
    df_all['dt_parsed'] = pd.to_datetime(df_all['created_datetime'], errors='coerce', utc=True)
    df_all = df_all.dropna(subset=['dt_parsed'])
    
    # 2. Extract targets
    df_curr = df_all[(df_all['dt_parsed'].dt.year == year) & (df_all['dt_parsed'].dt.month == month)].copy()
    
    prev_year, prev_month = get_previous_month(year, month)
    df_prev = df_all[(df_all['dt_parsed'].dt.year == prev_year) & (df_all['dt_parsed'].dt.month == prev_month)].copy()
    
    # Core Metrics - Total Violations
    total_violations = len(df_curr)
    prev_violations = len(df_prev)
    if prev_violations > 0:
        pct_change_violations = ((total_violations - prev_violations) / prev_violations) * 100.0
    else:
        pct_change_violations = 0.0
        
    # Validation Approval Rate
    curr_validated = df_curr[df_curr['validation_status'].isin(['approved', 'rejected'])]
    curr_approved = (curr_validated['validation_status'] == 'approved').sum()
    validation_approval_rate = curr_approved / len(curr_validated) if len(curr_validated) > 0 else 0.0
    
    prev_validated = df_prev[df_prev['validation_status'].isin(['approved', 'rejected'])]
    prev_approved = (prev_validated['validation_status'] == 'approved').sum()
    prev_approval_rate = prev_approved / len(prev_validated) if len(prev_validated) > 0 else 0.0
    
    if prev_approval_rate > 0:
        pct_change_approval = ((validation_approval_rate - prev_approval_rate) / prev_approval_rate) * 100.0
    else:
        pct_change_approval = 0.0
        
    # Vehicle types breakdown
    df_curr['veh_type'] = df_curr['updated_vehicle_type'].fillna(df_curr['vehicle_type']).astype(str).str.strip().str.upper()
    veh_breakdown = df_curr['veh_type'].value_counts().to_dict()
    # Filter out empty or null vehicle types if any
    veh_breakdown = {k: v for k, v in veh_breakdown.items() if k not in ['UNKNOWN', 'NONE', 'NAN', '']}
    
    # Daily counts across target month
    num_days = calendar.monthrange(year, month)[1]
    all_days = [f"{year:04d}-{month:02d}-{d:02d}" for d in range(1, num_days + 1)]
    daily_violations = {day: 0 for day in all_days}
    curr_daily = df_curr['dt_parsed'].dt.strftime('%Y-%m-%d').value_counts().to_dict()
    for d, c in curr_daily.items():
        if d in daily_violations:
            daily_violations[d] = c
            
    # Hour of day distribution
    hourly_violations = {h: 0 for h in range(24)}
    curr_hourly = df_curr['dt_parsed'].dt.hour.value_counts().to_dict()
    for h, c in curr_hourly.items():
        if h in hourly_violations:
            hourly_violations[h] = c
            
    # Top 10 hotspots for this month
    df_curr_juncs = df_curr[
        df_curr['junction_name'].notna() & 
        (~df_curr['junction_name'].str.upper().isin(['NO JUNCTION', 'UNKNOWN', 'NULL', 'NAN', '']))
    ]
    top_junc_counts = df_curr_juncs['junction_name'].value_counts().head(10).reset_index()
    top_junc_counts.columns = ['junction_name', 'violation_count']
    
    hotspots_path = os.path.join(DATA_DIR, "hotspots_scored.parquet")
    if os.path.exists(hotspots_path):
        df_hot = pd.read_parquet(hotspots_path)
        df_hot_unique = df_hot.drop_duplicates(subset=['junction_name'])
        if 'violation_count' in df_hot_unique.columns:
            df_hot_unique = df_hot_unique.drop(columns=['violation_count'])
        merged_hot = pd.merge(top_junc_counts, df_hot_unique, on='junction_name', how='left')
    else:
        merged_hot = top_junc_counts.copy()
        
    if 'congestion_cost_score' not in merged_hot.columns:
        merged_hot['congestion_cost_score'] = 0.0
    merged_hot['congestion_cost_score'] = merged_hot['congestion_cost_score'].fillna(0.0)
    
    if 'daily_cost_inr' not in merged_hot.columns:
        merged_hot['daily_cost_inr'] = None
        
    top_10_list = []
    for _, row in merged_hot.iterrows():
        top_10_list.append({
            "junction_name": row["junction_name"],
            "violation_count": int(row["violation_count"]),
            "congestion_cost_score": float(row["congestion_cost_score"]),
            "daily_cost_inr": row["daily_cost_inr"]
        })
        
    # Fines Summary
    total_fines_count = 0
    total_fine_amount = 0
    total_collected = 0
    total_outstanding = 0
    new_repeat_offenders = 0
    
    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            like_pattern = f"{year:04d}-{month:02d}%"
            cursor.execute("SELECT * FROM fines WHERE created_at LIKE ?", (like_pattern,))
            rows = cursor.fetchall()
            
            total_fines_count = len(rows)
            new_repeat_offenders = total_fines_count
            total_fine_amount = sum(row["fine_amount"] for row in rows)
            total_collected = sum(row["fine_amount"] for row in rows if row["status"] == "paid")
            total_outstanding = sum(row["fine_amount"] for row in rows if row["status"] == "unpaid")
            conn.close()
        except Exception as e:
            print(f"Error querying fines DB: {e}")
            
    # Recommended Focus Next Month
    recommended_focus = []
    predictive_calendar_path = os.path.join(DATA_DIR, "predictive_calendar.parquet")
    if os.path.exists(predictive_calendar_path):
        try:
            df_pred = pd.read_parquet(predictive_calendar_path)
            df_pred['score'] = df_pred['congestion_cost_score'] * df_pred['recurrence_probability']
            df_pred_top = df_pred.sort_values('score', ascending=False).head(5)
            
            for _, row in df_pred_top.iterrows():
                recommended_focus.append({
                    "junction_name": row["junction_name"],
                    "police_station": row["police_station"],
                    "day_of_week": row["day_of_week"],
                    "start_hour": int(row["start_hour"]),
                    "end_hour": int(row["end_hour"]),
                    "recurrence_probability": float(row["recurrence_probability"]),
                    "congestion_cost_score": float(row["congestion_cost_score"]),
                    "score": float(row["score"]),
                    "recommended_action": row["recommended_action"]
                })
        except Exception as e:
            print(f"Error querying predictive calendar: {e}")
            
    return {
        "year": year,
        "month": month,
        "month_name": calendar.month_name[month],
        "total_violations": total_violations,
        "pct_change_violations": pct_change_violations,
        "validation_approval_rate": validation_approval_rate,
        "pct_change_approval": pct_change_approval,
        "pct_change_approval_rate": pct_change_approval,
        "violations_by_vehicle_type": veh_breakdown,
        "daily_violation_counts": daily_violations,
        "violations_by_hour_of_day": hourly_violations,
        "top_10_hotspots": top_10_list,
        "fines_summary": {
            "total_fines_count": total_fines_count,
            "total_fine_amount": total_fine_amount,
            "total_collected": total_collected,
            "total_outstanding": total_outstanding,
            "new_repeat_offenders": new_repeat_offenders
        },
        "recommended_focus_next_month": recommended_focus
    }
