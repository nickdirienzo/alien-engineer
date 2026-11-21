FROM ubuntu:24.04

RUN apt-get update && apt-get install -y \
    curl git lsof procps python3 python3-pip jq build-essential sudo \
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

# Hidden requirement queue: root-only.
COPY harness/requirements /harness/queue
RUN chown -R root:root /harness && chmod -R go-rwx /harness

# Sacred: released spec, checks, harness, prompt. Readable, not writable.
COPY program.md spec_check.sh evolve.sh /sacred/
COPY harness/lib /sacred/lib
RUN mkdir -p /sacred/spec /sacred/checks && chmod -R a+rX,go-w /sacred

# Results: metrics + logs, root-only.
RUN mkdir -p /results && chmod 700 /results

# Agent workspace.
RUN mkdir -p /experiment && chown agent:agent /experiment
RUN mkdir -p /home/agent/.claude && \
    echo '{"hasCompletedOnboarding": true}' > /home/agent/.claude.json && \
    cp /home/agent/.claude.json /home/agent/.claude/.claude.json && \
    chown -R agent:agent /home/agent/.claude /home/agent/.claude.json

USER agent
WORKDIR /experiment
RUN git config --global user.email "alien@experiment" \
    && git config --global user.name "alien-engineer" \
    && git init -q \
    && git commit -q -m "generation 0: empty" --allow-empty

USER root
ENTRYPOINT ["bash", "/sacred/evolve.sh"]
