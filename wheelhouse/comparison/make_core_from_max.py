#!/usr/bin/env python3
"""
Derive a variety wheel tree from an already-built `root_max` wheel tree.


  1. Reads the original core RECORD purely as a manifest (which paths to ship).
  2. Copies each manifest payload file out of the max tree.
  3. Maps `<core>.libs/...` manifest entries onto max's `<max>.libs/...` files
     and keeps them under the max name (RPATHs already point there).
  4. Regenerates the .dist-info from max's, renaming the directory, patching
     `Name:` in METADATA, patching the identity fields in the SBOM, copying
     WHEEL / entry_points / licenses verbatim, and writing a fresh RECORD.
  5. Preserves ROOT.modulemap from the build-option based wheel
  6. Drops modules.idx
"""
import argparse
import base64
import hashlib
import os
import re
import shutil
import sys
from pathlib import Path

DISTINFO_RE = re.compile(r"^[^/]+\.dist-info/")
LIBS_RE = re.compile(r"^[^/]+\.libs/")


def die(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def record_hash(path: Path):
    """Return (('sha256=<urlsafe-b64-nopad>'), size) exactly as wheels encode it."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    digest = base64.urlsafe_b64encode(h.digest()).rstrip(b"=").decode("ascii")
    return f"sha256={digest}", path.stat().st_size


def find_single(dirpath: Path, suffix: str):
    hits = sorted(p.name for p in dirpath.iterdir() if p.name.endswith(suffix))
    if len(hits) != 1:
        die(f"expected exactly one '*{suffix}' in {dirpath}, found: {hits}")
    return hits[0]


def parse_manifest_paths(record_path: Path):
    """Yield the relative path of each RECORD entry (first CSV field)."""
    with open(record_path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            yield line.rsplit(",", 2)[0]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", help="unpacked root_max wheel tree (source of all files)", type=Path)
    ap.add_argument("--manifest", help="original core RECORD, used only as the file manifest", type=Path)
    ap.add_argument("--modulemap", help="original core ROOT.modulemap, will be copied into new wheel", type=Path)
    ap.add_argument("--out", help="output directory for the derived core wheel tree")
    ap.add_argument("--new-name", help="distribution name (underscore form) for the result")
    ap.add_argument("--force", action="store_true",
                    help="overwrite --out if it already exists")
    args = ap.parse_args()

    src = Path(args.src).resolve()
    manifest = Path(args.manifest).resolve()
    out = Path(args.out).resolve()

    if not src.is_dir():
        die(f"--src is not a directory: {src}")
    if not manifest.is_file():
        die(f"--manifest is not a file: {manifest}")
    if out.exists():
        if not args.force:
            die(f"--out already exists (use --force to overwrite): {out}")
        shutil.rmtree(out)

    # Discover max's identity from its own tree.
    src_distinfo = find_single(src, ".dist-info")          # e.g. root_max-0.1a14.dist-info
    src_libs = find_single(src, ".libs")                   # e.g. root_max.libs
    m = re.match(r"^(?P<name>.+)-(?P<ver>[^-]+)\.dist-info$", src_distinfo)
    if not m:
        die(f"cannot parse name/version from dist-info dir: {src_distinfo}")
    old_us = m.group("name")                               # root_max
    version = m.group("ver")                               # 0.1a14
    new_us = args.new_name                                 # root_core
    old_hy = old_us.replace("_", "-")                      # root-max
    new_hy = new_us.replace("_", "-")                      # root-core
    new_distinfo = f"{new_us}-{version}.dist-info"

    print(f"source wheel : {old_us} {version}   ({src})")
    print(f"target wheel : {new_us} {version}   ({out})")
    print(f"bundled libs : keeping '{src_libs}' (RPATHs already point there)")
    print()

    out.mkdir(parents=True)

    # copy files listed in core's RECORD manifest out of max and into new dir
    n_payload = n_libs = 0
    missing = []
    for rel in parse_manifest_paths(manifest):
        if DISTINFO_RE.match(rel):
            continue  # dist-info is regenerated below
        elif "modules.idx" in rel:
            continue  # drop the modules index; rebuilt at launch
        elif LIBS_RE.match(rel):
            # keep max's .libs to avoid patchelfing new rpaths
            tail = rel.split("/", 1)[1]
            source = src / src_libs / tail
            dest = out / src_libs / tail
            n_libs += 1
        elif "ROOT.modulemap" in rel:
            source = args.modulemap
            dest = out / rel
            n_payload += 1
        else:
            source = src / rel
            dest = out / rel
            n_payload += 1
        if not source.is_file():
            missing.append((rel, source))
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)

    if missing:
        print(f"error: {len(missing)} manifest file(s) not found in --src:",
              file=sys.stderr)
        for rel, source in missing[:25]:
            print(f"    {rel}  ->  {source}", file=sys.stderr)
        if len(missing) > 25:
            print(f"    ... and {len(missing) - 25} more", file=sys.stderr)
        die("aborting; the max tree does not contain every manifest file")

    print(f"copied {n_payload} payload files + {n_libs} bundled-lib files")

    # path max's .dist-info to report new wheel's metadata correctly
    src_di = src / src_distinfo
    dst_di = out / new_distinfo
    dst_di.mkdir(parents=True)

    for child in sorted(src_di.rglob("*")):
        if child.name == "RECORD":
            continue  # written last, from the finished tree
        target = dst_di / child.relative_to(src_di)
        if child.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)

        if child.name == "METADATA":
            text = child.read_text(encoding="utf-8")
            new_text, n = re.subn(rf"^Name: {re.escape(old_hy)}\s*$",
                                  f"Name: {new_hy}", text, count=1,
                                  flags=re.MULTILINE)
            if n != 1:
                die(f"did not find a 'Name: {old_hy}' line in METADATA to patch")
            target.write_text(new_text, encoding="utf-8")
            print(f"METADATA     : Name: {old_hy} -> {new_hy}")
        elif child.suffix == ".json" and "sbom" in child.parent.name:
            # SBOM identity fields (name / bom-ref / purl / file_name) all carry
            # the underscore form; bundled-system-lib refs never do.
            text = child.read_text(encoding="utf-8")
            new_text = text.replace(old_us, new_us)
            target.write_text(new_text, encoding="utf-8")
            print(f"SBOM         : {child.name}: {old_us} -> {new_us} "
                  f"({text.count(old_us)} refs)")
        else:
            shutil.copy2(child, target)  # WHEEL, entry_points.txt, licenses/* verbatim

    # write a fresh RECORD covering the finished tree
    record_lines = []
    record_rel = f"{new_distinfo}/RECORD"
    for path in sorted(out.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(out).as_posix()
        if rel == record_rel:
            continue
        h, size = record_hash(path)
        record_lines.append(f"{rel},{h},{size}")
    record_lines.append(f"{record_rel},,")  # RECORD lists itself with no hash

    (dst_di / "RECORD").write_text("\n".join(record_lines) + "\n", encoding="utf-8")
    print(f"RECORD       : {len(record_lines)} entries "
          f"(recomputed from copied bytes)")

    print()
    print(f"done -> {out}")
    print("pack into an installable wheel with:")
    print(f"    python -m wheel pack {out}")


if __name__ == "__main__":
    main()
