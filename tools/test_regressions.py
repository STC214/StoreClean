"""Offline regression checks for artifact integrity and non-destructive tool behavior."""

import hashlib
import json
import tempfile
import unittest
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import build_module
import inspect_apks
import check_device
import analyze_update
import review_project


class BuildTests(unittest.TestCase):
    def test_failed_staging_preserves_existing_release(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staging, release = root / "staging", root / "release"
            staging.mkdir()
            release.mkdir()
            stem = "storeclean-" + build_module.VERSION
            old = release / (stem + ".apk")
            old.write_bytes(b"previous verified APK")
            record = {}
            for key, suffix in (("apk", ".apk"), ("patch", ".patch"), ("source_zip", "-source.zip")):
                (staging / (stem + suffix)).write_bytes(b"new artifact")
                record[key + "_sha256"] = hashlib.sha256(b"new artifact").hexdigest()
            record["source_zip_sha256"] = "wrong"
            (staging / (stem + "-verification.json")).write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaises(ValueError):
                build_module.promote_release(staging, release)
            self.assertEqual(old.read_bytes(), b"previous verified APK")
            record["source_zip_sha256"] = hashlib.sha256(b"new artifact").hexdigest()
            (staging / (stem + ".apk.idsig")).write_bytes(b"signature fixture")
            (staging / (stem + "-verification.json")).write_text(json.dumps(record), encoding="utf-8")
            build_module.promote_release(staging, release)
            self.assertEqual(old.read_bytes(), b"new artifact")
            self.assertEqual([path.name for path in release.iterdir()], [stem + ".apk"])
            artifacts = root / "analysis/release_artifacts"
            self.assertTrue((artifacts / (stem + "-verification.json")).exists())
            self.assertTrue((artifacts / (stem + "-source.zip")).exists())
            self.assertTrue((artifacts / (stem + ".patch")).exists())
            self.assertEqual((artifacts / (stem + ".apk.idsig")).read_bytes(), b"signature fixture")

    def test_refresh_rejects_changed_resources_and_missing_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            module = Path(temporary)
            (module / "AndroidManifest.xml").write_text("<manifest/>", encoding="utf-8")
            (module / "res").mkdir()
            image = module / "res/icon.png"
            image.write_bytes(b"image fixture")
            with patch.object(build_module, "MODULE", module):
                record = {"compilation_inputs": build_module.compilation_inputs()}
                build_module.require_matching_inputs(record)
                with self.assertRaises(ValueError):
                    build_module.require_matching_inputs({})
                image.write_bytes(b"changed fixture")
                with self.assertRaises(ValueError):
                    build_module.require_matching_inputs(record)

    def test_each_build_gets_empty_unique_workspace(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(build_module, "MODULE", Path(temporary)):
                first = build_module.create_work_directory()
                (first / "stale.class").write_bytes(b"old")
                second = build_module.create_work_directory()
                self.assertNotEqual(first, second)
                self.assertEqual(list(second.iterdir()), [])


class InventoryTests(unittest.TestCase):
    def test_preference_owner_is_discovered_not_assumed_unobfuscated(self):
        source = "invoke-virtual {p0, v0}, Landroidx/preference/g;->findPreference(Ljava/lang/CharSequence;)Landroidx/preference/Preference;"
        self.assertEqual(review_project.preference_lookup_owner(source), "androidx.preference.g")
        with self.assertRaises(ValueError):
            review_project.preference_lookup_owner("no such call")

    def test_analysis_output_cannot_overwrite_unbound_or_out_of_scope_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / "analysis/apk_1"
            directory.mkdir(parents=True)
            (directory / "smali.fixture").write_bytes(b"existing unrelated evidence")
            with patch.object(analyze_update, "ROOT", root):
                for invalid in (root / ".git", root / "analysis", directory):
                    with self.assertRaises(ValueError):
                        analyze_update.validate_evidence_destination(invalid)
                (directory / "input.apk").write_bytes(b"bound fixture")
                analyze_update.validate_evidence_destination(directory)

    def test_rerun_preserves_appended_sample_and_existing_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "store_apk").mkdir()
            (root / "analysis/apk_1").mkdir(parents=True)
            (root / "store_apk/old.apk").write_bytes(b"original")
            (root / "analysis/apk_1/input.apk").write_bytes(b"original")
            digest = hashlib.sha256(b"original").hexdigest()
            entries = [{"file": "store_apk/old.apk", "copy": "analysis/apk_1/input.apk",
                        "analysis_directory": "analysis/apk_1", "sha256": digest},
                       {"file": "store_apk/device_new/base.apk", "analysis_directory": "analysis/apk_4",
                        "sha256": "retained nested sample"}]
            inventory = root / "analysis/inventory.json"
            inventory.write_text(json.dumps(entries), encoding="utf-8")
            with patch.object(inspect_apks, "ROOT", root), patch.object(inspect_apks, "capture") as capture:
                inspect_apks.main()
                capture.assert_not_called()
            self.assertEqual(json.loads(inventory.read_text(encoding="utf-8")), entries)


class DeviceTests(unittest.TestCase):
    def test_default_apk_is_current_manifest_version(self):
        args = check_device.parse_arguments(["--serial", "fixture", "--stage", "after"])
        self.assertEqual(args.apk, f"release/storeclean-{build_module.VERSION}.apk")

    def test_sessions_never_overwrite_history(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(check_device, "ROOT", Path(temporary)):
                first = check_device.create_session()
                (first / "evidence").write_bytes(b"historical")
                second = check_device.create_session()
                self.assertNotEqual(first, second)
                self.assertEqual((first / "evidence").read_bytes(), b"historical")

    def test_split_package_paths_and_input_bounds(self):
        self.assertEqual(check_device.package_paths("package:/data/base.apk\npackage:/data/split.apk\n"),
                         ["/data/base.apk", "/data/split.apk"])
        for output in ("", "error", "package:relative.apk", "package:/data/a;command.apk"):
            with self.assertRaises(ValueError):
                check_device.package_paths(output)
        for size in ((1156, 2510), (720, 1280)):
            x1, y1, x2, y2 = check_device.swipe_coordinates(*size)
            self.assertTrue(0 <= x1 == x2 < size[0])
            self.assertTrue(0 <= y2 < y1 < size[1])


class CleanupTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("powershell.exe"), "Windows PowerShell required")
    def test_numeric_order_sidecar_paths_and_dry_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "tools").mkdir()
            release = root / "release"
            release.mkdir()
            script = root / "tools/clean_release.ps1"
            shutil.copyfile(Path(__file__).with_name("clean_release.ps1"), script)
            for version in ("1.9.0", "1.10.0"):
                (release / f"storeclean-{version}.apk").write_bytes(b"fixture")
                (release / f"storeclean-{version}.apk.idsig").write_bytes(b"sidecar")
            record = {"version": "1.10.0", "apk_sha256": hashlib.sha256(b"fixture").hexdigest()}
            artifacts = root / "analysis/release_artifacts"
            artifacts.mkdir(parents=True)
            (artifacts / "storeclean-1.10.0-verification.json").write_text(json.dumps(record), encoding="utf-8")
            before = {path.name: path.read_bytes() for path in release.iterdir()}
            result = subprocess.run(["powershell.exe", "-NoProfile", "-File", str(script)],
                                    capture_output=True, text=True, encoding="utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("DRY RUN: no file removed", result.stdout)
            self.assertIn("storeclean-1.9.0.apk.idsig", result.stdout)
            self.assertIn("Keep: " + str(release / "storeclean-1.10.0.apk"), result.stdout)
            self.assertEqual({path.name: path.read_bytes() for path in release.iterdir()}, before)


if __name__ == "__main__":
    unittest.main()
