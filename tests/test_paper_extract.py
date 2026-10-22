from pathlib import Path
import tempfile
import unittest

from src.paper_extract import PaperExtractionError, load_paper


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PAPER = ROOT / "data" / "examples" / "incomplete-ml-project" / "paper.txt"


class PaperExtractTests(unittest.TestCase):
    def test_load_text_preserves_page_and_lines(self):
        document = load_paper(SAMPLE_PAPER)
        self.assertEqual(document.pages[0].page, 1)
        self.assertIn("CIFAR-10", document.text)
        self.assertGreaterEqual(len(list(document.iter_lines())), 8)

    def test_rejects_unknown_extension(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "paper.docx"
            path.write_text("not supported", encoding="utf-8")
            with self.assertRaises(PaperExtractionError):
                load_paper(path)

    def test_missing_pdf_dependency_has_actionable_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "paper.pdf"
            path.write_bytes(b"not a real pdf")
            with self.assertRaises(PaperExtractionError):
                load_paper(path)

    def test_load_pdf_when_pypdf_is_available(self):
        try:
            from pypdf import PdfWriter
        except ImportError:
            self.skipTest("pypdf is not installed")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "paper.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=612, height=792)
            writer.add_metadata({"/Title": "CIFAR-10 reproducibility experiment"})
            with path.open("wb") as stream:
                writer.write(stream)

            loaded = load_paper(path)
            self.assertEqual(len(loaded.pages), 1)


if __name__ == "__main__":
    unittest.main()
