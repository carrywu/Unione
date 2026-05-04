#!/usr/bin/env bash
# M2 Fail-Closed Gate Smoke Test
# Verifies canAddToPaper=0 and manualForceAddAllowed=0 for tasks with fallback_failed pages
set -euo pipefail

BASE_URL="${BACKEND_BASE_URL:-http://localhost:3010}"
PHONE="${ADMIN_PHONE:-13800138000}"
PASSWORD="${ADMIN_PASSWORD:-123456}"

echo "=== M2 Fail-Closed Gate Smoke Test ==="

# Login
TOKEN=$(curl -s "$BASE_URL/api/auth/login" -X POST \
  -H 'Content-Type: application/json' \
  -d "{\"phone\":\"$PHONE\",\"password\":\"$PASSWORD\"}" \
  | python3 -c "import json,sys; print(json.loads(sys.stdin.read())['data']['access_token'])")

if [ -z "$TOKEN" ]; then
  echo "FAIL: Login failed"
  exit 1
fi
echo "OK: Login successful"

# Use the known task with fallback_failed pages
TASK_ID="${1:-c70b99d8-cf3f-4057-a4c5-878ed268517e}"

# Check paper-candidates
RESULT=$(curl -s "$BASE_URL/admin/pdf/task/$TASK_ID/paper-candidates" \
  -H "Authorization: Bearer $TOKEN")

CAN_ADD=$(echo "$RESULT" | python3 -c "
import json,sys
d = json.loads(sys.stdin.read())
data = d.get('data',{})
items = data.get('items', data.get('questions',[]))
can_true = sum(1 for i in items if i.get('can_add_to_paper',i.get('canAddToPaper')))
print(can_true)
" 2>/dev/null)

MF_ADD=$(echo "$RESULT" | python3 -c "
import json,sys
d = json.loads(sys.stdin.read())
data = d.get('data',{})
items = data.get('items', data.get('questions',[]))
mf_true = sum(1 for i in items if i.get('manualForceAddAllowed'))
print(mf_true)
" 2>/dev/null)

TOTAL=$(echo "$RESULT" | python3 -c "
import json,sys
d = json.loads(sys.stdin.read())
data = d.get('data',{})
items = data.get('items', data.get('questions',[]))
print(len(items))
" 2>/dev/null)

echo "Task: $TASK_ID"
echo "Total questions: $TOTAL"
echo "canAddToPaper=true: $CAN_ADD"
echo "manualForceAddAllowed=true: $MF_ADD"

FAIL=0

if [ "$CAN_ADD" != "0" ]; then
  echo "FAIL: canAddToPaper=true should be 0, got $CAN_ADD"
  FAIL=1
else
  echo "OK: canAddToPaper=true is 0"
fi

if [ "$MF_ADD" != "0" ]; then
  echo "FAIL: manualForceAddAllowed=true should be 0, got $MF_ADD"
  FAIL=1
else
  echo "OK: manualForceAddAllowed=true is 0"
fi

# Check Q7 exists
Q7_EXISTS=$(echo "$RESULT" | python3 -c "
import json,sys
d = json.loads(sys.stdin.read())
data = d.get('data',{})
items = data.get('items', data.get('questions',[]))
# Q7 should be at index 6 (0-indexed)
found = len(items) > 6
print('yes' if found else 'no')
" 2>/dev/null)

if [ "$Q7_EXISTS" = "yes" ]; then
  echo "OK: Q7 exists in paper-candidates"
else
  echo "FAIL: Q7 not found in paper-candidates"
  FAIL=1
fi

# Check fallback-recovery debug file
DEBUG_DIR="backend/debug/pdf-ai-preaudit/$TASK_ID"
if [ -f "$DEBUG_DIR/fallback-recovery.json" ]; then
  FB_PAGES=$(python3 -c "
import json
with open('$DEBUG_DIR/fallback-recovery.json') as f:
    d = json.load(f)
pages = [p['page'] for p in d['pages'] if p.get('failureReason') == 'fallback_failed']
print(pages)
" 2>/dev/null)
  echo "OK: fallback_failed pages: $FB_PAGES"
else
  echo "WARN: fallback-recovery.json not found at $DEBUG_DIR"
fi

# Check source_text_span
if [ -f "$DEBUG_DIR/source-text-span-report.json" ]; then
  SPAN_COUNT=$(python3 -c "
import json
with open('$DEBUG_DIR/source-text-span-report.json') as f:
    d = json.load(f)
covered = sum(1 for q in d.get('questions',{}).values() if q.get('has_real_text_span'))
total = len(d.get('questions',{}))
print(f'{covered}/{total}')
" 2>/dev/null)
  echo "OK: source_text_span coverage: $SPAN_COUNT"
else
  echo "WARN: source-text-span-report.json not found"
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "=== M2 FAIL-CLOSED GATE: PASS ==="
  exit 0
else
  echo "=== M2 FAIL-CLOSED GATE: FAIL ==="
  exit 1
fi
