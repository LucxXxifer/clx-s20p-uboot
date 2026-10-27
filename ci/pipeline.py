#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Trusted pipeline orchestration; image builds never receive write credentials."""
import argparse
import json
from pathlib import Path
import shutil

from verify_build import compare_directories, require, sha, source_reviewed

ROOT = Path(__file__).resolve().parents[1]


def release_files(left, right, target, destination):
    lock_bytes = (ROOT / "ci/source.lock.json").read_bytes()
    lock = json.loads(lock_bytes)
    require(source_reviewed(lock["upstream_sha"], target),
            "Upstream SHA has not been reviewed; publish reports only")
    report = compare_directories(left, right)
    source = report["source"]
    require(source["upstream_sha"] == target and source["source_reviewed"] is True and
            source["reviewed_upstream_sha"] == target and
            source["lock_sha256"] == sha(lock_bytes) and
            source["patch_sha256"] == sha((ROOT / "ci/patches/s20p-gpt.patch").read_bytes()) and
            source["patched_mmc_sha256"] == sha((ROOT /
                "uboot-mtk-20250711/board/mediatek/common/mmc_helper.c").read_bytes()),
            "Artifact provenance does not match trusted source/patch/lock")
    destination.mkdir(parents=True, exist_ok=False)
    name = "fip-clx-s20p-2g-emmc-SP2-gptfix-" + target[:12] + ".bin"
    shutil.copyfile(left / "fip.bin", destination / name)
    (destination / "audit.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    shutil.copyfile(ROOT / "ci/source.lock.json", destination / "source.lock.json")
    (destination / "RELEASE-NOTES.md").write_text(
        "# CLX-S20P FIP candidate\n\n"
        "MT7986A / 2-GiB DDR4 / eMMC, SP2; FIP only. No BL2.\n\n"
        "Repairs secondary GPT alternate_lba and rejects malformed primary GPT uploads "
        "before writes. Partition entries are preserved. Two clean builds match; "
        "native C regression tests run under ASan/UBSan.\n\n"
        "**Prerelease: physical boot, Reset recovery, GPT write/readback, firmware boot "
        "and factory restore have not been tested with this image.** Updating FIP does "
        "not repair a previously invalid on-disk GPT. Keep per-unit recovery backups.\n\n"
        f"Upstream: `{target}`\n\n"
        f"FIP SHA-256: `{report['files']['fip.bin']['sha256']}`\n")
    names = sorted(p.name for p in destination.iterdir() if p.is_file())
    (destination / "SHA256SUMS").write_text("".join(
        sha((destination / name).read_bytes()) + "  " + name + "\n" for name in names))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left", type=Path, required=True)
    parser.add_argument("--right", type=Path, required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    result = release_files(args.left, args.right, args.sha, args.destination)
    print(json.dumps({"fip_sha256": result["files"]["fip.bin"]["sha256"],
                      "independent_matching_builds": 2}))


if __name__ == "__main__":
    main()
