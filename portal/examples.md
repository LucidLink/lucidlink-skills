# Examples - LucidLink Skills

## Build a dashboard for a filespace

Ask your agent:

```text
Build a dashboard for the production filespace.
```

The skill asks, in one message, which filespace and how to reach it, who reads
the page first, which folders matter, how much to spend, and where to put the
page (by default `/Dashboards/<filespace>/` inside the filespace). It then
collects, renders, and tells you where the page is, with the three most
notable findings and the limits of the snapshot.

## Find out who touched what

```text
Who touched what in /Shows this week?
```

## Find archive candidates

```text
Which files over 1 GB haven't changed in six months?
```

## Refresh without an agent

The two scripts in `skills/filespace-dashboard` run on their own with
Python 3.10 or newer. Schedule them with cron, launchd or Task Scheduler and
the dashboard refreshes without spending agent tokens.

```bash
python3 scripts/snapshot.py --config config.yaml
python3 scripts/render.py --snapshot out/snapshot.json --publish "/Volumes/<workspace>/<filespace>/Dashboards/<name>"
```
