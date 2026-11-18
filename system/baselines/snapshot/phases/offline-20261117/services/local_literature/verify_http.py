"""Run the actual loopback server with all outbound sockets rejected."""
from pathlib import Path
import contextlib,hashlib,http.client,json,os,subprocess,sys,time,urllib.parse
from cli import Corpus
ROOT=Path(__file__).resolve().parents[2];SERVICE=Path(__file__).resolve().parent
code='''
import sys,socket
sys.path.insert(0,sys.argv[1])
def forbidden(*a,**k):raise AssertionError('Server outbound network denied')
socket.socket.connect=forbidden
socket.create_connection=forbidden
from server import serve
serve(sys.argv[2],0,sys.argv[3])
'''
child=subprocess.Popen([sys.executable,'-c',code,str(SERVICE),str(ROOT/'inputs/corpus/corpus.sqlite'),str(ROOT/'state/local_literature_http_requests.jsonl')],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
try:
    ready=json.loads(child.stdout.readline());port=ready['port'];checks=[]
    def get(path):
        con=http.client.HTTPConnection('127.0.0.1',port,timeout=30);con.request('GET',path);response=con.getresponse();data=json.loads(response.read());status=response.status;con.close();return status,data
    status,health=get('/health');assert status==200 and health['compressed_content_exposed'] is False
    checks.append('actual_loopback_server_ready_with_outbound_socket_connect_forbidden')
    query={'q':'Agent Workflow Memory','mode':'all','scope':'same_source_fulltext','limit':3}
    status,result=get('/search?'+urllib.parse.urlencode(query));assert status==200
    with contextlib.closing(Corpus(ROOT/'inputs/corpus/corpus.sqlite')) as corpus:
        assert result==corpus.search(query['q'],limit=3,mode='all',scope='same_source_fulltext')
        status,read=get('/read?'+urllib.parse.urlencode({'id':'https://arxiv.org/pdf/2409.07429v1.pdf','max_chars':300}));assert status==200
        assert read==corpus.read('https://arxiv.org/pdf/2409.07429v1.pdf',max_chars=300)
    checks.append('HTTP_search_and_URL_read_are_identical_to_shared_CLI')
    for endpoint in ['/search?q=memory&view=insights','/entries/any','/api/v1/entries/any','/candidates','/read?id=https%3A%2F%2Fexample.invalid%2Fmissing']:
        status,result=get(endpoint);assert status in (400,404) and not result['ok'] and result['network_fallback'] is False
    checks.append('compressed_entries_candidates_and_unknown_URLs_are_rejected_without_fallback')
    con=http.client.HTTPConnection('127.0.0.1',port,timeout=10);con.request('POST','/papers/batch',body=b'{}');response=con.getresponse();assert response.status==405;response.read();con.close()
    checks.append('legacy_compressed_batch_is_not_misrepresented_as_raw_compatibility')
    receipt={'passed':True,'checks':checks,'public_network_calls':0,'model_calls':0,'local_http_calls_only':True,'outbound_network_blocked_inside_server':True,'corpus_id':ready['corpus_id'],'bind_host':ready['host'],'service_sha256':hashlib.sha256((SERVICE/'server.py').read_bytes()).hexdigest(),'cli_sha256':hashlib.sha256((SERVICE/'cli.py').read_bytes()).hexdigest()}
    (ROOT/'state/local_literature_http_acceptance.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
finally:
    child.terminate()
    try:child.wait(timeout=10)
    except subprocess.TimeoutExpired:child.kill();child.wait()
