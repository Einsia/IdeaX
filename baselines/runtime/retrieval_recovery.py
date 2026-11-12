"""Queue literature requests independently of GPT; never convert outages to no hits."""
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request
import requests
import shlex
from functools import lru_cache
from common import ROOT, save, read, slot, event, safe

class RetrievalUnavailable(RuntimeError): pass

@lru_cache(maxsize=1)
def openalex_credential():
    if os.environ.get('OPENALEX_API_KEY'): return os.environ['OPENALEX_API_KEY'], 'environment:OPENALEX_API_KEY'
    directory=Path(os.environ.get('LITGRAPH_SECRETS_DIR', str(Path(os.environ.get('IDEAX_GPT_PROFILE_FILE', str(Path.home()/'.config/litgraph/profile.json'))).parent)))
    path=directory/'openalex.env'
    values={}
    for line in path.read_text().splitlines():
        line=line.strip()
        if line.startswith('export '):line=line[7:]
        if not line or line.startswith('#') or '=' not in line:continue
        name,raw=line.split('=',1);parts=shlex.split(raw,comments=True)
        if parts:values[name.strip()]=parts[0]
    key=values.get('OPENALEX_API_KEY')
    if not key:raise RetrievalUnavailable('Configured OpenAlex credential is unavailable; anonymous fallback is disabled')
    return key,str(path)

def known_work(title):
    """Reuse actual OpenAlex records already obtained in this experiment."""
    target=' '.join(str(title).casefold().split())
    for path in (ROOT/'shared_retrieval_cache/coi').glob('*.json'):
        try:payload=json.loads(read(path).get('body','{}'))
        except ValueError:continue
        for work in payload.get('results',[]):
            if ' '.join(str(work.get('title','')).casefold().split())==target and work.get('id'):
                return work
    return None

def trace(kind, **fields):
    root=Path(os.environ.get('IDEASCIENTIST_EVIDENCE_DIR',str(Path.cwd()))).parent
    event(root/'retrieval_recovery_events.jsonl',kind,**fields)

def vault_get(path, params=None):
    url=os.environ['IDEASCIENTIST_VAULT_API_URL'].rstrip('/')+path
    if params:url+='?'+urllib.parse.urlencode(params)
    cache=ROOT/'shared_retrieval_cache/vault'/(hashlib.sha256(url.encode()).hexdigest()+'.json')
    if cache.exists():
        trace('vault_cache_hit',url=url);return read(cache)
    for attempt in range(1,9):
        try:
            with slot('vault',url):
                if cache.exists(): return read(cache)
                req=urllib.request.Request(url,headers={'Accept':'application/json'})
                with urllib.request.urlopen(req,timeout=90) as response:
                    raw=response.read(8_000_001)
                if len(raw)>8_000_000:raise ValueError('Vault response exceeds 8 MB')
                result=json.loads(raw)
                if not isinstance(result,dict):raise ValueError('Vault response must be an object')
                save(cache,result);trace('vault_request_completed',url=url,attempt=attempt,count=result.get('count'))
                return result
        except urllib.error.HTTPError as exc:
            body=exc.read().decode(errors='replace')
            trace('vault_request_failed',url=url,attempt=attempt,status=exc.code,error=safe(body))
            if exc.code not in (408,429,500,502,503,504):raise
            delay=max(5,min(60,int(exc.headers.get('Retry-After','0')) if str(exc.headers.get('Retry-After','0')).isdigit() else 5*attempt))
        except (urllib.error.URLError,TimeoutError,ConnectionError) as exc:
            trace('vault_request_failed',url=url,attempt=attempt,error=safe(exc));delay=min(60,5*attempt)
        if attempt<8:time.sleep(delay)
    raise RetrievalUnavailable('Vault remains unavailable after queued retries: '+url)

def coi_request(self,url,params=None,headers=None,attempts=2,cache=True):
    params={k:v for k,v in (params or {}).items() if v is not None}
    prepared=requests.Request('GET',url,params=params).prepare().url
    key=hashlib.sha256(prepared.encode()).hexdigest()
    cached=ROOT/'shared_retrieval_cache/coi'/(key+'.json')
    if cache and cached.exists():
        item=read(cached);self._trace('metadata_request',url=prepared,status=200,cache_hit=True)
        return item['body'],item['content_type']
    is_openalex=urllib.parse.urlsplit(url).hostname=='api.openalex.org'
    if is_openalex:
        secret,credential_path=openalex_credential()
        headers=dict(headers or {},Authorization='Bearer '+secret)
        # A daily quota failure opens one shared circuit; do not make every
        # domain independently retry the same exhausted account.
        quota=read(ROOT/'concurrency/openalex-quota.json')
        if quota.get('until',0)>time.time():
            raise RetrievalUnavailable('OpenAlex account daily quota is exhausted; shared requests paused until '+str(quota['until']))
        if params.get('search') and params.get('per-page')==5:
            work=known_work(params['search'])
            if work:
                self._trace('metadata_known_work_reused',title=work.get('title'),work_id=work['id'])
                return json.dumps({'results':[work]}),'application/json'
    is_arxiv='export.arxiv.org/api/' in url
    cooldown=ROOT/'concurrency/arxiv-cooldown.json'
    if is_arxiv and read(cooldown).get('until',0)>time.time():
        raise RetrievalUnavailable('arXiv API is in a shared cooldown after HTTP 429')
    for attempt in range(1,5):
        try:
            with slot('metadata',prepared):
                if cache and cached.exists():
                    item=read(cached);return item['body'],item['content_type']
                if is_arxiv:
                    # One request per 3.1 seconds across the whole experiment.
                    import fcntl
                    with (ROOT/'concurrency/arxiv-rate.lock').open('a+') as lock:
                        fcntl.flock(lock,fcntl.LOCK_EX)
                        lock.seek(0);previous=float(lock.read() or 0)
                        time.sleep(max(0,previous+3.1-time.time()))
                        lock.seek(0);lock.truncate();lock.write(str(time.time()));lock.flush()
                        response=requests.get(url,params=params,headers=headers,timeout=(10,60))
                else:response=requests.get(url,params=params,headers=headers,timeout=(10,60))
            self._trace('metadata_request',url=prepared,status=response.status_code,cache_hit=False,attempt=attempt,shared_admission=True)
            if response.status_code==200:
                item={'body':response.text,'content_type':response.headers.get('Content-Type','')}
                if cache:save(cached,item)
                return item['body'],item['content_type']
            if response.status_code==429 and is_arxiv:
                save(cooldown,{'until':time.time()+1800,'reason':'HTTP 429','retry_policy':'Use the existing OpenAlex metadata provider during cooldown'})
                raise RetrievalUnavailable('arXiv API HTTP 429; shared 30-minute cooldown')
            if response.status_code==429 and is_openalex:
                try:detail=response.json()
                except ValueError:detail={}
                wait=detail.get('retryAfter') or response.headers.get('Retry-After') or 60
                try:wait=max(1,float(wait))
                except (ValueError,TypeError):wait=60
                self._trace('openalex_rate_limit',authenticated=True,retry_after_seconds=wait,
                            daily_remaining_usd=detail.get('dailyRemainingUsd'),credential_source=credential_path)
                if detail.get('dailyRemainingUsd')==0 and not detail.get('prepaidRemainingUsd',0):
                    save(ROOT/'concurrency/openalex-quota.json',{'until':time.time()+wait,
                        'reason':'authenticated account quota exhausted','credential_source':credential_path})
                    raise RetrievalUnavailable('OpenAlex authenticated account daily quota exhausted; shared circuit opened')
            if response.status_code==404:return None,None
            if response.status_code not in (408,429,500,502,503,504):
                raise RetrievalUnavailable('Metadata endpoint HTTP '+str(response.status_code))
        except requests.RequestException as exc:
            self._trace('metadata_error',url=prepared,error=type(exc).__name__,attempt=attempt)
        if attempt<4:time.sleep(min(60,10*attempt))
    raise RetrievalUnavailable('Metadata endpoint unavailable after queued retries: '+url)

def install_coi():
    from searcher.sementic_search import SementicSearcher
    original=SementicSearcher._search_arxiv
    SementicSearcher._request=coi_request
    def search(self,query,limit,publicationDate=None,year=None):
        try:return original(self,query,limit,publicationDate,year)
        except RetrievalUnavailable as exc:
            self._trace('metadata_provider_failover',original='arxiv',provider='OpenAlex',reason=str(exc),query=query)
            # Same declared public-metadata backend; no change to GPT, topic,
            # native chain/review workflow, or literature-evidence requirements.
            filters=['is_oa:true']
            if year:filters.append('publication_year:'+str(year))
            body,_=self._request('https://api.openalex.org/works',{'search':str(query),'per-page':min(max(limit,10),50),'filter':','.join(filters)})
            works=json.loads(body or '{}').get('results',[]);rows=[]
            for work in works:
                row=self._openalex_row(work);row['paperId']=work['id'];row['url']=row['source_url']
                if row.get('openAccessPdf'):rows.append(row)
            self._trace('search_results',backend='openalex_fallback',query=str(query),returned=len(rows),reading_scope='title/abstract metadata; native full-text parsing still required')
            return {'data':rows}
    SementicSearcher._search_arxiv=search

def install_isci():
    from ideascientist.harness import corpus
    corpus._api_get=vault_get
