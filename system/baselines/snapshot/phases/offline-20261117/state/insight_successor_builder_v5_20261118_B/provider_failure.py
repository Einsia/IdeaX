"""Admit only explicit retryable response.failed server errors with unknown usage."""
import datetime,email.utils,math

def require(value,message):
 if not value:raise RuntimeError(message)

def explicit_server_failure(receipt,events):
 terminals=[e for e in events if e.get('type') in ['response.completed','response.failed','response.incomplete','error']]
 require(receipt['http_status']==200 and receipt.get('provider_status')=='failed','Not the explicit failed provider outcome')
 require(len(terminals)==1 and terminals[0].get('type')=='response.failed','Provider stream has a completed, incomplete, ambiguous, or other terminal')
 require(not any(str(e.get('type','')).startswith('response.refusal.') for e in events),'Provider refusal cannot be retried')
 response=terminals[0].get('response',{});error=response.get('error',{})
 require(response.get('status')=='failed' and response.get('id')==receipt.get('provider_response_id') and response.get('model')=='gpt-6-astra','Provider terminal identity differs')
 require(receipt.get('usage') is None and response.get('usage') is None,'Provider reported usage requires separate accounting review')
 require(error.get('code')=='server_error' and error.get('type') in ['server_error','service_unavailable_error'],'Provider failure is not the admitted explicit server error')
 require(not any(token in str(error).lower() for token in ['cyber_policy','policy_violation','content_policy']),'Provider policy error cannot be retried')
 for output in response.get('output',[]):
  require(output.get('type')!='refusal' and not any(part.get('type')=='refusal' for part in output.get('content',[]) if isinstance(part,dict)),'Provider terminal contains refusal content')
 headers={str(k).lower():str(v) for k,v in receipt.get('headers',{}).items()}
 headers.update({str(k).lower():str(v) for k,v in error.get('headers',{}).items()})
 return {'terminal_type':'response.failed','provider_status':'failed','provider_response_id':response['id'],'error_type':error['type'],'error_code':error['code'],'error':error,'usage':None,'usd':None,'retry_after_headers':{k:v for k,v in headers.items() if k in ['retry-after','retry-after-ms']},'partial_output_consumed':False}

def retry_delay_seconds(failure,actual_end_at):
 if not failure:return 0
 base=datetime.datetime.fromisoformat(actual_end_at).timestamp();values=[]
 for key,value in failure['retry_after_headers'].items():
  if key=='retry-after-ms':
   try:delay=float(value)/1000
   except (ValueError,TypeError):raise RuntimeError('Invalid provider retry-after-ms') from None
  else:
   try:delay=float(value)
   except (ValueError,TypeError):
    date=email.utils.parsedate_to_datetime(value)
    require(date is not None,'Invalid provider retry-after')
    if date.tzinfo is None:date=date.replace(tzinfo=datetime.timezone.utc)
    delay=date.timestamp()-base
  require(math.isfinite(delay),'Non-finite provider retry-after');values.append(max(0,delay))
 return max(values,default=0)
