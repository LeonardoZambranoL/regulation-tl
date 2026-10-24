import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import run_splade as pipeline


class SpladeWorkflowTest(unittest.TestCase):
    def test_selected_pages_references_and_deferred_candidates_are_audited(self):
        source=Mock()
        source.docs={'doc':{'document_id':'doc','sha256':'hash','regulation':'R','page_count':12}}
        source.expand.return_value=([('doc',7),('doc',10)],['unresolved'])
        source.packet.side_effect=lambda did,first,count: {'id':f'{did}-{first}'}
        engine=Mock()
        engine.base.manifest={'source_documents':[{'id':'doc','sha256':'hash'}]}
        engine.base.dense_meta={'model':'dense'};engine.meta={'model':'sparse'}
        rows=[{'id':str(i),'clause_id':str(i)} for i in range(3)]
        engine.retrieve.return_value=(rows,rows)
        cfg={'sparse_pool':300,'cross_encoder_head':0,'retrieval_per_query':2,
             'reference_depth':2,'packet_pages':3,'target_packets':2}
        with tempfile.TemporaryDirectory() as directory, patch.object(pipeline,'SparseDense',return_value=engine), \
             patch.object(pipeline,'load',return_value=(None,None,512,'dense')), \
             patch.object(pipeline,'encode',return_value=([[1]],0)):
            result=pipeline.targeted_packets(source,{'queries':['lamp']},[{'regulation':'R','decision':'uncertain'}],cfg,Path(directory))
            audit=json.loads((Path(directory)/'targeted-selection.json').read_text())
        self.assertEqual([r['id'] for r in result],['doc-1','doc-7'])
        self.assertEqual(audit['deferred_packets'],['doc-10'])
        self.assertEqual(audit['queries'][0]['deferred_clauses'],['2'])
        self.assertEqual(audit['unresolved_reference_edges'],['unresolved'])
        source.expand.assert_called_once_with(['0','1'],{'R'},2)

    def test_invalid_rerank_budget_fails_before_loading_models(self):
        with self.assertRaises(ValueError),patch.object(pipeline,'SparseDense') as engine:
            pipeline.targeted_packets(None,None,None,{'sparse_pool':1,'cross_encoder_head':3},None)
        engine.assert_not_called()


if __name__=='__main__':
    unittest.main()
