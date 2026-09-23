# Customizing the dashboard

The page is one HTML file that reads one JSON block. Change the JSON and the
page changes. Change the JavaScript at the bottom of `templates/dashboard.html`
and the tiles change. Nothing is compiled.

## Without touching code

| Want | Change |
|---|---|
| Per-show or per-client folders instead of top level | `folders.depth: 2` in `config.yaml` |
| Ignore a noisy folder | add its name to `folders.exclude` |
| Friendly names for service accounts | `actors.labels: { "sa-render-01": "Render farm" }` |
| Treat some humans as automations | add a regex to `actors.service_patterns` |
| Different archive rule | `cold.candidate_min_bytes`, `cold.candidate_min_age_days` |
| Longer window | `window_days: 30` or `--window 30` |
| Different title | `title:` in the config |
| Somewhere else in the filespace | `output.publish_to` |

## Adding a tile

1. Add the data to `snapshot.json`. If the collector produces it, add a block
   in `collect()` in `scripts/snapshot.py` and a key in the assembled dict. If
   the agent produces it through MCP, document the call in `mcp-recipe.md`.
2. In `templates/dashboard.html`, copy one of the tile functions, for example
   `ext()`, rename it, read your key from `S`, and build the body with the
   `el`, `table` and `card` helpers already there. `card()` takes `span`,
   `title`, `persona`, `subtitle`, `body` and `tryNext`.
3. Give the tile an empty state. Every source can fail to provide a field.
4. Keep the chart rules: one hue per series in a fixed order, a legend for two
   or more series, a table view for anything a colorblind reader might miss,
   no dual axes, no shadows on cards.

## Changing the look

The style is a token sheet at the top of the template. Replace the `--ll-*`
values with your own and every component follows.

Chart colors are separate tokens (`--viz-*`) so a rebrand does not silently
break the color rules. If you change them, check the categorical set with a
colorblind simulator.

## Making it live

- `refresh: script`: schedule `snapshot.py` then `render.py --publish` every
  hour. The page shows the snapshot time in the header.
- Trends: `--publish` keeps every snapshot under `history/`. Read them with a
  few lines of Python or a second page.
- Live ticker: a small process with the MCP Server or SDK that subscribes to a
  folder and appends to `recent`. See `tile-catalog.md`.

## Sharing outside the filespace

The page is self-contained, so it can be copied anywhere. Actor names inside
it are personal data. Keep it inside the filespace by default and ask before
sending it elsewhere.
