import os
import sys
import pandas as pd

# Add the project root to sys.path to ensure modular imports work from anywhere
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from backend.analysis.clean_data import print_report
except ImportError:
    # Inline fallback print_report implementation in case of path resolution issues
    def print_report(raw_count, clean_count, excluded_count, df_clean):
        import pandas as pd
        excluded_pct = (excluded_count / raw_count) * 100 if raw_count > 0 else 0
        val_status_counts = df_clean['validation_status'].value_counts(dropna=False)
        val_status_pct = df_clean['validation_status'].value_counts(dropna=False, normalize=True) * 100
        top_vehicles = df_clean['vehicle_type'].value_counts(dropna=False).head(10)
        top_junctions = df_clean['junction_name'].value_counts(dropna=False).head(10)
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

def run_summary():
    # Path setup
    raw_csv_path = os.path.join(project_root, "data", "violations_raw.csv")
    clean_wide_path = os.path.join(project_root, "data", "violations_clean.parquet")
    
    if not os.path.exists(clean_wide_path):
        print(f"\n[Error] Cleaned Parquet file not found at: {clean_wide_path}")
        print("Please run the cleaning pipeline first:")
        print("  python backend/analysis/clean_data.py\n")
        sys.exit(1)
        
    print(f"Loading cleaned dataset from {clean_wide_path}...")
    df_clean = pd.read_parquet(clean_wide_path)
    clean_count = len(df_clean)
    
    raw_count = None
    if os.path.exists(raw_csv_path):
        print(f"Loading raw count from {raw_csv_path} (reading index column only)...")
        try:
            # Read only 'id' to be highly efficient on large files
            df_raw_id = pd.read_csv(raw_csv_path, usecols=['id'])
            raw_count = len(df_raw_id)
        except Exception as e:
            print(f"Warning: Could not retrieve raw count from CSV. Error: {e}")
            
    if raw_count is None:
        raw_count = clean_count
        excluded_count = 0
    else:
        excluded_count = raw_count - clean_count
        
    print_report(raw_count, clean_count, excluded_count, df_clean)

if __name__ == "__main__":
    run_summary()
