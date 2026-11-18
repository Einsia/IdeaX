"""Same owner lock and queue, with persistent immutable successor preparation."""
from pathlib import Path
import fcntl,hashlib,importlib.util,sys,time,traceback
W=Path(__file__).resolve().parent;P=W.parents[1];S=P/'state/ar_baselines_automatic_successors_v2_20261118';sys.path[:0]=[str(P),str(S)]
assert hashlib.sha256((W/'owner_v4_base.py').read_bytes()).hexdigest()=='f83451450dbe1113ee0897b03a469c21878c2a32d91e53d14ae5f77cb3cfff54'
sp=importlib.util.spec_from_file_location('existing_recovery_owner',W/'owner_v4_base.py');M=importlib.util.module_from_spec(sp);sp.loader.exec_module(M);M.OWNER=Path(__file__).resolve()
import hook
def main():
 with (W/'owner.lock').open('a+') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  while True:
   try:M.tick()
   except Exception as exc:M.C.save(W/'owner_v4_error.json',{'at':M.C.now(),'stage':'existing_owner','error':repr(exc),'traceback':traceback.format_exc(),'worker_signals':0})
   try:hook.tick()
   except Exception as exc:M.C.save(S/'error.json',{'at':M.C.now(),'stage':'automatic_successor','error':repr(exc),'traceback':traceback.format_exc(),'worker_signals':0})
   time.sleep(15)
if __name__=='__main__':main()
