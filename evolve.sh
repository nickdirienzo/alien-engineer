#!/usr/bin/env bash
# The maintenance loop. The loop itself lives outside the agent's view.
exec python3 /harness/evolve.py "$@"
