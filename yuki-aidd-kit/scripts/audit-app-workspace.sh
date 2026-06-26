#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-.}"

if [ ! -d "$ROOT" ]; then
  echo "Directory not found: $ROOT" >&2
  exit 1
fi

echo "AIDD workspace audit"
echo "root: $ROOT"
echo

echo "Top-level projects:"
find "$ROOT" -maxdepth 1 -mindepth 1 -type d -print | sort | sed "s#^$ROOT/##"
echo

echo "Manifest files:"
find "$ROOT" \
  -path '*/node_modules' -prune -o \
  -path '*/.git' -prune -o \
  -path '*/venv' -prune -o \
  -path '*/.venv' -prune -o \
  \( -name package.json -o -name pyproject.toml -o -name requirements.txt -o -name playwright.config.ts -o -name playwright.config.js -o -name tsconfig.json -o -name Package.swift -o -name go.mod \) \
  -print | sort
echo

echo "Extension counts:"
if command -v rg >/dev/null 2>&1; then
  rg --files "$ROOT" \
    -g '!node_modules' -g '!.git' -g '!dist' -g '!build' -g '!coverage' \
    -g '!.next' -g '!.turbo' -g '!venv' -g '!.venv' -g '!__pycache__' \
    -g '!test-results' -g '!output' -g '!*.zip' -g '!*.gz' -g '!*.db' \
    | awk 'match($0,/\.[^.\/]+$/){ext=substr($0,RSTART); count[ext]++} END{for(e in count) print count[e], e}' \
    | sort -nr | head -40
else
  find "$ROOT" -type f | sed 's/.*//' | sort | uniq -c | sort -nr | head -40
fi
echo

echo "Recommended ECC DAILY baseline:"
echo "- skills/e2e-testing"
echo "- skills/browser-qa"
echo "- skills/accessibility"
echo "- skills/frontend-patterns"
echo "- skills/react-patterns"
echo "- skills/vite-patterns"
echo "- skills/python-patterns"
echo "- skills/python-testing"
echo "- skills/django-patterns"
echo "- skills/security-review"
echo "- skills/verification-loop"
echo "- skills/deep-research"
echo "- skills/eval-harness"
