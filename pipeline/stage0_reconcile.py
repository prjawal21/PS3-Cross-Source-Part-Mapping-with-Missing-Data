import re
import csv
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pdfplumber

from pipeline.common_paths import DATA_ROOT, OUTPUT_ROOT

# Paths
DOCS_DIR = DATA_ROOT / "docs"
CATALOGUE_PATH = DOCS_DIR / "IPC-GBX-450E_parts_catalogue.pdf"
XREF_PATH = DOCS_DIR / "parts_xref.csv"
BULLETIN_PATH = DOCS_DIR / "service_bulletin_SB-2019-04.md"
WORK_ORDER_PATH = DOCS_DIR / "work_order_WO-7741.txt"
INSPECTION_PATH = DOCS_DIR / "inspection_log.csv"

OUT_DIR = OUTPUT_ROOT
os.makedirs(OUT_DIR, exist_ok=True)

CANONICAL_PARTS_OUT = OUT_DIR / "canonical_parts.json"
CORRECTIONS_APPLIED_OUT = OUT_DIR / "corrections_applied.json"
CLEANED_INSPECTION_OUT = OUT_DIR / "cleaned_inspection_log.json"
CLEANED_WORK_ORDER_OUT = OUT_DIR / "cleaned_work_order.json"


def clean_number(val):
    if not val:
        return 0
    try:
        return int(val)
    except ValueError:
        return 0


def normalize_date(date_str):
    # Format 1: YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return date_str
    
    # Format 2: DD/MM/YYYY
    m1 = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", date_str)
    if m1:
        d, m, y = m1.groups()
        return f"{y}-{int(m):02d}-{int(d):02d}"
    
    # Format 3: DD.MM.YYYY
    m2 = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", date_str)
    if m2:
        d, m, y = m2.groups()
        return f"{y}-{int(m):02d}-{int(d):02d}"
        
    return None


def parse_bulletin_tables():
    """Parses corrections from the service bulletin markdown file."""
    with open(BULLETIN_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # Split into sections
    sections = re.split(r"###\s+", content)
    corrections_steps = []
    corrections_ipc = []
    torque_schedule = {}

    for sec in sections:
        lines = [line.strip() for line in sec.split("\n") if line.strip()]
        if not lines:
            continue
        title = lines[0]
        
        # Parse table lines in this section
        table_lines = [l for l in lines if l.startswith("|")]
        if len(table_lines) < 3:
            continue
        
        headers = [c.strip() for c in table_lines[0].split("|")[1:-1]]
        data_rows = table_lines[2:]  # skip header and divider

        if "Was" in headers and "Is" in headers:
            if "Ref" in headers:
                # Step corrections
                for row in data_rows:
                    cells = [c.strip() for c in row.split("|")[1:-1]]
                    if len(cells) >= 3:
                        corrections_steps.append({
                            "ref": cells[0],
                            "was": cells[1],
                            "is": cells[2]
                        })
            elif "PN" in headers:
                # IPC corrections
                for row in data_rows:
                    cells = [c.strip() for c in row.split("|")[1:-1]]
                    if len(cells) >= 4:
                        corrections_ipc.append({
                            "pn": cells[0],
                            "field": cells[1],
                            "was": cells[2],
                            "is": cells[3]
                        })
        elif "Fastener" in headers and "Torque" in headers:
            for row in data_rows:
                cells = [c.strip() for c in row.split("|")[1:-1]]
                if len(cells) >= 2:
                    torque_schedule[cells[0]] = cells[1]

    return corrections_steps, corrections_ipc, torque_schedule


def main():
    print("Executing Stage 0: Document Reconciliation...")

    # 1. Parse Parts Catalogue
    raw_catalogue = {}
    with pdfplumber.open(CATALOGUE_PATH) as pdf:
        # Page 4: summary table
        page_4 = pdf.pages[3]
        lines = page_4.extract_text().split("\n")
        for line in lines:
            line = line.strip()
            # Regex match summary lines
            m = re.match(r"^([^\s]*)\s+(GBX-[A-Z0-9-]+)\s+(.*?)\s+(A\d+-[A-Za-z0-9_-]+)\s+(\d+)\s*(.*)$", line)
            if m:
                item_num, part_no, desc, sub_asm, qty, material = m.groups()
                raw_catalogue[part_no] = {
                    "oem_pn": part_no,
                    "description": desc,
                    "sub_assembly": sub_asm,
                    "quantity": int(qty),
                    "material": material.strip() if material else None,
                    "status": "current", # Default value
                    "superseded_by": None
                }

    # Extract envelopes from detailed pages 5-20 (indices 4 to 19)
    with pdfplumber.open(CATALOGUE_PATH) as pdf:
        current_part = None
        for idx in range(4, 20):
            page_text = pdf.pages[idx].extract_text() or ""
            for line in page_text.split("\n"):
                line = line.strip()
                m_pn = re.search(r"Part number\s+(GBX-[A-Z0-9-]+)", line)
                if m_pn:
                    current_part = m_pn.group(1)
                    if current_part not in raw_catalogue:
                        # Let's ensure it is in the raw catalogue dict
                        raw_catalogue[current_part] = {
                            "oem_pn": current_part,
                            "oem_pn_clean": current_part,
                            "status": "current",
                            "superseded_by": None
                        }
                    # Check for Category on same line
                    m_cat = re.search(r"Category\s+(\w+)", line)
                    if m_cat:
                        raw_catalogue[current_part]["category"] = m_cat.group(1)
                
                if current_part:
                    # Capture other fields if not populated
                    m_qty = re.search(r"Qty\s*/\s*assy\s*(\d+)", line)
                    if m_qty and "quantity" not in raw_catalogue[current_part]:
                        raw_catalogue[current_part]["quantity"] = int(m_qty.group(1))

                    m_sub = re.search(r"Sub-asm\s+(\S+)", line)
                    if m_sub and "sub_assembly" not in raw_catalogue[current_part]:
                        raw_catalogue[current_part]["sub_assembly"] = m_sub.group(1)

                    if "envelope" in line.lower():
                        # Match dims, unit, and star
                        m_env = re.search(r"Envelope\s+([\d.]+)\s*[^\d.\s]\s*([\d.]+)\s*[^\d.\s]\s*([\d.]+)\s+(\w+)(?:\s+(\*))?", line)
                        if m_env:
                            d1, d2, d3, unit, star = m_env.groups()
                            raw_catalogue[current_part].update({
                                "envelope_raw": [float(d1), float(d2), float(d3)],
                                "envelope_unit": unit,
                                "envelope_star": bool(star),
                                "envelope_mm": [float(d1), float(d2), float(d3)]  # Default same
                            })
                            # If unit is cm or starred, we'll fix it in corrections section
                        else:
                            print(f"[WARN] Failed to parse envelope for {current_part}: {line}")
                        
                        m_mat = re.search(r"Material\s*(.*?)\s*Envelope", line)
                        if m_mat and "material" not in raw_catalogue[current_part]:
                            raw_catalogue[current_part]["material"] = m_mat.group(1).strip()

    # 2. Load Cross-reference
    xref_data = {}
    with open(XREF_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            oem_pn = row["oem_pn"]
            status_note = row["status_note"]
            # Exclude obsolete supplier parts if current exists
            is_obsolete = "obsolete" in status_note.lower()
            if oem_pn not in xref_data or not is_obsolete:
                xref_data[oem_pn] = {
                    "supplier_pn": row["supplier_pn"],
                    "din_ref": row["din_ref"] if row["din_ref"] else None,
                    "status_note": status_note
                }

    # Merge cross-reference into raw catalogue
    for oem_pn, data in raw_catalogue.items():
        if oem_pn in xref_data:
            data.update(xref_data[oem_pn])
        else:
            data.update({
                "supplier_pn": None,
                "din_ref": None,
                "status_note": None
            })

    # Create GBX-OS-124-B baseline from GBX-OS-124 since it replaces it
    if "GBX-OS-124-B" not in raw_catalogue and "GBX-OS-124" in raw_catalogue:
        raw_catalogue["GBX-OS-124-B"] = dict(raw_catalogue["GBX-OS-124"])
        raw_catalogue["GBX-OS-124-B"].update({
            "oem_pn": "GBX-OS-124-B",
            "status": "current",
            "material": "FKM"
        })
        if "GBX-OS-124-B" in xref_data:
            raw_catalogue["GBX-OS-124-B"].update(xref_data["GBX-OS-124-B"])

    # 3. Parse and Apply Bulletin Corrections
    corrections_steps, corrections_ipc, torque_schedule = parse_bulletin_tables()
    corrections_log = []

    # Apply quantity/status overrides
    for corr in corrections_ipc:
        pn_pattern = corr["pn"]
        # Pattern could be "GBX-SH-114 / GBX-OSH-115"
        parts = [p.strip() for p in pn_pattern.split("/") if p.strip()]
        for target_pn in parts:
            if target_pn in raw_catalogue:
                field = corr["field"]
                was_val = corr["was"]
                is_val = corr["is"]
                
                # Check fields and apply overrides
                if field == "qty/assy":
                    old_qty = raw_catalogue[target_pn]["quantity"]
                    # Extract number from "18 (2 added at...)"
                    new_qty = int(re.search(r"\d+", is_val).group())
                    raw_catalogue[target_pn]["quantity"] = new_qty
                    corrections_log.append({
                        "oem_pn": target_pn,
                        "field": "quantity",
                        "old_value": old_qty,
                        "new_value": new_qty,
                        "reason": f"SB-2019-04 override: {is_val}"
                    })
                elif field == "status":
                    old_status = raw_catalogue[target_pn]["status"]
                    # parse status
                    new_status = "superseded" if "superseded" in is_val.lower() else is_val
                    raw_catalogue[target_pn]["status"] = new_status
                    
                    # check if superseded PN is mentioned
                    m_sup = re.search(r"GBX-[A-Z0-9-]+", is_val)
                    if m_sup:
                        raw_raw_sup = m_sup.group()
                        raw_catalogue[target_pn]["superseded_by"] = raw_raw_sup
                    
                    corrections_log.append({
                        "oem_pn": target_pn,
                        "field": "status",
                        "old_value": old_status,
                        "new_value": new_status,
                        "reason": f"SB-2019-04 override: {is_val}"
                    })
                elif field == "envelope":
                    # SB says: printed values are in cm (transcription); multiply by 10 for mm.
                    # We handle the multiplication below as a general rule, but let's log this correction
                    pass

    # Process all parts details to apply unit corrections
    for oem_pn, data in raw_catalogue.items():
        # Handle starred/cm envelopes (including GBX-SH-114 and GBX-OSH-115)
        # Check if envelope_star is True, or if the bulletin explicitly corrected it
        star_flag = data.get("envelope_star", False)
        unit = data.get("envelope_unit", "mm")
        
        # Enforce unit correction if star_flag is true or unit is cm
        if star_flag or unit == "cm" or oem_pn in ["GBX-SH-114", "GBX-OSH-115"]:
            raw_env = data.get("envelope_raw", [0.0, 0.0, 0.0])
            corrected_env = [round(v * 10.0, 4) for v in raw_env]
            data["envelope_mm"] = corrected_env
            data["envelope_unit_corrected"] = True
            
            corrections_log.append({
                "oem_pn": oem_pn,
                "field": "envelope_mm",
                "old_value": raw_env,
                "new_value": corrected_env,
                "reason": f"Unit corrected from cm to mm (multiplied by 10) per bulletin/star flag."
            })
        else:
            data["envelope_unit_corrected"] = False

    # 4. Parse Work Order
    # Fixed-width/regex parsing of WO-7741
    work_order_entries = []
    with open(WORK_ORDER_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    start_table = False
    for line in lines:
        if "PARTS CONSUMED" in line:
            start_table = True
            continue
        if start_table and line.startswith("------"):
            continue
        if start_table and line.strip().startswith("line"):
            continue
        if start_table and not line.strip():
            # Stop or skip empty
            continue
        if start_table and "=" in line:
            # End of table
            start_table = False
            continue
        
        if start_table:
            # Extract line contents:
            # line  supplier_pn            qty   disposition
            #  1    DFT-BA-20x35x7-FKM      1    fitted, drive-end front bore        [20-40]
            # Match line number at start, then spacing, supplier pn, spacing, qty, then disposition + optional steps
            m_wo = re.match(r"^\s*(\d+)\s+(.*?)\s+(\d+)\s+(.*)$", line)
            if m_wo:
                l_num, sup_pn_raw, qty_val, remaining = m_wo.groups()
                
                # Check for step brackets in remaining
                m_step = re.search(r"\[([0-9\s,.-]+)\]", remaining)
                step_ids = []
                if m_step:
                    step_ids = [s.strip() for s in m_step.group(1).split(",")]
                    # remove steps from disposition text
                    disposition = remaining.replace(m_step.group(0), "").strip()
                else:
                    disposition = remaining.strip()
                
                # Clean supplier PN
                sup_pn = sup_pn_raw.replace("(in-house)", "").strip()
                
                struck = "STRUCK" in disposition or "unused" in disposition
                
                work_order_entries.append({
                    "line_number": int(l_num),
                    "supplier_pn_raw": sup_pn_raw.strip(),
                    "supplier_pn": sup_pn,
                    "qty": int(qty_val),
                    "disposition": disposition,
                    "step_ids": step_ids,
                    "struck": struck,
                    "serviced": not struck
                })

    # Save Cleaned Work Order
    with open(CLEANED_WORK_ORDER_OUT, "w") as f:
        json.dump(work_order_entries, f, indent=2)

    # 5. Clean Inspection Log
    inspection_entries = []
    dropped_log = []
    valid_oem_pns = set(raw_catalogue.keys())

    with open(INSPECTION_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            date_raw = row["date"]
            part_no = row["part_no"]
            disposition = row["disposition"]
            
            # Normalize date
            iso_date = normalize_date(date_raw)
            if not iso_date:
                dropped_log.append({
                    "row_index": i,
                    "part_no": part_no,
                    "reason": f"Invalid/unparseable date: {date_raw}"
                })
                continue
            
            # Drop check
            if disposition in ["VOID ROW", "UNKNOWN PN"]:
                dropped_log.append({
                    "row_index": i,
                    "part_no": part_no,
                    "reason": f"Explicitly dropped disposition: {disposition}"
                })
                continue
            
            # Validate matching OEM PN
            # (allow minor variations like GBX-OS-124 vs GBX-OS-124-B)
            # Find exact or prefix/superseded connection
            is_valid_pn = part_no in valid_oem_pns
            if not is_valid_pn:
                dropped_log.append({
                    "row_index": i,
                    "part_no": part_no,
                    "reason": f"Part number not found in OEM catalogue: {part_no}"
                })
                continue
            
            # Keep row
            row_cleaned = dict(row)
            row_cleaned["date"] = iso_date
            inspection_entries.append(row_cleaned)

    print(f"Inspection Clean: read {i+1} rows, kept {len(inspection_entries)}, dropped {len(dropped_log)}")
    with open(CLEANED_INSPECTION_OUT, "w") as f:
        json.dump({
            "cleaned_inspection_records": inspection_entries,
            "dropped_records": dropped_log
        }, f, indent=2)

    # Save corrections applied and canonical parts
    with open(CORRECTIONS_APPLIED_OUT, "w") as f:
        json.dump(corrections_log, f, indent=2)

    # Re-structure each part entry to match the Stage 7 canonical requirements:
    canonical_parts = {}
    for oem_pn, data in raw_catalogue.items():
        canonical_parts[oem_pn] = {
            "oem_pn": oem_pn,
            "description": data.get("description", "Unknown Description"),
            "category": data.get("category", "unspecified"),
            "qty_per_assy": data.get("quantity", 0),
            "qty_source": f"catalogue={data.get('quantity', 0)}" if oem_pn not in [c["oem_pn"] for c in corrections_log if c["field"] == "quantity"] else f"corrected by SB-2019-04 to {data.get('quantity', 0)}",
            "material": data.get("material", "Unknown"),
            "envelope_mm": data.get("envelope_mm", [0.0, 0.0, 0.0]),
            "envelope_raw": data.get("envelope_raw", [0.0, 0.0, 0.0]),
            "envelope_unit_corrected": data.get("envelope_unit_corrected", False),
            "status": data.get("status", "current"),
            "superseded_by": data.get("superseded_by", None),
            "supplier_pn": data.get("supplier_pn", None),
            "din_ref": data.get("din_ref", None),
            "status_note": data.get("status_note", None)
        }

    with open(CANONICAL_PARTS_OUT, "w") as f:
        json.dump(canonical_parts, f, indent=2)

    print(f"Stage 0 complete! Wrote:")
    print(f"  {CANONICAL_PARTS_OUT}")
    print(f"  {CORRECTIONS_APPLIED_OUT}")
    print(f"  {CLEANED_WORK_ORDER_OUT}")
    print(f"  {CLEANED_INSPECTION_OUT}")


if __name__ == "__main__":
    main()
