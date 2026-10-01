# 真机观察与日志核对

日期：2026-10-01。此记录保存本项目对话中已读取的证据，不代表发行版重新安装后的实测。

## 已确认环境

- 设备：23117RK66C，代号 manet；ADB 已连接，`su` 可读取 LSPosed 日志。
- 应用商店：4.126.10 / 40007640。
- 已安装模块：0.1.0 / 1；APK SHA-256 为 `909a039fe44e6458cc6ad070e98213dc845a75e528c71f8e7580e9366ecf4648`，与原构建产物一致。
- Android/HyperOS 和 LSPosed 具体版本未完整登记。

## 用户视觉反馈

用户确认模块视觉生效；进入功能设置页后，受控选项不可操作，开关开闭符合需求。视觉反馈来自用户现场观察，未另行保存逐项截图或 UI 自动化断言。

## 实际读取的日志

日志文件：`/data/adb/lspd/log/modules_2026-10-01T13:44:33.600472.log`。

```text
258:[ 2026-10-01T13:46:53.029    10168: 20032: 20032 I/LSPosedFramework ] (com.xiaomi.market:guard)[io.github.storeclean,XposedBridge,4e40-1a0f60058e5-2-1,0,1] [StoreClean] active version=4.126.10 hooks=34 controlled writes=blocked
459:[ 2026-10-01T13:59:36.371    10168: 26358: 26358 I/LSPosedFramework ] (com.xiaomi.market)[io.github.storeclean,XposedBridge,66f6-1a0f60bfead-2-1,0,1] [StoreClean] active version=4.126.10 hooks=34 controlled writes=blocked
```

verbose 日志也包含同样两条记录。`ps -A` 确认主进程 PID 为 26358。

检查命令与结果（当次读取的退出码均为 0）：

```text
adb -s SERIAL shell su -c 'grep -n -e StoreClean -e storeclean /data/adb/lspd/log/modules_2026-10-01T13:44:33.600472.log'
# 输出为上方两条记录。
adb -s SERIAL logcat -d -b crash -v threadtime
# stdout 为空。
adb -s SERIAL logcat -d --pid=26358 -v threadtime -s AndroidRuntime LSPosed-Bridge Xposed LSPosed
# stdout 为空。
```

`SERIAL` 表示当次连接设备，避免在共享文档中记录设备序列号。检查期间未重启应用、未清空日志、未执行卸载回退。

## 结论与边界

- 主界面进程的 34 个 Hook 注册成功；所读取模块记录未见初始化失败，当前崩溃缓冲区为空。
- 日志与用户视觉反馈一致。日志只记录初始化，`controlled writes=blocked` 不是逐项写入拦截事件，亦不独立证明每个功能路径已运行。
- 1.0.0 保留 Hook 行为；其新包的版本、调试属性、签名和 DEX 连续性由构建验证 JSON 检查，不能据此声称新包已真机安装。
- 待验证：1.0.0 覆盖更新、s.1/s.2、进程重启/云控刷新、深链阻断、核心业务、安全检测排除项以及禁用/卸载后的设备回退。
