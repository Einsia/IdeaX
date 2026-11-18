"""Loopback-only HTTP access to the shared frozen raw-paper corpus."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
import argparse, contextlib, datetime, hashlib, json, threading
from cli import Corpus, CorpusError


def serve(corpus_path, port=8766, audit_log=None):
    corpus_path=Path(corpus_path).resolve();audit_log=Path(audit_log) if audit_log else None
    lock=threading.Lock()
    with contextlib.closing(Corpus(corpus_path)) as corpus:
        corpus_id=corpus.corpus_id
    def log(value):
        if audit_log:
            audit_log.parent.mkdir(parents=True,exist_ok=True)
            with lock,audit_log.open('a') as stream:stream.write(json.dumps(value,ensure_ascii=False)+'\n')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):pass
        def do_GET(self):
            parsed=urlsplit(self.path);params=parse_qs(parsed.query,keep_blank_values=True)
            get=lambda key,default=None:params.get(key,[default])[0]
            status=200
            try:
                if get('view','raw')!='raw' or 'insights' in params:
                    raise CorpusError('raw_only_service','This service exposes original metadata, abstracts and local full text only.')
                with contextlib.closing(Corpus(corpus_path)) as corpus:
                    if parsed.path in ('/health','/stats'):
                        result=corpus.stats();result['service']='local_raw_literature';result['compressed_content_exposed']=False
                    elif parsed.path in ('/search','/v1/search'):
                        query=get('q',get('query',''))
                        result=corpus.search(query,int(get('limit',10)),int(get('offset',0)),get('scope','all_local_metadata'),'raw',get('mode','any'),get('date_before'))
                    elif parsed.path in ('/read','/v1/read'):
                        ident=get('id',get('url'))
                        if not ident:raise CorpusError('missing_identifier','Supply id or url.')
                        cap=get('max_chars')
                        result=corpus.read(ident,get('scope','all_local_metadata'),'raw',int(get('offset_chars',0)),int(cap) if cap is not None else None,get('require_full_text','false').lower() in ('1','true','yes'))
                    elif parsed.path.startswith('/v1/papers/'):
                        result=corpus.read(parsed.path[len('/v1/papers/'):],get('scope','all_local_metadata'),'raw')
                    else:
                        raise CorpusError('unsupported_endpoint','Only /health, /stats, /search, /read and /v1/papers/{id} exist. Compressed LitGraph entry endpoints are intentionally unavailable.')
            except CorpusError as exc:
                status=404 if exc.code in ('paper_not_in_frozen_corpus','unsupported_endpoint') else 400
                result={'ok':False,'corpus_id':corpus_id,'offline':True,'network_fallback':False,'error':{'code':exc.code,'message':exc.message,**exc.details}}
            except (ValueError,TypeError) as exc:
                status=400;result={'ok':False,'corpus_id':corpus_id,'offline':True,'network_fallback':False,'error':{'code':'invalid_parameter','message':str(exc)}}
            body=json.dumps(result,ensure_ascii=False).encode()
            log({'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'method':'GET','path':parsed.path,'parameters':params,'corpus_id':corpus_id,'status':status,'response_sha256':hashlib.sha256(body).hexdigest(),'representation':'raw'})
            self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.send_header('X-Corpus-ID',corpus_id);self.end_headers();self.wfile.write(body)
        def do_POST(self):
            body=json.dumps({'ok':False,'offline':True,'network_fallback':False,'error':{'code':'read_only_service','message':'Use raw-only GET /search and /read. Legacy compressed /papers/batch is not supported.'}}).encode()
            self.send_response(405);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    server=ThreadingHTTPServer(('127.0.0.1',int(port)),Handler)
    event={'status':'ready','host':'127.0.0.1','port':server.server_port,'corpus_id':corpus_id,'raw_only':True,'network_fallback':False}
    log({'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),**event});print(json.dumps(event),flush=True)
    server.serve_forever()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--corpus',type=Path,default=Path(__file__).resolve().parents[2]/'inputs/corpus/corpus.sqlite');p.add_argument('--port',type=int,default=8766);p.add_argument('--audit-log',type=Path);a=p.parse_args();serve(a.corpus,a.port,a.audit_log)
