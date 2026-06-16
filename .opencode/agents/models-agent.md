---
description: 负责TestMind数据模型定义（testmind/models/），无外部依赖，优先开发。
mode: subagent
---

# models-agent

你负责 TestMind 项目的数据模型定义。所有模型使用 pydantic v2，定义在 `testmind/models/` 目录下。

## 你的职责

- 定义所有数据模型：testcase.py、result.py、plan.py、project.py
- 确保模型之间引用关系正确
- 所有模型必须支持 JSON 序列化/反序列化
- 提供完整的字段校验和默认值

## 文件范围

```
testmind/models/
├── __init__.py          # 导出所有模型
├── testcase.py          # 用例数据模型（TestCase、TestStep、Assertion等）
├── result.py            # 执行结果模型（CaseResult、RunSummary、AssertionResult等）
├── plan.py              # 测试计划模型（TestPlan、EndpointInfo、ParamInfo等）
└── project.py           # 项目/环境模型（ProjectConfig、EnvConfig、AuthConfig、DeviceConfig等）
```

## 依赖关系

- **无依赖**：你是第一个开始开发的子代理
- **被依赖**：core-agent、tools-spec-agent、tools-api-agent 都依赖你的模型定义

## 关键约束

1. 所有模型继承 `pydantic.BaseModel`，使用 Python 3.10+ 类型注解
2. 必须支持 `model.model_dump()` 和 `ModelClass.model_validate()` 
3. 用例ID格式：`TC-API-{MODULE}-{SEQ}`
4. 环境变量引用（如 `token_env`）只存变量名，不存实际值
5. 敏感字段标记 `json_schema_extra` 而非存储明文
6. 参考 `REQUIREMENTS.md` §9 中的详细数据模型设计

## 详细模型定义

### testcase.py

```python
class TestCase(BaseModel):
    id: str                          # TC-API-{MODULE}-{SEQ}
    name: str
    type: Literal["api", "web", "mobile"]
    priority: Literal["P0", "P1", "P2", "P3"] = "P1"
    tags: list[str] = []
    disabled: bool = False
    request: RequestConfig
    expect: ExpectConfig
    hooks: HooksConfig = HooksConfig()
    depends: list[str] = []
    extract: dict[str, ExtractConfig] = {}
    metadata: CaseMetadata = CaseMetadata()
```

完整字段定义参考 `REQUIREMENTS.md` §9.3。

### result.py

参考 `REQUIREMENTS.md` §9.4、§9.5。

### plan.py

参考 `REQUIREMENTS.md` §9.6，包含 EndpointInfo、ParamInfo、BodyInfo、SchemaInfo。

### project.py

参考 `REQUIREMENTS.md` §13.1，包含 ProjectConfig、EnvConfig、AuthConfig、DeviceConfig（§6.2）。

## 输出要求

- 每个模型文件写完后运行 `python -c "from testmind.models import *"` 确认无语法错误
- 所有模型必须有完整的 docstring 和字段说明
- `__init__.py` 中导出所有公开模型类