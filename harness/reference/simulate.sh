#!/usr/bin/env bash
# Dry-run the whole loop with a fake model (no API calls, no cost).
# Lays the repo out as the Dockerfile does, so run it as root in a disposable
# container or VM: it creates users and writes to /harness /sacred /results ...
#   bash harness/reference/simulate.sh            # 9 serial generations
#   PARALLEL=1 MAX_GENERATIONS=4 bash harness/reference/simulate.sh
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run as root in a disposable container"; exit 1; }
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
for u in agent runner probe; do id $u >/dev/null 2>&1 || useradd -m -s /bin/bash $u; done
rm -rf /harness /sacred /results /experiment /work /opt/ae-private /opt/ae-ref /tmp/ae /tmp/ae-fake
mkdir -p /harness /sacred/spec /sacred/checks /results /experiment /opt/ae-ref
cp -r "$ROOT/harness/requirements" /harness/queue
cp "$ROOT/harness/evolve.py" /harness/
cp -r "$ROOT/harness/private" /opt/ae-private
cp -r "$ROOT/harness/probes" /opt/ae-private/probes
chmod -R go-rwx /harness; chown -R root:runner /opt/ae-private; chmod -R u=rwX,g=rX,o= /opt/ae-private
cp "$ROOT"/{program.md,REVIEW.md,spec_check.sh,evolve.sh} /sacred/
cp -r "$ROOT/harness/lib" /sacred/lib
chmod -R a+rX,go-w /sacred; chmod 700 /results
cp "$ROOT/harness/reference/app.py" /opt/ae-ref/app.py
install -m 755 "$ROOT/harness/reference/fake_claude.sh" /usr/local/bin/ae-fake-claude
chown agent:agent /experiment
sudo -u agent env HOME=/home/agent bash -c 'cd /experiment && git config --global user.email a@b && git config --global user.name sim && git init -q && git commit -q --allow-empty -m "generation 0: empty"'
cd /
CLAUDE_BIN=ae-fake-claude MAX_GENERATIONS="${MAX_GENERATIONS:-9}" PROBE_EVERY="${PROBE_EVERY:-2}" bash /sacred/evolve.sh
python3 "$ROOT/report.py" /results/metrics.tsv
