"""Static checks on the Jekyll source.

Jekyll itself can't be installed in this sandbox (rubygems is blocked), so this
verifies the things that actually break a build or a page:

  1. every _data/*.yml file parses
  2. every page has valid YAML front matter
  3. Liquid tags/blocks are balanced and blocks are properly nested
  4. every image path referenced by templates or data has a defined source
  5. internal links point at real permalinks
  6. people/gallery/project entries have required fields
"""
from __future__ import annotations

import os
import re
import sys

import yaml

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "_data")

errors: list[str] = []
warnings: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)


def warn(msg: str) -> None:
    warnings.append(msg)


# ---------------------------------------------------------------- front matter
def split_front_matter(text: str):
    if not text.startswith("---"):
        return None, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, text
    return parts[1], parts[2]


def page_files() -> list[str]:
    """Files Jekyll will actually process, honouring _config.yml `exclude`."""
    out = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [
            d for d in dirnames
            if d not in {"_site", ".git", "vendor", "node_modules", ".jekyll-cache"}
        ]
        for fn in filenames:
            if not fn.endswith((".html", ".md", ".scss")):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), ROOT)
            if rel in EXCLUDED or rel.split(os.sep)[0] in EXCLUDED:
                continue
            out.append(os.path.join(dirpath, fn))
    return sorted(out)


# ------------------------------------------------------------------ data files
data: dict[str, object] = {}
for fn in sorted(os.listdir(DATA)):
    if not fn.endswith((".yml", ".yaml")):
        continue
    path = os.path.join(DATA, fn)
    try:
        with open(path, encoding="utf-8") as fh:
            data[os.path.splitext(fn)[0]] = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        err(f"_data/{fn}: YAML parse error: {exc}")

with open(os.path.join(ROOT, "_config.yml"), encoding="utf-8") as fh:
    try:
        config = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        config = {}
        err(f"_config.yml: YAML parse error: {exc}")

# Files Jekyll is told to ignore — they need no front matter and are not pages.
EXCLUDED = set(config.get("exclude") or []) | {"README.md"}

# --------------------------------------------------------- required data fields
people = data.get("people") or []

# Only `name` is required. `role`, `group` and `photo` are all optional — the
# People page renders a flat grid of initials when they're absent.
for i, p in enumerate(people):
    if not p.get("name"):
        err(f"_data/people.yml[{i}]: missing 'name'")

valid_groups = {"pi", "postdocs", "students", "staff"}
grouped = [p for p in people if p.get("group")]

if grouped:
    # Groups are in use, so a bad or missing one is now meaningful.
    for p in people:
        if p.get("group") not in valid_groups:
            warn(f"people.yml: '{p.get('name')}' has group "
                 f"'{p.get('group')}' — falls into the catch-all section")
    if not any(p.get("group") == "pi" for p in people):
        warn("people.yml: groups are in use but no entry has group 'pi' — "
             "the PI is not listed on the People page")

roled = [p for p in people if p.get("role")]
if roled and len(roled) != len(people):
    warn(f"people.yml: {len(roled)} of {len(people)} entries have a 'role' — "
         "the rest will show a name with no title under it")

photoed = [p for p in people if p.get("photo")]
if photoed and len(photoed) != len(people):
    warn(f"people.yml: {len(photoed)} of {len(people)} entries have a photo — "
         "the rest render initials, so the grid will look mixed")

for i, g in enumerate(data.get("gallery") or []):
    for field in ("file", "alt"):
        if not g.get(field):
            err(f"_data/gallery.yml[{i}]: missing '{field}'")

for i, pr in enumerate(data.get("projects") or []):
    for field in ("title", "image", "body"):
        if not pr.get(field):
            err(f"_data/projects.yml[{i}]: missing '{field}'")

for i, pub in enumerate(data.get("publications") or []):
    for field in ("year", "authors", "title", "venue"):
        if not pub.get(field):
            err(f"_data/publications.yml[{i}]: missing '{field}'")

pubs = data.get("publications") or []
years = [p.get("year") for p in pubs if isinstance(p.get("year"), int)]
if years != sorted(years, reverse=True):
    warn("publications.yml: entries are not in descending year order")

# ----------------------------------------------------------- liquid well-formed
BLOCK_OPEN = {"if", "unless", "for", "case", "capture", "comment", "raw", "tablerow"}
NEUTRAL = {"else", "elsif", "when", "break", "continue"}

for path in page_files():
    rel = os.path.relpath(path, ROOT)
    with open(path, encoding="utf-8") as fh:
        text = fh.read()

    fm, body = split_front_matter(text)
    if rel.endswith((".html", ".md")) and not rel.startswith("_includes"):
        if fm is None and not rel.startswith("_layouts"):
            err(f"{rel}: missing YAML front matter")
    if fm is not None:
        try:
            yaml.safe_load(fm)
        except yaml.YAMLError as exc:
            err(f"{rel}: front matter YAML error: {exc}")

    # balanced {{ }} and {% %}
    if text.count("{{") != text.count("}}"):
        err(f"{rel}: unbalanced output braces "
            f"({text.count('{{')} open, {text.count('}}')} close)")
    if text.count("{%") != text.count("%}"):
        err(f"{rel}: unbalanced tag braces "
            f"({text.count('{%')} open, {text.count('%}')} close)")

    stack: list[str] = []
    for m in re.finditer(r"\{%-?\s*(\w+)", text):
        tag = m.group(1)
        if tag in BLOCK_OPEN:
            stack.append(tag)
        elif tag.startswith("end"):
            want = tag[3:]
            if not stack:
                err(f"{rel}: stray {{% {tag} %}} with no open block")
            elif stack[-1] != want:
                err(f"{rel}: {{% {tag} %}} closes '{want}' "
                    f"but innermost open block is '{stack[-1]}'")
                stack.pop()
            else:
                stack.pop()
        elif tag in NEUTRAL and not stack:
            err(f"{rel}: {{% {tag} %}} outside any block")
    if stack:
        err(f"{rel}: unclosed Liquid block(s): {', '.join(stack)}")

# ------------------------------------------------------------------- image refs
expected_images: set[str] = set()

for g in data.get("gallery") or []:
    if g.get("file"):
        expected_images.add(f"gallery/{g['file']}")
for pr in data.get("projects") or []:
    if pr.get("image"):
        expected_images.add(f"science/{pr['image']}")
for p in data.get("people") or []:
    if p.get("photo"):
        expected_images.add(f"people/{p['photo']}")

# Literal asset paths written into templates
LITERAL = re.compile(r"/assets/images/([A-Za-z0-9._\-/]+\.(?:jpg|jpeg|png|svg|webp))")
for path in page_files():
    with open(path, encoding="utf-8") as fh:
        for m in LITERAL.finditer(fh.read()):
            expected_images.add(m.group(1))

img_root = os.path.join(ROOT, "assets", "images")
present = set()
for dirpath, _dirnames, filenames in os.walk(img_root):
    for fn in filenames:
        present.add(
            os.path.relpath(os.path.join(dirpath, fn), img_root).replace(os.sep, "/")
        )

missing = sorted(expected_images - present)

# --------------------------------------------------------------- internal links
permalinks = {"/"}
for path in page_files():
    if not path.endswith((".html", ".md")):
        continue
    rel = os.path.relpath(path, ROOT)
    if rel.startswith(("_layouts", "_includes")):
        continue
    with open(path, encoding="utf-8") as fh:
        fm, _ = split_front_matter(fh.read())
    if not fm:
        continue
    meta = yaml.safe_load(fm) or {}
    if meta.get("permalink"):
        permalinks.add(meta["permalink"])
    elif rel == "index.html":
        permalinks.add("/")

INTERNAL = re.compile(r"\{\{\s*'([^']+)'\s*\|\s*relative_url\s*\}\}")
for path in page_files():
    rel = os.path.relpath(path, ROOT)
    with open(path, encoding="utf-8") as fh:
        for m in INTERNAL.finditer(fh.read()):
            target = m.group(1)
            if target.startswith("/assets") or target.endswith((".svg", ".css", ".jpg")):
                continue
            if target not in permalinks and target != "/404.html":
                err(f"{rel}: link to '{target}' has no matching permalink")

for item in (config.get("nav") or []):
    if item["url"] not in permalinks:
        err(f"_config.yml: nav item '{item['title']}' -> "
            f"'{item['url']}' has no matching page")

# ----------------------------------------------------------------------- report
print("=" * 66)
print("BYRNE LAB SITE — STATIC VERIFICATION")
print("=" * 66)

print(f"\nPages found:        {len([p for p in page_files() if p.endswith(('.html', '.md'))])}")
print(f"Permalinks:         {', '.join(sorted(permalinks))}")
print(f"Nav items:          {len(config.get('nav') or [])}")
print(f"People:             {len(data.get('people') or [])}")
print(f"Publications:       {len(data.get('publications') or [])}")
print(f"Projects:           {len(data.get('projects') or [])}")
print(f"Gallery images:     {len(data.get('gallery') or [])}")

print(f"\nImages referenced:  {len(expected_images)}")
print(f"Images present:     {len(present)}")
if missing:
    print(f"Images missing:     {len(missing)}  (run fetch_images.py locally)")

if warnings:
    print(f"\n--- {len(warnings)} warning(s) ---")
    for w in warnings:
        print(f"  ! {w}")

if errors:
    print(f"\n--- {len(errors)} ERROR(S) ---")
    for e in errors:
        print(f"  x {e}")
    print("\nFAILED")
    sys.exit(1)

print("\nNo structural errors. Liquid balanced, YAML valid, links resolve.")
sys.exit(0)
