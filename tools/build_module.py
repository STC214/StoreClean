"""Build, test and sign the standalone LSPosed release module using the local SDK."""

import argparse
import difflib
import hashlib
import json
import re
import struct
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "module"
ARTIFACTS = ROOT / "analysis/release_artifacts"
SDK = Path("F:/Android/Sdk")
BUILD_TOOLS = SDK / "build-tools/36.1.0"
ANDROID = SDK / "platforms/android-35/android.jar"
API = MODULE / "deps/xposed-api-82.jar"
API_SHA256 = "f48c635f1c7469fdec0e00ad2ea0b7a6b2f5b55065784a35b7ca3a84615e8e25"
SIGNING_CERT_SHA256 = "7afe9d9dda1cbf3ef70d23c29f98a55ef8a9d8a3bda280d98111a410eff31347"
MANIFEST = ET.parse(MODULE / "AndroidManifest.xml").getroot()
ANDROID_NS = "{http://schemas.android.com/apk/res/android}"
VERSION = MANIFEST.attrib[ANDROID_NS + "versionName"]
VERSION_CODE = int(MANIFEST.attrib[ANDROID_NS + "versionCode"])
RECORDS = []


def sha256(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def compilation_inputs():
    paths = [MODULE / "AndroidManifest.xml"]
    for folder in ("src", "res", "assets"):
        paths.extend(path for path in (MODULE / folder).rglob("*") if path.is_file())
    return {path.relative_to(MODULE).as_posix(): sha256(path) for path in sorted(paths)}


def require_matching_inputs(record):
    if record.get("compilation_inputs") != compilation_inputs():
        raise ValueError("APK inputs changed or snapshot missing; rebuild instead of refreshing sources")


def create_work_directory():
    parent = MODULE / "build" / VERSION
    parent.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="run-", dir=parent))


def promote_release(staging, release):
    stem = "storeclean-" + VERSION
    verification = staging / (stem + "-verification.json")
    record = json.loads(verification.read_text(encoding="utf-8"))
    names = {"apk": stem + ".apk", "patch": stem + ".patch", "source_zip": stem + "-source.zip"}
    # Complete validation precedes any replacement of the previous deliverables.
    for key, name in names.items():
        if sha256(staging / name) != record[key + "_sha256"]:
            raise ValueError("Staged artifact hash mismatch: " + name)
    release.mkdir(parents=True, exist_ok=True)
    artifacts = release.parent / "analysis/release_artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    for name in list(names.values()) + [stem + ".apk.idsig"]:
        source = staging / name
        if source.is_file():
            destination = release if name == names["apk"] else artifacts
            source.replace(destination / name)
    verification.replace(artifacts / verification.name)


def run(command):
    command = [str(part) for part in command]
    result = subprocess.run(command, cwd=ROOT, capture_output=True)
    record = {
        "command": command,
        "exit_code": result.returncode,
        "stdout": result.stdout.decode("utf-8", errors="replace"),
        "stderr": result.stderr.decode("utf-8", errors="replace"),
    }
    RECORDS.append(record)
    if result.returncode:
        raise RuntimeError(record)
    print(f"PASS command: {command[0]} {command[1] if len(command) > 1 else ''}")
    return record


def preflight():
    for path in (ANDROID, API, BUILD_TOOLS / "aapt.exe", BUILD_TOOLS / "lib/d8.jar"):
        if not path.is_file():
            raise FileNotFoundError(path)
    assert sha256(API) == API_SHA256, "Compile-only API dependency hash mismatch"
    assert re.fullmatch(r"\d+\.\d+\.\d+", VERSION) and VERSION_CODE > 0
    assert MANIFEST.find("application").get(ANDROID_NS + "debuggable") == "false"
    if not (MODULE / "signing/storeclean-dev.jks").is_file():
        raise FileNotFoundError("Existing signing key required for compatible release updates")
    ET.parse(MODULE / "res/values/arrays.xml")
    if MANIFEST.find("application").get(ANDROID_NS + "icon"):
        for density, size in (("mdpi", 48), ("hdpi", 72), ("xhdpi", 96), ("xxhdpi", 144), ("xxxhdpi", 192)):
            image = MODULE / "res" / ("mipmap-" + density) / "ic_launcher.png"
            data = image.read_bytes()
            assert data.startswith(b"\x89PNG\r\n\x1a\n")
            assert struct.unpack_from(">II", data, 16) == (size, size), image
    comparisons = json.loads((ROOT / "analysis/comparison.json").read_text(encoding="utf-8"))
    required = {
        "PrefUtils": [
            "getBoolean(Ljava/lang/String;Z[Lcom/xiaomi/market/util/PrefUtils$PrefFile;)Z",
            "setBoolean(Ljava/lang/String;Z[Lcom/xiaomi/market/util/PrefUtils$PrefFile;)V",
            "setBooleanSync(Ljava/lang/String;Z[Lcom/xiaomi/market/util/PrefUtils$PrefFile;)Z",
        ],
        "OrchardEntranceManager": ["isOpen()Z", "reopen()V"],
        "EntranceManager": ["getEntranceConfig()Lcom/xiaomi/market/util/EntranceConfig;", "needShowAnimation()Z"],
        "EntranceView": ["bindView(Landroid/content/Context;Ljava/lang/String;)V", "onFinishInflate()V"],
        "Preference": ["getPersistedBoolean(Z)Z", "persistBoolean(Z)Z"],
        "TwoStatePreference": ["setChecked(Z)V"],
        "FunctionSettingsFragment": [
            "onPreferenceChange(Landroidx/preference/Preference;Ljava/lang/Object;)Z",
            "onCreatePreferences(Landroid/os/Bundle;Ljava/lang/String;)V",
        ],
    }
    verified = []
    for version in comparisons["versions"]:
        directory = ROOT / version["directory"]
        count = 0
        for name, signatures in required.items():
            source = (directory / (name + ".smali")).read_text(encoding="utf-8")
            methods = re.findall(r"^\.method (.+)$", source, re.MULTILINE)
            for signature in signatures:
                assert any(method.endswith(" " + signature) for method in methods), (version["version"], name, signature)
                count += 1
        source = (directory / "SettingsUtils.smali").read_text(encoding="utf-8")
        for getter in version["getter_candidates"]:
            assert re.search(r"^\.method public static " + getter + r"\(\)Z$", source, re.MULTILINE)
            count += 1
        source = (directory / "OrchardSdkHelper.smali").read_text(encoding="utf-8")
        launches = re.findall(r"^\.method public final launchOrchard\([^\n]*\)V$", source, re.MULTILINE)
        h5 = re.findall(r"^\.method public final launchOrchardH5[^($]*\$?[^($]*\([^\n]*\)V$", source, re.MULTILINE)
        assert len(launches) >= 5
        parameters = ["Landroid/app/Activity;", "Ljava/lang/String;", "Ljava/lang/String;", "Ljava/lang/Integer;", "Ljava/util/Map;"]
        for length in range(1, 6):
            signature = "launchOrchard(" + "".join(parameters[:length]) + ")V"
            assert any(method.endswith(" " + signature) for method in launches), signature
        count += len(launches) + len(h5)
        assert count == 29 + len(launches) + len(h5)
        verified.append({"version": version["version"], "mandatory_hook_signatures": count,
                         "orchard_launches": len(launches), "h5_launches": len(h5), "status": "PASS"})
    print(f"PASS preflight: complete hook signatures exist in all {len(verified)} APK versions")
    return verified


def write_patch(destination):
    sources = [MODULE / "AndroidManifest.xml", MODULE / ".gitignore"]
    for directory in ("src", "tests", "fixtures", "res", "assets"):
        sources.extend(path for path in (MODULE / directory).rglob("*") if path.is_file())
    sources.extend(path for path in (ROOT / "tools").glob("*.py"))
    sources.extend(path for path in (ROOT / "tools").glob("*.ps1"))
    sources.extend(ROOT / name for name in (
        ".gitignore", "README.md", "CORE_REQUIREMENTS.md", "analysis/REPORT.md", "analysis/RUNTIME_VALIDATION.md",
        "analysis/COMPATIBILITY_1.1.0.md",
        "analysis/REVIEW_2026-10-15.md",
    ))
    if (MODULE / "README.md").exists():
        sources.append(MODULE / "README.md")
    patch = []
    for path in sorted(sources):
        name = path.relative_to(ROOT).as_posix()
        if path.suffix.lower() == ".png":
            # Native Git emits an applyable binary patch; exit 1 means a difference exists.
            result = subprocess.run(["git", "diff", "--no-index", "--binary", "--", "/dev/null", name],
                                    cwd=ROOT, capture_output=True)
            assert result.returncode == 1 and b"GIT binary patch" in result.stdout
            patch.append(result.stdout.decode("utf-8"))
        else:
            patch.append(f"diff --git a/{name} b/{name}\nnew file mode 100644\n")
            patch.extend(difflib.unified_diff([], path.read_text(encoding="utf-8").splitlines(keepends=True), fromfile="/dev/null", tofile="b/" + name))
    destination.write_text("".join(patch), encoding="utf-8", newline="\n")
    assert destination.read_text(encoding="utf-8").startswith("diff --git ")
    return sources


def refresh_sources():
    """Refresh source-only deliverables while preserving the installed, verified APK bytes."""
    release = ROOT / "release"
    verification = ARTIFACTS / ("storeclean-" + VERSION + "-verification.json")
    record = json.loads(verification.read_text(encoding="utf-8"))
    apk = Path(record["apk"])
    assert record["version"] == VERSION and record["version_code"] == VERSION_CODE
    assert sha256(apk) == record["apk_sha256"], "APK changed since build verification"
    require_matching_inputs(record)
    for key, suffix in (("patch", ".patch"), ("source_zip", "-source.zip")):
        path = ARTIFACTS / ("storeclean-" + VERSION + suffix)
        assert sha256(path) == record[key + "_sha256"], "Archived artifact changed before refresh"
        if record[key] != str(path):
            record.setdefault("paths_before_layout_change", {})[key] = record[key]
        record[key] = str(path)
    record["artifact_directory"] = str(ARTIFACTS)
    with zipfile.ZipFile(apk) as archive:
        assert archive.testzip() is None
    files = write_patch(Path(record["patch"]))
    run(["git", "apply", "--check", "--directory=module/build/patch-check", record["patch"]])
    with zipfile.ZipFile(record["source_zip"], "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(record["source_zip"]) as archive:
        assert archive.testzip() is None
        assert all(archive.read(path.relative_to(ROOT).as_posix()) == path.read_bytes() for path in files)
    record["patch_sha256"] = sha256(Path(record["patch"]))
    record["source_zip_sha256"] = sha256(Path(record["source_zip"]))
    rollback = run([sys.executable, "-X", "utf8", "tools/rollback_module.py"])
    assert "DRY RUN: no device command executed" in rollback["stdout"]
    record["source_refresh_commands"] = RECORDS
    # Preserve this build's runtime status. Never attach an older APK's observations.
    verification.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert sha256(apk) == record["apk_sha256"]
    print("PASS refreshed source ZIP and patch; APK bytes and runtime status unchanged")


def main():
    RECORDS.clear()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-inputs", action="store_true")
    parser.add_argument("--refresh-sources", action="store_true", help="Refresh documentation/source artifacts without rebuilding APK")
    args = parser.parse_args()
    targets = preflight()
    if args.check_inputs:
        return
    if args.refresh_sources:
        refresh_sources()
        return
    input_snapshot = compilation_inputs()
    run([sys.executable, "-X", "utf8", "tools/test_regressions.py", "-v"])
    work = create_work_directory()
    release = ROOT / "release"
    staging = work / "release"
    for path in (work, work / "classes", work / "tests", work / "dex", MODULE / "signing", staging):
        path.mkdir(parents=True, exist_ok=True)
    inventory = json.loads((ROOT / "analysis/inventory.json").read_text(encoding="utf-8"))
    original_hashes = {entry["file"]: sha256(ROOT / entry["file"]) for entry in inventory}
    assert all(original_hashes[entry["file"]] == entry["sha256"] for entry in inventory)
    sources = sorted((MODULE / "src").rglob("*.java"))
    tests = sorted((MODULE / "tests").rglob("*.java"))
    fixtures = sorted((MODULE / "fixtures").rglob("*.java"))
    flags = ["-J-Duser.language=en", "-J-Duser.country=US", "--release", "8", "-Xlint:-options", "-encoding", "UTF-8"]
    run(["javac"] + flags + ["-cp", str(ANDROID) + ";" + str(API), "-d", work / "classes"] + sources)
    test_classpath = ";".join(str(path) for path in (work / "tests", work / "classes", ANDROID, API))
    run(["javac"] + flags + ["-cp", str(work / "classes") + ";" + str(ANDROID) + ";" + str(API), "-d", work / "tests"] + fixtures + tests)
    run(["java", "-cp", test_classpath, "io.github.storeclean.PolicyTest"])
    for behavior in ("baseline", "enabled"):
        run(["java", "-cp", test_classpath, "io.github.storeclean.RuntimeFixtureTest", behavior])
    run(["java", "-cp", test_classpath, "io.github.storeclean.HookCallbackTest"])
    run(["jar", "cf", work / "bytecode.jar", "-C", work / "classes", "."])
    run(["java", "-cp", BUILD_TOOLS / "lib/d8.jar", "com.android.tools.r8.D8", "--min-api", "24", "--lib", ANDROID, "--classpath", API, "--output", work / "dex", work / "bytecode.jar"])
    run([BUILD_TOOLS / "aapt.exe", "package", "-f", "-M", MODULE / "AndroidManifest.xml", "-S", MODULE / "res", "-A", MODULE / "assets", "-I", ANDROID, "-F", work / "unsigned.apk"])
    with zipfile.ZipFile(work / "unsigned.apk", "a", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in (work / "dex").glob("classes*.dex"):
            archive.write(path, path.name)
    run([BUILD_TOOLS / "zipalign.exe", "-f", "4", work / "unsigned.apk", work / "aligned.apk"])
    key = MODULE / "signing/storeclean-dev.jks"
    apk = staging / ("storeclean-" + VERSION + ".apk")
    run(["java", "-jar", BUILD_TOOLS / "lib/apksigner.jar", "sign", "--ks", key, "--ks-key-alias", "storeclean-dev", "--ks-pass", "pass:android", "--key-pass", "pass:android", "--out", apk, work / "aligned.apk"])
    signing = run(["java", "-jar", BUILD_TOOLS / "lib/apksigner.jar", "verify", "--verbose", "--print-certs", apk])
    cert = re.search(r"Signer #1 certificate SHA-256 digest: ([0-9a-f]+)", signing["stdout"])
    assert cert and cert[1] == SIGNING_CERT_SHA256, "Unexpected module signing certificate"
    run([BUILD_TOOLS / "zipalign.exe", "-c", "4", apk])
    badging = run([BUILD_TOOLS / "aapt.exe", "dump", "badging", apk])
    assert f"versionCode='{VERSION_CODE}'" in badging["stdout"] and f"versionName='{VERSION}'" in badging["stdout"]
    manifest = run([BUILD_TOOLS / "aapt.exe", "dump", "xmltree", apk, "AndroidManifest.xml"])
    assert all(name in manifest["stdout"] for name in ("xposedmodule", "xposedminversion", "xposedscope"))
    assert "uses-permission" not in manifest["stdout"]
    assert "debuggable(0x0101000f)=(type 0x12)0x0" in manifest["stdout"]
    if MANIFEST.find("application").get(ANDROID_NS + "icon"):
        assert "android:icon" in manifest["stdout"] and "android:roundIcon" in manifest["stdout"]
        assert badging["stdout"].count("application-icon-") >= 5
    predecessor = release / ("storeclean-1.1.0.apk" if VERSION == "1.1.1" else "storeclean-1.0.0.apk")
    continuity = {"status": "baseline APK not present"}
    if predecessor.is_file():
        baseline_signing = run(["java", "-jar", BUILD_TOOLS / "lib/apksigner.jar", "verify", "--print-certs", predecessor])
        cert_pattern = r"Signer #1 certificate SHA-256 digest: ([0-9a-f]+)"
        cert = re.search(cert_pattern, signing["stdout"]).group(1)
        assert cert == re.search(cert_pattern, baseline_signing["stdout"]).group(1)
        with zipfile.ZipFile(predecessor) as old, zipfile.ZipFile(apk) as new:
            identical_dex = old.read("classes.dex") == new.read("classes.dex")
        continuity = {"status": "PASS", "baseline_sha256": sha256(predecessor), "same_signing_certificate": cert,
                      "identical_classes_dex": identical_dex}
    with zipfile.ZipFile(apk) as archive:
        assert archive.testzip() is None
        assert archive.read("assets/xposed_init").decode("utf-8").strip() == "io.github.storeclean.StoreHooks"
        assert archive.read("classes.dex").startswith(b"dex\n")
        assert not any("xposed-api" in name or name.endswith(".java") for name in archive.namelist())
        packaged_icons = [name for name in archive.namelist() if name.endswith("/ic_launcher.png")]
        if MANIFEST.find("application").get(ANDROID_NS + "icon"):
            assert len(packaged_icons) == 5
        data = archive.read("classes.dex")
        strings_offset = struct.unpack_from("<I", data, 0x3C)[0]
        types_offset = struct.unpack_from("<I", data, 0x44)[0]
        count, classes_offset = struct.unpack_from("<II", data, 0x60)
        defined_classes = []
        for index in range(count):
            type_index = struct.unpack_from("<I", data, classes_offset + index * 32)[0]
            string_index = struct.unpack_from("<I", data, types_offset + type_index * 4)[0]
            cursor = struct.unpack_from("<I", data, strings_offset + string_index * 4)[0]
            while data[cursor] & 0x80:
                cursor += 1
            cursor += 1
            name = data[cursor:data.index(b"\0", cursor)].decode("utf-8")
            assert name.startswith("Lio/github/storeclean/") and "Test;" not in name
            defined_classes.append(name)
    patch = staging / ("storeclean-" + VERSION + ".patch")
    files = write_patch(patch)
    run(["git", "apply", "--check", "--directory=module/build/patch-check", patch])
    rollback = run([sys.executable, "-X", "utf8", "tools/rollback_module.py"])
    assert "DRY RUN: no device command executed" in rollback["stdout"]
    source_zip = staging / ("storeclean-" + VERSION + "-source.zip")
    with zipfile.ZipFile(source_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(source_zip) as archive:
        assert archive.testzip() is None
    assert original_hashes == {name: sha256(ROOT / name) for name in original_hashes}
    assert compilation_inputs() == input_snapshot, "APK sources changed during the build; rebuild required"
    record = {
        "version": VERSION,
        "compilation_inputs": input_snapshot,
        "version_code": VERSION_CODE,
        "channel": "release",
        "debuggable": False,
        "application_icon": MANIFEST.find("application").get(ANDROID_NS + "icon"),
        "packaged_icons": packaged_icons,
        "predecessor_continuity": continuity,
        "predecessor_runtime_evidence": "analysis/RUNTIME_VALIDATION.md (0.1.0 on app store 4.126.10 only)",
        "apk": str(release / apk.name),
        "apk_sha256": sha256(apk),
        "patch": str(ARTIFACTS / patch.name),
        "patch_sha256": sha256(patch),
        "source_zip": str(ARTIFACTS / source_zip.name),
        "source_zip_sha256": sha256(source_zip),
        "defined_dex_classes": defined_classes,
        "rollback": {"script": str(ROOT / "tools/rollback_module.py"), "dry_run": "PASS", "device_execution": "NOT TESTED"},
        "dependency": {"url": "https://api.xposed.info/de/robv/android/xposed/api/82/api-82.jar", "sha256": API_SHA256, "packaged": False},
        "static_hook_validation": targets,
        "original_apk_hashes_unchanged": original_hashes,
        "commands": RECORDS,
        "device_runtime": "NOT TESTED FOR THIS APK; predecessor evidence is recorded separately",
        "fixture_scope": "Production callbacks are tested with explicit host fakes; no Android rendering or real Xposed engine is executed",
        "artifact_directory": str(ARTIFACTS),
    }
    verification = staging / ("storeclean-" + VERSION + "-verification.json")
    verification.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert json.loads(verification.read_text(encoding="utf-8"))["apk_sha256"] == sha256(apk)
    promote_release(staging, release)
    print(f"BUILT {record['apk']}\nSHA256 {record['apk_sha256']}\nVERIFIED {ARTIFACTS / verification.name}")


if __name__ == "__main__":
    main()
