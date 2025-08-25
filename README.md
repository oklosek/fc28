# FC28

## Network Configuration

Run `scripts/configure_network.sh` as root during installation to configure dual network interfaces:

- `eth0` is configured as WAN with DHCP for internet access.
- `eth1` is configured as an isolated LAN (`192.168.50.1/24`).
- Firewall rules block forwarding between WAN and LAN, allowing only the controller to communicate externally.

Adjust interface names or networks in the script if your hardware uses different identifiers.
