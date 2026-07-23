import argparse
import base64
import csv
import hashlib
import sys
from importlib.metadata import Distribution
from pathlib import Path


def dist_info_dir(wheel_dir):
    infos = list(wheel_dir.glob("*.dist-info"))
    if len(infos) != 1:
        sys.exit(f"error: expected one *.dist-info in {wheel_dir}, found {len(infos)}")
    return infos[0]


def manifest(dist_info):
    files = Distribution.at(dist_info).files
    if files is None:
        sys.exit(f"error: no readable RECORD in {dist_info}")
    prefix = dist_info.name + "/"
    # ignore .dist-info components
    return {str(f): f.hash.value
            for f in files if f.hash and not str(f).startswith(prefix) and f.name != "modules.idx"}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("core_dir", type=Path)
    ap.add_argument("advanced_dir", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--ignore-hashes", action="store_true")
    ap.add_argument("--preserve-pcms", action="store_true")
    ap.add_argument("--preserve-mod-maps", action="store_true")
    args = ap.parse_args()

    adv_dir = args.advanced_dir
    adv_info = dist_info_dir(adv_dir)
    core = manifest(dist_info_dir(args.core_dir))
    adv = manifest(adv_info)

    both = core.keys() & adv.keys()
    intersection = sorted(both)
    pcms = set(p for p in both if ".pcm" in p)
    module_maps = set(p for p in both if ".modulemap" in p)
    hash_matches = sorted(p for p in both if core[p] == adv[p])
    conflicts = sorted(p for p in both if core[p] != adv[p])

    print(module_maps)
    # delete modules.idx from both dirs
    if not args.dry_run:
        print("deleting modules.idx from both unpacked wheels...") 
        (args.core_dir / "ROOT/lib/modules.idx").unlink(missing_ok=True)
        (args.advanced_dir / "ROOT/lib/modules.idx").unlink(missing_ok=True)

    # optionally disable hash equivalence check and rely only on path equivalence
    shared = intersection if args.ignore_hashes else hash_matches 

    # delete shared files and prune newly-empty directories
    if not args.dry_run:
        for rel in shared:
            if args.preserve_pcms and rel in pcms:
                continue
            if args.preserve_mod_maps and rel in module_maps:
                continue
            (adv_dir / rel).unlink()
        for d in sorted((p for p in adv_dir.rglob("*") if p.is_dir()),
                        key=lambda p: len(p.parts), reverse=True):
            try:
                d.rmdir()  # succeeds only if empty
            except OSError:
                pass

    # rewrite RECORD without the deleted rows
    record = adv_info / "RECORD"
    rows = [r for r in csv.reader(record.read_text().splitlines())
            if r and r[0] not in set(shared) or (args.preserve_pcms and r[0] in pcms) or (args.preserve_mod_maps and r[0] in module_maps)]

    if not args.dry_run:
        with record.open("w", newline="") as f:
            csv.writer(f, lineterminator="\n").writerows(rows)

    verb = "would delete" if args.dry_run else "deleted"
    count = len(shared)
    if args.preserve_pcms:
        print(f"preserving {len(pcms)} PCMs") 
        count = len(set(shared) - pcms)
    if args.preserve_mod_maps:
        print(f"preserving {len(module_maps)} module maps")
        count = len(set(shared) - module_maps)
    print(f"{verb} {count} shared file(s) from {adv_dir}")
    if conflicts and not args.ignore_hashes:
        print(f"WARNING: kept {len(conflicts)} file(s) present in both "
              "wheels with different hashes:")
        for p in conflicts:
            print(f"  ~ {p}")
    if not args.dry_run:
        print(f"done — now run: wheel pack {adv_dir}")


if __name__ == "__main__":
    main()
