# snapshot.json schema, version lucidlink-filespace-dashboard/1

`scripts/render.py` checks the required keys and fills the defaults. Any field
may be `null` when the source could not provide it; every tile has an empty
state. Sizes are bytes. Times are ISO 8601 UTC strings ending in `Z`.

```jsonc
{
  "schema": "lucidlink-filespace-dashboard/1",
  "generated_at": "2026-09-11T02:02:21Z",
  "source": { "mode": "mount | sdk | mcp", "root": "/Volumes/ws/fs", "filespace": "fs.ws" },
  "budget": "lite | standard | deep",
  "window_days": 7,
  "title": "northwind-post",                    // header text

  "stats": {
    "entries": 13686, "files": 13492, "dirs": 194,
    "data_bytes": 31006007988,                  // logical
    "storage_bytes": 33081017209,               // stored after dedup and compression; null on mount
    "external_files": 2, "external_bytes": 23407352,   // Connect-linked files
    "stats_source": "tree walk | sdk get_statistics | provided (...)",
    "provenance": { "files": "tree walk", "data_bytes": "hub (provided)", "storage_bytes": "hub (provided)" },  // per field; the header labels walked figures and only computes the dedup ratio from two hub figures
    "walk_complete": true                       // false when the walk hit its budget; the header then says "sample"
  },

  "activity": {
    "events": 11980,
    "by_day": [ { "day": "2026-09-05", "reads": 0, "writes": 0, "deletes": 0, "other": 0 } ],   // one per day in window, oldest first
    "by_action": { "FileRead": 10903, "FileWritten": 391 },
    "by_actor": [ {
      "name": "user@example.com", "label": "user@example.com",
      "kind": "human | service",
      "events": 12027, "reads": 10903, "writes": 800, "deletes": 324,
      "last_seen": "2026-09-11T01:35:25Z", "hosts": ["host-a"]
    } ],
    "by_hour": [0, 0, 5, ...]                   // 24 ints, UTC; null when not collected
  },

  "folders": [ {                                // grouped at folders.depth, busiest first, max 40
    "path": "/Shows", "files": 375, "bytes": 123456,
    "reads": 10350, "writes": 471, "deletes": 12,
    "last_write": "2026-09-11T00:26:31Z", "writers": ["user@example.com"]
  } ],

  "cold": {
    "buckets": [ { "label": "last 7 days", "files": 132, "bytes": 2737810187 } ],   // six fixed buckets, see snapshot.py AGE_BUCKETS
    "candidates": [ { "path": "/a/b.mov", "bytes": 36000000, "mtime": "2026-03-22T10:00:00Z" } ],
    "candidate_rule": "files of at least 10 MB not modified for 180 days"
  },

  "extensions": [ { "ext": ".gguf", "files": 2, "bytes": 7556500160 } ],   // by bytes, max 10; ext "(none)" for no suffix
  "largest": [ { "path": "/models/x.gguf", "bytes": 4000000000 } ],
  "locks": null,                                // or [ { "path": "...", "holder": "..." } ]

  "recent": [ {                                 // newest first, max 25, collapsed per path and second
    "ts": "2026-09-11T00:26:31Z", "action": "FileCreate, FileWritten",
    "path": "/x/y.md", "user": "user@example.com"
  } ],

  "flags": [ { "level": "warning | success | neutral | danger", "text": "..." } ],
  "notes": [ "free text about sampling, clamps, missing data" ]
}
```

Required top-level keys: `schema`, `generated_at`, `stats`, `activity`,
`folders`, `cold`, `extensions`, `recent`, `notes`. Required inside `activity`:
`events`, `by_day`, `by_action`, `by_actor`.

## Conventions

- `kind` is `service` for any actor matching `actors.service_patterns` in the config. The default pattern marks any name without `@` as a service account.
- `folders[].path` of `/` means files sitting at the filespace root.
- `by_day` covers the whole window even when a day has no events, so the chart keeps its shape.
- `recent[].action` may list several actions joined by `, ` when they hit the same path in the same second.
- Anything the collector could not do goes into `notes` as one plain sentence. The Flags tile prints them under "About this snapshot".
- Action mapping: reads are `FileRead` and `PreHydrate`; deletes are `FileDelete` and `DirectoryDelete`; writes are `FileWritten`, `FileCreate`, `DirectoryCreate`, `Move`, `SymlinkCreate`, `ExtendedAttributeSet`, `ExtendedAttributeDelete`, `Pin`, `Unpin`; everything else is `other`.
- `by_day` has one bucket per UTC calendar day the window touches, oldest first, so a 7-day window that starts mid-day has 8 buckets. Its four counters must be integers (the chart adds them); folder and actor counters may be `null` where a source could not provide them (rendered as `n/a`).
- `stats.provenance` values that start with `hub` are treated as hub figures: only two hub figures produce the dedup ratio, and walked figures are labelled as such. `stats.walk_complete: false` makes the header say "sample".
- `stats.entries` is informational (the hub's entry count, audit-log files included); the page does not display it.
- `by_actor[].hosts` come from the device hostname in each audit row; they are personal data like the actor names.
- `locks` is reserved; the page does not render it yet.
