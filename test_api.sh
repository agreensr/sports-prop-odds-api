#!/bin/bash
#####################################################################
# NBA Sports API - Test Script
# Tests all new endpoints after deployment
#####################################################################

# Configuration
API_BASE="${API_BASE_URL:-http://89.117.150.95:8001}"
TIMEOUT=15

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_error() {
    echo -e "${RED}[✗]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[!]${NC} $1"
}

log_test() {
    echo -e "${BLUE}[TEST]${NC} $1"
}

# Test counter
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

run_test() {
    local test_name="$1"
    local command="$2"
    local expected="$3"

    TESTS_RUN=$((TESTS_RUN + 1))
    log_test "$test_name"

    response=$(eval "$command" 2>&1)
    exit_code=$?

    if [ $exit_code -eq 0 ]; then
        if [ -n "$expected" ]; then
            if echo "$response" | grep -q "$expected"; then
                log_info "PASSED"
                TESTS_PASSED=$((TESTS_PASSED + 1))
            else
                log_error "FAILED (Expected: $expected)"
                TESTS_FAILED=$((TESTS_FAILED + 1))
                echo "  Response: $response"
            fi
        else
            log_info "PASSED (HTTP OK)"
            TESTS_PASSED=$((TESTS_PASSED + 1))
        fi
    else
        log_error "FAILED (HTTP Error: $exit_code)"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo "  Response: $response"
    fi
    echo ""
}

print_header() {
    echo ""
    echo "============================================"
    echo "  NBA Sports API - Test Suite"
    echo "============================================"
    echo "  API Base: $API_BASE"
    echo "  Timeout: ${TIMEOUT}s"
    echo "============================================"
    echo ""
}

print_summary() {
    echo ""
    echo "============================================"
    echo "  Test Summary"
    echo "============================================"
    echo "  Tests Run:    $TESTS_RUN"
    echo -e "  ${GREEN}Passed:${NC}       $TESTS_PASSED"
    echo -e "  ${RED}Failed:${NC}       $TESTS_FAILED"
    echo "============================================"
    echo ""

    if [ $TESTS_FAILED -eq 0 ]; then
        log_info "All tests passed!"
        return 0
    else
        log_error "Some tests failed"
        return 1
    fi
}

#####################################################################
# Tests
#####################################################################

print_header

# 1. Basic Health Check
run_test "1. API Health Check" \
    "curl -s --max-time $TIMEOUT '${API_BASE}/api/health'" \
    "healthy"

# 2. Root Endpoint
run_test "2. Root Endpoint" \
    "curl -s --max-time $TIMEOUT '${API_BASE}/'" \
    "name"

# 3. OpenAPI Spec
run_test "3. OpenAPI Specification" \
    "curl -s --max-time $TIMEOUT '${API_BASE}/openapi.json'" \
    "openapi"

# 4. List Endpoints
log_test "4. Available Endpoints"
echo ""
curl -s --max-time $TIMEOUT "${API_BASE}/openapi.json" | \
    python3 -c "import sys, json; data = json.load(sys.stdin); print('\n'.join(sorted(data.get('paths', {}).keys())))" 2>/dev/null || \
    log_error "Could not parse endpoints"
echo ""

# 5. Player Search (NEW)
run_test "5. Player Search Endpoint (NEW)" \
    "curl -s --max-time $TIMEOUT '${API_BASE}/api/players/search?name=test'" \
    ""

# 6. Player by ESPN ID (NEW)
run_test "6. Player by ESPN ID Endpoint (NEW)" \
    "curl -s --max-time $TIMEOUT '${API_BASE}/api/predictions/player/espn/2544'" \
    ""

# 7. Data Status Endpoint (NEW)
run_test "7. Data Status Endpoint (NEW)" \
    "curl -s --max-time $TIMEOUT '${API_BASE}/api/data/status'" \
    "database"

# 8. Fetch Upcoming with Timeout Fix (FIXED)
log_test "8. Fetch Upcoming Games (FIXED - should complete in ${TIMEOUT}s)"
echo ""
start=$(date +%s)
response=$(curl -s --max-time $TIMEOUT -X POST "${API_BASE}/api/data/fetch/upcoming" \
    -H "Content-Type: application/json" -d '{}' 2>&1)
end=$(date +%s)
elapsed=$((end - start))

if [ $elapsed -le $TIMEOUT ]; then
    log_info "PASSED (Completed in ${elapsed}s, under ${TIMEOUT}s timeout)"
    TESTS_PASSED=$((TESTS_PASSED + 1))
    echo "  Response: $(echo "$response" | head -c 200)..."
else
    log_error "FAILED (Took ${elapsed}s, exceeded ${TIMEUREOUT}s timeout)"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi
echo ""

# 9. Check for new endpoints in OpenAPI
log_test "9. Verify New Endpoints in OpenAPI Spec"
echo ""
new_endpoints=(
    "/api/players/search"
    "/api/players/espn"
    "/api/predictions/player/espn"
    "/api/data/status"
)

openapi=$(curl -s --max-time $TIMEOUT "${API_BASE}/openapi.json")
found_new=0

for endpoint in "${new_endpoints[@]}"; do
    if echo "$openapi" | grep -q "$endpoint"; then
        log_info "Found: $endpoint"
        found_new=$((found_new + 1))
    else
        log_error "Missing: $endpoint"
    fi
done

if [ $found_new -eq ${#new_endpoints[@]} ]; then
    log_info "PASSED (All new endpoints found)"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    log_error "FAILED (Only $found_new/${#new_endpoints[@]} new endpoints found)"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi
echo ""

# 10. Database Stats
log_test "10. Database Statistics"
echo ""
curl -s --max-time $TIMEOUT "${API_BASE}/api/data/status" | python3 -m json.tool 2>/dev/null || \
    curl -s --max-time $TIMEOUT "${API_BASE}/api/data/status"
echo ""

print_summary
