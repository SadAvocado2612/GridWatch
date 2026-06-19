"""
offender_network.py - Repeat-offender analysis and network graph construction.

Reads violations_clean.parquet and hotspots_scored.parquet, identifies repeat
offenders, classifies their patterns, and exports a d3-force-ready JSON graph.
"""
import os
import json
import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")

# Proximity threshold in degrees (~200m at Bengaluru's latitude)
PROXIMITY_DEG = 0.002


def _resolve_vehicle_id(row):
    """Use updated_vehicle_number when vehicle_number is null/placeholder."""
    vn = row.get("vehicle_number")
    uvn = row.get("updated_vehicle_number")
    if pd.isna(vn) or str(vn).strip() == "":
        return uvn if not pd.isna(uvn) else None
    return vn


def _is_placeholder(vid):
    """Return True for generic placeholder vehicle identifiers."""
    if vid is None or pd.isna(vid):
        return True
    s = str(vid).strip().upper()
    if len(s) <= 3:
        return True
    placeholders = {"UNKNOWN", "NA", "N/A", "NONE", "NULL", "TEST", "TEMP", "0", "00", "000"}
    return s in placeholders


def build_offender_network():
    """Main pipeline: load data, compute offender stats, build graph, export JSON."""

    # ── Load data ────────────────────────────────────────────────────────────
    clean_path = os.path.join(DATA_DIR, "violations_clean.parquet")
    hotspots_path = os.path.join(DATA_DIR, "hotspots_scored.parquet")

    df = pd.read_parquet(clean_path)
    hotspots = pd.read_parquet(hotspots_path)

    # ── Step 1: Resolve vehicle ID & drop placeholders ───────────────────────
    df["resolved_vehicle_id"] = df.apply(_resolve_vehicle_id, axis=1)

    before = len(df)
    mask_placeholder = df["resolved_vehicle_id"].apply(_is_placeholder)
    dropped_count = mask_placeholder.sum()
    df = df[~mask_placeholder].copy()
    print(f"[offender_network] Dropped {dropped_count:,} rows with placeholder vehicle IDs "
          f"(from {before:,} to {len(df):,})")

    # ── Step 2: Assign each violation to nearest hotspot cluster ──────────────
    hotspot_lats = hotspots["representative_lat"].values
    hotspot_lons = hotspots["representative_lon"].values
    hotspot_ids = hotspots["cluster_id"].values

    def find_nearest_cluster(lat, lon):
        """Find nearest hotspot cluster within PROXIMITY_DEG threshold."""
        dlat = hotspot_lats - lat
        dlon = hotspot_lons - lon
        dist = np.sqrt(dlat ** 2 + dlon ** 2)
        idx = np.argmin(dist)
        if dist[idx] <= PROXIMITY_DEG:
            return hotspot_ids[idx]
        return None

    print("[offender_network] Assigning violations to nearest hotspot clusters...")
    df["cluster_id"] = df.apply(
        lambda r: find_nearest_cluster(r["latitude"], r["longitude"]), axis=1
    )

    # Parse date for distinct-days computation
    df["violation_date"] = pd.to_datetime(df["created_datetime"], utc=True).dt.date

    # ── Step 3: Compute per-vehicle stats (>= 3 violations) ──────────────────
    vg = df.groupby("resolved_vehicle_id")
    vehicle_stats = vg.agg(
        total_violations=("resolved_vehicle_id", "count"),
        distinct_days=("violation_date", "nunique"),
    ).reset_index()

    # Distinct clusters visited
    cluster_counts = (
        df[df["cluster_id"].notna()]
        .groupby("resolved_vehicle_id")["cluster_id"]
        .nunique()
        .reset_index()
        .rename(columns={"cluster_id": "distinct_clusters"})
    )
    vehicle_stats = vehicle_stats.merge(cluster_counts, on="resolved_vehicle_id", how="left")
    vehicle_stats["distinct_clusters"] = vehicle_stats["distinct_clusters"].fillna(0).astype(int)

    # Filter to >= 3 violations
    repeat_offenders = vehicle_stats[vehicle_stats["total_violations"] >= 3].copy()
    print(f"[offender_network] Found {len(repeat_offenders):,} repeat offenders (>=3 violations)")

    # ── Classification ───────────────────────────────────────────────────────
    # For each vehicle, compute per-cluster violation counts
    vehicle_cluster_counts = (
        df[df["cluster_id"].notna()]
        .groupby(["resolved_vehicle_id", "cluster_id"])
        .size()
        .reset_index(name="count_at_cluster")
    )

    def classify_vehicle(vid, total_v, distinct_c):
        """Classify as habitual, roaming, or mixed."""
        if distinct_c == 0:
            return "mixed"
        vcc = vehicle_cluster_counts[vehicle_cluster_counts["resolved_vehicle_id"] == vid]
        if len(vcc) == 0:
            return "mixed"
        max_at_single = vcc["count_at_cluster"].max()
        if max_at_single / total_v >= 0.70:
            return "habitual"
        if distinct_c >= 3:
            return "roaming"
        return "mixed"

    repeat_offenders["classification"] = repeat_offenders.apply(
        lambda r: classify_vehicle(
            r["resolved_vehicle_id"], r["total_violations"], r["distinct_clusters"]
        ),
        axis=1,
    )

    class_dist = repeat_offenders["classification"].value_counts()
    print(f"[offender_network] Classification distribution:\n{class_dist.to_string()}")

    # ── Step 4: Build d3-force graph ─────────────────────────────────────────
    # Top 150 vehicles by total_violations
    top_vehicles = repeat_offenders.nlargest(150, "total_violations")
    top_vids = set(top_vehicles["resolved_vehicle_id"])

    # Filter edges to only top vehicles
    edges_df = vehicle_cluster_counts[
        vehicle_cluster_counts["resolved_vehicle_id"].isin(top_vids)
    ].copy()

    # Collect cluster IDs that appear in edges
    cluster_ids_in_graph = set(edges_df["cluster_id"].unique())

    # Build node list
    nodes = []
    vid_to_class = dict(zip(top_vehicles["resolved_vehicle_id"], top_vehicles["classification"]))
    vid_to_total = dict(zip(top_vehicles["resolved_vehicle_id"], top_vehicles["total_violations"]))

    for vid in top_vids:
        nodes.append({
            "id": vid,
            "type": "vehicle",
            "label": vid,
            "size": int(vid_to_total.get(vid, 3)),
            "classification": vid_to_class.get(vid, "mixed"),
        })

    cluster_name_map = dict(zip(hotspots["cluster_id"], hotspots["junction_name"]))
    cluster_score_map = dict(zip(hotspots["cluster_id"], hotspots["congestion_cost_score"]))

    for cid in cluster_ids_in_graph:
        nodes.append({
            "id": cid,
            "type": "cluster",
            "label": cluster_name_map.get(cid, cid),
            "size": float(cluster_score_map.get(cid, 10)),
        })

    # Build link list
    links = []
    for _, row in edges_df.iterrows():
        links.append({
            "source": row["resolved_vehicle_id"],
            "target": row["cluster_id"],
            "weight": int(row["count_at_cluster"]),
        })

    graph = {"nodes": nodes, "links": links}

    # Export
    out_path = os.path.join(DATA_DIR, "offender_network.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(graph, f, ensure_ascii=False)
    print(f"[offender_network] Exported graph: {len(nodes)} nodes, {len(links)} links -> {out_path}")

    # ── Also export top-offenders flat table ─────────────────────────────────
    top_table = repeat_offenders.nlargest(500, "total_violations")[
        ["resolved_vehicle_id", "total_violations", "distinct_clusters", "distinct_days", "classification"]
    ].rename(columns={"resolved_vehicle_id": "vehicle_id"})

    table_path = os.path.join(DATA_DIR, "top_offenders.json")
    top_table.to_json(table_path, orient="records", force_ascii=False)
    print(f"[offender_network] Exported top offenders table: {len(top_table)} rows -> {table_path}")

    return graph, top_table.to_dict(orient="records")


if __name__ == "__main__":
    build_offender_network()
