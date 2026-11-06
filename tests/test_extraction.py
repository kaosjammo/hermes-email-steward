"""Synthetic, real-format attachment extraction contract tests."""
import io
from pathlib import Path
import json
import random
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile

from email_steward.extraction import Extraction, ExtractionFailure, extract, run_bounded
from scripts.extraction_fixtures import fixtures, office, pdf


ROOT = Path(__file__).resolve().parents[1]


class ExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.examples = fixtures()

    def test_real_formats(self):
        for name in ("letter.pdf", "letter.docx", "table.xlsx", "slides.pptx",
                     "scan.png", "scan.pdf", "mixed.pdf", "scan.bmp", "scan.tiff", "scan.jpg"):
            with self.subTest(name=name):
                result = extract(self.examples[name], name)
                self.assertIsInstance(result, Extraction)
                self.assertEqual(result.status, "ok", result.reason)
                self.assertIn("PAYMENT DUE FRIDAY", " ".join(result.text.split()))

    def test_detected_danger_returns_no_partial_text(self):
        for name, data in self.examples.items():
            if name.startswith("danger-"):
                with self.subTest(name=name):
                    result = extract(data, name)
                    self.assertEqual(result.status, "dangerous", result.reason)
                    self.assertEqual(result.text, "")

    def test_unreadable_and_unsupported_are_distinct(self):
        cases = [(b"broken", "bad.pdf", "unreadable"),
                 (b"broken", "bad.docx", "unreadable"),
                 (b"broken", "bad.png", "unreadable"),
                 (b"", "empty.pdf", "unreadable"),
                 (b"old office", "old.doc", "unsupported"),
                 (office("docx"), "archive.zip", "unsupported"),
                 (b"hello", "note.txt", "unsupported")]
        for data, name, status in cases:
            with self.subTest(name=name):
                result = extract(data, name)
                self.assertEqual(result.status, status, result.reason)
                self.assertTrue(result.reason)

    def test_input_and_output_limits_fail_closed(self):
        result = extract(b"X" * (16 * 1024 * 1024 + 1), "huge.pdf")
        self.assertEqual(result.status, "dangerous")
        rng = random.Random(19)
        result = extract(office("docx", "".join(rng.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ ", k=70000))), "long.docx")
        self.assertEqual(result.status, "dangerous", result.reason)
        self.assertIn("text limit", result.reason)
        self.assertEqual(result.text, "")

    def test_content_type_does_not_override_filename_or_signature(self):
        result = extract(self.examples["letter.pdf"], "payload.exe", "application/pdf")
        self.assertEqual(result.status, "dangerous")
        result = extract(self.examples["letter.pdf"], "letter.docx", "application/pdf")
        self.assertEqual(result.status, "unreadable")
        result = extract(self.examples["letter.pdf"], "letter.pdf", "application/octet-stream")
        self.assertEqual(result.status, "ok", result.reason)

    def test_temporary_files_are_removed_on_all_outcomes(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".local/extraction") as directory:
            root = Path(directory)
            for data, name in [(self.examples["letter.pdf"], "../../letter.pdf"),
                               (b"bad", "bad.pdf"),
                               (self.examples["danger-action.pdf"], "action.pdf")]:
                extract(data, name, scratch_root=root)
                self.assertEqual(list(root.iterdir()), [])

    def test_office_external_entities_in_utf16_are_rejected(self):
        xml = '<?xml version="1.0" encoding="utf-16"?><!DOCTYPE a [<!ENTITY x SYSTEM "file:///etc/passwd">]><a>&x;</a>'
        data = office("docx", replacement=xml.encode("utf-16"))
        result = extract(data, "entity.docx")
        self.assertEqual(result.status, "dangerous", result.reason)

    def test_zip_duplicate_and_crc_corruption(self):
        source = self.examples["letter.docx"]
        out = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(source)) as original, zipfile.ZipFile(out, "w") as target:
            for entry in original.infolist():
                target.writestr(entry.filename, original.read(entry.filename))
            with self.assertWarns(UserWarning):
                target.writestr("word/document.xml", b"<duplicate/>")
        self.assertEqual(extract(out.getvalue(), "duplicate.docx").status, "dangerous")
        damaged = bytearray(source)
        damaged[60] ^= 255
        self.assertNotEqual(extract(bytes(damaged), "damaged.docx").status, "ok")

    def test_password_pdf_and_blank_document(self):
        self.assertEqual(extract(pdf(""), "blank.pdf").status, "unreadable")
        result = extract(self.examples["protected.pdf"], "protected.pdf")
        self.assertEqual(result.status, "unreadable", result.reason)
        self.assertIn("password", result.reason)

    def test_subprocess_output_and_wall_limits(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".local/extraction") as directory:
            for script, cap, expected in [("print('X' * 100000)", 1024, "dangerous"),
                                           ("while True: pass", 1024, "unreadable")]:
                started = time.monotonic()
                with self.assertRaises(ExtractionFailure) as failure:
                    run_bounded([sys.executable, "-I", "-B", "-c", script],
                                cwd=Path(directory), timeout=0.2, output_limit=cap, new_session=True)
                self.assertEqual(failure.exception.status, expected)
                self.assertLess(time.monotonic() - started, 3)

    def test_effective_kernel_network_and_memory_limits(self):
        script = f'''import sys, json, os, resource, socket
sys.path.insert(0, {str(ROOT / "email_steward")!r})
from extract_worker import sandbox
sandbox()
result = {{"tmpdir": os.environ["TMPDIR"], "as": resource.getrlimit(resource.RLIMIT_AS)[0],
          "cpu": resource.getrlimit(resource.RLIMIT_CPU)[0], "core": resource.getrlimit(resource.RLIMIT_CORE)[0]}}
try:
    socket.socket()
    result["network"] = "ALLOWED"
except PermissionError:
    result["network"] = "DENIED"
try:
    bytearray(800 * 1024 * 1024)
    result["memory"] = "ALLOWED"
except MemoryError:
    result["memory"] = "DENIED"
print(json.dumps(result))
'''
        with tempfile.TemporaryDirectory(dir=ROOT / ".local/extraction") as directory:
            code, out, _ = run_bounded([sys.executable, "-I", "-B", "-c", script],
                                       cwd=Path(directory), timeout=5, output_limit=4096, new_session=True)
        self.assertEqual(code, 0)
        result = json.loads(out)
        self.assertEqual(result["network"], "DENIED")
        self.assertEqual(result["memory"], "DENIED")
        self.assertEqual(result["as"], 768 * 1024 * 1024)
        self.assertEqual(result["cpu"], 20)
        self.assertEqual(result["core"], 0)
        self.assertEqual(result["tmpdir"], directory)

    def test_oversized_image_and_malformed_image_list_are_not_processed(self):
        data = bytearray(self.examples["scan.png"])
        data[16:24] = (100000).to_bytes(4, "big") * 2
        self.assertEqual(extract(bytes(data), "large.png").status, "dangerous")
        # Not a valid image: verify that list-like trailing text cannot invoke file-list OCR.
        broken = self.examples["scan.png"][:33] + b"\n/nonexistent/synthetic-file.png\n"
        self.assertEqual(extract(broken, "broken.png").status, "unreadable")

    def test_cached_formula_and_shared_strings_are_read_without_evaluation(self):
        ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        data = office("xlsx", extras={
            "xl/sharedStrings.xml": f'<sst xmlns="{ns}"><si><t>PAYMENT DUE FRIDAY</t></si></sst>'.encode(),
            "xl/worksheets/sheet1.xml": f'<worksheet xmlns="{ns}"><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1"><f>20+22</f><v>42</v></c></row></sheetData></worksheet>'.encode()})
        result = extract(data, "formula.xlsx")
        self.assertEqual(result.status, "ok", result.reason)
        self.assertIn("PAYMENT DUE FRIDAY", result.text)
        self.assertIn("B1: 42", result.text)
        data = office("xlsx", extras={"xl/worksheets/sheet1.xml": f'<worksheet xmlns="{ns}"><sheetData><row><c><f>20+22</f></c></row></sheetData></worksheet>'.encode()})
        result = extract(data, "uncached.xlsx")
        self.assertEqual(result.status, "unreadable")
        self.assertIn("no cached value", result.reason)

    def test_symlink_scratch_is_refused(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".local/extraction") as directory:
            root = Path(directory)
            target = root / "target"
            target.mkdir(mode=0o700)
            link = root / "link"
            link.symlink_to(target, target_is_directory=True)
            result = extract(self.examples["letter.pdf"], "letter.pdf", scratch_root=link)
            self.assertEqual(result.status, "unreadable")
            self.assertIn("symlink", result.reason)
            self.assertEqual(list(target.iterdir()), [])

    def test_installed_copy_uses_explicit_profile_scratch(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".local/extraction") as directory:
            home = Path(directory)
            installed = home / "installed"
            installed.mkdir()
            for name in ("extraction.py", "extract_worker.py"):
                shutil.copyfile(ROOT / "email_steward" / name, installed / name)
            source = home / "safe.docx"
            source.write_bytes(self.examples["letter.docx"])
            scratch = home / "profile-scratch"
            script = ("import sys; from pathlib import Path; "
                      f"sys.path.insert(0, {str(installed)!r}); "
                      "from extraction import extract; "
                      f"r=extract(Path({str(source)!r}).read_bytes(), 'safe.docx', "
                      f"scratch_root=Path({str(scratch)!r})); "
                      "print(r.status, r.reason); assert r.status == 'ok'")
            result = subprocess.run([sys.executable, "-I", "-B", "-c", script],
                                    capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(sorted(p.name for p in installed.iterdir()),
                             ["extract_worker.py", "extraction.py"])
            self.assertEqual(list(scratch.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
