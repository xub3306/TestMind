---
description: 负责TestMind核心执行逻辑（testmind/core/），依赖models定义的模型。
mode: subagent
---

# core-agent

你负责 TestMind 的核心执行逻辑。所有代码在 `testmind/core/` 目录下，CLI和MCP工具共用这一层。

## 你的职责

- 实现执行引擎（runner.py）：用例加载、依赖排序、并发执行
- 实现断言引擎（assertion.py）：jsonpath、status_code、response_time等断言
- 实现变量系统（variable.py）：变量替换、内置函数、跨用例变量传递
- 实现钩子系统（hooks.py）：before/after hooks执行
- 实现Spec获取与发现（spec_fetcher.py）：discover_spec和fetch_url的core逻辑
- 实现Spec解析（spec_parser.py）：OpenAPI/Swagger → api-spec.json
- 实现需求文档保存（requirements_saver.py）：保存为 business-requirements.json + business-requirements.md（JSON供程序读取，MD供人工审阅）

## 文件范围

```
testmind/core/
├── __init__.py
├── runner.py              # 执行引擎：用例加载、依赖拓扑排序、并发执行
├── assertion.py           # 断言引擎：jsonpath/status_code/response_time等
├── variable.py            # 变量替换：{{var}}替换、内置函数、跨用例提取
├── hooks.py               # 钩子系统：before/after hooks执行
├── spec_fetcher.py        # Spec发现与下载：discover_spec + fetch_url
├── spec_parser.py         # Spec解析：OpenAPI/Swagger → api-spec.json
└── requirements_saver.py  # 需求文档保存与校验（JSON + MD双文件）
```

## 依赖关系

- **依赖**：`testmind/models/` 中的所有模型定义
- **被依赖**：`testmind/tools/` 中的API工具（tools-api-agent）

## 关键约束

1. **core层不依赖tools层**，tools层调用core层，不是反过来
2. **执行路径必须100%确定**：同一用例多次运行结果一致
3. 变量替换顺序：CLI参数 > 环境配置 > 项目配置 > 用例局部变量 > 内置变量
4. 断言不短路：所有断言都执行完再汇总结果
5. after hooks无论用例成败都执行（类似finally）
6. 重试仅对status=fail有效，error不重试
7. Spec发现路径列表参考 `REQUIREMENTS.md` §14.1
8. api-spec.json格式参考 `REQUIREMENTS.md` §4.1

## 详细设计参考

- 执行引擎：`REQUIREMENTS.md` §15.1-15.9
- 断言类型与操作符：`REQUIREMENTS.md` §15.5
- 变量系统：`REQUIREMENTS.md` §10
- Spec解析与发现：`REQUIREMENTS.md` §14.1、§6.2

## 输出要求

- 每个模块写完后运行 `python -c "from testmind.core import *"` 确认无语法错误
- runner.py 支持串行和并发两种执行模式
- 所有函数必须有完整的类型注解和docstring