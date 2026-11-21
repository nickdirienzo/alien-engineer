#!/usr/bin/env bash
# Runs every active requirement check against a fresh copy of /experiment.
# Read-only to the agent. See /sacred/SPEC.md for what is being checked.
exec python3 /sacred/lib/runner.py "$@"
