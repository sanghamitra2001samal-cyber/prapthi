#!/usr/bin/env bash
# Creates the Google Play upload key for Prapthi AI and the keystore.properties
# file the release build reads. Run it once, yourself: it asks for a password
# that only you should know. Keep the .jks file and the password somewhere
# safe (a password manager plus an offline copy). With Play App Signing a lost
# upload key can be reset through Play Console support, but it takes days.
set -euo pipefail
cd "$(dirname "$0")/../android"

KEYSTORE="prapthi-upload.jks"
ALIAS="prapthi-upload"
if [ -f "$KEYSTORE" ]; then
  echo "$KEYSTORE already exists — refusing to overwrite an existing key." >&2
  exit 1
fi

JAVA_HOME="${JAVA_HOME:-/usr/local/opt/openjdk@21}"
KEYTOOL="$JAVA_HOME/bin/keytool"
[ -x "$KEYTOOL" ] || KEYTOOL="$(command -v keytool)"

read -r -s -p "Choose a keystore password (min 6 characters): " PASS; echo
read -r -s -p "Type it again: " PASS2; echo
[ "$PASS" = "$PASS2" ] || { echo "Passwords do not match." >&2; exit 1; }
[ ${#PASS} -ge 6 ] || { echo "Too short." >&2; exit 1; }

"$KEYTOOL" -genkeypair -v -keystore "$KEYSTORE" -alias "$ALIAS" \
  -keyalg RSA -keysize 4096 -validity 10000 \
  -storepass "$PASS" -keypass "$PASS" \
  -dname "CN=Prapthi AI, O=Legal Care AI Pvt Ltd, C=IN"

umask 077
cat > keystore.properties <<PROPS
storeFile=$KEYSTORE
storePassword=$PASS
keyAlias=$ALIAS
keyPassword=$PASS
PROPS
chmod 600 "$KEYSTORE" keystore.properties
echo
echo "Created android/$KEYSTORE and android/keystore.properties (both git-ignored)."
echo "Back up $KEYSTORE and the password now."
