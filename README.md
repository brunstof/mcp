# MCP MariaDB Server

The MCP MariaDB Server provides a Model Context Protocol (MCP) interface for managing and querying MariaDB databases, supporting both standard SQL operations and advanced vector/embedding-based search. Designed for use with AI assistants, it enables seamless integration of AI-driven data workflows with relational and vector databases.

---

## Table of Contents

- [Overview](#overview)
- [Core Components](#core-components)
- [Available Tools](#available-tools)
- [Embeddings & Vector Store](#embeddings--vector-store)
- [Configuration & Environment Variables](#configuration--environment-variables)
- [Installation & Setup](#installation--setup)
- [Usage Examples](#usage-examples)
- [Integration - Claude desktop/Cursor/Windsurf](#integration---claude-desktopcursorwindsurf)
- [Logging](#logging)
- [Testing & Quality](#testing--quality)
- [Development & Quality](#development--quality)
- [Project Dashboards](#project-dashboards)
- [Project Status & Roadmap](#project-status--roadmap)
---

## Overview

The MCP MariaDB Server exposes a set of tools for interacting with MariaDB databases and vector stores via a standardized protocol. It supports:
- Listing databases and tables
- Retrieving table schemas
- Executing safe, read-only SQL queries
- Creating and managing vector stores for embedding-based search
- Integrating with embedding providers (currently OpenAI, Gemini, and HuggingFace) (optional)

---

## Core Components

- **server.py**: Main MCP server logic and tool definitions.
- **config.py**: Loads configuration from environment and `.env` files.
- **embeddings.py**: Handles embedding service integration (OpenAI).
- **tests/**: Manual and automated test documentation and scripts.

---

## Available Tools

### Standard Database Tools

- **list_databases**
  - Lists all accessible databases.
  - Parameters: _None_

- **list_tables**
  - Lists all tables in a specified database.
  - Parameters: `database_name` (string, required)

- **get_table_schema**
  - Retrieves schema for a table (columns, types, keys, etc.).
  - Parameters: `database_name` (string, required), `table_name` (string, required)

- **get_table_schema_with_relations**
  - Retrieves schema with foreign key relations for a table.
  - Parameters: `database_name` (string, required), `table_name` (string, required)

- **execute_sql**
  - Executes a read-only SQL query (`SELECT`, `SHOW`, `DESCRIBE`).
  - Parameters: `sql_query` (string, required), `database_name` (string, optional), `parameters` (list, optional)
  - _Note: Enforces read-only mode if `MCP_READ_ONLY` is enabled._
  
- **create_database**
  - Creates a new database if it doesn't exist.
  - Parameters: `database_name` (string, required)  

### Vector Store & Embedding Tools (optional)

**Note**: These tools are only available when `EMBEDDING_PROVIDER` is configured. If no embedding provider is set, these tools will be disabled.

- **create_vector_store**
  - Creates a new vector store (table) for embeddings.
  - Parameters: `database_name`, `vector_store_name`, `model_name` (optional), `distance_function` (optional, default: cosine)

- **delete_vector_store**
  - Deletes a vector store (table).
  - Parameters: `database_name`, `vector_store_name`

- **list_vector_stores**
  - Lists all vector stores in a database.
  - Parameters: `database_name`

- **insert_docs_vector_store**
  - Batch inserts documents (and optional metadata) into a vector store.
  - Parameters: `database_name`, `vector_store_name`, `documents` (list of strings), `metadata` (optional list of dicts)

- **search_vector_store**
  - Performs semantic search for similar documents using embeddings.
  - Parameters: `database_name`, `vector_store_name`, `user_query` (string), `k` (optional, default: 7)

---

## Embeddings & Vector Store

### Overview

The MCP MariaDB Server provides **optional** embedding and vector store capabilities. These features can be enabled by configuring an embedding provider, or completely disabled if you only need standard database operations.

### Supported Providers

- **OpenAI**
- **Gemini**
- **Open models from Huggingface**

### Configuration

- `EMBEDDING_PROVIDER`: Set to `openai`, `gemini`, `huggingface`, or leave unset to disable
- `OPENAI_API_KEY`: Required if using OpenAI embeddings
- `GEMINI_API_KEY`: Required if using Gemini embeddings
- `HF_MODEL`: Required if using HuggingFace embeddings (e.g., "intfloat/multilingual-e5-large-instruct" or "BAAI/bge-m3")
### Model Selection

- Default and allowed models are configurable in code (`DEFAULT_OPENAI_MODEL`, `ALLOWED_OPENAI_MODELS`)
- Model can be selected per request or defaults to the configured model

### Vector Store Schema

A vector store table has the following columns:
- `id`: Auto-increment primary key
- `document`: Text of the document
- `embedding`: VECTOR type (indexed for similarity search)
- `metadata`: JSON (optional metadata)

---

## Configuration & Environment Variables

All configuration is via environment variables (typically set in a `.env` file):

| Variable               | Description                                            | Required | Default      |
|------------------------|--------------------------------------------------------|----------|--------------|
| `DB_HOST`              | MariaDB host address                                   | Yes      | `localhost`  |
| `DB_PORT`              | MariaDB port                                           | No       | `3306`       |
| `DB_USER`              | MariaDB username                                       | Yes      |              |
| `DB_PASSWORD`          | MariaDB password                                       | Yes      |              |
| `DB_NAME`              | Default database (optional; can be set per query)      | No       |              |
| `DB_CHARSET`           | Character set for database connection (e.g., `cp1251`) | No       | MariaDB default |
| `MCP_READ_ONLY`        | Enforce read-only SQL mode (`true`/`false`)            | No       | `true`       |
| `MCP_MAX_POOL_SIZE`    | Max DB connection pool size                            | No       | `10`         |
| `EMBEDDING_PROVIDER`   | Embedding provider (`openai`/`gemini`/`huggingface`)   | No     |`None`(Disabled)|
| `OPENAI_API_KEY`       | API key for OpenAI embeddings                          | Yes (if EMBEDDING_PROVIDER=openai) | |
| `GEMINI_API_KEY`       | API key for Gemini embeddings                          | Yes (if EMBEDDING_PROVIDER=gemini) | |
| `HF_MODEL`             | Open models from Huggingface                           | Yes (if EMBEDDING_PROVIDER=huggingface) | |
| `ALLOWED_ORIGINS`      | Comma-separated list of allowed origins                | No       | Long list of allowed origins corresponding to local use of the server |
| `ALLOWED_HOSTS`        | Comma-separated list of allowed hosts                  | No       | `localhost,127.0.0.1` |

Note that if using 'http' or 'sse' as the transport, configuring authentication is important for security if you allow connections outside of localhost. Because different organizations use different authentication methods, the server does not provide a default authentication method. You will need to configure your own authentication method. Thankfully FastMCP provides a simple way to do this starting with version 2.12.1. See the [FastMCP documentation](https://gofastmcp.com/servers/auth/authentication#environment-configuration) for more information. We have provided an example configuration below.

#### Example `.env` file

**With Embedding Support (OpenAI):**
```dotenv
DB_HOST=localhost
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_PORT=3306
DB_NAME=your_default_database

MCP_READ_ONLY=true
MCP_MAX_POOL_SIZE=10

EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=AI...
HF_MODEL="BAAI/bge-m3"
```

**Without Embedding Support:**
```dotenv
DB_HOST=localhost
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_PORT=3306
DB_NAME=your_default_database
MCP_READ_ONLY=true
MCP_MAX_POOL_SIZE=10
```

#### Multiple Database Support

The server can connect to several MariaDB/MySQL servers at once. Use the
comma-separated `*S` variants of the connection variables instead of the
single-value ones; entries are matched by position. The first entry becomes
the default pool, and additional pools are keyed by `host:port`.

| Variable        | Description                                  |
|-----------------|----------------------------------------------|
| `DB_HOSTS`      | Comma-separated hosts                        |
| `DB_PORTS`      | Comma-separated ports                        |
| `DB_USERS`      | Comma-separated users                        |
| `DB_PASSWORDS`  | Comma-separated passwords                    |
| `DB_NAMES`      | Comma-separated default databases (optional) |
| `DB_CHARSETS`   | Comma-separated charsets (optional)          |

```dotenv
DB_HOSTS=localhost,db2.internal
DB_PORTS=3306,3320
DB_USERS=your_db_user,your_other_user
DB_PASSWORDS=your_db_password,your_other_password
DB_NAMES=demo,
DB_CHARSETS=,

MCP_READ_ONLY=false
MCP_MAX_POOL_SIZE=10
```

Each connection keeps its own pool, and queries are routed to the correct pool
based on the `database_name` argument passed to a tool. Single-database
configuration (the `DB_HOST`/`DB_PORT`/... variables above) remains fully
supported and unchanged.

**Example Authentication Configuration:**
This configuration uses external web authentication via GitHub or Google. If you have internal JWT authentication (desired for organizations who manage their own services), you can use the JWT provider instead.

```dotenv
# GitHub OAuth
export FASTMCP_SERVER_AUTH=fastmcp.server.auth.providers.github.GitHubProvider
export FASTMCP_SERVER_AUTH_GITHUB_CLIENT_ID="Ov23li..."
export FASTMCP_SERVER_AUTH_GITHUB_CLIENT_SECRET="github_pat_..."

# Google OAuth
export FASTMCP_SERVER_AUTH=fastmcp.server.auth.providers.google.GoogleProvider
export FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_ID="123456.apps.googleusercontent.com"
export FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_SECRET="GOCSPX-..."
```

---

## Installation & Setup

### Requirements

- **Python 3.13+** (see `.python-version`)
- **uv** (dependency manager; [install instructions](https://github.com/astral-sh/uv))
- MariaDB server (local or remote)

### Steps

1. **Clone the repository**
2. **Install `uv`** (if not already):
   ```bash
   pip install uv
   ```
3. **Install dependencies**
   ```bash
   uv lock
   uv sync
   ```
4. **Create `.env`** in the project root (see [Configuration](#configuration--environment-variables))
5. **Run the server**
   
   **Standard Input/Output (default):**
   ```bash
   uv run server.py
   ```
   
   **SSE Transport:**
   ```bash
   uv run server.py --transport sse --host 127.0.0.1 --port 9001
   ```
   
   **HTTP Transport (streamable HTTP):**
   ```bash
   uv run server.py --transport http --host 127.0.0.1 --port 9001 --path /mcp
   ```

---

## Usage Examples

### Standard SQL Query

```python
{
  "tool": "execute_sql",
  "parameters": {
    "database_name": "test_db",
    "sql_query": "SELECT * FROM users WHERE id = %s",
    "parameters": [123]
  }
}
```

### Create Vector Store

```python
{
  "tool": "create_vector_store",
  "parameters": {
    "database_name": "test_db",
    "vector_store_name": "my_vectors",
    "model_name": "text-embedding-3-small",
    "distance_function": "cosine"
  }
}
```

### Insert Documents into Vector Store

```python
{
  "tool": "insert_docs_vector_store",
  "parameters": {
    "database_name": "test_db",
    "vector_store_name": "my_vectors",
    "documents": ["Sample text 1", "Sample text 2"],
    "metadata": [{"source": "doc1"}, {"source": "doc2"}]
  }
}
```

### Semantic Search

```python
{
  "tool": "search_vector_store",
  "parameters": {
    "database_name": "test_db",
    "vector_store_name": "my_vectors",
    "user_query": "What is the capital of France?",
    "k": 5
  }
}
```
---

## Integration - Claude desktop/Cursor/Windsurf/VSCode

### Option 1: Direct Command (stdio)
```json
{
  "mcpServers": {
    "MariaDB_Server": {
      "command": "uv",
      "args": [
        "--directory",
        "path/to/mariadb-mcp-server/",
        "run",
        "server.py"
        ],
        "envFile": "path/to/mcp-server-mariadb-vector/.env"      
    }
  }
}
```

### Option 2: SSE Transport
```json
{
  "servers": {
    "mariadb-mcp-server": {
      "url": "http://{host}:9001/sse",
      "type": "sse"
    }
  }
}
```

### Option 3: HTTP Transport
```json
{
  "servers": {
    "mariadb-mcp-server": {
      "url": "http://{host}:9001/mcp",
      "type": "streamable-http"
    }
  }
}
```

---

## Logging

- Logs are written to `logs/mcp_server.log` by default.
- Log messages include tool calls, configuration issues, embedding errors, and client requests.
- Log level and output can be adjusted in the code (see `config.py` and logger setup).

---

## Testing & Quality

Tests live in `src/tests/` (see `src/tests/README.md`).

**Unit tests — no database required.** The pool / `_execute_query` are mocked, so these run anywhere
and fast. They guard the read-only query gateway: write-blocking, SQL-comment-bypass protection,
parameter forwarding and result limiting.

```bash
uv run pytest src/tests/test_execute_query_unit.py src/tests/test_list_databases_unittest.py -v
```

**Integration & provider tests — require live infrastructure.** A configured MariaDB is needed; the
embedding / vector-store tests additionally require an `EMBEDDING_PROVIDER`.

```bash
uv run pytest src/tests/ -v
```

---

## Development & Quality

This project uses [`ruff`](https://docs.astral.sh/ruff/) (lint + format),
[`mypy`](https://mypy-lang.org/) (type-check) and [`pre-commit`](https://pre-commit.com/).
A GitHub Actions workflow (`.github/workflows/ci.yml`) runs the lint/type gate plus the test suite
against a MariaDB service container on every push and pull request.

```bash
uv run ruff check src/          # lint (add --fix to autofix)
uv run ruff format src/         # format
uv run mypy src/                # type-check
uv run pre-commit install       # enable hooks (one-time)
uv run pre-commit run --all-files
```

Ad-hoc database-exploration scripts live in `scripts/exploration/` and read **all** credentials from
environment variables — never hardcode secrets (see `scripts/exploration/README.md`).

---

## Project Dashboards

Self-contained HTML dashboards — **architecture, infrastructure, implementation status, tech stack,
and testing** — live in [`docs/dashboards/`](docs/dashboards/). Open `docs/dashboards/index.html` in
any browser; no build step is required. Diagrams render with Mermaid (vendored locally with an
automatic CDN fallback).

---

## Project Status & Roadmap

A six-phase modernization is underway (internal-tooling focus). **Phases 0 & 1 are complete.**

| Phase | Scope | Status |
|-------|-------|--------|
| 0 | Repo cleanup & secret hygiene | ✅ Done |
| 1 | Tooling & CI — ruff, mypy, pre-commit, GitHub Actions, safety-net unit tests | ✅ Done |
| 2 | Refactor `server.py` into `pool` / `query` / `tools` modules | ⬜ Planned |
| 3 | DB driver: `asyncmy` → official `mariadb` Connector 2.0 (incl. `%s` → `?` placeholder change) | ⬜ Planned |
| 4 | FastMCP `2.12` → `3.x` | ⬜ Planned |
| 5 | Observability — OpenTelemetry, structured logs, richer `/health` | ⬜ Planned |

See [`docs/dashboards/implementation-status.html`](docs/dashboards/implementation-status.html) for the full roadmap.
