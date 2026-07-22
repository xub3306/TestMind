# TestMind PyPI 发布流程

> 本文档描述如何将 TestMind 打包并发布到 PyPI。
> 每次发布前请完整阅读并逐步执行。

## 1. 发布前检查

### 1.1 版本号同步

修改 `pyproject.toml` 中的版本号：

```toml
[project]
version = "0.6.0"    # ← 更新版本号
```

`testmind/__init__.py` 中的 `__version__` 通过 `importlib.metadata` 动态读取 `pyproject.toml`，无需手动修改。`testmind/cli.py` 从 `__init__` 导入，同样自动同步。

### 1.2 确认代码质量

```bash
# 运行全部测试
python -m pytest tests/ -x --tb=short

# Lint 检查
ruff check testmind/

# 类型检查
mypy testmind/
```

### 1.3 更新文档

```bash
# 检查 README.md 是否反映最新功能
# 更新 DEVELOPMENT.md 中的版本号和已完成功能
```

## 2. 构建

### 2.1 安装构建工具

```bash
source .venv/bin/activate
pip install build twine
```

### 2.2 清理旧构建产物

```bash
rm -rf dist/ build/ *.egg-info/
```

### 2.3 构建

```bash
python -m build
```

成功后生成两个文件：
```
dist/
├── testmind_ai-0.5.0-py3-none-any.whl    (wheel)
└── testmind_ai-0.5.0.tar.gz              (sdist)
```

### 2.4 验证包内容

```bash
# 格式检查
twine check dist/*

# 确认模板文件已打包（关键！）
unzip -l dist/testmind_ai-*-py3-none-any.whl | grep -E "\.j2"
# 应输出 17 个 .j2 模板文件

# 确认 sdist 包含模板
tar tzf dist/testmind_ai-*.tar.gz | grep -E "\.j2$"
```

## 3. PyPI 认证

### 3.1 创建 `~/.pypirc`

```ini
[pypi]
username = __token__
password = pypi-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

> ⚠️ 使用 API Token（`pypi-` 前缀），不要用密码。Token 在 https://pypi.org/manage/account/token/ 创建。

### 3.2 文件权限

```bash
chmod 600 ~/.pypirc
```

## 4. 上传

### 4.1 先上传到 TestPyPI（首次发布或重大变更时）

```bash
twine upload -r testpypi dist/*
```

### 4.2 验证 TestPyPI 安装

```bash
pip install -i https://test.pypi.org/simple/ testmind-ai
testmind --version
```

### 4.3 上传到正式 PyPI

```bash
twine upload dist/*
```

## 5. 发布后

### 5.1 打 Git Tag

```bash
git tag v0.5.0
git push origin v0.5.0
```

### 5.2 验证 PyPI 页面

访问 https://pypi.org/project/testmind-ai/ 确认：
- [ ] 版本号正确
- [ ] README 渲染正常
- [ ] 侧边栏信息完整（URLs、分类器、License）

### 5.3 验证安装

```bash
pip install testmind-ai
testmind --version
testmind init demo --base-url https://httpbin.org
cd demo && testmind run --env dev
```

### 5.4 重置 Token（如已暴露）

如果 API Token 不慎暴露（如 echo、cat 输出），立即在 https://pypi.org/manage/account/token/ 删除旧 token、创建新 token，并更新 `~/.pypirc`。

## 6. 常见问题

### 构建报错：`URL 'dependencies' of field 'project.urls' must be a string`

原因：TOML 解析顺序问题，`[project.urls]` 必须在 `dependencies` 字段之后。

正确顺序：
```toml
[project]
name = "testmind-ai"
...
classifiers = [...]

dependencies = [...]           # ← 先写

[project.urls]                 # ← 后写
Homepage = "..."

[project.optional-dependencies]
```

### 模板文件未打包

确认 `pyproject.toml` 中有：
```toml
[tool.hatch.build.targets.wheel.force-include]
"templates" = "templates"
```

### twine 提示输入密码但 `.pypirc` 不生效

检查文件名：是 `.pypirc`（有 `r`），不是 `.pypic`。

## 7. 关键文件清单

| 文件 | 作用 |
|------|------|
| `pyproject.toml` | 包名、版本、依赖、构建配置 |
| `MANIFEST.in` | sdist 包含文件声明 |
| `testmind/__init__.py` | 动态版本号（`importlib.metadata`） |
| `README.md` | PyPI 页面展示 |
| `~/.pypirc` | PyPI 认证凭据 |
| `PUBLISH.md` | 本文档 |
