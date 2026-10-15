# StoreClean 1.1.0：新旧应用商店兼容性

日期：2026-10-15。目标：当前 ADB 手机中的 `com.xiaomi.market`；只覆盖本模块及指定应用的验证，不修改原商店 APK 或清除应用数据。

## 样本身份

- 新版：4.127.11 / 40007661，64,548,165 字节，五个 DEX。
- 原件：`store_apk/device_4.127.11/com.xiaomi.market/base.apk`；分析副本：`analysis/apk_4/input.apk`。
- APK SHA-256：`1ac3be37cf56b29f417278903bca831e1623662e663b86b901316fae6fcebd10`。
- 签名验证通过，证书 SHA-256 与旧样本相同：`c9009d01ebf9f5d0302bc71b2fe9aa9a47a432bba17308a3111b75d7b2149025`。
- REA 拉取证据：`ev_9b7c6ce9e6e3072f42abacc540927de0beec3521a7ee6337df60d03b609a23a1`，覆盖完整 APK 集合，仅有 base.apk。原件与副本哈希及设备端 APK 哈希一致。
- 当前手机型号 2510DRK44C，代号 annibale；手机原模块为 0.1.0，不是此前生成但未安装的 1.0.0。

## 观察与差异

| 项目 | 旧 4.126.10 | 新 4.127.11 | 证据 / 结论类型 |
| --- | --- | --- | --- |
| 模块门控 | 启用 34 Hook | 旧模块输出 unsupported version | 设备日志观察 |
| 功能菜单 | 16 个 key、4 个分组 | 相同 | 静态 XML 与 zh-rCN 资源比较 |
| 左侧活动入口 | EntranceView.bindView / onFinishInflate | 同名同参数方法仍存在 | 静态方法和布局证据，不声称整个类字节一致 |
| launchOrchard | 5 个重载 | 7 个重载 | SDK 类 smali |
| H5 启动 | 无独立 H5 方法 | launchOrchardH5$app_release | SDK smali，包含 Activity.startActivity 调用 |

新增重载在原 Activity/String/String/Integer/Map 参数后扩展 boolean 和回调类型 `l8.o`；新七参数重载中存在 H5 方法调用。Kotlin `$default` 包装调用相应原方法，因此阻断原启动方法也覆盖这些包装调用。

由日志直接确认本次图标重现时旧模块被版本门控跳过；静态分析另揭示旧“五个重载”的硬断言不适用新版。两者是不同层级的原因，不能将后者误报为旧模块在手机上实际执行过的异常。

完整差异：`analysis/update_comparison.json`；目标方法、XML 和 59 条调用引用保存在 `analysis/apk_4/`。分析命令及退出码见其 `evidence_commands.json` 与 `trace_commands.json`。

## 实现与边界

- 1.1.0 / versionCode 3，沿用现有包名及签名。登记新增版本；老样本仍注册 34 Hook，新样本注册 37 Hook。
- 不再将果树启动重载数量固定为五个；拦截全部发现的 launchOrchard 与非默认包装 launchOrchardH5 方法，并检查 void 返回及 Activity 首参数。
- 未登记且格式正常的 4.x 版本可进入结构探测，但必须通过四个分组的完整 16-key 菜单检查，以及全部 Hook 类、参数与返回类型检查，才注册；已登记名称配错版本号、其他主版本、缺项、重复 key、新增设置或分组变化均不盲目启用。
- 15 个受控开关仍为 11 关、4 开；安全检测开关继续排除，未直接改写偏好文件。
- JVM 测试覆盖已登记版本、候选版本和错误版本、菜单缺项/重复/新增/错组、偏好排除、写入拦截与 View 隐藏。静态和 host fake 测试不等同于未知版本业务验证。

## 真机验证

用户明确批准安装并验证。命令的完整参数、字面输出与退出码保存在 `analysis/device_1.1.0/`：

- `before-commands.json`：备份已安装模块、确认原版本和 unsupported 日志。
- `upgrade-commands.json`：`adb install -r` 返回 Success，结束并启动应用商店；未清除数据。
- `after-commands.json`：安装包哈希与本地 1.1.0 APK 一致；商店原件哈希不变；主进程注入成功。
- `settings-commands.json` / `settings-bottom-commands.json`：设置页面观察与导航命令。

关键新日志：

```text
2026-10-15T09:55:58.188 (com.xiaomi.market) PID 32280
[StoreClean] active version=4.127.11 hooks=37 controlled writes=blocked profile=registered schema=16
```

用户已确认入口消失、设置开关正常；`after-screen.png` 为亮屏首页，未见左侧水果入口，搜索栏仍显示。`settings-screen.png` 显示导航/游戏开关关闭且为禁用样式，手机清理开启。其余开关完整性由用户现场确认，未声称全部均有独立自动化截图断言。下半页捕获期间用户已返回首页，`settings-bottom-screen.png` 不用作下半页开关证据。

首次采集时手机处于 Dozing，黑屏截图不作为图标消失证据。普通 shell 的 UI dump 和滑动未获设备所需权限；滑动改用已有 Root 会话，未修改设备安全配置。崩溃缓冲包含其他历史系统记录，未据此宣称整个缓冲为空。

## 待验证与回退

- 未登记版本的结构探测仅有策略测试，尚无其他 APK / 真机实测，不保证任意未来版本兼容。
- 旧三个样本完成静态与 JVM 回归，没有在当前手机逐一替换商店验证。
- H5 / 深链阻断尚无独立真机点击用例；搜索、下载、安装、更新、安全检测业务与云控刷新亦未做完整专项回归。
- 设备回退未实际执行，以免撤销已确认生效的模块；可在 LSPosed 禁用模块后重启商店，或使用 `tools/rollback_module.py` 先预览、确认后卸载模块。旧安装包备份保留，但低版本覆盖安装可能受 Android 降级限制，不承诺直接降级命令成功。
