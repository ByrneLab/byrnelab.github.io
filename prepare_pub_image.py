#!/usr/bin/env python3
"""Turn any figure into a publication thumbnail and wire it into the site.

Takes an image (a panel you cropped from your own figure, or one pulled by
fetch_pub_figures.py), squares it, resizes it, writes it to
assets/images/pubs/, and adds the `image:` line to the matching entry in
_data/publications.yml.

Usage
-----
    # match the publication by PMID and let it name the file
    python3 prepare_pub_image.py figure3b.tif --pmid 34664552

    # choose the filename yourself
    python3 prepare_pub_image.py figure3b.tif --pmid 34664552 --name scaavengr.jpg

    # crop a specific region first (left,top,right,bottom in pixels)
    python3 prepare_pub_image.py fig1.png --pmid 36509783 --crop 0,0,900,900

    # just make the file, don't touch the YAML
    python3 prepare_pub_image.py fig1.png --name something.jpg --no-yaml

By default the image is centre-cropped to a square. Use --crop to pick the
panel that actually matters — a whole multi-panel figure is unreadable at
88px.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata

try:
    import yaml
    from PIL import Image, ImageOps
except ImportError:
    sys.exit("Missing dependency. Run:  pip install pyyaml pillow")

ROOT = os.path.dirname(os.path.abspath(__file__))
PUBS_YML = os.path.join(ROOT, "_data", "publications.yml")
OUTDIR = os.path.join(ROOT, "assets", "images", "pubs")

# Displayed at 88px; 400px keeps it crisp on retina screens without bloating
# the repo.
SIZE = 400


def slugify(text: str) -> str:
    # Fold accents so filenames stay ASCII (Öztürk -> ozturk, Aït-Ali -> ait-ali).
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[\s_]+", "-", text).strip("-")


INITIALS = re.compile(r"^[A-Z]{1,3}\.?$")


def first_author_surname(authors: str) -> str:
    """Handles both "Xi Z" (surname first) and "Bilge E. Ozturk" (surname last)."""
    first = (authors or "").split(",")[0].strip()
    tokens = first.split()
    if not tokens:
        return "paper"
    if len(tokens) >= 2 and INITIALS.match(tokens[-1]):
        return slugify(tokens[0])
    return slugify(tokens[-1])


def load_pubs() -> list:
    with open(PUBS_YML, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def find_entry(pubs: list, pmid: str):
    for i, p in enumerate(pubs):
        if pmid in (p.get("pubmed") or ""):
            return i, p
    return None, None


def default_name(pub: dict) -> str:
    return f"{pub.get('year')}-{first_author_surname(pub.get('authors') or '')}.jpg"


def build_thumbnail(src: str, dest: str, crop: str | None) -> tuple[int, int]:
    img = Image.open(src)
    img = ImageOps.exif_transpose(img)

    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        rgba = img.convert("RGBA")
        bg.paste(rgba, mask=rgba.split()[-1])
        img = bg
    else:
        img = img.convert("RGB")

    original = img.size

    if crop:
        try:
            box = tuple(int(v) for v in crop.split(","))
            if len(box) != 4:
                raise ValueError
        except ValueError:
            sys.exit("--crop needs four integers: left,top,right,bottom")
        img = img.crop(box)

    # Square off, centred, then resize.
    img = ImageOps.fit(img, (SIZE, SIZE), method=Image.LANCZOS, centering=(0.5, 0.5))

    os.makedirs(os.path.dirname(dest), exist_ok=True)
    img.save(dest, "JPEG", quality=86, optimize=True, progressive=True)
    return original


def set_image_field(pmid: str, filename: str) -> str:
    """Insert or update `image:` on the entry with this PMID.

    Line-based on purpose — a YAML round-trip would strip the comments and
    reflow every block in the file.
    """
    with open(PUBS_YML, encoding="utf-8") as fh:
        lines = fh.readlines()

    # Entry boundaries
    starts = [i for i, l in enumerate(lines) if l.startswith("- year:")]
    starts.append(len(lines))

    for n in range(len(starts) - 1):
        a, b = starts[n], starts[n + 1]
        block = lines[a:b]
        if not any(pmid in l for l in block):
            continue

        for j, l in enumerate(block):
            if re.match(r"\s*image:", l):
                lines[a + j] = f"  image: {filename}\n"
                with open(PUBS_YML, "w", encoding="utf-8") as fh:
                    fh.writelines(lines)
                return "updated"

        # Insert after `venue:` (which may be a folded multi-line value).
        insert_at = None
        for j, l in enumerate(block):
            if re.match(r"\s*venue:", l):
                insert_at = j + 1
                while insert_at < len(block) and block[insert_at].startswith("    "):
                    insert_at += 1
                break
        if insert_at is None:
            insert_at = len(block)
            while insert_at > 0 and not block[insert_at - 1].strip():
                insert_at -= 1

        lines.insert(a + insert_at, f"  image: {filename}\n")
        with open(PUBS_YML, "w", encoding="utf-8") as fh:
            fh.writelines(lines)
        return "added"

    return "not found"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", help="image file to convert")
    ap.add_argument("--pmid", help="PMID of the publication to attach it to")
    ap.add_argument("--name", help="output filename (default: <year>-<author>.jpg)")
    ap.add_argument("--crop", help="left,top,right,bottom in source pixels")
    ap.add_argument("--no-yaml", action="store_true", help="write the image only")
    args = ap.parse_args()

    if not os.path.isfile(args.source):
        sys.exit(f"No such file: {args.source}")

    pub = None
    if args.pmid:
        idx, pub = find_entry(load_pubs(), args.pmid)
        if pub is None:
            sys.exit(f"No publication in publications.yml has PMID {args.pmid}")

    name = args.name or (default_name(pub) if pub else None)
    if not name:
        sys.exit("Give --pmid (to derive a name) or --name")
    if not name.lower().endswith(".jpg"):
        name += ".jpg"

    dest = os.path.join(OUTDIR, name)
    original = build_thumbnail(args.source, dest, args.crop)

    size_kb = os.path.getsize(dest) / 1024
    print(f"wrote  assets/images/pubs/{name}  ({SIZE}x{SIZE}, {size_kb:.0f} KB, "
          f"source was {original[0]}x{original[1]})")

    if pub:
        print(f"paper  {pub['year']} — {pub['title'][:60]}")

    if args.pmid and not args.no_yaml:
        result = set_image_field(args.pmid, name)
        print(f"yaml   image: {name}  ({result})")
    else:
        print(f"yaml   add this line to the entry:\n         image: {name}")

    print("\nCheck it with:  python3 verify_site.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
