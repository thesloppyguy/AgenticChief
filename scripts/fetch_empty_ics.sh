#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."

set -a
source /tmp/ichr_creds.env
set +a

AUTH=$(python3 -c "import base64,os; print(base64.b64encode(f\"{os.environ['ICHRATTRITION_USERNAME']}:{os.environ['ICHRATTRITION_PASSWORD']}\".encode()).decode())")
URL='https://l550084-iflmap.hcisbp.ae1.hana.ondemand.com/http/ICHRATTRITION'
LOG=/tmp/ichr_fetch_600.log

fetch_ic() {
  local IC="$1"
  local TIMEOUT="$2"
  local out="data/${IC}.json"
  echo "---- $IC timeout=${TIMEOUT}s ----" | tee -a "$LOG"
  local http_code
  http_code=$(curl --silent --show-error --location --request GET "$URL" \
    --header 'Content-Type: application/xml' \
    --header 'Accept: application/json, application/xml, text/xml, */*' \
    --header 'Connection: close' \
    --header "Authorization: Basic ${AUTH}" \
    --data "<Trigger><IC>${IC}</IC></Trigger>" \
    --max-time "$TIMEOUT" \
    --write-out '%{http_code}' \
    --output "$out" 2>>"$LOG")
  local rc=$?
  local size
  size=$(wc -c < "$out" | tr -d ' ')
  echo "IC=$IC rc=$rc HTTP=$http_code bytes=$size" | tee -a "$LOG"
  [[ $rc -eq 0 && "$http_code" == "200" && "$size" -gt 0 ]]
}

: > "$LOG"
EMPTY=()
for f in data/*.json; do
  if [[ ! -s "$f" ]]; then
    EMPTY+=("$(basename "$f" .json)")
  fi
done

echo "Empty ICs (${#EMPTY[@]}): ${EMPTY[*]}" | tee -a "$LOG"

for IC in "${EMPTY[@]}"; do
  if fetch_ic "$IC" 600; then
    echo "SUCCESS $IC (600s)" | tee -a "$LOG"
    continue
  fi
  echo "RETRY $IC with 1200s" | tee -a "$LOG"
  sleep 2
  if fetch_ic "$IC" 1200; then
    echo "SUCCESS $IC (1200s)" | tee -a "$LOG"
  else
    echo "FAILED $IC" | tee -a "$LOG"
  fi
done

echo "==== FINAL ====" | tee -a "$LOG"
for f in data/*.json; do
  ic=$(basename "$f" .json)
  size=$(wc -c < "$f" | tr -d ' ')
  if [[ "$size" -eq 0 ]]; then
    echo "EMPTY  $ic" | tee -a "$LOG"
  else
    echo "OK     $ic ($size bytes)" | tee -a "$LOG"
  fi
done
echo DONE | tee -a "$LOG"
