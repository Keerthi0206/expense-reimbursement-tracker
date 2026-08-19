#!/usr/bin/env bash
# Post-deploy smoke test. Run this after any deploy to Render/Vercel to
# confirm the live site actually works, not just that the build succeeded.
#
# Usage: ./validate-deployment.sh <backend_url> <frontend_url>
# Example: ./validate-deployment.sh https://expense-reimbursement-tracker.onrender.com https://expense-reimbursement-tracker-three.vercel.app

set -uo pipefail

BACKEND_URL="${1:?Usage: $0 <backend_url> <frontend_url>}"
FRONTEND_URL="${2:?Usage: $0 <backend_url> <frontend_url>}"
FAILURES=0

pass() { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1"; FAILURES=$((FAILURES + 1)); }

echo "Validating deployment"
echo "  Backend:  $BACKEND_URL"
echo "  Frontend: $FRONTEND_URL"
echo ""

# 1. Backend health check -- confirms the server is up AND the database is
# actually reachable, not just that the process started.
echo "1. Backend health check"
health_response=$(curl -sf "$BACKEND_URL/api/health" 2>/dev/null)
if [ -z "$health_response" ]; then
    fail "backend did not respond at /api/health"
else
    if echo "$health_response" | grep -q '"status":"ok"'; then
        pass "backend responded with status ok"
    else
        fail "backend responded but status was not ok: $health_response"
    fi
    if echo "$health_response" | grep -q '"database":"connected"'; then
        pass "database reports connected"
    else
        fail "database did not report connected: $health_response"
    fi
fi
echo ""

# 2. Real login against a seeded demo account -- confirms auth, the
# database has real data (not empty), and JWT issuing all work together.
echo "2. Login with a seeded demo account"
login_response=$(curl -sf -X POST "$BACKEND_URL/api/auth/login" \
    -H "Content-Type: application/json" \
    -H "Origin: $FRONTEND_URL" \
    -d '{"email":"rachel@example.com","password":"password123"}' 2>/dev/null)
if echo "$login_response" | grep -q '"access_token"'; then
    pass "login succeeded, received a real access token"
else
    fail "login did not return an access token: $login_response"
fi
echo ""

# 3. CORS -- confirms the backend actually allows the real frontend's
# origin, not just that it responds to a bare curl with no Origin header.
echo "3. CORS allows the frontend's origin"
cors_header=$(curl -sf -I -X OPTIONS "$BACKEND_URL/api/auth/login" \
    -H "Origin: $FRONTEND_URL" \
    -H "Access-Control-Request-Method: POST" 2>/dev/null | grep -i "access-control-allow-origin")
if [ -n "$cors_header" ]; then
    pass "CORS preflight allowed the frontend origin"
else
    fail "CORS preflight did not return an Access-Control-Allow-Origin header"
fi
echo ""

# 4. Frontend loads and shows expected content -- confirms the build
# actually deployed the right app, not a blank page or an error screen.
echo "4. Frontend serves the login page"
frontend_html=$(curl -sf "$FRONTEND_URL/login" 2>/dev/null)
if echo "$frontend_html" | grep -qi "sign in"; then
    pass "frontend login page loaded with expected content"
else
    fail "frontend did not return expected login page content"
fi
echo ""

echo "----------------------------------------"
if [ "$FAILURES" -eq 0 ]; then
    echo "All checks passed."
    exit 0
else
    echo "$FAILURES check(s) failed."
    exit 1
fi
