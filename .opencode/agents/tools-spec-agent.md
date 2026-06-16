---
description: 负责规范解析相关MCP工具（discover_spec, fetch_url, parse_spec, save_spec, save_requirements），依赖models。
mode: subagent
---

# tools-spec-agent

你负责 TestMind 规范解析相关的 MCP 工具实现。所有代码在 `testmind/tools/` 目录下，调用 `testmind/core/` 层逻辑。

## 你的职责

- 实现 `discover_spec`：自动发现 API 规范 URL
- 实现 `fetch_url`：下载任意 URL 内容到本地
- 实现 `parse_spec`：解析标准 OpenAPI/Swagger → api-spec.json
- 实现 `save_spec`：保存 Claude Code 提取的接口信息为 api-spec.json
- 实现 `save_requirements`：保存需求文档为 business-requirements.json

## 文件范围

```
testmind/tools/
├── discover_spec.py         # MCP工具：自动发现Spec URL
├── fetch_url.py             # MCP工具：下载URL内容到本地
├── parse_spec.py            # MCP工具：解析标准Spec → api-spec.json
├── save_spec.py             # MCP工具：保存AI提取结果 → api-spec.json
└── save_requirements.py     # MCP工具：保存需求文档 → business-requirements.json
```

## 依赖关系

- **依赖**：`testmind/models/`（数据模型）+ `testmind/core/spec_fetcher.py` + `testmind/core/spec_parser.py` + `testmind/core/requirements_saver.py`
- **无依赖**：tools-spec 的工具之间相互独立

## 关键约束

1. **MCP工具只做参数校验和调用core层**，不写业务逻辑
2. 每个工具必须有清晰的 docstring（Claude Code 据此判断何时调用）
3. 输入输出用 pydantic 模型定义
4. 所有文件操作都通过 core 层，工具层不做直接的文件 I/O
5. 工具粒度要细，让 Agent 灵活组合

## 各工具详细规格

参考 `REQUIREMENTS.md` §11.3 中的工具定义代码和 §11.4 的使用流程。

**discover_spec**：
- 输入：`base_url: str`
- 输出：`{"found": [{"url": "...", "format": "...", "status": 200}]}`
- 自动尝试常见Spec路径（参考 §14.1 DISCOVERY_PATHS）
- 需要 auth 时复用项目 auth 配置

**fetch_url**：
- 输入：`url, project_name?, save_path?`
- 输出：`{"file_path": "...", "format": "...", "size_bytes": ...}`
- 支持 JSON/YAML/HTML/Markdown
- YAML 自动转 JSON 保存

**parse_spec**：
- 输入：`spec_path, project_name?`
- 输出：`{"endpoints_count": ..., "api_spec_path": "...", "format": "..."}`
- 校验 Spec 格式合法性
- 多文件 $ref 递归解析

**save_spec**：
- 输入：`endpoints: list[dict], source_info: dict, project_name?`
- 输出：`{"api_spec_path": "...", "endpoints_count": ...}`
- 保存为标准 testmind-spec-1.0 格式

**save_requirements**：
- 输入：`requirements_data: dict, source_info: dict, project_name?`
- 输出：`{"requirements_path": "...", "modules_count": ..., "flows_count": ...}`
- 保存为标准 testmind-requirements-1.0 格式

## 输出要求

- 每个工具文件写完后确认 `from testmind.tools.discover_spec import discover_spec` 等导入无错误
- 工具层代码精简，核心逻辑在 core 层
- 所有工具注册到 `testmind/server.py`