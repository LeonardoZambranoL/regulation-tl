import sqlite3
import unittest
from build import segments
from corpus import audit


class SourceSegmentationTests(unittest.TestCase):
    def test_temperature_continuation_is_not_a_new_clause(self):
        blocks=segments(['Annex 6 Environmental Testing\nPart 1 - Resistance to heat\n1. Expose the sample at 65 °C ±\n2 °C for 48 hours.\n2. Inspect the sample.'])
        self.assertEqual([b['paragraph'] for b in blocks],['Annex 6','Annex 6 Part 1','Annex 6 Part 1 1','Annex 6 Part 1 2'])
        self.assertIn('2 °C for 48 hours.',blocks[2]['text'])

    def test_cross_page_continuation_retains_origin(self):
        blocks=segments(['4.1. The device shall withstand\nUN R1, version 1.0 | page 1 of 2','the prescribed test.\n4.2. The device shall remain visible.'])
        self.assertEqual((blocks[0]['page_start'],blocks[0]['page_end']),(1,2))
        self.assertIn('the prescribed test.',blocks[0]['text'])
        self.assertNotIn('page 1 of 2',blocks[0]['text'])

    def test_annex_reference_does_not_reset_context(self):
        blocks=segments(['Annex 4 Measurements\nPart 1 - Photometry\n1.2. Refer to\nAnnex 5 of this Regulation, for the required shape.\n1.3. Continue.\nPart 2 - Colour\n1.1. Use the illuminant.'])
        self.assertEqual(blocks[3]['paragraph'],'Annex 4 Part 1 1.3')
        self.assertEqual(blocks[-1]['paragraph'],'Annex 4 Part 2 1.1')

    def test_coverage_cannot_pass_without_review_or_provenance(self):
        c=sqlite3.connect(':memory:');c.row_factory=sqlite3.Row
        c.executescript('CREATE TABLE documents(document_id,regulation,version,role,pdf_path,page_count); CREATE TABLE clauses(clause_id,document_id,paragraph,kind,page_start,page_end); CREATE TABLE candidates(candidate_id,clause_id);')
        c.execute("INSERT INTO documents VALUES ('d','UN R1','1.0','base','source.pdf',2)")
        c.execute("INSERT INTO clauses VALUES ('c','d','1.1','clause',1,1)")
        c.execute("INSERT INTO candidates VALUES ('o','c')")
        submission={'requirements':[{'id':'R-1','source':{'regulation':'UN R1','version':'1.0','page':1}}]}
        scope=[{'regulation':'UN R1','decision':'primary','reason':'Applicable device.'}]
        bad=audit(c,submission,[],scope)
        self.assertFalse(bad['passed']);self.assertEqual(bad['missing_candidate_ids'],['o'])
        good=audit(c,submission,[{'candidate_id':'o','decision':'included','requirement_ids':['R-1'],'reason':'Same device obligation.'}],scope)
        self.assertTrue(good['passed'])
        c.execute("INSERT INTO documents VALUES ('later','UN R1','2.0','latest','later.pdf',3)")
        submission['requirements'][0]['source']['version']='2.0'
        mixed=audit(c,submission,[{'candidate_id':'o','decision':'included','requirement_ids':['R-1'],'reason':'Same device obligation.'}],scope)
        self.assertFalse(mixed['passed'])
        self.assertTrue(any('base version' in p for p in mixed['problems']))


if __name__=='__main__': unittest.main()
