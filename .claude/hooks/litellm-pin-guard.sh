#!/usr/bin/env bash
# PreToolUse(Edit|Write) guard — ask before changing the pinned LiteLLM version.
#
# CLAUDE.md hard rule #5: LiteLLM is pinned to 1.83.0 after the Mar 2026 supply-chain
# incident (malicious 1.82.7/1.82.8). Bump ONLY after changelog review + pip-audit, and
# in BOTH pyproject.toml AND the docker image tag. This hook turns that rule from guidance
# into an actual prompt: it returns permissionDecision "ask" (never a hard deny) when an
# edit would set litellm to a version other than the pin. Exits 0 with no decision otherwise.
set -uo pipefail

PIN="1.83.0"
PIN_RE="${PIN//./\\.}"

input=$(cat)
fp=$(printf '%s' "$input"   | jq -r '.tool_input.file_path // ""')
text=$(printf '%s' "$input" | jq -r '.tool_input.new_string // .tool_input.content // ""')

# Only the files that carry the pin are relevant; everything else passes through untouched.
case "$fp" in
  *pyproject.toml|*/docker/*|*docker-compose.yml|*litellm/config.yaml) ;;
  *) exit 0 ;;
esac

flagged=""
# pip pin:  litellm==<ver>   (the post-incident comment mentions 1.82.7/1.82.8 but has no '==', so it won't trip)
if printf '%s' "$text" | grep -oiE 'litellm==[0-9][0-9.]*' | grep -qvE "^litellm==${PIN_RE}$"; then
  flagged="pip pin (litellm==)"
fi
# docker image tag:  ghcr.io/berriai/litellm:main-v<ver>
if printf '%s' "$text" | grep -oiE 'litellm:main-v[0-9][0-9.]*' | grep -qvE "litellm:main-v${PIN_RE}$"; then
  flagged="${flagged:+$flagged; }docker image tag (litellm:main-v)"
fi

if [ -n "$flagged" ]; then
  jq -n --arg f "$flagged" --arg p "$PIN" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "ask",
      permissionDecisionReason: ("LiteLLM is pinned to " + $p + " (Mar 2026 supply-chain incident: malicious 1.82.7/1.82.8). This edit changes the " + $f + ". Per CLAUDE.md hard rule #5, bump ONLY after changelog review + pip-audit, and update BOTH pyproject.toml and the docker image tag together. Confirm that has been done.")
    }
  }'
  exit 0
fi

exit 0
