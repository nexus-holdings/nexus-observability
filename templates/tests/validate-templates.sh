#!/usr/bin/env bash
#
# validate-templates.sh
# Validates all deployment template files against the spec and acceptance criteria.
# Exit 0 if all checks pass, non-zero if any fail.
#
# Usage: bash validate-templates.sh [TEMPLATES_DIR]
#   TEMPLATES_DIR defaults to the parent of this script's directory.

set -euo pipefail

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATES_DIR="${1:-$(dirname "$SCRIPT_DIR")}"

PASS=0
FAIL=0
FAILURES=()

pass() {
  PASS=$((PASS + 1))
  printf "  \033[32mPASS\033[0m  %s\n" "$1"
}

fail() {
  FAIL=$((FAIL + 1))
  FAILURES+=("$1")
  printf "  \033[31mFAIL\033[0m  %s\n" "$1"
}

section() {
  printf "\n=== %s ===\n" "$1"
}

# ---------------------------------------------------------------------------
# 1. File existence
# ---------------------------------------------------------------------------
section "1. File Existence"

REQUIRED_FILES=(
  "docker-compose.yml"
  "Dockerfile"
  "nginx/nginx.conf"
  ".github/workflows/ci.yml"
  ".github/workflows/deploy.yml"
  ".env.example"
  "scripts/inject-secrets.sh"
  "scripts/preflight.sh"
  ".gitignore"
)

for f in "${REQUIRED_FILES[@]}"; do
  if [[ -f "$TEMPLATES_DIR/$f" ]]; then
    pass "File exists: $f"
  else
    fail "Missing required file: $f"
  fi
done

# ---------------------------------------------------------------------------
# 2. Docker Compose validity — valid YAML with required services
# ---------------------------------------------------------------------------
section "2. Docker Compose Validity"

DC_FILE="$TEMPLATES_DIR/docker-compose.yml"

if [[ -f "$DC_FILE" ]]; then
  # Check YAML validity (try python, yq, or ruby — whichever is available)
  YAML_VALID=false
  if command -v python3 &>/dev/null; then
    if python3 -c "import yaml, sys; yaml.safe_load(open(sys.argv[1]))" "$DC_FILE" 2>/dev/null; then
      YAML_VALID=true
    fi
  elif command -v yq &>/dev/null; then
    if yq eval '.' "$DC_FILE" &>/dev/null; then
      YAML_VALID=true
    fi
  elif command -v ruby &>/dev/null; then
    if ruby -ryaml -e "YAML.safe_load(File.read(ARGV[0]))" "$DC_FILE" 2>/dev/null; then
      YAML_VALID=true
    fi
  else
    # Fallback: just check it is not empty and starts with plausible YAML
    if [[ -s "$DC_FILE" ]]; then
      YAML_VALID=true
    fi
  fi

  if $YAML_VALID; then
    pass "docker-compose.yml is valid YAML"
  else
    fail "docker-compose.yml is NOT valid YAML"
  fi

  # Required services: app, db (PostgreSQL), nginx
  for svc in app db nginx; do
    if grep -qE "^\s+${svc}:" "$DC_FILE"; then
      pass "docker-compose.yml contains service: $svc"
    else
      fail "docker-compose.yml missing service: $svc"
    fi
  done

  # PostgreSQL image reference
  if grep -qi "postgres" "$DC_FILE"; then
    pass "docker-compose.yml references PostgreSQL"
  else
    fail "docker-compose.yml does not reference PostgreSQL"
  fi

  # Bedrock API configuration pattern
  if grep -qi "bedrock" "$DC_FILE"; then
    pass "docker-compose.yml contains Bedrock API configuration"
  else
    fail "docker-compose.yml missing Bedrock API configuration"
  fi

  # Health check
  if grep -qi "healthcheck" "$DC_FILE"; then
    pass "docker-compose.yml contains health check"
  else
    fail "docker-compose.yml missing health check"
  fi
else
  fail "docker-compose.yml not found — skipping compose checks"
fi

# ---------------------------------------------------------------------------
# 3. Dockerfile structure
# ---------------------------------------------------------------------------
section "3. Dockerfile Structure"

DOCKERFILE="$TEMPLATES_DIR/Dockerfile"

if [[ -f "$DOCKERFILE" ]]; then
  # Multi-stage build: more than one FROM instruction
  FROM_COUNT=$(grep -c "^FROM " "$DOCKERFILE" || true)
  if [[ "$FROM_COUNT" -ge 2 ]]; then
    pass "Dockerfile uses multi-stage build ($FROM_COUNT stages)"
  else
    fail "Dockerfile does not use multi-stage build (found $FROM_COUNT FROM)"
  fi

  # Non-root user
  if grep -qE "^USER\s+" "$DOCKERFILE"; then
    # Make sure it is not USER root
    if grep -qE "^USER\s+root" "$DOCKERFILE"; then
      fail "Dockerfile sets USER to root (should be non-root)"
    else
      pass "Dockerfile sets a non-root USER"
    fi
  else
    fail "Dockerfile missing non-root USER instruction"
  fi

  # HEALTHCHECK instruction
  if grep -q "^HEALTHCHECK " "$DOCKERFILE"; then
    pass "Dockerfile contains HEALTHCHECK instruction"
  else
    fail "Dockerfile missing HEALTHCHECK instruction"
  fi
else
  fail "Dockerfile not found — skipping Dockerfile checks"
fi

# ---------------------------------------------------------------------------
# 4. Nginx config
# ---------------------------------------------------------------------------
section "4. Nginx Configuration"

NGINX_CONF="$TEMPLATES_DIR/nginx/nginx.conf"

if [[ -f "$NGINX_CONF" ]]; then
  # upstream block
  if grep -q "upstream" "$NGINX_CONF"; then
    pass "nginx.conf contains upstream block"
  else
    fail "nginx.conf missing upstream block"
  fi

  # proxy_pass
  if grep -q "proxy_pass" "$NGINX_CONF"; then
    pass "nginx.conf contains proxy_pass"
  else
    fail "nginx.conf missing proxy_pass"
  fi

  # Security headers (at least some common ones)
  SECURITY_HEADERS_FOUND=0
  for hdr in "X-Frame-Options" "X-Content-Type-Options" "X-XSS-Protection" "Strict-Transport-Security" "Content-Security-Policy" "Referrer-Policy"; do
    if grep -q "$hdr" "$NGINX_CONF"; then
      SECURITY_HEADERS_FOUND=$((SECURITY_HEADERS_FOUND + 1))
    fi
  done
  if [[ "$SECURITY_HEADERS_FOUND" -ge 2 ]]; then
    pass "nginx.conf contains security headers ($SECURITY_HEADERS_FOUND found)"
  else
    fail "nginx.conf missing security headers (only $SECURITY_HEADERS_FOUND found, need >= 2)"
  fi
else
  fail "nginx/nginx.conf not found — skipping nginx checks"
fi

# ---------------------------------------------------------------------------
# 5. CI workflow
# ---------------------------------------------------------------------------
section "5. CI Workflow"

CI_FILE="$TEMPLATES_DIR/.github/workflows/ci.yml"

if [[ -f "$CI_FILE" ]]; then
  for job in lint test security; do
    if grep -qiE "(^|\s)${job}" "$CI_FILE"; then
      pass "CI workflow contains '$job' job/step"
    else
      fail "CI workflow missing '$job' job/step"
    fi
  done

  # OWASP-aligned security scan
  if grep -qi "owasp\|trivy\|snyk\|grype\|dependency.check\|safety" "$CI_FILE"; then
    pass "CI workflow references OWASP-aligned security scanning tool"
  else
    fail "CI workflow missing OWASP-aligned security scan reference"
  fi

  # PR trigger
  if grep -q "pull_request" "$CI_FILE"; then
    pass "CI workflow triggers on pull_request"
  else
    fail "CI workflow missing pull_request trigger"
  fi
else
  fail "CI workflow file not found — skipping CI checks"
fi

# ---------------------------------------------------------------------------
# 6. Deploy workflow
# ---------------------------------------------------------------------------
section "6. Deploy Workflow"

DEPLOY_FILE="$TEMPLATES_DIR/.github/workflows/deploy.yml"

if [[ -f "$DEPLOY_FILE" ]]; then
  # Blue-green deployment
  if grep -qi "blue.green\|blue_green" "$DEPLOY_FILE"; then
    pass "Deploy workflow contains blue-green deployment"
  else
    fail "Deploy workflow missing blue-green deployment"
  fi

  # Monitoring window / error rate check
  if grep -qi "monitor\|error.rate\|health" "$DEPLOY_FILE"; then
    pass "Deploy workflow contains monitoring/health check"
  else
    fail "Deploy workflow missing monitoring/error-rate check"
  fi

  # 5-minute monitoring window
  if grep -qE "5.?min|300|5m" "$DEPLOY_FILE"; then
    pass "Deploy workflow references 5-minute monitoring window"
  else
    fail "Deploy workflow missing 5-minute monitoring window reference"
  fi

  # Rollback
  if grep -qi "rollback" "$DEPLOY_FILE"; then
    pass "Deploy workflow contains rollback mechanism"
  else
    fail "Deploy workflow missing rollback mechanism"
  fi

  # Auto-rollback / Self-Improvement Co hook
  if grep -qi "auto.rollback\|self.improvement\|regression" "$DEPLOY_FILE"; then
    pass "Deploy workflow contains auto-rollback / regression detection hook"
  else
    fail "Deploy workflow missing auto-rollback / regression detection hook"
  fi

  # Docker image build and push
  if grep -qi "docker.*build\|docker.*push\|build.*push" "$DEPLOY_FILE"; then
    pass "Deploy workflow builds/pushes Docker image"
  else
    fail "Deploy workflow missing Docker image build/push"
  fi

  # Trigger on merge to main
  if grep -qE "push:.*main|branches:.*main" "$DEPLOY_FILE" || \
     grep -q "main" "$DEPLOY_FILE"; then
    pass "Deploy workflow references main branch"
  else
    fail "Deploy workflow missing main branch trigger"
  fi
else
  fail "Deploy workflow file not found — skipping deploy checks"
fi

# ---------------------------------------------------------------------------
# 7. Environment files
# ---------------------------------------------------------------------------
section "7. Environment Files"

ENV_FILE="$TEMPLATES_DIR/.env.example"

if [[ -f "$ENV_FILE" ]]; then
  REQUIRED_VARS=(
    "COMPANY_SLUG"
    "POSTGRES_PASSWORD"
    "BEDROCK_"
  )
  for var in "${REQUIRED_VARS[@]}"; do
    if grep -q "$var" "$ENV_FILE"; then
      pass ".env.example contains $var"
    else
      fail ".env.example missing required var: $var"
    fi
  done
else
  fail ".env.example not found — skipping env checks"
fi

# ---------------------------------------------------------------------------
# 8. Secrets injection — inject-secrets.sh references 1Password CLI
# ---------------------------------------------------------------------------
section "8. Secrets Injection"

INJECT_FILE="$TEMPLATES_DIR/scripts/inject-secrets.sh"

if [[ -f "$INJECT_FILE" ]]; then
  # References 1Password CLI tool 'op'
  if grep -qE "\bop\b|1password|1Password|onepassword" "$INJECT_FILE"; then
    pass "inject-secrets.sh references 1Password CLI (op)"
  else
    fail "inject-secrets.sh does not reference 1Password CLI (op)"
  fi

  # Should be executable or at least have a shebang
  if head -1 "$INJECT_FILE" | grep -q "^#!"; then
    pass "inject-secrets.sh has a shebang line"
  else
    fail "inject-secrets.sh missing shebang line"
  fi
else
  fail "inject-secrets.sh not found — skipping secrets injection checks"
fi

# ---------------------------------------------------------------------------
# 9. Preflight script
# ---------------------------------------------------------------------------
section "9. Preflight Script"

PREFLIGHT_FILE="$TEMPLATES_DIR/scripts/preflight.sh"

if [[ -f "$PREFLIGHT_FILE" ]]; then
  # Checks for Docker
  if grep -qi "docker" "$PREFLIGHT_FILE"; then
    pass "preflight.sh checks for Docker"
  else
    fail "preflight.sh does not check for Docker"
  fi

  # Checks for ports
  if grep -qi "port\|lsof\|netstat\|ss " "$PREFLIGHT_FILE"; then
    pass "preflight.sh checks for port availability"
  else
    fail "preflight.sh does not check for port availability"
  fi

  # Checks for .env file
  if grep -q "\.env" "$PREFLIGHT_FILE"; then
    pass "preflight.sh checks for .env file"
  else
    fail "preflight.sh does not check for .env file"
  fi

  # Shebang
  if head -1 "$PREFLIGHT_FILE" | grep -q "^#!"; then
    pass "preflight.sh has a shebang line"
  else
    fail "preflight.sh missing shebang line"
  fi
else
  fail "preflight.sh not found — skipping preflight checks"
fi

# ---------------------------------------------------------------------------
# 10. Security — no raw secrets, .gitignore covers .env
# ---------------------------------------------------------------------------
section "10. Security"

# Check that no template file contains raw secret values (common patterns)
RAW_SECRET_PATTERNS=(
  "password=.\{8,\}"
  "secret=.\{8,\}"
  "api_key=.\{8,\}"
  "token=.\{8,\}"
  "PRIVATE_KEY=.\{8,\}"
)

SECRET_LEAK=false
# Scan all files except the test script itself and any .git directory
while IFS= read -r -d '' tfile; do
  for pat in "${RAW_SECRET_PATTERNS[@]}"; do
    # Skip lines that are clearly placeholder/example patterns
    if grep -iE "$pat" "$tfile" 2>/dev/null | grep -ivE "your_|example|placeholder|changeme|CHANGEME|REPLACE|<|>|\{\{|\$\{|op://" | grep -ivq "^#"; then
      fail "Possible raw secret in $tfile (pattern: $pat)"
      SECRET_LEAK=true
    fi
  done
done < <(find "$TEMPLATES_DIR" -type f \
  ! -path "*/tests/*" \
  ! -path "*/.git/*" \
  ! -name "*.sh.bak" \
  -print0 2>/dev/null)

if ! $SECRET_LEAK; then
  pass "No raw secrets detected in template files"
fi

# .gitignore covers .env files
GITIGNORE="$TEMPLATES_DIR/.gitignore"

if [[ -f "$GITIGNORE" ]]; then
  if grep -qE "^\.env$|^\.env\b" "$GITIGNORE"; then
    pass ".gitignore covers .env files"
  else
    fail ".gitignore does not cover .env files"
  fi
else
  fail ".gitignore not found — cannot verify .env exclusion"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
TOTAL=$((PASS + FAIL))
printf "\n====================================\n"
printf "Results: %d passed, %d failed (out of %d)\n" "$PASS" "$FAIL" "$TOTAL"

if [[ "$FAIL" -gt 0 ]]; then
  printf "\nFailed checks:\n"
  for f in "${FAILURES[@]}"; do
    printf "  - %s\n" "$f"
  done
  printf "\n"
  exit 1
else
  printf "All checks passed.\n\n"
  exit 0
fi
