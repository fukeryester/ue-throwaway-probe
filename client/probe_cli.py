import argparse
import os
import sys

_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from client.probe_channel import execute
from client.readonly_scan import scan_script


def main(argv=None):
    parser = argparse.ArgumentParser(description="Send one throwaway read-only probe to a running Unreal editor.")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run")
    run.add_argument("--project-root", default="", help="Editor project directory. Must match the discovered node.")
    run.add_argument("--project-name", default="", help="Optional project name that must also match.")
    run.add_argument("--timeout", type=float, default=20.0)
    run.add_argument("--code", default="", help="Script text. Prefer --script for anything longer.")
    run.add_argument("--script", default="", help="Script file path, or - to read stdin.")
    run.set_defaults(func=_cmd_run)

    install = sub.add_parser("install")
    install.add_argument("--project-root", required=True, help="Unreal project directory that contains the .uproject.")
    install.set_defaults(func=_cmd_install)

    args = parser.parse_args(argv)
    return args.func(args)


def _cmd_run(args):
    source = _read_source(args)
    scanned = scan_script(source)
    if scanned:
        sys.stdout.write("ok=false\n%s\n" % scanned)
        return 1
    try:
        text = execute(source, args.project_root, args.project_name, args.timeout)
    except Exception as ex:
        sys.stdout.write("ok=false\nerror.channel=%s\n" % str(ex).replace("\n", " "))
        return 1
    sys.stdout.write(text.rstrip("\n") + "\n")
    if "ok=true" in text.splitlines():
        return 0
    return 2


def _cmd_install(args):
    project = os.path.abspath(args.project_root)
    uprojects = [name for name in os.listdir(project) if name.endswith(".uproject")]
    if not uprojects:
        sys.stderr.write("no .uproject in %s\n" % project)
        return 1
    import shutil
    source = os.path.join(_ROOT, "plugin", "ProbeHelper")
    target = os.path.join(project, "Plugins", "ProbeHelper")
    if os.path.isdir(target):
        shutil.rmtree(target)
    shutil.copytree(source, target)
    _merge_ini(
        os.path.join(project, "Config", "DefaultEngine.ini"),
        os.path.join(_ROOT, "install", "DefaultEngine.ini.snippet"),
    )
    sys.stdout.write("installed=%s\n" % target)
    sys.stdout.write("restart the editor after enabling PythonScriptPlugin\n")
    return 0


def _read_source(args):
    if args.code and args.script:
        raise SystemExit("pass only one of --code and --script")
    if args.code:
        return args.code
    if args.script == "-":
        return sys.stdin.read()
    if args.script:
        with open(args.script, "r", encoding="utf-8") as handle:
            return handle.read()
    raise SystemExit("pass --code or --script")


def _merge_ini(dest, snippet_path):
    with open(snippet_path, "r", encoding="utf-8") as handle:
        snippet = handle.read().strip() + "\n"
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    existing = ""
    if os.path.isfile(dest):
        with open(dest, "r", encoding="utf-8") as handle:
            existing = handle.read()
    section = "[/Script/PythonScriptPlugin.PythonScriptPluginSettings]"
    if section in existing and "bRemoteExecution=True" in existing:
        return
    with open(dest, "a", encoding="utf-8") as handle:
        if existing and not existing.endswith("\n"):
            handle.write("\n")
        handle.write("\n")
        handle.write(snippet)


if __name__ == "__main__":
    sys.exit(main())
