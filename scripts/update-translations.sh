#!/usr/bin/env bash
# FIBR-0017 — refresh finbreak's translation catalogs from the source.
#
#   update-translations.sh [<lang> …]
#
# Extracts every tr()/translate() string from the tracked src/finbreak/*.py into
# each src/finbreak/data/i18n/finbreak_<lang>.ts, then compiles each .ts to the
# .qm beside it. A <lang> with no catalog yet gets a new one (e.g. `es`, `pt_BR`).
# Both files are committed; tests/features/i18n's INV-6 fails when a run of this
# script would change them.
#
# -locations none keeps a code edit that only moves a string from rewriting the
# catalog; -no-obsolete drops strings the source no longer has.
set -euo pipefail

cd "$(dirname "$0")/.."
I18N="src/finbreak/data/i18n"
mkdir -p "$I18N"

catalogs=()
for lang in "$@"; do
    catalogs+=("$I18N/finbreak_${lang}.ts")
done
for ts in "$I18N"/finbreak_*.ts; do
    [ -e "$ts" ] || continue
    case " ${catalogs[*]-} " in
        *" $ts "*) ;;
        *) catalogs+=("$ts") ;;
    esac
done

if [ "${#catalogs[@]}" -eq 0 ]; then
    echo "update-translations.sh: no catalogs yet; pass a language, e.g. es" >&2
    exit 0
fi

mapfile -t sources < <(git ls-files 'src/finbreak/*.py')

for ts in "${catalogs[@]}"; do
    pyside6-lupdate -no-obsolete -locations none "${sources[@]}" -ts "$ts"
    pyside6-lrelease "$ts" -qm "${ts%.ts}.qm"
done
