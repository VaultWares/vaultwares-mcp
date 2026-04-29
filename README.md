# VaultWares FastMCP Server

A [FastMCP](https://github.com/prefecthq/fastmcp) server that provides **Credit Optimizer** and **Fast Navigation** skills for [Manus AI](https://manus.im) and any other [Model Context Protocol](https://modelcontextprotocol.io/) compatible client (Claude Desktop, Cursor, Windsurf, VS Code, etc.).

---

## Why This Server Exists

Manus AI charges credits per task. Most users waste **30–75%** because of:

| Problem | What happens | Waste |
|---|---|---|
| Wrong model routing | Simple tasks run in Max mode when Standard is identical | Up to **5× overpay** |
| No chat detection | Q&A / brainstorm tasks that cost $0 in Chat Mode run as Agent tasks | **100 % overpay** |
| Context bloat | Tokens accumulate across steps; each step costs more than the last | Exponential growth |
| Slow web fetching | Each URL takes 8–45 seconds via browser tool calls | **150+ seconds per 10 URLs** |

This server fixes all four automatically.

---

## Tools / Skills

### Credit Optimizer

| Tool | Description |
|---|---|
| `credit_classify` | Classify a prompt into one of 12 intents (code, research, qa, translation…) |
| `credit_recommend` | Recommend the cheapest Manus model with identical quality (chat / standard / max) |
| `credit_optimize` | Compress a prompt to reduce token costs while preserving meaning |
| `credit_estimate` | Estimate the credit cost of a prompt at each model tier |
| `credit_analyze_batch` | Analyse a list of prompts and return an aggregate optimisation plan |

### Fast Navigation

| Tool | Description |
|---|---|
| `nav_fetch` | Fetch a single URL via httpx — 30–2,000× faster than browser calls |
| `nav_fetch_many` | Fetch up to 20 URLs in parallel — 10 URLs in ~1.3 s vs. 150+ s |

---

## Skill Files (`skills/`)

The `skills/` directory contains **40 Manus-compatible `.skill` files** in valid YAML format.
Each file can be imported directly into Manus AI via **Settings → Skills → + Add → Upload `.skill` file**
or pushed to a GitHub repo and imported via **+ Add → Import from GitHub**.

### Credit Optimizer skills

| File | Description |
|---|---|
| `credit-optimizer.skill` | Full optimisation pipeline — routing + compression + batch detection |
| `credit-classify.skill` | Classify prompt intent into one of 12 categories |
| `credit-recommend.skill` | Recommend cheapest model tier with Quality Veto Rule |
| `credit-optimize-prompt.skill` | Compress prompts to reduce token cost |
| `credit-estimate.skill` | Estimate credit cost before execution |
| `credit-analyze-batch.skill` | Bulk-analyse a list of prompts for optimisation |
| `llm-context-hygiene.skill` | Detect and remove context bloat from long Manus sessions |

### Fast Navigation skills

| File | Description |
|---|---|
| `fast-navigation.skill` | Replace browser tool calls with direct httpx fetching (30–2,000× faster) |
| `web-scraping.skill` | Extract structured data from web pages |
| `research.skill` | Parallel multi-source web research |
| `browser-automation.skill` | Playwright automation for JS-heavy sites |

### Developer tools

| File | Description |
|---|---|
| `code-generation.skill` | Write idiomatic code in any language |
| `code-review.skill` | Security, correctness, and style review |
| `debugging.skill` | Diagnose and fix bugs from stack traces |
| `refactoring.skill` | Improve code structure without changing behaviour |
| `test-generation.skill` | Generate unit and integration tests |
| `documentation.skill` | Write docstrings, READMEs, and API references |
| `api-design.skill` | Design REST/GraphQL APIs with OpenAPI spec |
| `sql-query.skill` | Write and optimise SQL queries |
| `regex-builder.skill` | Build, test, and explain regular expressions |
| `performance-profiling.skill` | Identify and fix runtime bottlenecks |
| `security-audit.skill` | OWASP Top 10 and dependency vulnerability checks |
| `environment-setup.skill` | Set up Python/Node/Go/Rust dev environments |
| `git-workflow.skill` | Branching, commits, rebasing, PR prep |
| `ci-cd-pipeline.skill` | GitHub Actions, GitLab CI, CircleCI configs |
| `docker-compose.skill` | Dockerfile and docker-compose.yml best practices |
| `prompt-engineering.skill` | Write and optimise LLM system prompts |

### Data & document processing

| File | Description |
|---|---|
| `data-analysis.skill` | Stats, aggregation, and visualisation from CSV/JSON |
| `csv-processing.skill` | Read, clean, transform, and export CSV files |
| `pdf-processing.skill` | Extract text and tables from PDFs; merge/split |
| `image-processing.skill` | Resize, convert, compress, and OCR images |
| `json-yaml-transformer.skill` | Convert, validate, and transform JSON/YAML |
| `spreadsheet-formula.skill` | Excel and Google Sheets formula generation |
| `diagram-generation.skill` | Mermaid/PlantUML diagram generation |

### Writing & communication

| File | Description |
|---|---|
| `content-writing.skill` | Blog posts, articles, marketing copy |
| `translation.skill` | High-fidelity multi-language translation (Chat Mode, $0) |
| `email-drafting.skill` | Professional emails and cold outreach |
| `summarisation.skill` | Condense long documents into structured summaries |
| `markdown-formatting.skill` | Clean, well-structured Markdown output |

### Utilities

| File | Description |
|---|---|
| `cron-scheduler.skill` | Generate and explain cron expressions |

---

## Installation

### Prerequisites

- Python 3.10 or newer
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### Install from source

```bash
git clone https://github.com/VaultWares/fastmcp.git
cd fastmcp
pip install -e .
```

Or with uv:

```bash
uv pip install -e .
```

---

## Running the Server

### stdio transport (Claude Desktop, Cursor, Windsurf, VS Code)

```bash
python server.py
# or
python server.py --transport stdio
```

### HTTP transport (Manus AI custom MCP, any browser-based client)

```bash
python server.py --transport streamable-http --port 8000
```

The server will be available at `http://localhost:8000/mcp`.

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `MCP_TRANSPORT` | `stdio` | `stdio`, `sse`, or `streamable-http` |
| `MCP_HOST` | `0.0.0.0` | Host for HTTP transports |
| `MCP_PORT` | `8000` | Port for HTTP transports |
| `MCP_PATH` | `/mcp` | URL path for HTTP transports |

---

## Connecting from Manus AI

1. **Start the server** with HTTP transport (see above).  If you are running it
   on a remote machine, make sure port 8000 is publicly accessible or use a
   tunnel such as [ngrok](https://ngrok.com/) / [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/).

2. **Open Manus** → start a new conversation → click the **+** button next to
   the input field → choose **Connectors** → go to the **Custom MCP** tab.

3. Click **+ Add a custom MCP server** and fill in:

   | Field | Value |
   |---|---|
   | Server name | `VaultWares MCP` (or any name you like) |
   | Transport | `HTTP` |
   | Server URL | `http://<your-host>:8000/mcp` |

4. Click **Save**. Manus will fetch the tool list and display all 7 tools.

5. Use the tools directly in your conversations:
   - *"Use `credit_recommend` to analyse this prompt before running it"*
   - *"Use `nav_fetch_many` to read these 10 URLs in parallel"*

---

## Connecting from Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`
(macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "vaultwares-mcp": {
      "command": "python",
      "args": ["/absolute/path/to/fastmcp/server.py"]
    }
  }
}
```

Restart Claude Desktop — the tools will appear automatically.

---

## Connecting from Cursor / Windsurf / VS Code

Add to your project's `.cursor/mcp.json` (or equivalent):

```json
{
  "mcpServers": {
    "vaultwares-mcp": {
      "command": "python",
      "args": ["/absolute/path/to/fastmcp/server.py"]
    }
  }
}
```

---

## Development

### Run tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

### Project structure

```
fastmcp/
├── server.py               # FastMCP server entry point
├── tools/
│   ├── credit_optimizer.py # Credit Optimizer logic
│   └── fast_navigation.py  # Fast Navigation logic
├── skills/                 # 40 Manus-compatible .skill files (YAML)
│   ├── credit-optimizer.skill
│   ├── fast-navigation.skill
│   └── ... (38 more)
├── tests/
│   └── test_tools.py       # Unit tests
├── pyproject.toml
└── README.md
```

---

## License

MIT — see [LICENSE](LICENSE) for details.
