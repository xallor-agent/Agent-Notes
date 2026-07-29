# Agent Notes — Cursor / Agent 约定

本目录是 Obsidian vault，并用 Git 做版本管理。详细规则见 `.cursor/rules/`（含从 auto-book 继承的记忆、Skill/MCP 清单）。

编辑笔记时请遵守：

1. 保留 YAML frontmatter；不要无故删除 `tags` / `status` / `created`。
2. 站内链接优先 `[[wikilink]]`。
3. 修改时优先按章节增补或替换，避免整文件覆盖。
4. 删除、批量改标签、重命名前必须先得到用户确认。
5. 写新主题前先搜索 vault，避免重复笔记。
6. 新草稿放到 `00-Inbox/`；定稿主题放到 `10-Topics/`。
7. 勿将 Local REST API Key / 证书写入笔记或提交 Git；插件 `data.json` 已由 `.gitignore` 忽略。
