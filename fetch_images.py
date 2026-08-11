"""Download Byrne Lab images from the Squarespace CDN and optimize them.

Squarespace serves originals far larger than needed. We request a bounded
format and re-encode to progressive JPEG at a sane max dimension.
"""
import os
import sys
import urllib.request
from io import BytesIO

from PIL import Image, ImageOps

BASE = "https://images.squarespace-cdn.com/content/v1/64cd4f1ab87223731f867096/"
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "images")

# (subdir, output stem, cdn path, max width)
IMAGES = [
    # Home hero + mosaic gallery
    ("", "hero-fovea", "6cf6b07b-02d6-4008-9e24-8d0a53cd49b5/fovea1.jpg", 2000),
    ("gallery", "supp-fig-jb", "e86016fd-8914-437e-b76a-0ceafc56c75f/Supp+Fig+JB.jpg", 1400),
    ("gallery", "aav", "f8341cd9-d08d-4ddf-b0d8-779fbc903847/AAV.png", 1400),
    ("gallery", "retina-section", "31a45a34-3fe3-4a32-bf00-3f346382fbcc/10X%2Bsnap%2BDAPI_CAR594_PKCa_488_section%2B14_001.jpeg", 1400),
    ("gallery", "mosaic", "8f0ae872-6f07-4823-ba2e-635eebcc3d84/Leah%2B%236_mosaic%2B85x11.jpg", 1400),
    ("gallery", "capsid", "dc9cd937-5f22-4298-88a7-ad9cc4a84a67/image1.png", 1400),
    ("gallery", "umap", "e58b565c-37ce-426e-99f8-ca4cf2193d1f/umap.jpg", 1400),
    ("gallery", "cones", "114a0fe8-f47b-4bd9-8c33-333ec7514062/CONES_1.jpg", 1400),
    ("gallery", "mol-ther-cover", "9388871f-0628-48aa-b47c-c2e746ca6d90/Mol%2BTher%2Bcover%2Bimage%2Bv2w.jpg", 1400),
    ("gallery", "mouse-retina-3", "b4b7d754-4330-4af6-93d7-544ca9540927/mouse%2Bretina%2B3.jpg", 1400),
    ("gallery", "k9-library", "6108fd4b-ba2f-4767-877c-a9ee5ef88e44/K9_library.jpg", 1400),
    ("gallery", "two-minute", "532ba898-e77b-4e11-a40e-5f00b9549321/2-minute_Byrne_Lab.jpg", 1400),
    ("gallery", "mouse-retina-2", "9d24247c-c351-468c-8975-81ebdea194ce/mouse%2Bretina%2B2.jpg", 1400),
    ("gallery", "dual-injections", "2f0e4fb7-0d21-4b1f-a627-5e402f5efb47/Dual%2Binjections%2B10X%2Bzoomed%2Bout%2Bsnap%2BDAPI%2BeGFP%2BmCherry%2Badjusted.jpg", 1400),
    ("gallery", "rpe", "36b9d5a3-da73-404d-9d76-04dc25874953/RPE.jpg", 1400),
    ("gallery", "k912-montage", "7b1803c3-d0d4-45bf-9304-af6d92e23692/K912%2Bmontage_FINALs.jpg", 1400),
    # Science page
    ("science", "gene-therapy", "114a0fe8-f47b-4bd9-8c33-333ec7514062/CONES_1.jpg", 1200),
    ("science", "vector-design", "7ad05bb6-1bdf-4732-8c34-dc46a24c618b/image1.jpg", 1200),
    ("science", "aav-database", "e58b565c-37ce-426e-99f8-ca4cf2193d1f/umap.jpg", 1200),
    # People
    ("people", "alessandra-larimer-picciani", "324d0373-47be-4c3f-b340-cdd7df80f8af/Ali.jpeg", 700),
    ("people", "anfisa-ayalon", "b84eabc7-8c51-40f4-bf8f-7a335d24e713/Anfisa.jpeg", 700),
    ("people", "aman-virmani", "8a9c31de-d3af-442c-acbe-ba161ef0356b/Aman.jpg", 700),
    ("people", "katelin-samski", "8f99cbeb-ba01-44e7-a429-742ce19d14b3/Katelin.jpg", 700),
    ("people", "hamzah-aweidah", "a8d90f64-3479-441c-8c74-805d8e0c630e/Hamzah.jpeg", 700),
    ("people", "lora-waybright", "f4510d9f-48ce-4ebc-b276-293708c2104e/Lora_close.jpg", 700),
    ("people", "sushma-sappa", "84b40c34-8c50-4280-8bbf-2883e0629ebb/Sushma.jpg", 700),
    ("people", "avigail-beryozkin", "1abff9a4-74e5-486d-b595-6f2da187d7f4/Avi.jpg", 700),
    ("people", "max-lohss", "6150ae96-dfbc-4b07-a25e-6fcf4037ddaa/Max.jpg", 700),
    ("people", "jean-baptiste-couzy", "e88445c6-4385-44b5-a27a-de6f238d1895/JB.jpeg", 700),
    ("people", "wyatt-kriebel", "8ae55d52-e84d-410e-8ec3-ce3f0f40da4b/Wyatt.jpeg", 700),
    ("people", "annapurni-sriram", "07a6c2cd-02cc-4e5a-b873-ac586a90a2ab/IMG_5873.jpg", 700),
    ("people", "mahija-nukala", "1693c094-1d00-47ac-99f3-2b52813f66ac/Mahija.jpeg", 700),
    # Join
    ("", "mercy-pavilion", "54fbd815-1796-47bc-9f17-e74648267597/mercy%2Bpavillion.jpeg", 1600),
    # Publication thumbnails. These were the per-paper figures on the
    # Squarespace publications page — the lab's own choice of panel for each
    # paper, which is why they're worth preserving rather than re-deriving.
    ("pubs", "frontiers-young-minds", "3d1acbac-506e-42d5-89fd-851fc330698f/FYM.jpeg", 1000),
    ("pubs", "rdcvf", "d4a69c39-2857-4b14-845f-cd0fd76bef7f/rdcvf.jpg", 1000),
    ("pubs", "umap", "e58b565c-37ce-426e-99f8-ca4cf2193d1f/umap.jpg", 1000),
    ("pubs", "2023-aweidah", "e2c7fbda-1e72-4517-aa68-8706f83bd947/Figure+3.jpg", 800),
    ("pubs", "2023-lohss-clamp", "ed3e7b56-af94-4578-8102-5ab8b41f8132/clamp.jpg", 800),
    ("pubs", "2023-zin", "14b7ef84-11b8-48ca-87e6-ecd73ec1ff9e/fig.png", 800),
    ("pubs", "2022-xi-erg", "0a1b3f2b-fb51-4fa8-8e47-edf869a5e7c4/erg.png", 800),
    ("pubs", "2022-rodrigues-organoid", "9b24c974-c78f-41c3-a495-f89e8c661126/organoid.png", 800),
    ("pubs", "2022-xi-retina", "b37aac59-1745-48f2-93a5-e7f47b7b2e32/retina.png", 800),
    ("pubs", "2022-lawler", "9aa21ea4-e59c-4afd-9f4f-6701c3a760cc/fig1.png", 800),
    ("pubs", "2022-miyadera", "754cbd2a-1610-452d-8604-16abb12c0bc4/invert.png", 800),
    ("pubs", "2021-he-striatum", "dbd4ac40-6e3c-424e-be7a-6fd3081b1881/nudap.png", 800),
    ("pubs", "2021-gemayel", "5a4beeca-ec3b-467a-a641-1a7b4bbd7974/Picture1.jpg", 800),
    ("pubs", "2020-byrne-fovea", "dca86098-76d3-4b9e-b3e7-21c62bdbc031/fov.png", 800),
    ("pubs", "2018-day-nab", "09a99785-09d8-41be-b1c4-a86f980e8ebe/nab.png", 800),
    ("pubs", "2015-byrne-aav9",
     "575e4bcb-725b-4f11-b97d-e7cca7bffc70/Dual+injections+10X+zoomed+out+snap+DAPI%2BeGFP%2BmCherry+adjusted.jpg", 800),
    ("pubs", "2015-byrne-rdcvf-cones", "05ede9fe-3d37-49b2-baef-c26169bf9cef/cones.png", 800),
    ("pubs", "2014-byrne-rs1h", "5bce5079-421b-482b-a072-b5a7c340d567/rs1h.jpg", 800),
    ("pubs", "2014-day-virus", "4015fc46-333a-4d8c-a564-229ae24dbcee/virus.png", 800),
    ("pubs", "2013-dalkara-7m8", "4f2f21c3-3585-4b71-b16b-44d51aedddbf/7m8.png", 800),
    # PGTB
    ("pgtb", "logo", "9ab77d0c-9db3-442e-9622-c5d24f0aaca4/logo%2B3.jpg", 1200),
    ("pgtb", "flyer", "cfb9285e-9c62-45b6-9d24-84ca842c4349/FINAL%2BGeneTherapyBootcampFlyer_2024.jpg", 1400),
    ("pgtb", "cohort", "b2e5a301-7b45-4b93-a0c3-84319a248419/309058123_458519709642372_2783298561289825940_n.jpg", 1200),
    ("pgtb", "pittwire", "a4fb6f52-842b-4711-9e26-1fcb8a54e7e0/pittwir.png", 1000),
]

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) byrnelab-migration"}


class AlreadyHave(Exception):
    """Raised when the file is already on disk, so re-runs stay cheap."""


def fetch(path: str) -> bytes:
    url = BASE + path + "?format=2500w"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=90) as resp:
        return resp.read()


def process(subdir: str, stem: str, path: str, max_w: int) -> str:
    outdir = os.path.join(ROOT, subdir) if subdir else ROOT
    os.makedirs(outdir, exist_ok=True)

    out_existing = os.path.join(outdir, stem + ".jpg")
    if os.path.exists(out_existing) and os.path.getsize(out_existing) > 0:
        # Already downloaded — re-running should only pick up what's new.
        raise AlreadyHave(out_existing)

    raw = fetch(path)
    img = Image.open(BytesIO(raw))
    img = ImageOps.exif_transpose(img)

    has_alpha = img.mode in ("RGBA", "LA") or (
        img.mode == "P" and "transparency" in img.info
    )
    if has_alpha:
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img.convert("RGBA"), mask=img.convert("RGBA").split()[-1])
        img = bg
    else:
        img = img.convert("RGB")

    if img.width > max_w:
        h = round(img.height * max_w / img.width)
        img = img.resize((max_w, h), Image.LANCZOS)

    out = os.path.join(outdir, stem + ".jpg")
    img.save(out, "JPEG", quality=82, optimize=True, progressive=True)
    return out


def main() -> int:
    failures, skipped = [], 0
    total = 0
    for subdir, stem, path, max_w in IMAGES:
        try:
            out = process(subdir, stem, path, max_w)
            size = os.path.getsize(out)
            total += size
            rel = os.path.relpath(out, ROOT)
            print(f"ok    {rel:52s} {size/1024:8.0f} KB")
        except AlreadyHave:
            skipped += 1
        except Exception as exc:  # noqa: BLE001
            failures.append((stem, exc))
            print(f"FAIL  {stem:52s} {exc}")

    fetched = len(IMAGES) - len(failures) - skipped
    print(f"\n{fetched} new, {skipped} already present, {len(failures)} failed "
          f"({len(IMAGES)} total) — {total/1024/1024:.1f} MB downloaded")
    if failures:
        print("\nFailed:")
        for stem, exc in failures:
            print(f"  {stem}: {exc}")
        print("\nIf these are 403s, the Squarespace site may already be cancelled.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
