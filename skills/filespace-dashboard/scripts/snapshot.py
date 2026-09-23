#!/usr/bin/env python3
"""
snapshot.py: collect a dashboard snapshot from a LucidLink filespace.

Reads the filespace tree and the audit trail, aggregates them into one
snapshot.json that templates/dashboard.html renders. Standard library only
for the "mount" source. The "sdk" source needs the lucidlink package.

Usage:
    python3 scripts/snapshot.py --config config.yaml
    python3 scripts/snapshot.py --root /Volumes/<ws>/<filespace> --budget lite
    python3 scripts/snapshot.py --config config.yaml --stats '{"storage_bytes": 33081017209}'

Exit code 0 on success. Notes about sampling, clamped budgets and missing
data are written into snapshot["notes"] rather than failing the run.
"""
from __future__ import annotations

import argparse
import bisect
import collections
import datetime as dt
import json
import os
import re
import sys
import time
from pathlib import Path

SCHEMA = "lucidlink-filespace-dashboard/1"

# Walk budgets per budget mode: (max_entries, max_seconds, audit_window_days_default)
BUDGETS = {
    "lite": {"max_entries": 3000, "max_seconds": 30, "window_days": 7, "hours": False, "flags": False},
    "standard": {"max_entries": 40000, "max_seconds": 120, "window_days": 7, "hours": True, "flags": True},
    "deep": {"max_entries": 400000, "max_seconds": 900, "window_days": 30, "hours": True, "flags": True},
}

WRITE_ACTIONS = {"FileWritten", "FileCreate", "DirectoryCreate", "Move", "SymlinkCreate",
                 "ExtendedAttributeSet", "ExtendedAttributeDelete", "Pin", "Unpin"}
DELETE_ACTIONS = {"FileDelete", "DirectoryDelete"}
READ_ACTIONS = {"FileRead", "PreHydrate"}
TICKER_ACTIONS = {"FileWritten", "FileCreate", "FileDelete", "Move", "DirectoryCreate", "DirectoryDelete"}

# A session's open audit log carries a .log.active suffix until it rotates; it can hold
# days of the newest events, so it is read exactly like a closed .log file.
AUDIT_SUFFIXES = (".log", ".log.active")

DEFAULT_EXCLUDES = [".lucid_audit", ".DS_Store", ".git", ".venv", "node_modules", "__pycache__", ".Trash", ".Spotlight-V100", ".fseventsd"]

AGE_BUCKETS = [
    ("last 7 days", 7),
    ("7 to 30 days", 30),
    ("30 to 90 days", 90),
    ("90 days to 1 year", 365),
    ("1 to 2 years", 730),
    ("over 2 years", None),
]


# --------------------------------------------------------------------------- config

def load_config(path: str | None) -> dict:
    if not path:
        return {}
    p = Path(path)
    if not p.is_file():
        sys.exit(f"config not found: {path}")
    text = p.read_text()
    try:
        if p.suffix in (".yaml", ".yml"):
            try:
                import yaml  # type: ignore
            except ImportError:
                sys.exit("config is YAML but PyYAML is not installed. Run: pip install pyyaml, or use a .json config.")
            data = yaml.safe_load(text) or {}
        else:
            data = json.loads(text)
    except (ValueError, Exception) as e:  # yaml.YAMLError is not importable without PyYAML
        sys.exit(f"{path} could not be parsed: {e}")
    if not isinstance(data, dict):
        sys.exit(f"{path}: the top level must be a mapping of settings, not a {type(data).__name__}")
    return data


def deep_get(d: dict, *keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


# --------------------------------------------------------------------------- sources

class MountSource:
    """Filespace mounted as a local path. Metadata reads only, no content reads."""

    def __init__(self, root: str):
        self.root = Path(root)
        if not self.root.is_dir():
            sys.exit(f"root is not a directory: {root}")

    def walk(self, excludes: list[str], max_entries: int, max_seconds: int):
        """Yield (relpath, is_dir, size, mtime_epoch). Stops at budget and reports via .clamped."""
        self.clamped = None
        started = time.time()
        seen = 0
        # Breadth-first, so a walk that hits its budget has visited every top-level folder
        # shallowly rather than one folder to the bottom and the rest not at all.
        queue = collections.deque([self.root])
        while queue:
            d = queue.popleft()
            try:
                with os.scandir(d) as it:
                    for e in it:
                        if e.name in excludes:
                            continue
                        seen += 1
                        if seen > max_entries:
                            self.clamped = f"walk stopped at {max_entries} entries (budget)"
                            return
                        if time.time() - started > max_seconds:
                            self.clamped = f"walk stopped after {max_seconds}s (budget)"
                            return
                        try:
                            st = e.stat(follow_symlinks=False)
                        except OSError:
                            continue
                        rel = "/" + str(Path(e.path).relative_to(self.root)).replace(os.sep, "/")
                        if e.is_dir(follow_symlinks=False):
                            yield rel, True, 0, st.st_mtime
                            queue.append(Path(e.path))
                        else:
                            yield rel, False, st.st_size, st.st_mtime
            except (PermissionError, FileNotFoundError):
                continue

    def audit_files(self):
        base = self.root / ".lucid_audit"
        if not base.is_dir():
            return []
        return sorted(str(p) for p in base.rglob("*.log*") if p.name.endswith(AUDIT_SUFFIXES))

    def open_audit(self, path: str):
        return open(path, "r", encoding="utf-8", errors="replace")

    def stats(self) -> dict | None:
        return None  # stored size is not visible through a mount


class SdkSource:
    """Filespace reached through the lucidlink Python SDK (0.12 to 0.15 signatures).

    Written against the SDK's public signatures. Exercise it against your own
    filespace before relying on it; see README "Sources".
    """

    def __init__(self, filespace: str, token: str):
        try:
            import lucidlink  # type: ignore
        except ImportError:
            sys.exit("source=sdk needs the lucidlink package: pip install lucidlink")
        self.ll = lucidlink
        self.client = lucidlink.Client()
        self.client.login(lucidlink.ServiceAccountCredentials(token=token))
        fs_key, _, ws_key = filespace.partition(".")
        # get_workspace() only takes an id. Service-account tokens are workspace-scoped,
        # so list_workspaces() returns the one workspace the token can see; match the
        # configured <workspace> part by name or id and fall back to that single entry.
        infos = self.client.list_workspaces()
        matches = [w for w in infos if ws_key and ws_key in (w.id, getattr(w, "name", None))]
        if ws_key and not matches and len(infos) != 1:
            sys.exit(f"workspace {ws_key!r} is not visible to this token; available: "
                     + ", ".join(f"{w.name} ({w.id})" for w in infos))
        info = matches[0] if matches else infos[0]
        self.workspace = self.client.get_workspace(info.id)
        # Names can be renamed under a scheduled script; link by id (name= is deprecated).
        fs_infos = self.workspace.list_filespaces()
        fs_matches = [f for f in fs_infos if fs_key in (f.id, f.name)]
        if not fs_matches:
            sys.exit(f"filespace {fs_key!r} not found in workspace {info.name!r}; available: "
                     + ", ".join(f.name for f in fs_infos))
        self.fs_obj = self.workspace.link_filespace(id=fs_matches[0].id)
        self.fs = self.fs_obj.fs
        self.clamped = None

    def walk(self, excludes, max_entries, max_seconds):
        started = time.time()
        seen = 0
        queue = collections.deque(["/"])  # breadth-first, see MountSource.walk
        while queue:
            d = queue.popleft()
            try:
                entries = self.fs.read_dir(d)
            except Exception:
                continue
            for e in entries:
                if e.name in excludes:
                    continue
                seen += 1
                if seen > max_entries:
                    self.clamped = f"walk stopped at {max_entries} entries (budget)"
                    return
                if time.time() - started > max_seconds:
                    self.clamped = f"walk stopped after {max_seconds}s (budget)"
                    return
                rel = (d.rstrip("/") + "/" + e.name)
                mtime = e.mtime / 1e9 if e.mtime > 1e12 else e.mtime
                if e.is_dir():
                    yield rel, True, 0, mtime
                    queue.append(rel)
                else:
                    yield rel, False, e.size, mtime

    def audit_files(self):
        out = []
        stack = ["/.lucid_audit"]
        while stack:
            d = stack.pop()
            try:
                entries = self.fs.read_dir(d)
            except Exception:
                continue
            for e in entries:
                p = d.rstrip("/") + "/" + e.name
                if e.is_dir():
                    stack.append(p)
                elif e.name.endswith(AUDIT_SUFFIXES):
                    out.append(p)
        return sorted(out)

    def open_audit(self, path):
        import io
        data = self.fs.read_file(path)
        if isinstance(data, bytes):
            data = data.decode("utf-8", errors="replace")
        return io.StringIO(data)

    def stats(self):
        try:
            s = self.fs.get_statistics()
            # file_count / directory_count are not reliably populated (they read 0 on
            # filespaces with tens of thousands of entries), so the walk keeps those;
            # only the hub-side byte and external-file figures come from here.
            return {
                "data_bytes": getattr(s, "data_size", None),
                "storage_bytes": getattr(s, "storage_size", None),
                "external_files": getattr(s, "external_files_count", None),
                "external_bytes": getattr(s, "external_files_size", None),
            }
        except Exception:
            return None


# --------------------------------------------------------------------------- audit parsing

AUDIT_NAME_RE = re.compile(r"(\d{4}-\d{2}-\d{2})T(\d{2})\.(\d{2})\.(\d{2})Z\.log(?:\.active)?$")


def audit_file_start(path: str) -> float | None:
    m = AUDIT_NAME_RE.search(path)
    if not m:
        return None
    d, hh, mm, ss = m.groups()
    t = dt.datetime.fromisoformat(f"{d}T{hh}:{mm}:{ss}+00:00")
    return t.timestamp()


def classify_actor(name: str, service_patterns: list[str]) -> str:
    for pat in service_patterns:
        if re.search(pat, name):
            return "service"
    return "human"


def top_folder(path: str, depth: int) -> str:
    parts = [p for p in path.split("/") if p]
    if not parts:
        return "/"
    return "/" + "/".join(parts[:depth])


def folder_of(path: str, depth: int) -> str:
    """Group an entry by its PARENT directory, so a depth of 2 yields /show/episode rows
    and never one row per file; entries directly under the root land in "/"."""
    parent = path.rsplit("/", 1)[0]
    return top_folder(parent, depth) if parent else "/"


def under(path: str, prefix: str | None) -> bool:
    return bool(prefix) and (path == prefix or path.startswith(prefix.rstrip("/") + "/"))


def iso(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- collect

def collect(cfg: dict, args) -> dict:
    budget = args.budget or cfg.get("budget") or "deep"
    if budget not in BUDGETS:
        sys.exit(f"unknown budget {budget}; choose lite, standard or deep")
    b = BUDGETS[budget]
    window_days = int(args.window or cfg.get("window_days") or b["window_days"])
    excludes = list(DEFAULT_EXCLUDES) + list(deep_get(cfg, "folders", "exclude", default=[]) or [])
    folder_depth = int(deep_get(cfg, "folders", "depth", default=1) or 1)
    service_patterns = deep_get(cfg, "actors", "service_patterns", default=None) or [r"^(?!.*@)"]
    actor_labels = deep_get(cfg, "actors", "labels", default={}) or {}
    cold_min_bytes = int(deep_get(cfg, "cold", "candidate_min_bytes", default=10 * 1024 * 1024))
    cold_min_age_days = int(deep_get(cfg, "cold", "candidate_min_age_days", default=180))

    source_kind = args.source or deep_get(cfg, "filespace", "source", default="mount")
    fs_name = deep_get(cfg, "filespace", "name", default=None)
    notes: list[str] = []

    # The dashboard's own folder, as a path inside the filespace, kept out of every count.
    # output.filespace_path names it directly (any source); the mount source can also derive
    # it from output.publish_to.
    skip_prefix: str | None = None
    fs_path = deep_get(cfg, "output", "filespace_path")
    if fs_path:
        skip_prefix = "/" + str(fs_path).strip("/")
        notes.append(f"Excluded {skip_prefix} (the dashboard's own folder) from counts.")

    if source_kind == "mount":
        root = args.root or deep_get(cfg, "filespace", "root")
        if not root:
            sys.exit("mount source needs --root or filespace.root in config")
        src = MountSource(root)
        source_desc = {"mode": "mount", "root": str(root), "filespace": fs_name}
        # keep the dashboard's own folder out of its numbers: tree and audit alike
        publish_to = deep_get(cfg, "output", "publish_to")
        if publish_to and not skip_prefix:
            try:
                rel_pub = Path(publish_to).resolve().relative_to(Path(root).resolve())
                if rel_pub.parts:
                    skip_prefix = "/" + "/".join(rel_pub.parts)
                    notes.append(f"Excluded {skip_prefix} (the dashboard's own folder) from counts.")
            except ValueError:
                pass
    elif source_kind == "sdk":
        token_env = deep_get(cfg, "filespace", "sdk", "token_env", default="LUCIDLINK_TOKEN")
        token = os.environ.get(token_env)
        if not token:
            sys.exit(f"sdk source needs a service-account token in ${token_env}")
        if not fs_name:
            sys.exit("sdk source needs filespace.name (<filespace>.<workspace>) in config")
        src = SdkSource(fs_name, token)
        source_desc = {"mode": "sdk", "filespace": fs_name}
    else:
        sys.exit(f"unknown source {source_kind}; use mount or sdk (mcp mode is driven by the agent, see references/mcp-recipe.md)")

    now = time.time()
    window_start = now - window_days * 86400

    # ---- tree walk
    files = dirs = 0
    total_bytes = 0
    by_folder: dict[str, dict] = collections.defaultdict(lambda: {"files": 0, "bytes": 0, "reads": 0, "writes": 0, "deletes": 0, "last_write": None, "writers": collections.Counter()})
    by_ext: collections.Counter = collections.Counter()
    by_ext_bytes: collections.Counter = collections.Counter()
    age_files = [0] * len(AGE_BUCKETS)
    age_bytes = [0] * len(AGE_BUCKETS)
    cold_candidates: list[tuple[int, str, float]] = []
    largest: list[tuple[int, str]] = []
    walked: list[tuple[str, bool, int, float]] = []

    for rel, is_dir, size, mtime in src.walk(excludes, b["max_entries"], b["max_seconds"]):
        if under(rel, skip_prefix):
            continue
        if is_dir:
            dirs += 1
            continue
        files += 1
        total_bytes += size
        f = by_folder[folder_of(rel, folder_depth)]
        f["files"] += 1
        f["bytes"] += size
        ext = Path(rel).suffix.lower() or "(none)"
        by_ext[ext] += 1
        by_ext_bytes[ext] += size
        age_days = max(0.0, (now - mtime) / 86400)
        for i, (_, limit) in enumerate(AGE_BUCKETS):
            if limit is None or age_days < limit:
                age_files[i] += 1
                age_bytes[i] += size
                break
        if size >= cold_min_bytes and age_days >= cold_min_age_days:
            cold_candidates.append((size, rel, mtime))
        if size > 0:
            largest.append((size, rel))
        if size >= cold_min_bytes:
            walked.append((rel, False, size, mtime))
    if src.clamped:
        notes.append(src.clamped + ". Tree-derived tiles are a sample, not a census.")
    cold_candidates.sort(reverse=True)
    largest.sort(reverse=True)
    candidate_rule = f"files of at least {cold_min_bytes // (1024 * 1024)} MB not modified for {cold_min_age_days} days"
    if not cold_candidates:
        oldest_large = sorted(((s_, r_, m_) for r_, d_, s_, m_ in walked if not d_ and s_ >= cold_min_bytes), key=lambda x: x[2])
        cold_candidates = oldest_large[:10]
        if cold_candidates:
            candidate_rule = f"no file of at least {cold_min_bytes // (1024 * 1024)} MB is older than {cold_min_age_days} days; showing the oldest large files instead"

    # ---- audit trail
    audit_present = False
    events = 0
    by_day: dict[str, dict] = collections.defaultdict(lambda: {"reads": 0, "writes": 0, "deletes": 0, "other": 0})
    by_action: collections.Counter = collections.Counter()
    by_actor: dict[str, dict] = {}
    by_hour = [0] * 24
    ticker: list[dict] = []
    delete_times: dict[str, list[float]] = collections.defaultdict(list)  # actor -> delete timestamps
    skipped_files = 0

    audit_files = src.audit_files()
    if audit_files:
        audit_present = True
    for path in audit_files:
        start = audit_file_start(path)
        # a log file spans forward from its name until the next file opens, so keep files
        # that begin up to one day before the window and filter per event below
        if start is not None and start < window_start - 86400:
            skipped_files += 1
            continue
        try:
            fh = src.open_audit(path)
        except Exception:
            continue
        with fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = rec.get("timestamp", 0) / 1e6
                if ts < window_start:
                    continue
                op = rec.get("operation", {})
                action = op.get("action", "?")
                epath = op.get("entryPath", "") or ""
                if epath.startswith("/.lucid_audit") or under(epath, skip_prefix):
                    continue
                # Excluded names (.DS_Store, node_modules, folders.exclude ...) stay out of the
                # folder table and the ticker, but the event still happened: it counts toward
                # the pulse and the actor, otherwise a login that only touched excluded paths
                # vanishes from the page and the totals stop matching the hub.
                excluded = any(seg in excludes for seg in epath.split("/") if seg)
                user = (rec.get("user") or {}).get("name") or "unknown"
                host = (rec.get("device") or {}).get("hostName")
                events += 1
                day = dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%d")
                hour = dt.datetime.fromtimestamp(ts, dt.timezone.utc).hour
                by_action[action] += 1
                d = by_day[day]
                if action in READ_ACTIONS:
                    d["reads"] += 1
                elif action in DELETE_ACTIONS:
                    d["deletes"] += 1
                elif action in WRITE_ACTIONS:
                    d["writes"] += 1
                else:
                    d["other"] += 1
                if b["hours"]:
                    by_hour[hour] += 1
                a = by_actor.setdefault(user, {"name": user, "label": actor_labels.get(user, user), "kind": classify_actor(user, service_patterns), "events": 0, "reads": 0, "writes": 0, "deletes": 0, "last_seen": 0.0, "hosts": collections.Counter()})
                a["events"] += 1
                if action in READ_ACTIONS:
                    a["reads"] += 1
                elif action in DELETE_ACTIONS:
                    a["deletes"] += 1
                    delete_times[user].append(ts)
                elif action in WRITE_ACTIONS:
                    a["writes"] += 1
                a["last_seen"] = max(a["last_seen"], ts)
                if host:
                    a["hosts"][host] += 1
                if excluded:
                    continue
                grp = folder_of(epath, folder_depth)
                f = by_folder[grp]
                if action in READ_ACTIONS:
                    f["reads"] += 1
                elif action in DELETE_ACTIONS:
                    f["deletes"] += 1
                    f["writers"][user] += 1
                    f["last_write"] = max(f["last_write"] or 0, ts)
                elif action in WRITE_ACTIONS:
                    f["writes"] += 1
                    f["writers"][user] += 1
                    f["last_write"] = max(f["last_write"] or 0, ts)
                tpath = (op.get("targetPath") or "") if action == "Move" else ""
                if tpath and not tpath.startswith("/.lucid_audit") and not any(seg in excludes for seg in tpath.split("/") if seg):
                    tgrp = folder_of(tpath, folder_depth)
                    if tgrp != grp:
                        t = by_folder[tgrp]
                        t["writes"] += 1
                        t["writers"][user] += 1
                        t["last_write"] = max(t["last_write"] or 0, ts)
                if action in TICKER_ACTIONS:
                    ticker.append({"ts": ts, "action": action, "path": epath + (" \u2192 " + tpath if tpath else ""), "user": user})

    if not audit_present:
        notes.append("No audit trail found under /.lucid_audit. Activity tiles are empty. An admin can enable the audit trail for this filespace; only events after that point are recorded.")
    elif events == 0:
        notes.append(f"Audit trail present but no events in the last {window_days} days.")
    if skipped_files:
        notes.append(f"Skipped {skipped_files} audit log files outside the {window_days}-day window without reading them.")

    # collapse safe-save fan-out: same action+path within the same second counts once in the ticker
    ticker.sort(key=lambda e: e["ts"], reverse=True)
    collapsed: list[dict] = []
    index: dict[tuple, dict] = {}
    for e in ticker:
        key = (e["path"], int(e["ts"]))
        if key in index:
            row = index[key]
            if e["action"] not in row["actions"]:
                row["actions"].append(e["action"])
            continue
        if len(collapsed) >= 25:
            break
        row = {"ts": iso(e["ts"]), "actions": [e["action"]], "path": e["path"], "user": actor_labels.get(e["user"], e["user"])}
        index[key] = row
        collapsed.append(row)
    for row in collapsed:
        row["action"] = ", ".join(sorted(row.pop("actions")))

    # ---- flags
    flags: list[dict] = []
    if b["flags"] and events:
        # Any 60-minute span with 100+ deletes by one actor, not clock hours: a burst that
        # straddles xx:00 must not be split into two halves that both stay under the bar.
        for user, times in delete_times.items():
            times.sort()
            i = 0
            while i < len(times):
                k = bisect.bisect_right(times, times[i] + 3600)
                if k - i >= 100:
                    when = dt.datetime.fromtimestamp(times[i], dt.timezone.utc).strftime("%Y-%m-%d %H:%MZ")
                    flags.append({"level": "warning", "text": f"{actor_labels.get(user, user)} deleted {k - i} entries within one hour starting {when}."})
                    i = k
                else:
                    i += 1
        humans = [a for a in by_actor.values() if a["kind"] == "human"]
        services = [a for a in by_actor.values() if a["kind"] == "service"]
        if not services:
            flags.append({"level": "neutral", "text": "No service accounts (agents or automations) touched this filespace in the window. Every event came from a human login."})
        if len(humans) == 1 and not services:
            flags.append({"level": "neutral", "text": "Single actor in the window. Per-actor tiles will look flat until more people or agents work here."})
        for a in by_actor.values():
            if a["kind"] == "service" and a["writes"] == 0 and a["deletes"] == 0 and a["reads"] > 0:
                flags.append({"level": "success", "text": f"Service account {a['label']} is read-only in practice: {a['reads']} reads, no writes."})
        writes_off_hours = sum(by_hour[h] for h in range(0, 6))
        if b["hours"] and events and writes_off_hours / events > 0.5:
            flags.append({"level": "neutral", "text": "Over half of all activity happened between 00:00 and 06:00 UTC. If that is not your working day, an automation or a remote team is the likely source."})

    # ---- assemble
    # One bucket per UTC calendar day the window touches, the first (partial) day
    # included, so every event counted above also appears in the chart.
    days = []
    cursor = dt.datetime.fromtimestamp(window_start, dt.timezone.utc).date()
    last_day = dt.datetime.fromtimestamp(now, dt.timezone.utc).date()
    while cursor <= last_day:
        day = cursor.isoformat()
        d = by_day.get(day, {"reads": 0, "writes": 0, "deletes": 0, "other": 0})
        days.append({"day": day, **d})
        cursor += dt.timedelta(days=1)

    stats = {
        "entries": files + dirs,
        "files": files,
        "dirs": dirs,
        "data_bytes": total_bytes,
        "storage_bytes": None,
        "external_files": None,
        "external_bytes": None,
        "stats_source": "tree walk",
    }
    # Where each header number came from, so the page can say "sample" next to a walked
    # figure and only compute stored/logical ratios from two hub figures.
    provenance = {"files": "tree walk", "dirs": "tree walk", "data_bytes": "tree walk"}
    src_stats = src.stats()
    if src_stats:
        for k, v in src_stats.items():
            if v is not None and not (k in ("entries", "files", "dirs") and not v):
                stats[k] = v
                provenance[k] = "hub (sdk get_statistics)"
        stats["stats_source"] = "sdk get_statistics"
    if args.stats:
        override = json.loads(Path(args.stats).read_text()) if os.path.exists(args.stats) else json.loads(args.stats)
        for k, v in override.items():
            stats[k] = v
            provenance[k] = "hub (provided)"
        stats["stats_source"] = "provided (for example from the MCP filespace_stats tool)"
    stats["provenance"] = provenance
    stats["walk_complete"] = src.clamped is None
    if stats.get("storage_bytes") is None:
        notes.append("Stored size (after deduplication and compression) is not visible through a mount. Pass --stats with storage_bytes from the MCP filespace_stats tool or use the sdk source.")

    folders_out = []
    for path, f in by_folder.items():
        if path == "/" and f["files"] == 0 and f["writes"] == 0 and f["reads"] == 0:
            continue
        folders_out.append({
            "path": path,
            "files": f["files"],
            "bytes": f["bytes"],
            "reads": f["reads"],
            "writes": f["writes"],
            "deletes": f["deletes"],
            "last_write": iso(f["last_write"]) if f["last_write"] else None,
            "writers": [actor_labels.get(u, u) for u, _ in f["writers"].most_common(5)],
        })
    folders_out.sort(key=lambda x: (x["writes"] + x["deletes"], x["reads"], x["bytes"]), reverse=True)

    actors_out = []
    for a in sorted(by_actor.values(), key=lambda x: x["events"], reverse=True):
        actors_out.append({
            "name": a["name"], "label": a["label"], "kind": a["kind"], "events": a["events"],
            "reads": a["reads"], "writes": a["writes"], "deletes": a["deletes"],
            "last_seen": iso(a["last_seen"]), "hosts": [h for h, _ in a["hosts"].most_common(3)],
        })

    snapshot = {
        "schema": SCHEMA,
        "generated_at": iso(now),
        "source": source_desc,
        "budget": budget,
        "window_days": window_days,
        "title": cfg.get("title") or (fs_name or Path(str(source_desc.get("root", "filespace"))).name),
        "stats": stats,
        "activity": {
            "events": events,
            "by_day": days,
            "by_action": dict(by_action.most_common()),
            "by_actor": actors_out,
            "by_hour": by_hour if b["hours"] else None,
        },
        "folders": folders_out[:40],
        "cold": {
            "buckets": [{"label": AGE_BUCKETS[i][0], "files": age_files[i], "bytes": age_bytes[i]} for i in range(len(AGE_BUCKETS))],
            "candidates": [{"path": p, "bytes": s, "mtime": iso(m)} for s, p, m in cold_candidates[:10]],
            "candidate_rule": candidate_rule,
        },
        "extensions": [{"ext": e, "files": by_ext[e], "bytes": by_ext_bytes[e]} for e, _ in by_ext_bytes.most_common(10)],
        "largest": [{"path": p, "bytes": s} for s, p in largest[:10]],
        "locks": None,
        "recent": collapsed,
        "flags": flags,
        "notes": notes,
    }
    return snapshot


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", help="config.yaml or config.json")
    ap.add_argument("--root", help="mounted filespace path (mount source)")
    ap.add_argument("--source", choices=["mount", "sdk"], help="override filespace.source")
    ap.add_argument("--budget", choices=list(BUDGETS), help="lite, standard or deep")
    ap.add_argument("--window", type=int, help="audit window in days")
    ap.add_argument("--stats", help="JSON string or file with stats overrides, e.g. storage_bytes from MCP filespace_stats")
    ap.add_argument("--out", help="output directory (default: config output.dir or ./out)")
    args = ap.parse_args()

    cfg = load_config(args.config)
    snap = collect(cfg, args)
    out_dir = Path(args.out or deep_get(cfg, "output", "dir", default="out"))
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "snapshot.json"
    out_path.write_text(json.dumps(snap, indent=2))
    print(f"wrote {out_path}")
    print(f"  entries walked: {snap['stats']['files']} files, {snap['stats']['dirs']} dirs; audit events in window: {snap['activity']['events']}; budget {snap['budget']}")
    for n in snap["notes"]:
        print(f"  note: {n}")


if __name__ == "__main__":
    main()
