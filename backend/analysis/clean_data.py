import os
import json
import pandas as pd
import numpy as np

def parse_json_list(val):
    """Parses a stringified JSON list. Safe against nulls and invalid formats."""
    if pd.isna(val) or val is None:
        return []
    val_str = str(val).strip()
    if not val_str or val_str.upper() == 'NULL':
        return []
    try:
        parsed = json.loads(val_str)
        if isinstance(parsed, list):
            return parsed
        else:
            return [parsed]
    except Exception:
        # Fallback for non-JSON string values
        return [val_str]

def clean_offence_code_list(lst):
    """Cleans offence codes to integers where possible, otherwise strings."""
    cleaned = []
    all_ints = True
    for item in lst:
        if item is None or pd.isna(item) or str(item).strip().upper() == 'NULL' or str(item).strip() == '':
            cleaned.append(None)
        else:
            try:
                cleaned.append(int(float(item)))
            except Exception:
                cleaned.append(str(item).strip())
                all_ints = False
    if not all_ints:
        cleaned = [str(x) if x is not None else None for x in cleaned]
    return cleaned

def clean_violation_type_list(lst):
    """Cleans violation types to uppercase strings."""
    cleaned = []
    for item in lst:
        if item is None or pd.isna(item) or str(item).strip().upper() == 'NULL' or str(item).strip() == '':
            cleaned.append(None)
        else:
            cleaned.append(str(item).strip().upper())
    return cleaned

def clean_single_record(raw_dict: dict) -> dict:
    """Cleans a single raw violation record dictionary and returns a cleaned dictionary."""
    cleaned = raw_dict.copy()
    
    # 1. Parse created_datetime into proper timezone-aware datetime (UTC)
    dt = cleaned.get('created_datetime')
    if dt is not None and not pd.isna(dt):
        try:
            cleaned['created_datetime'] = pd.to_datetime(dt, utc=True)
        except Exception:
            cleaned['created_datetime'] = pd.NaT
    else:
        cleaned['created_datetime'] = pd.NaT
        
    # 2. Normalize vehicle_type
    vt = cleaned.get('vehicle_type')
    if vt is not None and not pd.isna(vt) and str(vt).strip().upper() != 'NULL' and str(vt).strip() != '':
        cleaned['vehicle_type'] = str(vt).strip().upper()
    else:
        cleaned['vehicle_type'] = None
        
    # 3. Normalize validation_status
    vs = cleaned.get('validation_status')
    if vs is not None and not pd.isna(vs) and str(vs).strip().upper() != 'NULL' and str(vs).strip() != '':
        cleaned['validation_status'] = str(vs).strip().lower()
    else:
        cleaned['validation_status'] = 'approved'
        
    # 4. Parse JSON lists for violation_type and offence_code and align them
    raw_vt = cleaned.get('violation_type')
    raw_oc = cleaned.get('offence_code')
    
    vt_parsed = raw_vt if isinstance(raw_vt, list) else parse_json_list(raw_vt)
    oc_parsed = raw_oc if isinstance(raw_oc, list) else parse_json_list(raw_oc)
    
    vt_cleaned = clean_violation_type_list(vt_parsed)
    oc_cleaned = clean_offence_code_list(oc_parsed)
    
    max_len = max(len(vt_cleaned), len(oc_cleaned))
    vt_padded = vt_cleaned + [None] * (max_len - len(vt_cleaned))
    oc_padded = oc_cleaned + [None] * (max_len - len(oc_cleaned))
    
    cleaned['violation_type'] = vt_padded
    cleaned['offence_code'] = oc_padded
    
    # 5. Format coordinates
    for col in ['latitude', 'longitude']:
        if col in cleaned:
            val = cleaned[col]
            if val is not None and not pd.isna(val):
                try:
                    cleaned[col] = float(val)
                except Exception:
                    cleaned[col] = None
            else:
                cleaned[col] = None
                
    return cleaned

def is_garbage_record(r: dict) -> bool:
    """Checks if a record contains garbage coordinates or police station."""
    lat = r.get('latitude')
    lon = r.get('longitude')
    ps = r.get('police_station')
    
    if lat is None or pd.isna(lat) or lon is None or pd.isna(lon):
        return True
    try:
        lat_f = float(lat)
        lon_f = float(lon)
        if lat_f == 0.0 and lon_f == 0.0:
            return True
        if lat_f < -90.0 or lat_f > 90.0 or lon_f < -180.0 or lon_f > 180.0:
            return True
    except Exception:
        return True
        
    if ps is None or pd.isna(ps) or str(ps).strip() == '' or str(ps).strip().upper() == 'NULL':
        return True
        
    return False

def run_cleaning_pipeline(raw_csv_path, clean_wide_path, clean_long_path):
    print("=" * 80)
    print("GRIDWATCH DATA CLEANING PIPELINE STARTED")
    print(f"Loading raw data from: {raw_csv_path}")
    print("=" * 80)
    
    # Check if raw data exists
    if not os.path.exists(raw_csv_path):
        raise FileNotFoundError(f"Raw data file not found at {raw_csv_path}")
        
    df = pd.read_csv(raw_csv_path)
    initial_row_count = len(df)
    print(f"Loaded {initial_row_count:,} raw records.")
    
    # Run the cleaned single record logic row-by-row on the batch records
    print("Cleaning all records row-by-row using clean_single_record...")
    raw_records = df.to_dict(orient='records')
    cleaned_records = [clean_single_record(r) for r in raw_records]
    df_cleaned = pd.DataFrame(cleaned_records)
    
    print("Identifying and flagging garbage rows...")
    df_cleaned['exclude_row'] = df_cleaned.apply(is_garbage_record, axis=1)
    
    # Split the dataset into clean and excluded
    df_clean = df_cleaned[~df_cleaned['exclude_row']].copy()
    df_excluded = df_cleaned[df_cleaned['exclude_row']].copy()
    
    clean_row_count = len(df_clean)
    excluded_row_count = len(df_excluded)
    
    # Drop the temporary helper column from the clean dataset
    df_clean = df_clean.drop(columns=['exclude_row'])
    
    # 5. Export clean datasets to Parquet
    print(f"Exporting cleaned wide dataset to: {clean_wide_path}")
    # Ensure directory exists
    os.makedirs(os.path.dirname(clean_wide_path), exist_ok=True)
    df_clean.to_parquet(clean_wide_path, engine='pyarrow', index=False)
    
    print(f"Exporting cleaned long dataset to: {clean_long_path}")
    # Explode the lists to create the long table (tidy format: one row per violation per tag)
    df_long = df_clean.explode(['violation_type', 'offence_code'])
    df_long.to_parquet(clean_long_path, engine='pyarrow', index=False)
    
    # 6. Generate and print Data Quality Report
    print_report(initial_row_count, clean_row_count, excluded_row_count, df_clean)
    print("=" * 80)
    print("GRIDWATCH DATA CLEANING PIPELINE COMPLETED SUCCESSFULLY")
    print("=" * 80)

def print_report(raw_count, clean_count, excluded_count, df_clean):
    excluded_pct = (excluded_count / raw_count) * 100 if raw_count > 0 else 0
    
    # Validation status metrics
    val_status_counts = df_clean['validation_status'].value_counts(dropna=False)
    val_status_pct = df_clean['validation_status'].value_counts(dropna=False, normalize=True) * 100
    
    # Top 10 vehicle types
    top_vehicles = df_clean['vehicle_type'].value_counts(dropna=False).head(10)
    
    # Top 10 junctions
    top_junctions = df_clean['junction_name'].value_counts(dropna=False).head(10)
    
    # Unique administrative units
    unique_stations = df_clean['police_station'].nunique(dropna=True)
    unique_locations = df_clean['location'].nunique(dropna=True)
    
    print("\n" + "=" * 50)
    print("           GRIDWATCH DATA QUALITY REPORT           ")
    print("=" * 50)
    print("Row Counts:")
    print(f"  - Raw Dataset:      {raw_count:,} rows")
    print(f"  - Cleaned Dataset:  {clean_count:,} rows")
    print(f"  - Excluded Dataset: {excluded_count:,} rows ({excluded_pct:.2f}%)")
    print("\nValidation Status (Cleaned Data):")
    for status, pct in val_status_pct.items():
        count = val_status_counts[status]
        status_name = "None" if pd.isna(status) else str(status)
        print(f"  - {status_name:<15}: {pct:.2f}% ({count:,} rows)")
        
    print("\nTop 10 Vehicle Types:")
    for i, (vehicle, count) in enumerate(top_vehicles.items(), 1):
        veh_name = "None" if pd.isna(vehicle) else str(vehicle)
        pct = (count / clean_count) * 100 if clean_count > 0 else 0
        print(f"  {i:>2}. {veh_name:<18} {count:>7,} rows ({pct:.2f}%)")
        
    print("\nTop 10 Junctions:")
    for i, (junction, count) in enumerate(top_junctions.items(), 1):
        junc_name = "None" if pd.isna(junction) else str(junction)
        pct = (count / clean_count) * 100 if clean_count > 0 else 0
        print(f"  {i:>2}. {junc_name:<18} {count:>7,} rows ({pct:.2f}%)")
        
    print("\nGeographic & Administrative Summary:")
    print(f"  - Unique Police Stations: {unique_stations:,}")
    print(f"  - Unique Location Strings: {unique_locations:,}")
    print("=" * 50 + "\n")

if __name__ == "__main__":
    RAW_CSV = os.path.join("data", "violations_raw.csv")
    CLEAN_WIDE = os.path.join("data", "violations_clean.parquet")
    CLEAN_LONG = os.path.join("data", "violations_tags_long.parquet")
    
    run_cleaning_pipeline(RAW_CSV, CLEAN_WIDE, CLEAN_LONG)
