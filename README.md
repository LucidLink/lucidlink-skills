# LucidLink Skills

Agent skills from [LucidLink](https://www.lucidlink.com): packaged procedures
that give a coding agent a job to do in a LucidLink filespace. This repository
is one [Claude Code](https://code.claude.com) plugin, `lucidlink`, and the same
folder is a plain [Agent Skills](https://agentskills.io) package for
[Codex](https://developers.openai.com/codex) and other harnesses that read
`SKILL.md`. Tested with Claude Code and Codex; nothing else has been tried yet.

| Skill | What it does | Needs |
|---|---|---|
| [`filespace-dashboard`](skills/filespace-dashboard/) | Builds a shareable dashboard for a filespace from its audit trail and directory tree and places it inside the filespace: activity pulse, who is working where, humans versus agents, cold data, storage mix, newest changes. | a filespace with the audit trail on, and one of a mount, the LucidLink MCP server, or the Python SDK |

![filespace dashboard](skills/filespace-dashboard/examples/demo/screenshot.png)

## Install

Claude Code, as a plugin. Every skill in this repository comes with it, and
updates arrive when the plugin version changes:

```
/plugin marketplace add LucidLink/lucidlink-skills
/plugin install lucidlink@lucidlink-skills
```

Codex, as a skills folder. New sessions pick it up, and `git pull` brings new
skills:

```bash
git clone https://github.com/LucidLink/lucidlink-skills.git ~/.codex/skills/lucidlink
```

For one repository instead of your user account, clone into its
`.agents/skills/lucidlink`. When a skill writes into a mounted filespace, start
Codex with `--add-dir` for that folder; the sandbox blocks writes outside the
workspace otherwise. Claude Code without a marketplace takes the same clone at
`~/.claude/skills/lucidlink`.

Skills are named `lucidlink:<skill>` in both harnesses:
`/lucidlink:filespace-dashboard` in Claude Code, `$lucidlink:filespace-dashboard`
in Codex. Usually you just ask; each skill's description triggers it.

## Layout

```
lucidlink-skills/
├── .claude-plugin/
│   ├── plugin.json              # the plugin: name lucidlink, version
│   └── marketplace.json         # the catalog Claude Code adds: one entry, this plugin
├── skills/<name>/               # one folder per skill: SKILL.md, README.md, scripts, references, examples
├── LICENSE
└── README.md
```

A new skill is a new folder under `skills/`, a row in the table above, and a
version bump in `plugin.json`. Skill names are short and unprefixed; the plugin
supplies the `lucidlink:` namespace.

## Links

- [LucidLink AI](https://github.com/LucidLink/lucidlink-ai) - all LucidLink AI integrations
- [LucidLink MCP server on PyPI](https://pypi.org/project/lucidlink-mcp/)
- [LucidLink Python SDK on PyPI](https://pypi.org/project/lucidlink/)
- [LucidLink Developer Portal](https://developer.lucidlink.com/)
- [LucidLink Support](https://support.lucidlink.com/)
