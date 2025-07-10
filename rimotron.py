import argparse
from collections import defaultdict
from typing import Iterable, List

import pandas as pd
from phonemizer import phonemize
from rapidfuzz.distance import Levenshtein

LEX: pd.DataFrame | None = None
RHYME_IX: dict[str, list[tuple[str, float]]] | None = None
COVER_IX: dict[int, list[str]] | None = None
PH_DISCRET = {"ə", "j", "w"}


def load_lexicon(path: str) -> None:
    """Load Parquet lexicon and prepare rhyme indexes."""
    global LEX, COVER_IX, RHYME_IX
    LEX = pd.read_parquet(path)

    COVER_IX = LEX.groupby("len_ph")["ortho"].apply(list).to_dict()

    RHYME_IX = defaultdict(list)
    for _, row in LEX.iterrows():
        suffix = row["ipa"][-10:]
        freq = float(row.get("freqfilms2", 0))
        RHYME_IX[suffix].append((row["ortho"], freq))


def split_phonemes(word: str) -> list[str]:
    row = LEX.loc[LEX['ortho'] == word]
    if not row.empty:
        return list(row.iloc[0]['ipa'])
    ipa = phonemize(word, language='fr-fr', backend='espeak', strip=True)
    return [p for p in ipa if p not in PH_DISCRET]


def rhyme_candidates(word: str, min_syl: int = 3, limit: int = 20,
                     approx: bool = False) -> List[str]:
    """Return words sharing the final phonemes of ``word``.

    If ``approx`` is True and no results are found, perform an approximate
    search based on Levenshtein distance of the IPA sequences.
    """
    ipa = ''.join(split_phonemes(word))
    if len(ipa) < min_syl:
        min_syl = len(ipa)
    suffix = ipa[-min_syl:]

    # Exact matches by suffix
    matches = []
    for suf, words in RHYME_IX.items():
        if suf.endswith(suffix):
            matches.extend(words)

    matches = sorted(matches, key=lambda x: -x[1])
    out = [w for w, _ in matches if w != word][:limit]
    if out or not approx:
        return out

    # Approximate search if nothing found
    cand = []
    for _, row in LEX.iterrows():
        dist = Levenshtein.distance(row['ipa'], ipa)
        if dist <= 1:
            cand.append((row['ortho'], float(row.get('freqfilms2', 0)), dist))

    cand.sort(key=lambda x: (x[2], -x[1]))
    return [w for w, _, _ in cand if w != word][:limit]


def find_longest_cover(target: str, max_branch: int = 5) -> List[List[str]]:
    """Greedy search for the longest homophone cover of ``target``."""
    ipa = split_phonemes(target)
    memo = {}

    def dfs(i):
        if i == len(ipa):
            return [[]]
        if i in memo:
            return memo[i]
        out = []
        for L in range(len(ipa) - i, 0, -1):
            candidates = COVER_IX.get(L, [])
            hits = [w for w in candidates if split_phonemes(w) == ipa[i:i+L]][:max_branch]
            if not hits:
                continue
            for tail in dfs(i+L):
                out += [[h] + tail for h in hits]
            if out:
                break
        memo[i] = out
        return out

    return dfs(0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Rhyme assistant")
    parser.add_argument("--lexicon", default="lex_master.parquet", help="Lexicon file")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_cover = sub.add_parser("cover", help="Find homophone cover for a phrase")
    p_cover.add_argument("phrase")
    p_cover.add_argument("--max-branch", type=int, default=5)

    p_rhyme = sub.add_parser("rhyme", help="Suggest rhymes for a word")
    p_rhyme.add_argument("word")
    p_rhyme.add_argument("--min-syl", type=int, default=3)
    p_rhyme.add_argument("--max-results", type=int, default=20)
    p_rhyme.add_argument("--approx", action="store_true")

    args = parser.parse_args()

    load_lexicon(args.lexicon)

    if args.cmd == "cover":
        words = args.phrase.strip().split()
        for word in words:
            covers = find_longest_cover(word, args.max_branch)
            print(word, "->", covers)
    elif args.cmd == "rhyme":
        rhymes = rhyme_candidates(args.word, args.min_syl, args.max_results, args.approx)
        for r in rhymes:
            print(r)


if __name__ == '__main__':
    main()
