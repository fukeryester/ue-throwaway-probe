import hashlib
import os
import sys

_unreal_override = None
_loaded_hash = None


def set_unreal_for_test(module):
    global _unreal_override
    _unreal_override = module


def _unreal():
    if _unreal_override is not None:
        return _unreal_override
    import unreal
    return unreal


def file_hash():
    path = os.path.abspath(__file__)
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        digest.update(handle.read())
    return digest.hexdigest()


def prepare(expected_hash):
    global _loaded_hash
    current = file_hash()
    if _loaded_hash is not None and _loaded_hash != current:
        import importlib
        importlib.reload(sys.modules[__name__])
        return sys.modules[__name__].prepare(expected_hash)
    _loaded_hash = current
    if expected_hash and expected_hash != current:
        return "error.helper=hash_mismatch editor=%s client=%s" % (current[:12], expected_hash[:12])
    return None


def GetPieWorld():
    unreal = _unreal()
    iterator = getattr(unreal, "ObjectIterator", None)
    world_type = getattr(unreal, "World", None)
    if iterator is None or world_type is None:
        return None, "error.world=object_iterator_missing"
    try:
        worlds = list(iterator(world_type))
    except Exception as ex:
        return None, "error.world=iterate_failed:%s" % _one_line(ex)

    pie = []
    for world in worlds:
        flag = _is_pie(world)
        if flag is None:
            return None, "error.world=cannot_detect_pie"
        if flag:
            pie.append(world)
    if len(pie) == 0:
        return None, "error.world=none"
    if len(pie) != 1:
        return None, "error.world=multiple count=%d" % len(pie)
    return pie[0], None


def TryGetProperty(obj, *names):
    if obj is None:
        return False, None, "error.get_property=obj_null"
    cleaned = [name for name in names if name]
    if not cleaned:
        return False, None, "error.get_property=names_empty"
    getter = getattr(obj, "get_editor_property", None)
    if not callable(getter):
        return False, None, "error.unreflected=no_property_api"
    missed = []
    for name in cleaned:
        try:
            value = getter(name)
        except Exception:
            missed.append(name)
            continue
        return True, value, None
    return False, None, "miss.property=" + "|".join(missed)


def FormatProperty(obj, *names):
    ok, value, error = TryGetProperty(obj, *names)
    if not ok:
        return error
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value)
    return text.replace("\r", " ").replace("\n", "\\n")


def IterActors(world, class_name):
    if world is None:
        return None, "error.actors=world_null"
    if not class_name:
        return None, "error.class=empty"
    unreal = _unreal()
    actor_class = _resolve_class(unreal, class_name)
    if actor_class is None:
        return None, "error.class=miss:%s" % class_name
    statics = getattr(unreal, "GameplayStatics", None)
    getter = getattr(statics, "get_all_actors_of_class", None) if statics is not None else None
    if not callable(getter):
        return None, "error.actors=api_missing"
    try:
        actors = list(getter(world, actor_class))
    except Exception as ex:
        return None, "error.actors=iterate_failed:%s" % _one_line(ex)
    return actors, None


def CallReflected(obj, func_name, *args):
    if obj is None:
        return False, None, "error.call=obj_null"
    if not func_name:
        return False, None, "error.call=name_empty"
    func = getattr(obj, func_name, None)
    if not callable(func):
        return False, None, "miss.function=" + func_name
    try:
        return True, func(*args), None
    except Exception as ex:
        return False, None, "error.call=invoke_threw:%s:%s" % (func_name, _one_line(ex))


def Subject(obj):
    if obj is None:
        return "subject=null"
    path = getattr(obj, "get_path_name", None)
    if callable(path):
        try:
            return "subject=" + str(path())
        except Exception:
            pass
    return "subject=" + obj.__class__.__name__


def _is_pie(world):
    detector = getattr(world, "is_play_in_editor", None)
    if callable(detector):
        try:
            return bool(detector())
        except Exception:
            return None
    world_type = getattr(world, "world_type", None)
    if world_type is None:
        return None
    name = str(world_type)
    return name == "PIE" or name.endswith(".PIE") or name.endswith(":PIE") or name.endswith("::PIE")


def _resolve_class(unreal, class_name):
    direct = getattr(unreal, class_name, None)
    if direct is not None and direct is not getattr(unreal, "World", None):
        return direct
    load_class = getattr(unreal, "load_class", None)
    if not callable(load_class):
        return None
    candidates = [class_name] if class_name.startswith("/") else [
        "/Script/Engine." + class_name,
        "/Script/CoreUObject." + class_name,
    ]
    for candidate in candidates:
        try:
            found = load_class(None, candidate)
        except Exception:
            found = None
        if found is not None:
            return found
    return None


def _one_line(value):
    return str(value).replace("\r", " ").replace("\n", " ")
