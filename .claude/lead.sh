#!/usr/bin/env bash
# Start the bankside lead session, the one that dispatches the role agents.
#
# Everything gh and git do from this session, and from the agents it spawns,
# runs on the agent token (bankside only), never on the user's own login or
# SSH key:
# - GH_TOKEN points gh at the agent token;
# - git reaches GitHub over HTTPS, with gh as its credential helper, so pushes
#   use the same token;
# - SSH is disabled for git, so the user's key (which reaches every repo) is
#   never used.
# BANKSIDE_AGENT_SESSION tells .claude/hooks/guard.py that this was done.
#
# Usage: .claude/lead.sh [claude options]
# The token file can be overridden with BANKSIDE_AGENT_TOKEN_FILE.
set -euo pipefail

token_file="${BANKSIDE_AGENT_TOKEN_FILE:-$HOME/.config/bankside/agent-gh-token}"
if [[ ! -r "$token_file" ]]; then
  echo "lead.sh: can't read the agent token at $token_file" >&2
  exit 1
fi

GH_TOKEN="$(tr -d '[:space:]' <"$token_file")"
export GH_TOKEN
unset GITHUB_TOKEN SSH_AUTH_SOCK

export GIT_SSH_COMMAND=false
export GIT_TERMINAL_PROMPT=0
export GIT_CONFIG_COUNT=3
export GIT_CONFIG_KEY_0=url.https://github.com/.insteadOf
export GIT_CONFIG_VALUE_0=git@github.com:
# An empty helper first clears any helper from the user's own git config.
export GIT_CONFIG_KEY_1=credential.https://github.com.helper
export GIT_CONFIG_VALUE_1=
export GIT_CONFIG_KEY_2=credential.https://github.com.helper
export GIT_CONFIG_VALUE_2='!gh auth git-credential'

export BANKSIDE_AGENT_SESSION=1

cd "$(dirname "$(realpath "$0")")/.."
exec claude "$@"
