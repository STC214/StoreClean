"""Build, test and sign the standalone LSPosed release module using the local SDK."""

import argparse
import difflib
import hashlib
import json
import re
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "module"
SDK = Path("F:/Android/Sdk")
BUILD_TOOLS = SDK / "build-tools/36.1.0"
ANDROID = SDK / "platforms/android-35/android.jar"
API = MODULE / "deps/xposed-api-82.jar"
API_SHA256 = "f48c635f1c7469fdec0e00ad2ea0b7a6b2f5b55065784a35b7ca3a84615e8e25"
MANIFEST = ET.parse(MODULE / "AndroidManifest.xml").getroot()
ANDROID_NS = "{http://schemas.android.com/apk/res/android}"
VERSION = MANIFEST.attrib[ANDROID_NS + "versionName"]
VERSION_CODE = int(MANIFEST.attrib[ANDROID_NS + "versionCode"])
RECORDS = []


def sha256(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


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
    sources.extend(ROOT / name for name in (
        ".gitignore", "README.md", "CORE_REQUIREMENTS.md", "analysis/REPORT.md", "analysis/RUNTIME_VALIDATION.md",
        "analysis/COMPATIBILITY_1.1.0.md",
    ))
    if (MODULE / "README.md").exists():
        sources.append(MODULE / "README.md")
    patch = []
    for path in sorted(sources):
        name = path.relative_to(ROOT).as_posix()
        patch.extend(difflib.unified_diff([], path.read_text(encoding="utf-8").splitlines(keepends=True), fromfile="/dev/null", tofile="b/" + name))
    destination.write_text("".join(patch), encoding="utf-8")
    assert destination.read_text(encoding="utf-8").startswith("--- /dev/null\n")
    return sources


def refresh_sources():
    """Refresh source-only deliverables while preserving the installed, verified APK bytes."""
    release = ROOT / "release"
    verification = release / ("storeclean-" + VERSION + "-verification.json")
    record = json.loads(verification.read_text(encoding="utf-8"))
    apk = Path(record["apk"])
    assert record["version"] == VERSION and record["version_code"] == VERSION_CODE
    assert sha256(apk) == record["apk_sha256"], "APK changed since build verification"
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
    device = ROOT / "analysis/device_1.1.0"
    evidence = []
    for stage in ("before", "upgrade", "after", "settings", "settings-bottom"):
        path = device / (stage + "-commands.json")
        if path.is_file():
            evidence.append({"path": str(path.relative_to(ROOT)), "sha256": sha256(path)})
    record["device_runtime_evidence"] = {
        "report": "analysis/COMPATIBILITY_1.1.0.md", "records": evidence,
        "scope": "Observed on 4.127.11 only; user confirmed entrance/settings; no unknown-version runtime test",
    }
    if evidence:
        record["device_runtime"] = "See separate device evidence and its scoped conclusions; APK bytes preserved"
    verification.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert sha256(apk) == record["apk_sha256"]
    print("PASS refreshed source ZIP, patch and evidence references; installed APK unchanged")


def main():
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
    work = MODULE / "build" / VERSION
    release = ROOT / "release"
    for path in (work, work / "classes", work / "tests", work / "dex", MODULE / "signing", release):
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
    apk = release / ("storeclean-" + VERSION + ".apk")
    run(["java", "-jar", BUILD_TOOLS / "lib/apksigner.jar", "sign", "--ks", key, "--ks-key-alias", "storeclean-dev", "--ks-pass", "pass:android", "--key-pass", "pass:android", "--out", apk, work / "aligned.apk"])
    signing = run(["java", "-jar", BUILD_TOOLS / "lib/apksigner.jar", "verify", "--verbose", "--print-certs", apk])
    run([BUILD_TOOLS / "zipalign.exe", "-c", "4", apk])
    badging = run([BUILD_TOOLS / "aapt.exe", "dump", "badging", apk])
    assert f"versionCode='{VERSION_CODE}'" in badging["stdout"] and f"versionName='{VERSION}'" in badging["stdout"]
    manifest = run([BUILD_TOOLS / "aapt.exe", "dump", "xmltree", apk, "AndroidManifest.xml"])
    assert all(name in manifest["stdout"] for name in ("xposedmodule", "xposedminversion", "xposedscope"))
    assert "uses-permission" not in manifest["stdout"]
    assert "debuggable(0x0101000f)=(type 0x12)0x0" in manifest["stdout"]
    predecessor = release / "storeclean-1.0.0.apk"
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
    patch = release / ("storeclean-" + VERSION + ".patch")
    files = write_patch(patch)
    run(["git", "apply", "--check", "--directory=module/build/patch-check", patch])
    rollback = run([sys.executable, "-X", "utf8", "tools/rollback_module.py"])
    assert "DRY RUN: no device command executed" in rollback["stdout"]
    source_zip = release / ("storeclean-" + VERSION + "-source.zip")
    with zipfile.ZipFile(source_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(source_zip) as archive:
        assert archive.testzip() is None
    assert original_hashes == {name: sha256(ROOT / name) for name in original_hashes}
    record = {
        "version": VERSION,
        "version_code": VERSION_CODE,
        "channel": "release",
        "debuggable": False,
        "predecessor_continuity": continuity,
        "predecessor_runtime_evidence": "analysis/RUNTIME_VALIDATION.md (0.1.0 on app store 4.126.10 only)",
        "apk": str(apk),
        "apk_sha256": sha256(apk),
        "patch": str(patch),
        "patch_sha256": sha256(patch),
        "source_zip": str(source_zip),
        "source_zip_sha256": sha256(source_zip),
        "defined_dex_classes": defined_classes,
        "rollback": {"script": str(ROOT / "tools/rollback_module.py"), "dry_run": "PASS", "device_execution": "NOT TESTED"},
        "dependency": {"url": "https://api.xposed.info/de/robv/android/xposed/api/82/api-82.jar", "sha256": API_SHA256, "packaged": False},
        "static_hook_validation": targets,
        "original_apk_hashes_unchanged": original_hashes,
        "commands": RECORDS,
        "device_runtime": "NOT TESTED FOR THIS APK; predecessor evidence is recorded separately",
        "fixture_scope": "Production callbacks are tested with explicit host fakes; no Android rendering or real Xposed engine is executed",
    }
    verification = release / ("storeclean-" + VERSION + "-verification.json")
    verification.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert json.loads(verification.read_text(encoding="utf-8"))["apk_sha256"] == sha256(apk)
    print(f"BUILT {apk}\nSHA256 {record['apk_sha256']}\nVERIFIED {verification}")


if __name__ == "__main__":
    main()
