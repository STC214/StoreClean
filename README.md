# StoreClean

StoreClean 是一个面向 Android 应用商店的 LSPosed 模块。项目目标、受控设置及详细验收条件见 [`CORE_REQUIREMENTS.md`](CORE_REQUIREMENTS.md)；APK 静态分析与运行记录见 [`analysis/REPORT.md`](analysis/REPORT.md) 和 [`analysis/RUNTIME_VALIDATION.md`](analysis/RUNTIME_VALIDATION.md)。

## 项目结构

- `module/`：模块源码、Android 清单、资源、fixture 与 JVM 测试；模块使用说明见 [`module/README.md`](module/README.md)。
- `tools/`：APK 分析、证据校验、构建和回退脚本。
- `analysis/`：版本比较、分析报告及验证记录。
- `store_apk/`：用于分析的 APK 输入，保留在本地。
- `release/`：已生成的发行 APK、源码归档、补丁和构建验证记录，保留在本地。

## 环境要求

- Python 3
- JDK（`javac`、`java`、`jar`）
- Android SDK；构建脚本当前指向 `F:/Android/Sdk`，使用 Android 35 平台和 Build Tools 36.1.0
- 构建正式升级包需存在项目现有签名材料 `module/signing/storeclean-dev.jks`。密钥不纳入版本库。

## 分析与验证

在项目根目录运行：

```text
python -X utf8 tools/verify_analysis.py
```

该命令复核分析脚本、APK 副本哈希、签名及已采集类的一致性，并更新 `analysis/verification_commands.json`。详细命令与结果保存在 `analysis/` 下的 JSON 记录中。

## 构建

先检查输入及本机构建条件，再构建发行包：

```text
python -X utf8 tools/build_module.py --check-inputs
python -X utf8 tools/build_module.py
```

构建结果写入 `release/`，中间产物写入 `module/build/`。构建脚本会运行 JVM/fixture 测试并生成 APK、源码归档、补丁及验证 JSON。发行和设备验收的具体步骤见 [`module/README.md`](module/README.md)。

## 回退

常规回退是在 LSPosed 中停用模块并重启目标应用进程。设备回退脚本默认仅预览：

```text
python -X utf8 tools/rollback_module.py
```

确认目标设备后，按 `module/README.md` 的说明显式传入设备序列号和 `--apply`。脚本回退会卸载本模块并结束目标应用进程，不会卸载目标应用或清除其数据。

## 本地文件与临时产物

原始 APK、发行产物、提取分析目录、构建目录、依赖缓存和签名材料按 `.gitignore` 规则留在本地或排除于版本控制。临时分析下载文件及 Python 缓存不属于项目文档或源码。
