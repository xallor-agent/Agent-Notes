# 换机 / 新环境部署清单

clone 本库后，Cursor 打开本目录即可带上 **rules + project skills + MCP 声明**。还需本机一次性配置：

## 1. Obsidian

1. 安装 Obsidian，打开本 vault
2. 启用社区插件 **Local REST API with MCP**（`community-plugins.json` 已声明；缺插件时从社区重装）
3. 开启 insecure HTTP（`27123`），复制 API Key

## 2. 环境变量（密钥，勿提交）

PowerShell（当前用户）：

```powershell
[Environment]::SetEnvironmentVariable("OBSIDIAN_REST_API_KEY", "<你的 API Key>", "User")
```

然后**重启 Cursor**。项目 `.cursor/mcp.json` 通过 `${env:OBSIDIAN_REST_API_KEY}` 注入，仓库内无明文密钥。

## 3. GitHub 免密（可选）

```powershell
winget install --id GitHub.cli -e
gh auth login
gh auth setup-git
```

## 4. 自检

- Cursor Settings → MCP：`obsidian` 已连接
- Agent 能 `vault_list` / 读一篇笔记
- `git push` 不再要密码（已 `gh auth`）

## 已进仓库 vs 仅本机

| 进 Git | 仅本机 |
|--------|--------|
| `.cursor/rules/` | `OBSIDIAN_REST_API_KEY` |
| `.cursor/skills/` | `.obsidian/plugins/**/data.json` |
| `.cursor/mcp.json`（无密钥） | `~/.cursor/mcp.json` 里其它个人 MCP |
| `笔记/` 正文与 `AGENTS.md` | GitHub PAT / SSH key |

笔记：默认 `笔记/<标题>.md` 平铺。根目录不放知识笔记。不预建 Inbox / 附件 / 模板目录。

