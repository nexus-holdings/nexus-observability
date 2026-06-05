#!/usr/bin/env bash
# Nexus Holdings — Pre-flight Health Check
# Run before `docker compose up` to validate the environment is ready.
#
# Usage: ./scripts/preflight.sh
# Exit code 0 = all checks passed, non-zero = failure with details.

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
FAIL=0
WARN=0

pass()  { ((PASS++)); echo -e "  ${GREEN}✓${NC} $1"; }
fail()  { ((FAIL++)); echo -e "  ${RED}✗${NC} $1"; }
warn()  { ((WARN++)); echo -e "  ${YELLOW}⚠${NC} $1"; }

echo ""
echo "═══════════════════════════════════════════════════"
echo "  Nexus Holdings — Pre-flight Check"
echo "═══════════════════════════════════════════════════"
echo ""

# ── 1. Required tools ───────────────────────────────────────
echo "Checking required tools..."

if command -v docker &>/dev/null; then
  DOCKER_VERSION=$(docker --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
  pass "Docker installed (v${DOCKER_VERSION})"
else
  fail "Docker is not installed"
fi

if docker compose version &>/dev/null; then
  COMPOSE_VERSION=$(docker compose version --short 2>/dev/null || echo "unknown")
  pass "Docker Compose available (v${COMPOSE_VERSION})"
else
  fail "Docker Compose is not available"
fi

if command -v curl &>/dev/null; then
  pass "curl installed"
else
  warn "curl not installed — health checks will not work"
fi

# ── 2. Docker daemon ────────────────────────────────────────
echo ""
echo "Checking Docker daemon..."

if docker info &>/dev/null; then
  pass "Docker daemon is running"
else
  fail "Docker daemon is not running — start Docker Desktop or dockerd"
fi

# ── 3. Environment file ─────────────────────────────────────
echo ""
echo "Checking environment configuration..."

if [ -f .env ]; then
  pass ".env file exists"
else
  if [ -f .env.example ]; then
    fail ".env file missing — copy from .env.example: cp .env.example .env"
  else
    fail ".env file missing — no .env.example found either"
  fi
fi

# ── 4. Required environment variables ───────────────────────
echo ""
echo "Checking required environment variables..."

REQUIRED_VARS=(
  "COMPANY_SLUG"
  "POSTGRES_PASSWORD"
)

if [ -f .env ]; then
  for var in "${REQUIRED_VARS[@]}"; do
    if grep -q "^${var}=" .env && [ -n "$(grep "^${var}=" .env | cut -d= -f2-)" ]; then
      pass "${var} is set"
    else
      fail "${var} is missing or empty in .env"
    fi
  done
else
  for var in "${REQUIRED_VARS[@]}"; do
    fail "${var} — cannot check (.env missing)"
  done
fi

# ── 5. Port availability ────────────────────────────────────
echo ""
echo "Checking port availability..."

check_port() {
  local port=$1
  local service=$2
  if ! lsof -i ":${port}" &>/dev/null; then
    pass "Port ${port} is available (${service})"
  else
    fail "Port ${port} is in use (needed for ${service})"
  fi
}

# Source .env for port values if available
if [ -f .env ]; then
  # shellcheck disable=SC1091
  source .env 2>/dev/null || true
fi

check_port "${NGINX_HTTP_PORT:-80}" "Nginx HTTP"
check_port "${NGINX_HTTPS_PORT:-443}" "Nginx HTTPS"
check_port "${DB_PORT:-5432}" "PostgreSQL"

# ── 6. Disk space ───────────────────────────────────────────
echo ""
echo "Checking disk space..."

AVAILABLE_KB=$(df -k . | tail -1 | awk '{print $4}')
AVAILABLE_GB=$((AVAILABLE_KB / 1024 / 1024))

if [ "${AVAILABLE_GB}" -ge 5 ]; then
  pass "Disk space: ${AVAILABLE_GB}GB available"
elif [ "${AVAILABLE_GB}" -ge 2 ]; then
  warn "Disk space low: ${AVAILABLE_GB}GB available (recommend 5GB+)"
else
  fail "Disk space critical: ${AVAILABLE_GB}GB available (need at least 2GB)"
fi

# ── 7. Docker image pull test ────────────────────────────────
echo ""
echo "Checking Docker image access..."

if docker pull postgres:16-alpine &>/dev/null; then
  pass "Can pull PostgreSQL image"
else
  warn "Cannot pull PostgreSQL image — may work if cached locally"
fi

# ── Summary ─────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════"
echo -e "  Results: ${GREEN}${PASS} passed${NC}  ${RED}${FAIL} failed${NC}  ${YELLOW}${WARN} warnings${NC}"
echo "═══════════════════════════════════════════════════"
echo ""

if [ "${FAIL}" -gt 0 ]; then
  echo -e "${RED}Pre-flight check FAILED. Fix the issues above before deploying.${NC}"
  exit 1
else
  echo -e "${GREEN}Pre-flight check PASSED. Ready to deploy!${NC}"
  echo ""
  echo "  Next: docker compose up -d"
  echo ""
  exit 0
fi
