"""Offline voice-selection regressions; never contact a speech service."""

import importlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
TTS = ROOT / "core/tts"
CLI = TTS / "tts_zh.py"


class VoicePresetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(TTS))
        cls.library = importlib.import_module("voice_library")
        cls.catalog = cls.library.load_catalog()
        cls.presets = {item["id"]: item for item in cls.catalog["presets"]}

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="lemo voices 中文 ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.output = self.base / "new audio"

    def resolve(self, lines=None, **options):
        if lines is None:
            lines = [{"id": "intro", "text": "欢迎收听今天的故事。"}]
        return self.library.resolve_lines(lines, **options)

    def command(self, *arguments):
        # -S removes third-party site-packages: listing/planning must work
        # before numpy, soundfile and edge-tts have been installed.
        return subprocess.run(
            [sys.executable, "-S", str(CLI), *map(str, arguments)],
            cwd=self.base, capture_output=True, text=True, timeout=15,
        )

    def write_json(self, filename, data):
        path = self.base / filename
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    def assert_selection(self, line, preset_id):
        preset = self.presets[preset_id]
        for field in ("voice", "rate", "pitch"):
            self.assertEqual(line[field], preset[field], field)

    def test_catalog_can_select_every_advertised_preset(self):
        self.assertEqual(len(self.presets), len(self.catalog["presets"]))
        self.assertIn(self.catalog["default"], self.presets)
        for preset in self.catalog["presets"]:
            with self.subTest(preset=preset["id"]):
                line = self.resolve(preset=preset["id"])[0]
                self.assert_selection(line, preset["id"])
                self.assertTrue(preset["sample_text"].strip())

    def test_existing_calls_retain_the_original_defaults(self):
        line = self.resolve()[0]
        self.assertEqual(line["voice"], "zh-CN-XiaoxiaoNeural")
        self.assertEqual(line["rate"], "+0%")
        self.assertEqual(line["pitch"], "+0Hz")
        self.assertEqual(line["say"], line["text"])

    def test_existing_per_line_voice_speed_and_say_remain_supported(self):
        line = self.resolve([{
            "id": "v01", "text": "速度 1.5。", "say": "速度一点五。",
            "voice": "zh-CN-YunxiNeural", "speed": 1.1, "pitch": "-2Hz",
        }])[0]
        self.assertEqual(line["voice"], "zh-CN-YunxiNeural")
        self.assertEqual(line["rate"], "+10%")
        self.assertEqual(line["pitch"], "-2Hz")
        self.assertEqual(line["say"], "速度一点五。")
        self.assertEqual(line["text"], "速度 1.5。")

    def test_explicit_global_values_override_global_preset(self):
        line = self.resolve(
            preset="zh-warm-female", voice="zh-CN-YunxiNeural",
            rate="+12%", pitch="-4Hz",
        )[0]
        self.assertEqual((line["voice"], line["rate"], line["pitch"]),
                         ("zh-CN-YunxiNeural", "+12%", "-4Hz"))

    def test_cast_presets_replace_global_voice_and_prosody_together(self):
        lines = self.resolve([
            {"id": "a", "text": "讲述开始。", "role": "narrator"},
            {"id": "b", "text": "你好呀。", "role": "fox"},
        ], voice="en-US-AriaNeural", rate="+40%", pitch="+9Hz", cast={
            "narrator": "zh-warm-female",
            "fox": {"preset": "zh-youth-male", "rate": "-9%"},
        })
        self.assert_selection(lines[0], "zh-warm-female")
        self.assertEqual(lines[1]["voice"], self.presets["zh-youth-male"]["voice"])
        self.assertEqual(lines[1]["pitch"], self.presets["zh-youth-male"]["pitch"])
        self.assertEqual(lines[1]["rate"], "-9%")

    def test_line_preset_then_line_overrides_win_over_cast(self):
        line = self.resolve([{
            "id": "v01", "text": "玫瑰需要照料。", "role": "narrator",
            "preset": "zh-warm-female", "pitch": "-7Hz",
        }], preset="zh-warm-female", rate="+35%", cast={
            "narrator": {"preset": "zh-youth-male", "rate": "-9%"},
        })[0]
        self.assertEqual(line["voice"], self.presets["zh-warm-female"]["voice"])
        self.assertEqual(line["rate"], self.presets["zh-warm-female"]["rate"])
        self.assertEqual(line["pitch"], "-7Hz")

    def test_rate_takes_precedence_over_legacy_speed(self):
        line = self.resolve([{
            "id": "v01", "text": "速度测试。", "rate": "+5%", "speed": 0.5,
        }])[0]
        self.assertEqual(line["rate"], "+5%")
        numeric = self.resolve([{"id": "v02", "text": "慢一点。", "rate": 0.85}])[0]
        self.assertEqual(numeric["rate"], "-15%")

    def test_invalid_speeds_and_prosody_are_rejected(self):
        for field, value in [
            ("speed", 0), ("speed", -1), ("speed", float("nan")),
            ("speed", float("inf")), ("rate", "fast"), ("rate", "10%"),
            ("rate", "-100%"), ("pitch", "low"), ("pitch", "2Hz"),
        ]:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.resolve([{"id": "v01", "text": "测试。", field: value}])

    def test_unknown_preset_and_unmapped_role_are_rejected(self):
        for options in ({"preset": "does-not-exist"}, {"cast": {"fox": "does-not-exist"}}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.resolve(**options)
        with self.assertRaises(ValueError):
            self.resolve([{"id": "v01", "text": "你好。", "role": "unmapped"}])

    def test_cast_schema_errors_are_rejected(self):
        for cast in ([], "narrator", {"narrator": []}, {"narrator": 3},
                     {"narrator": {"presett": "zh-warm-female"}},
                     {"narrator": {"emotion": "sad"}}):
            with self.subTest(cast=cast), self.assertRaises(ValueError):
                self.resolve(cast=cast)

    def test_safe_unicode_space_and_dotted_ids_remain_compatible(self):
        for identifier in ("第一句", "opening line", "narration.v1", "中文 第一段.v2", 7):
            with self.subTest(identifier=identifier):
                line = self.resolve([{"id": identifier, "text": "旧项目的旁白。"}])[0]
                self.assertEqual(line["id"], str(identifier))

    def test_paths_and_duplicate_ids_cannot_overwrite_another_line(self):
        for identifier in ("../escape", "a/b", "a\\b", "/absolute", "..", "", "NUL", "COM1"):
            with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                self.resolve([{"id": identifier, "text": "测试。"}])
        for identifiers in (("same", "same"), (1, "1"), ("Intro", "intro")):
            with self.subTest(identifiers=identifiers), self.assertRaises(ValueError):
                self.resolve([{"id": identifier, "text": "测试。"} for identifier in identifiers])

    def test_invalid_script_is_rejected_before_synthesis(self):
        invalid = [[], {}, ["text"], [{}], [{"id": "a"}],
                   [{"id": "a", "text": "  "}], [{"id": "a", "text": 42}],
                   [{"id": "a", "text": "字幕", "say": " "}]]
        for lines in invalid:
            with self.subTest(lines=lines), self.assertRaises(ValueError):
                self.resolve(lines)

    def test_list_and_help_require_no_audio_dependencies(self):
        result = self.command("--list-presets", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        catalog = json.loads(result.stdout)
        self.assertEqual({p["id"] for p in catalog["presets"]}, set(self.presets))
        for arguments in (("--list-presets",), ("--help",)):
            result = self.command(*arguments)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(result.stdout.strip())

    def test_dry_run_resolves_cast_without_network_or_creating_output(self):
        script = self.write_json("lines.json", [
            {"id": "v01", "text": "珍贵的关系。", "role": "narrator"},
            {"id": "v02", "text": "需要用时间去照料。", "role": "fox"},
        ])
        cast = self.write_json("cast.json", {"narrator": "zh-warm-female", "fox": "zh-youth-male"})
        result = self.command(script, self.output, "--preset", "zh-warm-female", "--cast", cast, "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assert_selection(plan["lines"][0], "zh-warm-female")
        self.assert_selection(plan["lines"][1], "zh-youth-male")
        self.assertFalse(self.output.exists())
        self.assertEqual(sorted(p.name for p in self.base.iterdir()), ["cast.json", "lines.json"])

    def test_preview_all_uses_each_presets_own_language_sample(self):
        result = self.command("--preview", "all", "--out-dir", self.output, "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = json.loads(result.stdout)["lines"]
        self.assertEqual({line["id"] for line in lines}, set(self.presets))
        for line in lines:
            self.assert_selection(line, line["id"])
            self.assertEqual(line["say"], self.presets[line["id"]]["sample_text"])
        self.assertFalse(self.output.exists())

    def test_invalid_later_line_fails_without_partial_output(self):
        script = self.write_json("lines.json", [
            {"id": "v01", "text": "第一句有效。"},
            {"id": "../escape", "text": "第二句路径无效。"},
        ])
        result = self.command(script, self.output)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("ModuleNotFoundError", result.stderr)
        self.assertFalse(self.output.exists())

    def test_malformed_json_has_actionable_error_without_traceback(self):
        script = self.base / "broken.json"
        script.write_text('{"bad json"', encoding="utf-8")
        result = self.command(script, self.output, "--dry-run")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(self.output.exists())

    def test_unknown_preview_does_not_create_output(self):
        result = self.command("--preview", "does-not-exist", "--out-dir", self.output)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("ModuleNotFoundError", result.stderr)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
