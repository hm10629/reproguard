from pathlib import Path
import tempfile
import unittest

from src.repository_scan import scan_repository


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_REPO = ROOT / "data" / "examples" / "incomplete-ml-project" / "repository"


class RepositoryScanTests(unittest.TestCase):
    def test_scans_expected_text_files(self):
        snapshot = scan_repository(SAMPLE_REPO)
        names = {item.relative_path for item in snapshot.files}
        self.assertIn("README.md", names)
        self.assertIn("requirements.txt", names)
        self.assertIn("train.py", names)

    def test_ignores_output_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("# demo", encoding="utf-8")
            (root / "outputs").mkdir()
            (root / "outputs" / "result.json").write_text("{}", encoding="utf-8")
            snapshot = scan_repository(root)
            self.assertEqual([item.relative_path for item in snapshot.files], ["README.md"])
            self.assertTrue(any("outputs" in item for item in snapshot.skipped_files))

    def test_skips_large_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            large = root / "notes.txt"
            large.write_text("x" * 100, encoding="utf-8")
            snapshot = scan_repository(root, max_file_size=10)
            self.assertEqual(snapshot.files, [])
            self.assertTrue(snapshot.skipped_files)


if __name__ == "__main__":
    unittest.main()
