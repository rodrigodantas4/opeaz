# Django project for Document Tree technical assessment (Phase 2 PoC).

Architecture decisions: [docs/adr/001-document-tree.md](docs/adr/001-document-tree.md)

## Setup

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py test
python manage.py runserver
```

For manual API checks below, use a second terminal. All examples assume `http://localhost:8000/api/v1` and store the session in `cookies.txt`.

## Session entity context (PoC)

Tree **read** endpoints require an active entity bound to the Django session. Select it once, then send the session cookie on subsequent requests.

```bash
curl -c cookies.txt -X POST http://localhost:8000/api/v1/session/entity/ \
  -H "Content-Type: application/json" \
  -d '{"entity_type": "pharmacy", "entity_id": 1}'
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

---

## Phase 2 — step-by-step validation

Each section below maps to a **Decisions at a glance** row in the ADR. Run the shared bootstrap first, then follow the steps for each topic.

### 0 — Bootstrap (all manual checks)

```bash
# Load PDF example data (CPC, Nuxe, Bioderma, three pharmacies, full trees)
curl -X POST http://localhost:8000/api/v1/test/seed/

# Optional: list entities to confirm pagination works
curl "http://localhost:8000/api/v1/test/pharmacies/?page=1"

# Bind session as Farmácia Central (primary pharmacy from seed; id is usually 1 on fresh DB)
curl -c cookies.txt -X POST http://localhost:8000/api/v1/session/entity/ \
  -H "Content-Type: application/json" \
  -d '{"entity_type": "pharmacy", "entity_id": 1}'
```

Save node IDs from the seed response `nodes` object (e.g. `cpc_root_id`, `conditions_2025_id`, `conditions_leaf_id`, `nuxe_root_id`, `my_documents_id`, `vat_leaf_id`). Replace `$ID` placeholders below with those values.

Automated regression for the whole PoC:

```bash
python manage.py test
```

---

### Q1 — Tree structure (adjacency list, lazy children, move)

**What to prove:** children are loaded per folder (not full tree at once); move updates `parent_id` without duplicating nodes.

1. **Lazy children** — CPC shared root should expose two folders, not deeper leaves:

```bash
curl -b cookies.txt "http://localhost:8000/api/v1/tree-nodes/$CPC_ROOT_ID/children/"
```

Expect names `Condições 2025` and `Flyers do agrupamento` (alphabetical). No `Condições gerais` or `Flyer Solares` here.

2. **Drill down** — load grandchildren:

```bash
curl -b cookies.txt "http://localhost:8000/api/v1/tree-nodes/$CONDITIONS_2025_ID/children/"
```

Expect one leaf: `Condições gerais`.

3. **Move node** — reparent the VAT leaf under `Meus documentos` (already its parent in seed; move to same parent is idempotent, or pick another owned folder):

```bash
curl -b cookies.txt -X PATCH "http://localhost:8000/api/v1/tree-nodes/$VAT_LEAF_ID/move/" \
  -H "Content-Type: application/json" \
  -d '{"owner_type": "pharmacy", "owner_id": 1, "parent_id": '$MY_DOCUMENTS_ID'}'
```

Expect `200` and `"parent_id": <my_documents_id>`. Re-fetch children of `Meus documentos` to confirm the leaf appears there.

4. **Cycle rejected** — moving a folder into its own descendant should return `400` (see `document_tree/tests.py` → `TreeNodeMoveViewTests`).

---

### Q2 — Polymorphic owner (Laboratory, Groupement, Pharmacy)

**What to prove:** trees owned by different entity types appear in one aggregated pharmacy view.

```bash
curl -b cookies.txt http://localhost:8000/api/v1/entities/tree/
```

Expect roots/names from three owners:

| Name | Owner type | `is_owned` | `is_shared` |
|------|------------|------------|-------------|
| `Meus documentos` | pharmacy | `true` | `false` |
| `CPC` | groupement | `false` | `true` |
| `Nuxe` | laboratory | `false` | `true` |

Shared roots should include `shared_by.entity_type` (`groupement` or `laboratory`).

---

### Q3 — Sharing model (`NodeShare`, explicit + groupement_all)

**What to prove:** groupement share reaches all member pharmacies; lab share is explicit; descendants inherit access without extra share rows.

1. **Groupement_all (CPC)** — as Farmácia Central, `/children/` on `cpc_root_id` works (step Q1). Bind **Farmácia Norte** (another CPC member) and repeat:

```bash
curl -c cookies.txt -X POST http://localhost:8000/api/v1/session/entity/ \
  -H "Content-Type: application/json" \
  -d '{"entity_type": "pharmacy", "entity_id": 2}'

curl -b cookies.txt "http://localhost:8000/api/v1/tree-nodes/$CPC_ROOT_ID/children/"
```

Expect the same two folders without creating a new share.

2. **Explicit lab share (Nuxe → Farmácia Central only)** — Central sees `Nuxe` in bootstrap; bind a pharmacy **outside** CPC membership (create via admin or DB) and confirm `403` with `"Entity does not have permission"` on Nuxe children.

3. **Create share** — groupement shares a new folder with one pharmacy:

```bash
curl -b cookies.txt -X POST "http://localhost:8000/api/v1/tree-nodes/$FOLDER_ID/shares/" \
  -H "Content-Type: application/json" \
  -d '{
    "sharer_type": "groupement",
    "sharer_id": 1,
    "scope": "explicit",
    "target": {"entity_type": "pharmacy", "entity_id": 1}
  }'
```

4. **Share validation** — groupement cannot share with a pharmacy outside its membership (`400`). Covered by `TreeNodeShareViewTests`.

5. **Full subtree (test helper)** — optional deep view:

```bash
curl -b cookies.txt "http://localhost:8000/api/v1/test/tree-nodes/$CPC_ROOT_ID/subtree/"
```

Expect nested `children` down to `Condições gerais` and `Flyer Solares`.

---

### Q4 — Content polymorphism (Document, Flyer, CommercialCondition)

**What to prove:** leaf nodes resolve to typed payloads with signed file URLs where applicable.

```bash
# Commercial condition (shared CPC leaf)
curl -b cookies.txt "http://localhost:8000/api/v1/tree-nodes/$CONDITIONS_LEAF_ID/content/"
# Expect: "content_type": "commercialcondition", "name": "Condições gerais"

# Document (owned pharmacy leaf)
curl -b cookies.txt "http://localhost:8000/api/v1/tree-nodes/$VAT_LEAF_ID/content/"
# Expect: "content_type": "document", "file_url" contains "sig="

# Flyer
curl -b cookies.txt "http://localhost:8000/api/v1/tree-nodes/$FLYER_LEAF_ID/content/"
# Expect: "content_type": "flyer", "image_url" contains "sig="

# Folder returns 400
curl -b cookies.txt "http://localhost:8000/api/v1/tree-nodes/$CPC_ROOT_ID/content/"
```

---

### Q5 — Extensibility (new content types without TreeNode migration)

**What to prove:** adding a type (e.g. `Contract`) is an allowlist + serializer change, not a schema migration on `TreeNode`.

1. Inspect [`document_tree/validators.py`](document_tree/validators.py) — `ALLOWED_CONTENT_MODELS` and `validate_content_type`.
2. Inspect [`document_tree/serializers.py`](document_tree/serializers.py) — `CONTENT_SERIALIZERS` registry.
3. Confirm `TreeNode` uses generic `content_content_type` / `content_object_id` only ([`document_tree/models.py`](document_tree/models.py)) — no per-type FK columns.

No HTTP step required; this is a code-structure check aligned with the ADR.

---

### Q6 — Permissions and integrity (session auth, owner-only writes, soft delete)

**What to prove:** reads require session; unauthorized entity access gets `403` (`Entity does not have permission`); unknown nodes get `404`; mutations require owner context; deleted nodes are hidden.

1. **Session required** — clear cookie jar and call tree without binding:

```bash
rm -f cookies.txt
curl -c cookies.txt http://localhost:8000/api/v1/entities/tree/
# Expect: 401 Unauthorized

curl -c cookies.txt -X POST http://localhost:8000/api/v1/session/entity/ \
  -H "Content-Type: application/json" \
  -d '{"entity_type": "pharmacy", "entity_id": 99999}'
# Expect: 400 (unknown entity)
```

2. **Access control** — bind a pharmacy with no shares and request CPC children → `403` with `"Entity does not have permission"`.

3. **Owner-only move** — PATCH move with wrong `owner_type` / `owner_id` → `400` “Only the node owner can move”.

4. **Soft delete** — `TreeNode` default manager excludes `deleted_at` set rows ([`TreeNodeManager.alive`](document_tree/models.py)). Restore/delete API is out of PoC scope; verify via Django admin or shell if needed.

---

### Q7 — Aggregated view (bootstrap: roots + first level only)

**What to prove:** initial load is shallow; deeper nodes require `/children/`.

```bash
curl -b cookies.txt http://localhost:8000/api/v1/entities/tree/
```

**Included** (first level under each root):

- Own: `Meus documentos`, `Declaração IVA` (child of Meus documentos)
- Shared CPC: `CPC`, `Condições 2025`, `Flyers do agrupamento`
- Shared Nuxe: `Nuxe`, `Operação primavera`

**Excluded** (load via `/children/` instead):

- `Condições gerais`, `Flyer Solares`, `Brief de produto`

Confirm `CPC` has `"parent_id": null` and `"is_shared": true` even though groupement-owned.

---

### Q8 — API design (flat list, metadata, breadcrumb, ordering)

**What to prove:** flat JSON with `parent_id`; `is_owned` / `is_shared` / `shared_by`; siblings sorted by name; breadcrumb for navigation.

1. **Flat list** — bootstrap response is an array of objects with `parent_id`, not nested `children`.

2. **Breadcrumb** — path to a deep shared leaf:

```bash
curl -b cookies.txt "http://localhost:8000/api/v1/tree-nodes/$CONDITIONS_LEAF_ID/breadcrumb/"
```

Expect ordered names: `CPC` → `Condições 2025` → `Condições gerais`.

3. **Sibling ordering** — CPC children (Q1) return `Condições 2025` before `Flyers do agrupamento` (ASCII alphabetical by `name`).

4. **Read-only shared metadata** — shared nodes have `"is_owned": false`, `"is_shared": true`, and populated `shared_by`.

---

## Quick reference — seed node names (PDF example)

| Node | Owner |
|------|-------|
| Meus documentos → Declaração IVA | Farmácia Central |
| CPC → Condições 2025 → Condições gerais | CPC (groupement) |
| CPC → Flyers do agrupamento → Flyer Solares | CPC (groupement) |
| Nuxe → Operação primavera → Brief de produto | Nuxe (laboratory, shared to Central) |

Shares: CPC root → `groupement_all`; Nuxe root → explicit to Farmácia Central.

---

## Phase 2 — automated test mapping

Each README validation step has a corresponding test (run via `python manage.py test`).

| README section | Scenario | Test(s) |
|----------------|----------|---------|
| **0 Bootstrap** | Seed PDF data | `SeedAssessmentDataTests` |
| | Entity list pagination | `ValidationEntityListTests` |
| | Session bind / invalid entity / clear | `EntitySessionViewTests` |
| **Q1 Tree** | Lazy children | `test_list_children_of_shared_folder` |
| | Drill-down grandchildren | `test_list_grandchildren_of_shared_folder` |
| | Move node | `test_move_node`, `test_move_then_visible_under_new_parent` |
| | Cycle rejected | `test_move_into_descendant_rejected` |
| **Q2 Owner** | Mixed owners + metadata | `test_aggregated_view_includes_own_and_shared_first_level` |
| **Q3 Sharing** | `groupement_all` member access | `test_groupement_all_member_can_list_cpc_children`, `test_groupement_all_grants_new_pharmacy_access` |
| | Explicit share denied | `test_explicit_lab_share_denied_for_non_recipient`, `test_children_not_accessible_returns_403` |
| | Create share | `test_create_explicit_share` |
| | Share validation | `test_groupement_cannot_share_with_foreign_pharmacy` |
| | Full subtree | `TestTreeNodeSubtreeTests.test_subtree_returns_nested_descendants` |
| **Q4 Content** | Commercial condition | `test_resolve_leaf_content` |
| | Document + signed URL | `test_resolve_document_leaf_includes_signed_url` |
| | Flyer + signed URL | `test_resolve_flyer_leaf_includes_signed_url` |
| | Folder rejected | `test_resolve_folder_returns_400` |
| **Q5 Extensibility** | Content allowlist | `ValidatorUnitTests` |
| **Q6 Permissions** | Session required (401) | `test_aggregated_view_without_session_returns_401`, `test_children_requires_session` |
| | Access denied (403) | `test_children_not_accessible_returns_403`, `test_subtree_not_accessible_returns_403` |
| | Owner-only move | `test_move_rejected_for_non_owner` |
| | Soft delete hidden | `test_soft_deleted_nodes_hidden_from_default_manager` |
| **Q7 Aggregated** | Shallow bootstrap | `test_aggregated_view_includes_own_and_shared_first_level` |
| **Q8 API** | Flat list | `test_aggregated_view_is_flat_list_without_nested_children` |
| | Breadcrumb | `test_breadcrumb_path` |
| | Alphabetical siblings | `test_children_sorted_alphabetically` |
| | Shared metadata | `test_aggregated_view_includes_own_and_shared_first_level` |
