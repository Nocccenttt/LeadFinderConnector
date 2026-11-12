import json
import tempfile
import unittest
from pathlib import Path

from design_comparison import compare_sites


def site(root, name, gap, reverse=False):
    folder = root/name
    website = folder/'website'
    website.mkdir(parents=True)
    (folder/'business.json').write_text(json.dumps({'business_name':name}))
    (website/'index.html').write_text(f'<main><h1>{name}</h1><p>Discuss your project and confirm the next steps before making arrangements.</p></main>')
    children = [{'slot':'title'},{'slot':'image'}]
    if reverse:
        children.reverse()
    (website/'design_spec.json').write_text(json.dumps({'page_blueprint':{'sections':[
        {'key':'hero','reference_section':gap,'layout':{'type':'grid','columns':[1,1],'gap':gap,'children':children}},
        {'key':'cta','layout':{'type':'stack','children':[{'slot':'title'},{'slot':'actions'}]}}]}}))
    return folder


class ComparisonTests(unittest.TestCase):
    def test_extra_stack_wrappers_do_not_create_a_unique_opening(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            left=site(root,'Alpha',24)
            right=site(root,'Beta',24)
            path=right/'website/design_spec.json'
            design=json.loads(path.read_text())
            design['page_blueprint']['sections'][0]['layout']={'type':'stack','children':[{'slot':'eyebrow'},{'slot':'title'},{'slot':'image'}]}
            path.write_text(json.dumps(design))
            path=left/'website/design_spec.json'
            design=json.loads(path.read_text())
            design['page_blueprint']['sections'][0]['layout']={'type':'stack','children':[{'type':'stack','children':[{'slot':'title'}]},{'slot':'image'}]}
            path.write_text(json.dumps(design))
            report=compare_sites([left,right])
        self.assertEqual(report['distinct_hero_family_count'],1)
        self.assertTrue(report['pairs'][0]['same_hero_family'])

    def test_names_and_cosmetic_changes_do_not_count_as_unique(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report = compare_sites([site(root,'Alpha',24),site(root,'Beta',72)])
        self.assertEqual(report['distinct_structure_count'],1)
        self.assertTrue(report['pairs'][0]['same_copy_after_identity_mask'])
        self.assertEqual(report['pairs_requiring_review'],1)

    def test_image_reordering_changes_structure_even_when_copy_is_the_same(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report = compare_sites([site(root,'Alpha',24),site(root,'Beta',24,True)])
        self.assertEqual(report['distinct_structure_count'],2)
        self.assertFalse(report['pairs'][0]['same_structure'])
        self.assertTrue(report['pairs'][0]['same_copy_after_identity_mask'])
        self.assertTrue(report['pairs'][0]['review_repetition'])
