# SPDX-License-Identifier: GPL-2.0
import hashlib
import importlib
from pathlib import Path
import struct
import sys
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BL31 = "47d4086d4cfe98469b952950cbbd5a00"
BL33 = "d6d0eea7fcead54b97829934f234b6e4"
CHECKSUM = "a2cceab7f8254b279704633a6fd69ad8"


def fixture():
    bl31, bl33 = b"A" * 512, b"B" * 8192
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


if __name__ == "__main__":
    unittest.main()
