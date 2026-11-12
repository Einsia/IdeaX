"""Resolve citations through original vault metadata caches and bounded retries."""
import hashlib,json,time
from pathlib import Path
import requests
from common import ROOT,read,save,sha,slot,event

class VaultMetadataUnavailable(RuntimeError):pass

def checked(item,pid):
    if not isinstance(item,dict) or item.get('paper_id')!=pid or not item.get('title'):
        raise ValueError('Vault metadata identity mismatch for citation '+str(pid))
    return item

def resolve(pid,config,run_dir):
    url=config['vault_api_url'].rstrip('/')+'/api/v1/papers/'+str(pid)
    cache=ROOT/'shared_retrieval_cache/vault'/(hashlib.sha256(url.encode()).hexdigest()+'.json')
    audit=Path(run_dir)/'validation_metadata.jsonl'
    if cache.exists():
        try:item=checked(json.loads(cache.read_text()),pid)
        except (ValueError,OSError,TypeError):event(audit,'invalid_cache_ignored',paper_id=pid,cache_path=str(cache))
        else:
            event(audit,'validated_original_vault_cache',paper_id=pid,cache_path=str(cache),sha256=sha(cache))
            return item
    for attempt in range(1,7):
        try:
            with slot('vault','delivery_validation/'+str(pid)):
                response=requests.get(url,timeout=(10,40))
            event(audit,'vault_validation_response',paper_id=pid,attempt=attempt,status=response.status_code)
            if response.status_code==404:return None
            if response.status_code in (408,429,500,502,503,504):
                raise VaultMetadataUnavailable('Vault metadata HTTP '+str(response.status_code))
            response.raise_for_status()
            item=checked(response.json(),pid);save(cache,item)
            return item
        except (requests.Timeout,requests.ConnectionError,VaultMetadataUnavailable) as exc:
            event(audit,'vault_validation_retry',paper_id=pid,attempt=attempt,error_type=type(exc).__name__)
            if attempt==6:raise VaultMetadataUnavailable('Vault metadata unavailable after six attempts for citation '+str(pid)) from exc
            time.sleep(min(30,2**attempt))
