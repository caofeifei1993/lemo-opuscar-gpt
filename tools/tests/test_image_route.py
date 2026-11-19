"""Integration tests through the film maker's provider-selection CLI."""
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


CORE = Path(__file__).resolve().parents[2] / "core/image"


class ImageRouteTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory(prefix="影片 images ")
        self.addCleanup(tmp.cleanup)
        self.project = Path(tmp.name)

    def run_cli(self, command, *args, fail=False):
        r = subprocess.run([sys.executable, "-S", str(CORE / "image_route.py"), command,
                            str(self.project), *args], text=True, capture_output=True)
        if fail:
            self.assertNotEqual(r.returncode, 0)
            return
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_separate_routes_and_reusable_native_references(self):
        self.run_cli("configure", "--kind", "storyboard", "--provider", "openart", "--model", "sample-model")
        img = self.project / "reference.jpg"
        img.touch()
        base = ("--name", "shot-01", "--prompt", "Describe the scene")
        art = self.run_cli("plan", "--kind", "illustration", *base, "--ref", img.name, "--aspect", "16:9")
        self.assertEqual(art["call"]["toolName"], "image_gen.imagegen")
        self.assertEqual(art["call"]["arguments"]["referenced_image_paths"], [str(img.resolve())])
        self.assertNotIn("transparent_background", art["call"]["arguments"])
        board = self.run_cli("plan", "--kind", "storyboard", *base, "--reference-count", "2")
        self.assertEqual((board["model"], board["mode"], board["reference_count"]), ("sample-model", "image2image", 2))
        self.assertEqual(board["destination"], "storyboard/images/shot-01.png")
        self.assertFalse((self.project / ".image-jobs").exists())
        self.run_cli("configure", "--kind", "both", "--provider", "native", "--model", "sample-model", fail=True)
        self.assertEqual(self.run_cli("show")["storyboard"]["model"], "sample-model")

    def test_record_pending_and_reject_second_submission_or_repurposed_name(self):
        self.run_cli("configure", "--kind", "both", "--provider", "openart", "--model", "sample-model")
        ident = ("--kind", "illustration", "--name", "boat")
        self.run_cli("plan", *ident, "--prompt", "A boat", "--save")
        self.run_cli("submitted", *ident, "--history-id", "job-1", "--model", "wrong-model", fail=True)
        for _ in range(2):
            pending = self.run_cli("submitted", *ident, "--history-id", "job-1", "--model", "sample-model")
            self.assertEqual(pending["status"], "submitted")
        self.run_cli("submitted", *ident, "--history-id", "job-2", "--model", "sample-model", fail=True)
        self.run_cli("plan", *ident, "--prompt", "Another image", "--save", fail=True)
        self.assertEqual(self.run_cli("status", *ident)["submission"]["historyId"], "job-1")

    def test_unsafe_paths_and_unsupported_modes_rejected_before_writing(self):
        base = ("--kind", "storyboard", "--prompt", "A storyboard")
        for args in (("--name", "../escape"), ("--name", "panel", "--recent-images", "6"),
                     ("--name", "panel", "--reference-count", "1"), ("--name", "panel", "--aspect", "0:9")):
            self.run_cli("plan", *base, *args, "--save", fail=True)
        self.assertFalse((self.project / ".image-jobs").exists())
        self.run_cli("plan", *base, "--name", "panel", "--save")
        p = self.project / "storyboard/images/panel.png"
        p.parent.mkdir(parents=True)
        p.write_bytes(b"unrelated")
        self.run_cli("status", "--kind", "storyboard", "--name", "panel", fail=True)


if __name__ == "__main__":
    unittest.main()
