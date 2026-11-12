"""Persist completed requests; retry transport failures in the same native call."""
import hashlib,json,os,threading,time,urllib.error
from pathlib import Path
from datetime import datetime,timezone
_LOCK=threading.Lock()

def install():
    from ideascientist.harness.client import AgenticLLMClient
    from ideascientist.utils.llm import ResponsesAPIError
    original=AgenticLLMClient.chat
    def chat(self,messages,*args,**kwargs):
        root=Path(os.environ['IDEASCIENTIST_CALL_CACHE']);root.mkdir(parents=True,exist_ok=True)
        key=hashlib.sha256(json.dumps({'model':self.model,'messages':messages,'args':args,'kwargs':kwargs,'max_tokens':self.max_tokens},sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()
        cache=root/(key+'.json')
        def event(kind,**more):
            with _LOCK:
                with (root.parent/'transport_events.jsonl').open('a') as f:f.write(json.dumps({'at':datetime.now(timezone.utc).isoformat(),'event':kind,'request_sha256':key,'step':getattr(self,'_step_name',''),'model':self.model,**more})+'\n')
        # Cache is private to this independent run. It is for replay/recovery,
        # never shared across the five independent scientific proposals.
        if cache.exists():
            event('completed_request_cache_hit');return json.loads(cache.read_text())
        for cycle in range(3):
            event('native_request_start',recovery_cycle=cycle)
            try:
                result=original(self,messages,*args,**kwargs)
                temp=root/(key+'.tmp');temp.write_text(json.dumps(result,ensure_ascii=False));temp.replace(cache)
                event('native_request_completed',usage=result.get('usage',{}));return result
            except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError,ConnectionError,ResponsesAPIError) as exc:
                retryable=not isinstance(exc,urllib.error.HTTPError) or exc.code in (408,429,500,502,503,504,520,522,524)
                if isinstance(exc,ResponsesAPIError):
                    detail=exc.response.get('error') or {}
                    retryable=(detail.get('code') in ('upstream_error','server_error','rate_limit_exceeded') or 'no text or function call' in str(exc) or 'no terminal response' in str(exc))
                event('native_request_failed',error_type=type(exc).__name__,status=getattr(exc,'code',None),will_retry=retryable and cycle<2)
                if not retryable or cycle>=2:raise
                time.sleep(45)
    AgenticLLMClient.chat=chat
