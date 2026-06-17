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

Architecture decisions: [docs/adr/001-document-tree.md](docs/adr/001-document-tree.md)
