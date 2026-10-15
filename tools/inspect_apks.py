"""Read-only APK inventory and targeted DEX/resource evidence collection."""

import hashlib
import json
import re
import shutil
import struct
import subprocess
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AAPT = Path("F:/Android/Sdk/build-tools/36.1.0/aapt.exe")
KEYWORDS = re.compile(
    r"导航栏管理|游戏服务管理|其他功能管理|我的页功能管理|应用安全检测|种果树|"
    r"fruit|orchard|plant|function.?setting|navigation.?manage|game.?service|"
    r"feature.?manage|mine.?setting|tab.?manage|home.?activity|welfare|"
    r"功能设置|签到|种树",
    re.IGNORECASE,
)


def dex_strings(data):
    if not data.startswith(b"dex\n"):
        raise ValueError("Unsupported DEX header")
    count, offset = struct.unpack_from("<II", data, 0x38)
    for index in range(count):
        cursor = struct.unpack_from("<I", data, offset + index * 4)[0]
        while data[cursor] & 0x80:
            cursor += 1
        cursor += 1
        end = data.index(b"\0", cursor)
        yield data[cursor:end].decode("utf-8", errors="replace")


def capture(command, output):
    result = subprocess.run(command, capture_output=True, check=False)
    output.write_bytes(result.stdout)
    record = {
        "command": [str(value) for value in command],
        "exit_code": result.returncode,
        "stdout_path": str(output.relative_to(ROOT)),
        "stderr": result.stderr.decode("utf-8", errors="replace"),
    }
    if result.returncode:
        raise RuntimeError(record)
    return record


def main():
    output = ROOT / "analysis"
    output.mkdir(exist_ok=True)
    inventory_path = output / "inventory.json"
    entries = json.loads(inventory_path.read_text(encoding="utf-8")) if inventory_path.exists() else []
    for apk in sorted((ROOT / "store_apk").glob("*.apk")):
        known = next((entry for entry in entries if ROOT / entry["file"] == apk), None)
        if known:
            with apk.open("rb") as source:
                assert hashlib.file_digest(source, "sha256").hexdigest() == known["sha256"], "Registered original changed"
            with (ROOT / known["copy"]).open("rb") as source:
                assert hashlib.file_digest(source, "sha256").hexdigest() == known["sha256"], "Registered copy changed"
            print(f"{apk.name}: existing evidence preserved")
            continue
        number = 1
        while (output / f"apk_{number}").exists():
            number += 1
        directory = output / f"apk_{number}"
        directory.mkdir(exist_ok=True)
        with apk.open("rb") as source:
            original_hash = hashlib.file_digest(source, "sha256").hexdigest()
        copy = directory / "input.apk"
        shutil.copyfile(apk, copy)
        with copy.open("rb") as source:
            assert original_hash == hashlib.file_digest(source, "sha256").hexdigest()
        commands = [
            capture([str(AAPT), "dump", "badging", str(copy)], directory / "badging.txt"),
            capture([str(AAPT), "dump", "--values", "resources", str(copy)], directory / "resources.txt"),
            capture([str(AAPT), "dump", "xmltree", str(copy), "AndroidManifest.xml"], directory / "manifest.txt"),
        ]
        hits = []
        dex_inventory = []
        with zipfile.ZipFile(apk) as archive:
            corrupt = archive.testzip()
            if corrupt:
                raise ValueError(f"Corrupt archive member: {corrupt}")
            for name in archive.namelist():
                if re.fullmatch(r"classes\d*\.dex", name):
                    data = archive.read(name)
                    strings = list(dex_strings(data))
                    dex_inventory.append({"name": name, "sha256": hashlib.sha256(data).hexdigest(), "strings": len(strings)})
                    hits.extend({"dex": name, "string": value} for value in strings if KEYWORDS.search(value))
        (directory / "dex_hits.json").write_text(json.dumps(hits, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        resources = (directory / "resources.txt").read_text(encoding="utf-8", errors="replace").splitlines()
        resource_hits = []
        for index, line in enumerate(resources):
            if KEYWORDS.search(line):
                resource_hits.append("\n".join(resources[max(0, index - 3):index + 2]))
        (directory / "resource_hits.txt").write_text("\n\n".join(resource_hits) + "\n", encoding="utf-8")
        with apk.open("rb") as source:
            final_hash = hashlib.file_digest(source, "sha256").hexdigest()
        assert original_hash == final_hash, "Original APK changed"
        entry = {"file": str(apk.relative_to(ROOT)), "analysis_directory": str(directory.relative_to(ROOT)), "copy": str(copy.relative_to(ROOT)), "bytes": apk.stat().st_size, "sha256": original_hash, "unchanged": True, "zip_integrity": "passed", "dex": dex_inventory, "commands": commands, "dex_hits": len(hits)}
        entries.append(entry)
        print(f"{apk.name}: sha256={original_hash}; dex={len(dex_inventory)}; hits={len(hits)}; unchanged=True")
    inventory_path.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
