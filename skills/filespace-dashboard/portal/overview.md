# Overview - Filespace Dashboard

Filespace Dashboard is an agent skill that builds a shareable dashboard for a
LucidLink filespace from its audit trail and directory tree, and places it
inside the filespace so everyone with the drive mounted sees the same page.
Ask your agent for a dashboard and the skill confirms the details, collects
the data, renders the page, and tells you where it is. It ships in the
`lucidlink` plugin for Claude Code and works as an Agent Skills folder in
Codex; it has been tested with both.

:::features
- **Activity pulse**
  Reads, writes and deletes per day, with an hourly profile.
- **Humans versus agents**
  Service accounts appear as separate, accountable actors next to people.
- **Who is working where**
  Writers per folder, taken from the audit trail.
- **Cold data and storage mix**
  Bytes on the age curve, archive candidates, and size by file type.
- **Newest changes**
  Recent writes, moves and deletes with their actor, with one save's several audit rows collapsed into one.
:::

The dashboard is a single self-contained `index.html`: no server, no build
step, no network requests. The skill only reads the filespace, and its one
write is the dashboard folder you agree to.

## Requirements

- A LucidLink filespace with the audit trail enabled by a filespace admin. Only events after that point are recorded.
- One way to reach the filespace: a local mount, the LucidLink MCP server in your agent, or Python 3.10 or newer with the LucidLink Python SDK and a service-account token.
- Claude Code or Codex.
