#!/usr/bin/env bash
set -euo pipefail

RELEASE=${ONS_RELEASE:-"73.1.1"}
ARCHIVE_URL="https://github.com/ONSdigital/design-system/releases/download/${RELEASE}/templates.zip"
TMPFILE=$(mktemp ./templates.XXXXXXXXXX)

if command -v wget >/dev/null 2>&1; then
  wget "${ARCHIVE_URL}" -O "${TMPFILE}"
else
  curl -L "${ARCHIVE_URL}" -o "${TMPFILE}"
fi
rm -rf src/theme_analysis_ui/templates/components
rm -rf src/theme_analysis_ui/templates/layout
unzip -o "${TMPFILE}" -d src/theme_analysis_ui
rm "${TMPFILE}"

echo "Downloaded ONS Design System templates for release ${RELEASE}."
