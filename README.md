# Gearbox Service Mapping Pipeline

This project maps gearbox mesh nodes to service steps and exports a structured GLB hierarchy for repair workflows.

## Project structure

- `main.py` — orchestrates the full pipeline
- `pipeline/` — stage-by-stage processing scripts
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
