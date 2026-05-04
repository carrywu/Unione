#!/usr/bin/env bash
# Ralph loop runner for this repository.
# Usage:
#   ./scripts/ralph/ralph.sh [max_iterations]
#   ./scripts/ralph/ralph.sh --tool claude [max_iterations]

set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  ./scripts/ralph/ralph.sh [max_iterations]
  ./scripts/ralph/ralph.sh --tool amp|claude [max_iterations]

Examples:
  ./scripts/ralph/ralph.sh
  ./scripts/ralph/ralph.sh 3
  ./scripts/ralph/ralph.sh --tool claude 5
EOF
}

TOOL="amp"
MAX_ITERATIONS=10

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --tool)
      if [[ $# -lt 2 ]]; then
        echo "Error: --tool requires a value: amp or claude" >&2
        exit 1
      fi
      TOOL="$2"
      shift 2
      ;;
    --tool=*)
      TOOL="${1#*=}"
      shift
      ;;
    *)
      if [[ "$1" =~ ^[0-9]+$ ]]; then
        MAX_ITERATIONS="$1"
        shift
      else
        echo "Error: Unknown argument '$1'" >&2
        usage >&2
        exit 1
      fi
      ;;
  esac
done

if [[ "$TOOL" != "amp" && "$TOOL" != "claude" ]]; then
  echo "Error: Invalid tool '$TOOL'. Must be 'amp' or 'claude'." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PRD_FILE="$PROJECT_ROOT/prd.json"
PROGRESS_FILE="$PROJECT_ROOT/progress.txt"
ARCHIVE_DIR="$PROJECT_ROOT/archive"
LAST_BRANCH_FILE="$SCRIPT_DIR/.last-branch"

if ! command -v jq >/dev/null 2>&1; then
  echo "Error: jq is required but not installed." >&2
  exit 1
fi

if [[ "$TOOL" == "amp" ]]; then
  PROMPT_FILE="$SCRIPT_DIR/prompt.md"
  TOOL_CMD="amp"
else
  PROMPT_FILE="$SCRIPT_DIR/CLAUDE.md"
  TOOL_CMD="claude"
fi

if ! command -v "$TOOL_CMD" >/dev/null 2>&1; then
  echo "Error: '$TOOL_CMD' is not installed or not on PATH." >&2
  exit 1
fi

if [[ ! -f "$PRD_FILE" ]]; then
  echo "Error: Missing PRD file at $PRD_FILE" >&2
  exit 1
fi

if [[ ! -f "$PROMPT_FILE" ]]; then
  echo "Error: Missing prompt file at $PROMPT_FILE" >&2
  exit 1
fi

if ! jq empty "$PRD_FILE" >/dev/null 2>&1; then
  echo "Error: PRD file is not valid JSON: $PRD_FILE" >&2
  exit 1
fi

mkdir -p "$ARCHIVE_DIR"

current_branch_from_prd="$(jq -r '.branchName // empty' "$PRD_FILE")"

if [[ -f "$LAST_BRANCH_FILE" && -n "$current_branch_from_prd" ]]; then
  last_branch="$(cat "$LAST_BRANCH_FILE" 2>/dev/null || true)"
  if [[ -n "$last_branch" && "$last_branch" != "$current_branch_from_prd" ]]; then
    archive_date="$(date +%Y-%m-%d)"
    archive_name="$(printf '%s' "$last_branch" | sed 's|^ralph/||')"
    archive_path="$ARCHIVE_DIR/$archive_date-$archive_name"
    mkdir -p "$archive_path"
    cp "$PRD_FILE" "$archive_path/prd.json"
    [[ -f "$PROGRESS_FILE" ]] && cp "$PROGRESS_FILE" "$archive_path/progress.txt"
    echo "Archived previous Ralph state to $archive_path"
  fi
fi

if [[ -n "$current_branch_from_prd" ]]; then
  printf '%s\n' "$current_branch_from_prd" > "$LAST_BRANCH_FILE"
fi

if [[ ! -f "$PROGRESS_FILE" ]]; then
  {
    echo "Project: unknown"
    echo "Branch: ${current_branch_from_prd:-unknown}"
    echo "Initialized At: $(date '+%Y-%m-%d %H:%M:%S %Z (%z)')"
    echo "Status: initialized by scripts/ralph/ralph.sh"
  } > "$PROGRESS_FILE"
fi

export RALPH_PROJECT_ROOT="$PROJECT_ROOT"
export RALPH_PRD_FILE="$PRD_FILE"
export RALPH_PROGRESS_FILE="$PROGRESS_FILE"
export RALPH_TOOL="$TOOL"

cd "$PROJECT_ROOT"

echo "Starting Ralph"
echo "  Tool: $TOOL"
echo "  Max iterations: $MAX_ITERATIONS"
echo "  Project root: $PROJECT_ROOT"
echo "  PRD: $PRD_FILE"
echo "  Progress: $PROGRESS_FILE"

for i in $(seq 1 "$MAX_ITERATIONS"); do
  echo
  echo "==============================================================="
  echo "  Ralph Iteration $i of $MAX_ITERATIONS ($TOOL)"
  echo "==============================================================="

  if [[ "$TOOL" == "amp" ]]; then
    OUTPUT="$(amp --dangerously-allow-all < "$PROMPT_FILE" 2>&1 | tee /dev/stderr)" || true
  else
    OUTPUT="$(claude --dangerously-skip-permissions --print < "$PROMPT_FILE" 2>&1 | tee /dev/stderr)" || true
  fi

  if printf '%s' "$OUTPUT" | grep -q "<promise>COMPLETE</promise>"; then
    echo
    echo "Ralph completed all tasks."
    echo "Completed at iteration $i of $MAX_ITERATIONS"
    exit 0
  fi

  echo "Iteration $i complete. Continuing..."
  sleep 2
done

echo
echo "Ralph reached max iterations ($MAX_ITERATIONS) without completing all tasks."
echo "Check $PROGRESS_FILE for progress."
exit 1
