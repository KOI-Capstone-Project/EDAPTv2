#!/bin/sh
# EDAPT v2 — scheduled-retrain sidecar loop.
#
# Runs scheduled_retrain.py once, sleeps 24h, repeats. scheduled_retrain.py
# is itself the safety gate: it's a confirmed, side-effect-free no-op when
# no new study period has appeared (see check_new_period.py), so running it
# once a day regardless of whether anything actually changed is safe by
# design, not just in practice.
#
# A `|| true` around the invocation deliberately keeps the loop itself
# alive even if a single run fails (bad data, a training error, a registry
# lock timeout under RegistryLockTimeout) — the next day's run gets a fresh
# attempt rather than the whole sidecar container needing a manual restart.
# Restarting this container resets the 24h timer, not a fixed wall-clock
# schedule — acceptable because each run's own no-op check is what actually
# guards correctness, not the exact cadence.
set -u

while true; do
  echo "[retrain_loop] $(date -u +%Y-%m-%dT%H:%M:%SZ) — running scheduled_retrain.py"
  python -m app.ml.scheduled_retrain || echo "[retrain_loop] scheduled_retrain.py exited non-zero — will retry on the next 24h cycle"
  echo "[retrain_loop] sleeping 24h until next check"
  sleep 86400
done
