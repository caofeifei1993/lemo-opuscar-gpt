"""Offline regressions for the OpenArt host boundary (no image generation)."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "core/image/openart_request.py"
sys.path.insert(0, str(CLI.parent))
import openart_request as adapter


class OpenArtRequestTests(unittest.TestCase):
    def setUp(self):
        self.plan = {"provider": "openart", "model": "My Model", "prompt": "A ferry at dawn.",
                     "aspect": "16:9", "mode": "text2image", "reference_count": 0}
        self.model = {"id": "my-model-id", "displayName": "My Model", "modes": {"image": [
            {"mode": "text2image", "affordable": True, "totalCredits": 4},
            {"mode": "image2image", "affordable": True, "totalCredits": 8}]}}
        self.catalog = {"models": [self.model]}
        self.form = {"model": "my-model-id", "media": "image", "mode": "text2image", "jsonSchema": {
            "type": "object", "required": ["prompt"], "properties": {
                "prompt": {"type": "string", "minLength": 1, "maxLength": 100},
                "aspectRatio": {"type": "string", "enum": ["1:1", "16:9"]},
                "resolution": {"type": "string", "enum": ["1K", "2K"]},
                "imageCount": {"type": "integer", "minimum": 1, "maximum": 8}}}}
        self.quote = {"currency": "credits", "items": [{"model": "my-model-id", "mode": "text2image",
            "quantity": 1, "totalCredits": 5, "mediaType": "image", "affordable": True,
            "config": {"aspectRatio": "16:9", "resolution": "2K", "imageCount": 1}}]}

    def prepare(self, **kwargs):
        return adapter.prepare(self.plan, self.catalog, self.form, **kwargs)

    def test_full_display_name_resolves_to_live_id_without_guessing(self):
        self.assertEqual(adapter.resolve(self.plan, self.catalog)["form"]["arguments"]["model"], "my-model-id")
        self.plan["model"] = "My"
        with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
            adapter.resolve(self.plan, self.catalog)
        self.plan["model"] = "MY MODEL"
        self.catalog["models"].append({**self.model, "id": "another-id"})
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            adapter.resolve(self.plan, self.catalog)

    def test_generation_requires_an_exact_affordable_quote(self):
        params = {"resolution": "2K"}
        priced = self.prepare(overrides=params)
        self.assertEqual(priced["cost"]["toolName"], "openart_model_cost")
        self.assertNotIn("generate", priced)
        ready = self.prepare(overrides=params, quote=self.quote)
        self.assertEqual(ready["generate"]["arguments"], priced["cost"]["arguments"])
        self.assertEqual(ready["credits"], 5)
        self.assertEqual(ready["generate"]["arguments"]["params"]["prompt"], self.plan["prompt"])
        with self.assertRaisesRegex(ValueError, "configuration changed"):
            self.prepare(overrides={"resolution": "1K"}, quote=self.quote)
        for change in ({"affordable": False}, {"affordable": None}, {"mode": "image2image"},
                       {"model": "other"}, {"quantity": 2}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.prepare(quote={**self.quote, "items": [{**self.quote["items"][0], **change}]})

    def test_unknown_form_mode_and_unrepresentable_aspect_fail(self):
        self.form["model"] = "other-model"
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.prepare()
        self.form["model"] = self.model["id"]
        self.plan["aspect"] = "2:3"
        with self.assertRaisesRegex(ValueError, "choices"):
            self.prepare()
        del self.form["jsonSchema"]["properties"]["aspectRatio"]
        with self.assertRaisesRegex(ValueError, "does not support aspectRatio"):
            self.prepare()
        self.plan["aspect"] = None
        self.assertNotIn("aspectRatio", self.prepare()["cost"]["arguments"]["params"])
        self.plan["mode"] = "text2video"
        with self.assertRaisesRegex(ValueError, "image plan"):
            self.prepare()

    def test_overrides_cannot_change_routing_requested_inputs_or_bill_for_a_batch(self):
        for bad in ({"prompt": "different"}, {"model": "different"}, {"visualReferences": []},
                    {"aspectRatio": "1:1"}, {"imageCount": 2}, {"imageCount": True},
                    {"resolution": "4K"}, {"resoluton": "2K"}, {"resolution": 1}):
            with self.subTest(override=bad), self.assertRaises(ValueError):
                self.prepare(overrides=bad)

    def test_import_results_preserve_order_and_host_reference_shapes(self):
        self.plan.update(mode="image2image", reference_count=2)
        self.form["mode"] = "image2image"
        self.form["jsonSchema"]["required"].append("visualReferences")
        self.form["jsonSchema"]["properties"]["visualReferences"] = {"type": "array", "minItems": 1, "maxItems": 2}
        source = [
            {"type": "image", "id": "upload:one", "label": "character", "url": "https://example.test/stale"},
            {"type": "image", "id": "two", "label": "setting", "url": "https://example.test/upload",
             "metadata": {"width": 1920}},
        ]
        imported = {"results": [{"status": "SUCCESS", "visualReference": ref} for ref in source]}
        actual = self.prepare(refs=imported)["cost"]["arguments"]["params"]["visualReferences"]
        self.assertEqual(actual, [
            {"type": "image", "id": "upload:one", "label": "character"},
            {"type": "image", "id": "two", "label": "setting", "url": source[1]["url"]}])
        for bad in (source[:1], {"results": [{"status": "FAILED"}]}, ["./local.png", source[1]],
                    [source[0], {**source[1], "url": "file:///tmp/image.png"}]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.prepare(refs=bad)
        self.plan["mode"] = self.form["mode"] = "text2image"
        with self.assertRaisesRegex(ValueError, "cannot use reference"):
            self.prepare(refs=source)

    def test_cli_operates_on_host_structured_content_without_optional_dependencies(self):
        with tempfile.TemporaryDirectory() as td:
            paths = []
            for name, value in (("plan", self.plan), ("catalog", self.catalog), ("form", self.form)):
                path = Path(td, name + ".json")
                path.write_text(json.dumps(value))
                paths.extend(["--" + name, str(path)])
            result = subprocess.run([sys.executable, "-S", str(CLI), *paths], text=True,
                                    capture_output=True, cwd=td, check=True)
            self.assertEqual(json.loads(result.stdout)["cost"]["arguments"]["mode"], "text2image")


if __name__ == "__main__":
    unittest.main()
