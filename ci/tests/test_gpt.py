# SPDX-License-Identifier: GPL-2.0
"""Exercise the actual production GPT C block; no router or large disk image."""
import json
import os
from pathlib import Path
import shlex
import struct
import subprocess
import tempfile
import unittest
import uuid
import zlib

ROOT = Path(os.environ.get("S20P_SOURCE_ROOT", Path(__file__).resolve().parents[2]))
UBOOT = ROOT / "uboot-mtk-20250711"
HEADER = struct.Struct("<8sIIIIQQQQ16sQIII")
SECTORS = (241696768, 244277248)
BLOCK = 512
COUNT = 128
TABLE_BYTES = COUNT * 128
PRIMARY_BYTES = 2 * BLOCK + TABLE_BYTES


def primary(sectors=SECTORS[0], count=COUNT):
    entries = bytearray(count * 128)
    ranges = ((1024, 2047), (2048, 6143), (6144, 10239), (12288, 4206591))
    for i, (start, end) in enumerate(ranges[:count]):
        entry = struct.pack("<16s16sQQQ72s", bytes([i + 1]) * 16,
                            bytes([i + 17]) * 16, start, end, 0,
                            f"partition-{i}".encode("utf-16le").ljust(72, b"\0"))
        entries[i * 128:(i + 1) * 128] = entry
    table_blocks = (len(entries) + BLOCK - 1) // BLOCK
    header = HEADER.pack(b"EFI PART", 0x10000, HEADER.size, 0, 0, 1,
                         sectors - 1, 2 + table_blocks,
                         sectors - table_blocks - 2, uuid.UUID(int=17).bytes_le,
                         2, count, 128, zlib.crc32(entries))
    mbr = bytearray(BLOCK)
    mbr[450] = 0xEE
    struct.pack_into("<II", mbr, 454, 1, min(sectors - 1, 0xFFFFFFFF))
    mbr[510:512] = b"\x55\xaa"
    blob = bytearray(mbr + header.ljust(BLOCK, b"\0") +
                     entries.ljust(table_blocks * BLOCK, b"\0"))
    return fix_crc(blob)


def fix_crc(blob, table=False):
    blob = bytearray(blob)
    if table:
        count, size = struct.unpack_from("<II", blob, BLOCK + 80)
        entries = blob[2 * BLOCK:2 * BLOCK + count * size]
        struct.pack_into("<I", blob, BLOCK + 88, zlib.crc32(entries))
    struct.pack_into("<I", blob, BLOCK + 16, 0)
    struct.pack_into("<I", blob, BLOCK + 16,
                     zlib.crc32(blob[BLOCK:BLOCK + HEADER.size]))
    return blob


def change(blob, offset, fmt, value, table=False):
    blob = bytearray(blob)
    struct.pack_into(fmt, blob, offset, value)
    return fix_crc(blob, table=table)


def checked_header(blob, offset):
    fields = HEADER.unpack_from(blob, offset)
    assert fields[0] == b"EFI PART" and fields[2] == HEADER.size
    raw = bytearray(blob[offset:offset + HEADER.size])
    struct.pack_into("<I", raw, 16, 0)
    assert zlib.crc32(raw) == fields[3], "header CRC mismatch"
    return fields


class GPTWriteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="s20p-gpt-tests-")
        directory = Path(cls.tmp.name)
        src = (UBOOT / "board/mediatek/common/mmc_helper.c").read_text()
        block = src[src.index("static int adjust_gpt("):
                    src.index("void mmc_setup_boot_options(")]
        types = (UBOOT / "include/part_efi.h").read_text()
        types = types[types.index("struct partition {"):
                      types.index("#define EFI_PARTITION_INFO_PROTOCOL_GUID")]
        shim = Path(__file__).with_name("mmc_shim.h").read_text()
        main = r'''
#undef printf
int main(int argc, char **argv)
{
    FILE *input;
    long size;
    void *data;
    int ret;
    if (argc != 9) return 64;
    input = fopen(argv[1], "rb");
    if (!input) return 65;
    fseek(input, 0, SEEK_END); size = ftell(input); rewind(input);
    data = malloc(size ? (size_t)size : 1);
    if (!data || fread(data, 1, size, input) != (size_t)size) return 66;
    fclose(input);
    desc.lba = strtoull(argv[2], NULL, 10);
    outputs[0] = argv[3]; outputs[1] = argv[4];
    fail_call = atoi(argv[5]);
    card.read_bl_len = (unsigned int)atoi(argv[6]);
    card.write_bl_len = (unsigned int)atoi(argv[7]);
    ret = mmc_write_gpt(0, 0, strtoul(argv[8], NULL, 10), data, size);
    printf("{\"rc\":%d,\"writes\":%d,\"part_init\":%d}\n",
           ret, calls, initialized);
    free(data);
    return 0;
}
'''
        harness = directory / "harness.c"
        harness.write_text(shim + "\n" + types +
                           '\n#define printf(...) ((void)0)\n' + block + main)
        cls.binary = directory / "gpt-harness"
        compiler = shlex.split(os.environ.get("CC", "clang"))
        subprocess.run(compiler + ["-std=gnu11", "-g", "-O1", "-Werror",
                       "-Wall", "-Wextra", "-Wno-unused-parameter",
                       "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                       str(harness), "-o", str(cls.binary)], check=True,
                       capture_output=True, text=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_image(self, image, sectors=SECTORS[0], fail=0, block=512,
                  write_block=512, max_size=2 * 1024 * 1024):
        with tempfile.TemporaryDirectory(dir=self.tmp.name) as td:
            td = Path(td)
            (td / "input").write_bytes(image)
            proc = subprocess.run([str(self.binary), str(td / "input"),
                   str(sectors), str(td / "primary"), str(td / "secondary"),
                   str(fail), str(block), str(write_block), str(max_size)],
                   capture_output=True, text=True,
                   env={**os.environ, "ASAN_OPTIONS": "detect_leaks=0",
                        "UBSAN_OPTIONS": "halt_on_error=1"})
            self.assertEqual(proc.returncode, 0, proc.stderr[-6000:])
            report = json.loads(proc.stdout)
            report["primary"] = ((td / "primary").read_bytes()
                                   if (td / "primary").exists() else b"")
            report["secondary"] = ((td / "secondary").read_bytes()
                                     if (td / "secondary").exists() else b"")
            return report

    def assert_pair(self, result, original, sectors):
        self.assertEqual(result["rc"], 0)
        self.assertEqual(result["writes"], 2)
        self.assertEqual(result["part_init"], 1)
        p, s = result["primary"], result["secondary"]
        h = checked_header(p, BLOCK)
        b = checked_header(s, len(s) - BLOCK)
        entry_bytes = h[11] * h[12]
        table_blocks = (entry_bytes + BLOCK - 1) // BLOCK
        self.assertEqual((h[5], h[6]), (1, sectors - 1))
        self.assertEqual((b[5], b[6]), (sectors - 1, 1))
        self.assertEqual(b[10], sectors - 1 - table_blocks)
        self.assertEqual(h[8], sectors - 2 - table_blocks)
        self.assertEqual(h[7:10], b[7:10])
        self.assertEqual(h[11:], b[11:])
        entries = original[2 * BLOCK:2 * BLOCK + entry_bytes]
        self.assertEqual(p[2 * BLOCK:2 * BLOCK + entry_bytes], entries)
        self.assertEqual(s[:entry_bytes], entries)
        self.assertEqual(zlib.crc32(entries), h[13])
        self.assertEqual(len(p), 2 * BLOCK + table_blocks * BLOCK)
        self.assertEqual(len(s), (table_blocks + 1) * BLOCK)

    def test_both_observed_emmc_geometries(self):
        for sectors in SECTORS:
            with self.subTest(sectors=sectors):
                image = primary(sectors)
                self.assert_pair(self.run_image(image, sectors), image, sectors)

    def test_resize_to_live_geometry_without_moving_partitions(self):
        for sectors in SECTORS:
            with self.subTest(sectors=sectors):
                image = primary(8 * 1024 * 1024)
                self.assert_pair(self.run_image(image, sectors), image, sectors)

    def test_entry_metadata_controls_backup_size(self):
        for count in (4, 5, 32, 128):
            with self.subTest(entries=count):
                image = primary(count=count)
                self.assert_pair(self.run_image(image), image, SECTORS[0])

    def test_bad_inputs_never_write(self):
        image = primary()
        bad_crc = bytearray(image)
        bad_crc[BLOCK + 16] ^= 1
        bad_table = bytearray(image)
        bad_table[1100] ^= 1
        cases = {
            "empty": b"", "truncated-header": image[:BLOCK + 91],
            "truncated-table": image[:-1], "whole-disk-or-padding": image + bytes(BLOCK),
            "bad-mbr-signature": change(image, 510, "<H", 0),
            "bad-protective-type": change(image, 450, "<B", 0x83),
            "bad-protective-start": change(image, 454, "<I", 2),
            "bad-signature": change(image, BLOCK, "<Q", 0),
            "bad-revision": change(image, BLOCK + 8, "<I", 0x20000),
            "short-header": change(image, BLOCK + 12, "<I", 80),
            "huge-header": change(image, BLOCK + 12, "<I", 0xFFFFFFFF),
            "reserved-header": change(image, BLOCK + 20, "<I", 1),
            "header-crc": bad_crc, "table-crc": bad_table,
            "not-primary": change(image, BLOCK + 24, "<Q", 7),
            "wrong-table-lba": change(image, BLOCK + 72, "<Q", 3),
            "zero-entry-count": change(image, BLOCK + 80, "<I", 0),
            "huge-entry-count": change(image, BLOCK + 80, "<I", 0xFFFFFFFF),
            "wrong-entry-size": change(image, BLOCK + 84, "<I", 256),
            "first-overlaps-table": change(image, BLOCK + 40, "<Q", 33),
            "usable-reversed": change(image, BLOCK + 48, "<Q", 1),
            "last-overlaps-backup": change(image, BLOCK + 48, "<Q", SECTORS[0] - 1),
            "partition-reversed": change(image, 2 * BLOCK + 32, "<Q", 3000, table=True),
            "partition-before-usable": change(image, 2 * BLOCK + 32, "<Q", 1, table=True),
            "partition-outside-disk": change(image, 2 * BLOCK + 40, "<Q", SECTORS[0], table=True),
            "partition-overlap": change(image, 2 * BLOCK + 128 + 32, "<Q", 2047, table=True),
        }
        for name, blob in cases.items():
            with self.subTest(case=name):
                report = self.run_image(blob)
                self.assertLess(report["rc"], 0)
                self.assertEqual(report["writes"], 0)
                self.assertEqual(report["part_init"], 0)

    def test_device_geometry_rejections_do_not_write(self):
        for options in ({"sectors": 0}, {"sectors": 20}, {"sectors": 4096},
                        {"block": 4096}, {"write_block": 4096},
                        {"max_size": 512}):
            with self.subTest(**options):
                report = self.run_image(primary(), **options)
                self.assertLess(report["rc"], 0)
                self.assertEqual(report["writes"], 0)

    def test_io_errors_propagate_without_reinitializing_partitions(self):
        for fail, expected in ((-1, 0), (1, 1), (2, 2)):
            with self.subTest(fail=fail):
                report = self.run_image(primary(), fail=fail)
                self.assertLess(report["rc"], 0)
                self.assertEqual(report["writes"], expected)
                self.assertEqual(report["part_init"], 0)


if __name__ == "__main__":
    unittest.main()
