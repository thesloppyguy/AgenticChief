#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."

OUT_DIR="EmployeeCycle"
mkdir -p "$OUT_DIR"

URL='https://l550084-iflmap.hcisbp.ae1.hana.ondemand.com/http/ICHRATTRITION'
AUTH='UDIwMDExNDc2MzM6ZGFyQDEyM2tiSA=='
LOG=/tmp/employee_cycle_fetch.log
TIMEOUT=600

# All ICs from API.md
ICS=(
  PTD TI RCF LTPO GEO REN HCI PAH MMH DC
  HYOS HYOF DEIC MIPD RELT MRSF HENG VALV MRHL HYOW
  LEDT IU72 HOSC LTST SWC LTGE SU LTCG WETD WETI
)

fetch_ic() {
  local IC="$1"
  local out="${OUT_DIR}/${IC}.json"
  echo "---- $IC ----" | tee -a "$LOG"
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
  size=$(wc -c < "$out" 2>/dev/null | tr -d ' ' || echo 0)
  echo "IC=$IC rc=$rc HTTP=$http_code bytes=$size" | tee -a "$LOG"
  [[ $rc -eq 0 && "$http_code" == "200" && "$size" -gt 0 ]]
}

: > "$LOG"
echo "Fetching ${#ICS[@]} ICs into ${OUT_DIR}/ (timeout=${TIMEOUT}s each)" | tee -a "$LOG"

OK=()
FAIL=()
for IC in "${ICS[@]}"; do
  if fetch_ic "$IC"; then
    OK+=("$IC")
    echo "SUCCESS $IC" | tee -a "$LOG"
  else
    echo "RETRY $IC" | tee -a "$LOG"
    sleep 2
    if fetch_ic "$IC"; then
      OK+=("$IC")
      echo "SUCCESS $IC (retry)" | tee -a "$LOG"
    else
      FAIL+=("$IC")
      echo "FAILED $IC" | tee -a "$LOG"
    fi
  fi
  sleep 1
done

echo "==== FINAL ====" | tee -a "$LOG"
echo "OK (${#OK[@]}): ${OK[*]}" | tee -a "$LOG"
echo "FAIL (${#FAIL[@]}): ${FAIL[*]:-none}" | tee -a "$LOG"
for f in "$OUT_DIR"/*.json; do
  [[ -e "$f" ]] || continue
  ic=$(basename "$f" .json)
  size=$(wc -c < "$f" | tr -d ' ')
  if [[ "$size" -eq 0 ]]; then
    echo "EMPTY  $ic" | tee -a "$LOG"
  else
    echo "OK     $ic ($size bytes)" | tee -a "$LOG"
  fi
done
echo DONE | tee -a "$LOG"
