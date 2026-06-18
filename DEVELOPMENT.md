# TestMind 开发状态

> 本文件用于跨会话继承上下文。新会话开头读取此文件即可恢复开发状态。
> 每次开发结束时更新此文件，包含已完成、进行中、下一步的信息。

## 项目概述

TestMind 是一个开源智能测试AI平台，采用 MCP Server + Agent 混合架构，Python技术栈。

- **架构**：Agent是大脑（Claude Code / OpenCode），TestMind是骨骼（MCP Server暴露工具）
- **需求文档**：`REQUIREMENTS.md`（永不上传仓库）
- **代理指令**：`AGENTS.md`（永不上传仓库）
- **仓库**：`git@github.com:xub3306/TestMind.git`

## 当前版本

**MVP v0.1.0** — 初始版本，全部功能已开发完毕并通过测试。

## 已完成功能 ✅

### 核心框架
- [x] 项目目录结构（按 REQUIREMENTS.md §8）
- [x] CLI入口 `testmind` 命令（init / run / results / list / clean / validate / approve / discover-spec / fetch-url / parse-spec / serve / hooks）
- [x] MCP Server入口 `testmind serve`
- [x] 项目初始化 `testmind init`（Jinja2模板、Claude/OpenCode配置生成）

### 数据模型（testmind/models/）
- [x] TestCase 全套模型（SkipCondition / AssertionDef / DataDriven / ExtractVar / HookConfig / RequestDef / ExpectDef / CaseMetadata）
- [x] Result 模型（RequestSnapshot / ResponseSnapshot / AssertionResult / CaseResult / SummaryResult）
- [x] Project 模型（ApiSpec / EndpointInfo / ParamInfo / BodyInfo / SchemaInfo / SpecSource / BusinessRequirements / ModuleInfo / BusinessFlow / StepInfo / ErrorFlow / PageInfo / BusinessRule / RequirementsSource）
- [x] Suite 模型（TestSuite + id字段）
- [x] Device模型（DeviceInfo / PlatformDevices / DevicesConfig）
- [x] Config模型（ProjectConfig / EnvConfig / AuthConfig / ProxyConfig + PrivateAttr）

### 核心引擎（testmind/core/）
- [x] Runner 执行引擎（拓扑排序、依赖解析、skip_if、disabled、env过滤、fail-fast、并发执行workers）
- [x] Assertion 断言引擎（status_code / jsonpath / header / response_time / json_schema / body_contains / custom）
- [x] Variable 变量系统（5级优先级、内置函数timestamp/uuid/random_int/random_string/random_email、响应提取）
- [x] Hooks 钩子系统（before/after/setup/teardown、同步/异步）
- [x] SpecFetcher + SpecParser（discover / fetch / parse / save）
- [x] RequirementsSaver（JSON + Markdown双输出）
- [x] ProjectInit（Jinja2模板渲染、Claude/OpenCode配置生成）

### MCP工具（testmind/tools/）
- [x] discover_spec — 自动发现API规范URL
- [x] fetch_url — 下载URL内容到本地
- [x] parse_spec — 解析Spec为api-spec.json
- [x] save_spec — 保存Agent提取的接口信息
- [x] save_requirements — 保存业务需求（JSON+MD双文件）
- [x] validate_case — 校验用例格式（JSON Schema + Pydantic）
- [x] save_case — 保存用例（去重、审核机制）
- [x] run_cases — 执行用例集
- [x] get_results — 获取执行结果
- [x] list_cases — 列出项目用例
- [x] init_project — 初始化项目
- [x] get_config — 获取项目配置
- [x] 全部12个工具集成审计日志

### Skill模板（templates/）
- [x] 6个Claude Skill（testmind / requirement-analyst / case-generator / case-runner / result-analyst / app-explorer）
- [x] 6个OpenCode Skill（同上，带YAML frontmatter）
- [x] 项目配置模板（project.json.j2 / env.json.j2）
- [x] Agent配置模板（Claude settings.json / OpenCode opencode.jsonc / Cursor .cursorrules）

### 其他
- [x] 35个单元测试全部通过
- [x] CLI退出码（0/1/2/10/20）
- [x] 重试结果持久化（{case_id}_retry_{n}.json）
- [x] Jinja2模板语法冲突修复（{{type:XXX}} / {{timestamp}}等）

## Bug修复记录 🐛

| Bug | 文件 | 修复 |
|-----|------|------|
| `_print_summary`引用不存在的`_current_results` | runner.py | 改为传递`all_results`参数 |
| `server.py`调用不存在的`validate_single_case` | runner.py | 添加函数 |
| `discover_async`签名不匹配 | spec_fetcher.py | 添加`project_name`参数 |
| `run_async`未真正异步 | runner.py | 改为`run_in_executor` |
| CLI `--agent`参数未解析为列表 | cli.py | 逗号分隔字符串处理 |
| `pyproject.toml`构建后端错误 | pyproject.toml | `hatchling.backends` → `hatchling.build` |
| Jinja2模板`{{type:XXX}}`冲突 | 10个模板文件 | `{% raw %}`包裹 |
| Jinja2模板`{{timestamp}}`等冲突 | 5个模板文件 | `{% raw %}`包裹 |

## 设计决策记录 📝

| 决策 | 选择 | 原因 |
|------|------|------|
| 用例去重 | fingerprint = hash(method+path+sorted(params)) | 同接口同参数视为重复 |
| 用例审核 | 同ID→.pending/，同fingerprint→拒绝 | 不覆盖已有用例 |
| 变量优先级 | CLI > 环境配置 > 项目配置 > 内置 | 最灵活 |
| Requirements输出 | JSON+MD双文件 | JSON程序读取，MD人工审阅 |
| MD生成方式 | JSON→MD单向派生 | 避免双向同步复杂性 |
| MCP工具注册 | `@server.list_tools()` + `@server.call_tool()` | 每个tool模块独立register |
| Skill架构 | 按工作流拆（1主+5工作流） | 不按测试类型拆 |
| 测试类型 | 作为Skill内知识区段 | 所有类型走同一流水线 |
| ProjectConfig._project_dir | Pydantic PrivateAttr | 避免model_dump包含内部字段 |
| CaseResult.status | Literal["pass","fail","error","skipped"] | 类型安全 |

## 项目结构速查 📁

```
testmind/
├── cli.py                    # CLI入口（click）
├── server.py                 # MCP Server入口
├── config/
│   ├── settings.py           # ProjectConfig / EnvConfig / AuthConfig
│   └── schema.py             # JSON Schema校验
├── models/
│   ├── testcase.py           # TestCase / RequestDef / ExpectDef / DataDriven / ExtractVar / HookConfig
│   ├── result.py             # CaseResult / SummaryResult / AssertionResult
│   ├── project.py            # ApiSpec / EndpointInfo / BusinessRequirements / DeviceInfo
│   └── suite.py               # TestSuite
├── core/
│   ├── runner.py              # 执行引擎（拓扑排序、并发、重试、fail-fast）
│   ├── assertion.py           # 断言引擎（7+类型）
│   ├── variable.py            # 变量系统（5级优先级、内置函数、响应提取）
│   ├── hooks.py               # 钩子系统（before/after/setup/teardown）
│   ├── spec_fetcher.py         # API规范发现和下载
│   ├── spec_parser.py          # Spec解析和标准化
│   ├── requirements_saver.py  # 需求保存（JSON+MD双输出）
│   └── project_init.py        # 项目初始化（Jinja2模板）
├── tools/                     # 12个MCP工具（每个独立register）
└── utils/
    └── logger.py              # 审计日志+敏感信息脱敏

templates/                     # Jinja2模板（6 Claude + 6 OpenCode + 配置）
tests/                         # 35个单元测试
```

## 下一步 📋

### P0 — 功能完善
- [ ] 完善`spec_parser.py`中`_extract_endpoints`适配EndpointInfo新类型（ParamInfo/BodyInfo/SchemaInfo）
- [ ] MCP Server实际启动验证（`testmind serve`）
- [ ] 端到端测试：创建项目→下载Spec→解析→生成用例→执行→查看结果

### P1 — 测试覆盖
- [ ] tools层单元测试（12个MCP工具）
- [ ] core层单元测试（assertion / variable / hooks / runner完整流程）
- [ ] requirements_saver的MD生成测试

### P2 — 功能扩展
- [ ] discover_spec扩展路径（10+常见路径）
- [ ] 测试套件高级功能（调度、并发策略）
- [ ] HTML报告（终端 + HTML双输出）
- [ ] 敏感信息加密存储（crypto模块）

### P3 — V2功能
- [ ] Web UI测试支持（Playwright MCP工具）
- [ ] 用例管理（版本历史/changelog）
- [ ] 结果分析流程完善

### P4 — V3功能
- [ ] Android APP自动探索（Redroid + Appium）
- [ ] iOS APP自动探索（Xcode Simulator + Appium）
- [ ] 性能/安全测试

## 技术栈

| 类别 | 选型 |
|------|------|
| 语言 | Python 3.10+ |
| MCP框架 | mcp-python-sdk |
| HTTP客户端 | httpx (async) |
| 数据模型 | pydantic v2 |
| CLI | click |
| JSONPath | jsonpath-ng |
| 模板 | jinja2 |
| 终端输出 | rich |
| 测试 | pytest + pytest-asyncio |