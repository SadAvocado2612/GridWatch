import os
import sys
import pandas as pd
import numpy as np

def format_hour(h):
    """Formats an hour (0-24) into a clean 12-hour AM/PM string representation."""
    if h == 0 or h == 24:
        return "12am"
    elif h == 12:
        return "12pm"
    elif h > 12:
        return f"{h - 12}pm"
    else:
        return f"{h}am"

def format_time_range(start, end):
    """Formats a 2-hour range into a clean string, e.g. 8-10am or 10am-12pm."""
    start_str = format_hour(start)
    end_str = format_hour(end)
    if start_str[-2:] == end_str[-2:]:
        return f"{start_str[:-2]}-{end_str}"
    else:
        return f"{start_str}-{end_str}"

def format_weekday_short(day_name):
    """Returns short 3-letter weekday name."""
    mapping = {
        'Monday': 'Mon', 'Tuesday': 'Tue', 'Wednesday': 'Wed',
        'Thursday': 'Thu', 'Friday': 'Fri', 'Saturday': 'Sat', 'Sunday': 'Sun'
    }
    return mapping.get(day_name, day_name[:3])

def run_recurrence_mining(clean_parquet_path, scored_parquet_path, calendar_parquet_path):
    print("=" * 80)
    print("GRIDWATCH RECURRENCE MINING ENGINE STARTED")
    print(f"Loading cleaned data from: {clean_parquet_path}")
    print(f"Loading scored hotspots from: {scored_parquet_path}")
    print("=" * 80)
    
    if not os.path.exists(clean_parquet_path):
        raise FileNotFoundError(f"Cleaned parquet not found at {clean_parquet_path}")
    if not os.path.exists(scored_parquet_path):
        raise FileNotFoundError(f"Scored hotspots parquet not found at {scored_parquet_path}")
        
    df = pd.read_parquet(clean_parquet_path)
    hotspots = pd.read_parquet(scored_parquet_path)
    
    if len(df) == 0 or len(hotspots) == 0:
        print("Empty dataset. Generating empty predictive calendar.")
        empty_cols = [
            'cluster_id', 'junction_name', 'police_station', 'day_of_week', 
            'start_hour', 'end_hour', 'recurrence_probability', 
            'congestion_cost_score', 'recommended_action'
        ]
        df_empty = pd.DataFrame(columns=empty_cols)
        df_empty.to_parquet(calendar_parquet_path, index=False)
        return
        
    # Standardize created_datetime as datetime with UTC
    df['created_datetime'] = pd.to_datetime(df['created_datetime'], errors='coerce', utc=True)
    
    # Recreate cluster_id to match hotspots
    df['grid_lat'] = (df['latitude'] / 0.00045).round() * 0.00045
    df['grid_lon'] = (df['longitude'] / 0.00046).round() * 0.00046
    df['cluster_id'] = np.where(
        (df['junction_name'].notna()) & (df['junction_name'] != 'No Junction') & (df['junction_name'] != ''),
        df['junction_name'],
        "GRID_" + df['grid_lat'].round(5).astype(str) + "_" + df['grid_lon'].round(5).astype(str)
    )
    
    # 1. Bucket by day of week and 2-hour range
    df['day_of_week'] = df['created_datetime'].dt.day_name()
    df['start_hour'] = (df['created_datetime'].dt.hour // 2) * 2
    df['end_hour'] = df['start_hour'] + 2
    df['year_week'] = df['created_datetime'].dt.strftime('%G-W%V')
    
    # Compute total weeks observed per weekday
    weeks_per_weekday = df.groupby('day_of_week')['year_week'].nunique().to_dict()
    
    # 2. Count occurrences (unique weeks containing a violation in the window)
    print("Calculating recurrence statistics per window...")
    window_stats = df.groupby(['cluster_id', 'day_of_week', 'start_hour', 'end_hour'])['year_week'].nunique().reset_index()
    window_stats = window_stats.rename(columns={'year_week': 'occurrences'})
    
    window_stats['total_weeks'] = window_stats['day_of_week'].map(weeks_per_weekday)
    window_stats['recurrence_probability'] = window_stats['occurrences'] / window_stats['total_weeks']
    
    # 3. Filter for windows with recurrence probability >= 0.5
    predictive_df = window_stats[window_stats['recurrence_probability'] >= 0.5].copy()
    print(f"Filtered {len(window_stats):,} windows down to {len(predictive_df):,} recurring windows (probability >= 50%).")
    
    # 4. Merge with scored hotspots data
    print("Merging with congestion score dataset...")
    predictive_df = pd.merge(
        predictive_df,
        hotspots[['cluster_id', 'junction_name', 'police_station', 'congestion_cost_score']],
        on='cluster_id',
        how='inner'
    )
    
    # 5. Generate recommended action text
    def generate_action(row):
        time_str = format_time_range(row['start_hour'], row['end_hour'])
        day_short = format_weekday_short(row['day_of_week'])
        hit_rate = int(round(row['recurrence_probability'] * 100))
        return f"Deploy patrol {time_str} {day_short}, {hit_rate}% historical hit rate"
        
    predictive_df['recommended_action'] = predictive_df.apply(generate_action, axis=1)
    
    # Order and clean columns
    output_cols = [
        'cluster_id', 'junction_name', 'police_station', 'day_of_week', 
        'start_hour', 'end_hour', 'recurrence_probability', 
        'congestion_cost_score', 'recommended_action'
    ]
    predictive_df = predictive_df[output_cols]
    
    # Save output to Parquet
    print(f"Saving predictive calendar to: {calendar_parquet_path}")
    os.makedirs(os.path.dirname(calendar_parquet_path), exist_ok=True)
    predictive_df.to_parquet(calendar_parquet_path, engine='pyarrow', index=False)
    
    # 6. Rank by value (recurrence_probability * congestion_cost_score) and print top 20
    predictive_df['priority_value'] = predictive_df['recurrence_probability'] * predictive_df['congestion_cost_score']
    print_top_recommendations(predictive_df, 20)
    
    print("=" * 80)
    print("GRIDWATCH RECURRENCE MINING ENGINE COMPLETED")
    print("=" * 80)

def print_top_recommendations(df, top_n=20):
    df_sorted = df.sort_values('priority_value', ascending=False).head(top_n)
    
    print("\n" + "=" * 125)
    print("                                      TOP 20 NEXT-ENFORCEMENT OPPORTUNITIES                                      ")
    print("=" * 125)
    header_fmt = " {rank:>2} | {location:<32} | {station:<14} | {weekday:<9} | {block:<9} | {prob:>7} | {c_score:>7} | {val:>7} "
    print(header_fmt.format(
        rank="Rk", location="Junction / Grid Location", station="Police Stn",
        weekday="Weekday", block="Time Block", prob="Recur %", c_score="Congest", val="Value"
    ))
    print("-" * 125)
    
    for i, (_, row) in enumerate(df_sorted.iterrows(), 1):
        loc_disp = row['junction_name'] if row['junction_name'] != 'No Junction' else row['cluster_id']
        if len(loc_disp) > 32:
            loc_disp = loc_disp[:29] + "..."
            
        station_disp = row['police_station'] if row['police_station'] else "Unknown"
        if len(station_disp) > 14:
            station_disp = station_disp[:11] + "..."
            
        prob_str = f"{int(round(row['recurrence_probability'] * 100))}%"
        congest_str = f"{row['congestion_cost_score']:.1f}"
        val_str = f"{row['priority_value']:.2f}"
        block_str = format_time_range(row['start_hour'], row['end_hour'])
        
        print(header_fmt.format(
            rank=i, location=loc_disp, station=station_disp,
            weekday=row['day_of_week'][:9], block=block_str,
            prob=prob_str, c_score=congest_str, val=val_str
        ))
        print(f"      Recommendation: {row['recommended_action']}")
    print("=" * 125 + "\n")

if __name__ == "__main__":
    CLEAN_PARQUET = os.path.join("data", "violations_clean.parquet")
    SCORED_PARQUET = os.path.join("data", "hotspots_scored.parquet")
    CALENDAR_PARQUET = os.path.join("data", "predictive_calendar.parquet")
    
    run_recurrence_mining(CLEAN_PARQUET, SCORED_PARQUET, CALENDAR_PARQUET)
