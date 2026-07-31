import json
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.common_paths import OUTPUT_ROOT

FILTERED_PATH = OUTPUT_ROOT / "filtered_nodes.json"
STEPS_PATH = OUTPUT_ROOT / "resolved_steps.json"
OUT_MAPPING_PATH = OUTPUT_ROOT / "step_assignments_stage5.json"


def euclidean_distance(pt1, pt2):
    return np.linalg.norm(np.array(pt1) - np.array(pt2))


def main():
    nodes = json.load(open(FILTERED_PATH))
    steps = json.load(open(STEPS_PATH))
    
    # Collect all active nodes
    active = {}
    for name, info in nodes.items():
        if not info["excluded"]:
            active[name] = info
            
    print(f"Total active nodes: {len(active)}")
    
    # Map step_id to assigned nodes
    assignment = {step["step_id"]: [] for step in steps}
    
    # We will build mapping rules for each step
    for name, info in list(active.items()):
        pn = info["top_lexical_pn"]
        x, y, z = info["centroid"]
        vol = info["bbox_volume"]
        
        assigned_step = None
        
        # 1. Specific unassigned/noise node overrides
        if name in ["Object.086", "Object.900"]:
            # Bevel Gears GBX-GB-105
            assigned_step = "20-50"
        elif name == "Object.157":
            # B-side Bearing Cap GBX-BC-108
            assigned_step = "40-30"
        elif name == "Object.378":
            # Distance Sleeve GBX-DS-125
            assigned_step = "30-70"
        elif name in ["Object.676", "body_x717"]:
            # Flat Washer GBX-FW-112 -> Step 30-10 or 20-60. Let's do 30-10
            assigned_step = "30-10"
        elif name in ["body_x354", "solid_61"]:
            # Small pins/spacers -> Step 30-70
            assigned_step = "30-70"
        elif name == "mesh_efd324":
            # Sight glass -> Step 10-10
            assigned_step = "10-10"
        elif name == "dichthalter.033 (2)":
            # Seal Retainer B-side -> Step 40-30
            assigned_step = "40-30"
        elif name == "seal_plate.010_v3":
            # Seal Retainer A-side -> Step 20-40
            assigned_step = "20-40"
            
        # 2. General rules
        # GBX-BRP-120: Breather / Filler Plug
        elif pn == "GBX-BRP-120" or "breather" in name.lower():
            assigned_step = "10-10"
            
        # GBX-BC-108: Bearing Retainer Cap
        elif pn == "GBX-BC-108" or "brg_cap" in name.lower() or "cap_brg" in name.lower() or "abschlussdeckel" in name.lower() or "endcap" in name.lower():
            if x > 160.0:
                if z > 0:
                    assigned_step = "20-10" # front cap (Z > 0)
                else:
                    assigned_step = "20-20"  # rear cap (Z < 0)
            else:
                assigned_step = "40-30"  # B-side caps
                
        # GBX-OS-124 / GBX-OS-124-B: Radial Oil Seal
        elif pn in ["GBX-OS-124", "GBX-OS-124-B"] or "oilseal" in name.lower() or "simmerring" in name.lower() or "wellendichtring" in name.lower() or name == "Object.662":
            if x > 160.0:
                assigned_step = "20-40"  # drive-end front oil seal
            else:
                assigned_step = "40-30"  # B-side oil seals
                
        # GBX-DP-130: Locating Dowel Pin
        elif pn == "GBX-DP-130" or "pin_loc" in name.lower() or "dowel" in name.lower():
            assigned_step = "10-30"
            
        # GBX-SCS-121: Socket Cap Screw
        elif (pn == "GBX-SCS-121" and vol > 0.1) or "zylschraube" in name.lower() or "capscrw" in name.lower() or ("skt_schr" in name.lower() and vol > 0.1) or name in ["Object.589", "Object.417", "mesh_7784d5", "mesh_b4502f", "solid_33"]:
            assigned_step = "30-20"  # case split line screws
            
        # GBX-HXB-122: Cover Hex Bolt (DIN 933)
        elif (pn == "GBX-HXB-122" and vol < 0.1) or "sechskant" in name.lower() or "hexbolt" in name.lower() or "bolt_m6" in name.lower() or ("skt_schr" in name.lower() and vol < 0.1) or name == "body_x75":
            if x > 160.0:
                if z < 0:
                    assigned_step = "20-30" # mid-ring bolts
                else:
                    assigned_step = "10-20" # front cover flange bolts
            else:
                assigned_step = "30-10"  # rear cover bolts
                
        # GBX-ISH-116: Input Shaft
        elif pn == "GBX-ISH-116" or "in_shaft" in name.lower():
            assigned_step = "20-50"
            
        # GBX-GP-104: Input Pinion
        elif pn == "GBX-GP-104" or "ritzel" in name.lower() or name == "solid_52":
            assigned_step = "20-50"
            
        # GBX-GB-105: Bevel Gear
        elif pn == "GBX-GB-105" or "hel_gear" in name.lower():
            assigned_step = "20-50"
            
        # GBX-CL-111: Internal Circlip
        elif pn == "GBX-CL-111" or "circlip_i" in name.lower():
            assigned_step = "20-60"
            
        # GBX-TW-109: Thrust Washer
        elif pn == "GBX-TW-109" or "thr_washer" in name.lower() or "washer_fl" in name.lower():
            assigned_step = "20-60"
            
        # GBX-HSG-100: Housing Half
        elif pn == "GBX-HSG-100" or "casing_ot" in name.lower() or "gehaeuse" in name.lower():
            assigned_step = "30-30"
            
        # GBX-SH-114: Layshaft / Countershaft
        elif pn == "GBX-SH-114" or "layshft" in name.lower() or "countershaft" in name.lower():
            assigned_step = "30-40"
            
        # GBX-GC-107: Cluster Gear
        elif pn == "GBX-GC-107" or "radblock" in name.lower() or "cluster" in name.lower():
            assigned_step = "30-50"
            
        # GBX-GH-103: Helical Reduction Gear
        elif pn == "GBX-GH-103" or "helix_gr" in name.lower() or "schraegverz" in name.lower():
            assigned_step = "30-50"
            
        # GBX-GI-106: Idler Gear
        elif pn == "GBX-GI-106" or "idler" in name.lower():
            assigned_step = "30-50"
            
        # GBX-GR-101: Internal Ring Gear
        elif pn == "GBX-GR-101" or "zahnkranz" in name.lower() or "gr_ring" in name.lower():
            assigned_step = "30-50"
            
        # GBX-NB-129: Needle Roller Bearing
        elif pn == "GBX-NB-129" or "nadellager" in name.lower() or "needle_brg" in name.lower():
            assigned_step = "30-60"
            
        # GBX-SR-110: External Snap Ring
        elif pn == "GBX-SR-110" or "snapring" in name.lower() or "sicherungsring" in name.lower() or "circlip" in name.lower():
            assigned_step = "30-70"
            
        # GBX-SHM-118: Adjusting Shim / Spacer
        elif pn == "GBX-SHM-118" or "scheibe" in name.lower() or name == "body_x348":
            assigned_step = "30-70"
            
        # GBX-DS-125: Distance Sleeve
        elif pn == "GBX-DS-125" or "sleeve" in name.lower():
             # We should make sure distance sleeves go to 30-70 (some were lexically mapped to NB bearings)
             assigned_step = "30-70"
            
        # GBX-CF-117: Coupling Flange
        elif pn == "GBX-CF-117" or "cplg_flg" in name.lower() or "flange" in name.lower():
            assigned_step = "40-10"
            
        # GBX-MF-126: Mounting Flange
        elif pn == "GBX-MF-126" or "montageflansch" in name.lower():
            assigned_step = "40-30"
                
        # GBX-KEY-113: Parallel Shaft Key
        elif pn == "GBX-KEY-113" or "key_par" in name.lower():
            assigned_step = "40-10"
            
        # GBX-OSH-115: Output Shaft
        elif pn == "GBX-OSH-115" or "abtriebswelle" in name.lower():
            assigned_step = "40-20"
            
        # GBX-GLG-102: Output Spur Gear
        elif pn == "GBX-GLG-102" or "spur_out" in name.lower() or "zahnrad_gr" in name.lower():
            assigned_step = "40-20"
            
        # GBX-BRG-123: Cylindrical Roller Bearing
        elif pn == "GBX-BRG-123" or "roller_brg" in name.lower() or "brg_cyl" in name.lower():
            assigned_step = "40-30"
            
        if assigned_step:
            assignment[assigned_step].append(name)
            active.pop(name)
            
    print(f"\nRemaining unassigned active nodes after rules: {len(active)}")
    for name, info in active.items():
        print(f"  Name: {name:<30} Centroid: {[round(c, 2) for c in info['centroid']]} Vol: {info['bbox_volume']:.4f} TopPN: {info['top_lexical_pn']}")
        
    with open(OUT_MAPPING_PATH, "w") as f:
        json.dump(assignment, f, indent=2)

if __name__ == "__main__":
    main()
