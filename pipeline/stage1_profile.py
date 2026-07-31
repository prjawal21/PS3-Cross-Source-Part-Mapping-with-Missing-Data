import json
import os
import sys
from pathlib import Path

import numpy as np
import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.common_paths import DATA_ROOT, OUTPUT_ROOT

GLB_PATH = DATA_ROOT / "gearbox_service_unit.glb"
OUT_DIR = OUTPUT_ROOT
OUT_PATH = OUT_DIR / "geometry_profile.json"

def main():
    scene = trimesh.load(GLB_PATH)
    if not isinstance(scene, trimesh.Scene):
        raise SystemExit("Expected a Scene (multiple nodes) — got a single mesh instead.")

    records = []
    # Using sorted list for deterministic serialization
    for node_name in sorted(scene.graph.nodes_geometry):
        transform, geom_name = scene.graph[node_name]
        geom = scene.geometry[geom_name]
        verts_world = trimesh.transform_points(geom.vertices, transform)

        mins = verts_world.min(axis=0)
        maxs = verts_world.max(axis=0)
        extents = maxs - mins
        centroid = verts_world.mean(axis=0)
        volume = float(extents[0] * extents[1] * extents[2])

        records.append({
            "node_name": node_name,
            "geometry_name": geom_name,
            "vertex_count": int(geom.vertices.shape[0]),
            "centroid": centroid.tolist(),
            "bbox_min": mins.tolist(),
            "bbox_max": maxs.tolist(),
            "bbox_extents": extents.tolist(),
            "bbox_volume": volume,
        })

    with open(OUT_PATH, "w") as f:
        json.dump(records, f, indent=2)

    vols = np.array([r["bbox_volume"] for r in records])
    print(f"Profiled {len(records)} mesh nodes -> {OUT_PATH}")
    print(f"Volume range: {vols.min():.4f} to {vols.max():.1f}")
    
    # Assert and verify node count
    assert len(records) == 102, f"Expected 102 geometry nodes, but got {len(records)}"
    print("[OK] Verification passed: node count is exactly 102")

if __name__ == "__main__":
    main()
