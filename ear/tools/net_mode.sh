#!/usr/bin/env bash
# Pi networking: venue Wi-Fi (internet, git, Tailscale) and the HEIMDALL hotspot for phones.
#
#   ear/tools/net_mode.sh dual     ALFA USB adapter joins the venue Wi-Fi, built-in Wi-Fi runs the hotspot.
#                                  Both at once, permanently (survives reboots). Use this when the ALFA works.
#   ear/tools/net_mode.sh dev      single radio: built-in Wi-Fi joins the venue Wi-Fi (no hotspot)
#   ear/tools/net_mode.sh demo     single radio: built-in Wi-Fi becomes the hotspot (no internet, no Tailscale)
#   ear/tools/net_mode.sh status   show what's active
#
# Hotspot: SSID HEIMDALL, WPA2 password heimdallforge26, Pi at 10.42.0.1, DHCP for phones.
# Profiles are bound to each radio's MAC address, so wlan0/wlan1 renaming doesn't matter.
# Env: VENUE_CON = NetworkManager profile for the venue Wi-Fi (default "BASE-X Guest").
#      Create it once with:  sudo nmcli dev wifi connect "BASE-X Guest" password 'PASS'
#      (single quotes: the venue password contains a $).
set -euo pipefail

VENUE_CON="${VENUE_CON:-BASE-X Guest}"
VENUE_USB_CON="venue-usb"
HOTSPOT_CON="heimdall-hotspot"
SSID="HEIMDALL"
PSK="heimdallforge26"
ADDR="10.42.0.1/24"

nm() { sudo nmcli "$@"; }
have_con() { nmcli -t -f NAME con show | grep -qxF "$1"; }

# Built-in radio = brcmfmac driver; USB radio = any other wlan.
BUILTIN="" USB=""
for i in /sys/class/net/wlan*; do
  [ -e "$i/device/driver" ] || continue
  if [ "$(basename "$(readlink "$i/device/driver")")" = brcmfmac ]; then BUILTIN=$(basename "$i"); else USB=$(basename "$i"); fi
done
[ -n "$BUILTIN" ] || { echo "No built-in Wi-Fi (brcmfmac) found"; exit 1; }
mac() { cat "/sys/class/net/$1/address"; }

ensure_hotspot_profile() {
  if have_con "$HOTSPOT_CON"; then return; fi
  echo "Creating hotspot profile $HOTSPOT_CON ($SSID on $BUILTIN, $ADDR)"
  nm con add type wifi con-name "$HOTSPOT_CON" ifname "*" 802-11-wireless.mac-address "$(mac "$BUILTIN")" \
    autoconnect no ssid "$SSID" \
    802-11-wireless.mode ap 802-11-wireless.band bg 802-11-wireless.channel 6 \
    ipv4.method shared ipv4.addresses "$ADDR" ipv6.method disabled \
    wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$PSK" \
    wifi-sec.proto rsn wifi-sec.pairwise ccmp wifi-sec.group ccmp wifi-sec.pmf disable
}

require_venue() {
  if ! have_con "$VENUE_CON"; then
    echo "No connection named '$VENUE_CON'. Existing:"; nmcli -f NAME,TYPE con show
    echo "Create it:  sudo nmcli dev wifi connect \"BASE-X Guest\" password 'PASS'   (or set VENUE_CON=<name>)"
    exit 1
  fi
}

# Only these wifi profiles may autoconnect; everything else (old Imager profiles etc.) is switched off.
only_autoconnect() {
  local name type
  while IFS=: read -r name type; do
    [ "$type" = 802-11-wireless ] || continue
    if printf '%s\n' "$@" | grep -qxF "$name"; then
      nm con modify "$name" connection.autoconnect yes connection.autoconnect-priority 10
    else
      nm con modify "$name" connection.autoconnect no
    fi
  done < <(nmcli -t -f NAME,TYPE con show)
}

status() {
  echo "Active connections:"
  nmcli -f NAME,TYPE,DEVICE con show --active
  echo
  ip -4 -br addr show | grep -E "^wlan|^eth|^tailscale" || true
}

# Run the switch detached, so it finishes even when the SSH session dies with the old network.
detached() {
  sudo systemd-run --quiet --collect --unit="net-mode-$(date +%s)" bash -c "$1"
}

case "${1:-}" in
  dual)
    [ -n "$USB" ] || { echo "No USB Wi-Fi adapter found (plug in the ALFA). Use dev/demo instead."; exit 1; }
    require_venue
    ensure_hotspot_profile
    if ! have_con "$VENUE_USB_CON"; then
      echo "Cloning '$VENUE_CON' -> $VENUE_USB_CON on $USB"
      nm con clone "$VENUE_CON" "$VENUE_USB_CON"
    fi
    nm con modify "$VENUE_USB_CON" connection.interface-name "" 802-11-wireless.mac-address "$(mac "$USB")"
    only_autoconnect "$VENUE_USB_CON" "$HOTSPOT_CON"
    echo ">>> $USB (USB) joins venue Wi-Fi..."
    nm con up "$VENUE_USB_CON" ifname "$USB"
    if ! ping -c 2 -W 3 -I "$USB" 1.1.1.1 >/dev/null 2>&1; then
      echo "!!! no internet through $USB; leaving $BUILTIN as it is"; exit 1
    fi
    echo ">>> internet OK on $USB. $BUILTIN (built-in) becomes hotspot $SSID ($ADDR) in a few seconds."
    echo "    SSH over Tailscale may pause ~10 s while it moves to $USB."
    detached "nmcli con down '$VENUE_CON' 2>/dev/null; sleep 1; nmcli con up '$HOTSPOT_CON' ifname '$BUILTIN'"
    ;;
  dev)
    require_venue
    ensure_hotspot_profile
    only_autoconnect "$VENUE_CON"
    echo ">>> DEV mode: $BUILTIN leaves hotspot $SSID and joins venue Wi-Fi '$VENUE_CON'."
    echo "    Phones on $SSID will drop."
    detached "nmcli con down '$HOTSPOT_CON' 2>/dev/null; sleep 1; nmcli con up '$VENUE_CON' ifname '$BUILTIN'"
    ;;
  demo)
    ensure_hotspot_profile
    only_autoconnect "$HOTSPOT_CON"
    echo ">>> DEMO mode: $BUILTIN leaves venue Wi-Fi and becomes hotspot $SSID ($ADDR)."
    echo "!!! No internet and no Tailscale in this mode: SSH over venue Wi-Fi/Tailscale WILL DROP."
    echo "    Get back in: join $SSID (password $PSK) and run: ssh heimdall@10.42.0.1"
    echo "    Back to dev: ear/tools/net_mode.sh dev"
    sleep 3
    detached "nmcli con down '$VENUE_CON' 2>/dev/null; sleep 1; nmcli con up '$HOTSPOT_CON' ifname '$BUILTIN'"
    ;;
  status)
    status
    ;;
  *)
    echo "usage: $0 dual|dev|demo|status"; exit 2
    ;;
esac
