-- Drop-in chunk for a project that already hosts a lua_State.
-- Do not add UnLua just to get this file. Do not call UnLua.HotReload.

local Probe = {}

local function one_line(text)
    text = tostring(text or "")
    text = string.gsub(text, "[\r\n]", " ")
    return text
end

function Probe.Eval(code)
    if type(code) ~= "string" or code == "" then
        return "ok=false\nerror.lua=empty"
    end
    local chunk, load_err = load(code, "probe", "t")
    if not chunk then
        return "ok=false\nerror.lua=" .. one_line(load_err)
    end
    local ok, result = pcall(chunk)
    if not ok then
        return "ok=false\nerror.lua=" .. one_line(result)
    end
    if result == nil then
        return "ok=true"
    end
    return tostring(result)
end

-- Call hook must be removed on every exit. Lua has no finally, so clear it after pcall.
function Probe.TraceCalls(code, on_call)
    if type(on_call) ~= "function" then
        return "ok=false\nerror.lua=hook_missing"
    end
    debug.sethook(on_call, "c")
    local text = Probe.Eval(code)
    debug.sethook()
    return text
end

return Probe
