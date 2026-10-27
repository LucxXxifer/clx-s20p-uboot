#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Materialize an exact upstream commit and apply the reviewed GPT patch."""
import argparse
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile

from verify_build import require, sha, source_reviewed

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATHS = ("build.sh", "uboot-mtk-20250711", "atf-20260123",
                "atf-20240117-bacca82a8/configs")
MMC_PATH = "uboot-mtk-20250711/board/mediatek/common/mmc_helper.c"


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def extract_source(archive, destination):
    """Extract files first, then create only links contained in the source root.

    Python tarfile filter backports differ in handling relative directory links.
    Never allow an archive member to be written through an archive symlink.
    """
    destination = destination.resolve()
    require(not any(destination.iterdir()), "Extraction root must be empty")
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
        members = bundle.getmembers()
        links = {member.name for member in members if member.issym()}
        names = set()
        for member in members:
            path = Path(member.name)
            require(not path.is_absolute() and ".." not in path.parts and
                    member.name not in names and
                    all(str(parent) not in links for parent in path.parents),
                    "Unsafe or duplicated archive path: " + member.name)
            require(member.isfile() or member.isdir() or member.issym(),
                    "Unsupported archive member: " + member.name)
            names.add(member.name)
        # No archive links exist while regular files are extracted.
        bundle.extractall(destination, members=[m for m in members if not m.issym()],
                          filter="data")
        for member in members:
            if not member.issym():
                continue
            link = destination / member.name
            target = (link.parent / member.linkname).resolve()
            require(not Path(member.linkname).is_absolute() and
                    target.is_relative_to(destination), "External archive symlink: " + member.name)
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(member.linkname)


def prepare(target, destination):
    lock = json.loads((ROOT / "ci/source.lock.json").read_text())
    reviewed = source_reviewed(lock["upstream_sha"], target)
    require(not destination.exists(), "Source destination must not already exist")
    if subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", target + "^{commit}"],
                      capture_output=True).returncode:
        git("fetch", "--no-tags", "--depth=100", lock["upstream_url"], target)
    if subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e",
                       lock["upstream_sha"] + "^{commit}"], capture_output=True).returncode:
        git("fetch", "--no-tags", "--depth=1", lock["upstream_url"], lock["upstream_sha"])
    destination.mkdir(parents=True)
    archive = git("archive", "--format=tar", target, *SOURCE_PATHS)
    extract_source(archive, destination)
    for name, expected in lock["input_sha256"].items():
        require(sha((destination / name).read_bytes()) == expected,
                "Reviewed build input changed; review and update lock: " + name)
    patch = ROOT / "ci/patches/s20p-gpt.patch"
    env = {**os.environ, "GIT_CEILING_DIRECTORIES": str(destination.parent)}
    for options in (("--check",), ()):
        subprocess.run(["git", "apply", "--whitespace=error-all", *options, str(patch)],
                       cwd=destination, env=env, check=True)
    if reviewed:
        require((destination / MMC_PATH).read_bytes() == git("show", "HEAD:" + MMC_PATH),
                "Checked-in repair and maintained patch differ")
    changed = git("diff", "--name-only", lock["upstream_sha"], target).decode().splitlines()
    report = {"schema": 1, "upstream_sha": target,
              "reviewed_upstream_sha": lock["upstream_sha"], "source_reviewed": reviewed,
              "upstream_url": lock["upstream_url"], "patch_sha256": sha(patch.read_bytes()),
              "patched_mmc_sha256": sha((destination / MMC_PATH).read_bytes()),
              "lock_sha256": sha((ROOT / "ci/source.lock.json").read_bytes()),
              "source_date_epoch": int(git("show", "-s", "--format=%ct", target)),
              "board": lock["board"], "version": lock["version"],
              "changed_upstream_paths": changed,
              "compare_url": "https://github.com/Yuzhii0718/bl-mt798x-dhcpd/compare/" +
                             lock["upstream_sha"] + "..." + target}
    (destination / "source.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    report = prepare(args.sha, args.destination.resolve())
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
