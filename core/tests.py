from django.urls import reverse

from rest_framework import status

from rest_framework.test import APITestCase


from document_tree.test_utils import bind_entity_session

from document_tree.tests import AssessmentFixtureMixin



from document_tree.models import NodeShare, TreeNode

from .models import Document, Groupement, Laboratory, Pharmacy

from .seed import seed_assessment_data





class TestTreeNodeSubtreeTests(AssessmentFixtureMixin, APITestCase):

    def test_subtree_returns_nested_descendants(self):

        url = reverse('test-tree-node-subtree', kwargs={'node_id': self.cpc_root.pk})

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(response.data['name'], 'CPC')

        self.assertTrue(response.data['is_shared'])



        child_names = {child['name'] for child in response.data['children']}

        self.assertEqual(child_names, {'Conditions 2025', 'Groupement flyers'})



        conditions = next(c for c in response.data['children'] if c['name'] == 'Conditions 2025')

        self.assertEqual(len(conditions['children']), 1)

        self.assertEqual(conditions['children'][0]['name'], 'General conditions')

        self.assertEqual(conditions['children'][0]['children'], [])

        flyers = next(c for c in response.data['children'] if c['name'] == 'Groupement flyers')
        self.assertEqual(flyers['children'][0]['name'], 'Solar flyer')

    def test_subtree_requires_session(self):
        session = self.client.session
        session.pop('entity_type', None)
        session.pop('entity_id', None)
        session.save()
        url = reverse('test-tree-node-subtree', kwargs={'node_id': self.cpc_root.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)



    def test_subtree_not_accessible_returns_403(self):
        other_pharmacy = Pharmacy.objects.create(name='Other', groupement=None)
        bind_entity_session(self.client, other_pharmacy)
        url = reverse('test-tree-node-subtree', kwargs={'node_id': self.cpc_root.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['detail'], 'Entity does not have permission')





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
        self.assertTrue(response.data['reset'])
        self.assertIn('cleared_before', response.data)



    def test_seed_module_idempotent_with_reset(self):
        seed_assessment_data(reset=True)
        self.assertEqual(Laboratory.objects.filter(code='NUXE').count(), 1)
        self.assertEqual(TreeNode.all_objects.count(), 10)
        self.assertEqual(NodeShare.objects.count(), 2)

        seed_assessment_data(reset=True)
        self.assertEqual(Laboratory.objects.filter(code='NUXE').count(), 1)
        self.assertEqual(Groupement.objects.count(), 1)
        self.assertEqual(TreeNode.all_objects.count(), 10)
        self.assertEqual(NodeShare.objects.count(), 2)

    def test_clear_assessment_data_removes_extra_rows(self):
        seed_assessment_data(reset=True)
        Groupement.objects.create(name='Leftover')
        self.assertEqual(Groupement.objects.count(), 2)

        from core.seed import _clear_assessment_data
        _clear_assessment_data()

        self.assertEqual(Groupement.objects.count(), 0)
        self.assertEqual(Pharmacy.objects.count(), 0)
        self.assertEqual(Laboratory.objects.count(), 0)
        self.assertEqual(TreeNode.all_objects.count(), 0)
        self.assertEqual(NodeShare.objects.count(), 0)
        self.assertEqual(Document.objects.count(), 0)

    def test_seed_reset_clears_session_and_reports_cleared_counts(self):
        seed_assessment_data(reset=True)
        session = self.client.session
        session['entity_type'] = 'pharmacy'
        session['entity_id'] = 999
        session.save()

        response = self.client.post(reverse('test-seed-assessment'))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['reset'])
        self.assertGreater(response.data['cleared_before']['tree_nodes'], 0)
        self.assertNotIn('entity_type', self.client.session)
        self.assertNotIn('entity_id', self.client.session)


