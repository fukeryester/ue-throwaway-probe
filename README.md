# UE 即用即弃探针

在已经开着的虚幻编辑器里跑一段只读 Python，读取当前 PIE，把文本交回来。脚本不进入玩法工程，也不走 Live Coding。

设计说明在 `design/UE即用即弃探针设计案.md`。给 AI 的操作手册在 `.cursor/skills/ue-throwaway-probe/SKILL.md`。

## 安装到虚幻工程

1. 编辑器里启用 Python Editor Script Plugin。
2. 在本仓库根目录执行：

```bash
python -m client.probe_cli install --project-root "<含 .uproject 的目录>"
```

这会把 `plugin/ProbeHelper` 拷到该工程的 `Plugins/ProbeHelper`，并在 `Config/DefaultEngine.ini` 里补上远程执行配置。组播 TTL 为 0，只绑 `127.0.0.1`。

3. 重启编辑器。`Content/Python/init_unreal.py` 会载入 `ProbeHelper`。

Remote Control 的可选配置在 `install/DefaultRemoteControl.ini.snippet`。本仓库的客户端走的是 Python 插件的 Remote Execution，不走 HTTP。

## 发送一次探针

```bash
python -m client.probe_cli run --project-root "<含 .uproject 的目录>" --timeout 20 --script -
```

标准输入是当次脚本。`--project-root` 必须和编辑器回报的工程目录一致；对不上就不会执行。

返回文本以 `ok=true` 或 `ok=false` 开头。`miss.property=` 是属性名不存在，`null` 是值存在但为空。

## 仓库里有什么

| 路径 | 作用 |
|------|------|
| `plugin/ProbeHelper` | 编辑器插件。找 PIE 世界、读反射属性 |
| `client/probe_cli.py` | 发现本机编辑器、扫描脚本、发送并打印结果 |
| `client/readonly_scan.py` | 发送前拒绝写入、`import unreal` 和无界循环 |
| `optional/lua/probe_eval.lua` | 工程里已经有 Lua 虚拟机时的第二通道，不附带 UnLua |

`ProbeHelper.prepare` 会在源码哈希变化时重新加载模块。编辑器里的文件和本仓库不一致时，结果是 `error.helper=hash_mismatch`，需要重新 install 并重启编辑器。

官方的 `ExecuteFile` 在编辑器游戏线程上执行。客户端不再把调用丢到后台线程。
