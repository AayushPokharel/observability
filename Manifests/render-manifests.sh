#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_DIR="$ROOT_DIR/templates"
RENDERED_DIR="$ROOT_DIR/rendered"

: "${STUDENT:?Set STUDENT first, for example: export STUDENT=student01}"
: "${COMPOSE_PROJECT_NAME:=observe-${STUDENT}}"
export STUDENT COMPOSE_PROJECT_NAME

rm -rf "$RENDERED_DIR"
mkdir -p "$RENDERED_DIR"

# Keep the rendered tree identical to the template tree while replacing only
# the two workshop-scoping placeholders. This avoids consuming shell syntax
# that may legitimately belong to Compose or application configuration.
while IFS= read -r -d '' src; do
  rel="${src#"$TEMPLATE_DIR/"}"
  dest="$RENDERED_DIR/$rel"
  mkdir -p "$(dirname "$dest")"
  case "$src" in
    *.yml|*.yaml|*.conf|*.tpl|*.json|*.env|*.md|*.sh|*/Dockerfile|*/requirements.txt|*.py)
      sed \
        -e "s|__STUDENT__|$STUDENT|g" \
        -e "s|__COMPOSE_PROJECT_NAME__|$COMPOSE_PROJECT_NAME|g" \
        "$src" > "$dest"
      ;;
    *)
      cp "$src" "$dest"
      ;;
  esac
done < <(find "$TEMPLATE_DIR" -type f -print0 | sort -z)

chmod +x "$RENDERED_DIR"/app/start.sh 2>/dev/null || true

echo "Rendered workshop manifests for STUDENT=$STUDENT"
echo "Compose project: $COMPOSE_PROJECT_NAME"
echo "Output: $RENDERED_DIR"
