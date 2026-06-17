from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Groupement, Laboratory, Pharmacy
from .seed import seed_assessment_data


from document_tree.tests import AssessmentFixtureMixin


class TestTreeNodeSubtreeTests(AssessmentFixtureMixin, APITestCase):
    def test_subtree_returns_nested_descendants(self):
        url = reverse('test-tree-node-subtree', kwargs={'node_id': self.cpc_root.pk})
        response = self.client.get(url, {'entity_type': 'pharmacy', 'entity_id': self.pharmacy.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'CPC')
        self.assertTrue(response.data['is_shared'])

        child_names = {child['name'] for child in response.data['children']}
        self.assertEqual(child_names, {'Conditions 2025', 'Groupement flyers'})

        conditions = next(c for c in response.data['children'] if c['name'] == 'Conditions 2025')
        self.assertEqual(len(conditions['children']), 1)
        self.assertEqual(conditions['children'][0]['name'], 'General conditions')
        self.assertEqual(conditions['children'][0]['children'], [])

    def test_subtree_requires_entity_context(self):
        url = reverse('test-tree-node-subtree', kwargs={'node_id': self.cpc_root.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_subtree_not_accessible_returns_404(self):
        other_pharmacy = Pharmacy.objects.create(name='Other', groupement=None)
        url = reverse('test-tree-node-subtree', kwargs={'node_id': self.cpc_root.pk})
        response = self.client.get(url, {'entity_type': 'pharmacy', 'entity_id': other_pharmacy.pk})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class ValidationEntityListTests(APITestCase):
    def setUp(self):
        self.groupement = Groupement.objects.create(name='CPC')
        self.pharmacy = Pharmacy.objects.create(name='Pharmacy 7', groupement=self.groupement)
        self.lab = Laboratory.objects.create(name='Nuxe', code='NUXE')

    def test_list_laboratories(self):
        response = self.client.get(reverse('test-laboratory-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['code'], 'NUXE')

    def test_list_groupements(self):
        response = self.client.get(reverse('test-groupement-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results'][0]['name'], 'CPC')

    def test_list_pharmacies(self):
        response = self.client.get(reverse('test-pharmacy-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results'][0]['groupement_id'], self.groupement.pk)

    def test_pagination_page_size_capped_at_50(self):
        for i in range(55):
            Laboratory.objects.create(name=f'Lab {i}', code=f'LAB{i:03d}')
        response = self.client.get(reverse('test-laboratory-list'), {'page_size': 100})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertLessEqual(len(response.data['results']), 50)


class SeedAssessmentDataTests(APITestCase):
    def test_seed_endpoint_loads_pdf_example(self):
        response = self.client.post(reverse('test-seed-assessment'))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Groupement.objects.count(), 1)
        self.assertEqual(Laboratory.objects.count(), 2)
        self.assertEqual(Pharmacy.objects.count(), 3)
        self.assertEqual(response.data['groupements'][0]['name'], 'CPC')
        self.assertIn('tree_preview_url', response.data)
        self.assertIn('cpc_root_id', response.data['nodes'])

    def test_seed_module_idempotent_with_reset(self):
        seed_assessment_data(reset=True)
        self.assertEqual(Laboratory.objects.filter(code='NUXE').count(), 1)
        seed_assessment_data(reset=True)
        self.assertEqual(Laboratory.objects.filter(code='NUXE').count(), 1)
        self.assertEqual(Groupement.objects.count(), 1)
