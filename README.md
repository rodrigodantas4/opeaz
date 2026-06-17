# Django project for Document Tree technical assessment (Phase 2 PoC).

## Setup

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py test
```

## API (base `/api/v1/`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `entities/{entity_type}/{entity_id}/tree/` | Aggregated bootstrap view |
| GET | `tree-nodes/{id}/children/?entity_type=&entity_id=` | List child nodes |
| GET | `tree-nodes/{id}/content/?entity_type=&entity_id=` | Resolve leaf content |
| POST | `tree-nodes/{id}/shares/` | Create share |
| GET | `tree-nodes/{id}/breadcrumb/?entity_type=&entity_id=` | Breadcrumb path |
| PATCH | `tree-nodes/{id}/move/` | Reparent node (owner context in body) |

### Test / validation only (TODO — remove before production)

| Method | Path | Description |
|--------|------|-------------|
| GET | `test/laboratories/` | Paginated laboratories (max 50/page) |
| GET | `test/groupements/` | Paginated groupements (max 50/page) |
| GET | `test/pharmacies/` | Paginated pharmacies (max 50/page) |
| POST | `test/seed/` | Load assessment PDF example data (labs, groupements, pharmacies, trees) |
| GET | `test/tree-nodes/{id}/subtree/?entity_type=&entity_id=` | Full nested subtree from a node (test only) |

Query params: `?page=1`, `?page_size=50` (capped at 50). Seed: `?reset=false` to append without clearing (default `reset=true`).

Architecture decisions: [docs/adr/001-document-tree.md](docs/adr/001-document-tree.md)
