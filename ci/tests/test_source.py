# SPDX-License-Identifier: GPL-2.0
import importlib
import io
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def archive(links):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as bundle:
        for name, value in (("old/configs/board", b"test-board\n"),):
            item = tarfile.TarInfo(name)
            item.size = len(value)
            bundle.addfile(item, io.BytesIO(value))
        for name, target in links:
            item = tarfile.TarInfo(name)
            item.type = tarfile.SYMTYPE
            item.linkname = target
            bundle.addfile(item)
    return output.getvalue()


class SourceExtractionTests(unittest.TestCase):
    def test_internal_cross_directory_symlink_is_preserved(self):
        module = importlib.import_module("prepare_source")
        with tempfile.TemporaryDirectory() as td:
            module.extract_source(archive([("new/configs", "../old/configs")]), Path(td))
            self.assertEqual((Path(td) / "new/configs/board").read_bytes(), b"test-board\n")

    def test_external_or_ambiguous_paths_are_rejected(self):
        module = importlib.import_module("prepare_source")
        for links in ([('new/configs', '../../outside')],
                      [('new/configs', '/tmp/outside')],
                      [('../outside', 'old/configs')],
                      [('old', 'new')]):
            with self.subTest(links=links), tempfile.TemporaryDirectory() as td:
                with self.assertRaises(ValueError):
                    module.extract_source(archive(links), Path(td))


if __name__ == "__main__":
    unittest.main()
