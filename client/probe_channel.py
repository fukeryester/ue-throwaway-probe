import hashlib
import json
import os
import socket
import textwrap
import time
import uuid

PROTOCOL_VERSION = 1
PROTOCOL_MAGIC = "ue_py"
TYPE_PING = "ping"
TYPE_PONG = "pong"
TYPE_OPEN_CONNECTION = "open_connection"
TYPE_CLOSE_CONNECTION = "close_connection"
TYPE_COMMAND = "command"
TYPE_COMMAND_RESULT = "command_result"
MODE_EXEC_FILE = "ExecuteFile"

MULTICAST_GROUP = ("239.0.0.1", 6766)
MULTICAST_BIND = "127.0.0.1"
MULTICAST_TTL = 0
MAX_RESULT_BYTES = 8 * 1024 * 1024


def helper_source_path():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "plugin", "ProbeHelper", "Content", "Python", "ProbeHelper.py"))


def helper_hash(path=None):
    target = path or helper_source_path()
    digest = hashlib.sha256()
    with open(target, "rb") as handle:
        digest.update(handle.read())
    return digest.hexdigest()


def wrap_script(source, expected_hash):
    indented = textwrap.indent(source.strip() + "\n", "    ")
    header = (
        "import ProbeHelper\n"
        "_probe_err = ProbeHelper.prepare(%s)\n"
        "if _probe_err:\n"
        "    print('ok=false')\n"
        "    print(_probe_err)\n"
        "else:\n"
    ) % repr(expected_hash)
    return header + indented


def encode_message(type_, source, dest=None, data=None):
    if not type_ or not source:
        raise ValueError("type and source are required")
    payload = {
        "version": PROTOCOL_VERSION,
        "magic": PROTOCOL_MAGIC,
        "type": type_,
        "source": source,
    }
    if dest:
        payload["dest"] = dest
    if data:
        payload["data"] = data
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def parse_message(raw):
    if isinstance(raw, bytes):
        text = raw.decode("utf-8")
    else:
        text = raw
    decoder = json.JSONDecoder()
    obj, _end = decoder.raw_decode(text.lstrip())
    if obj.get("version") != PROTOCOL_VERSION or obj.get("magic") != PROTOCOL_MAGIC:
        raise ValueError("protocol header mismatch")
    if not obj.get("type") or not obj.get("source"):
        raise ValueError("message missing type or source")
    return obj


def accept_message(message, node_id):
    if message.get("source") == node_id:
        return False
    dest = message.get("dest")
    return not dest or dest == node_id


def select_node(nodes, project_root, project_name):
    if not project_root and not project_name:
        return None, None, "error.channel=project_required"
    matches = []
    for node_id, data in nodes.items():
        data = data or {}
        root_ok = True
        name_ok = True
        if project_root:
            root_ok = _same_path(_field(data, "project_root"), project_root)
        if project_name:
            name_ok = _field(data, "project_name") == project_name
        if root_ok and name_ok:
            matches.append((node_id, data))
    if len(matches) == 1:
        return matches[0][0], matches[0][1], None
    summary = _node_summary(nodes)
    if len(matches) == 0:
        return None, None, "error.channel=project_not_found " + summary
    return None, None, "error.channel=multiple_nodes " + summary


def format_command_result(data):
    if not isinstance(data, dict):
        return "ok=false\nerror.channel=bad_result"
    lines = []
    output = data.get("output")
    if isinstance(output, list):
        for entry in output:
            if isinstance(entry, dict):
                text = entry.get("output", entry.get("text", ""))
            else:
                text = str(entry)
            if text:
                lines.append(str(text).rstrip("\r\n"))
    elif isinstance(output, str) and output:
        lines.append(output.rstrip("\r\n"))
    body = "\n".join(lines).strip("\n")
    result = data.get("result")
    if not body and result not in (None, "", "None"):
        body = str(result).strip("\n")
    if "ok=" not in body:
        detail = ""
        if data.get("success") is False and result not in (None, "", "None"):
            detail = "\nerror.channel_detail=" + str(result).replace("\n", " ")
        body = (body + "\nok=false\nerror.channel=no_result_contract" + detail).strip("\n")
    return body


def execute(source, project_root, project_name, timeout):
    wrapped = wrap_script(source, helper_hash())
    node_id = str(uuid.uuid4())
    broadcast = _open_broadcast()
    try:
        nodes = _discover(broadcast, node_id, min(timeout, 5.0))
        if not nodes:
            return "ok=false\nerror.channel=no_node"
        remote_id, _data, error = select_node(nodes, project_root, project_name)
        if error:
            return "ok=false\n" + error
        result = _run_command(broadcast, node_id, remote_id, wrapped, timeout)
    finally:
        broadcast.close()
    return format_command_result(result)


def _open_broadcast():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        if hasattr(socket, "SO_REUSEADDR"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((MULTICAST_BIND, MULTICAST_GROUP[1]))
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, MULTICAST_TTL)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(MULTICAST_BIND))
        membership = socket.inet_aton(MULTICAST_GROUP[0]) + socket.inet_aton(MULTICAST_BIND)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
    except OSError:
        sock.close()
        raise
    sock.settimeout(0.2)
    return sock


def _discover(broadcast, node_id, timeout):
    nodes = {}
    deadline = time.time() + timeout
    next_ping = 0.0
    while time.time() < deadline:
        now = time.time()
        if now >= next_ping:
            broadcast.sendto(encode_message(TYPE_PING, node_id), MULTICAST_GROUP)
            next_ping = now + 1.0
        try:
            data, _addr = broadcast.recvfrom(65535)
        except socket.timeout:
            continue
        try:
            message = parse_message(data)
        except (ValueError, UnicodeError, json.JSONDecodeError):
            continue
        if not accept_message(message, node_id):
            continue
        if message.get("type") == TYPE_PONG:
            nodes[message["source"]] = message.get("data") or {}
    return nodes


def _run_command(broadcast, node_id, remote_id, command, timeout):
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(5.0)
        host, port = listener.getsockname()
        open_data = {"command_ip": host, "command_port": port}
        channel = None
        deadline = time.time() + min(timeout, 30.0)
        while channel is None and time.time() < deadline:
            broadcast.sendto(
                encode_message(TYPE_OPEN_CONNECTION, node_id, remote_id, open_data),
                MULTICAST_GROUP,
            )
            try:
                channel, _addr = listener.accept()
            except socket.timeout:
                channel = None
        if channel is None:
            return {"success": False, "result": "editor did not connect", "output": []}
        channel.settimeout(timeout)
        try:
            payload = encode_message(TYPE_COMMAND, node_id, remote_id, {
                "command": command,
                "unattended": True,
                "exec_mode": MODE_EXEC_FILE,
            })
            channel.sendall(payload)
            raw = _recv_json(channel, timeout)
            message = parse_message(raw)
            if not accept_message(message, node_id) or message.get("type") != TYPE_COMMAND_RESULT:
                return {"success": False, "result": "unexpected reply", "output": []}
            return message.get("data") or {}
        finally:
            channel.close()
            broadcast.sendto(encode_message(TYPE_CLOSE_CONNECTION, node_id, remote_id), MULTICAST_GROUP)
    finally:
        listener.close()


def _recv_json(channel, timeout):
    deadline = time.time() + timeout
    chunks = []
    size = 0
    while time.time() < deadline:
        try:
            piece = channel.recv(65535)
        except socket.timeout:
            break
        if not piece:
            break
        chunks.append(piece)
        size += len(piece)
        if size > MAX_RESULT_BYTES:
            raise RuntimeError("result exceeded 8MB")
        try:
            parse_message(b"".join(chunks))
            return b"".join(chunks)
        except (ValueError, UnicodeError, json.JSONDecodeError):
            continue
    raise RuntimeError("timed out waiting for command_result")


def _field(data, key):
    for name, value in data.items():
        if str(name).lower() == key.lower() and value:
            return str(value)
    return ""


def _same_path(left, right):
    if not left or not right:
        return False
    return os.path.normcase(os.path.normpath(left)) == os.path.normcase(os.path.normpath(right))


def _node_summary(nodes):
    parts = []
    for node_id, data in nodes.items():
        data = data or {}
        parts.append("%s root=%s name=%s" % (node_id, _field(data, "project_root") or "?", _field(data, "project_name") or "?"))
    return "nodes=" + ("; ".join(parts) if parts else "none")
