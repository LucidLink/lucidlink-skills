# Overview - LucidLink Skills

LucidLink Skills gives a coding agent a job to do in a LucidLink filespace.
Each skill is a packaged procedure the agent follows when you ask for that
job. The repository is one Claude Code plugin, `lucidlink`, and the same
folder is a plain Agent Skills package for Codex and other harnesses that read
`SKILL.md`. It has been tested with Claude Code and Codex.

The first skill, `filespace-dashboard`, builds a shareable dashboard for a
filespace from its audit trail and directory tree, and places it inside the
filespace so everyone with the drive mounted sees the same page.

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
