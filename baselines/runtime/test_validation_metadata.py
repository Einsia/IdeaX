import contextlib,hashlib,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
import validation_metadata as vm
from native_delivery import validate_delivery
from common import save

class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=os.environ['IDEAX_SCRATCH']);self.root=Path(self.temp.name)
        self.config=dict(vault_api_url='http://vault.test',cutoff_date='2027-01-01',reader_source='test')
        self.patch=patch.object(vm,'ROOT',self.root);self.patch.start()
        self.admission=patch.object(vm,'slot',lambda *args:contextlib.nullcontext());self.admission.start()
    def tearDown(self):self.admission.stop();self.patch.stop();self.temp.cleanup()
    def cache(self,pid,item):
        url=self.config['vault_api_url']+'/api/v1/papers/'+str(pid)
        p=self.root/'shared_retrieval_cache/vault'/(hashlib.sha256(url.encode()).hexdigest()+'.json');save(p,item)
    def response(self,status,item=None):
        r=Mock(status_code=status);r.json.return_value=item;r.raise_for_status.return_value=None;return r
    def test_valid_cache_survives_service_outage_without_request(self):
        item=dict(paper_id=1,title='Original paper',date='2025-01-01');self.cache(1,item)
        with patch.object(vm.requests,'get',side_effect=AssertionError('Must reuse original metadata')):
            self.assertEqual(vm.resolve(1,self.config,self.root),item)
    def test_503_retries_same_identity_then_caches_success(self):
        item=dict(paper_id=1,title='Original paper',date='2025-01-01')
        with patch.object(vm.requests,'get',side_effect=[self.response(503),self.response(200,item)]) as request,patch.object(vm.time,'sleep'):
            self.assertEqual(vm.resolve(1,self.config,self.root),item);self.assertEqual(request.call_count,2)
    def test_retry_exhaustion_is_incomplete_not_zero(self):
        with patch.object(vm.requests,'get',return_value=self.response(503)) as request,patch.object(vm.time,'sleep'):
            with self.assertRaises(vm.VaultMetadataUnavailable):vm.resolve(1,self.config,self.root)
            self.assertEqual(request.call_count,6)
    def test_wrong_cached_identity_does_not_pass(self):
        self.cache(1,dict(paper_id=2,title='Wrong paper',date='2025-01-01'))
        with patch.object(vm.requests,'get',return_value=self.response(404)):
            self.assertIsNone(vm.resolve(1,self.config,self.root))
    def test_cached_metadata_keeps_cutoff_and_reader_digest_checks(self):
        out=self.root/'outputs';out.mkdir()
        for name in ('plan.md','gaps.md','candidates.md','scores.md'):(out/name).write_text('Existing native evidence '*3)
        report={k:'Real existing content [1]' for k in ('title','one_sentence_thesis','core_problem','key_novelty','method','proposed_evaluation','falsifiable_predictions','limitations')};save(out/'report.json',report)
        self.cache(1,dict(paper_id=1,title='Future paper',date='2028-01-01'))
        result=validate_delivery(self.root,self.config)
        self.assertEqual(result['status'],'incomplete');self.assertTrue(any('cutoff' in e for e in result['errors']));self.assertTrue(any('digest' in e for e in result['errors']))

if __name__=='__main__':unittest.main()
