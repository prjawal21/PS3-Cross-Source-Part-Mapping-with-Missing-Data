import json
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.common_paths import OUTPUT_ROOT

PARTS_PATH = OUTPUT_ROOT / "canonical_parts.json"
PROFILE_PATH = OUTPUT_ROOT / "geometry_profile.json"
LEXICAL_PATH = OUTPUT_ROOT / "lexical_scores.json"

OUT_DIR = OUTPUT_ROOT
OUT_PATH = OUT_DIR / "filtered_nodes.json"
EXCLUSIONS_PATH = OUT_DIR / "stale_and_duplicate_nodes.json"


def euclidean_distance(pt1, pt2):
    return np.linalg.norm(np.array(pt1) - np.array(pt2))


def main():
    parts = json.load(open(PARTS_PATH))
    profiles = {p["node_name"]: p for p in json.load(open(PROFILE_PATH))}
    lexical = {l["node_name"]: l for l in json.load(open(LEXICAL_PATH))}

    results = {}
    exclusions = []
    
    VOL_TOLERANCE = 0.05      # 5%
    PROPAGATION_DIST_TOLERANCE = 1.5   # world units for noise propagation
    DUPLICATE_DIST_TOLERANCE = 0.05     # world units to ensure only overlapping duplicates are excluded
    
    # 1. Parse and initialize nodes
    for name, node_profile in profiles.items():
        lex_data = lexical.get(name, {})
        is_stale = "_old" in name.lower() or "donotuse" in name.lower()
        
        top_pn = None
        top_score = 0.0
        top_desc = None
        
        lex_candidates = lex_data.get("lexical_candidates", [])
        if lex_candidates:
            top_pn = lex_candidates[0]["oem_pn"]
            top_score = lex_candidates[0]["score"]
            top_desc = lex_candidates[0]["description"]

        results[name] = {
            "node_name": name,
            "geometry_name": node_profile["geometry_name"],
            "centroid": node_profile["centroid"],
            "bbox_volume": node_profile["bbox_volume"],
            "bbox_extents": node_profile["bbox_extents"],
            "flagged_stale": is_stale,
            "top_lexical_pn": top_pn,
            "top_lexical_score": top_score,
            "top_lexical_desc": top_desc,
            "lexical_candidates": lex_candidates,
            "is_pure_noise": lex_data.get("is_pure_noise", False),
            "excluded": False,
            "exclude_reason": None,
            "requires_manual_review": False
        }

    # 2. Propagate lexical signals from non-noise to noise spatial duplicates
    for name, info in results.items():
        if not info["is_pure_noise"]:
            continue
        
        # Search for a non-noise spatial duplicate
        for other_name, other_info in results.items():
            if other_name == name or other_info["is_pure_noise"]:
                continue
                
            v1, v2 = info["bbox_volume"], other_info["bbox_volume"]
            c1, c2 = info["centroid"], other_info["centroid"]
            
            # Check volume & distance
            max_vol = max(v1, v2)
            vol_diff = abs(v1 - v2) / max_vol if max_vol > 0 else 0
            dist = euclidean_distance(c1, c2)
            
            if vol_diff <= VOL_TOLERANCE and dist <= PROPAGATION_DIST_TOLERANCE:
                # Copy lexical match metadata
                info["top_lexical_pn"] = other_info["top_lexical_pn"]
                info["top_lexical_score"] = other_info["top_lexical_score"]
                info["top_lexical_desc"] = other_info["top_lexical_desc"]
                info["lexical_candidates"] = other_info["lexical_candidates"]
                print(f"Propagated lexical PN {info['top_lexical_pn']} from {other_name} to noise node {name} via spatial match")
                break

    # 3. Detect duplicate pairs sharing same top lexical PN
    pn_groups = {}
    for name, info in results.items():
        if not info["top_lexical_pn"]:
            continue
        pn_groups.setdefault(info["top_lexical_pn"], []).append(name)

    for pn, group in pn_groups.items():
        if len(group) < 2:
            continue
        
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                n1 = group[i]
                n2 = group[j]
                
                info1 = results[n1]
                info2 = results[n2]
                
                if info1["excluded"] or info2["excluded"]:
                    continue
                    
                v1, v2 = info1["bbox_volume"], info2["bbox_volume"]
                c1, c2 = info1["centroid"], info2["centroid"]
                
                max_vol = max(v1, v2)
                vol_diff = abs(v1 - v2) / max_vol if max_vol > 0 else 0
                dist = euclidean_distance(c1, c2)
                
                if vol_diff <= VOL_TOLERANCE and dist <= DUPLICATE_DIST_TOLERANCE:
                    # Keep the one without stale flag
                    if info1["flagged_stale"] and not info2["flagged_stale"]:
                        keep_name, exclude_name = n2, n1
                    elif info2["flagged_stale"] and not info1["flagged_stale"]:
                        keep_name, exclude_name = n1, n2
                    else:
                        keep_name, exclude_name = n1, n2
                    
                    results[exclude_name]["excluded"] = True
                    results[exclude_name]["exclude_reason"] = f"Near-duplicate of {keep_name} (vol diff={vol_diff:.2%}, dist={dist:.2f})"
                    
                    exclusions.append({
                        "excluded_node": exclude_name,
                        "canonical_node": keep_name,
                        "top_pn": pn,
                        "volume_difference_pct": vol_diff * 100,
                        "distance": dist,
                        "reason": results[exclude_name]["exclude_reason"]
                    })

    # 4. Exclude any remaining stale nodes that weren't caught in duplicate checks
    # BUT only if they are overlapping duplicates (dist < 0.05) of a non-stale active node!
    # Otherwise, even if flagged stale by name, this mesh is the only model geometry at that location.
    for name, info in results.items():
        if info["flagged_stale"] and not info["excluded"]:
            pn = info["top_lexical_pn"]
            c1 = info["centroid"]
            v1 = info["bbox_volume"]
            
            has_replacement = False
            replacement_node = None
            rep_vol_diff = 0
            rep_dist = 0
            
            for other_name, other_info in results.items():
                if other_name == name or other_info["excluded"] or other_info["flagged_stale"]:
                    continue
                # Check top_pn match (or simply spatial overlap)
                if other_info["top_lexical_pn"] == pn:
                    c2 = other_info["centroid"]
                    v2 = other_info["bbox_volume"]
                    max_vol = max(v1, v2)
                    vol_diff = abs(v1 - v2) / max_vol if max_vol > 0 else 0
                    dist = euclidean_distance(c1, c2)
                    if vol_diff <= VOL_TOLERANCE and dist <= 0.05:
                        has_replacement = True
                        replacement_node = other_name
                        rep_vol_diff = vol_diff
                        rep_dist = dist
                        break
            
            if has_replacement:
                info["excluded"] = True
                info["exclude_reason"] = f"Stale draft geometry replaced by duplicate {replacement_node} (flagged_stale=True)"
                exclusions.append({
                    "excluded_node": name,
                    "canonical_node": replacement_node,
                    "top_pn": pn,
                    "volume_difference_pct": rep_vol_diff * 100,
                    "distance": rep_dist,
                    "reason": info["exclude_reason"]
                })

    # 5. Flag obsolete references for review
    for name, info in results.items():
        if info["excluded"]:
            continue
        pn = info["top_lexical_pn"]
        if pn and pn in parts:
            status = parts[pn]["status"]
            if status in ["obsolete", "superseded"]:
                has_current_alt = False
                for cand in info["lexical_candidates"]:
                    cand_pn = cand["oem_pn"]
                    if cand_pn in parts and parts[cand_pn]["status"] == "current":
                        has_current_alt = True
                        break
                if not has_current_alt:
                    info["requires_manual_review"] = True

    # Save
    with open(OUT_PATH, "w") as f:
        json.dump(results, f, indent=2)

    with open(EXCLUSIONS_PATH, "w") as f:
        json.dump(exclusions, f, indent=2)

    print(f"\nStage 3 complete!")
    print(f"  Excluded {len(exclusions)} nodes. Saved log to {EXCLUSIONS_PATH}")
    for item in exclusions:
        print(f"    - Excluded: {item['excluded_node']} | Kept: {item['canonical_node']} | Reason: {item['reason']}")


if __name__ == "__main__":
    main()
