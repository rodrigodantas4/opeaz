import io
from datetime import date

from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import CommercialCondition, Document, Flyer, Groupement, Laboratory, Pharmacy
from document_tree.models import NodeType, ShareScope, TreeNode
from document_tree.services import ShareService, TreeService
from document_tree.test_utils import bind_entity_session


def ct_for(model):
    return ContentType.objects.get_for_model(model)


def make_folder(name, owner, parent=None):
    ct = ct_for(owner.__class__)
    return TreeNode.objects.create(
        name=name,
        node_type=NodeType.FOLDER,
        parent=parent,
        owner_content_type=ct,
        owner_object_id=owner.pk,
    )


def make_leaf(name, owner, content_obj, parent=None):
    content_ct = ct_for(content_obj.__class__)
    owner_ct = ct_for(owner.__class__)
    return TreeNode.objects.create(
        name=name,
        node_type=NodeType.LEAF,
        parent=parent,
        owner_content_type=owner_ct,
        owner_object_id=owner.pk,
        content_content_type=content_ct,
        content_object_id=content_obj.pk,
    )


class AssessmentFixtureMixin:
    def setUp(self):
        self.groupement = Groupement.objects.create(name='CPC')
        self.pharmacy = Pharmacy.objects.create(name='Pharmacy 7', groupement=self.groupement)
        self.lab = Laboratory.objects.create(name='Nuxe', code='NUXE')

        self.doc = Document.objects.create(
            laboratory=self.lab,
            name='VAT declaration',
            file=SimpleUploadedFile('vat.pdf', b'pdf-content'),
        )
        self.flyer = Flyer.objects.create(
            laboratory=self.lab,
            title='Solar flyer',
            image=SimpleUploadedFile('flyer.jpg', b'jpg-content'),
            start_at=date(2025, 6, 1),
            end_at=date(2025, 8, 31),
        )
        self.condition = CommercialCondition.objects.create(
            laboratory=self.lab,
            name='General conditions',
            text='Terms...',
            year=2025,
        )
        self.product_brief = Document.objects.create(
            laboratory=self.lab,
            name='Product brief',
            file=SimpleUploadedFile('brief.pdf', b'brief'),
        )

        # Pharmacy own tree
        self.my_docs = make_folder('My documents', self.pharmacy)
        self.vat_leaf = make_leaf('VAT declaration', self.pharmacy, self.doc, parent=self.my_docs)

        # Groupement tree shared with all pharmacies
        self.cpc_root = make_folder('CPC', self.groupement)
        self.conditions_folder = make_folder('Conditions 2025', self.groupement, parent=self.cpc_root)
        self.conditions_leaf = make_leaf(
            'General conditions', self.groupement, self.condition, parent=self.conditions_folder,
        )
        self.flyers_folder = make_folder('Groupement flyers', self.groupement, parent=self.cpc_root)
        self.flyer_leaf = make_leaf('Solar flyer', self.groupement, self.flyer, parent=self.flyers_folder)

        ShareService.create_share(
            self.groupement, self.cpc_root, ShareScope.GROUPEMENT_ALL, groupement=self.groupement,
        )

        # Lab tree shared with pharmacy
        self.nuxe_root = make_folder('Nuxe', self.lab)
        self.spring_folder = make_folder('Spring operation', self.lab, parent=self.nuxe_root)
        self.brief_leaf = make_leaf('Product brief', self.lab, self.product_brief, parent=self.spring_folder)

        ShareService.create_share(
            self.lab, self.nuxe_root, ShareScope.EXPLICIT, target=self.pharmacy,
        )

        bind_entity_session(self.client, self.pharmacy)


class EntitySessionViewTests(APITestCase):
    def test_post_session_binds_entity(self):
        pharmacy = Pharmacy.objects.create(name='Test pharmacy')
        response = self.client.post(
            reverse('entity-session'),
            {'entity_type': 'pharmacy', 'entity_id': pharmacy.pk},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.client.session['entity_type'], 'pharmacy')
        self.assertEqual(self.client.session['entity_id'], pharmacy.pk)

    def test_post_session_invalid_entity_returns_400(self):
        response = self.client.post(
            reverse('entity-session'),
            {'entity_type': 'pharmacy', 'entity_id': 99999},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_delete_session_clears_entity(self):
        pharmacy = Pharmacy.objects.create(name='Test pharmacy')
        self.client.post(
            reverse('entity-session'),
            {'entity_type': 'pharmacy', 'entity_id': pharmacy.pk},
            format='json',
        )
        response = self.client.delete(reverse('entity-session'))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertNotIn('entity_type', self.client.session)


class EntityTreeViewTests(AssessmentFixtureMixin, APITestCase):
    def test_aggregated_view_includes_own_and_shared_first_level(self):
        url = reverse('entity-tree')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = {item['name'] for item in response.data}
        self.assertIn('My documents', names)
        self.assertIn('VAT declaration', names)
        self.assertIn('CPC', names)
        self.assertIn('Conditions 2025', names)
        self.assertIn('Groupement flyers', names)
        self.assertIn('Nuxe', names)
        self.assertNotIn('General conditions', names)
        self.assertNotIn('Product brief', names)

        cpc = next(item for item in response.data if item['name'] == 'CPC')
        self.assertTrue(cpc['is_shared'])
        self.assertIsNone(cpc['parent_id'])
        self.assertEqual(cpc['shared_by']['entity_type'], 'groupement')

    def test_aggregated_view_without_session_returns_401(self):
        session = self.client.session
        session.pop('entity_type', None)
        session.pop('entity_id', None)
        session.save()
        response = self.client.get(reverse('entity-tree'))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class TreeNodeChildrenViewTests(AssessmentFixtureMixin, APITestCase):
    def test_list_children_of_shared_folder(self):
        url = reverse('tree-node-children', kwargs={'node_id': self.cpc_root.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = {item['name'] for item in response.data}
        self.assertEqual(names, {'Conditions 2025', 'Groupement flyers'})

    def test_children_requires_session(self):
        session = self.client.session
        session.pop('entity_type', None)
        session.pop('entity_id', None)
        session.save()
        url = reverse('tree-node-children', kwargs={'node_id': self.cpc_root.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_children_not_accessible_returns_404(self):
        other_pharmacy = Pharmacy.objects.create(name='Other', groupement=None)
        bind_entity_session(self.client, other_pharmacy)
        url = reverse('tree-node-children', kwargs={'node_id': self.cpc_root.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class TreeNodeContentViewTests(AssessmentFixtureMixin, APITestCase):
    def test_resolve_leaf_content(self):
        url = reverse('tree-node-content', kwargs={'node_id': self.conditions_leaf.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['content_type'], 'commercialcondition')
        self.assertEqual(response.data['name'], 'General conditions')

    def test_resolve_document_leaf_includes_signed_url(self):
        url = reverse('tree-node-content', kwargs={'node_id': self.vat_leaf.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('sig=', response.data['file_url'])

    def test_resolve_folder_returns_400(self):
        url = reverse('tree-node-content', kwargs={'node_id': self.cpc_root.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TreeNodeShareViewTests(AssessmentFixtureMixin, APITestCase):
    def test_create_explicit_share(self):
        folder = make_folder('Lab share', self.lab)
        url = reverse('tree-node-shares', kwargs={'node_id': folder.pk})
        response = self.client.post(url, {
            'sharer_type': 'laboratory',
            'sharer_id': self.lab.pk,
            'scope': ShareScope.EXPLICIT,
            'target': {'entity_type': 'pharmacy', 'entity_id': self.pharmacy.pk},
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_groupement_cannot_share_with_foreign_pharmacy(self):
        foreign = Pharmacy.objects.create(name='Foreign', groupement=None)
        folder = make_folder('Groupement only', self.groupement)
        url = reverse('tree-node-shares', kwargs={'node_id': folder.pk})
        response = self.client.post(url, {
            'sharer_type': 'groupement',
            'sharer_id': self.groupement.pk,
            'scope': ShareScope.EXPLICIT,
            'target': {'entity_type': 'pharmacy', 'entity_id': foreign.pk},
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TreeNodeBreadcrumbViewTests(AssessmentFixtureMixin, APITestCase):
    def test_breadcrumb_path(self):
        url = reverse('tree-node-breadcrumb', kwargs={'node_id': self.conditions_leaf.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item['name'] for item in response.data], ['CPC', 'Conditions 2025', 'General conditions'])


class TreeNodeMoveViewTests(AssessmentFixtureMixin, APITestCase):
    def test_move_node(self):
        folder = make_folder('Movable', self.pharmacy)
        leaf = make_leaf('Child', self.pharmacy, self.doc, parent=folder)
        url = reverse('tree-node-move', kwargs={'node_id': leaf.pk})
        response = self.client.patch(url, {
            'owner_type': 'pharmacy',
            'owner_id': self.pharmacy.pk,
            'parent_id': self.my_docs.pk,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        leaf.refresh_from_db()
        self.assertEqual(leaf.parent_id, self.my_docs.pk)

    def test_move_into_descendant_rejected(self):
        parent = make_folder('Parent', self.pharmacy)
        child = make_folder('Child', self.pharmacy, parent=parent)
        url = reverse('tree-node-move', kwargs={'node_id': parent.pk})
        response = self.client.patch(url, {
            'owner_type': 'pharmacy',
            'owner_id': self.pharmacy.pk,
            'parent_id': child.pk,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TreeServiceUnitTests(AssessmentFixtureMixin, TestCase):
    def test_can_entity_access_shared_descendant(self):
        self.assertTrue(TreeService.can_entity_access_node(self.conditions_leaf, self.pharmacy))

    def test_groupement_all_grants_new_pharmacy_access(self):
        new_pharmacy = Pharmacy.objects.create(name='New member', groupement=self.groupement)
        self.assertTrue(TreeService.can_entity_access_node(self.cpc_root, new_pharmacy))
