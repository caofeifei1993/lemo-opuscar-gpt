"""Offline behavioral tests. Git commits are created only in temporary fixtures."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SETUP = Path("plugin/skills/lemo-opuscar/scripts/setup.sh")
INSTALLER = Path("tools/install_codex.py")


class CodexSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="lemo codex 中文 ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.work = self.base / "外部工作目录"
        self.work.mkdir()
        self.env = os.environ.copy()
        for key in ("LEMO_OPUSCAR_HOME", "LEMO_OPUSCAR_REPO"):
            self.env.pop(key, None)
        self.env["GIT_TERMINAL_PROMPT"] = "0"
        self.lib = self.library("素材库 with spaces")

    def run_command(self, args, cwd=None, env=None):
        return subprocess.run(
            [str(arg) for arg in args], cwd=cwd or self.work,
            env=env or self.env, text=True, capture_output=True, timeout=20,
        )

    def git(self, path, *args):
        result = self.run_command([
            "git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
            "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null",
            "-C", path, *args,
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def commit(self, path):
        self.git(path, "add", ".")
        self.git(path, "commit", "-qm", "test(fixtures): 保存离线安装测试数据")

    def library(self, name):
        path = self.base / name
        (path / SETUP).parent.mkdir(parents=True)
        (path / INSTALLER).parent.mkdir()
        (path / "core/render").mkdir(parents=True)
        (path / "core/render/.keep").touch()
        for relative in (SETUP, INSTALLER):
            shutil.copy2(ROOT / relative, path / relative)
        (path / "plugin/skills/lemo-opuscar/SKILL.md").write_text("name: lemo-opuscar\n")
        (path / "AGENTS.md").write_text("fixture library\n")
        (path / "package.json").write_text('{"name": "fixture"}\n')
        (path / "package-lock.json").write_text('{}\n')
        (path / "requirements.txt").write_text("")
        self.git(path, "init", "-q", "--initial-branch=main")
        self.commit(path)
        return path

    def setup(self, *args, library=None, script=None, cwd=None, extra_env=None):
        env = self.env | (extra_env or {})
        if library is not None:
            env["LEMO_OPUSCAR_HOME"] = str(library)
        return self.run_command(["sh", script or self.lib / SETUP, *args], cwd=cwd, env=env)

    def assert_library(self, result, library):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], f"LIB={library.resolve()}")

    def test_external_and_symlink_paths_use_local_library(self):
        link = self.base / "技能链接"
        link.symlink_to(self.lib / "plugin/skills/lemo-opuscar", target_is_directory=True)
        file_link = self.base / "setup link.sh"
        file_link.symlink_to(link / "scripts/setup.sh")
        for script in (self.lib / SETUP, link / "scripts/setup.sh", file_link):
            with self.subTest(script=script):
                self.assert_library(self.setup(script=script), self.lib)

    def test_library_precedence(self):
        current = self.library("当前库")
        override = self.library("指定库")
        self.assert_library(self.setup(cwd=current), current)
        self.assert_library(self.setup(cwd=current, library=override), override)
        relative = os.path.relpath(override, self.work)
        self.assert_library(self.setup(library=relative), override)

    def test_check_preserves_dirty_managed_library_and_origin(self):
        self.git(self.lib, "config", "lemo.managed", "true")
        self.git(self.lib, "remote", "add", "origin", str(self.base / "offline.git"))
        (self.lib / "AGENTS.md").write_text("my adaptation\n")
        (self.lib / "untracked.txt").write_text("keep me\n")
        before = self.git(self.lib, "status", "--porcelain")
        head = self.git(self.lib, "rev-parse", "HEAD")
        self.assert_library(self.setup(), self.lib)
        self.assertEqual((self.lib / "AGENTS.md").read_text(), "my adaptation\n")
        self.assertEqual(self.git(self.lib, "status", "--porcelain"), before)
        self.assertEqual(self.git(self.lib, "rev-parse", "HEAD"), head)
        self.assertEqual(self.git(self.lib, "remote", "get-url", "origin"), str(self.base / "offline.git"))
        self.assertFalse((self.lib / ".git/FETCH_HEAD").exists())

    def test_missing_library_and_bad_arguments_do_not_install(self):
        missing = self.base / "not downloaded"
        for args in ((), ("typo",), ("check", "extra"), ("deps", "typo"),
                     ("deps", "deps"), ("demo", "../escape"), ("demo", "a", "extra")):
            with self.subTest(args=args):
                result = self.setup(*args, library=missing)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(missing.exists())

    def test_explicit_install_uses_configured_repository(self):
        destination = self.base / "新下载库"
        result = self.setup("install", library=destination,
                            extra_env={"LEMO_OPUSCAR_REPO": str(self.lib)})
        self.assert_library(result, destination)
        self.assertEqual(self.git(destination, "remote", "get-url", "origin"), str(self.lib))
        self.assertTrue((destination / "AGENTS.md").exists())

    def clone_for_update(self):
        destination = self.base / "更新目标"
        self.git(self.base, "clone", "-q", str(self.lib), str(destination))
        return destination

    def test_install_rejects_repository_without_library_structure(self):
        invalid = self.library("错误来源")
        (invalid / "AGENTS.md").unlink()
        self.commit(invalid)
        destination = self.base / "invalid download"
        result = self.setup("install", library=destination,
                            extra_env={"LEMO_OPUSCAR_REPO": str(invalid)})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not a Lemo-Opuscar library", result.stderr)
        self.assertTrue(destination.exists())

    def test_update_fast_forwards_existing_origin(self):
        destination = self.clone_for_update()
        (self.lib / "AGENTS.md").write_text("new upstream instructions\n")
        self.commit(self.lib)
        result = self.setup("update", library=destination)
        self.assert_library(result, destination)
        self.assertEqual(self.git(destination, "rev-parse", "HEAD"), self.git(self.lib, "rev-parse", "HEAD"))
        self.assertEqual(self.git(destination, "remote", "get-url", "origin"), str(self.lib))

    def test_update_rejects_tracked_and_untracked_changes_before_fetch(self):
        destination = self.clone_for_update()
        for name in ("AGENTS.md", "new-file.txt"):
            with self.subTest(name=name):
                path = destination / name
                original = path.read_text() if path.exists() else None
                path.write_text("local changes\n")
                result = self.setup("update", library=destination)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("local changes", result.stderr)
                self.assertEqual(path.read_text(), "local changes\n")
                self.assertFalse((destination / ".git/FETCH_HEAD").exists())
                if original is None:
                    path.unlink()
                else:
                    path.write_text(original)

    def test_update_rejects_divergence_without_losing_local_commit(self):
        destination = self.clone_for_update()
        (destination / "local.txt").write_text("local work\n")
        self.commit(destination)
        head = self.git(destination, "rev-parse", "HEAD")
        (self.lib / "remote.txt").write_text("upstream work\n")
        self.commit(self.lib)
        result = self.setup("update", library=destination)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.git(destination, "rev-parse", "HEAD"), head)
        self.assertEqual((destination / "local.txt").read_text(), "local work\n")
        self.assertFalse((destination / "remote.txt").exists())

    def test_update_rejects_other_branches_and_offline_origin(self):
        destination = self.clone_for_update()
        self.git(destination, "checkout", "-qb", "my-work")
        result = self.setup("update", library=destination)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((destination / ".git/FETCH_HEAD").exists())
        self.git(destination, "checkout", "-q", "main")
        self.git(destination, "remote", "set-url", "origin", str(self.base / "offline.git"))
        head = self.git(destination, "rev-parse", "HEAD")
        result = self.setup("update", library=destination)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.git(destination, "rev-parse", "HEAD"), head)

    def installer(self, destination):
        return self.run_command([sys.executable, self.lib / INSTALLER, "--dest", destination])

    def test_installer_links_source_and_is_idempotent(self):
        destination = self.base / "Codex 技能/with spaces/lemo-opuscar"
        for _ in range(2):
            result = self.installer(destination)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(destination.is_symlink())
            self.assertEqual(destination.resolve(), (self.lib / "plugin/skills/lemo-opuscar").resolve())
        self.assert_library(self.setup(script=destination / "scripts/setup.sh"), self.lib)

    def test_installer_never_replaces_existing_paths(self):
        file = self.base / "existing file"
        file.write_text("preserve\n")
        directory = self.base / "existing directory"
        directory.mkdir()
        other_link = self.base / "other link"
        other_link.symlink_to(directory, target_is_directory=True)
        dangling = self.base / "dangling link"
        dangling.symlink_to(self.base / "missing")
        for destination in (file, directory, other_link, dangling):
            with self.subTest(destination=destination):
                result = self.installer(destination)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Refusing", result.stderr)
        self.assertEqual(file.read_text(), "preserve\n")
        self.assertTrue(directory.is_dir())
        self.assertEqual(os.readlink(other_link), str(directory))
        self.assertTrue(dangling.is_symlink())

    def test_deps_does_not_restore_modified_package_files(self):
        self.git(self.lib, "config", "lemo.managed", "true")
        (self.lib / "package.json").write_text('{"name":"my-local-change"}\n')
        fakebin = self.base / "fake tools"
        fakebin.mkdir()
        scripts = {
            "npm": '#!/bin/sh\nmkdir -p node_modules\nprintf "local lock\\n" > package-lock.json\n',
            "node": '#!/bin/sh\ncase "$1" in -p) echo 20 ;; -v) echo v20.0.0 ;; esac\n',
            "uv": '#!/bin/sh\nexit 0\n',
        }
        for name, content in scripts.items():
            path = fakebin / name
            path.write_text(content)
            path.chmod(0o755)
        python = self.lib / ".venv/bin/python"
        python.parent.mkdir(parents=True)
        python.write_text('#!/bin/sh\ncase "$1" in -V) echo "Python 3.12.0" ;; esac\n')
        python.chmod(0o755)
        result = self.setup("deps", extra_env={"PATH": str(fakebin) + os.pathsep + self.env["PATH"]})
        self.assert_library(result, self.lib)
        self.assertEqual((self.lib / "package.json").read_text(), '{"name":"my-local-change"}\n')
        self.assertEqual((self.lib / "package-lock.json").read_text(), "local lock\n")


if __name__ == "__main__":
    unittest.main()
