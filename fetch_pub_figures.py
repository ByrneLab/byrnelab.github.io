#!/usr/bin/env python3
"""Download candidate figures for publications from the PMC Open Access subset.

Only touches papers that PMC reports as Open Access with a reuse licence
(CC BY and friends). Anything else is listed in the report for you to handle
by hand from your own figure files — this script will not scrape figures from
subscription journals.

Nothing is written into the live site. Figures land in `pub-figures-review/`
for you to look through; once you pick one, run:

    python3 prepare_pub_image.py pub-figures-review/<folder>/<file>.jpg --pmid <PMID>

Usage
-----
    python3 fetch_pub_figures.py            # fetch everything possible
    python3 fetch_pub_figures.py --list     # just show the table, fetch nothing
    python3 fetch_pub_figures.py --pmid 34664552   # single paper

NCBI asks for <=3 requests/second without an API key; this sleeps accordingly.
Set NCBI_API_KEY in your environment to go faster.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import tarfile
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

try:
    import yaml
except ImportError:
    sys.exit("Missing dependency. Run:  pip install pyyaml pillow")

ROOT = os.path.dirname(os.path.abspath(__file__))
PUBS = os.path.join(ROOT, "_data", "publications.yml")
REVIEW = os.path.join(ROOT, "pub-figures-review")

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
OA_SERVICE = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi"
IDCONV = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
API_KEY = os.environ.get("NCBI_API_KEY", "")
PAUSE = 0.12 if API_KEY else 0.36

UA = {"User-Agent": "byrnelab-site/1.0 (lab website figure collection)"}

IMAGE_EXT = (".jpg", ".jpeg", ".png", ".gif", ".tif", ".tiff")


def classify_licence(licence: str) -> tuple[str, str]:
    """Return (verdict, note).

    verdict is one of: free, noncommercial, no-derivatives, none.

    The ND distinction matters: a no-derivatives licence does not permit
    cropping a panel out of a figure, which is exactly what a thumbnail is.
    You are an author on these papers and retain your own reuse rights, so
    these are still downloaded — but they're flagged so the choice is yours
    rather than silently assumed.
    """
    lic = (licence or "").upper().replace("_", "-")
    if not lic or lic in ("NONE", "UNSPECIFIED"):
        return "none", "no reuse licence"
    if "ND" in re.split(r"[- ]", lic):
        return "no-derivatives", "ND: cropping not permitted for third parties"
    if "NC" in re.split(r"[- ]", lic):
        return "noncommercial", "NC: non-commercial use only"
    if re.search(r"CC[ -]?(BY|0)", lic):
        return "free", ""
    return "none", f"unrecognised licence: {licence}"


def get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def slugify(text: str) -> str:
    # Fold accents so filenames stay ASCII (Öztürk -> ozturk, Aït-Ali -> ait-ali).
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[\s_]+", "-", text).strip("-")


INITIALS = re.compile(r"^[A-Z]{1,3}\.?$")


def first_author_surname(authors: str) -> str:
    """The author lists mix two conventions:

        "Xi Z, Vats A"              -> surname first, then initials
        "Bilge E. Ozturk, Molly..." -> given names first, surname last

    Trailing initials identify the first form; otherwise take the last token.
    """
    first = (authors or "").split(",")[0].strip()
    tokens = first.split()
    if not tokens:
        return "unknown"
    if len(tokens) >= 2 and INITIALS.match(tokens[-1]):
        return slugify(tokens[0])
    return slugify(tokens[-1])


def entry_slug(pub: dict) -> str:
    """Stable, readable folder/file stem: 2021-ozturk-scaavengr."""
    surname = first_author_surname(pub.get("authors") or "")
    words = [w for w in slugify(pub.get("title", "")).split("-") if len(w) > 3]
    tail = "-".join(words[:3]) or "paper"
    return f"{pub.get('year')}-{surname}-{tail}"


def pmid_of(pub: dict):
    m = re.search(r"/(\d{7,8})/", pub.get("pubmed") or "")
    return m.group(1) if m else None


def pmid_to_pmcid(pmid: str):
    """PMID -> PMCID via NCBI's ID Converter.

    Do NOT use elink for this. elink(pubmed->pmc) returns *related* PMC
    records — citing papers, similar articles — and the first result is often
    not the article itself. That silently produced PMC IDs from the wrong
    decade. idconv is the authoritative 1:1 mapping.
    """
    url = (f"{IDCONV}?ids={pmid}&idtype=pmid&format=json"
           + (f"&api_key={API_KEY}" if API_KEY else ""))
    try:
        data = json.loads(get(url, timeout=30))
    except Exception:
        return None
    for rec in data.get("records", []):
        if rec.get("pmcid"):
            return rec["pmcid"]
    return None


def oa_record(pmcid: str):
    """Return (license, tgz_url) or (None, None) if not in the OA subset."""
    try:
        xml = get(f"{OA_SERVICE}?id={urllib.parse.quote(pmcid)}", timeout=30)
    except Exception:
        return None, None
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return None, None
    if root.find("error") is not None:
        return None, None
    rec = root.find(".//record")
    if rec is None:
        return None, None
    licence = rec.get("license") or "unspecified"
    href = None
    for link in rec.findall("link"):
        if link.get("format") == "tgz":
            href = link.get("href")
            break
    if href and href.startswith("ftp://"):
        # The FTP host serves the same paths over HTTPS.
        href = "https://" + href[len("ftp://"):]
    return licence, href


def save_bytes(outdir: str, name: str, payload: bytes, min_size: int = 20_000):
    """Write an image, skipping tiny icons/thumbnails packages carry."""
    if len(payload) < min_size:
        return None
    os.makedirs(outdir, exist_ok=True)
    dest = os.path.join(outdir, name)
    with open(dest, "wb") as fh:
        fh.write(payload)
    return dest


def tgz_candidates(href: str, pmcid: str) -> list[str]:
    """The OA service returns an ftp:// href. The same tree is served over
    HTTPS, but the host has moved around, so try the known forms in order."""
    urls = []
    if href:
        path = href.split("://", 1)[-1]
        rest = path.split("/", 1)[1] if "/" in path else path
        urls += [
            "https://" + path,                        # ftp.ncbi.nlm.nih.gov/...
            "https://ftp.ncbi.nlm.nih.gov/" + rest,
            "https://pmc.ncbi.nlm.nih.gov/" + rest,
        ]
    seen, out = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def figures_from_tgz(href: str, pmcid: str, outdir: str):
    """Returns (files, error). Tries each candidate URL."""
    last = None
    for url in tgz_candidates(href, pmcid):
        try:
            blob = get(url, timeout=180)
        except Exception as exc:
            last = f"{type(exc).__name__} on {url}"
            continue
        saved = []
        try:
            with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
                for m in tar.getmembers():
                    if not m.isfile():
                        continue
                    name = os.path.basename(m.name)
                    if name.startswith(".") or not name.lower().endswith(IMAGE_EXT):
                        continue
                    fh = tar.extractfile(m)
                    if fh is None:
                        continue
                    dest = save_bytes(outdir, name, fh.read())
                    if dest:
                        saved.append(dest)
        except Exception as exc:
            last = f"bad archive from {url}: {exc}"
            continue
        return sorted(saved), None
    return [], last


# Any <img src> or <source srcset>. PMC has moved figure hosting more than
# once — old articles used /pmc/articles/PMCxxx/bin/fig.jpg, the current site
# serves from cdn.ncbi.nlm.nih.gov/pmc/blobs/... — so match broadly and filter
# afterwards rather than hard-coding one path shape.
IMG_ANY = re.compile(r'<(?:img|source)[^>]+(?:src|srcset)="([^"]+)"', re.I)
NOT_FIGURE = re.compile(r"(logo|icon|banner|sprite|avatar|button|spinner|/core/)", re.I)


def absolutise(src: str) -> str:
    if src.startswith("//"):
        return "https:" + src
    if src.startswith("/"):
        return "https://pmc.ncbi.nlm.nih.gov" + src
    return src


def article_image_urls(html: str) -> list[str]:
    urls, seen = [], set()
    for m in IMG_ANY.finditer(html):
        # srcset can hold several candidates: "a.jpg 1x, b.jpg 2x"
        for part in m.group(1).split(","):
            src = part.strip().split(" ")[0]
            if not src:
                continue
            src = absolutise(src)
            base = src.split("?")[0]
            if not base.lower().endswith(IMAGE_EXT):
                continue
            if NOT_FIGURE.search(base):
                continue
            if src in seen:
                continue
            seen.add(src)
            urls.append(src)
    # Full-size before thumbnails, but keep both — some articles only expose
    # the thumbnail variant in the markup.
    urls.sort(key=lambda u: ("thumb" in u.lower(), u))
    return urls


def figures_from_article(pmcid: str, outdir: str, debug: bool = False):
    page_urls = [
        f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/",
        f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/",
    ]
    html, last = None, None
    used = None
    for u in page_urls:
        try:
            html = get(u, timeout=60).decode("utf-8", "ignore")
            used = u
            break
        except Exception as exc:
            last = f"{type(exc).__name__} fetching {u}"
    if html is None:
        return [], last

    urls = article_image_urls(html)

    if debug:
        print(f"    [debug] page {used}: {len(html)} bytes, "
              f"{html.lower().count('<img')} <img> tags, "
              f"{len(urls)} figure candidates")
        for u in urls[:6]:
            print(f"    [debug]   {u}")

    saved = []
    for src in urls:
        try:
            dest = save_bytes(outdir, os.path.basename(src.split("?")[0]),
                              get(src, timeout=90), min_size=15_000)
            if dest:
                saved.append(dest)
        except Exception as exc:
            if debug:
                print(f"    [debug]   FAILED {src}: {exc}")
            continue
        time.sleep(PAUSE)

    if not saved:
        last = (f"page had {html.lower().count('<img')} <img> tags, "
                f"{len(urls)} looked like figures, none downloadable")
    return sorted(saved), last


def collect_figures(href: str, pmcid: str, outdir: str, debug: bool = False):
    """tgz first, article page as fallback. Returns (files, method, error).

    Reports BOTH failure reasons — an earlier version let the fallback's error
    mask the tarball's, which made the real cause invisible.
    """
    files, tgz_err = figures_from_tgz(href, pmcid, outdir)
    if files:
        return files, "tgz", None
    if debug:
        print(f"    [debug] tgz href: {href}")
        print(f"    [debug] tgz error: {tgz_err}")
    files, page_err = figures_from_article(pmcid, outdir, debug=debug)
    if files:
        return files, "article page", None
    return [], None, f"tgz: {tgz_err} | page: {page_err}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="show the table, fetch nothing")
    ap.add_argument("--pmid", help="process a single PMID")
    ap.add_argument("--strict", action="store_true",
                    help="skip no-derivatives (ND) licences instead of flagging them")
    ap.add_argument("--debug", action="store_true",
                    help="print the OA href, page size and candidate image URLs")
    args = ap.parse_args()

    with open(PUBS, encoding="utf-8") as fh:
        pubs = yaml.safe_load(fh)

    rows, downloaded, manual, flagged = [], 0, [], []

    for pub in pubs:
        pmid = pmid_of(pub)
        slug = entry_slug(pub)
        short = (pub.get("title") or "")[:48]

        if args.pmid and pmid != args.pmid:
            continue

        if pub.get("image"):
            rows.append((pub["year"], slug, "has image", "-", "skipped"))
            continue
        if not pmid:
            rows.append((pub["year"], slug, "no PMID", "-", "manual"))
            manual.append((slug, short, pub.get("doi") or ""))
            continue
        if args.list:
            rows.append((pub["year"], slug, pmid, "?", "not checked"))
            continue

        pmcid = pmid_to_pmcid(pmid)
        time.sleep(PAUSE)
        if not pmcid:
            rows.append((pub["year"], slug, pmid, "not in PMC", "manual"))
            manual.append((slug, short, f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"))
            continue

        licence, tgz = oa_record(pmcid)
        time.sleep(PAUSE)

        verdict, note = classify_licence(licence)

        if not tgz and verdict == "none":
            rows.append((pub["year"], slug, pmcid, licence or "-", "manual: not open access"))
            manual.append((slug, short, f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"))
            continue

        if verdict == "none":
            rows.append((pub["year"], slug, pmcid, licence or "-", f"manual: {note}"))
            manual.append((slug, short, f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"))
            continue

        if verdict == "no-derivatives" and args.strict:
            rows.append((pub["year"], slug, pmcid, licence, "skipped: ND (--strict)"))
            manual.append((slug, short, f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"))
            continue

        outdir = os.path.join(REVIEW, slug)
        if os.path.isdir(outdir) and os.listdir(outdir):
            rows.append((pub["year"], slug, pmcid, licence, "already fetched"))
            continue

        if args.debug:
            print(f"\n--- {slug} ({pmcid}, {licence}) ---")
        figs, method, err = collect_figures(tgz, pmcid, outdir, debug=args.debug)
        if not figs:
            rows.append((pub["year"], slug, pmcid, licence, f"failed: {err}"))
            continue

        downloaded += 1
        flag = "  [ND]" if verdict == "no-derivatives" else ""
        rows.append((pub["year"], slug, pmcid, licence,
                     f"{len(figs)} figures via {method}{flag}"))
        if note:
            flagged.append((slug, licence, note))

    print("=" * 96)
    print(f"{'YEAR':5} {'SLUG':42} {'ID':12} {'LICENCE':16} RESULT")
    print("=" * 96)
    for r in rows:
        print(f"{str(r[0]):5} {r[1][:42]:42} {str(r[2])[:12]:12} {str(r[3])[:16]:16} {r[4]}")

    print(f"\n{downloaded} paper(s) fetched into {os.path.relpath(REVIEW, ROOT)}/")

    if flagged:
        print(f"\n{len(flagged)} fetched paper(s) carry licence conditions — you are an "
              f"author on these and retain your own reuse rights, but check before\n"
              f"publishing crops if in doubt:")
        for slug, lic, note in flagged:
            print(f"  {slug}\n      {lic} — {note}")

    if manual:
        print(f"\n{len(manual)} paper(s) need a figure from your own files:")
        for slug, title, link in manual:
            print(f"  {slug}")
            print(f"      {title}")
            if link:
                print(f"      {link}")

    print("\nNext: pick a figure, then run")
    print("  python3 prepare_pub_image.py <path-to-figure> --pmid <PMID>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
