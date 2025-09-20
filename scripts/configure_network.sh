#!/bin/bash
# Ensure the script is executed with root privileges
if [ "$EUID" -ne 0 ]; then
  echo "Run as root"
  exit 1
fi
# Configure dual-network interface setup with isolated LAN and WAN
# WAN interface has internet access, LAN is internal network without internet access.
# This script should be run with root privileges during system installation.

set -euo pipefail

WAN_IFACE="eth0"
LAN_IFACE="eth1"
LAN_IP="192.168.50.1"
LAN_NET="192.168.50.0/24"

# Bring up interfaces
ip link set "$WAN_IFACE" up
ip link set "$LAN_IFACE" up

# Ensure the WAN interface uses DHCP
if command -v dhclient >/dev/null 2>&1; then
  # Release an existing lease to avoid "already assigned" errors
  dhclient -r "$WAN_IFACE" >/dev/null 2>&1 || true
  ip addr flush dev "$WAN_IFACE"
  dhclient "$WAN_IFACE"
fi

# Configure static IP on LAN interface
ip addr flush dev "$LAN_IFACE"
ip addr replace "$LAN_IP/24" dev "$LAN_IFACE"

# Disable IP forwarding to keep LAN isolated from WAN
sysctl -w net.ipv4.ip_forward=0

# Reset firewall rules when iptables is available
if command -v iptables >/dev/null 2>&1; then
  iptables -F
  iptables -t nat -F
  iptables -P INPUT DROP
  iptables -P FORWARD DROP
  iptables -P OUTPUT ACCEPT

  # Allow loopback and established connections
  iptables -A INPUT -i lo -j ACCEPT
  iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

  # Allow LAN devices to reach the controller
  iptables -A INPUT -i "$LAN_IFACE" -s "$LAN_NET" -j ACCEPT

  # Allow selected inbound services from WAN (SSH and HTTPS by default)
  iptables -A INPUT -i "$WAN_IFACE" -p tcp -m multiport --dports 22,443 -j ACCEPT

  # Block forwarding between LAN and WAN
  iptables -A FORWARD -i "$LAN_IFACE" -o "$WAN_IFACE" -j DROP
  iptables -A FORWARD -i "$WAN_IFACE" -o "$LAN_IFACE" -j DROP

  # Save rules if iptables-persistent is available
  if command -v netfilter-persistent >/dev/null 2>&1; then
    netfilter-persistent save
  elif [ -d /etc/iptables ]; then
    iptables-save > /etc/iptables/rules.v4
  fi
else
  echo "iptables not found; skipping firewall configuration" >&2
fi

echo "Network configuration applied: WAN=$WAN_IFACE, LAN=$LAN_IFACE"

