import json
import os
import base64
import io
import time
import re
import sys
from pathlib import Path

import requests
import numpy as np
import trimesh
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.common_paths import DATA_ROOT, OUTPUT_ROOT

# ----- Configuration -----
GLB_PATH = DATA_ROOT / "gearbox_service_unit.glb"
MAPPING_PATH = OUTPUT_ROOT / "step_assignments_stage5.json"
STEPS_PATH = OUTPUT_ROOT / "resolved_steps.json"
PROFILE_PATH = OUTPUT_ROOT / "geometry_profile.json"
OUTPUT_DIR = OUTPUT_ROOT
LOG_PATH = OUTPUT_DIR / "agent_log.jsonl"

OLLAMA_URL = "http://localhost:11434"
VLM_MODEL = "moondream:latest"
RENDER_RESOLUTION = (800, 600)


def log_entry(entry):
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def get_node_world_vertices(scene, node_name):
    transform, geom_name = scene.graph[node_name]
    geom = scene.geometry[geom_name]
    return trimesh.transform_points(geom.vertices, transform), geom.faces


def compute_global_bounds(profile_path, margin_frac=0.08):
    if not os.path.exists(profile_path):
        return np.array([-100.0, -100.0, -100.0]), np.array([100.0, 100.0, 100.0])
    try:
        recs = json.load(open(profile_path))
        mins = np.array([r["bbox_min"] for r in recs]).min(axis=0)
        maxs = np.array([r["bbox_max"] for r in recs]).max(axis=0)
        extents = maxs - mins
        margin = extents * margin_frac
        return mins - margin, maxs + margin
    except Exception:
        return np.array([-100.0, -100.0, -100.0]), np.array([100.0, 100.0, 100.0])


# Global bounding box computed once
GLOBAL_MIN, GLOBAL_MAX = compute_global_bounds(PROFILE_PATH)


def make_shaded_collection(faces_xyz, base_color=(0.75, 0.75, 0.78), alpha=1.0):
    from matplotlib.colors import LightSource
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    ls = LightSource(azdeg=315, altdeg=45)
    
    normals = np.cross(
        faces_xyz[:, 1] - faces_xyz[:, 0],
        faces_xyz[:, 2] - faces_xyz[:, 0],
    )
    norm_len = np.linalg.norm(normals, axis=1, keepdims=True)
    norm_len[norm_len == 0] = 1.0
    normals = normals / norm_len

    light_dir = np.array(ls.direction)
    intensity = np.clip(normals @ light_dir, 0.2, 1.0)

    base = np.array(base_color)
    face_colors = base[None, :] * intensity[:, None]
    face_colors = np.clip(face_colors, 0, 1)

    rgba_face_colors = np.hstack([face_colors, np.full((len(face_colors), 1), alpha)])

    coll = Poly3DCollection(faces_xyz)
    coll.set_facecolor(rgba_face_colors)
    coll.set_edgecolor((0, 0, 0, 0.03))  # extremely faint edges
    return coll


def render_scene_matplotlib(scene, highlighted_nodes=None, angle="iso_right"):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    fig = plt.figure(figsize=(8, 6), dpi=150)
    ax = fig.add_subplot(111, projection='3d')
    ax.set_facecolor('#0f0f1a')
    fig.patch.set_facecolor('#0f0f1a')
    ax.set_axis_off()
    ax.margins(0)
    fig.subplots_adjust(left=0, right=1, bottom=0, top=1)

    highlighted_set = set(highlighted_nodes) if highlighted_nodes else set()
    all_nodes = list(scene.graph.nodes_geometry)
    dimmed_polys = []

    # Render structural context elements with low opacity
    for node_name in all_nodes:
        if node_name in highlighted_set:
            continue
        try:
            verts, faces = get_node_world_vertices(scene, node_name)
            # Decimate/subsample faces to optimize rendering memory and CPU speed
            if len(faces) > 150:
                idx = np.random.RandomState(42).choice(len(faces), 150, replace=False)
                faces = faces[idx]
            polys = verts[faces]
            dimmed_polys.append(polys)
        except Exception:
            pass

    if dimmed_polys:
        dimmed_polys_arr = np.concatenate(dimmed_polys, axis=0)
        pc = make_shaded_collection(dimmed_polys_arr, base_color=(0.7, 0.73, 0.8), alpha=0.15)
        ax.add_collection3d(pc)

    # Render highlighted nodes in high intensity magenta
    highlighted_polys = []
    for node_name in highlighted_set:
        if node_name not in scene.graph.nodes_geometry:
            continue
        try:
            verts, faces = get_node_world_vertices(scene, node_name)
            polys = verts[faces]
            highlighted_polys.append(polys)
        except Exception:
            pass

    if highlighted_polys:
        highlighted_polys_arr = np.concatenate(highlighted_polys, axis=0)
        pc = Poly3DCollection(highlighted_polys_arr, alpha=0.9)
        pc.set_facecolor((1.0, 0.0, 0.7)) # vivid hot magenta
        pc.set_edgecolor((1.0, 0.5, 0.9, 0.3))
        pc.set_linewidth(0.4)
        ax.add_collection3d(pc)

    # Set angles
    angles = {
        "front": (20, 0),
        "iso_right": (25, 45),
        "iso_left": (25, -45),
        "top": (85, 0),
        "back": (20, 180),
    }
    elev, azim = angles.get(angle, (25, 45))
    ax.view_init(elev=elev, azim=azim)

    # Set aspect ratio and bounds/projection box
    ax.set_xlim(GLOBAL_MIN[0], GLOBAL_MAX[0])
    ax.set_ylim(GLOBAL_MIN[1], GLOBAL_MAX[1])
    ax.set_zlim(GLOBAL_MIN[2], GLOBAL_MAX[2])
    extents = GLOBAL_MAX - GLOBAL_MIN
    ax.set_box_aspect(tuple(extents))

    # Convert plot figures to PIL Image bytes buffer
    buf = io.BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight', facecolor=fig.get_facecolor(), pad_inches=0, dpi=150)
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf)


def image_to_base64(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def query_vlm(prompt, image_b64):
    payload = {
        "model": VLM_MODEL,
        "prompt": prompt,
        "stream": False,
        "images": [image_b64],
        "options": {
            "temperature": 0.1,
            "num_predict": 250
        }
    }
    try:
        resp = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json().get("response", "")
    except Exception as e:
        return f"ERROR communicating with local VLM: {e}"


def parse_vlm_confirmation(text):
    text_lower = text.lower().strip()
    yes_indicators = ["yes", "correct", "matches", "confirm", "true", "looking appropriate"]
    no_indicators = ["no", "incorrect", "does not", "false", "mismatch", "wrong part"]
    
    yes_score = sum(1 for y in yes_indicators if y in text_lower)
    no_score = sum(1 for n in no_indicators if n in text_lower)
    
    if yes_score > no_score:
        return True, min(0.6 + yes_score * 0.1, 0.98)
    else:
        return False, min(0.5 + no_score * 0.1, 0.95)


def main():
    print("Stage 6 -- Agentic Vision Validation Loop")
    print(f"Connecting to Ollama model '{VLM_MODEL}' at {OLLAMA_URL}...")
    
    try:
        # Check connection
        requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
    except Exception as e:
        print(f"[ERROR] Could not connect to Ollama: {e}. Please ensure it is running.")
        return

    # Load resources
    scene = trimesh.load(GLB_PATH)
    assignments = json.load(open(MAPPING_PATH))
    steps = json.load(open(STEPS_PATH))
    step_dict = {s["step_id"]: s for s in steps}
    
    # Representative subset of steps to verify via VLM to demonstrate verification loop
    steps_to_verify = ["10-10", "20-10", "20-40", "30-30", "40-10", "40-20"]
    
    # Initialize log
    if os.path.exists(LOG_PATH):
        os.remove(LOG_PATH)
        
    print(f"Loaded GLB scene with {len(scene.geometry)} nodes.")
    print(f"Starting verification on {len(steps_to_verify)} target steps...")
    
    for sid in steps_to_verify:
        if sid not in assignments or not assignments[sid]:
            print(f"  Skipping step {sid} - no assigned nodes.")
            continue
            
        step_title = step_dict[sid]["title"]
        step_instruction = step_dict[sid]["instruction"]
        assigned_nodes = assignments[sid]
        
        print(f"\nVerifying Step {sid}: \"{step_title}\"")
        print(f"  Assigned nodes: {assigned_nodes}")
        
        # Render front view
        try:
            print("  Rendering view...")
            img = render_scene_matplotlib(scene, highlighted_nodes=assigned_nodes, angle="iso_right")
            img_path = os.path.join(OUTPUT_DIR, f"verify_step_{sid}.png")
            img.save(img_path)
            print(f"  Saved render to: {img_path}")
            
            img_b64 = image_to_base64(img)
            
            prompt = (
                f"We are disassembling a mechanical industrial gearbox. "
                f"For the task: \"{step_title}\" ({step_instruction}), "
                f"the highlighted magenta/pink parts in the gearbox visual are selected. "
                f"Analyze if the highlighted components correspond correctly to this specific sub-step. "
                f"Respond with YES or NO followed by a brief physical confirmation reason."
            )
            
            t0 = time.time()
            vlm_response = query_vlm(prompt, img_b64)
            elapsed = time.time() - t0
            
            confirmed, confidence = parse_vlm_confirmation(vlm_response)
            
            print(f"  VLM Response: {vlm_response}")
            print(f"  Validation Result: {'CONFIRMED' if confirmed else 'REJECTED'} (Confidence: {confidence:.2f}, Time: {elapsed:.1f}s)")
            
            log_entry({
                "step_id": sid,
                "step_title": step_title,
                "assigned_nodes": assigned_nodes,
                "vlm_response": vlm_response,
                "confirmed": confirmed,
                "confidence": confidence,
                "elapsed_seconds": round(elapsed, 2)
            })
            
        except Exception as e:
            print(f"  [ERROR] Failed rendering or VLM validation for step {sid}: {e}")

    print("\nStage 6 verification completed. Logs and screenshot renders saved to pipeline_output/.")

if __name__ == "__main__":
    main()
