"""Select a domain only from the sealed route index and its own frozen material."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parent
P=ROOT.parents[2]

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text())
def require(value,message):
 if not value:raise RuntimeError(message)
def verify_bindings(bindings):
 for path,expected in bindings.items():require(sha(path)==expected,'Frozen binding changed: '+path)

def select(domain_json):
 domain_json=Path(domain_json).resolve();domain=read(domain_json).get('id')
 require(domain_json==P/'inputs'/str(domain)/'domain.json','Domain input is not its canonical frozen file')
 routes=read(ROOT/'routes.json')
 require(domain in routes['domains'],'Domain has no independently prepared first-slot route')
 entry=routes['domains'][domain];path=Path(entry['manifest']);require(sha(path)==entry['sha256'],'Domain manifest changed')
 m=read(path);require(m['domain']==domain and Path(m['domain_json'])==domain_json and m['domain_sha256']==sha(domain_json),'Domain/material identity mismatch')
 require(entry['generation_slots']==m['generation_slots']==[1] and entry['scoring_approved'] is False and m['scoring_approved'] is False,'First-slot-only scope changed')
 verify_bindings(m['bindings'])
 a=read(Path(m['graph_bundle'])/'acceptance.json');n=read(Path(m['graph_bundle'])/'native_path_acceptance.json')
 require(a['passed'] and a['native_failed_chunks']==0 and a['domain_id']==domain and n['passed'] and n.get('pilot') is False,'Own-domain graph/path not accepted')
 require(a['retained_nodes']==m['retained_nodes'] and a['retained_edges']==m['retained_edges'],'Domain graph counts differ from accepted receipt')
 require(n['graph_acceptance_sha256']==sha(Path(m['graph_bundle'])/'acceptance.json'),'Native path belongs to another graph')
 require(m['comparison_scope']=='matched-domain-abstract-graph' and m['original_graph_transfer_included'] is False,'Comparison scope differs')
 return domain,path,m,None

def validate_output(output,manifest,fixture):
 output=Path(output).resolve()
 if fixture:require(output.is_relative_to(P/'state'),'Fixture output must remain outside production roots')
 else:require(output==Path(manifest['first_slot_output']),'Only the own-domain fresh slot01 is admitted')
 return output

def verify_release():
 value=read(ROOT/'frozen_components.json')
 require(value.get('passed') is True and value.get('fixture_passed') is True,'Complete three-domain fixture acceptance required')
 verify_bindings(value['bindings'])
 return value
