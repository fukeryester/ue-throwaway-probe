import ast

_DENIED_CALLS = {
    "HotReload",
    "__import__",
    "breakpoint",
    "compile",
    "delattr",
    "destroy_actor",
    "destroy_component",
    "eval",
    "exec",
    "execute_console_command",
    "getattr",
    "hot_reload",
    "input",
    "k2_destroy_actor",
    "open",
    "set_actor_hidden_in_game",
    "set_actor_location",
    "set_actor_rotation",
    "set_actor_scale3d",
    "set_actor_transform",
    "set_editor_properties",
    "set_editor_property",
    "setattr",
    "spawn_actor_from_class",
    "spawn_actor_from_object",
}

_ALLOWED_IMPORTS = {"ProbeHelper"}


def scan_script(source):
    if source is None or not str(source).strip():
        return "error.scan=empty"
    try:
        tree = ast.parse(source)
    except SyntaxError as ex:
        return "error.scan=syntax:%s" % str(ex).replace("\n", " ")
    visitor = _Scanner()
    visitor.visit(tree)
    return visitor.error


class _Scanner(ast.NodeVisitor):
    def __init__(self):
        self.error = None

    def visit(self, node):
        if self.error is not None:
            return
        super(_Scanner, self).visit(node)

    def visit_Import(self, node):
        for alias in node.names:
            root = alias.name.split(".")[0]
            if root not in _ALLOWED_IMPORTS:
                self.error = "error.scan=import:%s" % alias.name
                return

    def visit_ImportFrom(self, node):
        module = node.module or ""
        root = module.split(".")[0]
        if root not in _ALLOWED_IMPORTS:
            self.error = "error.scan=import:%s" % (module or "?")

    def visit_Call(self, node):
        name = _call_name(node.func)
        if name in _DENIED_CALLS or _looks_like_write(name):
            self.error = "error.scan=call:%s" % name
            return
        if name == "CallReflected":
            reflected = _literal_arg(node, 1)
            if not isinstance(reflected, str):
                self.error = "error.scan=call_reflected_dynamic"
                return
            if reflected in _DENIED_CALLS or _looks_like_write(reflected):
                self.error = "error.scan=call:%s" % reflected
                return
        self.generic_visit(node)

    def visit_Assign(self, node):
        if _writes_attribute(node.targets):
            self.error = "error.scan=assign_attribute"
            return
        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        if _writes_attribute([node.target]):
            self.error = "error.scan=assign_attribute"
            return
        self.generic_visit(node)

    def visit_AugAssign(self, node):
        if _writes_attribute([node.target]):
            self.error = "error.scan=assign_attribute"
            return
        self.generic_visit(node)

    def visit_Delete(self, node):
        self.error = "error.scan=delete"

    def visit_While(self, node):
        self.error = "error.scan=while"

    def visit_With(self, node):
        self.error = "error.scan=with"

    def visit_AsyncFunctionDef(self, node):
        self.error = "error.scan=async"

    def visit_AsyncFor(self, node):
        self.error = "error.scan=async"

    def visit_Await(self, node):
        self.error = "error.scan=async"


def _looks_like_write(name):
    lower = name.lower()
    if any(token in lower for token in ("destroy", "spawn", "remove", "delete", "kill")):
        return True
    return lower.startswith(("set", "add", "apply", "teleport"))


def _literal_arg(node, index):
    if index >= len(node.args):
        return None
    arg = node.args[index]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    return None


def _call_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _writes_attribute(targets):
    for target in targets:
        if isinstance(target, (ast.Attribute, ast.Subscript)):
            return True
        if isinstance(target, (ast.Tuple, ast.List)):
            if _writes_attribute(target.elts):
                return True
    return False
