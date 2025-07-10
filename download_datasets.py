import argparse
import hashlib
import json
import os
import urllib.request
import shutil
from pathlib import Path


def md5sum(path: Path) -> str:
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def download_file(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as r, open(dest, 'wb') as f:
        shutil.copyfileobj(r, f)


def load_descriptors(path: Path) -> dict:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def ensure_dataset(ds: dict, dest_root: Path) -> None:
    dest = dest_root / ds['path']
    if dest.exists() and ds.get('md5'):
        if md5sum(dest) == ds['md5']:
            print(f"{dest.name} already up to date")
            return
        else:
            print(f"Checksum mismatch for {dest.name}, re-downloading")
    print(f"Downloading {dest.name}...")
    download_file(ds['url'], dest)
    if ds.get('md5') and md5sum(dest) != ds['md5']:
        raise RuntimeError(f"MD5 mismatch for {dest}")


def main() -> None:
    p = argparse.ArgumentParser(description='Download linguistic datasets')
    p.add_argument('--desc', default='datasets.json', help='Dataset descriptor file')
    p.add_argument('dest', nargs='?', default='/Users/bengpt/Downloads/DATASET_LINGUISTIQUE', help='Destination directory')
    args = p.parse_args()

    descs = load_descriptors(Path(args.desc))
    dest_root = Path(args.dest)
    dest_root.mkdir(parents=True, exist_ok=True)

    for ds in descs.values():
        ensure_dataset(ds, dest_root)


if __name__ == '__main__':
    main()
