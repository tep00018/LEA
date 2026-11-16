"""Central configuration: the default course and course discovery.

No course is hard-coded anywhere else. The default course comes from here, and the list of
available courses is whatever has a folder under ``data/kc_models/``.

    DEFAULT_COURSE      "DEMO101" unless the environment variable LEA_DEFAULT_COURSE is set
    DEFAULT_LOCATION    "London" unless the environment variable LEA_DEFAULT_LOCATION is set
                        (used by the weather tools when a request names no location)
    discover_courses()  course codes found as folders under data/kc_models/
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
KC_MODELS_DIR = DATA_DIR / "kc_models"
COURSE_PROFILES_DIR = DATA_DIR / "course_profiles"

DEFAULT_COURSE = os.getenv("LEA_DEFAULT_COURSE", "DEMO101").strip() or "DEMO101"
DEFAULT_LOCATION = os.getenv("LEA_DEFAULT_LOCATION", "London").strip() or "London"


def discover_courses(kc_models_dir: Optional[Path] = None) -> List[str]:
    """Course codes available on this installation, sorted.

    A course is any sub-folder of ``data/kc_models/`` (hidden folders are ignored). If none is
    found, the default course is returned so that callers always get a usable, non-empty list.
    """
    base = Path(kc_models_dir) if kc_models_dir is not None else KC_MODELS_DIR
    try:
        found = sorted(p.name for p in base.iterdir() if p.is_dir() and not p.name.startswith("."))
    except OSError:
        found = []
    return found or [DEFAULT_COURSE]
