import json
import os
import re
import sys
from pathlib import Path

from pygltflib import GLTF2, Node
import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.common_paths import DATA_ROOT, OUTPUT_ROOT

GLB_PATH = DATA_ROOT / "gearbox_service_unit.glb"
MAPPING_PATH = OUTPUT_ROOT / "mapping.json"
STEPS_PATH = OUTPUT_ROOT / "resolved_steps.json"
FILTERED_PATH = OUTPUT_ROOT / "filtered_nodes.json"
OUT_GLB_PATH = OUTPUT_ROOT / "gearbox_restructured.glb"


def make_group_name(step_id, title):
    # Convert special characters and format to PascalCase
    title = title.replace("&", "And").replace("/", "Or").replace("-", " ")
    title = re.sub(r"[^a-zA-Z0-9\s]", "", title)
    words = title.strip().split()
    camel_title = "".join(w.capitalize() for w in words)
    sid = step_id.replace("-", "_")
    return f"Step_{sid}_{camel_title}"


def main():
    print("Stage 8 -- Restructuring GLB Hierarchy Using pygltflib")
    print("=" * 60)
    
    # 1. Load resources
    gltf = GLTF2.load(GLB_PATH)
    mapping_data = json.load(open(MAPPING_PATH))
    steps = json.load(open(STEPS_PATH))
    filtered = json.load(open(FILTERED_PATH))
    
    print(f"Original GLB nodes: {len(gltf.nodes)}")
    
    step_dict = {s["step_id"]: s for s in steps}
    
    # Map node name to index in gltf.nodes
    node_name_to_idx = {}
    for idx, node in enumerate(gltf.nodes):
        if node.name:
            node_name_to_idx[node.name] = idx
            
    # Track assigned nodes
    assigned_indices = set()
    step_groups = []
    
    # 2. Construct Step Group Nodes
    for assignment in mapping_data["assignments"]:
        step_id = assignment["step_id"]
        assigned_meshes = assignment["assigned_meshes"]
        title = step_dict[step_id]["title"]
        
        group_name = make_group_name(step_id, title)
        
        child_indices = []
        for name in assigned_meshes:
            if name in node_name_to_idx:
                idx = node_name_to_idx[name]
                child_indices.append(idx)
                assigned_indices.add(idx)
            else:
                print(f"[WARNING] Mesh '{name}' from mapping not found in GLB nodes.")
                
        # Create group node
        group_node = Node(name=group_name, children=child_indices)
        group_idx = len(gltf.nodes)
        gltf.nodes.append(group_node)
        step_groups.append(group_idx)
        print(f"  Created group '{group_name}' with {len(child_indices)} meshes (Index: {group_idx})")

    # 3. Construct Excluded_Stale_Drafts Group Node
    excluded_meshes = [name for name, info in filtered.items() if info["excluded"]]
    excluded_indices = []
    for name in excluded_meshes:
        if name in node_name_to_idx:
            idx = node_name_to_idx[name]
            excluded_indices.append(idx)
            assigned_indices.add(idx)
        else:
            print(f"[WARNING] Excluded mesh '{name}' not found in GLB nodes.")
            
    excluded_group = Node(name="Excluded_Stale_Drafts", children=excluded_indices)
    excluded_idx = len(gltf.nodes)
    gltf.nodes.append(excluded_group)
    print(f"  Created group 'Excluded_Stale_Drafts' with {len(excluded_indices)} meshes (Index: {excluded_idx})")
    
    # 4. Check for any leftover mesh nodes
    leftover_indices = []
    for idx in range(1, 103): # Mesh indices 1 to 102
        if idx not in assigned_indices:
            leftover_indices.append(idx)
            
    if leftover_indices:
        print(f"[WARNING] {len(leftover_indices)} mesh nodes were left out of groups. Adding to Unassigned.")
        unassigned_group = Node(name="Unassigned", children=leftover_indices)
        unassigned_idx = len(gltf.nodes)
        gltf.nodes.append(unassigned_group)
        all_groups = step_groups + [excluded_idx, unassigned_idx]
    else:
        print("[SUCCESS] All 102 meshes account for in group nodes.")
        all_groups = step_groups + [excluded_idx]
        
    # 5. Connect Groups to Node 0 ("world")
    gltf.nodes[0].children = all_groups
    
    # 6. Save restructured GLB
    print(f"Saving restructured asset to: {OUT_GLB_PATH}...")
    gltf.save(OUT_GLB_PATH)
    
    # 7. Verification load using trimesh
    print("Validating saved GLB using trimesh...")
    try:
        scene = trimesh.load(OUT_GLB_PATH)
        print("[SUCCESS] Restructured GLB loaded in trimesh without validation errors!")
        print(f"  Scene geometries count: {len(scene.geometry)}")
    except Exception as e:
        print(f"[ERROR] Restructured GLB loading failed or is invalid: {e}")

if __name__ == "__main__":
    main()
