"""Persistent world + detector snapshots so ``serve`` boots fully populated.

AppState was ephemeral: every server restart meant an empty dashboard until
someone clicked "Build". A snapshot captures a built world (stream, features,
attack batch, red-team) plus a trained detector, so ``serve`` can restore a
complete lab in about a second instead of a ~18s cold build-plus-train.

Layout  data/snapshot/
    world.pkl       the World dataclass (pure numpy/pandas, pickled)
    detector/       Detector.save() output (model trees + threshold + metrics)
    meta.json       the exact build configuration, used to pre-warm the
                    world_cache so an identical "New simulation" is instant
"""

import json
import pickle
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

from .config import DATA_DIR

SNAPSHOT_DIR: Path = Path(DATA_DIR) / "snapshot"


def save_snapshot(world, det, run_id: str,
                  directory: Optional[Path] = None,
                  meta: Optional[Dict] = None) -> Path:
    """Write world + detector + build configuration to ``directory``."""
    directory = Path(directory or SNAPSHOT_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "world.pkl").open("wb") as f:
        pickle.dump(world, f, protocol=pickle.HIGHEST_PROTOCOL)
    det.save(directory / "detector")
    info = {
        "run_id": run_id,
        "created_at": time.time(),
        "n_transactions": int(len(world.tx)),
        "fraud_prevalence": round(float(world.y.mean()), 5),
        "n_attack_scenarios": int(world.batch.n_scenarios),
        **(meta or {}),
    }
    (directory / "meta.json").write_text(
        json.dumps(info, indent=2, default=str))
    return directory


def has_snapshot(directory: Optional[Path] = None) -> bool:
    directory = Path(directory or SNAPSHOT_DIR)
    return (directory / "world.pkl").exists() \
        and (directory / "detector" / "detector.json").exists()


def load_snapshot(directory: Optional[Path] = None) -> Tuple[object, object, Dict]:
    """Return (world, detector, meta). The callers own the objects; nothing is
    registered anywhere or persisted to the store."""
    from .detection import Detector
    directory = Path(directory or SNAPSHOT_DIR)
    with (directory / "world.pkl").open("rb") as f:
        world = pickle.load(f)
    det = Detector.load(directory / "detector")
    meta = json.loads((directory / "meta.json").read_text())
    return world, det, meta


def snapshot_config_fingerprint(meta: Dict) -> str:
    """The world_cache key for the snapshot's own build configuration, so that
    an identically-configured simulate after boot returns instantly instead of
    rebuilding the same world."""
    import json as _json
    attack_types = meta.get("attack_types")
    return _json.dumps({
        "scale": meta.get("scale"),
        "seed": meta.get("seed"),
        "target_prevalence": meta.get("target_prevalence"),
        "model_kind": meta.get("model_kind"),
        "train": True,
        "persist": True,
        "attack_types": sorted(attack_types) if attack_types else None,
        "difficulty_mix": None,
    }, sort_keys=True)