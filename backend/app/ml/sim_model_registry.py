"""
EDAPT v2 — Versioned registry for the simulated-progress (mid-term) model
family, mirroring model_registry.py's pattern for the complete-record
model exactly (register-only writes, explicit promotion, a real lock).

Why this is a SEPARATE module rather than parameterizing model_registry.py:
this was added urgently, after discovering train_simulated_progress.py had
no promotion gate at all — it overwrote best_model_simulated_progress.pkl
directly, live immediately, no versioning, no comparison, no human review.
Reusing model_registry.py's logic without risking any change to the
already-correct, already-in-production complete-record registry was the
priority; a smaller, independent module pointed at its own directory does
that with zero risk to the existing one.

Layout:
    backend/app/ml/models_simulated/
        registry.json
        model_20260808_140230.pkl
        ...

Predictor.py loads the live version from here (load_live_model()) instead
of a hardcoded best_model_simulated_progress.pkl path. A one-time
migration folds whatever best_model_simulated_progress.pkl exists on disk
in as the first version, live from the start — zero-disruption for
whatever's currently deployed, same approach model_registry.py used for
its own legacy best_model.pkl migration.
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import joblib
import contextlib

MODELS_DIR    = Path(__file__).resolve().parent / "models_simulated"
REGISTRY_PATH = MODELS_DIR / "registry.json"

# Legacy path from before this registry existed — read only, for one-time
# migration. New versions never write here again.
LEGACY_PKL_PATH = Path(__file__).resolve().parent / "best_model_simulated_progress.pkl"

LOCK_PATH = MODELS_DIR / ".registry.lock"
LOCK_STALE_SECONDS = 30 * 60
LOCK_WAIT_MAX_SECONDS = 5 * 60
LOCK_POLL_INTERVAL_SECONDS = 1

# Same threshold model_registry.py's compare_and_promote.py uses — reused
# deliberately, not re-derived, per the instruction to match the existing
# complete-record logic where reasonable.
MEANINGFULLY_WORSE_RECALL_DROP    = 0.03
MEANINGFULLY_WORSE_PRECISION_DROP = 0.03


class RegistryLockTimeout(RuntimeError):
    """Raised when the registry lock couldn't be acquired within
    LOCK_WAIT_MAX_SECONDS."""


def _acquire_registry_lock() -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + LOCK_WAIT_MAX_SECONDS
    while True:
        try:
            fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w") as f:
                f.write(f"{os.getpid()} {datetime.now(timezone.utc).isoformat()}\n")
            return
        except FileExistsError:
            pass

        try:
            age = time.time() - LOCK_PATH.stat().st_mtime
        except FileNotFoundError:
            continue

        if age > LOCK_STALE_SECONDS:
            print(f"[sim_model_registry] Removing stale registry lock (age {age:.0f}s > "
                  f"{LOCK_STALE_SECONDS}s) — presumed orphaned by a crashed process.")
            with contextlib.suppress(FileNotFoundError):
                LOCK_PATH.unlink()
            continue

        if time.monotonic() >= deadline:
            raise RegistryLockTimeout(
                f"Could not acquire the sim-model registry lock within {LOCK_WAIT_MAX_SECONDS}s."
            )
        time.sleep(LOCK_POLL_INTERVAL_SECONDS)


def _release_registry_lock() -> None:
    with contextlib.suppress(FileNotFoundError):
        LOCK_PATH.unlink()


def _empty_registry() -> dict:
    return {"live_version": None, "versions": [], "promotion_history": []}


def load_registry() -> dict:
    if not REGISTRY_PATH.exists():
        return _empty_registry()
    with open(REGISTRY_PATH) as f:
        return json.load(f)


def save_registry(registry: dict) -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    with open(REGISTRY_PATH, "w") as f:
        json.dump(registry, f, indent=2)


def new_version_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def register_version(model_package: dict, extra_metadata: dict, version: Optional[str] = None) -> str:
    """Save model_package to models_simulated/model_{version}.pkl and append
    a registry entry. Does NOT set it live."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    _acquire_registry_lock()
    try:
        registry = load_registry()
        existing_versions = {v["version"] for v in registry["versions"]}

        candidate = version or new_version_id()
        final_version = candidate
        suffix = 2
        while final_version in existing_versions:
            final_version = f"{candidate}_dup{suffix}"
            suffix += 1

        file_name = f"model_{final_version}.pkl"
        joblib.dump(model_package, MODELS_DIR / file_name)

        registry["versions"].append({"version": final_version, "file": file_name, **extra_metadata})
        save_registry(registry)
    finally:
        _release_registry_lock()
    return final_version


def get_version(registry: dict, version: str) -> Optional[dict]:
    return next((v for v in registry["versions"] if v["version"] == version), None)


def get_live_entry(registry: dict) -> Optional[dict]:
    if registry.get("live_version") is None:
        return None
    return get_version(registry, registry["live_version"])


def promote(version: str, reason: str) -> dict:
    """Point live serving at `version`. Raises if it isn't registered."""
    _acquire_registry_lock()
    try:
        registry = load_registry()
        entry = get_version(registry, version)
        if entry is None:
            raise ValueError(f"No such version in registry: {version}")

        previous = registry.get("live_version")
        registry["live_version"] = version
        registry["promotion_history"].append({
            "version":     version,
            "previous":    previous,
            "promoted_at": datetime.now(timezone.utc).isoformat(),
            "reason":      reason,
        })
        save_registry(registry)
    finally:
        _release_registry_lock()
    return entry


def _migrate_legacy() -> Optional[str]:
    """One-time: fold the pre-registry best_model_simulated_progress.pkl in
    as the first version, live from the start — zero-disruption for
    whatever's currently deployed."""
    if not LEGACY_PKL_PATH.exists():
        return None
    print(f"[sim_model_registry] No registry found — migrating existing {LEGACY_PKL_PATH.name} "
          f"into the registry as the first version.")
    package = joblib.load(LEGACY_PKL_PATH)

    trained_at = package.get("trained_at")
    version = None
    if trained_at:
        try:
            version = datetime.fromisoformat(trained_at).strftime("%Y%m%d_%H%M%S")
        except ValueError:
            version = None

    version = register_version(package, {
        "trained_at":            trained_at,
        "accuracy":              package.get("accuracy"),
        "decision_threshold":    package.get("decision_threshold"),
        "classification_report": package.get("classification_report"),
        "train_row_count":       package.get("train_row_count"),
        "trained_on":            package.get("trained_on"),
        "validated_on":          package.get("validated_on"),
        "model_name":            package.get("model_name"),
        "features":              package.get("features"),
        "migrated_from_legacy":  True,
    }, version=version)
    promote(version, reason="Migrated existing best_model_simulated_progress.pkl as the first registry version.")
    return version


def load_live_model() -> Optional[dict]:
    """Load the currently-live simulated-progress model package. Falls back
    to migrating the legacy file into the registry on first run."""
    registry = load_registry()
    live = get_live_entry(registry)

    if live is None and not registry["versions"]:
        _migrate_legacy()
        registry = load_registry()
        live = get_live_entry(registry)

    if live is None:
        return None

    path = MODELS_DIR / live["file"]
    if not path.exists():
        print(f"WARNING: sim registry's live version file missing: {path}")
        return None
    return joblib.load(path)
