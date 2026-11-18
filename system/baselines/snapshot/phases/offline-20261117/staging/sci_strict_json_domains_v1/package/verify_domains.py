"""Full native first-request boundaries inside the real offline launcher; zero inference."""
import argparse,concurrent.futures,json,socket,subprocess,threading
from pathlib import Path
from binding import ROOT,P,read,require,sha


def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);a=ap.parse_args()
 base=Path(a.output).resolve();base.mkdir(parents=True,exist_ok=False)
 routes=read(ROOT/'routes.json');fake=Path('/tmp/sciagents-strict-json-four-domain-fixture.sock')
 connections=[];stopped=threading.Event()
 with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as listener:
  listener.bind(str(fake));listener.listen(16);listener.settimeout(.2)
  def monitor():
   while not stopped.is_set():
    try:conn,_=listener.accept()
    except socket.timeout:continue
    connections.append(True)
    with conn:conn.sendall(b'HTTP/1.0 403 Forbidden\r\nContent-Length: 0\r\n\r\n')
  thread=threading.Thread(target=monitor,daemon=True);thread.start()
  def run(domain):
   output=base/domain;command=['/usr/bin/python3',str(ROOT/'host_dispatch.py'),'--domain-json',str(P/'inputs'/domain/'domain.json'),
      '--output-dir',str(output),'--fixture','--model-socket',str(fake)]
   with (base/(domain+'.log')).open('wb') as log:status=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT).returncode
   require(status==0,'Native first-request fixture failed: '+domain)
   proof=read(output/'fixture_acceptance.json');boundary=read(output/'offline_boundary.json');material=read(output/'input_material_version.json')
   require(proof['passed'] and proof['model_calls']==0,'Domain fixture acceptance failed')
   require(material['domain']==domain and material['fixture'] is True,'Fixture domain identity changed')
   require(boundary['network_namespace']!=boundary['parent_network_namespace'] and boundary['no_default_route'],'Missing private netns')
   return {'domain':domain,'passed':True,'native_checks':len(proof['checks']),'fixture_acceptance':{'path':str(output/'fixture_acceptance.json'),'sha256':sha(output/'fixture_acceptance.json')},
        'first_native_request':{'path':str(output/'first_native_request_fixture.json'),'sha256':sha(output/'first_native_request_fixture.json')},
        'boundary':{'path':str(output/'offline_boundary.json'),'sha256':sha(output/'offline_boundary.json')}}
  try:
   with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,routes['domains']))
  finally:stopped.set();thread.join(timeout=1)
 fake.unlink();require(not connections,'Fixture unexpectedly attempted model transport')
 (base/'acceptance.json').write_text(json.dumps({'passed':True,'domains':results,'paid_calls':0,'model_socket_connections':0,
  'routes_sha256':sha(ROOT/'routes.json'),'all_three_domain_graphs_reach_original_full_first_request':True},ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'passed':True,'domains':len(results),'paid_calls':0,'acceptance':str(base/'acceptance.json')}))
if __name__=='__main__':main()
