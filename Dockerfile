FROM ubuntu:24.04

RUN apt-get update && apt-get install -y \
    curl git lsof procps iptables python3 python3-pip jq build-essential sudo \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Runtimes the agent might reach for (it can also download its own tools).
RUN apt-get update && apt-get install -y golang-go rustc cargo sqlite3 \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g @anthropic-ai/claude-code

# The agent runs unprivileged. By default it gets no sudo: `sudo apt-get` is a
# well-known path to root, and root could read the hidden requirement queue.
# Build with --build-arg ALLOW_APT=1 to allow it anyway.
ARG ALLOW_APT=0
RUN useradd -m -s /bin/bash agent \
    && if [ "$ALLOW_APT" = "1" ]; then \
         echo "agent ALL=(ALL) NOPASSWD: /usr/bin/apt-get, /usr/bin/apt" > /etc/sudoers.d/agent; fi

# runner executes the system under test (empty home, no API key, no network).
# probe runs reviewer and probe models on copies of the workspace.
RUN useradd -m -s /bin/bash runner && useradd -m -s /bin/bash probe

# Hidden from the agent: the loop and the requirement queue (root only), and
# the benchmark and newcomer tasks (root + runner).
COPY harness/requirements /harness/queue
COPY harness/evolve.py /harness/evolve.py
COPY harness/private /opt/ae-private
COPY harness/probes /opt/ae-private/probes
RUN chown -R root:root /harness && chmod -R go-rwx /harness \
    && chown -R root:runner /opt/ae-private && chmod -R u=rwX,g=rX,o= /opt/ae-private

# Sacred: released spec, checks, harness, prompt. Readable, not writable.
COPY program.md REVIEW.md spec_check.sh evolve.sh /sacred/
COPY harness/lib /sacred/lib
RUN mkdir -p /sacred/spec /sacred/checks && chmod -R a+rX,go-w /sacred

# Results: metrics + logs, root-only.
RUN mkdir -p /results && chmod 700 /results

# Agent workspace.
RUN mkdir -p /experiment && chown agent:agent /experiment
RUN for u in agent probe; do mkdir -p /home/$u/.claude && \
    echo '{"hasCompletedOnboarding": true}' > /home/$u/.claude.json && \
    cp /home/$u/.claude.json /home/$u/.claude/.claude.json && \
    chown -R $u:$u /home/$u/.claude /home/$u/.claude.json; done

USER agent
WORKDIR /experiment
RUN git config --global user.email "alien@experiment" \
    && git config --global user.name "alien-engineer" \
    && git init -q \
    && git commit -q -m "generation 0: empty" --allow-empty

USER root
ENTRYPOINT ["bash", "/sacred/evolve.sh"]
