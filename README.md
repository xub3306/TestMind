# TestMind

Open-source intelligent testing AI platform. MCP Server + Agent hybrid architecture for Python.

## Quick Start

```bash
# Install
pip install testmind

# Initialize a project
testmind init my-project --type api --base-url https://api.example.com --agent claude

# Run tests
testmind run --env dev --tags smoke

# Start MCP Server
testmind serve
```

## Architecture

TestMind uses a **MCP Server + Agent** hybrid architecture:
- **Agent** (Claude Code / OpenCode) is the "brain" — makes decisions
- **TestMind MCP Server** is the "skeleton" — exposes tools for execution

Two usage paths:
1. **Agent + MCP** — AI-driven test generation, analysis, and strategy
2. **CLI standalone** — Pure execution, zero AI, for CI/CD pipelines

## License

MIT