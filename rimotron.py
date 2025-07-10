import argparse
import pandas as pd
from phonemizer import phonemize

LEX = None
COVER_IX = None
PH_DISCRET = {"ə", "j", "w"}


def load_lexicon(path: str) -> None:
    global LEX, COVER_IX
    LEX = pd.read_parquet(path)
    COVER_IX = LEX.groupby("len_ph")['ortho'].apply(list).to_dict()


def split_phonemes(word: str) -> list[str]:
    row = LEX.loc[LEX['ortho'] == word]
    if not row.empty:
        return list(row.iloc[0]['ipa'])
    ipa = phonemize(word, language='fr-fr', backend='espeak', strip=True)
    return [p for p in ipa if p not in PH_DISCRET]


def find_cover(target: str, max_branch: int = 5):
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


def main():
    parser = argparse.ArgumentParser(description='Rhyme assistant')
    parser.add_argument('phrase', help='Input phrase')
    parser.add_argument('--lexicon', default='lex_master.parquet', help='Lexicon file')
    parser.add_argument('--max-syl', type=int, default=5, help='Max length per branch')
    args = parser.parse_args()

    load_lexicon(args.lexicon)

    words = args.phrase.strip().split()
    for word in words:
        covers = find_cover(word, args.max_syl)
        print(word, '->', covers)


if __name__ == '__main__':
    main()
