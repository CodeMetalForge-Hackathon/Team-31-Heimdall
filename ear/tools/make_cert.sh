#!/usr/bin/env bash
# Make a tiny local CA + a server cert for the Ear (30 days).
# The server cert covers IP:10.42.0.1 (hotspot), DNS:heimdall.local, and localhost for laptop tests.
# Phones can either click through the warning, or install ca.pem once (served at /ca.crt).
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)/certs"
DAYS=30
mkdir -p "$DIR"
cd "$DIR"

if [[ -f cert.pem && "${1:-}" != "--force" ]]; then
  echo "certs already exist in $DIR (use --force to remake)"
  openssl x509 -in cert.pem -noout -subject -enddate
  exit 0
fi

openssl req -x509 -newkey rsa:2048 -nodes -days "$DAYS" -sha256 \
  -keyout ca.key -out ca.pem -subj "/CN=Heimdall Local CA" \
  -addext "basicConstraints=critical,CA:TRUE" -addext "keyUsage=critical,keyCertSign,cRLSign"

openssl req -newkey rsa:2048 -nodes -sha256 -keyout key.pem -out server.csr -subj "/CN=heimdall.local"

cat > server.ext <<EOF
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=IP:10.42.0.1,DNS:heimdall.local,DNS:localhost,IP:127.0.0.1
EOF
openssl x509 -req -in server.csr -CA ca.pem -CAkey ca.key -CAcreateserial -days "$DAYS" -sha256 \
  -extfile server.ext -out cert.pem
rm -f server.csr server.ext ca.srl
chmod 600 ca.key key.pem

echo "Made certs in $DIR:"
openssl x509 -in cert.pem -noout -subject -enddate -ext subjectAltName
