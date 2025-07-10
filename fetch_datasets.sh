#!/bin/bash
# Download French linguistic datasets used by build_lexicon.py
set -euo pipefail
DEST="${1:-/Users/bengpt/Downloads/DATASET_LINGUISTIQUE}"
mkdir -p "$DEST"

curl -L https://raw.githubusercontent.com/pmichel31415/openlexicon/master/lexique383/Lexique383.tsv \
    -o "$DEST/Lexique382.txt"

curl -L https://raw.githubusercontent.com/bootphon/glaff/master/glaff-2.1.tsv \
    -o "$DEST/glaff.tsv"

curl -L https://raw.githubusercontent.com/lethexfan/dela/master/fra.delaf.txt.gz \
    -o "$DEST/fra.delaf.txt.gz"

curl -L https://raw.githubusercontent.com/colinbenne/lefff/master/lefff.tsv \
    -o "$DEST/lefff.tsv"
