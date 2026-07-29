---
title: 如何更好的面向Agent 的Obsidian 笔记编辑工具
tags:
  - agent
  - obsidian
  - mcp
  - skill
created: 2026-07-29
status: evergreen
---

# 如何更好的面向Agent 的Obsidian 笔记编辑工具

本库只用两样东西：**一个 Skill、一个 MCP**。

| 组件 | 仓库 | 作用 |
|------|------|------|
| **Skill** | [kepano/obsidian-skills](https://github.com/kepano/obsidian-skills) | 教 Agent 正确写 Obsidian 语法（wikilink、callout、properties、Bases、Canvas 等） |
| **MCP** | [coddingtonbear/obsidian-local-rest-api](https://github.com/coddingtonbear/obsidian-local-rest-api) | 让 Agent 通过工具读写/搜索本 vault（Obsidian 需保持打开） |

Vault：`C:\Users\andy.wang\Desktop\Agent-Notes`

---

## 1. Skill：`kepano/obsidian-skills`

### 有啥用

- 改笔记时遵守 Obsidian Flavored Markdown，而不是当普通文本乱改
- 正确处理 `[[wikilink]]`、embed、callout、YAML properties
- 需要时还能处理 Bases / JSON Canvas / Obsidian CLI

### 本机已配置

已装到 Cursor 个人 Skills 目录：

`C:\Users\andy.wang\.cursor\skills\`

含：`obsidian-markdown`、`obsidian-bases`、`json-canvas`、`obsidian-cli`、`defuddle`

### 自己重装（可选）

```bash
npx skills add https://github.com/kepano/obsidian-skills
```

或手动把仓库里 `skills/*` 拷到 `%USERPROFILE%\.cursor\skills\`。

装完后 **重启 Cursor / 新开 Agent 对话** 后生效。

---

## 2. MCP：`obsidian-local-rest-api`

### 有啥用

- Agent 可 list / read / search / create / append / patch 本 vault 笔记
- 走 Obsidian 进程内的 Local REST API + 内置 MCP，比「当文件夹瞎改」更安全、更贴 Obsidian

### Obsidian 侧（本库已预装插件）

1. 用 Obsidian **打开本库** `Agent-Notes`（须保持运行）
2. 设置 → **社区插件** → 关闭安全模式（若提示）
3. 确认已启用：**Local REST API with MCP**
4. 设置 → 该插件 → 打开 **Enable non-encrypted (HTTP) server**（本库 `data.json` 已设为开启）
5. 在插件设置里查看 **API Key**（密钥只留本机：插件 `data.json` 与 `~/.cursor/mcp.json`，**不要写进笔记或提交 Git**）

HTTP MCP 地址：`http://127.0.0.1:27123/mcp/`

### Cursor 侧（已写入 `~/.cursor/mcp.json`）

```json
"obsidian": {
  "url": "http://127.0.0.1:27123/mcp/",
  "headers": {
    "Authorization": "Bearer <从 Obsidian 插件设置复制 API Key>"
  }
}
```

然后：**Cursor Settings → MCP** 刷新/重启，看到 `obsidian` 为已连接。

### 自检

1. Obsidian 已打开 `Agent-Notes`
2. 浏览器或 curl 访问：`http://127.0.0.1:27123/`（应有 API 响应；未授权会 401，属正常）
3. Cursor Agent 能列出 Obsidian MCP 工具并读一篇笔记

---

## 3. 怎么一起用

1. Obsidian 打开本 vault  
2. Cursor Agent 编辑笔记时：  
   - **Skill** 约束写法  
   - **MCP** 执行读写  
3. 不要关着 Obsidian 还指望这个 MCP 工作（它跑在 Obsidian 进程里）
