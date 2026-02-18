#!/usr/bin/env bash
set -u -o pipefail

# Kei CLI <-> Kei API integration checks.
#
# Prerequisites:
# 1) Kei API running at KEI_API_BASE (default http://127.0.0.1:8081)
# 2) KEI_API_TOKEN set (defaults to test-token)
# 3) CLI virtualenv installed at .venv (auto-bootstrapped by default)

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
AUTO_BOOTSTRAP_VENV="${KEI_AUTO_BOOTSTRAP_VENV:-1}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "[INFO] Missing Python venv: $PYTHON_BIN"

  if [[ "$AUTO_BOOTSTRAP_VENV" != "1" ]]; then
    echo "[FAIL] Auto-bootstrap disabled (KEI_AUTO_BOOTSTRAP_VENV=$AUTO_BOOTSTRAP_VENV)"
    echo "Run: cd $ROOT_DIR && python3 -m venv .venv && .venv/bin/pip install -e ."
    exit 1
  fi

  if ! command -v python3 >/dev/null 2>&1; then
    echo "[FAIL] python3 not found; cannot bootstrap venv."
    exit 1
  fi

  echo "[INFO] Bootstrapping CLI venv..."
  if ! (cd "$ROOT_DIR" && python3 -m venv .venv); then
    echo "[FAIL] Failed to create virtualenv at $ROOT_DIR/.venv"
    exit 1
  fi

  if ! (cd "$ROOT_DIR" && .venv/bin/pip install -e .); then
    echo "[FAIL] Failed to install CLI into virtualenv."
    echo "Try manually: cd $ROOT_DIR && .venv/bin/pip install -e ."
    exit 1
  fi

  if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "[FAIL] Virtualenv bootstrap completed but python executable not found: $PYTHON_BIN"
    exit 1
  fi
fi

API_BASE="${KEI_API_BASE:-http://127.0.0.1:8081}"
API_TOKEN="${KEI_API_TOKEN:-test-token}"
SALON_SCOPE="${KEI_SALON_SCOPE:-salon}"
HOME_SCOPE="${KEI_HOME_SCOPE:-home}"
EXPECT_BOTH_SCOPES="${KEI_EXPECT_BOTH_SCOPES:-0}"

TEST_HOME="$(mktemp -d /tmp/kei-cli-home.XXXXXX)"
trap 'rm -rf "$TEST_HOME"' EXIT

PASS_COUNT=0
FAIL_COUNT=0
LAST_OUT=""
LAST_STATUS=0

run_capture() {
  LAST_OUT="$("$@" 2>&1)"
  LAST_STATUS=$?
}

run_cli() {
  run_capture env \
    HOME="$TEST_HOME" \
    KEI_API_BASE="$API_BASE" \
    KEI_API_TOKEN="$API_TOKEN" \
    NO_COLOR=1 \
    "$PYTHON_BIN" -m kei.cli "$@"
}

run_cli_with_base() {
  local base="$1"
  shift
  run_capture env \
    HOME="$TEST_HOME" \
    KEI_API_BASE="$base" \
    KEI_API_TOKEN="$API_TOKEN" \
    NO_COLOR=1 \
    "$PYTHON_BIN" -m kei.cli "$@"
}

pass() {
  local msg="$1"
  PASS_COUNT=$((PASS_COUNT + 1))
  printf '[PASS] %s\n' "$msg"
}

show_last_out() {
  if [[ -n "$LAST_OUT" ]]; then
    printf '%s\n' "$LAST_OUT" | sed 's/^/    /'
  fi
}

fail() {
  local msg="$1"
  FAIL_COUNT=$((FAIL_COUNT + 1))
  printf '[FAIL] %s\n' "$msg"
  show_last_out
}

printf 'Kei CLI integration checks\n'
printf '  API base: %s\n' "$API_BASE"
printf '  Salon scope: %s\n' "$SALON_SCOPE"
printf '  Home scope: %s\n' "$HOME_SCOPE"
printf '  Expect both scopes in by-scope: %s\n\n' "$EXPECT_BOTH_SCOPES"

cd "$ROOT_DIR"

# 1) Health
run_cli health
if [[ $LAST_STATUS -eq 0 && "$LAST_OUT" == *"API healthy"* ]]; then
  pass "Health check"
else
  fail "Health check"
fi

# 2) Write commands require scope
run_cli tx add expense 1 test --desc "scope check"
if [[ $LAST_STATUS -ne 0 && "$LAST_OUT" == *"requires scope"* ]]; then
  pass "Scope required for writes"
else
  fail "Scope required for writes"
fi

SUFFIX="$(date +%s)"
ENTITY_NAME="Integration Entity $SUFFIX"
SERVICE_NAME="Integration Service $SUFFIX"
ITEM_NAME="Integration Item $SUFFIX"
BAD_ITEM_NAME="Bad Qty $SUFFIX"

ENTITY_ID=""
ENTITY_PREFIX=""
ITEM_PREFIX=""

# 3) Create baseline data
run_cli -s "$SALON_SCOPE" entity add "$ENTITY_NAME" --type client --phone "444-555-6666"
if [[ $LAST_STATUS -eq 0 && "$LAST_OUT" =~ ([0-9a-f]{32}) ]]; then
  ENTITY_ID="${BASH_REMATCH[1]}"
  ENTITY_PREFIX="${ENTITY_ID:0:8}"
  pass "Create entity in $SALON_SCOPE"
else
  fail "Create entity in $SALON_SCOPE"
fi

if [[ -n "$ENTITY_ID" ]]; then
  run_cli -s "$SALON_SCOPE" tx add income 85 haircut --entity "$ENTITY_ID" --cash
  if [[ $LAST_STATUS -eq 0 ]]; then
    pass "Create salon transaction"
  else
    fail "Create salon transaction"
  fi
else
  FAIL_COUNT=$((FAIL_COUNT + 1))
  echo "[FAIL] Create salon transaction (entity not available)"
fi

run_cli -s "$HOME_SCOPE" tx add expense 25 groceries --desc "integration home"
if [[ $LAST_STATUS -eq 0 ]]; then
  pass "Create home transaction"
else
  fail "Create home transaction"
fi

run_cli -s "$SALON_SCOPE" service add "$SERVICE_NAME" 180 --category color --duration 120 --tags premium
if [[ $LAST_STATUS -eq 0 ]]; then
  pass "Create service in $SALON_SCOPE"
else
  fail "Create service in $SALON_SCOPE"
fi

run_cli -s "$SALON_SCOPE" item add "$ITEM_NAME" --category haircare --qty 5 --reorder 2
if [[ $LAST_STATUS -eq 0 && "$LAST_OUT" =~ ID:\ ([0-9a-f]{8}) ]]; then
  ITEM_PREFIX="${BASH_REMATCH[1]}"
  pass "Create item in $SALON_SCOPE"
else
  fail "Create item in $SALON_SCOPE"
fi

# 4) Service tag filter
run_cli -s "$SALON_SCOPE" service list --tag premium
if [[ $LAST_STATUS -eq 0 && "$LAST_OUT" == *"$SERVICE_NAME"* ]]; then
  pass "Service tag filter"
else
  fail "Service tag filter"
fi

# 5) Short ID prefix resolution
if [[ -n "$ENTITY_PREFIX" && -n "$ENTITY_ID" ]]; then
  run_cli -s "$SALON_SCOPE" entity get "$ENTITY_PREFIX"
  if [[ $LAST_STATUS -eq 0 && "$LAST_OUT" == *"$ENTITY_ID"* ]]; then
    pass "Short ID resolution"
  else
    fail "Short ID resolution"
  fi
else
  FAIL_COUNT=$((FAIL_COUNT + 1))
  echo "[FAIL] Short ID resolution (entity ID not available)"
fi

# 6) Item adjust + movement date formatting
if [[ -n "$ITEM_PREFIX" ]]; then
  run_cli -s "$SALON_SCOPE" item adjust "$ITEM_PREFIX" --out 1 --reason "integration"
  if [[ $LAST_STATUS -eq 0 && "$LAST_OUT" == *"Adjusted stock"* ]]; then
    pass "Item adjust"
  else
    fail "Item adjust"
  fi

  run_cli -s "$SALON_SCOPE" item movements "$ITEM_PREFIX"
  if [[ $LAST_STATUS -eq 0 && "$LAST_OUT" =~ [0-9]{4}-[0-9]{2}-[0-9]{2} ]]; then
    pass "Item movement date formatting"
  else
    fail "Item movement date formatting"
  fi
else
  FAIL_COUNT=$((FAIL_COUNT + 2))
  echo "[FAIL] Item adjust (item ID not available)"
  echo "[FAIL] Item movement date formatting (item ID not available)"
fi

# 7) Summary by scope
run_cli summary by-scope --period month
if [[ $LAST_STATUS -ne 0 ]]; then
  if [[ "$LAST_OUT" == *"404"* || "$LAST_OUT" == *"Not Found"* ]]; then
    fail "Summary by-scope endpoint available (API likely outdated; expected /api/summary/by-scope)"
  else
    fail "Summary by-scope command"
  fi
else
  HAS_SALON=0
  HAS_HOME=0
  [[ "$LAST_OUT" == *"$SALON_SCOPE"* ]] && HAS_SALON=1
  [[ "$LAST_OUT" == *"$HOME_SCOPE"* ]] && HAS_HOME=1

  if [[ "$EXPECT_BOTH_SCOPES" == "1" ]]; then
    if [[ $HAS_SALON -eq 1 && $HAS_HOME -eq 1 ]]; then
      pass "Summary by-scope includes both scopes"
    else
      fail "Summary by-scope includes both scopes"
    fi
  else
    if [[ $HAS_SALON -eq 1 || $HAS_HOME -eq 1 ]]; then
      pass "Summary by-scope returns scope data"
    else
      fail "Summary by-scope returns scope data"
    fi
  fi
fi

# 8) Custom period trends + by-day
FROM_DATE="$(date +%Y-%m-01)"
TO_DATE="$(date +%Y-%m-%d)"

run_cli summary trends --period custom --from "$FROM_DATE" --to "$TO_DATE"
if [[ $LAST_STATUS -eq 0 ]]; then
  pass "Summary trends custom period"
else
  fail "Summary trends custom period"
fi

run_cli summary by-day --period custom --from "$FROM_DATE" --to "$TO_DATE"
if [[ $LAST_STATUS -eq 0 ]]; then
  pass "Summary by-day custom period"
else
  fail "Summary by-day custom period"
fi

# 9) Entity insights new filters
run_cli -s "$SALON_SCOPE" entity insights --created-after "$FROM_DATE" --sort name
if [[ $LAST_STATUS -eq 0 ]]; then
  pass "Entity insights --created-after"
else
  fail "Entity insights --created-after"
fi

run_cli -s "$SALON_SCOPE" entity insights --created-before "$TO_DATE" --sort name
if [[ $LAST_STATUS -eq 0 ]]; then
  pass "Entity insights --created-before"
else
  fail "Entity insights --created-before"
fi

# 10) Structured validation errors
# Primary check: invalid transaction date should 422 on current API.
run_cli -s "$SALON_SCOPE" tx add income 10 haircut --date "2026-99-99"
if [[ $LAST_STATUS -ne 0 && "$LAST_OUT" == *"Validation error"* ]]; then
  pass "Validation error rendering"
else
  # Fallback check: negative item quantity should also 422 on current API.
  run_cli -s "$SALON_SCOPE" item add "$BAD_ITEM_NAME" --qty -1
  if [[ $LAST_STATUS -ne 0 && "$LAST_OUT" == *"Validation error"* ]]; then
    pass "Validation error rendering"
  else
    fail "Validation error rendering (API may be running an older schema/validation build)"
  fi
fi

# 11) Connection error UX
run_cli_with_base "http://127.0.0.1:9999" -s "$SALON_SCOPE" summary
if [[ $LAST_STATUS -ne 0 && "$LAST_OUT" == *"Connection error"* && "$LAST_OUT" != *"Traceback"* ]]; then
  pass "Connection error rendering"
else
  fail "Connection error rendering"
fi

printf '\nSummary: %d passed, %d failed\n' "$PASS_COUNT" "$FAIL_COUNT"
if [[ $FAIL_COUNT -gt 0 ]]; then
  exit 1
fi
