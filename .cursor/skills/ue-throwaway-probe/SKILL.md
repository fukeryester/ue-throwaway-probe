---
name: ue-throwaway-probe
description: >-
  在已打开的虚幻编辑器里执行一段只读、即用即弃的 Python，读取当前 PIE 世界并把文本交回来。
  使用 ProbeHelper 与 client.probe_cli。当用户要在 UE / Unreal 里查看正在跑的对局、Actor、组件或反射属性，
  或提到即用即弃探针、PIE 状态、ProbeHelper 时使用。禁止 Live Coding、热重载和改玩法工程。
---

# UE 即用即弃探针

在已打开的编辑器里执行一段只读脚本，读当前 PIE，把文本交回来。

仓库根目录执行命令。脚本只存在于本次调用，不写入玩法工程。

## 铁律

1. 唯一允许 AI 产生的代码是当次脚本字符串。禁止改游戏 C++、蓝图、玩法 Lua、配置和资源。
2. 禁止触发 Live Coding、模块重编译、编辑器重启、资产保存。
3. 世界只能来自 `ProbeHelper.GetPieWorld()`。
4. 读属性只用 `TryGetProperty` / `FormatProperty`。禁止用「值是 None」判断成员不存在。
5. 默认只读。脚本里出现生成、销毁、改属性、发 RPC，视为越界，不发送。
6. 一次一问。脚本只回答当前排查，不顺手修 Bug。
7. 通道没返回 `ok=` 行，就汇报通道失败，不编造对局状态。

`client/readonly_scan.py` 会在发送前拒绝 `import unreal`、属性赋值、`while`、`set_*` / `spawn` / `destroy`，以及 `CallReflected` 的非常量或写入函数名。扫描失败时不要改扫描器来放行。

## 调用

编辑器需已打开，并启用 Python 远程执行（`install/DefaultEngine.ini.snippet`，组播 TTL 为 0，只绑 127.0.0.1）。`--project-root` 必须和对上的那个编辑器工程目录一致。超时默认 20 秒。执行模式固定为 `ExecuteFile`。

```bash
python -m client.probe_cli run --project-root "<uproject 所在目录>" --timeout 20 --script -
```

脚本从标准输入送入。需要命令参数时用 `--code`，不要同时传 `--script`。

返回文本里先看 `ok`、`error.*`、`miss.*`，再解释对局。`ok=false` 且没有任何 `error.*` 或 `miss.*` 时，当作通道失败。

| 行 | 含义 |
|----|------|
| `ok=true` | 脚本跑完，下面的值是这次读到的状态 |
| `ok=false` | 没读成。继续看原因行 |
| `error.world=none` | 没有 PIE。不要改用编辑器世界 |
| `error.world=multiple count=N` | 不止一个 PIE，不猜测 |
| `error.world=cannot_detect_pie` | 当前引擎绑定无法判断 PIE |
| `error.channel=no_node` | 没有发现开着远程执行的编辑器 |
| `error.channel=project_not_found` | 工程路径对不上。输出里的 `nodes=` 列出了实际节点 |
| `error.channel=no_result_contract` | 编辑器有返回，但没有 `ok=` 行 |
| `error.scan=...` | 脚本被拒绝，没有发送 |
| `error.helper=hash_mismatch` | 编辑器里的 ProbeHelper 和本仓库不一致。重新 `install` 后重启编辑器 |
| `miss.property=A\|B` | 这些反射属性名都不存在 |
| `null` | 属性存在，当前值是空 |
| `error.unreflected=no_property_api` | 对象没有反射属性入口 |
| `error.class=miss:Name` | 类名没解析到 |

`miss.property` 表示名字写错，换候选名再探一次。`null` 才表示值是空。

## 辅助 API

| 调用 | 结果 |
|------|------|
| `GetPieWorld()` | `(world, error)`。`error` 为 `None` 或 `error.world=...` |
| `TryGetProperty(obj, name, ...)` | `(ok, value, error)`。失败时 `error` 为 `miss.property=` 或 `error.get_property=` |
| `FormatProperty(obj, name, ...)` | 失败返回上面的错误原文；值为空返回 `null` |
| `IterActors(world, class_name)` | `(actors, error)`。类名用 `StaticMeshActor` 或 `/Script/Engine.StaticMeshActor` |
| `Subject(obj)` | `subject=<路径>`，没有路径时用类名 |
| `CallReflected(obj, "GetActorLocation")` | 仅当属性接口不够且函数名是常量、且不是写入。默认不要用 |

`IterActors` 的 `class_name` 不能空。不要遍历整个世界。

## 结果契约

脚本自己打印这些行：

```text
ok=true
world=pie
subject=<路径或类名>
count=<数量>
<key>=<value>
```

失败时：

```text
ok=false
error.world=none
```

或

```text
ok=false
world=pie
miss.property=Mana|Shield
```

## 示例

读到一个对象：

```python
import ProbeHelper

world, err = ProbeHelper.GetPieWorld()
if err:
    print("ok=false")
    print(err)
else:
    actors, err = ProbeHelper.IterActors(world, "StaticMeshActor")
    print("ok=true" if not err else "ok=false")
    print("world=pie")
    if err:
        print(err)
    elif not actors:
        print("count=0")
    else:
        print("count=" + str(len(actors)))
        print(ProbeHelper.Subject(actors[0]))
        print("name=" + ProbeHelper.FormatProperty(actors[0], "Name", "ActorLabel"))
```

属性名错误时，`FormatProperty` 直接打出 `miss.property=Mana|Shield`。不要把这次输出写成「法力值为空」。

## 误用对照

| 做法 | 结果 |
|------|------|
| 用 `unreal.EditorLevelLibrary.get_editor_world()` | 读到没在跑的编辑器世界。扫描器也会拒绝 `import unreal` |
| 看到 Python `None` 就说属性不存在 | 和「值为空」混在一起。只认 `miss.property` 与 `null` |
| 把脚本保存成玩法资源或改 C++ | 探针不再是即用即弃 |
| 用 Live Coding、`UnLua.HotReload()` 观察状态 | 改的是正在跑的代码 |
| 发现多个节点时挑第一个 | 可能连错工程。必须让 `--project-root` 命中唯一节点 |

远程通道不可用、人还在编辑器前时，可以把同一段已通过扫描的脚本贴进输出日志的 `py`。世界选择和只读约束不变。

可选 Lua 片段在 `optional/lua/`。只有工程里已经有 `lua_State` 才用。不要为探针接入 UnLua。
