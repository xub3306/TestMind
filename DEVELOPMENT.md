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

**MVP v0.4.0** — P0/P1/P2/P3全部完成，P4核心功能已交付。
288个测试全部通过，18个MCP工具。
- 用例版本历史管理、结果分析引擎、Web UI Playwright工具
- 性能测试引擎（benchmark + baseline + percentiles）、安全扫描（SQLi/XSS/路径遍历）

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
- [x] 6个OpenCode Skill（同上，带YAML frontmatter + skills.paths配置）
- [x] 项目配置模板（project.json.j2 / env.json.j2）
- [x] Agent配置模板（Claude settings.json / OpenCode opencode.jsonc / Cursor .cursorrules）

### 测试覆盖
- [x] **288个单元/集成测试全部通过**（35原有 + 8端到端 + 92工具层 + 50core补充 + 3 discover扩展 + 8 HTML报告 + 7并发 + 23 crypto + 13 suite）
- [x] 端到端集成测试（test_e2e.py）：init→parse_spec→validate→save→list→run→results→report 完整流程
- [x] tools层单元测试（test_tools/）：12个MCP工具全覆盖
- [x] core层补充测试（test_core_supplement.py）：assertion/variable/hooks/requirements_saver/runner
- [x] 并发执行集成测试（test_concurrent.py）：workers>1拓扑分层并发、依赖顺序、结果一致性
- [x] suite集成测试（test_suite.py）：setup/teardown hooks、策略覆盖、case收集、CLI命令
- [x] crypto模块测试（test_crypto.py）：加密/解密/透明解密/嵌套dict
- [x] HTML报告测试（test_report.py）：生成/空run/重试文件过滤/HTML转义
- [x] CLI退出码（0/1/2/10/20）
- [x] 重试结果持久化（{case_id}_retry_{n}.json）
- [x] Jinja2模板语法冲突修复（{{type:XXX}} / {{timestamp}}等）

### P2新增功能（v0.2.0）
- [x] discover_spec扩展路径（DISCOVERY_PATHS_EXTENDED，11个扩展路径，--extended参数）
- [x] HTML报告生成器（testmind/core/report.py，run后自动生成report.html，testmind report命令）
- [x] 并发执行bug修复（_execute_concurrent的all_results.append缺失，导致workers>1时结果丢失）
- [x] 敏感信息加密存储（testmind/utils/crypto.py，Fernet对称加密，enc:前缀格式，config透明解密，testmind crypto命令组）
- [x] CLI discover-spec命令修复（迭代bug + --extended参数）
- [x] 测试套件高级功能（suite级setup/teardown hooks执行、workers/retry/fail_fast策略覆盖、testmind suite create/list/show命令）

### P3新增功能（v0.3.0）
- [x] 用例版本历史管理（approve_cases自动升级version+记录changelog、save_case_to_project自动加metadata、testmind case pending/reject/history/show命令、approve加--project参数）
- [x] 结果分析引擎（testmind/core/analyze.py：run history/pass rate trend/top failures/duration trend、testmind analyze命令）
- [x] Web UI测试支持（Playwright MCP工具：browser_navigate/click/type/screenshot/get_text/close；18个MCP工具总计；testmind/core/web_driver.py浏览器生命周期管理）

## 本轮开发修复的Bug 🐛（P0端到端验证发现）

| Bug | 文件 | 修复 |
|-----|------|------|
| runner多处用`os.getcwd()`定位workspace，MCP server非项目目录启动时save/run/get_results全失败 | runner.py | 新增`_workspace_dir(config)`优先用`config.project_dir`，fallback到cwd |
| `_send_request`中`dict(request_data.get("headers", {}))`当headers为None时`dict(None)`崩溃 | runner.py | 改为`or {}`安全处理headers和params |
| httpx默认`trust_env=True`在Windows读取IE/Edge系统代理，localhost流量被路由导致502 | runner.py | 用`httpx.Client(trust_env=False)`替代`httpx.request`模块函数 |
| spec_fetcher的`httpx.AsyncClient`同样未禁用trust_env，discover/fetch在Windows受系统代理干扰 | spec_fetcher.py | 两处AsyncClient加`trust_env=False` |
| `_print_summary`用Unicode图标(✓✗○)在Windows GBK终端崩溃`UnicodeEncodeError` | runner.py / cli.py | 改为ASCII图标（PASS/FAIL/ERR!/SKIP） |
| **`_execute_concurrent`缺少`all_results.append(result)`，导致workers>1时用例结果全部丢失** | runner.py | **并发和单case层路径都补上append** |
| **CLI `discover-spec`命令迭代SpecFetchResult对象而非.found列表，且访问不存在的.url属性** | cli.py | **改为迭代result.found，访问dict键** |
| **`get_results`未过滤`*_retry_*.json`文件，导致重试结果被重复计入** | runner.py | **跳过stem含`_retry_`的文件** |
| **`_build_context`未放`project_dir`，导致suite setup/teardown hooks执行时报"project_dir not found"** | runner.py | **context里加`project_dir`字段** |
| **`_find_case_by_id`返回`case_id`而非`str(json_file)`，导致`get_case_history`读错路径** | runner.py | **改为返回文件路径** |
| **CLI `approve`命令缺`--project`参数，测试中无法指定项目路径** | cli.py | **加`--project`选项** |

## Bug修复记录 🐛（历史）

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
| **workspace定位** | **优先config.project_dir，fallback到os.getcwd()** | **MCP server可能从任意目录启动，不能依赖cwd** |
| **httpx请求** | **Client(trust_env=False)** | **避免Windows IE/Edge系统代理干扰localhost请求导致502** |
| **终端输出图标** | **ASCII（PASS/FAIL/ERR!/SKIP）** | **Windows GBK终端下Unicode图标崩溃** |
| **测试并行策略** | **子代理不并行跑pytest** | **pytest cache锁竞争+输出混乱导致子代理卡死，改为主代理顺序执行** |

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
│   ├── runner.py              # 执行引擎（拓扑排序、并发、重试、fail-fast、_workspace_dir）
│   ├── assertion.py           # 断言引擎（7+类型）
│   ├── variable.py            # 变量系统（5级优先级、内置函数、响应提取、$response.*）
│   ├── hooks.py               # 钩子系统（before/after/setup/teardown）
│   ├── spec_fetcher.py         # API规范发现和下载（trust_env=False、extended路径）
│   ├── spec_parser.py          # Spec解析和标准化
│   ├── requirements_saver.py  # 需求保存（JSON+MD双输出）
│   ├── report.py              # HTML报告生成器（自包含静态HTML）
│   └── project_init.py        # 项目初始化（Jinja2模板）
├── tools/                     # 12个MCP工具（每个独立register）
└── utils/
    ├── logger.py              # 审计日志+敏感信息脱敏
    └── crypto.py              # Fernet对称加密、enc:前缀、透明解密

templates/                     # Jinja2模板（6 Claude + 6 OpenCode + 配置）
tests/                         # 239个测试
├── test_e2e.py                # 端到端集成测试（9个，含mock HTTP server + report生成验证）
├── test_core/
│   ├── test_runner.py         # 原有core测试（31个）
│   ├── test_core_supplement.py # core补充测试（50个：assertion/variable/hooks/req_saver/runner）
│   ├── test_concurrent.py     # 并发执行集成测试（7个：拓扑分层/依赖顺序/结果一致性）
│   ├── test_report.py         # HTML报告测试（7个）
│   └── test_suite.py          # 测试套件集成测试（13个：setup/teardown/策略覆盖/CLI命令）
├── test_tools/                # tools层测试（92个）
│   ├── conftest.py            # 共享fixture（mock_api_server/project/cwd隔离）
│   ├── test_validate_case.py / test_save_case.py / test_run_cases.py
│   ├── test_get_results.py / test_list_cases.py / test_project_tools.py
│   └── test_discover_spec.py / test_fetch_url.py / test_parse_spec_tool.py
│       / test_save_spec.py / test_save_requirements.py
├── test_utils/
│   └── test_crypto.py         # crypto模块测试（23个）
└── test_models/               # 模型测试（4个）
```

## 下一步 📋

### P0 — 功能完善 ✅ 已完成
- [x] ~~完善`spec_parser.py`中`_extract_endpoints`适配EndpointInfo新类型~~（已在MVP完成）
- [x] ~~MCP Server实际启动验证~~（register_all验证通过，start_server可用）
- [x] ~~端到端测试：创建项目→下载Spec→解析→生成用例→执行→查看结果~~（test_e2e.py 8个测试通过）

### P1 — 测试覆盖 ✅ 已完成
- [x] ~~tools层单元测试（12个MCP工具）~~（test_tools/ 92个测试）
- [x] ~~core层单元测试（assertion / variable / hooks / runner完整流程）~~（test_core_supplement.py 50个测试）
- [x] ~~requirements_saver的MD生成测试~~（6个Markdown渲染测试）

### P2 — 功能扩展 ✅ 已完成
- [x] ~~discover_spec扩展路径（10+常见路径）~~（DISCOVERY_PATHS_EXTENDED 11路径 + --extended参数）
- [x] ~~测试套件高级功能（调度、并发策略）~~（suite setup/teardown、workers/retry/fail_fast覆盖、CLI命令）
- [x] ~~HTML报告（终端 + HTML双输出）~~（testmind/core/report.py，自动生成 + testmind report命令）
- [x] ~~敏感信息加密存储（crypto模块）~~（testmind/utils/crypto.py，Fernet + enc:前缀 + config透明解密）
- [x] ~~runner并发执行的完整集成测试（workers>1）~~（test_concurrent.py 7测试 + 修复all_results.append bug）

### P3 — V2功能 ✅ 已完成
- [x] ~~用例管理（版本历史/changelog）~~（approve自动升级版本+changelog、save_case自动加metadata、CLI case命令组）
- [x] ~~Web UI测试支持（Playwright MCP工具）~~（6个browser工具：navigate/click/type/screenshot/get_text/close，MCP工具总计18个）
- [x] ~~结果分析流程完善~~（analyze引擎 + testmind analyze命令：趋势/排行榜/统计）

### P4 — V3功能
- [x] ~~性能测试引擎~~（perf.py：多轮benchmark、p50/p90/p95/p99百分位、baseline对比回归检测、testmind perf run命令）
- [x] ~~安全测试引擎~~（security.py：SQL注入/XSS/路径遍历payload扫描、响应模式匹配、testmind security scan命令）
- [ ] Android APP自动探索（Redroid + Appium）

## 技术栈

| 类别 | 选型 |
|------|------|
| 语言 | Python 3.10+ |
| MCP框架 | mcp-python-sdk |
| HTTP客户端 | httpx (async, trust_env=False) |
| 数据模型 | pydantic v2 |
| CLI | click |
| JSONPath | jsonpath-ng |
| 模板 | jinja2 |
| 终端输出 | rich (ASCII icons) |
| 加密 | cryptography (Fernet, 可选依赖) |
| 测试 | pytest + pytest-asyncio |