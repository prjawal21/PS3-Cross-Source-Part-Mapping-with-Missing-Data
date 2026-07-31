import os
import re
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rapidfuzz import fuzz

from pipeline.common_paths import OUTPUT_ROOT

PARTS_PATH = OUTPUT_ROOT / "canonical_parts.json"
PROFILE_PATH = OUTPUT_ROOT / "geometry_profile.json"
OUT_DIR = OUTPUT_ROOT
OUT_PATH = OUT_DIR / "lexical_scores.json"

TRANSLATION_DICT = {
    # German terms
    "sechskant": "hex bolt",
    "zahnrad": "gear",
    "zahnkranz": "ring gear",
    "welle": "shaft",
    "abtriebswelle": "output shaft",
    "antriebswelle": "input shaft",
    "lager": "bearing",
    "dichtung": "seal",
    "scheibe": "washer",
    "stift": "pin",
    "keil": "key",
    "deckel": "cap",
    "kappe": "cap",
    "schraube": "screw",
    "zw": "idler",
    
    "abschlussdeckel": "end cap",
    "gehaeuse": "housing",
    "lagergehaeuse": "bearing housing boss",
    "montageflansch": "mounting flange",
    "nadellager": "needle bearing",
    "ritzel": "pinion",
    "schraegverz": "helical gear",
    "simmerring": "oil seal",
    "wellendichtring": "oil seal",
    "skt": "socket",
    "schr": "screw",
    "zylschraube": "socket screw",
    "skt_schr": "socket screw",
    "sicherungsring": "snap ring",
    "dichthalter": "seal retainer plate",
    "abtrieb": "output",
    "antrieb": "input",
    "flansch": "flange",
    
    # English terms
    "brg": "bearing",
    "cyl": "cylindrical",
    "scrw": "screw",
    "capscrw": "cap screw",
    "casing": "housing",
    "ot": "upper",
    "blk": "block",
    "cplg": "coupling",
    "flg": "flange",
    "layshft": "layshaft",
    "loc": "locating",
    "par": "parallel",
    "shm": "shim",
    "thr": "thrust",
    "hexbolt": "hex bolt",
    "snapring": "snap ring",
    "circlip": "circlip",
    "endcap": "end cap",
    "oilseal": "oil seal",
    "layshaft": "layshaft",
    "countershaft": "countershaft",
    "flatwasher": "flat washer",
    "needle": "needle",
    "hel": "helical",
    "helix": "helical",
    "radblock": "cluster gear",
    "gr": "gear"
}

def translate_name(name):
    cruft_patterns = [
        r"_v\d+", r"_rev\d+", r"_final.*", r"_FINAL.*", r"_copy", 
        r"\.\d+$", r"\(\d+\)", r"_old.*", r"_neu", r"_DONOTUSE", r"_imp$", r"_x$"
    ]
    cleaned = name
    for pat in cruft_patterns:
        cleaned = re.sub(pat, "", cleaned)
    
    raw_tokens = re.split(r"[_.\s]+", cleaned)
    translated_tokens = []
    
    for tok in raw_tokens:
        stok = tok.strip()
        if not stok:
            continue
        if re.match(r"^m\d+$", stok, re.IGNORECASE):
            tok_clean = stok.lower()
        else:
            tok_clean = re.sub(r"\d+", "", stok).lower().strip()
            
        if not tok_clean:
            continue
            
        if tok_clean in TRANSLATION_DICT:
            translated_tokens.append(TRANSLATION_DICT[tok_clean])
        else:
            translated_tokens.append(tok_clean)
            
    translated_str = " ".join(translated_tokens)
    translated_str = re.sub(r"\s+", " ", translated_str).strip()
    return translated_str


def is_pure_noise(name):
    noise_patterns = [
        r"^Object\.\d+$",
        r"^mesh_[a-f0-9]+$",
        r"^solid_\d+$",
        r"^body_x\d+$"
    ]
    return any(re.match(pat, name, re.IGNORECASE) for pat in noise_patterns)


def main():
    parts = json.load(open(PARTS_PATH))
    profile = json.load(open(PROFILE_PATH))
    
    scores_out = []
    
    for node in profile:
        name = node["node_name"]
        pure_noise = is_pure_noise(name)
        
        candidates = []
        cleaned_str = ""
        
        if not pure_noise:
            cleaned_str = translate_name(name)
            for oem_pn, part_data in parts.items():
                desc = part_data["description"]
                score = float(fuzz.token_set_ratio(cleaned_str.lower(), desc.lower()))
                candidates.append({
                    "oem_pn": oem_pn,
                    "description": desc,
                    "score": score
                })
            # Sort candidates by score descending
            candidates = sorted(candidates, key=lambda c: c["score"], reverse=True)
            
        scores_out.append({
            "node_name": name,
            "cleaned_name": cleaned_str,
            "is_pure_noise": pure_noise,
            "lexical_candidates": candidates
        })
        
    with open(OUT_PATH, "w") as f:
        json.dump(scores_out, f, indent=2)
        
    print(f"Stage 2 complete! Wrote lexical matching results for {len(scores_out)} nodes to {OUT_PATH}")

if __name__ == "__main__":
    main()
