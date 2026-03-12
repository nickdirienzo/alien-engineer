FROM ubuntu:24.04

# System dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    lsof \
    python3 \
    python3-pip \
    jq \
    build-essential \
    sudo \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install runtimes the agent might reach for
RUN apt-get update && apt-get install -y \
    golang-go \
    rustc \
    cargo \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code
RUN npm install -g @anthropic-ai/claude-code

# Create non-root user for the agent
# Give it sudo for apt only (to install packages)
RUN useradd -m -s /bin/bash agent \
    && echo "agent ALL=(ALL) NOPASSWD: /usr/bin/apt-get, /usr/bin/apt" >> /etc/sudoers.d/agent

# Sacred files: root-owned directory, agent cannot write to it
COPY SPEC.md spec_check.sh evolve.sh program.md /sacred/
RUN chmod 555 /sacred && chmod 444 /sacred/*

# Agent workspace: agent owns everything here
RUN mkdir -p /experiment && chown agent:agent /experiment
COPY --chown=agent:agent README.md .gitignore /experiment/

RUN mkdir -p /home/agent/.claude && \
    echo '{"hasCompletedOnboarding": true, "lastOnboardingVersion": "2.1.74"}' > /home/agent/.claude.json && \
    cp /home/agent/.claude.json /home/agent/.claude/.claude.json && \
    chown -R agent:agent /home/agent/.claude /home/agent/.claude.json

# Git setup as agent user
USER agent
WORKDIR /experiment
RUN git config --global user.email "alien@experiment" \
    && git config --global user.name "alien-engineer" \
    && git init \
    && git add -A \
    && git commit -m "generation 0: initial state" --allow-empty

USER root
WORKDIR /experiment
ENTRYPOINT ["bash", "/sacred/evolve.sh"]
