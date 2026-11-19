"""Exercise reusable identity images through the same native plan and resume commands used by Codex."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

try:
    from PIL import Image
except ImportError:
    Image = None


CLI = Path(__file__).resolve().parents[2] / "core/image/image_route.py"


@unittest.skipUnless(Image, "install core dependencies (Pillow) to register character images")
class ImageCharacterTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="character shots ")
        self.addCleanup(tmp.cleanup)
        self.project = Path(tmp.name).resolve() / "影片"
        self.project.mkdir()
        self.run_cli("configure", "--kind", "both", "--provider", "native", "--model", "auto")

    def run_cli(self, command, *args, ok=True):
        result = subprocess.run([sys.executable, str(CLI), command, str(self.project), *args],
                                capture_output=True, text=True, timeout=20)
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        return result.stderr

    def source(self, name, color):
        path = self.project / name
        with Image.new("RGB", (20, 12), color) as original:
            original.save(path)
        return path

    def register(self, identifier, description, source, **options):
        return self.run_cli("character", "--id", identifier, "--description", description, "--ref", str(source), **options)

    def test_distinct_recurring_roles_bind_in_order_in_both_kinds_of_shot(self):
        fox = self.register("狐狸", "红耳尖，白尾端", self.source("狐.png", "red").name)
        prince_source = self.source("王子.jpg", "yellow")
        prince = self.register("小王子", "金色卷发，绿色外套", prince_source)
        prince_source.unlink()  # The original can move after registration.
        self.assertCountEqual(self.run_cli("characters"), [prince, fox])
        scene = self.source("构图.png", "blue")
        common = ("--name", "远景", "--prompt", "宽镜头，两个角色面向日落", "--aspect", "16:9")
        art = self.run_cli("plan", "--kind", "illustration", *common,
                           "--character", "小王子", "--character", "狐狸", "--ref", scene.name, "--save")
        self.assertEqual(art["characters"], [prince, fox])
        self.assertEqual(art["reference_count"], 3)
        self.assertEqual(art["mode"], "image2image")
        self.assertEqual(art["call"]["toolName"], "image_gen.imagegen")
        args = art["call"]["arguments"]
        self.assertEqual(args["referenced_image_paths"], [str(self.project / c["reference"]) for c in (prince, fox)] + [str(scene)])
        self.assertIn("Reference 1 — 小王子: 金色卷发，绿色外套", args["prompt"])
        self.assertIn("Reference 2 — 狐狸: 红耳尖，白尾端", args["prompt"])
        self.assertNotIn("transparent_background", args)
        self.assertNotIn("num_last_images_to_include", args)
        panel = self.run_cli("plan", "--kind", "storyboard", *common, "--character", "狐狸")
        self.assertEqual(panel["characters"], [fox])
        self.assertEqual(panel["call"]["arguments"]["referenced_image_paths"], [str(self.project / fox["reference"])])

    def test_idempotent_registration_and_resume_detect_drift(self):
        source = self.source("source.jpg", "red")
        master = self.register("fox", "black paws", source)
        image = self.project / master["reference"]
        self.assertEqual(master["sha256"], hashlib.sha256(image.read_bytes()).hexdigest())
        self.assertEqual(master, self.register("fox", "black paws", source))
        self.register("fox", "white paws", source, ok=False)
        self.register("fox", "black paws", self.source("blue.png", "blue"), ok=False)
        self.assertEqual(self.run_cli("characters"), [master])
        shot = ("--name", "closeup", "--kind", "storyboard")
        self.run_cli("plan", *shot, "--prompt", "waves", "--character", "fox", "--save")
        moved = self.project.with_name("新影片")
        self.project = self.project.rename(moved)
        image = moved / master["reference"]
        self.assertEqual(self.run_cli("status", *shot)["plan"]["call"]["arguments"]["referenced_image_paths"], [str(image)])
        receipt = image.with_suffix(".json")
        receipt.write_text(json.dumps(dict(master, description="white paws")), encoding="utf-8")
        self.assertIn("differs", self.run_cli("status", *shot, ok=False))
        receipt.write_text(json.dumps(master), encoding="utf-8")
        image.write_bytes(b"changed")
        self.assertIn("digest", self.run_cli("status", *shot, ok=False))
        self.assertIn("digest", self.run_cli("plan", *shot, "--prompt", "waves", "--character", "fox", ok=False))

    def test_rejects_missing_ambiguous_and_unsupported_references(self):
        shot = ("--name", "solo", "--kind", "storyboard", "--prompt", "close up", "--save")
        self.assertIn("register", self.run_cli("plan", *shot, "--character", "absent", ok=False))
        source = self.source("source.png", "red")
        self.register("../escape", "black paws", source, ok=False)
        self.register("fox", " ", source, ok=False)
        self.register("fox", "black paws", source)
        self.assertIn("once", self.run_cli("plan", *shot, "--character", "fox", "--character", "fox", ok=False))
        self.assertIn("local", self.run_cli("plan", *shot, "--character", "fox", "--recent-images", "1", ok=False))
        self.run_cli("configure", "--kind", "storyboard", "--provider", "openart", "--model", "sample-model")
        self.assertIn("host-bound", self.run_cli("plan", *shot, "--character", "fox", ok=False))
        self.assertFalse((self.project / ".image-jobs").exists())
        self.assertEqual(self.run_cli("plan", *shot, "--reference-count", "1")["mode"], "image2image")

    def test_unsupported_file_and_external_registry_are_rejected(self):
        bad = self.project / "corrupt.png"
        bad.write_bytes(b"not an image")
        self.register("fox", "black paws", bad, ok=False)
        self.assertEqual(self.run_cli("characters"), [])
        empty = self.project / "assets/characters"
        empty.rmdir()
        external = self.project.parent / "outside"
        external.mkdir()
        empty.symlink_to(external, target_is_directory=True)
        self.register("fox", "black paws", self.source("source.png", "red"), ok=False)
        self.assertEqual(list(external.iterdir()), [])
