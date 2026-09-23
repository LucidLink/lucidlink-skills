#!/usr/bin/env python3
"""
render.py: turn snapshot.json into a self-contained index.html.

The template carries a <script id="ll-snapshot" type="application/json"> block.
This script replaces its contents with the snapshot, so the page works when
opened straight from a mounted filespace (file://) with no server and no fetch.

Usage:
    python3 scripts/render.py --snapshot out/snapshot.json --out out/index.html
    python3 scripts/render.py --snapshot out/snapshot.json --publish "/Volumes/<ws>/<fs>/Dashboards/<name>"

--publish copies index.html and snapshot.json into a directory (typically inside
the filespace) and, unless --no-history is given, appends a dated copy of the
snapshot under <publish>/history/ so trends can be built later.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_TEMPLATE = HERE.parent / "templates" / "dashboard.html"
REQUIRED = ["schema", "generated_at", "stats", "activity", "folders", "cold", "extensions", "recent", "notes"]
DEFAULTS = {
    "flags": [],
    "largest": [],
    "locks": None,
    "budget": "unknown",
    "window_days": 7,
    "title": "LucidLink filespace",
    "source": {"mode": "unknown"},
}


def validate(snap) -> list[str]:
    """Required keys AND the shapes the template indexes into; a wrong type used to
    render fine here and then throw in the browser, leaving an empty page."""
    if not isinstance(snap, dict):
        return ["snapshot must be a JSON object"]
    problems = []
    for k in REQUIRED:
        if k not in snap:
            problems.append(f"missing top-level key: {k}")
    for k, v in DEFAULTS.items():
        snap.setdefault(k, v)
    for k in ("folders", "extensions", "recent", "notes", "flags", "largest"):
        if k in snap and not isinstance(snap[k], list):
            problems.append(f"{k} must be a list")
    if not isinstance(snap.get("stats"), dict):
        problems.append("stats must be an object")
    cold = snap.get("cold")
    if not isinstance(cold, dict) or not isinstance(cold.get("buckets", []), list) or not isinstance(cold.get("candidates", []), list):
        problems.append("cold must be an object with list fields buckets and candidates")
    act = snap.get("activity")
    if not isinstance(act, dict):
        problems.append("activity must be an object")
        return problems
    for k in ("events", "by_day", "by_action", "by_actor"):
        if k not in act:
            problems.append(f"missing activity.{k}")
    for k in ("by_day", "by_actor"):
        if k in act and not isinstance(act[k], list):
            problems.append(f"activity.{k} must be a list")
    if "by_action" in act and not isinstance(act["by_action"], dict):
        problems.append("activity.by_action must be an object")
    return problems


def render(snap: dict, template: Path) -> str:
    html = template.read_text(encoding="utf-8")
    # Inside <script type="application/json"> the HTML parser still scans for "</script"
    # and "<!--"; escaping every <, > and & means no path or user name can end the block.
    payload = (json.dumps(snap, ensure_ascii=False)
               .replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e"))
    pattern = re.compile(r'(<script id="ll-snapshot" type="application/json">)(.*?)(</script>)', re.S)
    if not pattern.search(html):
        sys.exit("template has no <script id=\"ll-snapshot\"> block")
    return pattern.sub(lambda m: m.group(1) + payload + m.group(3), html, count=1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--template", default=str(DEFAULT_TEMPLATE))
    ap.add_argument("--out", help="output html path (default: <snapshot dir>/index.html)")
    ap.add_argument("--publish", help="directory to copy index.html and snapshot.json into, for example a folder inside the filespace")
    ap.add_argument("--no-history", action="store_true")
    args = ap.parse_args()

    snap_path = Path(args.snapshot)
    if not snap_path.is_file():
        sys.exit(f"snapshot not found: {snap_path}")
    try:
        snap = json.loads(snap_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.exit(f"{snap_path} is not valid JSON: {e}")
    if not Path(args.template).is_file():
        sys.exit(f"template not found: {args.template}")
    problems = validate(snap)
    if problems:
        sys.exit("snapshot.json is not renderable:\n  " + "\n  ".join(problems) + "\nSee references/snapshot-schema.md")

    out = Path(args.out) if args.out else snap_path.parent / "index.html"
    out.write_text(render(snap, Path(args.template)), encoding="utf-8")
    print(f"wrote {out}")

    if args.publish:
        pub = Path(args.publish)
        pub.mkdir(parents=True, exist_ok=True)
        shutil.copy2(out, pub / "index.html")
        shutil.copy2(snap_path, pub / "snapshot.json")
        if not args.no_history:
            hist = pub / "history"
            hist.mkdir(exist_ok=True)
            stamp = snap.get("generated_at", dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")).replace(":", ".")
            shutil.copy2(snap_path, hist / f"snapshot-{stamp}.json")
        print(f"published to {pub}")


if __name__ == "__main__":
    main()
