# SPDX-License-Identifier: GPL-2.0
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BL31 = "47d4086d4cfe98469b952950cbbd5a00"
BL33 = "d6d0eea7fcead54b97829934f234b6e4"
CHECKSUM = "a2cceab7f8254b279704633a6fd69ad8"


def fixture(dtb=b""):
    bl31, bl33 = b"A" * 512, b"B" * 8192 + dtb
    pos = 176
    toc = bytearray(struct.pack("<IIQ", 0xAA640001, 0x12345678, 0))
    for uid, data in ((BL31, bl31), (BL33, bl33), (CHECKSUM, bytes(40))):
        toc += bytes.fromhex(uid) + struct.pack("<QQQ", pos, len(data), 0)
        pos += len(data)
    toc += bytes(16) + struct.pack("<QQQ", pos, 0, 0)
    prefix = bytes(toc) + bl31 + bl33
    checksum = struct.pack("<II32s", len(prefix), zlib.crc32(prefix),
                           hashlib.sha256(prefix).digest())
    return prefix + checksum, bl31, bl33


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.verify = importlib.import_module("verify_build")

    def test_valid_mediatek_fip_checks_internal_hash_and_payloads(self):
        payload, bl31, bl33 = fixture()
        entries = self.verify.inspect_fip(payload, bl31, bl33)
        self.assertEqual(set(entries), {BL31, BL33, CHECKSUM})

    def test_bad_fip_is_rejected(self):
        image, bl31, bl33 = fixture()
        cases = {"truncated": image[:-1], "trailing-data": image + bytes(8),
                 "wrong-bl31": (image, b"wrong", bl33),
                 "wrong-bl33": (image, bl31, b"wrong")}
        for name, offset, fmt, value in (
            ("bad-magic", 0, "<I", 0),
            ("bad-flags", 8, "<Q", 1),
            ("overlap", 72, "<Q", 176),
            ("out-of-bounds", 32, "<Q", 1 << 63),
            ("bad-null-entry", 152, "<Q", 0),
            ("bad-component-flags", 48, "<Q", 1),
            ("bad-checksum", len(image) - 1, "<B", 0),
        ):
            corrupted = bytearray(image)
            struct.pack_into(fmt, corrupted, offset, value)
            cases[name] = bytes(corrupted)
        corrupted = bytearray(image)
        corrupted[16] ^= 1
        cases["unknown-uuid"] = bytes(corrupted)
        for name, value in cases.items():
            args = value if isinstance(value, tuple) else (value, bl31, bl33)
            with self.subTest(case=name), self.assertRaises(ValueError):
                self.verify.inspect_fip(*args)

    def test_source_review_requires_exact_full_sha(self):
        reviewed = "1" * 40
        self.assertTrue(self.verify.source_reviewed(reviewed, reviewed))
        self.assertFalse(self.verify.source_reviewed(reviewed, "2" * 40))
        for sha in ("master", "1" * 12, "$(id)", "A" * 40, "1" * 40 + "\n"):
            with self.subTest(sha=sha), self.assertRaises(ValueError):
                self.verify.source_reviewed(reviewed, sha)

    def directory(self, destination):
        root = Path(__file__).resolve().parents[2]
        lock_data = (root / "ci/source.lock.json").read_bytes()
        lock = json.loads(lock_data)
        destination.mkdir()
        dtb = bytes.fromhex("d00dfeed") + bytes(44)
        image, bl31, bl33 = fixture(dtb)
        config = '''CONFIG_DEFAULT_DEVICE_TREE="mt7986a-clx_s20"
CONFIG_IPADDR="192.168.1.1"
CONFIG_TARGET_MT7986=y
CONFIG_MMC_MTK=y
CONFIG_MTK_WEB_FAILSAFE=y
CONFIG_WEBUI_FAILSAFE_GPT=y
CONFIG_MTK_DHCPD=y
CONFIG_ENV_IS_IN_MMC=y
CONFIG_OF_EMBED=y
'''
        source = {"upstream_sha": lock["upstream_sha"],
                  "reviewed_upstream_sha": lock["upstream_sha"],
                  "source_reviewed": True, "board": lock["board"],
                  "version": lock["version"], "lock_sha256": self.verify.sha(lock_data),
                  "patch_sha256": self.verify.sha((root / "ci/patches/s20p-gpt.patch").read_bytes()),
                  "patched_mmc_sha256": self.verify.sha((root /
                      "uboot-mtk-20250711/board/mediatek/common/mmc_helper.c").read_bytes())}
        for name, value in {"fip.bin": image, "bl31.bin": bl31, "u-boot.bin": bl33,
                            "u-boot.dtb": dtb, "uboot.config": config.encode(),
                            "atf.config": b"_PLAT_MT7986=y\n_DRAM_DDR4=y\n_BOOT_DEVICE_EMMC=y\n",
                            "dtb-memory.txt": b"40000000 80000000\n",
                            "toolchain.txt": b"synthetic-test-toolchain\n",
                            "source.json": json.dumps(source).encode()}.items():
            (destination / name).write_bytes(value)
        return source

    def test_wrong_atf_platform_memory_or_storage_is_rejected(self):
        expected = "_PLAT_MT7986=y\n_DRAM_DDR4=y\n_BOOT_DEVICE_EMMC=y\n"
        for correct, wrong in (("_PLAT_MT7986=y", "_PLAT_MT7981=y"),
                               ("_DRAM_DDR4=y", "_DRAM_DDR3=y"),
                               ("_BOOT_DEVICE_EMMC=y", "_BOOT_DEVICE_NOR=y")):
            with self.subTest(setting=correct), tempfile.TemporaryDirectory() as td:
                directory = Path(td) / "build"
                self.directory(directory)
                (directory / "atf.config").write_text(expected.replace(correct, wrong))
                with self.assertRaisesRegex(ValueError, "ATF"):
                    self.verify.verify_directory(directory)

    def test_compressed_fip_configuration_is_rejected(self):
        for setting in ("_ENABLE_FIP_COMPRESS=y", "FIP_COMPRESS=1"):
            with self.subTest(setting=setting), tempfile.TemporaryDirectory() as td:
                directory = Path(td) / "build"
                self.directory(directory)
                config = directory / "atf.config"
                config.write_text(config.read_text() + setting + "\n")
                with self.assertRaisesRegex(ValueError, "uncompressed"):
                    self.verify.verify_directory(directory)

    def test_different_clean_builds_cannot_release(self):
        with tempfile.TemporaryDirectory() as td:
            left, right = Path(td) / "left", Path(td) / "right"
            self.directory(left)
            shutil.copytree(left, right)
            self.assertEqual(self.verify.compare_directories(left, right)
                             ["independent_matching_builds"], 2)
            (right / "toolchain.txt").write_text("changed compiler\n")
            with self.assertRaisesRegex(ValueError, "builds differ"):
                self.verify.compare_directories(left, right)

    def test_release_requires_review_and_trusted_provenance(self):
        pipeline = importlib.import_module("pipeline")
        with tempfile.TemporaryDirectory() as td:
            left, right, output = (Path(td) / name for name in ("left", "right", "release"))
            source = self.directory(left)
            shutil.copytree(left, right)
            with self.assertRaisesRegex(ValueError, "has not been reviewed"):
                pipeline.release_files(left, right, "2" * 40, output)
            self.assertFalse(output.exists())
            source["patch_sha256"] = "0" * 64
            for directory in (left, right):
                (directory / "source.json").write_text(json.dumps(source))
            with self.assertRaisesRegex(ValueError, "provenance"):
                pipeline.release_files(left, right, source["upstream_sha"], output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
