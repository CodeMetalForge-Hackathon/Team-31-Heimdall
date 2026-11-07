#!/usr/bin/env bash
# Switch the Pi's built-in Wi-Fi between venue client (dev) and the HEIMDALL hotspot (demo).
#   ear/tools/net_mode.sh dev      wlan0 joins the venue Wi-Fi (internet, git, SSH via heimdall.local)
#   ear/tools/net_mode.sh demo     wlan0 becomes hotspot HEIMDALL / heimdallforge26 at 10.42.0.1
#   ear/tools/net_mode.sh status   show what's active
# The choice persists across reboots (autoconnect flags are flipped).
# Env: IFACE (default wlan0), VENUE_CON (NetworkManager connection name for the venue Wi-Fi,
#      default: the Raspberry Pi Imager profile "preconfigured").
set -euo pipefail

IFACE="${IFACE:-wlan0}"
VENUE_CON="${VENUE_CON:-preconfigured}"
HOTSPOT_CON="heimdall-hotspot"
SSID="HEIMDALL"
PSK="heimdallforge26"
ADDR="10.42.0.1/24"

nm() { sudo nmcli "$@"; }

ensure_hotspot_profile() {
  if nmcli -t -f NAME con show | grep -qx "$HOTSPOT_CON"; then return; fi
  echo "Creating hotspot profile $HOTSPOT_CON ($SSID on $IFACE, $ADDR)"
  nm con add type wifi ifname "$IFACE" con-name "$HOTSPOT_CON" autoconnect no ssid "$SSID" \
    802-11-wireless.mode ap 802-11-wireless.band bg 802-11-wireless.channel 6 \
    ipv4.method shared ipv4.addresses "$ADDR" ipv6.method disabled \
    wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$PSK" \
    wifi-sec.proto rsn wifi-sec.pairwise ccmp wifi-sec.group ccmp wifi-sec.pmf disable
}

status() {
  echo "Active connections:"
  nmcli -f NAME,TYPE,DEVICE con show --active
  echo
  ip -4 -br addr show "$IFACE" || true
}

# Run the actual switch detached, so it finishes even when the SSH session dies with the old network.
switch_detached() {
  local up="$1" down="$2"
  nm con modify "$up" connection.autoconnect yes connection.autoconnect-priority 10
  nm con modify "$down" connection.autoconnect no
  sudo systemd-run --quiet --collect --unit="net-mode-$(date +%s)" \
    bash -c "nmcli con down '$down' 2>/dev/null; sleep 1; nmcli con up '$up'"
}

case "${1:-}" in
  dev)
    ensure_hotspot_profile
    if ! nmcli -t -f NAME con show | grep -qx "$VENUE_CON"; then
      echo "No connection named '$VENUE_CON'. Existing:"; nmcli -f NAME,TYPE con show
      echo "Re-run with VENUE_CON=<name>, or add one: sudo nmcli dev wifi connect 'BASE-X Guest' password '...'"
      exit 1
    fi
    echo ">>> DEV mode: $IFACE leaves hotspot $SSID and joins venue Wi-Fi '$VENUE_CON'."
    echo "    Phones on $SSID will drop. SSH again with: ssh heimdall@heimdall.local"
    switch_detached "$VENUE_CON" "$HOTSPOT_CON"
    ;;
  demo)
    ensure_hotspot_profile
    echo ">>> DEMO mode: $IFACE leaves venue Wi-Fi and becomes hotspot $SSID ($ADDR)."
    echo "!!! If you are SSH'd in over the venue Wi-Fi, this session WILL DROP in a few seconds."
    echo "    Get back in: join $SSID (password $PSK) and run: ssh heimdall@10.42.0.1"
    echo "    Or use Ethernet (UGREEN switch). Back to dev: ear/tools/net_mode.sh dev"
    sleep 3
    switch_detached "$HOTSPOT_CON" "$VENUE_CON"
    ;;
  status)
    status
    ;;
  *)
    echo "usage: $0 dev|demo|status"; exit 2
    ;;
esac
