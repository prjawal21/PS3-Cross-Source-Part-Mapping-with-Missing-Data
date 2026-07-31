from pathlib import Path
import os

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def resolve_data_root() -> Path:
    env_root = os.environ.get("GEARBOX_DATA_ROOT")
    if env_root:
        candidate = Path(env_root).expanduser()
        if candidate.exists():
            return candidate.resolve()

    candidates = [
        PROJECT_ROOT / "service-to-3d-challenge-minimal",
        PROJECT_ROOT.parent / "metadome" / "service-to-3d-challenge-minimal",
        Path(r"C:\trash\metadome\service-to-3d-challenge-minimal"),
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    return (PROJECT_ROOT / "service-to-3d-challenge-minimal").resolve()


DATA_ROOT = resolve_data_root()
OUTPUT_ROOT = DATA_ROOT / "pipeline_output"
