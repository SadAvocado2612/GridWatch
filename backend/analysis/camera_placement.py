import os
import sys
import math
import pandas as pd
import numpy as np

def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculates great-circle distance in kilometers.
    """
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 + 
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    c = 2 * math.asin(math.sqrt(a))
    return R * c

def compute_distances_vectorized(hotspot_lats, hotspot_lons, device_lats, device_lons):
    """
    Numpy-vectorized Haversine distance calculator. Returns an array of shape (N,) 
    representing the minimum distance in meters from each hotspot to the nearest camera.
    """
    h_lats = np.radians(hotspot_lats)[:, np.newaxis]
    h_lons = np.radians(hotspot_lons)[:, np.newaxis]
    d_lats = np.radians(device_lats)[np.newaxis, :]
    d_lons = np.radians(device_lons)[np.newaxis, :]
    
    dlat = d_lats - h_lats
    dlon = d_lons - h_lons
    
    a = np.sin(dlat / 2.0)**2 + np.cos(h_lats) * np.cos(d_lats) * np.sin(dlon / 2.0)**2
    c = 2.0 * np.arcsin(np.sqrt(a))
    dists = 6371.0 * c * 1000.0  # Convert to meters
    
    return np.min(dists, axis=1)

def run_camera_placement(clean_parquet_path, scored_parquet_path, recommendations_parquet_path, K=10):
    print("=" * 80)
    print("GRIDWATCH CAMERA PLACEMENT PLANNING STARTED")
    print(f"Loading cleaned data from: {clean_parquet_path}")
    print(f"Loading scored hotspots from: {scored_parquet_path}")
    print("=" * 80)
    
    if not os.path.exists(clean_parquet_path) or not os.path.exists(scored_parquet_path):
        raise FileNotFoundError("Cleaned parquet or scored hotspots parquet not found. Run previous steps first.")
        
    df_clean = pd.read_parquet(clean_parquet_path)
    df_hot = pd.read_parquet(scored_parquet_path)
    
    if len(df_clean) == 0 or len(df_hot) == 0:
        print("Empty dataset. Generating empty recommendations table.")
        empty_cols = [
            'cluster_id', 'lat', 'lon', 'junction_name', 
            'congestion_cost_score', 'distance_to_nearest_existing_device_m', 'justification'
        ]
        df_empty = pd.DataFrame(columns=empty_cols)
        df_empty.to_parquet(recommendations_parquet_path, index=False)
        return
        
    # 1. Identify existing enforcement coverage
    # Filter out null/invalid device_ids
    df_devices = df_clean[
        df_clean['device_id'].notna() & 
        (df_clean['device_id'].astype(str).str.strip().str.upper() != 'NULL') &
        (df_clean['device_id'].astype(str).str.strip() != '')
    ]
    
    print("Calculating existing camera centroids...")
    device_centroids = df_devices.groupby('device_id')[['latitude', 'longitude']].mean().reset_index()
    print(f"Found {len(device_centroids):,} active enforcement devices in the dataset.")
    
    # 2. For every hotspot cluster, compute distance to the nearest existing device centroid
    print("Computing distances to nearest existing cameras (vectorized)...")
    if len(device_centroids) > 0:
        min_dists = compute_distances_vectorized(
            df_hot['representative_lat'].values,
            df_hot['representative_lon'].values,
            device_centroids['latitude'].values,
            device_centroids['longitude'].values
        )
    else:
        # If no cameras exist, distance is infinite
        min_dists = np.full(len(df_hot), float('inf'))
        
    df_hot['distance_to_nearest_existing_device_m'] = min_dists
    
    # 3. Flag coverage gaps (distance > 300m and top 30% of congestion_cost_score)
    congest_threshold = df_hot['congestion_cost_score'].quantile(0.70)
    print(f"Congestion cost score 70th percentile threshold: {congest_threshold:.2f}")
    
    df_hot['is_coverage_gap'] = (
        (df_hot['distance_to_nearest_existing_device_m'] > 300.0) &
        (df_hot['congestion_cost_score'] >= congest_threshold)
    )
    
    # Compute overall rank across all hotspots
    df_hot_sorted = df_hot.sort_values('congestion_cost_score', ascending=False).copy()
    df_hot_sorted['overall_rank'] = range(1, len(df_hot_sorted) + 1)
    
    gap_candidates = df_hot_sorted[df_hot_sorted['is_coverage_gap']].copy()
    print(f"Identified {len(gap_candidates):,} coverage gaps among hotspots.")
    
    # 4. Greedy maximum-coverage selection (top K spaced at least 200m apart)
    print(f"Selecting top {K} camera locations (spacing constraint >= 200m)...")
    selected_list = []
    
    for _, row in gap_candidates.iterrows():
        if len(selected_list) >= K:
            break
            
        lat1, lon1 = row['representative_lat'], row['representative_lon']
        too_close = False
        
        # Check distance to already selected recommendation sites
        for sel in selected_list:
            lat2, lon2 = sel['representative_lat'], sel['representative_lon']
            dist = haversine_distance(lat1, lon1, lat2, lon2) * 1000.0  # Distance in meters
            if dist < 200.0:
                too_close = True
                break
                
        if not too_close:
            selected_list.append(row)
            
    df_recs = pd.DataFrame(selected_list) if selected_list else pd.DataFrame(columns=df_hot_sorted.columns)
    
    # Format justification
    def generate_justification(row):
        dist_m = int(round(row['distance_to_nearest_existing_device_m']))
        dist_str = f"{dist_m}m" if dist_m != float('inf') else "infinity"
        rank = row['overall_rank']
        return f"No existing device within 300m (nearest is {dist_str}); ranked #{rank} by congestion impact."
        
    if len(df_recs) > 0:
        df_recs['justification'] = df_recs.apply(generate_justification, axis=1)
        
    # Order and clean columns
    df_recs = df_recs.rename(columns={
        'representative_lat': 'lat',
        'representative_lon': 'lon'
    })
    
    output_cols = [
        'cluster_id', 'lat', 'lon', 'junction_name', 
        'congestion_cost_score', 'distance_to_nearest_existing_device_m', 'justification'
    ]
    df_recs = df_recs[output_cols]
    
    # Save output to Parquet
    print(f"Saving camera recommendations to: {recommendations_parquet_path}")
    os.makedirs(os.path.dirname(recommendations_parquet_path), exist_ok=True)
    df_recs.to_parquet(recommendations_parquet_path, engine='pyarrow', index=False)
    
    # Print top K recommendations
    print_camera_recommendations(df_recs, K)
    print("=" * 80)
    print("GRIDWATCH CAMERA PLACEMENT PLANNING COMPLETED")
    print("=" * 80)

def print_camera_recommendations(df, K):
    print("\n" + "=" * 120)
    print(f"                                   RECOMMENDED NEW CAMERA PLACEMENTS (TOP {K})                                   ")
    print("=" * 120)
    header_fmt = " {rank:>2} | {location:<32} | {coords:<24} | {score:>7} | {dist:>10} | {justification:<40} "
    print(header_fmt.format(
        rank="Rk", location="Junction / Grid Location", coords="Coordinates (Lat, Lon)",
        score="Score", dist="Near Dev(m)", justification="Justification Summary"
    ))
    print("-" * 120)
    
    for i, (_, row) in enumerate(df.iterrows(), 1):
        loc_disp = row['junction_name'] if row['junction_name'] != 'No Junction' else row['cluster_id']
        if len(loc_disp) > 32:
            loc_disp = loc_disp[:29] + "..."
            
        coords_str = f"{row['lat']:.5f}, {row['lon']:.5f}"
        score_str = f"{row['congestion_cost_score']:.1f}"
        
        dist_val = row['distance_to_nearest_existing_device_m']
        dist_str = f"{int(round(dist_val))}m" if dist_val != float('inf') else "inf"
        
        just_str = row['justification']
        if len(just_str) > 40:
            just_str = just_str[:37] + "..."
            
        print(header_fmt.format(
            rank=i, location=loc_disp, coords=coords_str,
            score=score_str, dist=dist_str, justification=just_str
        ))
    print("=" * 120 + "\n")

if __name__ == "__main__":
    CLEAN_PARQUET = os.path.join("data", "violations_clean.parquet")
    SCORED_PARQUET = os.path.join("data", "hotspots_scored.parquet")
    RECS_PARQUET = os.path.join("data", "camera_recommendations.parquet")
    
    run_camera_placement(CLEAN_PARQUET, SCORED_PARQUET, RECS_PARQUET, K=10)
