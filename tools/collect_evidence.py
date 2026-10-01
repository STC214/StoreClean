"""Collect reproducible smali and settings XML for the three inventoried APKs."""

import json
import re
from pathlib import Path

from inspect_apks import AAPT, ROOT, capture


CLASSES = (
    "com.xiaomi.market.business_ui.settings.function.FunctionSettingsFragment",
    "com.xiaomi.market.business_ui.settings.PreferenceHelperKt",
    "com.xiaomi.market.util.SettingsUtils",
    "com.xiaomi.market.util.OrchardEntranceManager",
    "com.xiaomi.market.util.PrefUtils",
    "com.xiaomi.market.model.PageConfig",
    "com.xiaomi.market.incentive.orchard.OrchardSdkHelper",
    "com.xiaomi.market.incentive.IncentiveSDKHelper",
    "com.xiaomi.market.incentive.IncentiveRouter",
    "com.xiaomi.market.business_ui.main.MarketTabActivity",
    "com.xiaomi.market.business_ui.main.home.NativeHomePagePagerFragment",
    "com.xiaomi.market.business_ui.main.home.HomeFeatureTabFragment",
    "com.xiaomi.market.widget.MainSearchContainer",
    "com.xiaomi.market.ui.DoubleTabProxyActivityWrapper",
    "com.xiaomi.market.ui.entrance.EntranceView",
    "com.xiaomi.market.util.EntranceManager",
    "com.xiaomi.market.util.EntranceConfig",
    "androidx.preference.Preference",
    "androidx.preference.TwoStatePreference",
)
JAVA = [
    "java",
    "-Dcom.android.sdklib.toolsdir=F:/Android/Sdk/cmdline-tools/latest",
    "-classpath",
    "F:/Android/Sdk/cmdline-tools/latest/lib/apkanalyzer-classpath.jar",
    "com.android.tools.apk.analyzer.ApkAnalyzerCli",
]


def main():
    inventory = json.loads((ROOT / "analysis/inventory.json").read_text(encoding="utf-8"))
    for entry in inventory:
        directory = ROOT / entry["analysis_directory"]
        apk = ROOT / entry["copy"]
        command_file = directory / "evidence_commands.json"
        commands = json.loads(command_file.read_text(encoding="utf-8")) if command_file.exists() else []
        for name in CLASSES:
            artifact = directory / (name.rsplit(".", 1)[1] + ".smali")
            if not artifact.exists():
                commands.append(capture(JAVA + ["dex", "code", "--class", name, str(apk)], artifact))
        resources = (directory / "resources.txt").read_text(encoding="utf-8")
        match = re.search(r"resource 0x[0-9a-f]+ com\.xiaomi\.market:xml/function_settings:.*?\n\s+\(string8\) \"([^\"]+)\"", resources)
        if not match:
            raise ValueError("Missing function_settings XML")
        artifact = directory / "function_settings.xmltree.txt"
        if not artifact.exists():
            commands.append(capture([str(AAPT), "dump", "xmltree", str(apk), match[1]], artifact))
        for layout in ("native_main_search_box_layout", "main_search_container"):
            match = re.search(r"resource 0x[0-9a-f]+ com\.xiaomi\.market:layout/" + layout + r":.*?\n\s+\(string8\) \"([^\"]+)\"", resources)
            if not match:
                raise ValueError("Missing layout: " + layout)
            artifact = directory / (layout + ".xmltree.txt")
            if not artifact.exists():
                commands.append(capture([str(AAPT), "dump", "xmltree", str(apk), match[1]], artifact))
        command_file.write_text(json.dumps(commands, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{directory.name}: {len(commands)} evidence commands passed")


if __name__ == "__main__":
    main()
