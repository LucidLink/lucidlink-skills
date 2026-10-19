# Installation - Filespace Dashboard

## Claude Code

Install it as a plugin. Every skill in the repository comes with it, and
updates arrive when the plugin version changes.

:::steps
1. **Add the marketplace**
   ```text
   /plugin marketplace add LucidLink/lucidlink-skills
   ```
2. **Install the plugin**
   ```text
   /plugin install lucidlink@lucidlink-skills
   ```
3. **Ask for a skill's job**
   The description triggers the skill. To call it by name, use `/lucidlink:filespace-dashboard`.
:::

## Codex

Install it as a skills folder. New sessions pick it up, and `git pull` brings
new skills.

:::steps
1. **Clone the repository into your Codex skills folder**
   ```bash
   git clone https://github.com/LucidLink/lucidlink-skills.git ~/.codex/skills/lucidlink
   ```
2. **Allow writes to a mounted filespace, if a skill needs them**
   Start Codex with `--add-dir` for that folder. The sandbox blocks writes outside the workspace otherwise.
3. **Ask for a skill's job**
   To call it by name, use `$lucidlink:filespace-dashboard`.
:::

:::note
For a single repository instead of your user account, clone into its `.agents/skills/lucidlink`. Claude Code without a marketplace takes the same clone at `~/.claude/skills/lucidlink`.
:::
