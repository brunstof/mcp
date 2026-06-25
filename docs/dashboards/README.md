# Project dashboards

Self-contained HTML dashboards visualising the MariaDB MCP Server. Open
[`index.html`](index.html) in any browser — no build step or server required.

| Page | Contents |
|------|----------|
| `index.html` | Overview, headline metrics, navigation |
| `architecture.html` | Request-flow flowchart, MCP tool catalog, vector-search sequence diagram |
| `infrastructure.html` | Docker topology, internal MariaDB server map, `kbme_statistic` data pipeline |
| `implementation-status.html` | 6-phase modernization roadmap (flow + gantt), task breakdown |
| `tech-stack.html` | Layered stack diagram, current-vs-target versions |
| `testing.html` | Test pyramid, CI quality gate, safety-net coverage |

## Diagrams

Diagrams render with [Mermaid 11](https://mermaid.js.org/). The pages load a
locally vendored copy from `vendor/mermaid.min.js` if present (works fully
offline), and otherwise fall back to the jsDelivr CDN. Each diagram renders
independently and surfaces any parse error inline.

The `vendor/` directory is git-ignored (the bundle is ~3 MB). To re-create it
for offline use:

```bash
mkdir -p docs/dashboards/vendor
curl -fsS -o docs/dashboards/vendor/mermaid.min.js \
  https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js
```
