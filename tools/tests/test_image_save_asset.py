"""Check the shared generated-image handoff without calling a generation service."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

try:
    from PIL import Image
except ImportError:
    Image = None

CLI = Path(__file__).resolve().parents[2] / "core/image/save_asset.py"


@unittest.skipUnless(Image, "install core dependencies (Pillow) to test generated assets")
class SaveAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with mock.patch.object(sys, "path", [str(CLI.parent), *sys.path]):
            import save_asset
        cls.module = save_asset

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="image asset ")
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name) / "影片"
        self.project.mkdir()
        self.args = [str(self.project), "--kind", "illustration", "--name", "fox-01", "--provider", "native"]
        self.output = self.project / "assets/illustrations/fox-01.png"

    def image_bytes(self, fmt="PNG", mode="RGBA", color=(12, 34, 56, 128)):
        output = io.BytesIO()
        with Image.new(mode, (64, 36), color) as image:
            image.save(output, format=fmt)
        return output.getvalue()

    def run_cli(self, *args, data=None, ok=True):
        result = subprocess.run([sys.executable, str(CLI), *args], input=data, capture_output=True, timeout=15)
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            return json.loads(result.stdout)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(b"Traceback", result.stderr)
        return result.stderr.decode()

    def test_native_stdin_and_repeat(self):
        data = self.image_bytes()
        command = [*self.args, "--aspect", "16:9", "--stdin"]
        result = self.run_cli(*command, data=data)
        self.assertEqual(result["status"], "saved")
        self.assertEqual(Path(result["path"]), self.output.resolve())
        record = json.loads(self.output.with_suffix(".json").read_text())
        self.assertEqual(record["model"], "auto")
        self.assertEqual(record["sha256"], hashlib.sha256(self.output.read_bytes()).hexdigest())
        with Image.open(self.output) as image:
            self.assertEqual(image.getpixel((0, 0)), (12, 34, 56, 128))
        original_time = self.output.stat().st_mtime_ns
        self.assertEqual(self.run_cli(*command, data=data)["status"], "reused")
        self.assertEqual(self.output.stat().st_mtime_ns, original_time)

    def test_openart_jpeg_import_and_expired_url_retry(self):
        source = self.project / "original"
        source.write_bytes(self.image_bytes("JPEG", "RGB", (12, 34, 56)))
        args = [str(self.project), "--kind", "storyboard", "--name", "shot-02", "--provider", "openart",
                "--model", "model-id", "--history-id", "job-id", "--resource-id", "result-id"]
        result = self.run_cli(*args, "--file", str(source))
        expected = self.project / "storyboard/images/shot-02.png"
        with Image.open(expected) as image:
            self.assertEqual(image.format, "PNG")
        receipt = json.loads(Path(result["metadata"]).read_text())
        self.assertEqual((receipt["width"], receipt["height"]), (64, 36))
        self.assertEqual((receipt["history_id"], receipt["resource_id"]), ("job-id", "result-id"))
        result = self.run_cli(*args, "--url", "https://expired.invalid/image?sig=neverlogthis")
        self.assertEqual(result["status"], "reused")
        self.assertNotIn("neverlogthis", expected.with_suffix(".json").read_text())

    def test_invalid_aspect_and_truncated_data_leave_no_pair(self):
        for data, aspect in ((self.image_bytes(), "1:1"), (self.image_bytes()[:40], "16:9"),
                             (b"<!doctype html>", "16:9")):
            with self.subTest(aspect=aspect, size=len(data)):
                self.run_cli(*self.args, "--aspect", aspect, "--stdin", data=data, ok=False)
                self.assertFalse(self.output.exists())
                self.assertFalse(self.output.with_suffix(".json").exists())

    def test_foreign_existing_files_and_conflicting_receipt_are_preserved(self):
        data = self.image_bytes()
        self.output.parent.mkdir(parents=True)
        self.output.write_bytes(b"existing")
        self.run_cli(*self.args, "--stdin", data=data, ok=False)
        self.assertEqual(self.output.read_bytes(), b"existing")
        self.output.unlink()
        self.run_cli(*self.args, "--stdin", data=data)
        old = self.output.read_bytes()
        self.run_cli(*self.args, "--stdin", data=self.image_bytes(color=(0, 0, 0, 255)), ok=False)
        self.assertEqual(self.output.read_bytes(), old)
        self.run_cli(*self.args, "--model", "other-provider-claim", "--stdin", data=data, ok=False)

    def test_retry_finishes_an_interrupted_publication(self):
        data = self.image_bytes()
        self.run_cli(*self.args, "--stdin", data=data)
        self.output.unlink()  # interrupt after linking the receipt, before linking the image
        self.run_cli(*self.args, "--stdin", data=self.image_bytes(color=(1, 2, 3, 4)), ok=False)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.run_cli(*self.args, "--stdin", data=data)["status"], "saved")

    def test_rejects_escape_unsafe_urls_and_redirects(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        (self.project / "assets").symlink_to(outside, target_is_directory=True)
        self.run_cli(*self.args, "--stdin", data=self.image_bytes(), ok=False)
        self.assertFalse(list(outside.iterdir()))
        self.run_cli(*self.args, "--name", "../target", "--stdin", data=self.image_bytes(), ok=False)
        error = self.run_cli(*self.args, "--url", "https://images.invalid/p?sig=neverlogthis", ok=False)
        self.assertNotIn("neverlogthis", error)
        error = self.run_cli(*self.args, "--url", "http://images.invalid/p?sig=neverlogthis", ok=False)
        self.assertNotIn("neverlogthis", error)
        module = self.module
        with self.assertRaises(ValueError):
            module.HTTPSRedirect().redirect_request(None, None, 302, "", {}, "http://wrong.invalid")

    def test_completed_https_resource_becomes_real_png(self):
        module = self.module
        opener = mock.Mock()
        url = "https://images.invalid/result.webp?sig=neverlogthis"
        args = mock.Mock(project=self.project, kind="illustration", provider="openart", model="model-id",
                         history_id="job", resource_id="result", aspect=None, url=url)
        args.name = "save"
        opener.open.return_value = io.BytesIO(self.image_bytes("WEBP"))
        with mock.patch.object(module, "build_opener", return_value=opener):
            result = module.save(args)
            self.assertEqual(result["status"], "saved")
        opener.open.assert_called_once_with(url, timeout=60)
        self.assertNotIn("neverlogthis", Path(result["metadata"]).read_text())
        self.assertNotIn("neverlogthis", json.dumps(result))
        with Image.open(result["path"]) as image:
            self.assertEqual(image.format, "PNG")


if __name__ == "__main__":
    unittest.main()
