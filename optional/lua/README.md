# 可选：已有 Lua 虚拟机时的第二通道

玩法状态已经住在 Lua 表里时，把 `probe_eval.lua` 交给现有的 `lua_State` 执行一次，之后用 `Probe.Eval(code)` 跑当次字符串。

不要为了探针去接入 UnLua。不要调用 `UnLua.HotReload()`。`Probe.TraceCalls` 会在 `pcall` 之后卸掉 `debug.sethook`；不要在别的路径再设 hook。
