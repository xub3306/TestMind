# TestMind

[![PyPI](https://img.shields.io/pypi/v/testmind-ai)](https://pypi.org/project/testmind-ai/)
[![Python](https://img.shields.io/pypi/pyversions/testmind-ai)](https://pypi.org/project/testmind-ai/)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

Open-source intelligent testing AI platform. **MCP Server + Agent** hybrid architecture — let AI generate, execute, and analyze your tests.

## Why TestMind?

- **🤖 AI-Driven**: Claude Code / OpenCode / Cursor act as the "brain" — they understand your API specs and generate high-quality test cases.
- **⚡ Dual Mode**: Use **Agent + MCP** for AI-powered workflows, or **CLI standalone** for CI/CD pipelines with zero AI dependency.
- **🔌 MCP-Native**: Built on the Model Context Protocol — any MCP-compatible agent can drive TestMind out of the box.
- **📐 Spec-Driven**: Point at an OpenAPI/Swagger spec, and TestMind generates structured, maintainable test cases automatically.

## Quick Start

```bash
# Install
pip install testmind-ai

# Initialize a new test project
testmind init my-project --type api --base-url https://api.example.com --agent claude

# Discover and parse your API spec
testmind discover-spec https://api.example.com
testmind fetch-url https://api.example.com/openapi.json
testmind parse-spec specs/openapi.json

# Run tests
testmind run --env dev --tags smoke

# View results
testmind results --status fail

# Start MCP Server (for AI agent integration)
testmind serve
```

## Architecture

```
┌──────────────────────┐     MCP Protocol     ┌──────────────────────────────┐
│   AI Agent (Brain)    │ ◄──────────────────► │   TestMind MCP Server         │
│  Claude / OpenCode    │                      │   • 18 MCP tools              │
│  Generate, Analyze,   │                      │   • Spec parsing              │
│  Strategy decisions   │                      │   • Case execution            │
└──────────────────────┘                      │   • Results analysis          │
                                               │   • Security scanning         │
                                               │   • Performance benchmarking  │
┌──────────────────────┐                      └──────────────────────────────┘
│   TestMind CLI        │
│  Zero AI, pure exec   │                                     │ HTTP
│  For CI/CD pipelines  │                      ┌──────────────────────────────┐
└──────────────────────┘                      │   Your API / Web App          │
                                               └──────────────────────────────┘
```

## Features

### Core Engine
- **Runner**: Topological sort, concurrent execution, retry, fail-fast, env filtering
- **Assertions**: status_code, jsonpath, header, response_time, json_schema, body_contains, custom
- **Variables**: 5-tier priority system + built-in functions (timestamp, uuid, random, etc.)
- **Hooks**: before/after, setup/teardown at project/suite/case level

### MCP Tools (18 total)
| Category | Tools |
|----------|-------|
| Spec | `discover_spec`, `fetch_url`, `parse_spec`, `save_spec`, `save_requirements` |
| Execution | `validate_case`, `save_case`, `run_cases`, `get_results`, `list_cases` |
| Project | `init_project`, `get_config` |
| Web UI | `browser_navigate`, `browser_click`, `browser_type`, `browser_screenshot`, `browser_get_text`, `browser_close` |

### CLI Commands
```bash
testmind init          # Create new project
testmind run           # Execute test cases
testmind results       # View test results
testmind analyze       # Analyze trends & failures
testmind perf run      # Performance benchmarking (p50/p90/p95/p99)
testmind security scan # SQL injection, XSS, path traversal scanning
testmind suite create  # Group cases into suites
testmind approve       # Review & approve pending cases
```

## Installation Options

```bash
# Core installation
pip install testmind-ai

# With crypto support (encrypted secrets)
pip install testmind-ai[crypto]

# With web UI testing (Playwright)
pip install testmind-ai[web]

# Full development setup
pip install testmind-ai[dev,crypto,web]
```

## Project Structure (after `testmind init`)

```
my-project/
├── testmind/
│   ├── project.json         # Project config
│   ├── envs/                # Environment configs (dev/staging/prod)
│   ├── specs/               # API specifications
│   ├── cases/               # Test cases (JSON)
│   ├── suites/              # Test suites
│   ├── hooks/               # Custom hook scripts
│   ├── results/             # Execution results + HTML reports
│   └── logs/                # Audit & run logs
├── .claude/                 # Claude Code integration (auto-generated)
├── .opencode/               # OpenCode integration (auto-generated)
└── .cursorrules             # Cursor rules (auto-generated)
```

## Requirements

- Python **3.10+**
- No external services required — runs entirely locally

## License

MIT © TestMind Team
