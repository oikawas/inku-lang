"""Check that concurrent builds cannot reuse a version or build number."""

import concurrent.futures
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("allocate-build-number.py")


class AllocationTest(unittest.TestCase):
    def test_legacy_counter_and_concurrent_worktrees(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "counter").write_text("27\n", encoding="ascii")

            def allocate(_):
                return subprocess.check_output(
                    [sys.executable, str(SCRIPT), "--directory", directory,
                     "--floor", "22", "--version-floor", "1.1.6"], text=True
                ).strip()

            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                pairs = list(executor.map(allocate, range(8)))
            self.assertEqual(set(pairs), {f"1.1.{7 + i} {28 + i}" for i in range(8)})
            self.assertEqual(Path(directory, "counter").read_text(encoding="ascii"), "35\n")

    def test_higher_floor_and_invalid_state(self):
        with tempfile.TemporaryDirectory() as directory:
            command = [sys.executable, str(SCRIPT), "--directory", directory, "--floor", "22", "--version-floor"]
            self.assertEqual(subprocess.check_output(command + ["1.2.0"], text=True).strip(), "1.2.1 23")
            self.assertEqual(subprocess.check_output(command + ["1.1.6"], text=True).strip(), "1.2.2 24")
            Path(directory, "version-state.json").write_text("{}", encoding="ascii")
            result = subprocess.run(command + ["1.1.6"], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(Path(directory, "counter").read_text(encoding="ascii"), "24\n")


if __name__ == "__main__":
    unittest.main()
