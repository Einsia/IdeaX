"""Shared Astra transport; never modifies native prompts or selection semantics."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import fcntl, hashlib, json, os, random, re, shlex, time, urllib.error, urllib.request, uuid
ROOT = Path(__file__).resolve().parents[1]
MODEL = 'gpt-6-astra'
BASE_URL = 'https://sbtunnel.xiaoaojianghu.fun/v1'
SECRET_FILE = Path('/mnt/einsia/aws01-nvme/liuhanzuo/ai-home/.secrets/insightpro-ar-baselines-20261116.env')
class InfrastructureFailure(RuntimeError): pass
class NativeFailure(RuntimeError): pass

def now(): return datetime.now(timezone.utc).isoformat()
def save(path, obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name('.'+path.name+'.'+uuid.uuid4().hex+'.tmp')
    tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n');tmp.replace(path)
def read(path, default=None):
    try:return json.loads(Path(path).read_text())
    except (OSError,ValueError):return default

def credentials():
    values={}
    for line in SECRET_FILE.read_text().splitlines():
        for token in shlex.split(line,comments=True):
            if '=' in token:
                k,v=token.split('=',1);values[k]=v
    return BASE_URL,values['OPENAI_API_KEY']
def safe(value):
    s=str(value)
    try:s=s.replace(credentials()[1],'[REDACTED]')
    except (OSError,KeyError):pass
    return re.sub(r'\bsk-[A-Za-z0-9_-]{12,}','[REDACTED]',s)[:6000]
@contextmanager
def admission(label, units=1):
    """Reserve all requested weighted units atomically, releasing partial attempts."""
    if type(units) is not int or not 1 <= units <= 250:raise ValueError('Admission units must be1..250')
    locks=ROOT/'state/request_slots';locks.mkdir(exist_ok=True)
    held=[]
    while not held:
        n=int(read(ROOT/'state/control.json',{}).get('request_concurrency',100))
        n=max(0,min(n,250))
        if n<units:time.sleep(0.5);continue
        indices=list(range(n));random.shuffle(indices);trial=[]
        for i in indices:
            f=(locks/f'{i:03}.lock').open('a+')
            try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:f.close();continue
            trial.append(f)
            if len(trial)==units:break
        if len(trial)==units:
            held=trial
            for index,f in enumerate(held,1):
                f.seek(0);f.truncate();json.dump({'pid':os.getpid(),'label':label,'at':now(),'units_total':units,'unit_index':index},f);f.flush()
        else:
            for f in trial:f.close()
            time.sleep(0.5+random.random())
    try:yield
    finally:
        for f in held:f.close()

def event(path,kind,**details):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX)
        stream.write(json.dumps({'at':now(),'event':kind,**details},ensure_ascii=False)+'\n');stream.flush()

def single_prompt(domain):
    text=domain['prompt']
    if '提出 5 条' not in text:raise ValueError('Frozen domain output-count instruction missing')
    return text.replace('提出 5 条','提出 1 条',1)

class AstraClient:
    def __init__(self, output_dir, timeout=1800, max_attempts=5):
        self.output_dir=Path(output_dir);self.logs=self.output_dir/'api_requests';self.logs.mkdir(parents=True,exist_ok=True)
        self.timeout=timeout;self.max_attempts=max_attempts
    def completion(self,messages,system=None,max_tokens=32768,request_id=None,**kwargs):
        msgs=list(messages)
        if system is not None:msgs=[{'role':'system','content':system}]+msgs
        payload={'model':MODEL,'messages':msgs,'reasoning_effort':'xhigh','max_completion_tokens':max_tokens,'stream':True,'stream_options':{'include_usage':True}}
        # Preserve tool schema and output format when the native caller supplies them.
        for k in ('tools','tool_choice','response_format','stop','n','seed','parallel_tool_calls'):
            if k in kwargs and kwargs[k] is not None:payload[k]=kwargs[k]
        digest=hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        ident=request_id or (str(time.time_ns())+'-'+uuid.uuid4().hex[:8])
        if not re.fullmatch(r'[A-Za-z0-9_.-]+',ident):raise ValueError('Invalid request identifier')
        target=self.logs/ident;target.mkdir(exist_ok=True)
        invocation=uuid.uuid4().hex
        ledger=self.output_dir/'api_events.jsonl'
        context={'request_id':ident,'invocation_id':invocation,'request_sha256':digest}
        old=read(target/'receipt.json',{})
        if old.get('status')=='native_failure':
            event(ledger,'cache_hit',**context,status='native_failure',physical_request=False)
            raise NativeFailure('Cached native completion exhausted output budget')
        if old.get('status')=='completed':
            if old['request_sha256']!=digest:raise ValueError('Request id reused with different payload')
            event(ledger,'cache_hit',**context,status='completed',physical_request=False)
            return read(target/'response.json')
        save(target/'request.json',payload)
        base,key=credentials()
        body=json.dumps(payload,ensure_ascii=False).encode()
        for attempt in range(1,self.max_attempts+1):
            started=now();attempt_id=str(time.time_ns())+'-'+uuid.uuid4().hex[:12]
            attempt_dir=target/'attempts'/attempt_id;attempt_dir.mkdir(parents=True)
            details={**context,'attempt_id':attempt_id,'attempt_in_invocation':attempt,'pid':os.getpid()}
            try:
                req=urllib.request.Request(base+'/chat/completions',data=body,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
                with admission(str(self.output_dir)):
                    event(ledger,'attempt_start',**details,model=MODEL,reasoning_effort='xhigh',endpoint=base+'/chat/completions')
                    with urllib.request.urlopen(req,timeout=self.timeout) as response:
                        content_type=response.headers.get('Content-Type','')
                        if 'text/event-stream' in content_type:
                            chunks=[];data={'choices':[]};choices={};usage={}
                            with (attempt_dir/'stream.jsonl').open('w') as trace:
                                for raw_line in response:
                                    line=raw_line.decode('utf-8').strip()
                                    if not line.startswith('data:'):continue
                                    value=line[5:].strip()
                                    if value=='[DONE]':break
                                    if not value:continue
                                    chunk=json.loads(value);trace.write(json.dumps(chunk,ensure_ascii=False)+'\n');trace.flush()
                                    if chunk.get('error'):raise InfrastructureFailure(safe(chunk['error']))
                                    for k in ('id','model','created','system_fingerprint'):
                                        if k in chunk:data[k]=chunk[k]
                                    if chunk.get('usage'):usage=chunk['usage']
                                    for choice in chunk.get('choices',[]):
                                        idx=choice['index'];acc=choices.setdefault(idx,{'index':idx,'message':{'role':'assistant','content':''},'finish_reason':None})
                                        delta=choice.get('delta',{})
                                        for field in ('content','reasoning_content','refusal'):
                                            if delta.get(field):acc['message'][field]=acc['message'].get(field,'')+delta[field]
                                        if delta.get('tool_calls'):
                                            acc.setdefault('_tools',{})
                                            for tool in delta['tool_calls']:
                                                t=acc['_tools'].setdefault(tool['index'],{'id':'','type':'function','function':{'name':'','arguments':''}})
                                                if tool.get('id'):t['id']+=tool['id']
                                                for field in ('name','arguments'):
                                                    if tool.get('function',{}).get(field):t['function'][field]+=tool['function'][field]
                                        if choice.get('finish_reason'):acc['finish_reason']=choice['finish_reason']
                            for acc in choices.values():
                                if '_tools' in acc:acc['message']['tool_calls']=[t for _,t in sorted(acc.pop('_tools').items())]
                            data['choices']=[v for _,v in sorted(choices.items())];data['usage']=usage
                            if not data['choices'] or any(c['finish_reason'] is None for c in data['choices']):raise InfrastructureFailure('Stream closed before terminal completion')
                            raw=json.dumps(data,ensure_ascii=False).encode()
                        else:
                            raw=response.read();data=json.loads(raw)
                if data.get('error'):raise InfrastructureFailure(safe(data['error']))
                if data.get('model')!=MODEL:raise InfrastructureFailure('Response model mismatch: '+str(data.get('model')))
                if not data.get('choices'):raise InfrastructureFailure('No completion choices')
                save(target/'response.json',data)
                finish=data['choices'][0].get('finish_reason')
                save(target/'receipt.json',{'status':'native_failure' if finish=='length' else 'completed','started':started,'completed':now(),'attempt':attempt,'attempt_id':attempt_id,'invocation_id':invocation,'request_sha256':digest,'response_sha256':hashlib.sha256(raw).hexdigest(),'model':MODEL,'effort':'xhigh','finish_reason':finish})
                save(attempt_dir/'response.json',data)
                event(ledger,'attempt_end',**details,status='native_failure' if finish=='length' else 'completed',finish_reason=finish,response_id=data.get('id'),usage=data.get('usage'),usage_known=bool(data.get('usage')))
                if finish=='length':raise NativeFailure('Native generation hit configured output limit; saved raw response')
                return data
            except NativeFailure:raise
            except Exception as exc:
                error={'attempt':attempt,'started':started,'ended':now(),'error':safe(exc),'type':type(exc).__name__}
                if isinstance(exc,urllib.error.HTTPError):
                    # Keep transport diagnoses distinct from inferred model limits.
                    # Only nonsecret response metadata is retained; request auth is never logged.
                    try:body_text=exc.read(65537).decode('utf-8',errors='replace')
                    except Exception:body_text='[response body unavailable]'
                    error['http']={'status':exc.code,'body':safe(body_text),
                                   'body_truncated':len(body_text)>6000,
                                   'headers':{k:safe(v) for k,v in exc.headers.items() if k.lower() in
                                              ('content-type','retry-after','server','cf-ray','x-request-id','request-id')}}
                save(attempt_dir/'error.json',error)
                event(ledger,'attempt_end',**details,status='infrastructure_failure',error_type=type(exc).__name__,error=safe(exc),usage=None,usage_known=False)
                if isinstance(exc,urllib.error.HTTPError) and exc.code in (400,401,403,404,422):
                    raise InfrastructureFailure(safe(exc)) from exc
                if attempt==self.max_attempts:raise InfrastructureFailure(safe(exc)) from exc
                time.sleep(min(60,2**attempt+random.uniform(0,2)))
    def chat(self,messages,system=None,max_tokens=32768,**kwargs):
        data=self.completion(messages,system=system,max_tokens=max_tokens,**kwargs)
        content=data['choices'][0]['message'].get('content')
        if not isinstance(content,str) or not content.strip():raise NativeFailure('Native generation returned empty content')
        return content
