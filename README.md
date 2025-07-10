# Rime Generator Toolkit

This repository provides two main scripts to merge several French
lexicons and query them for rhymes.

## build_lexicon.py

```
python build_lexicon.py --lexique Lexique382.txt \
                        --glaff glaff.tsv \
                        --dela fra.delaf.txt.gz \
                        --lefff lefff.tsv \
                        --output lex_master.parquet
```

Each input file must be downloaded separately. The script converts the
SAMPA fields to IPA using `phonemizer`, merges all entries and writes a
parquet file indexed by the last ten phonemes.

## rimotron.py

```
python rimotron.py "amour toujours" --lexicon lex_master.parquet
```

This loads the parquet file and prints possible homophone covers for
each word in the phrase.


## Downloading datasets

To grab all required resources into `/Users/bengpt/Downloads/DATASET_LINGUISTIQUE` run:

```bash
./fetch_datasets.sh
```

Specify a different destination as the first argument if needed. After the downloads finish you can build the merged lexicon with `build_lexicon.py`.
