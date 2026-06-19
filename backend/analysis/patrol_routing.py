import os
import sys
import math
import pandas as pd
import numpy as np

# Configurable constants
PATROL_DWELL_TIME_MINUTES = 30  # Assumed duration patrol stays at each hotspot
AVERAGE_URBAN_SPEED_KMH = 20.0   # Average speed in km/h

def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Computes the great-circle distance between two points on the Earth's surface
    using the Haversine formula. Returns distance in kilometers.
    """
    R = 6371.0  # Earth's radius in kilometers
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 + 
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    c = 2 * math.asin(math.sqrt(a))
    return R * c

def plan_patrols(day_of_week, hour, num_units):
    """
    Given N patrol units, plans routes for the specified day of the week and hour.
    Returns a dictionary mapping unit index to an ordered list of planned stops.
    """
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    calendar_path = os.path.join(project_root, "data", "predictive_calendar.parquet")
    hotspots_path = os.path.join(project_root, "data", "hotspots_scored.parquet")
    
    if not os.path.exists(calendar_path) or not os.path.exists(hotspots_path):
        raise FileNotFoundError("Calendar or Hotspots scored Parquet file not found. Ensure previous steps are run.")
        
    df_cal = pd.read_parquet(calendar_path)
    df_hot = pd.read_parquet(hotspots_path)
    
    # 1. Filter calendar to windows active at that day/hour
    df_filtered = df_cal[
        (df_cal['day_of_week'].str.lower() == day_of_week.lower()) &
        (df_cal['start_hour'] <= hour) &
        (df_cal['end_hour'] > hour)
    ].copy()
    
    if len(df_filtered) == 0:
        return {u: [] for u in range(num_units)}
        
    # 2. Merge with hotspots table to get lat/lon coords
    df_merged = pd.merge(
        df_filtered,
        df_hot[['cluster_id', 'representative_lat', 'representative_lon']],
        on='cluster_id',
        how='inner'
    )
    
    # Calculate priority rank
    df_merged['priority_value'] = df_merged['congestion_cost_score'] * df_merged['recurrence_probability']
    df_merged = df_merged.sort_values('priority_value', ascending=False)
    
    candidates = df_merged.to_dict('records')
    routes = {u: [] for u in range(num_units)}
    unvisited = candidates.copy()
    
    # 3. Greedy Nearest-Neighbor Route Builder
    # Seed routes for each unit using the highest-priority targets
    for u in range(num_units):
        if not unvisited:
            break
        stop = unvisited.pop(0)
        stop['distance_from_prev_km'] = 0.0
        routes[u].append(stop)
        
    # Greedily allocate remaining unvisited stops to the nearest active unit
    while unvisited:
        for u in range(num_units):
            if not unvisited:
                break
                
            # If the unit is currently idle, seed it with the highest priority unvisited stop
            if not routes[u]:
                stop = unvisited.pop(0)
                stop['distance_from_prev_km'] = 0.0
                routes[u].append(stop)
                continue
                
            # Find the unvisited stop closest to the last stop in unit u's route
            last_stop = routes[u][-1]
            lat1, lon1 = last_stop['representative_lat'], last_stop['representative_lon']
            
            best_idx = 0
            min_dist = float('inf')
            for idx, cand in enumerate(unvisited):
                lat2, lon2 = cand['representative_lat'], cand['representative_lon']
                dist = haversine_distance(lat1, lon1, lat2, lon2)
                if dist < min_dist:
                    min_dist = dist
                    best_idx = idx
                    
            closest_stop = unvisited.pop(best_idx)
            closest_stop['distance_from_prev_km'] = min_dist
            routes[u].append(closest_stop)
            
    # 4. Calculate ETAs per unit
    # Speed is 20 km/h -> 3 minutes per kilometer
    minutes_per_km = 60.0 / AVERAGE_URBAN_SPEED_KMH
    
    for u in range(num_units):
        current_minutes = hour * 60.0  # Start planning at the beginning of the requested hour
        
        for stop in routes[u]:
            dist = stop['distance_from_prev_km']
            travel_time_mins = dist * minutes_per_km
            
            # Arrival Time (ETA)
            arrival_minutes = current_minutes + travel_time_mins
            arrival_hour = int(arrival_minutes // 60) % 24
            arrival_min = int(round(arrival_minutes % 60))
            if arrival_min == 60:
                arrival_hour = (arrival_hour + 1) % 24
                arrival_min = 0
                
            stop['travel_time_mins'] = travel_time_mins
            stop['eta'] = f"{arrival_hour:02d}:{arrival_min:02d}"
            
            # Departure Time (Arrival + Dwell Time)
            departure_minutes = arrival_minutes + PATROL_DWELL_TIME_MINUTES
            current_minutes = departure_minutes
            
    return routes

def print_patrol_plan(routes, day_of_week, hour, num_units):
    print("=" * 110)
    print(f"                               GRIDWATCH PATROL ROUTING DISPATCH PLAN                               ")
    print(f"                                 Time: {day_of_week} at {hour:02d}:00 | Units: {num_units}                                 ")
    print("=" * 110)
    
    for u in range(num_units):
        route = routes.get(u, [])
        print(f"\n[UNIT {u+1}] Route:")
        print("-" * 110)
        
        if not route:
            print("  (Idle - No active enforcement windows assigned)")
            continue
            
        total_dist = 0.0
        total_travel_time = 0.0
        
        for i, stop in enumerate(route, 1):
            dist = stop['distance_from_prev_km']
            travel = stop['travel_time_mins']
            total_dist += dist
            total_travel_time += travel
            
            loc_disp = stop['junction_name'] if stop['junction_name'] != 'No Junction' else stop['cluster_id']
            if len(loc_disp) > 40:
                loc_disp = loc_disp[:37] + "..."
                
            prob_pct = int(round(stop['recurrence_probability'] * 100))
            score = stop['congestion_cost_score']
            prio = stop['priority_value']
            
            lat = stop['representative_lat']
            lon = stop['representative_lon']
            
            if i == 1:
                print(f"  {i:>2}. STOP: {loc_disp:<40} | ETA: {stop['eta']} | Start Point")
            else:
                print(f"  {i:>2}. STOP: {loc_disp:<40} | ETA: {stop['eta']} | +{dist:.2f} km ({int(round(travel))} mins)")
                
            print(f"      Coords: ({lat:.5f}, {lon:.5f}) | Congestion Score: {score:.1f} | Hit Rate: {prob_pct}% | Priority: {prio:.2f}")
            print(f"      Action: {stop['recommended_action']}")
            
        print("-" * 110)
        total_time_mins = total_travel_time + (len(route) * PATROL_DWELL_TIME_MINUTES)
        hours_tot = int(total_time_mins // 60)
        mins_tot = int(round(total_time_mins % 60))
        print(f"  Summary: {len(route)} stops | Total Travel Dist: {total_dist:.2f} km | Total Route Time: {hours_tot}h {mins_tot}m")
    print("=" * 110 + "\n")

if __name__ == "__main__":
    # Test 1: Requested CLI test for Monday, 8 AM, with 3 units
    try:
        print("Running Test 1: Monday at 08:00 (3 units)...")
        planned_routes = plan_patrols("Monday", 8, 3)
        print_patrol_plan(planned_routes, "Monday", 8, 3)
    except Exception as e:
        print(f"Error running test 1: {e}")
        print("Ensure you run clean_data.py, congestion_score.py, and recurrence_mining.py first.")
        
    # Test 2: High-density Sunday, 4 AM, with 3 units to demonstrate routing logic
    try:
        print("Running Test 2: Sunday at 04:00 (3 units)...")
        planned_routes = plan_patrols("Sunday", 4, 3)
        print_patrol_plan(planned_routes, "Sunday", 4, 3)
    except Exception as e:
        print(f"Error running test 2: {e}")
