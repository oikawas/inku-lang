"""Check the device copies rule: a second copy on the same day is not taken, and only two are kept."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("device_backups.py")


def run(*arguments):
    return subprocess.run([sys.executable, str(SCRIPT), *arguments], capture_output=True, text=True)


class DeviceBackupsTest(unittest.TestCase):
    def test_a_copy_of_today_is_found_and_prune_keeps_two(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for name in ["20261113-090000", "20261114-221810-before-check", "20261114-222047", "notes"]:
                (folder / name).mkdir()
            # Failure: a second copy is taken on a day that already has one (the note counts as a copy).
            self.assertEqual(run("taken-today", directory, "--today", "20261115").returncode, 1)
            found = run("taken-today", directory, "--today", "20261114")
            self.assertEqual((found.returncode, found.stdout.strip()), (0, str(folder / "20261114-222047")))
            # Failure: more than two copies stay, the newest is removed, or a folder that is no copy is touched.
            self.assertEqual(run("prune", directory).returncode, 0)
            self.assertEqual(sorted(path.name for path in folder.iterdir()),
                             ["20261114-221810-before-check", "20261114-222047", "notes"])


if __name__ == "__main__":
    unittest.main()
