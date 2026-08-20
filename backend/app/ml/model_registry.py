"""
EDAPT v2 — Versioned model registry.

Every train_model.py run saves a new, timestamped model version under
models/ instead of overwriting best_model.pkl directly. registry.json
tracks every version's metadata and which one is currently "live" (the one
predictor.py actually serves). Promotion is never automatic —
compare_and_promote.py is the only thing that changes live_version, and it
requires an explicit --promote flag after printing a comparison against
whatever is currently live. The same promote() function backs both
"promote a new candidate" and "roll back to an earlier version" — a
rollback is just a promotion whose target happens to be older, and every
promotion (including rollbacks) is appended to promotion_history so the
full sequence of what was live and when stays auditable.

Layout:
    backend/app/ml/models/
        registry.json
        model_20260714_140230.pkl
        model_20260714_151002.pkl
        ...
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import joblib
import contextlib

MODELS_DIR    = Path(__file__).resolve().parent / "models"
REGISTRY_PATH = MODELS_DIR / "registry.json"

# Legacy path from before versioning existed — read only, for one-time
# migration. New versions never write here again.
LEGACY_PKL_PATH = Path(__file__).resolve().parent / "best_model.pkl"

# ── Concurrency guard ────────────────────────────────────────────────────────
# register_version() and promote() both do load_registry() -> mutate ->
# save_registry() with no atomicity — confirmed by direct reproduction that
# two overlapping callers race: the second writer's save() clobbers the
# first's, silently dropping its registration even though that run's .pkl
# file still exists on disk, orphaned and uncatalogued. A simple exclusive
# lock file closes this: only one register_version()/promote() call can be
# inside its read-modify-write section at a time.
LOCK_PATH = MODELS_DIR / ".registry.lock"
# A lock older than this is presumed orphaned by a process that crashed
# before releasing it (register_version()'s actual critical section — a
# joblib.dump plus a small JSON rewrite — normally completes in well under a
# minute, so 30 minutes is a generous margin, not a realistic hold time).
LOCK_STALE_SECONDS = 30 * 60
# How long a well-behaved concurrent caller waits for the current holder to
# finish before giving up. Generous relative to the expected sub-minute hold
# time, but bounded — if this elapses, something is wrong (very slow holder,
# or a crash inside the stale-timeout window) and failing cleanly here is
# safer than blocking indefinitely or proceeding unprotected.
LOCK_WAIT_MAX_SECONDS = 5 * 60
LOCK_POLL_INTERVAL_SECONDS = 1


class RegistryLockTimeout(RuntimeError):
    """Raised when the registry lock couldn't be acquired within
    LOCK_WAIT_MAX_SECONDS. Fails cleanly rather than proceeding unprotected
    and risking the lost-update race this lock exists to prevent."""


def _acquire_registry_lock() -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + LOCK_WAIT_MAX_SECONDS
    while True:
        try:
            # O_CREAT|O_EXCL is an atomic "create only if it doesn't already
            # exist" at the OS level — the actual mutual-exclusion primitive.
            # A plain "if not path.exists(): create it" has its own race
            # between the check and the create, which would defeat the point.
            fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w") as f:
                f.write(f"{os.getpid()} {datetime.now(timezone.utc).isoformat()}\n")
            return
        except FileExistsError:
            pass

        try:
            age = time.time() - LOCK_PATH.stat().st_mtime
        except FileNotFoundError:
            continue  # released between our open() and stat() — retry immediately

        if age > LOCK_STALE_SECONDS:
            print(f"[model_registry] Removing stale registry lock (age {age:.0f}s > "
                  f"{LOCK_STALE_SECONDS}s) — presumed orphaned by a crashed process.")
            with contextlib.suppress(FileNotFoundError):
                LOCK_PATH.unlink()
            continue

        if time.monotonic() >= deadline:
            raise RegistryLockTimeout(
                f"Could not acquire the model registry lock within {LOCK_WAIT_MAX_SECONDS}s — "
                f"another register_version()/promote() call appears to still be in progress. "
                f"Failing cleanly rather than risking a lost update to registry.json."
            )
        time.sleep(LOCK_POLL_INTERVAL_SECONDS)


def _release_registry_lock() -> None:
    with contextlib.suppress(FileNotFoundError):
        LOCK_PATH.unlink()


def _empty_registry() -> dict:
    return {"live_version": None, "versions": [], "promotion_history": []}


def load_registry() -> dict:
    """Read registry.json for the COMPLETE-RECORD model family.

    Returns an empty-but-valid registry ({"live_version": None, "versions": [],
    "promotion_history": []}) when the file does not exist yet, rather than
    raising — a fresh clone has no registry, and callers should see "no live
    model" instead of an exception during import.
    """
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
    """
    Save model_package to models/model_{version}.pkl and append an entry to
    the registry. Does NOT set it live.

    The whole version-assignment + dump + registry-update sequence runs under
    the registry lock — not just the JSON read-modify-write — so two
    overlapping callers can no longer race on this, and (extremely unlikely,
    but now cheap to also guard against since calls are serialized anyway)
    two callers landing on the identical second-precision timestamp can't
    silently overwrite each other's model file under one shared version id.
    """
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
    """The entry for one version id, or None if that version was never
    registered. Does not touch disk — pass a registry from load_registry()."""
    return next((v for v in registry["versions"] if v["version"] == version), None)


def get_live_entry(registry: dict) -> Optional[dict]:
    """The entry currently serving traffic, or None if nothing is promoted.

    None is a real, expected state, not an error: registration never promotes
    automatically (see register_version), so a registry can hold many versions
    with no live one until a human runs compare_and_promote.
    """
    if registry.get("live_version") is None:
        return None
    return get_version(registry, registry["live_version"])


def promote(version: str, reason: str) -> dict:
    """Point the live serving layer at `version`. Raises if it isn't registered.

    Same registry lock as register_version() — promote() does the identical
    load-mutate-save on registry.json, so it's exposed to the same lost-update
    race if it ever overlaps with a concurrent register_version() (or another
    promote()) call.
    """
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
    """One-time: fold the pre-versioning best_model.pkl into the registry as
    the first version, live from the start, so switching predictor.py to
    registry-based loading is zero-disruption for whatever is deployed today."""
    if not LEGACY_PKL_PATH.exists():
        return None
    print(f"[model_registry] No registry found — migrating existing {LEGACY_PKL_PATH.name} "
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
        "safe_subjects":         package.get("safe_subjects", []),
        "train_row_count":       package.get("train_row_count"),
        "trained_on":            package.get("trained_on"),
        "validated_on":          package.get("validated_on"),
        "model_name":            package.get("model_name"),
        "migrated_from_legacy":  True,
    }, version=version)
    promote(version, reason="Migrated existing best_model.pkl as the first registry version.")
    return version


def load_live_model() -> Optional[dict]:
    """
    Load the currently-live model package. Drop-in replacement for the old
    `joblib.load(best_model.pkl)` pattern — falls back to migrating legacy
    best_model.pkl into the registry on first run, so there's zero
    disruption to whatever is already deployed.
    """
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
        print(f"WARNING: registry's live version file missing: {path}")
        return None
    return joblib.load(path)
