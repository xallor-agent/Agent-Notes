---
title: 大模型推理实践：Gemma 4 12B 的 llama.cpp 部署与 OpenClaw 接入
tags:
  - gemma
  - llama-cpp
  - openclaw
  - wsl
  - docker
created: 2026-11-12
status: evergreen
---

# 大模型推理实践：Gemma 4 12B 的 llama.cpp 部署与 OpenClaw 接入

本文从一个已经可用的 WSL2 Ubuntu 开始，完成四件事：配置 CUDA 容器环境、从 ModelScope 下载 Gemma 4 12B、用 `llama-server` 提供 OpenAI 兼容 API、让同一 WSL Ubuntu 中的 OpenClaw 调用这套服务。

实测环境是 Ubuntu 22.04、RTX 4060 Ti 16GB、约 23GB WSL 内存和 6GB Swap；OpenClaw CLI 固定为 2026.11.3。模型使用 Google 官方 QAT Q4_0 GGUF，初始上下文为 16K。

## 1. 检查 Ubuntu、GPU 和内存

```bash
cat /etc/os-release
nvidia-smi
free -h
df -h /
```

WSL 中的 `nvidia-smi` 应能看到显卡、驱动和显存。不要在 WSL 内另装 Linux NVIDIA 显卡驱动；WSL 使用 Windows 驱动提供的 GPU 通道。

如果 `free -h` 显示的内存明显少于 16GB，模型下载不受影响，但模型加载、KV Cache 和多模态预处理更容易触发 OOM。可在 Windows 的 `%UserProfile%\.wslconfig` 中提高限制：

```ini
[wsl2]
memory=20GB
swap=8GB
```

保存后在 Windows PowerShell 执行：

```powershell
wsl --shutdown
```

重新进入 Ubuntu，再用 `free -h` 确认。`memory` 和 `swap` 是 WSL 的资源上限，应按 Windows 主机的实际物理内存调整，不要直接照搬示例值。这里只调整已有 WSL 的资源，不涉及 WSL 安装过程。

## 2. 安装 Docker Engine

按 Docker 官方 Ubuntu 仓库安装：

```bash
sudo apt update
sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
```

让当前用户可以直接运行 Docker：

```bash
sudo usermod -aG docker "$USER"
newgrp docker
docker version
```

## 3. 配置 NVIDIA Container Toolkit

```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -sL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt update
sudo apt install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

用 CUDA 基础镜像验证容器可以访问 GPU：

```bash
docker run --rm --gpus all \
  nvidia/cuda:12.8.1-base-ubuntu22.04 \
  nvidia-smi
```

成功标准是容器内能看到与 WSL 相同的 NVIDIA GPU。

## 4. 从 ModelScope 下载 Gemma 4 12B

创建独立目录：

```bash
mkdir -p ~/services/gemma4-llamacpp/{models,testdata}
cd ~/services/gemma4-llamacpp
```

使用 ModelScope CLI 时，先放进虚拟环境，避免污染系统 Python：

```bash
sudo apt install -y python3-venv
python3 -m venv ~/.venvs/modelscope
source ~/.venvs/modelscope/bin/activate
python -m pip install --upgrade pip modelscope
```

只下载运行所需的主模型和多模态投影文件：

```bash
modelscope download \
  google/gemma-4-12B-it-qat-q4_0-gguf \
  gemma-4-12b-it-qat-q4_0.gguf \
  mmproj-gemma-4-12b-it-qat-q4_0.gguf \
  --local-dir ~/services/gemma4-llamacpp/models
```

上面的写法已用 ModelScope `1.40.3` 验证。该版本把仓库 ID 和文件名作为位置参数；旧文章里常见的 `--model` 写法不适用于这个版本。

如果不想安装 ModelScope SDK，也可以直接使用仓库的 `resolve` 地址。`--continue-at -` 支持断点续传：

```bash
base=~/services/gemma4-llamacpp

curl -fL --retry 5 --retry-delay 3 --continue-at - \
  --output "$base/models/gemma-4-12b-it-qat-q4_0.gguf" \
  https://www.modelscope.cn/models/google/gemma-4-12B-it-qat-q4_0-gguf/resolve/master/gemma-4-12b-it-qat-q4_0.gguf

curl -fL --retry 5 --retry-delay 3 --continue-at - \
  --output "$base/models/mmproj-gemma-4-12b-it-qat-q4_0.gguf" \
  https://www.modelscope.cn/models/google/gemma-4-12B-it-qat-q4_0-gguf/resolve/master/mmproj-gemma-4-12b-it-qat-q4_0.gguf
```

下载完成后校验：

```bash
cd ~/services/gemma4-llamacpp/models
sha256sum gemma-4-12b-it-qat-q4_0.gguf \
  mmproj-gemma-4-12b-it-qat-q4_0.gguf
```

应得到：

```text
93567e57a8fe10b23569b9d9ec38cd005deedf71e29477c421a4b83f418a538b  gemma-4-12b-it-qat-q4_0.gguf
cb018338a7538a9814d994bfe54644c71eb7ed54e31eae2f721e45fd3c260da7  mmproj-gemma-4-12b-it-qat-q4_0.gguf
```

## 5. 拉取 llama.cpp CUDA 镜像

本文固定到 `b12282` 构建，避免 `latest` 在以后改变行为：

```bash
docker pull ghcr.io/ggml-org/llama.cpp:server-cuda-b12282
docker image inspect ghcr.io/ggml-org/llama.cpp:server-cuda-b12282 \
  --format '{{index .RepoDigests 0}}'
```

实测镜像索引摘要为：

```text
ghcr.io/ggml-org/llama.cpp@sha256:17934f68b6efc68671800735f25e209b489f47b610cfbb5c0a5c30965b54023c
```

## 6. 启动 llama-server

```bash
docker run -d \
  --name gemma4-llamacpp \
  --restart unless-stopped \
  --gpus all \
  -p 127.0.0.1:8080:8080 \
  -v "$HOME/services/gemma4-llamacpp/models:/models:ro" \
  ghcr.io/ggml-org/llama.cpp:server-cuda-b12282 \
  -m /models/gemma-4-12b-it-qat-q4_0.gguf \
  --mmproj /models/mmproj-gemma-4-12b-it-qat-q4_0.gguf \
  -c 16384 \
  -ngl 99 \
  --flash-attn on \
  --jinja \
  --api-key local-model \
  --host 0.0.0.0 \
  --port 8080
```

查看启动日志：

```bash
docker logs -f gemma4-llamacpp
```

看到模型加载完成后按 `Ctrl+C` 退出日志，不会停止容器。

检查模型加载后的资源占用：

```bash
nvidia-smi
free -h
docker stats --no-stream gemma4-llamacpp
```

分别观察 GPU 显存、WSL 内存与 Swap、容器 CPU 和内存占用。

## 7. 用 curl 验证 API

### 健康检查

```bash
curl -fsS http://127.0.0.1:8080/health
curl -fsS http://127.0.0.1:8080/v1/models \
  -H 'Authorization: Bearer local-model'
```

健康接口应返回 `{"status":"ok"}`。

### 文本请求

```bash
curl -fsS http://127.0.0.1:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer local-model' \
  -d '{
    "model": "gemma-4-12b-it-qat-q4_0.gguf",
    "messages": [
      {"role": "user", "content": "只回答一个数字：17 加 25 等于多少？"}
    ],
    "max_tokens": 64,
    "chat_template_kwargs": {"enable_thinking": false}
  }'
```

### 工具调用生成

下面的请求验证模型能否根据工具定义生成结构化调用。它只验证 tool call 的生成，不代表工具已经被执行：

```bash
curl -fsS http://127.0.0.1:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer local-model' \
  -d '{
    "model": "gemma-4-12b-it-qat-q4_0.gguf",
    "messages": [{
      "role": "user",
      "content": "调用 echo_code，参数 code 必须是 GEMMA4_TOOL_OK，不要直接回答。"
    }],
    "tools": [{
      "type": "function",
      "function": {
        "name": "echo_code",
        "description": "返回输入的校验码",
        "parameters": {
          "type": "object",
          "properties": {"code": {"type": "string"}},
          "required": ["code"]
        }
      }
    }],
    "tool_choice": "required",
    "max_tokens": 64,
    "chat_template_kwargs": {"enable_thinking": false}
  }'
```

成功时，响应中的 `tool_calls` 应包含 `echo_code` 和参数 `{"code":"GEMMA4_TOOL_OK"}`。

### 图片、音频和视频

多模态请求也走 `/v1/chat/completions`。把媒体文件路径替换为自己的文件，下面的 Python 脚本会把图片编码为 data URL、把音频和视频编码为原始 Base64，再依次发起测试：

```python
import base64
import json
import mimetypes
import pathlib
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8080/v1/chat/completions"
MODEL = "gemma-4-12b-it-qat-q4_0.gguf"

def data_url(path):
    p = pathlib.Path(path)
    mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(p.read_bytes()).decode()
    return f"data:{mime};base64,{encoded}"

def ask(label, content):
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 128,
        "temperature": 0,
        "chat_template_kwargs": {"enable_thinking": False},
    }).encode()
    request = urllib.request.Request(
        BASE,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer local-model",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            result = json.load(response)
        print(label, result["choices"][0]["message"])
    except urllib.error.HTTPError as error:
        print(label, error.code, error.read().decode())

ask("image", [
    {"type": "text", "text": "简要描述图片内容。"},
    {"type": "image_url", "image_url": {"url": data_url("test-image.png")}},
])
ask("audio", [
    {"type": "text", "text": "这是语音、音乐还是稳定的电子音？简要回答。"},
    {"type": "input_audio", "input_audio": {
        "data": base64.b64encode(pathlib.Path("test-audio.wav").read_bytes()).decode(),
        "format": "wav",
    }},
])
ask("video", [
    {"type": "text", "text": "简要描述视频中随时间发生的变化。"},
    {"type": "input_video", "input_video": {
        "data": base64.b64encode(pathlib.Path("test-video.mp4").read_bytes()).decode(),
        "format": "mp4",
    }},
])
```

本次验证结果：

| 路径 | 结果 |
| --- | --- |
| GPU backend | 通过，识别 RTX 4060 Ti 16GB |
| `/health`、`/v1/models` | 通过，模型加载完成并报告多模态能力 |
| 文本 | 通过，`17 + 25` 返回 `42` |
| 图片 | 通过，测试图返回 `Blue and yellow` |
| 工具调用生成 | 通过，模型返回 `echo_code` 与 `GEMMA4_TOOL_OK` 参数；未在该请求中执行工具 |
| 音频 | 当前模型、投影文件、b12282 与测试音频组合未给出有效识别，不宣称通过 |
| 视频 | 当前模型、投影文件、b12282 与请求格式组合返回 HTTP 400：`Failed to load image or audio file`，不宣称通过 |

“模型元数据列出支持某种模态”不等于该模态在这份 checkpoint、投影文件和请求格式组合下已经验证通过；部署结论以实际请求结果为准。OpenClaw Provider 的输入模态也只声明本次已验证通过的文本和图片。

## 8. 在 WSL Ubuntu 中接入 OpenClaw

OpenClaw 与 llama-server 运行在同一个 WSL Ubuntu 中，直接使用回环地址调用 API。

安装 OpenClaw CLI：

```bash
curl -fsSL https://openclaw.ai/install-cli.sh \
  | bash -s -- --version 2026.11.3 --runtime-only
export PATH="$HOME/.openclaw/bin:$PATH"
openclaw --version
openclaw setup --baseline
```

创建 Provider 补丁：

```bash
cat >/tmp/openclaw-gemma4-provider.json5 <<'EOF'
{
  models: {
    providers: {
      "gemma4-local": {
        baseUrl: "http://127.0.0.1:8080/v1",
        apiKey: "local-model",
        api: "openai-completions",
        timeoutSeconds: 300,
        models: [{
          id: "gemma-4-12b-it-qat-q4_0.gguf",
          name: "Gemma 4 12B QAT Q4_0",
          reasoning: false,
          input: ["text", "image"],
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
          contextWindow: 16384,
          maxTokens: 2048
        }]
      }
    }
  }
}
EOF
```

先做 dry-run，再应用并验证配置：

```bash
openclaw config patch --file /tmp/openclaw-gemma4-provider.json5 --dry-run
openclaw config patch --file /tmp/openclaw-gemma4-provider.json5
rm /tmp/openclaw-gemma4-provider.json5

openclaw config validate
openclaw models list
```

`models list` 应能看到 `gemma4-local/gemma-4-12b-it-qat-q4_0.gguf`。最后显式选择该模型完成一次 Agent 调用，不修改已有默认模型：

```bash
openclaw agent exec \
  --model gemma4-local/gemma-4-12b-it-qat-q4_0.gguf \
  --local-model-lean \
  --code-mode direct \
  --thinking off \
  "只回答一个数字：17 加 25 等于多少？" \
  --json
```

成功时，JSON 结果应包含 `"ok": true`、`"status": "ok"`，并且 `final` 字段包含 `42`。

本文固定安装 OpenClaw 2026.11.3，因此命令以该版本为准。

## 9. 常用维护命令

```bash
docker ps --filter name=gemma4-llamacpp
docker logs --tail 100 gemma4-llamacpp
docker restart gemma4-llamacpp
docker stop gemma4-llamacpp
docker start gemma4-llamacpp
nvidia-smi
```

模型文件挂载为只读，容器重建不会删除权重。API 只监听本机，不应直接暴露到局域网或公网。

## 参考资料

- [Gemma 4 官方文档](https://ai.google.dev/gemma/docs/core)
- [Google Gemma 4 12B QAT Q4_0 GGUF](https://huggingface.co/google/gemma-4-12B-it-qat-q4_0-gguf)
- [ModelScope 模型仓库](https://modelscope.cn/models/google/gemma-4-12B-it-qat-q4_0-gguf)
- [llama.cpp Docker 文档](https://github.com/ggml-org/llama.cpp/blob/master/docs/docker.md)
- [llama.cpp 多模态文档](https://github.com/ggml-org/llama.cpp/blob/master/docs/multimodal.md)
- [OpenClaw llama.cpp Provider](https://docs.openclaw.ai/plugins/llama-cpp)
- [WSL 高级配置](https://learn.microsoft.com/windows/wsl/wsl-config)
