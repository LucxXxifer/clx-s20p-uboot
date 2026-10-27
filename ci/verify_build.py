#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Independent FIP, configuration, provenance and reproducibility gates."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import zlib

BL31 = "47d4086d4cfe98469b952950cbbd5a00"
BL33 = "d6d0eea7fcead54b97829934f234b6e4"
CHECKSUM = "a2cceab7f8254b279704633a6fd69ad8"
FILES = ("fip.bin", "bl31.bin", "u-boot.bin", "u-boot.dtb", "uboot.config",
         "atf.config", "dtb-memory.txt", "toolchain.txt", "source.json")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def source_reviewed(approved, target):
    for value in (approved, target):
        require(re.fullmatch(r"[0-9a-f]{40}", value) is not None,
                "Source must be an exact lowercase 40-character commit SHA")
    return approved == target


def inspect_fip(payload, bl31, bl33):
    require(176 < len(payload) <= 2 * 1024 * 1024, "FIP size outside S20P candidate limit")
    magic, serial, flags = struct.unpack_from("<IIQ", payload)
    require(magic == 0xAA640001 and serial == 0x12345678 and flags == 0,
            "Unexpected FIP header")
    entries, ranges = {}, []
    for offset in (16, 56, 96):
        uid = payload[offset:offset + 16].hex()
        start, size, flags = struct.unpack_from("<QQQ", payload, offset + 16)
        require(uid in (BL31, BL33, CHECKSUM) and uid not in entries,
                "Unexpected or duplicated FIP component")
        require(start >= 176 and start % 8 == 0 and size > 0 and
                start + size <= len(payload) and flags == 0,
                "FIP component outside file or unsupported flags")
        require(not any(start < end and begin < start + size for begin, end in ranges),
                "Overlapping FIP components")
        ranges.append((start, start + size))
        entries[uid] = {"offset": start, "bytes": size,
                        "sha256": sha(payload[start:start + size])}
    null_uid = payload[136:152]
    end, size, flags = struct.unpack_from("<QQQ", payload, 152)
    require(null_uid == bytes(16) and (end, size, flags) == (len(payload), 0, 0),
            "Invalid FIP terminator or trailing data")
    for uid, expected in ((BL31, bl31), (BL33, bl33)):
        item = entries[uid]
        require(payload[item["offset"]:item["offset"] + item["bytes"]] == expected,
                "FIP payload differs from the compiled component")
    item = entries[CHECKSUM]
    require(item["bytes"] == 40 and item["offset"] + 40 == len(payload),
            "Unexpected MediaTek checksum component")
    length, crc, digest = struct.unpack_from("<II32s", payload, item["offset"])
    prefix = payload[:item["offset"]]
    require(length == len(prefix) and crc == zlib.crc32(prefix) and
            digest == hashlib.sha256(prefix).digest(), "MediaTek internal checksum mismatch")
    return entries


def verify_directory(directory):
    directory = Path(directory)
    data = {name: (directory / name).read_bytes() for name in FILES}
    components = inspect_fip(data["fip.bin"], data["bl31.bin"], data["u-boot.bin"])
    require(len(data["u-boot.dtb"]) > 40 and data["u-boot.dtb"] in data["u-boot.bin"],
            "Checked board DTB is not embedded in BL33")
    require(data["dtb-memory.txt"].decode().strip() == "40000000 80000000",
            "Expected 2-GiB board memory map")
    cfg = set(data["uboot.config"].decode().splitlines())
    expected = {'CONFIG_DEFAULT_DEVICE_TREE="mt7986a-clx_s20"',
                'CONFIG_IPADDR="192.168.1.1"', "CONFIG_TARGET_MT7986=y",
                "CONFIG_MMC_MTK=y", "CONFIG_MTK_WEB_FAILSAFE=y",
                "CONFIG_WEBUI_FAILSAFE_GPT=y", "CONFIG_MTK_DHCPD=y",
                "CONFIG_ENV_IS_IN_MMC=y", "CONFIG_OF_EMBED=y"}
    require(expected <= cfg, "Missing expected S20P/recovery/GPT configuration")
    atf = set(data["atf.config"].decode().splitlines())
    require({"_PLAT_MT7986=y", "_DRAM_DDR4=y", "_BOOT_DEVICE_EMMC=y"} <= atf,
            "Missing expected S20P ATF platform/memory/storage configuration")
    require(not {"_ENABLE_FIP_COMPRESS=y", "FIP_COMPRESS=1"} & atf,
            "Expected uncompressed FIP configuration")
    source = json.loads(data["source.json"])
    source_reviewed(source["reviewed_upstream_sha"], source["upstream_sha"])
    require(source["board"] == "mt7986_clx_s20" and source["version"] == "SP2",
            "Wrong source board/version")
    report = {"schema": 1, "source": source, "components": components,
              "files": {name: {"sha256": sha(value), "bytes": len(value)}
                        for name, value in data.items()},
              "hardware_boot_tested": False, "hardware_gpt_write_tested": False,
              "factory_restore_tested": False}
    return report


def compare_directories(left, right):
    a, b = verify_directory(left), verify_directory(right)
    require(a == b, "Independent clean builds differ; do not publish")
    a["independent_matching_builds"] = 2
    return a


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--compare", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = (compare_directories(args.directory, args.compare) if args.compare
              else verify_directory(args.directory))
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"fip_sha256": report["files"]["fip.bin"]["sha256"],
                      "matching_builds": report.get("independent_matching_builds", 1)}))


if __name__ == "__main__":
    main()
