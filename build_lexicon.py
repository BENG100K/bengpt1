import argparse
import gzip
import pandas as pd
import re
from glob import glob
from phonemizer import phonemize

PH_DISCRET = {"ə", "j", "w"}


def to_ipa(phon: str) -> str:
    ipa = phonemize(
        phon,
        language="fr-fr",
        backend="espeak",
        strip=True,
        separator="-",
    )
    return "".join(p for p in ipa.split("-") if p not in PH_DISCRET)


def process_lexique(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, sep="\t")
    df["ipa"] = df["phon"].apply(to_ipa)
    return df[["ortho", "ipa", "freqfilms2"]]


def process_glaff(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, sep="\t")
    return df[["ortho", "phon"]].rename(columns={"phon": "ipa"})


def process_dela(path: str) -> pd.DataFrame:
    pat = re.compile(r"([^,]+),([^:]+):([A-Z]+)")
    rows = []
    with gzip.open(path, "rt", encoding="utf16") as f:
        for line in f:
            if "," not in line:
                continue
            m = pat.match(line)
            if not m:
                continue
            rows.append(m.groups())
    df = pd.DataFrame(rows, columns=["lemma", "ortho", "pos"])
    return df[["ortho"]].assign(ipa=df["ortho"].apply(to_ipa))


def process_lefff(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, sep="\t", header=None, names=["ortho", "lemma", "pos", "inflected", "sampa"])
    df["ipa"] = df["sampa"].fillna("" ).apply(to_ipa)
    return df[["ortho", "ipa"]]


def build_index(output: str, frames: list[pd.DataFrame]) -> None:
    lex = pd.concat(frames, ignore_index=True).drop_duplicates("ortho")
    lex["ipa_suffix"] = lex["ipa"].str[-10:]
    lex["len_ph"] = lex["ipa"].str.len()
    lex = lex.set_index("ipa_suffix").sort_index()
    lex.to_parquet(output, index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build merged French lexicon")
    parser.add_argument("--lexique", required=True, help="Lexique383.tsv path")
    parser.add_argument("--glaff", required=False, help="GLAFF.tsv path")
    parser.add_argument("--dela", required=False, help="fra.delaf.txt.gz path")
    parser.add_argument("--lefff", required=False, help="lefff.tsv path")
    parser.add_argument("--output", required=True, help="Output parquet file")

    args = parser.parse_args()

    frames = [process_lexique(args.lexique)]
    if args.glaff:
        frames.append(process_glaff(args.glaff))
    if args.dela:
        frames.append(process_dela(args.dela))
    if args.lefff:
        frames.append(process_lefff(args.lefff))

    build_index(args.output, frames)


if __name__ == "__main__":
    main()
