"""Assessment reference data — mirrors the Document Tree technical test PDF example."""

import shutil
from datetime import date

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.db import transaction

from core.models import CommercialCondition, Document, Flyer, Groupement, Laboratory, Pharmacy
from document_tree.models import NodeShare, NodeType, ShareScope, TreeNode
from document_tree.services import ShareService


def _ct(model):
    return ContentType.objects.get_for_model(model)


def _folder(name, owner, parent=None):
    ct = _ct(owner.__class__)
    return TreeNode.objects.create(
        name=name,
        node_type=NodeType.FOLDER,
        parent=parent,
        owner_content_type=ct,
        owner_object_id=owner.pk,
    )


def _leaf(name, owner, content_obj, parent=None):
    return TreeNode.objects.create(
        name=name,
        node_type=NodeType.LEAF,
        parent=parent,
        owner_content_type=_ct(owner.__class__),
        owner_object_id=owner.pk,
        content_content_type=_ct(content_obj.__class__),
        content_object_id=content_obj.pk,
    )


def _delete_file_fields(queryset, *field_names):
    for obj in queryset.iterator():
        for field_name in field_names:
            field_file = getattr(obj, field_name, None)
            if field_file:
                field_file.delete(save=False)


def _assessment_row_counts():
    return {
        'groupements': Groupement.objects.count(),
        'pharmacies': Pharmacy.objects.count(),
        'laboratories': Laboratory.objects.count(),
        'tree_nodes': TreeNode.all_objects.count(),
        'node_shares': NodeShare.objects.count(),
        'documents': Document.objects.count(),
        'flyers': Flyer.objects.count(),
        'commercial_conditions': CommercialCondition.objects.count(),
    }


def _clear_assessment_media():
    for subdir in ('documents', 'flyers'):
        path = settings.MEDIA_ROOT / subdir
        if path.is_dir():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)


def _clear_assessment_data_in_transaction():
    """TODO(test-validation): wipe seeded data before reload."""
    NodeShare.objects.all().delete()
    TreeNode.all_objects.update(parent=None)
    TreeNode.all_objects.all().delete()

    for model, file_fields in (
        (CommercialCondition, ()),
        (Flyer, ('image',)),
        (Document, ('file',)),
    ):
        qs = model.objects.all()
        if file_fields:
            _delete_file_fields(qs, *file_fields)
        qs.delete()

    Pharmacy.objects.all().delete()
    Groupement.objects.all().delete()
    Laboratory.objects.all().delete()
    _clear_assessment_media()


def _clear_assessment_data():
    """TODO(test-validation): wipe seeded data and uploaded media before reload."""
    with transaction.atomic():
        _clear_assessment_data_in_transaction()


def _create_assessment_data():
    # --- Entities (PDF context: CPC groupement, Nuxe/Bioderma labs, member pharmacies) ---
    groupement_cpc = Groupement.objects.create(name='CPC')
    lab_nuxe = Laboratory.objects.create(name='Nuxe', code='NUXE')
    Laboratory.objects.create(name='Bioderma', code='BIODERMA')

    pharmacy_central = Pharmacy.objects.create(name='Farmácia Central', groupement=groupement_cpc)
    Pharmacy.objects.create(name='Farmácia Norte', groupement=groupement_cpc)
    Pharmacy.objects.create(name='Farmácia Sul', groupement=groupement_cpc)

    # --- Business content (laboratory-owned document objects) ---
    doc_vat = Document.objects.create(
        laboratory=lab_nuxe,
        name='Declaração IVA',
        file=ContentFile(b'vat-declaration-content', name='declaracao-iva.pdf'),
    )
    doc_brief = Document.objects.create(
        laboratory=lab_nuxe,
        name='Brief de produto',
        file=ContentFile(b'product-brief-content', name='brief-produto.pdf'),
    )
    flyer_solar = Flyer.objects.create(
        laboratory=lab_nuxe,
        title='Flyer Solares',
        image=ContentFile(b'flyer-solares-image', name='flyer-solares.jpg'),
        start_at=date(2025, 6, 1),
        end_at=date(2025, 8, 31),
    )
    condition_general = CommercialCondition.objects.create(
        laboratory=lab_nuxe,
        name='Condições gerais',
        text='Condições comerciais gerais 2025.',
        year=2025,
    )

    # --- Pharmacy own tree: Meus documentos → Declaração IVA ---
    my_documents = _folder('Meus documentos', pharmacy_central)
    vat_leaf = _leaf('Declaração IVA', pharmacy_central, doc_vat, parent=my_documents)

    # --- Groupement tree: CPC → Condições 2025 / Flyers do agrupamento ---
    cpc_root = _folder('CPC', groupement_cpc)
    conditions_2025 = _folder('Condições 2025', groupement_cpc, parent=cpc_root)
    conditions_leaf = _leaf('Condições gerais', groupement_cpc, condition_general, parent=conditions_2025)
    flyers_folder = _folder('Flyers do agrupamento', groupement_cpc, parent=cpc_root)
    flyer_leaf = _leaf('Flyer Solares', groupement_cpc, flyer_solar, parent=flyers_folder)

    share_cpc_all = ShareService.create_share(
        groupement_cpc, cpc_root, ShareScope.GROUPEMENT_ALL, groupement=groupement_cpc,
    )

    # --- Laboratory tree: Nuxe → Operação primavera → Brief de produto ---
    nuxe_root = _folder('Nuxe', lab_nuxe)
    spring_op = _folder('Operação primavera', lab_nuxe, parent=nuxe_root)
    brief_leaf = _leaf('Brief de produto', lab_nuxe, doc_brief, parent=spring_op)

    share_nuxe_pharmacy = ShareService.create_share(
        lab_nuxe, nuxe_root, ShareScope.EXPLICIT, target=pharmacy_central,
    )

    return {
        'groupements': [{'id': groupement_cpc.pk, 'name': groupement_cpc.name}],
        'laboratories': [
            {'id': lab_nuxe.pk, 'name': lab_nuxe.name, 'code': lab_nuxe.code},
            {'id': Laboratory.objects.get(code='BIODERMA').pk, 'name': 'Bioderma', 'code': 'BIODERMA'},
        ],
        'pharmacies': [
            {'id': p.pk, 'name': p.name, 'groupement_id': p.groupement_id}
            for p in Pharmacy.objects.order_by('name')
        ],
        'primary_pharmacy_id': pharmacy_central.pk,
        'tree_preview_url': '/api/v1/entities/tree/',
        'nodes': {
            'my_documents_id': my_documents.pk,
            'vat_leaf_id': vat_leaf.pk,
            'cpc_root_id': cpc_root.pk,
            'conditions_2025_id': conditions_2025.pk,
            'conditions_leaf_id': conditions_leaf.pk,
            'flyers_folder_id': flyers_folder.pk,
            'flyer_leaf_id': flyer_leaf.pk,
            'nuxe_root_id': nuxe_root.pk,
            'spring_operation_id': spring_op.pk,
            'brief_leaf_id': brief_leaf.pk,
        },
        'shares': {
            'cpc_groupement_all_id': share_cpc_all.pk,
            'nuxe_pharmacy_id': share_nuxe_pharmacy.pk,
        },
        'content': {
            'document_vat_id': doc_vat.pk,
            'document_brief_id': doc_brief.pk,
            'flyer_solar_id': flyer_solar.pk,
            'commercial_condition_id': condition_general.pk,
        },
    }


def seed_assessment_data(*, reset: bool = True) -> dict:
    """
    Load labs, groupements, pharmacies and document trees from the assessment PDF example.

    TODO(test-validation): for PoC / manual API testing only — remove before production.
    """
    cleared_before = None
    if reset:
        cleared_before = _assessment_row_counts()
        _clear_assessment_data()

    with transaction.atomic():
        payload = _create_assessment_data()

    payload['reset'] = reset
    if cleared_before is not None:
        payload['cleared_before'] = cleared_before
    return payload
