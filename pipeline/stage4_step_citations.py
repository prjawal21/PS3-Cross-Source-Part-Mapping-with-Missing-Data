import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.common_paths import DATA_ROOT, OUTPUT_ROOT

STEPS_PATH = DATA_ROOT / "docs" / "service_steps.json"
PARTS_PATH = OUTPUT_ROOT / "canonical_parts.json"

OUT_DIR = OUTPUT_ROOT
OUT_PATH = OUT_DIR / "resolved_steps.json"


def main():
    steps_data = json.load(open(STEPS_PATH))
    steps = steps_data.get("steps", [])
    parts = json.load(open(PARTS_PATH))
    
    pn_regex = re.compile(r"GBX-[A-Z]{2,5}-\d{3}[A-Z-]*")
    
    resolved_steps = []
    
    for step in steps:
        # Instruction and title fields
        text = (step.get("title", "") + " " + step.get("instruction", ""))
        
        # Find all mentions
        mentions = pn_regex.findall(text)
        
        # De-duplicate mentions in the same step
        unique_mentions = sorted(list(set(mentions)))
        
        cited_parts = []
        for raw_pn in unique_mentions:
            # Resolve against canonical parts
            resolved_pn = raw_pn
            
            # Check if this exact PN is in canonical parts
            if raw_pn in parts:
                part_info = parts[raw_pn]
                # If superseded, resolve to the current active part
                if part_info.get("status") == "superseded" and part_info.get("superseded_by"):
                    resolved_pn = part_info["superseded_by"]
                    print(f"Step {step['step_id']}: Resolved superseded PN {raw_pn} -> {resolved_pn}")
                cited_parts.append({
                    "raw_pn": raw_pn,
                    "resolved_pn": resolved_pn
                })
            else:
                # Part number might not be in catalogue but try anyway
                cited_parts.append({
                    "raw_pn": raw_pn,
                    "resolved_pn": raw_pn
                })
                print(f"[WARN] Step {step['step_id']}: Cited PN {raw_pn} not found in canonical parts database")

        step_copy = dict(step)
        step_copy["cited_parts"] = cited_parts
        resolved_steps.append(step_copy)

    with open(OUT_PATH, "w") as f:
        json.dump(resolved_steps, f, indent=2)
        
    print(f"Stage 4 complete! Wrote resolved steps with citations to {OUT_PATH}")

if __name__ == "__main__":
    main()
