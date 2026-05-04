#!/usr/bin/env bash
set -uo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

REPORT_DIR="debug/regression/$(date '+%Y%m%d-%H%M%S')"
mkdir -p "$REPORT_DIR"
REPORT="$REPORT_DIR/regression-report.md"

PASSED=0
FAILED=0
SKIPPED=0

run_check() {
  local name=$1 dir=$2 cmd=$3
  echo "Running: $name"
  local start_time=$(date +%s)
  local output
  output=$(cd "$dir" && eval "$cmd" 2>&1)
  local exit_code=$?
  local end_time=$(date +%s)
  local duration=$((end_time - start_time))

  if [ $exit_code -eq 0 ]; then
    echo -e "  ${GREEN}PASS${NC} ($duration s)"
    echo "| $name | PASS | ${duration}s |" >> "$REPORT"
    PASSED=$((PASSED+1))
  else
    echo -e "  ${RED}FAIL${NC} (exit $exit_code, $duration s)"
    echo "| $name | FAIL (exit $exit_code) | ${duration}s |" >> "$REPORT"
    FAILED=$((FAILED+1))
    echo "$output" > "$REPORT_DIR/$(echo "$name" | tr ' ' '-').log"
  fi
}

cat > "$REPORT" << 'EOF'
# Regression Test Report

Generated: $(date '+%Y-%m-%d %H:%M:%S')
Branch: $(git branch --show-current)

## Results

| Check | Status | Duration |
|-------|--------|----------|
EOF

# Fix the generated header
sed -i "s/\$(date '+%Y-%m-%d %H:%M:%S')/$(date '+%Y-%m-%d %H:%M:%S')/" "$REPORT"
sed -i "s/\$(git branch --show-current)/$(git branch --show-current)/" "$REPORT"

run_check "Backend build" "/home/carry/project2/backend" "npm run build"
run_check "Admin-web build" "/home/carry/project2/admin-web" "npm run build"
run_check "Backend test" "/home/carry/project2/backend" "node -r ts-node/register -r tsconfig-paths/register test/pdf-review-workflow.test.ts"

# PDF service tests (with venv)
if [ -d "/home/carry/project2/pdf-service/.venv" ]; then
  run_check "PDF service tests" "/home/carry/project2/pdf-service" "source .venv/bin/activate && python -m pytest tests/ -v --tb=short 2>&1 | tail -1"
else
  echo "| PDF service tests | SKIP (no venv) | - |" >> "$REPORT"
  SKIPPED=$((SKIPPED+1))
fi

cat >> "$REPORT" << EOF

## Summary

- Passed: $PASSED
- Failed: $FAILED
- Skipped: $SKIPPED
EOF

echo ""
echo "=== Summary ==="
echo -e "  Passed: ${GREEN}$PASSED${NC}"
echo -e "  Failed: ${RED}$FAILED${NC}"
echo -e "  Skipped: ${YELLOW}$SKIPPED${NC}"
echo ""
echo "Report: $REPORT"

if [ $FAILED -gt 0 ]; then
  exit 1
fi
