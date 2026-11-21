#!/usr/bin/env python3
"""bankside guard: a PreToolUse hook for the role agents.

Claude Code runs it before every Write, Edit, NotebookEdit and Bash call. It
only restricts subagents (the hook input carries their `agent_type`); the
user's own session, with no `agent_type`, passes through.

- Writes: an agent may write only the paths its role owns (the ownership table
  in CLAUDE.md), plus scratch files in the temp dir. Nobody but the user
  writes .claude/, CLAUDE.md, src/common/util/ or .git/. An agent type not in
  the table writes nothing in the repo.
- Bash: the commands no agent may run (gh api, merges, force pushes, ...), and
  any gh or git push outside a session started by .claude/lead.sh, which is
  what points them at the agent token instead of the user's login.

Bash checks are best-effort: a determined command can hide what it does. The
real boundaries are the agent token and the ruleset on main.

Exit 2 blocks the call; stderr is shown to the agent.
"""
import json
import os
import re
import sys
import tempfile

OWNED = {
    "architect": ["src/*/doc/**"],
    "designer": ["src/*/rtl/**", "src/*/syn/**"],
    "dv": ["src/*/dv/**", "src/*/opendv.yaml", ".github/workflows/**"],
    "pm": ["pm/**", "README.md", ".github/ISSUE_TEMPLATE/**",
           ".github/pull_request_template.md"],
}
USER_ONLY = [".claude/**", "CLAUDE.md", "src/common/util/**", ".git/**"]

# Commands no agent runs (CLAUDE.md, Rules). Matched anywhere in the command,
# so `cd x && gh api ...` is caught too.
FORBIDDEN = [
    (r"\bgh\s+(api|auth|repo|ssh-key|gpg-key|secret|variable|gist|release|"
     r"extension|alias)\b", "this gh command is reserved for the user"),
    (r"\bgh\s+pr\s+merge\b", "merging is the user's"),
    (r"\bgh\s+(issue|label)\s+(delete|transfer)\b", "deleting is the user's"),
    (r"\bgit\s+push\b.*(\s-f\b|--force|\s\+\S)", "no force pushes"),
    (r"\bgit\s+push\b.*\s(main|HEAD:main|\S+:main)\s*($|[;&|])",
     "never push to main: open a PR"),
    (r"GIT_SSH|sshCommand|SSH_AUTH_SOCK|\bssh\s|credential\.helper|"
     r"insteadOf|\bGH_TOKEN\b|\bGITHUB_TOKEN\b|agent-gh-token",
     "don't touch git or gh credentials"),
]
NEEDS_AGENT_TOKEN = r"\bgh\s|\bgit\s+(push|fetch|pull|ls-remote)\b"


def glob_re(pattern):
    """`**` matches across folders, `*` within one."""
    out = re.escape(pattern).replace(r"\*\*", "\0").replace(r"\*", "[^/]*")
    return re.compile(out.replace("\0", ".*") + r"\Z")


def matches(rel, patterns):
    return any(glob_re(p).match(rel) for p in patterns)


def block(msg):
    print(f"bankside guard: {msg}", file=sys.stderr)
    sys.exit(2)


def check_write(role, path, cwd, root):
    full = os.path.realpath(os.path.join(cwd, os.path.expanduser(path)))
    tmp = os.path.realpath(tempfile.gettempdir())
    if full == root or full.startswith(root + os.sep):
        rel = os.path.relpath(full, root)
        if matches(rel, USER_ONLY):
            block(f"{rel} is the user's only. File an issue instead.")
        if not matches(rel, OWNED.get(role, [])):
            if role not in OWNED:
                block(f"agent type '{role}' writes nothing in the repo.")
            block(f"{rel} isn't owned by the {role} (see Ownership in "
                  "CLAUDE.md). File an issue for its owner instead.")
    elif not (full == tmp or full.startswith(tmp + os.sep)):
        block(f"{full} is outside the repo; use {tmp}/ for scratch files.")


def check_bash(cmd):
    for pattern, why in FORBIDDEN:
        if re.search(pattern, cmd):
            block(f"{why}. Refused: {cmd}")
    if re.search(NEEDS_AGENT_TOKEN, cmd) and not os.environ.get(
            "BANKSIDE_AGENT_SESSION"):
        block("this session wasn't started with .claude/lead.sh, so gh and "
              "git would use the user's login, not the agent token. Stop and "
              "report this to the lead.")


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        block("couldn't read the hook input")
    role = data.get("agent_type")
    if not role:
        return  # the user's own session
    tool = data.get("tool_name", "")
    args = data.get("tool_input") or {}
    root = os.path.realpath(os.environ.get("CLAUDE_PROJECT_DIR")
                            or data.get("cwd") or os.getcwd())
    cwd = data.get("cwd") or root
    if tool == "Bash":
        check_bash(args.get("command", ""))
    elif tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        path = args.get("file_path") or args.get("notebook_path")
        if not path:
            block(f"{tool} without a path")
        check_write(role, path, cwd, root)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:  # fail closed for agents
        block(f"internal error, call refused: {e!r}")
