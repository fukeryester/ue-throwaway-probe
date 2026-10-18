import os
import sys
import unittest

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "plugin", "ProbeHelper", "Content", "Python"))

import ProbeHelper
from client.probe_channel import (
    accept_message,
    encode_message,
    format_command_result,
    parse_message,
    select_node,
    wrap_script,
)
from client.readonly_scan import scan_script


class _World(object):
    def __init__(self, pie=None, world_type=None):
        self._pie = pie
        self.world_type = world_type

    def is_play_in_editor(self):
        if self._pie is None:
            raise RuntimeError("no pie flag")
        return self._pie


class _Blind(object):
    pass


class _Actor(object):
    def get_editor_property(self, name):
        if name == "Hp":
            return None
        if name == "Name":
            return "hero"
        raise RuntimeError(name)

    def get_path_name(self):
        return "/Game/Map.Map:PersistentLevel.Hero_0"

    def GetActorLocation(self):
        return "1,2,3"


class _Unreal(object):
    def __init__(self, worlds, actors):
        self.World = type("WorldToken", (), {})
        self.StaticMeshActor = type("StaticMeshActor", (), {})
        self._worlds = worlds
        self._actors = actors
        self.GameplayStatics = self

    def ObjectIterator(self, cls):
        return list(self._worlds)

    def get_all_actors_of_class(self, world, cls):
        return list(self._actors)

    def load_class(self, _outer, name):
        if name.endswith("StaticMeshActor"):
            return self.StaticMeshActor
        return None


SAMPLE = """
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
        print(ProbeHelper.FormatProperty(actors[0], "Name", "Hp"))
"""


class HelperTest(unittest.TestCase):
    def tearDown(self):
        ProbeHelper.set_unreal_for_test(None)

    def test_one_pie_world(self):
        editor = _World(pie=False)
        pie = _World(pie=True)
        ProbeHelper.set_unreal_for_test(_Unreal([editor, pie], []))
        world, err = ProbeHelper.GetPieWorld()
        self.assertIsNone(err)
        self.assertIs(world, pie)

    def test_no_pie_world(self):
        ProbeHelper.set_unreal_for_test(_Unreal([_World(pie=False)], []))
        world, err = ProbeHelper.GetPieWorld()
        self.assertIsNone(world)
        self.assertEqual(err, "error.world=none")

    def test_multiple_pie_worlds(self):
        ProbeHelper.set_unreal_for_test(_Unreal([_World(pie=True), _World(pie=True)], []))
        _world, err = ProbeHelper.GetPieWorld()
        self.assertEqual(err, "error.world=multiple count=2")

    def test_world_type_fallback(self):
        pie = _Blind()
        pie.world_type = "WorldType.PIE"
        editor = _Blind()
        editor.world_type = "WorldType.Editor"
        ProbeHelper.set_unreal_for_test(_Unreal([editor, pie], []))
        world, err = ProbeHelper.GetPieWorld()
        self.assertIsNone(err)
        self.assertIs(world, pie)

    def test_cannot_detect(self):
        ProbeHelper.set_unreal_for_test(_Unreal([_Blind()], []))
        _world, err = ProbeHelper.GetPieWorld()
        self.assertEqual(err, "error.world=cannot_detect_pie")

    def test_property_miss_and_null(self):
        actor = _Actor()
        ok, value, err = ProbeHelper.TryGetProperty(actor, "Missing", "Name")
        self.assertTrue(ok)
        self.assertEqual(value, "hero")
        self.assertIsNone(err)
        text = ProbeHelper.FormatProperty(actor, "Hp")
        self.assertEqual(text, "null")
        miss = ProbeHelper.FormatProperty(actor, "Mana", "Shield")
        self.assertEqual(miss, "miss.property=Mana|Shield")
        _ok, _value, empty = ProbeHelper.TryGetProperty(None, "Name")
        self.assertEqual(empty, "error.get_property=obj_null")

    def test_actors_and_subject(self):
        actor = _Actor()
        pie = _World(pie=True)
        ProbeHelper.set_unreal_for_test(_Unreal([pie], [actor]))
        world, _err = ProbeHelper.GetPieWorld()
        actors, err = ProbeHelper.IterActors(world, "StaticMeshActor")
        self.assertIsNone(err)
        self.assertEqual(actors, [actor])
        self.assertEqual(ProbeHelper.Subject(actor), "subject=/Game/Map.Map:PersistentLevel.Hero_0")
        _actors, miss = ProbeHelper.IterActors(world, "Nope")
        self.assertEqual(miss, "error.class=miss:Nope")

    def test_hash_mismatch(self):
        err = ProbeHelper.prepare(ProbeHelper.file_hash())
        self.assertIsNone(err)
        mismatch = ProbeHelper.prepare("0" * 64)
        self.assertTrue(mismatch.startswith("error.helper=hash_mismatch"))


class ScanTest(unittest.TestCase):
    def test_sample_allowed(self):
        self.assertIsNone(scan_script(SAMPLE))

    def test_rejects_writes_and_imports(self):
        self.assertEqual(scan_script(""), "error.scan=empty")
        self.assertTrue(scan_script("import unreal\n").startswith("error.scan=import:"))
        self.assertEqual(
            scan_script("import ProbeHelper\nactor.set_editor_property('Hp', 1)\n"),
            "error.scan=call:set_editor_property",
        )
        self.assertEqual(
            scan_script("import ProbeHelper\nProbeHelper.CallReflected(actor, 'SetActorLocation', 1)\n"),
            "error.scan=call:SetActorLocation",
        )
        self.assertIsNone(
            scan_script("import ProbeHelper\nProbeHelper.CallReflected(actor, 'GetActorLocation')\n")
        )
        self.assertEqual(scan_script("while True:\n    pass\n"), "error.scan=while")


class ChannelTest(unittest.TestCase):
    def test_message_roundtrip(self):
        raw = encode_message("ping", "local")
        message = parse_message(raw)
        self.assertEqual(message["type"], "ping")
        self.assertTrue(accept_message(message, "other"))
        self.assertFalse(accept_message(message, "local"))

    def test_select_node_requires_a_match(self):
        nodes = {
            "a": {"project_root": r"D:\Game", "project_name": "Game"},
            "b": {"project_root": r"E:\Other", "project_name": "Other"},
        }
        node_id, _data, err = select_node(nodes, r"D:/Game", "")
        self.assertEqual(node_id, "a")
        self.assertIsNone(err)
        _id, _data, missing = select_node(nodes, "", "")
        self.assertEqual(missing, "error.channel=project_required")
        _id, _data, many = select_node(
            {"a": {"project_name": "Game"}, "b": {"project_name": "Game"}},
            "",
            "Game",
        )
        self.assertTrue(many.startswith("error.channel=multiple_nodes"))

    def test_result_contract(self):
        text = format_command_result({
            "success": True,
            "output": [{"type": "Info", "output": "ok=true\nworld=pie\n"}],
        })
        self.assertIn("ok=true", text)
        failed = format_command_result({"success": False, "result": "boom", "output": []})
        self.assertIn("error.channel=no_result_contract", failed)
        self.assertIn("error.channel_detail=boom", failed)

    def test_wrap_indents_user_script(self):
        wrapped = wrap_script("print('ok=true')\n", "abc")
        self.assertIn("ProbeHelper.prepare('abc')", wrapped)
        self.assertIn("    print('ok=true')", wrapped)


if __name__ == "__main__":
    unittest.main()
