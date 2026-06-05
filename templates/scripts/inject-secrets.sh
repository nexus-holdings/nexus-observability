#!/usr/bin/env bash
# Nexus Holdings — 1Password CLI Secret Injection
# Injects secrets from 1Password into the environment WITHOUT exposing raw values.
#
# Prerequisites:
#   - 1Password CLI (op) installed: https://developer.1password.com/docs/cli/
#   - Signed in: eval $(op signin)
#   - Vault "Nexus" exists with required items
#
# Usage:
#   source ./scripts/inject-secrets.sh          # Export to current shell
#   ./scripts/inject-secrets.sh --docker-env    # Generate Docker --env-file
#   ./scripts/inject-secrets.sh --verify        # Verify all secrets accessible
#
# Agents never see raw secrets — 1Password CLI resolves references at runtime.

set -euo pipefail

VAULT="${OP_VAULT:-Nexus}"
COMPANY_SLUG="${COMPANY_SLUG:-default}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# ── Secret Mappings ──────────────────────────────────────────
# Format: ENV_VAR_NAME:op://Vault/Item/Field
declare -A SECRETS=(
  ["POSTGRES_PASSWORD"]="op://${VAULT}/${COMPANY_SLUG}-db/password"
  ["AWS_ACCESS_KEY_ID"]="op://${VAULT}/aws-bedrock/access-key-id"
  ["AWS_SECRET_ACCESS_KEY"]="op://${VAULT}/aws-bedrock/secret-access-key"
  ["SESSION_SECRET"]="op://${VAULT}/${COMPANY_SLUG}/session-secret"
  ["STRIPE_SECRET_KEY"]="op://${VAULT}/${COMPANY_SLUG}-stripe/secret-key"
  ["STRIPE_WEBHOOK_SECRET"]="op://${VAULT}/${COMPANY_SLUG}-stripe/webhook-secret"
  ["INTERNAL_API_KEY"]="op://${VAULT}/${COMPANY_SLUG}/internal-api-key"
  ["WEBHOOK_SIGNING_SECRET"]="op://${VAULT}/${COMPANY_SLUG}/webhook-signing-secret"
  ["SELF_IMPROVEMENT_TOKEN"]="op://${VAULT}/self-improvement/api-token"
)

# ── Functions ────────────────────────────────────────────────

check_op_cli() {
  if ! command -v op &>/dev/null; then
    echo -e "${RED}Error: 1Password CLI (op) is not installed.${NC}"
    echo "Install: https://developer.1password.com/docs/cli/get-started/"
    exit 1
  fi

  if ! op account list &>/dev/null 2>&1; then
    echo -e "${RED}Error: Not signed in to 1Password CLI.${NC}"
    echo "Run: eval \$(op signin)"
    exit 1
  fi
}

inject_to_env() {
  echo -e "${GREEN}Injecting secrets from 1Password vault '${VAULT}'...${NC}"
  echo ""

  local injected=0
  local skipped=0

  for var_name in "${!SECRETS[@]}"; do
    local op_ref="${SECRETS[$var_name]}"

    # Only inject if the variable is referenced in .env or expected
    if op read "${op_ref}" &>/dev/null 2>&1; then
      export "${var_name}"="$(op read "${op_ref}")"
      echo -e "  ${GREEN}✓${NC} ${var_name}"
      ((injected++))
    else
      echo -e "  ${YELLOW}⚠${NC} ${var_name} — not found at ${op_ref} (skipped)"
      ((skipped++))
    fi
  done

  echo ""
  echo -e "Injected: ${GREEN}${injected}${NC}  Skipped: ${YELLOW}${skipped}${NC}"
}

generate_docker_env() {
  echo -e "${GREEN}Generating Docker env file with 1Password references...${NC}"

  local output_file=".env.secrets"

  : > "${output_file}"

  for var_name in "${!SECRETS[@]}"; do
    local op_ref="${SECRETS[$var_name]}"
    if op read "${op_ref}" &>/dev/null 2>&1; then
      echo "${var_name}=$(op read "${op_ref}")" >> "${output_file}"
      echo -e "  ${GREEN}✓${NC} ${var_name}"
    fi
  done

  echo ""
  echo -e "Written to ${GREEN}${output_file}${NC}"
  echo "Usage: docker compose --env-file .env --env-file .env.secrets up -d"
  echo ""
  echo -e "${YELLOW}Warning: .env.secrets contains resolved secrets.${NC}"
  echo "It will be automatically deleted after docker compose starts."
  echo "Ensure .env.secrets is in .gitignore."
}

verify_secrets() {
  echo -e "${GREEN}Verifying 1Password secret access...${NC}"
  echo ""

  local accessible=0
  local missing=0

  for var_name in "${!SECRETS[@]}"; do
    local op_ref="${SECRETS[$var_name]}"
    if op read "${op_ref}" &>/dev/null 2>&1; then
      echo -e "  ${GREEN}✓${NC} ${var_name} — accessible"
      ((accessible++))
    else
      echo -e "  ${RED}✗${NC} ${var_name} — NOT accessible at ${op_ref}"
      ((missing++))
    fi
  done

  echo ""
  echo -e "Accessible: ${GREEN}${accessible}${NC}  Missing: ${RED}${missing}${NC}"

  if [ "${missing}" -gt 0 ]; then
    echo ""
    echo -e "${YELLOW}To create missing items:${NC}"
    echo "  op item create --vault '${VAULT}' --category login --title 'item-name'"
    exit 1
  fi
}

# ── Main ─────────────────────────────────────────────────────

check_op_cli

case "${1:-}" in
  --docker-env)
    generate_docker_env
    ;;
  --verify)
    verify_secrets
    ;;
  --help|-h)
    echo "Usage: ./scripts/inject-secrets.sh [OPTION]"
    echo ""
    echo "Options:"
    echo "  (none)         Export secrets to current shell environment"
    echo "  --docker-env   Generate .env.secrets file for Docker"
    echo "  --verify       Verify all secrets are accessible in 1Password"
    echo "  --help         Show this help message"
    echo ""
    echo "Environment:"
    echo "  OP_VAULT         1Password vault name (default: Nexus)"
    echo "  COMPANY_SLUG     Company identifier for secret lookups"
    ;;
  *)
    inject_to_env
    ;;
esac
