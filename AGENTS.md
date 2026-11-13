# Agent Notes — Cursor / Agent 约定

Obsidian vault + Git。细则：`.cursor/rules/vault.mdc`（建设与编辑）、`.cursor/rules/obsidian-stack.mdc`（Skill/MCP）。换机：`.cursor/SETUP.md`。

- 笔记只在 `笔记/`，默认平铺 `笔记/标题.md`
- 保留 `AGENTS.md`、`.cursor/`、`.obsidian/`、Git
- 不预建 Inbox / 编号夹 / 附件 / 模板；没有的配置不加
- 有歧义先问；只做被要求的事；「以后再说」则现在不做
- Markdown 加粗内容以括号等标点结尾且后面紧接正文时，将标点移出加粗范围（如 `**反向传播**（Backpropagation）沿……`）或在结束的 `**` 后加空格，避免 CommonMark 无法识别加粗闭合。

## 笔记开头规范

每篇 Markdown 笔记（`.md`）都应在正文一级标题后、文章内容前放置以下仓库介绍，使用 Markdown 引用块和可点击链接；新建或编辑笔记时补齐，已有时不重复添加。本规则适用于笔记正文文件，不适用于 `AGENTS.md`、`SKILL.md` 等项目配置或指令文件。

```markdown
> 本文收录于 [AI-Engineering-Notes](https://github.com/xallor-ai/AI-Engineering-Notes)，分享 AI 技术研究、工程实践与应用探索。欢迎 Star 关注后续更新，也欢迎通过 Issue 交流和纠错。
```
