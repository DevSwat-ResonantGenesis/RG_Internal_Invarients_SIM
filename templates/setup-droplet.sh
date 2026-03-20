#!/bin/bash
# DigitalOcean Droplet Setup Script for RARA
# Run as root on a fresh Ubuntu 22.04 droplet

set -e

echo "=== RARA Droplet Setup ==="

# 1. Create groups
echo "Creating groups..."
groupadd -f resonant
groupadd -f resonant-agent

# 2. Create users
echo "Creating users..."
id -u resonant-core &>/dev/null || useradd -r -s /usr/sbin/nologin resonant-core
id -u resonant-agent &>/dev/null || useradd -r -s /usr/sbin/nologin resonant-agent

# 3. Create directory structure
echo "Creating directory structure..."
mkdir -p /opt/resonant/core
mkdir -p /opt/resonant/runtime/services
mkdir -p /opt/resonant/runtime/configs
mkdir -p /opt/resonant/runtime/routes
mkdir -p /opt/resonant/runtime/experiments
mkdir -p /opt/resonant/agent/bin
mkdir -p /opt/resonant/agent/manifests
mkdir -p /opt/resonant/snapshots
mkdir -p /opt/resonant/logs
mkdir -p /opt/resonant/state/hashsphere
mkdir -p /opt/resonant/state/metrics
mkdir -p /opt/resonant/state/locks

# 4. Set ownership
echo "Setting ownership..."

# core: read-only, even for agent
chown -R resonant-core:resonant /opt/resonant/core
chmod -R 0550 /opt/resonant/core

# runtime: writable by agent
chown -R resonant-agent:resonant-agent /opt/resonant/runtime
chmod -R 0750 /opt/resonant/runtime

# agent: executable, but not self-modifiable
chown -R resonant-agent:resonant-agent /opt/resonant/agent
chmod -R 0550 /opt/resonant/agent

# snapshots: append-only
chown -R resonant-agent:resonant-agent /opt/resonant/snapshots
chmod -R 0750 /opt/resonant/snapshots

# logs/state
chown -R resonant-agent:resonant-agent /opt/resonant/logs /opt/resonant/state
chmod -R 0750 /opt/resonant/logs /opt/resonant/state

# 5. Install sudoers
echo "Installing sudoers configuration..."
cp /opt/resonant/agent/templates/sudoers.d-resonant-agent /etc/sudoers.d/resonant-agent
chmod 0440 /etc/sudoers.d/resonant-agent

# 6. Install systemd service
echo "Installing systemd service..."
cp /opt/resonant/agent/templates/resonant-agent.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable resonant-agent

echo "=== Setup Complete ==="
echo ""
echo "Directory structure:"
echo "  /opt/resonant/core     - IMMUTABLE (read-only)"
echo "  /opt/resonant/runtime  - MUTABLE (agent allowed)"
echo "  /opt/resonant/agent    - RESTRICTED (self-update only)"
echo "  /opt/resonant/snapshots - Rollback store"
echo ""
echo "To start the agent:"
echo "  systemctl start resonant-agent"
echo ""
echo "To check status:"
echo "  systemctl status resonant-agent"
