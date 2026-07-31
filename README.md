# Gearbox Service Mapping Pipeline

This project maps gearbox mesh nodes to service steps and exports a structured GLB hierarchy for repair workflows.

## Project structure

- `main.py` — orchestrates the full pipeline
- `pipeline/` — stage-by-stage processing scripts
- `Stage 0:` Reconcile (stage0_reconcile.py)
Analogy: Doing inventory. It looks at the incoming text data and the raw 3D model to make sure everything is readable and ready to be processed.
- `Stage 1:` Profile (stage1_profile.py)
Analogy: Scanning the manual. It breaks down the written repair instructions to understand exactly what components are being talked about.
- `Stage 2:` Lexical (stage2_lexical.py)
Analogy: Word matching. It checks if the names of the parts in the text exactly match the names of the parts in the 3D files (e.g., matching "gear" to "gear_01").
- `Stage 3:` Mesh Filter (stage3_mesh_filter.py)
Analogy: Filtering out the junk. 3D models often have invisible geometric junk or duplicated structure nodes. This stage cleans up the model and isolates only the real, physical parts we care about.
- `Stage 4:` Step Citations (stage4_step_citations.py)
Analogy: Highlighting the manual. It officially links specific parts mentioned in the repair manual to the steps they belong to.
- `Stage 5:` Propose & Verify (stage5_propose_verify.py)
Analogy: Making the connection. An intelligent matchmaking process where it attempts to say "This specific 3D node belongs to this exact repair step." It relies on physical space and naming rules.
- `Stage 6:` Vision (stage6_vision.py)
Analogy: The QA team. It uses a vision model (an AI that can 'see') to double-check the work. It renders a picture of the part and asks the AI, "Does this look like the part the instruction is talking about?"
- `Stage 7:` Output (stage7_output.py)
Analogy: Writing the final report. It takes all confirmed matches and saves them to our mapping.json file.
- `Stage 8:` Restructure (stage8_restructure.py)
Analogy: Rebuilding the physical puzzle. It uses the mapping.json to physically rebuild the 3D .glb file, ensuring the new file's hierarchy perfectly matches the service steps.
- `mapping.json` — final mesh-to-step assignment mapping
- `gearbox_restructured.glb` — output GLB grouped by service step

## Required data

The pipeline expects the challenge data bundle in a sibling folder named `service-to-3d-challenge-minimal` or in the environment variable `GEARBOX_DATA_ROOT`.

Typical layout:

```text
C:\trash\metadome\service-to-3d-challenge-minimal\
  docs\
  gearbox_service_unit.glb
  pipeline_output\
```

If you want to point the project at a different location, set:

```powershell
$env:GEARBOX_DATA_ROOT = "C:\path\to\service-to-3d-challenge-minimal"
```

## Quick start

From the repo root:

```powershell
py main.py
```

## Dependencies

```powershell
py -m pip install -r requirements.txt
```

## Notes

- The project was designed to run with the Windows Python launcher (`py`) in environments where `python` is not on PATH.
- The output is grouped into repair steps and can be inspected directly in a 3D viewer.
