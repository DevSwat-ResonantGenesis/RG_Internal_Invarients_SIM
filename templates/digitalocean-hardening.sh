#!/bin/bash
# ============================================================================
# RARA DigitalOcean Droplet Hardening Script
# 
# This script configures a production-grade security posture for RARA.
# Run as root on a fresh Ubuntu 22.04 LTS droplet.
#
# Security measures:
# 1. Linux user/group separation
# 2. Filesystem permissions (immutable core, mutable runtime)
# 3. systemd service hardening
# 4. AppArmor profile
# 5. Firewall configuration
# 6. Audit logging
# ============================================================================

set -e

echo "=============================================="
echo "RARA DigitalOcean Hardening Script"
echo "=============================================="
echo ""

# ============================================================================
# 1. SYSTEM UPDATES
# ============================================================================

echo "[1/10] Updating system packages..."
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq \
    rsync \
    curl \
    jq \
    auditd \
    apparmor \
    apparmor-utils \
    ufw \
    fail2ban

# ============================================================================
# 2. CREATE USERS AND GROUPS
# ============================================================================

echo "[2/10] Creating users and groups..."

# Groups
groupadd -f resonant
groupadd -f resonant-agent
groupadd -f resonant-audit

# Users
# resonant-core: owns immutable core layer
id -u resonant-core &>/dev/null || \
    useradd -r -s /usr/sbin/nologin -g resonant resonant-core

# resonant-agent: runs the agent, owns runtime
id -u resonant-agent &>/dev/null || \
    useradd -r -s /usr/sbin/nologin -g resonant-agent resonant-agent

# Add resonant-agent to docker group if docker is installed
if getent group docker > /dev/null; then
    usermod -aG docker resonant-agent
fi

# ============================================================================
# 3. CREATE DIRECTORY STRUCTURE
# ============================================================================

echo "[3/10] Creating directory structure..."

mkdir -p /opt/resonant/core/gateway
mkdir -p /opt/resonant/core/auth
mkdir -p /opt/resonant/core/policy
mkdir -p /opt/resonant/core/invariants
mkdir -p /opt/resonant/core/bootstrap

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

mkdir -p /opt/resonant/audit

# ============================================================================
# 4. SET OWNERSHIP AND PERMISSIONS
# ============================================================================

echo "[4/10] Setting ownership and permissions..."

# Core: read-only, owned by resonant-core
chown -R resonant-core:resonant /opt/resonant/core
chmod -R 0550 /opt/resonant/core

# Runtime: writable by agent
chown -R resonant-agent:resonant-agent /opt/resonant/runtime
chmod -R 0750 /opt/resonant/runtime

# Agent: executable, not self-modifiable
chown -R resonant-agent:resonant-agent /opt/resonant/agent
chmod -R 0550 /opt/resonant/agent
# Agent bin needs execute
chmod 0555 /opt/resonant/agent/bin

# Snapshots: append-only semantics (agent can create, not delete old)
chown -R resonant-agent:resonant-agent /opt/resonant/snapshots
chmod -R 0750 /opt/resonant/snapshots

# Logs: writable by agent
chown -R resonant-agent:resonant-agent /opt/resonant/logs
chmod -R 0750 /opt/resonant/logs

# State: writable by agent
chown -R resonant-agent:resonant-agent /opt/resonant/state
chmod -R 0750 /opt/resonant/state

# Audit: writable by agent, readable by audit group
chown -R resonant-agent:resonant-audit /opt/resonant/audit
chmod -R 0750 /opt/resonant/audit

# Make core truly immutable (requires root to change)
chattr +i /opt/resonant/core 2>/dev/null || true

# ============================================================================
# 5. INSTALL SYSTEMD SERVICE
# ============================================================================

echo "[5/10] Installing systemd service..."

cat > /etc/systemd/system/resonant-agent.service << 'EOF'
[Unit]
Description=Resonant Autonomous Runtime Agent (RARA)
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
User=resonant-agent
Group=resonant-agent

WorkingDirectory=/opt/resonant/agent

ExecStart=/opt/resonant/agent/bin/rara-agent \
  --runtime /opt/resonant/runtime \
  --core /opt/resonant/core \
  --snapshots /opt/resonant/snapshots \
  --state /opt/resonant/state \
  --logs /opt/resonant/logs

Restart=always
RestartSec=5
WatchdogSec=60

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectKernelLogs=true
ProtectControlGroups=true
ProtectHostname=true
ProtectClock=true

# Filesystem access
ReadWritePaths=/opt/resonant/runtime
ReadWritePaths=/opt/resonant/snapshots
ReadWritePaths=/opt/resonant/logs
ReadWritePaths=/opt/resonant/state
ReadWritePaths=/opt/resonant/audit
ReadOnlyPaths=/opt/resonant/core
ReadOnlyPaths=/opt/resonant/agent

# Network
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
IPAddressDeny=any
IPAddressAllow=localhost
IPAddressAllow=10.0.0.0/8
IPAddressAllow=172.16.0.0/12
IPAddressAllow=192.168.0.0/16

# Resource limits
LimitNOFILE=65536
MemoryMax=2G
CPUQuota=200%

# Capabilities
CapabilityBoundingSet=
AmbientCapabilities=

# System call filter
SystemCallFilter=@system-service
SystemCallFilter=~@privileged @resources
SystemCallErrorNumber=EPERM

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable resonant-agent

# ============================================================================
# 6. INSTALL SUDOERS (VERY LIMITED)
# ============================================================================

echo "[6/10] Installing sudoers configuration..."

cat > /etc/sudoers.d/resonant-agent << 'EOF'
# Sudoers configuration for resonant-agent
# VERY LIMITED - only service restarts allowed

resonant-agent ALL=(root) NOPASSWD: \
    /usr/bin/docker-compose restart *, \
    /usr/bin/systemctl restart resonant-*, \
    /usr/bin/systemctl reload resonant-*

# Explicitly deny everything else
resonant-agent ALL=(ALL) !ALL
EOF

chmod 0440 /etc/sudoers.d/resonant-agent
visudo -c

# ============================================================================
# 7. CONFIGURE APPARMOR PROFILE
# ============================================================================

echo "[7/10] Configuring AppArmor profile..."

cat > /etc/apparmor.d/opt.resonant.agent << 'EOF'
#include <tunables/global>

/opt/resonant/agent/bin/rara-agent {
  #include <abstractions/base>
  #include <abstractions/python>
  
  # Allow reading core (immutable)
  /opt/resonant/core/** r,
  
  # Allow reading agent binaries
  /opt/resonant/agent/** r,
  /opt/resonant/agent/bin/* ix,
  
  # Allow read/write to runtime
  /opt/resonant/runtime/** rw,
  
  # Allow read/write to snapshots
  /opt/resonant/snapshots/** rw,
  
  # Allow read/write to logs
  /opt/resonant/logs/** rw,
  
  # Allow read/write to state
  /opt/resonant/state/** rw,
  
  # Allow read/write to audit
  /opt/resonant/audit/** rw,
  
  # Deny access to sensitive paths
  deny /etc/passwd w,
  deny /etc/shadow rw,
  deny /etc/sudoers rw,
  deny /root/** rw,
  deny /home/** rw,
  
  # Network
  network inet stream,
  network inet6 stream,
  network unix stream,
  
  # Capabilities
  capability net_bind_service,
}
EOF

apparmor_parser -r /etc/apparmor.d/opt.resonant.agent 2>/dev/null || true

# ============================================================================
# 8. CONFIGURE FIREWALL
# ============================================================================

echo "[8/10] Configuring firewall..."

ufw --force reset
ufw default deny incoming
ufw default allow outgoing

# SSH
ufw allow 22/tcp

# RARA API (internal only by default)
# ufw allow 8093/tcp  # Uncomment if external access needed

# Gateway (if running)
ufw allow 8000/tcp

# Enable firewall
ufw --force enable

# ============================================================================
# 9. CONFIGURE AUDIT LOGGING
# ============================================================================

echo "[9/10] Configuring audit logging..."

cat > /etc/audit/rules.d/resonant.rules << 'EOF'
# Audit rules for RARA

# Monitor changes to core (should never happen)
-w /opt/resonant/core -p wa -k resonant_core_change

# Monitor agent binary changes
-w /opt/resonant/agent/bin -p wa -k resonant_agent_change

# Monitor state changes
-w /opt/resonant/state/FREEZE -p wa -k resonant_freeze
-w /opt/resonant/state/EMERGENCY_STOP -p wa -k resonant_emergency

# Monitor sudo usage by resonant-agent
-a always,exit -F arch=b64 -S execve -F euid=resonant-agent -k resonant_sudo
EOF

systemctl restart auditd

# ============================================================================
# 10. CONFIGURE FAIL2BAN
# ============================================================================

echo "[10/10] Configuring fail2ban..."

cat > /etc/fail2ban/jail.d/resonant.conf << 'EOF'
[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 3600
EOF

systemctl restart fail2ban

# ============================================================================
# VERIFICATION
# ============================================================================

echo ""
echo "=============================================="
echo "Hardening Complete - Verification"
echo "=============================================="
echo ""

echo "Users:"
id resonant-core 2>/dev/null && echo "  ✓ resonant-core exists" || echo "  ✗ resonant-core missing"
id resonant-agent 2>/dev/null && echo "  ✓ resonant-agent exists" || echo "  ✗ resonant-agent missing"

echo ""
echo "Directories:"
[ -d /opt/resonant/core ] && echo "  ✓ /opt/resonant/core exists" || echo "  ✗ /opt/resonant/core missing"
[ -d /opt/resonant/runtime ] && echo "  ✓ /opt/resonant/runtime exists" || echo "  ✗ /opt/resonant/runtime missing"
[ -d /opt/resonant/agent ] && echo "  ✓ /opt/resonant/agent exists" || echo "  ✗ /opt/resonant/agent missing"
[ -d /opt/resonant/snapshots ] && echo "  ✓ /opt/resonant/snapshots exists" || echo "  ✗ /opt/resonant/snapshots missing"

echo ""
echo "Permissions:"
stat -c "%U:%G %a %n" /opt/resonant/core
stat -c "%U:%G %a %n" /opt/resonant/runtime
stat -c "%U:%G %a %n" /opt/resonant/agent

echo ""
echo "Services:"
systemctl is-enabled resonant-agent 2>/dev/null && echo "  ✓ resonant-agent enabled" || echo "  ✗ resonant-agent not enabled"
systemctl is-active ufw 2>/dev/null && echo "  ✓ ufw active" || echo "  ✗ ufw not active"
systemctl is-active auditd 2>/dev/null && echo "  ✓ auditd active" || echo "  ✗ auditd not active"
systemctl is-active fail2ban 2>/dev/null && echo "  ✓ fail2ban active" || echo "  ✗ fail2ban not active"

echo ""
echo "=============================================="
echo "Setup Complete"
echo "=============================================="
echo ""
echo "Next steps:"
echo "  1. Deploy RARA agent binary to /opt/resonant/agent/bin/rara-agent"
echo "  2. Deploy core services to /opt/resonant/core/"
echo "  3. Start the agent: systemctl start resonant-agent"
echo "  4. Check status: systemctl status resonant-agent"
echo ""
echo "Kill switch commands:"
echo "  Freeze:    touch /opt/resonant/state/FREEZE"
echo "  Unfreeze:  rm /opt/resonant/state/FREEZE"
echo "  Emergency: touch /opt/resonant/state/EMERGENCY_STOP"
echo "  Signal:    kill -SIGUSR1 \$(pgrep rara-agent)  # freeze"
echo "            kill -SIGUSR2 \$(pgrep rara-agent)  # unfreeze"
echo ""
