# Django project for Document Tree technical assessment (Phase 2 PoC).

## Setup

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py test
```

## Session entity context (PoC)

Tree read endpoints require an active entity bound to the Django session. Select it once, then send the session cookie on subsequent requests.

```bash
# 1. Bind entity (stores session cookie)
curl -c cookies.txt -X POST http://localhost:8000/api/v1/session/entity/ \
  -H "Content-Type: application/json" \
  -d '{"entity_type": "pharmacy", "entity_id": 1}'

# 2. Read tree (uses session)
curl -b cookies.txt http://localhost:8000/api/v1/entities/tree/
```

Production would replace session keys with JWT claims; authorization (`TreeService.can_entity_access_node`) stays the same.

## API (base `/api/v1/`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `session/entity/` | Bind active entity to session |
| DELETE | `session/entity/` | Clear session entity |
| GET | `entities/tree/` | Aggregated bootstrap view (session required) |
| GET | `tree-nodes/{id}/children/` | List child nodes (session required) |
| GET | `tree-nodes/{id}/content/` | Resolve leaf content (session required) |
| POST | `tree-nodes/{id}/shares/` | Create share |
| GET | `tree-nodes/{id}/breadcrumb/` | Breadcrumb path (session required) |
| PATCH | `tree-nodes/{id}/move/` | Reparent node (owner context in body) |

### Test / validation only (TODO — remove before production)

| Method | Path | Description |
|--------|------|-------------|
| GET | `test/laboratories/` | Paginated laboratories (max 50/page) |
| GET | `test/groupements/` | Paginated groupements (max 50/page) |
| GET | `test/pharmacies/` | Paginated pharmacies (max 50/page) |
| POST | `test/seed/` | Load assessment PDF example data (labs, groupements, pharmacies, trees) |
| GET | `test/tree-nodes/{id}/subtree/` | Full nested subtree from a node (session required) |

Query params: `?page=1`, `?page_size=50` (capped at 50). Seed: `?reset=false` to append without clearing (default `reset=true`).

Architecture decisions: [docs/adr/001-document-tree.md](docs/adr/001-document-tree.md)
