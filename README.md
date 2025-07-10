# Rime Generator Toolkit

This repository provides two main scripts to merge several French
lexicons and query them for rhymes.

## build_lexicon.py

```
python build_lexicon.py --lexique Lexique383.tsv \
                        --glaff glaff.tsv \
                        --dela fra.delaf.txt.gz \
                        --lefff lefff.tsv \
                        --output lex_master.parquet
```

Each input file must be downloaded separately. The script converts the
SAMPA fields to IPA using `phonemizer`, merges all entries and writes a
parquet file indexed by the last ten phonemes.

## rimotron.py

The rhyme assistant exposes two subcommands:

```
python rimotron.py cover "amour toujours" --lexicon lex_master.parquet
python rimotron.py rhyme amour --lexicon lex_master.parquet --min-syl 3
```

`cover` searches for homophone coverings of each word in the phrase, while
`rhyme` lists words sharing the same final phonemes.


## Downloading datasets

To grab all required resources into `/Users/bengpt/Downloads/DATASET_LINGUISTIQUE` run:

```bash
./fetch_datasets.sh
```

Specify a different destination as the first argument if needed. After the downloads finish you can build the merged lexicon with `build_lexicon.py`.
