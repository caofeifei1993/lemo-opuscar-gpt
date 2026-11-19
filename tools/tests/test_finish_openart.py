"""Verify remote OpenArt completions against recorded routing state before import."""
import argparse
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

try:
    from PIL import Image
except ImportError:
    Image = None

IMAGE = Path(__file__).resolve().parents[2] / "core/image"


@unittest.skipUnless(Image, "install core dependencies (Pillow) to test generated assets")
class FinishOpenArtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with mock.patch.object(sys, "path", [str(IMAGE), *sys.path]):
            import finish_openart
        cls.module = finish_openart

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.args = argparse.Namespace(project=self.project, kind="storyboard", name="shot", resource_id=None)
        jobs = self.project / ".image-jobs/storyboard/shot"
        jobs.mkdir(parents=True)
        selection = {"provider": "openart", "kind": "storyboard", "name": "shot", "model": "Model Name",
                     "aspect": "16:9"}
        (jobs / "plan.json").write_text(json.dumps(selection))
        (jobs / "submission.json").write_text(json.dumps({"model": "model-id", "historyId": "job-id"}))
        self.item = {"mediaType": "image", "id": "result-01", "url": "https://images.invalid/art?sig=PRIVATE"}
        self.result = {"historyId": "job-id", "status": "COMPLETED", "capabilityId": "model-id:text2image",
                       "modelDisplayName": "Model Name", "resources": [self.item]}

    def test_wrapped_result_imports_image_and_plain_replay_is_offline(self):
        output = io.BytesIO()
        Image.new("RGB", (80, 45)).save(output, "WEBP")
        output.seek(0)
        with mock.patch("save_asset.build_opener") as build:
            build.return_value.open.return_value = output
            result = self.module.finish(self.args, {"structuredContent": self.result, "isError": False})
            self.assertEqual(result["status"], "saved")
            self.assertEqual(self.module.finish(self.args, self.result)["status"], "reused")
            build.return_value.open.assert_called_once_with(self.item["url"], timeout=60)
        self.assertNotIn("PRIVATE", Path(result["metadata"]).read_text())

    def test_incomplete_mismatched_jobs_and_failed_images_do_not_import(self):
        for bad in ({"status": "RUNNING"}, {"historyId": "wrong"}, {"capabilityId": "other:text2image"},
                    {"warning": "some image failed"}, {"resources": [{**self.item, "mediaType": "video"}]},
                    {"resources": [{**self.item, "status": "FAILED"}]}, {"resourceCount": 2},
                    {"resources": [{**self.item, "url": "http://bad.invalid/?sig=PRIVATE"}]}):
            with self.subTest(bad=tuple(bad)), mock.patch.object(self.module, "save") as save:
                with self.assertRaises(ValueError) as err:
                    self.module.finish(self.args, {**self.result, **bad})
                self.assertNotIn("PRIVATE", str(err.exception))
                save.assert_not_called()

    def test_multislot_completion_requires_explicit_selection(self):
        other = {**self.item, "id": "result-02", "url": "https://images.invalid/second"}
        self.result["resources"].append(other)
        with self.assertRaisesRegex(ValueError, "multiple resources"):
            self.module.finish(self.args, self.result)
        self.args.resource_id = "result-02"
        with mock.patch.object(self.module, "save") as save:
            self.module.finish(self.args, self.result)
        self.assertEqual(save.call_args.args[0].url, other["url"])


if __name__ == "__main__":
    unittest.main()
