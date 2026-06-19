import os
import sys
import pandas as pd
import numpy as np

# Vehicle footprint mapping configuration (width in meters when illegally parked)
VEHICLE_FOOTPRINT = {
    'SCOOTER': 0.8,
    'MOPED': 0.8,
    'MOTOR CYCLE': 0.8,
    'CAR': 1.8,
    'PASSENGER AUTO': 1.8,
    'MAXI-CAB': 2.0,
    'VAN': 2.0,
    'LGV': 2.6,
    'PRIVATE BUS': 2.6,
    'GOODS AUTO': 2.6,
}
DEFAULT_FOOTPRINT = 1.8  # Default width (standard car) for unmapped vehicle types
DEFAULT_ROAD_WIDTH_M = 7.0  # Default road width in meters (2 lanes)
DEFAULT_DWELL_TIME_MINUTES = 20  # Assumed duration for violations with null closed_datetime

def get_road_width_from_osm(lat, lon):
    """
    NOTE: OSM Integration
    Integration with Overpass API or local OSM database to query the actual 
    road width/number of lanes for the given latitude and longitude is planned.
    
    For now, returns the default road width of 7.0 meters.
    """
    return DEFAULT_ROAD_WIDTH_M

def run_congestion_scoring(clean_parquet_path, scored_parquet_path):
    print("=" * 80)
    print("GRIDWATCH CONGESTION SCORING ENGINE STARTED")
    print(f"Loading cleaned data from: {clean_parquet_path}")
    print("=" * 80)
    
    if not os.path.exists(clean_parquet_path):
        raise FileNotFoundError(f"Cleaned data file not found at {clean_parquet_path}")
        
    df = pd.read_parquet(clean_parquet_path)
    if len(df) == 0:
        print("Empty dataset. Generating empty scored table.")
        empty_cols = [
            'cluster_id', 'representative_lat', 'representative_lon', 
            'junction_name', 'police_station', 'violation_count', 
            'peak_hour', 'peak_capacity_loss_pct', 'peak_delay_factor', 
            'congestion_cost_score', 'description'
        ]
        df_empty = pd.DataFrame(columns=empty_cols)
        df_empty.to_parquet(scored_parquet_path, index=False)
        return
        
    print(f"Processing {len(df):,} violations...")
    
    # Step 1: Apply vehicle footprint width
    df['footprint_width'] = df['vehicle_type'].map(VEHICLE_FOOTPRINT).fillna(DEFAULT_FOOTPRINT)
    
    # Step 2: Hotspot clustering
    # Round lat/lon to ~50m grid cells
    # 50m / 111,111m = 0.00045 deg latitude
    # 50m / (111,111m * cos(12.97 deg)) = 0.00046 deg longitude
    df['grid_lat'] = (df['latitude'] / 0.00045).round() * 0.00045
    df['grid_lon'] = (df['longitude'] / 0.00046).round() * 0.00046
    
    # Define group keys
    # Group by junction name if it is a valid junction, otherwise use grid coordinates
    df['cluster_id'] = np.where(
        (df['junction_name'].notna()) & (df['junction_name'] != 'No Junction') & (df['junction_name'] != ''),
        df['junction_name'],
        "GRID_" + df['grid_lat'].round(5).astype(str) + "_" + df['grid_lon'].round(5).astype(str)
    )
    
    # 3. Capacity Impact: Define active time window for each violation
    # Ensure start_time and closed_datetime are properly parsed UTC datetimes
    df['start_time'] = pd.to_datetime(df['created_datetime'], errors='coerce', utc=True)
    df['closed_time_parsed'] = pd.to_datetime(df['closed_datetime'], errors='coerce', utc=True)
    df['end_time'] = df['closed_time_parsed'].fillna(df['start_time'] + pd.Timedelta(minutes=DEFAULT_DWELL_TIME_MINUTES))
    
    df['date'] = df['start_time'].dt.date
    df['hour'] = df['start_time'].dt.hour
    
    # Compute start and end minutes in the hour
    df['start_m'] = df['start_time'].dt.minute + df['start_time'].dt.second / 60.0
    df['duration_m'] = (df['end_time'] - df['start_time']).dt.total_seconds() / 60.0
    df['end_m'] = (df['start_m'] + df['duration_m']).clip(upper=60.0)
    
    print("Calculating peak hourly concurrent widths...")
    # Optimized numpy boundary-based grouping to calculate peak overlapping width
    # Sort dataset by grouping dimensions to process contiguous arrays
    df_sorted = df.sort_values(['cluster_id', 'date', 'hour']).copy()
    cluster_ids = df_sorted['cluster_id'].values
    dates = df_sorted['date'].values
    hours = df_sorted['hour'].values
    starts = df_sorted['start_m'].values
    ends = df_sorted['end_m'].values
    widths = df_sorted['footprint_width'].values
    
    n = len(df_sorted)
    change_mask = (cluster_ids[:-1] != cluster_ids[1:]) | (dates[:-1] != dates[1:]) | (hours[:-1] != hours[1:])
    change_indices = np.where(change_mask)[0] + 1
    group_boundaries = [0] + list(change_indices) + [n]
    
    group_peaks = []
    for i in range(len(group_boundaries) - 1):
        g_start = group_boundaries[i]
        g_end = group_boundaries[i+1]
        
        c_id = cluster_ids[g_start]
        dt = dates[g_start]
        hr = hours[g_start]
        
        if g_end - g_start == 1:
            peak_w = widths[g_start]
        else:
            # Event-driven interval overlap algorithm to find peak concurrent width
            events = []
            for idx in range(g_start, g_end):
                events.append((starts[idx], widths[idx]))
                events.append((ends[idx], -widths[idx]))
            # End events first if times are equal (more conservative)
            events.sort(key=lambda x: (x[0], x[1]))
            
            max_w = 0.0
            curr_w = 0.0
            for t, w in events:
                curr_w += w
                if curr_w > max_w:
                    max_w = curr_w
            peak_w = max_w
            
        group_peaks.append({
            'cluster_id': c_id,
            'date': dt,
            'hour': hr,
            'peak_width': peak_w
        })
        
    df_peaks = pd.DataFrame(group_peaks)
    
    # Calculate average daily peak concurrent width per cluster per hour
    df_hourly = df_peaks.groupby(['cluster_id', 'hour'])['peak_width'].mean().reset_index()
    
    # Compute road capacity loss and delay factor for each cluster hour
    df_hourly['road_width'] = df_hourly.apply(
        lambda row: get_road_width_from_osm(0.0, 0.0), axis=1 # Replace with coords if mapping osm
    )
    df_hourly['capacity_loss_pct'] = df_hourly['peak_width'] / df_hourly['road_width']
    df_hourly['capacity_loss_pct'] = df_hourly['capacity_loss_pct'].clip(upper=0.90)  # Cap at 90%
    
    # BPR-style delay multiplier
    df_hourly['delay_factor'] = 1.0 / ((1.0 - df_hourly['capacity_loss_pct']) ** 2)
    df_hourly['delay_factor'] = df_hourly['delay_factor'].clip(upper=5.0)  # Cap at 5x delay
    
    # Find peak hour for each cluster (hour with maximum capacity loss)
    idx_max = df_hourly.groupby('cluster_id')['peak_width'].idxmax()
    df_cluster_peaks = df_hourly.loc[idx_max].copy().rename(columns={
        'hour': 'peak_hour',
        'capacity_loss_pct': 'peak_capacity_loss_pct',
        'delay_factor': 'peak_delay_factor'
    })[['cluster_id', 'peak_hour', 'peak_capacity_loss_pct', 'peak_delay_factor', 'road_width']]
    
    # Compute basic stats per cluster (counts, locations, modes)
    print("Aggregating overall cluster properties...")
    cluster_stats = df.groupby('cluster_id').agg(
        violation_count=('id', 'count'),
        representative_lat=('latitude', 'mean'),
        representative_lon=('longitude', 'mean'),
        junction_name=('junction_name', lambda x: x.mode().iloc[0] if not x.empty else 'No Junction'),
        police_station=('police_station', lambda x: x.mode().iloc[0] if not x.empty else None),
        avg_footprint_width=('footprint_width', 'mean')
    ).reset_index()
    
    # Calculate hourly distribution of violation counts (0-23)
    print("Computing hourly violation distribution for sparklines...")
    df['hour_val'] = df['start_time'].dt.hour
    hourly_counts = df.groupby(['cluster_id', 'hour_val']).size().unstack(fill_value=0)
    for h in range(24):
        if h not in hourly_counts.columns:
            hourly_counts[h] = 0
    hourly_counts = hourly_counts[list(range(24))]
    hourly_dist_series = hourly_counts.apply(lambda row: row.tolist(), axis=1)
    hourly_dist_df = pd.DataFrame({'cluster_id': hourly_dist_series.index, 'hourly_distribution': hourly_dist_series.values})
    
    cluster_stats = pd.merge(cluster_stats, hourly_dist_df, on='cluster_id', how='left')
    
    # Merge stats and scoring metrics
    df_scored = pd.merge(cluster_stats, df_cluster_peaks, on='cluster_id', how='left')
    
    # Step 4: Normalization & Scoring
    df_scored['raw_cost'] = df_scored['violation_count'] * df_scored['peak_delay_factor']
    
    max_raw_cost = df_scored['raw_cost'].max()
    if max_raw_cost > 0:
        df_scored['congestion_cost_score'] = (df_scored['raw_cost'] / max_raw_cost) * 100
    else:
        df_scored['congestion_cost_score'] = 0.0
        
    # Round final scores to 2 decimal places
    df_scored['congestion_cost_score'] = df_scored['congestion_cost_score'].round(2)
    
    # Plain English description
    def make_description(row):
        loss_pct = int(round(row['peak_capacity_loss_pct'] * 100))
        delay = round(row['peak_delay_factor'], 1)
        return f"Estimated {loss_pct}% capacity loss during peak hour, ~{delay}x normal delay."
        
    df_scored['description'] = df_scored.apply(make_description, axis=1)
    
    # Order columns
    output_cols = [
        'cluster_id', 'representative_lat', 'representative_lon', 
        'junction_name', 'police_station', 'violation_count', 
        'peak_hour', 'peak_capacity_loss_pct', 'peak_delay_factor', 
        'congestion_cost_score', 'description', 'hourly_distribution',
        'road_width', 'avg_footprint_width'
    ]
    df_scored = df_scored[output_cols]
    
    # Save output to Parquet
    print(f"Saving scored hotspots to: {scored_parquet_path}")
    os.makedirs(os.path.dirname(scored_parquet_path), exist_ok=True)
    df_scored.to_parquet(scored_parquet_path, engine='pyarrow', index=False)
    
    # Print top 15
    print_top_hotspots(df_scored, 15)
    print("=" * 80)
    print("GRIDWATCH CONGESTION SCORING ENGINE COMPLETED")
    print("=" * 80)

def print_top_hotspots(df, top_n=15):
    df_sorted = df.sort_values('congestion_cost_score', ascending=False).head(top_n)
    
    print("\n" + "=" * 110)
    print("                                TOP 15 CONGESTION HOTSPOTS (BY SCORE)                                ")
    print("=" * 110)
    header_fmt = " {rank:>2} | {cluster_id:<32} | {station:<14} | {counts:>7} | {hour:>7} | {loss:>8} | {delay:>5} | {score:>6} "
    print(header_fmt.format(
        rank="Rk", cluster_id="Cluster ID / Junction", station="Police Stn", 
        counts="Violations", hour="Peak Hr", loss="Cap Loss", delay="Delay", score="Score"
    ))
    print("-" * 110)
    
    for i, (_, row) in enumerate(df_sorted.iterrows(), 1):
        # Format values for display
        loss_str = f"{int(round(row['peak_capacity_loss_pct'] * 100))}%"
        delay_str = f"{row['peak_delay_factor']:.1f}x"
        score_str = f"{row['congestion_cost_score']:.2f}"
        hour_str = f"{int(row['peak_hour']):02d}:00"
        
        cluster_disp = row['cluster_id']
        if len(cluster_disp) > 32:
            cluster_disp = cluster_disp[:29] + "..."
            
        station_disp = row['police_station'] if row['police_station'] else "Unknown"
        if len(station_disp) > 14:
            station_disp = station_disp[:11] + "..."
            
        print(header_fmt.format(
            rank=i, cluster_id=cluster_disp, station=station_disp,
            counts=f"{row['violation_count']:,}", hour=hour_str, 
            loss=loss_str, delay=delay_str, score=score_str
        ))
        print(f"      Description: {row['description']}")
    print("=" * 110 + "\n")

if __name__ == "__main__":
    CLEAN_PARQUET = os.path.join("data", "violations_clean.parquet")
    SCORED_PARQUET = os.path.join("data", "hotspots_scored.parquet")
    
    run_congestion_scoring(CLEAN_PARQUET, SCORED_PARQUET)
