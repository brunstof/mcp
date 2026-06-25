# Exploration scripts

Ad-hoc, throwaway scripts used to inspect internal MariaDB servers while
investigating the `ad_service`, `kbme_*`, `matgrade` and `kbelog_db`
databases. They are **not** part of the MCP server and are kept only for
reference.

> **Credentials never live in these files.** They are read from environment
> variables via [`_conn.py`](_conn.py). Older copies of these scripts had
> passwords hardcoded — do not reintroduce that.

## Setup

Create a local, git-ignored `.env` (or export the vars in your shell):

```env
EXPLORE_DB_HOST=your-host
EXPLORE_DB_PORT=3320
EXPLORE_DB_USER=your-user
EXPLORE_DB_PASSWORD=your-password

# Only needed by the multi-server scripts (check_all_databases, find_ad_service):
EXPLORE_SERVERS=host-a:3306:user-a,host-b:3320:user-b
```

Load it and run a script:

```bash
set -a; . ./.env; set +a
uv run python scripts/exploration/analyze_ad_service.py
```

## Scripts

| Script | Purpose |
|--------|---------|
| `analyze_ad_service.py` | Record counts + ManagerEmail/CostCenter stats in `ad_service`. |
| `analyze_matgrade.py` | Structure of `matgrade` / `ad_service`, ManagerEmail columns. |
| `check_ad_service.py` | List `%ad%` / `%service%` databases and KBME tables. |
| `check_all_databases.py` | Multi-server database + table inventory. |
| `check_databases.py` | Inventory via the MCP server's FastMCP client. |
| `check_db.py` | Probe a single server for `ad_service`. |
| `department_diagram.py` | Department headcount chart from `ad_service.adusers`. |
| `find_ad_service.py` | Discover `ad_service` across multiple servers. |
| `find_manager_email.py` | Find ManagerEmail columns across all databases. |
| `list_dbs.py` | List databases/tables via the MCP server pool. |
| `query_ad_service.py` | Inspect `ad_service` Manager columns. |
| `query_matgrade.py` | Inspect `matgrade` / `ad_service` ManagerEmail columns. |
