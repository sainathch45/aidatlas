"""Download every resource file of an HDX dataset via the public CKAN API.

No authentication required for reads. Usage:

    python fetch_hdx_dataset.py hdx-hapi-syr
    python fetch_hdx_dataset.py hdx-hapi-irq --out raw

Dataset ids are the slug at the end of a data.humdata.org dataset URL,
e.g. https://data.humdata.org/dataset/hdx-hapi-syr -> hdx-hapi-syr
"""

import argparse
import pathlib
import re
import sys
from urllib.parse import urlsplit

import requests

CKAN_BASE = "https://data.humdata.org/api/3/action"

# Characters NTFS/Windows reject in filenames. Resource "name" fields from
# HDX often contain a colon (e.g. "Affected People: IDPs for Syria") -- on
# Windows, open()ing a path with a colon in it silently creates an NTFS
# alternate data stream instead of erroring, so the bytes land somewhere
# `ls`/`wc -c` can't see rather than failing loudly. Prefer the clean
# filename HDX already puts at the end of the resource URL; only fall back
# to a sanitized version of `name` if the URL has none.
_INVALID_WINDOWS_CHARS = re.compile(r'[<>:"/\\|?*]')


def safe_filename(name: str, url: str, fmt: str) -> str:
    url_name = pathlib.PurePosixPath(urlsplit(url).path).name
    if url_name and "." in url_name:
        return url_name
    base = _INVALID_WINDOWS_CHARS.sub("_", name).strip()
    return base if "." in base else f"{base}.{fmt.lower() or 'bin'}"


def fetch_resource_list(dataset_id: str) -> list[dict]:
    resp = requests.get(f"{CKAN_BASE}/package_show", params={"id": dataset_id}, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("success"):
        raise RuntimeError(f"CKAN lookup failed for '{dataset_id}': {payload}")
    return payload["result"]["resources"]


def download_resources(dataset_id: str, out_dir: pathlib.Path) -> None:
    resources = fetch_resource_list(dataset_id)
    target = out_dir / dataset_id
    target.mkdir(parents=True, exist_ok=True)

    for res in resources:
        url = res.get("url")
        name = res.get("name") or res["id"]
        fmt = res.get("format") or ""
        if not url:
            continue
        dest = target / safe_filename(name, url, fmt)
        print(f"  {name}  ({fmt})  -> {dest}", flush=True)
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 16):
                    f.write(chunk)

    print(f"Saved {len(resources)} resource(s) to {target}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_id", help="HDX dataset slug, e.g. hdx-hapi-syr")
    parser.add_argument("--out", default="raw", help="output directory (default: raw)")
    args = parser.parse_args()

    try:
        download_resources(args.dataset_id, pathlib.Path(args.out))
    except requests.HTTPError as exc:
        print(f"HTTP error fetching '{args.dataset_id}': {exc}", file=sys.stderr)
        sys.exit(1)
