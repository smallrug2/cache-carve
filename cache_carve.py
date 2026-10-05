"""Carve JPEG and PNG images out of opaque cache files.

Scans every file in --indir for JPEG (FFD8..FFD9) and PNG
(signature..IEND) blobs and writes blobs meeting the size threshold
to --outdir.

Usage:
  python cache_carve.py --indir DIR --outdir DIR [--min-kb 50]

Platform notes: cross-platform (Windows + Linux), stdlib only.
Pillow is used for verification only if already installed
(try/except import; verification is skipped when missing).
"""
import argparse
import sys
from pathlib import Path

JPEG_SOI = b"\xff\xd8\xff"
JPEG_EOI = b"\xff\xd9"
PNG_SIG = b"\x89PNG\r\n\x1a\n"
PNG_IEND = b"IEND\xaeB`\x82"  # "IEND" + CRC (8 bytes total)

try:
    from PIL import Image  # optional: verify only
    import io as _io
    _HAVE_PIL = True
except Exception:
    _HAVE_PIL = False


def default_indir():
    return str(Path.home() / "cache")


def default_outdir():
    return str(Path.home() / "carved")


def valid_image(blob: bytes, ext: str):
    """Return True if blob looks like a real image.

    Without Pillow: accept by magic bytes only. With Pillow: open + load.
    """
    if not _HAVE_PIL:
        return True
    try:
        im = _io.BytesIO(blob)
        with Image.open(im) as pic:
            pic.load()
        return True
    except Exception:
        return False


def carve_jpegs(data: bytes, min_bytes: int):
    """Yield JPEG blobs (SOI..EOI inclusive) meeting min size."""
    blobs = []
    idx = 0
    while True:
        s = data.find(JPEG_SOI, idx)
        if s < 0:
            break
        e = data.find(JPEG_EOI, s + 2)
        if e < 0:
            break
        blob = data[s:e + 2]
        idx = e + 2
        if len(blob) >= min_bytes:
            blobs.append(blob)
        if len(blobs) > 10000:  # bound runaway files
            break
    return blobs


def carve_pngs(data: bytes, min_bytes: int):
    """Yield PNG blobs (signature..IEND+CRC) meeting min size."""
    blobs = []
    idx = 0
    while True:
        s = data.find(PNG_SIG, idx)
        if s < 0:
            break
        e = data.find(PNG_IEND, s + len(PNG_SIG))
        if e < 0:
            break
        # e points at "IEND"; blob ends after IEND + 4-byte CRC.
        blob = data[s:e + 8]
        idx = e + len(PNG_IEND)
        if len(blob) >= min_bytes:
            blobs.append(blob)
        if len(blobs) > 10000:
            break
    return blobs


def main(argv=None):
    ap = argparse.ArgumentParser(description="Carve JPEG/PNG blobs from cache files.")
    ap.add_argument("--indir", default=default_indir(), help="input cache dir")
    ap.add_argument("--outdir", default=default_outdir(), help="output dir for carved images")
    ap.add_argument("--min-kb", type=float, default=50,
                    help="minimum blob size in KiB (default 50)")
    args = ap.parse_args(argv)

    indir, outdir = Path(args.indir), Path(args.outdir)
    if not indir.is_dir():
        print("error: not a directory: %s" % indir, file=sys.stderr)
        return 2
    try:
        outdir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print("error: cannot create outdir %s: %s" % (outdir, e), file=sys.stderr)
        return 2
    min_bytes = int(args.min_kb * 1024)
    print("Pillow verification: %s" % ("on" if _HAVE_PIL else "off (not installed)"))

    found = []
    files = [p for p in indir.iterdir() if p.is_file()]
    for fp in sorted(files):
        try:
            data = fp.read_bytes()
        except OSError as e:
            print("skip %s: %s" % (fp.name, e))
            continue
        if len(data) < min_bytes:
            continue
        n = 0
        for blob in carve_jpegs(data, min_bytes):
            if not valid_image(blob, ".jpg"):
                continue
            dest = outdir / ("%s_%d.jpg" % (fp.name, n))
            try:
                dest.write_bytes(blob)
            except OSError as e:
                print("skip write %s: %s" % (dest, e))
                continue
            found.append((str(dest), len(blob)))
            n += 1
        for blob in carve_pngs(data, min_bytes):
            if not valid_image(blob, ".png"):
                continue
            dest = outdir / ("%s_p%d.png" % (fp.name, n))
            try:
                dest.write_bytes(blob)
            except OSError as e:
                print("skip write %s: %s" % (dest, e))
                continue
            found.append((str(dest), len(blob)))
            n += 1
    print("CARVED: %d image(s)" % len(found))
    for p, size in sorted(found, key=lambda t: -t[1]):
        print("  %s (%d bytes)" % (p, size))
    return 0


if __name__ == "__main__":
    sys.exit(main())
