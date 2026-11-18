"""Native continuation SSE collection with original per-logical SDK retry budgets. Native SDK receives only the exact final Response object."""
import json
import os
from pathlib import Path
import time
import httpx2
from evidence import digest,encode,event,freeze,freeze_bytes,sha


class StreamRejected(Exception): pass

def require(value,message):
    if not value:raise StreamRejected(message)


def stream_wire(native):
    value=json.loads(native)
    require('stream' not in value and native.endswith(b'}'),'Original wire shape/stream flag changed')
    body=native[:-1]+b', "stream": true}'
    require(json.loads(body)==value|{'stream':True},'Streaming changed a native parameter')
    return body


def reconstruct(raw):
    """Final response is authoritative; never synthesize a result from partial deltas."""
    text=raw.decode('utf-8').replace('\r\n','\n')
    require('\r' not in text,'Unsupported bare CR in SSE')
    frames=text.split('\n\n')
    require(not frames[-1].strip(),'SSE ended in an incomplete frame')
    terminal=None;terminal_type=None;events=[];ids=set();texts={};arguments={};last_seq=None;done=False
    for frame in frames[:-1]:
        lines=frame.split('\n');data=[];event_name=None
        for line in lines:
            if not line or line.startswith(':'):continue
            key,_,value=line.partition(':');value=value[1:] if value.startswith(' ') else value
            if key=='data':data.append(value)
            elif key=='event':event_name=value
            elif key not in ('id','retry'):raise StreamRejected('Unknown SSE field')
        if not data:continue
        value='\n'.join(data)
        if value=='[DONE]':
            require(terminal is not None and not done,'DONE before terminal or duplicate DONE');done=True;continue
        require(not done,'Event after DONE')
        try:item=json.loads(value)
        except ValueError:raise StreamRejected('Malformed SSE JSON') from None
        require(isinstance(item,dict) and isinstance(item.get('type'),str),'Missing SSE event type')
        kind=item['type'];require(event_name in (None,kind),'SSE event name/type mismatch')
        seq=item.get('sequence_number')
        if seq is not None:
            require(isinstance(seq,int) and not isinstance(seq,bool) and (last_seq is None or seq>last_seq),'SSE sequence duplicate or out of order');last_seq=seq
        events.append(item)
        response=item.get('response')
        if isinstance(response,dict) and response.get('id'):ids.add(response['id'])
        require(len(ids)<=1,'SSE mixed response identities')
        require(terminal is None,'Event after terminal response')
        if kind in ('response.completed','response.incomplete','response.failed'):
            require(isinstance(response,dict),'Terminal event has no complete Response object')
            terminal,terminal_type=response,kind
        elif kind=='error':raise StreamRejected('Provider stream error event')
        elif kind=='response.output_text.delta':
            key=(item.get('output_index'),item.get('content_index'))
            require(all(isinstance(i,int) and i>=0 for i in key) and isinstance(item.get('delta'),str),'Invalid text delta')
            texts[key]=texts.get(key,'')+item['delta']
        elif kind=='response.function_call_arguments.delta':
            key=item.get('output_index')
            require(isinstance(key,int) and key>=0 and isinstance(item.get('delta'),str),'Invalid function delta')
            arguments[key]=arguments.get(key,'')+item['delta']
    require(terminal is not None,'No terminal Response object; partial output is never accepted')
    require(terminal_type=='response.completed' and terminal.get('status')=='completed','Provider response incomplete/failed')
    require(terminal.get('object')=='response' and isinstance(terminal.get('id'),str)
            and isinstance(terminal.get('output'),list),'Invalid final Response object')
    require(not terminal.get('error') and not terminal.get('incomplete_details'),'Completed response carries incomplete/error details')
    try:
        for (i,j),value in texts.items():require(terminal['output'][i]['content'][j]['text']==value,'Text deltas differ from final response')
        for i,value in arguments.items():require(terminal['output'][i]['arguments']==value,'Function deltas differ from final response')
    except (IndexError,KeyError,TypeError):raise StreamRejected('Deltas reference missing final output') from None
    return terminal,{'event_count':len(events),'terminal_event':terminal_type,'response_id':terminal['id'],
                     'response_status':terminal['status'],'text_delta_groups':len(texts),'function_delta_groups':len(arguments),
                     'done_marker_seen':done,'all_native_response_fields_preserved':True}


def terminal_metadata(raw):
    # Failure accounting may retain provider-reported usage without consuming output.
    result={}
    try:
        for frame in raw.decode('utf-8').replace('\r\n','\n').split('\n\n'):
            data='\n'.join(line[5:].lstrip(' ') for line in frame.split('\n') if line.startswith('data:'))
            if not data or data=='[DONE]':continue
            item=json.loads(data)
            if item.get('type') in ('response.completed','response.incomplete','response.failed'):
                value=item.get('response')
                if isinstance(value,dict):result=value
    except (UnicodeError,ValueError,AttributeError):pass
    return result


def handle_stream(recorder,request):
    require(request.method == 'POST' and str(request.url) == 'http://127.0.0.1:8765/v1/responses',
            'Only the bound local Responses bridge is available')
    policy=recorder.policy
    native=request.read();c=policy.contract
    require(json.loads(native)==recorder.expected_body,'Original native SDK request differs')
    require(recorder.expected_body.get('model')=='gpt-6-astra' and recorder.expected_body.get('reasoning')=={'effort':'xhigh'},'Frozen model or effort changed')
    wire=stream_wire(native)
    if policy.is_target(recorder.logical_dir):
        require(digest(native)==c['target_wire_sha256'] and digest(wire)==c['target_stream_wire_sha256'],'Reviewed failed-target stream wire changed')
        require(recorder.physical_index==c['original_physical_attempts'],'Reviewed extra physical submission already consumed')
    else:
        require(policy.is_new_stream(recorder.logical_dir),'Only fresh native logical requests can use later stream transport')
        require(recorder.physical_index < recorder.max_attempts == 3,'Original SDK physical attempt budget exceeded')
        require(recorder.first_wire_sha in (None,digest(native)),'SDK retry changed original native wire bytes')
        recorder.first_wire_sha=digest(native)
    recorder.physical_index+=1
    directory=recorder.logical_dir/f'physical-{recorder.physical_index:02}';directory.mkdir(exist_ok=False)
    freeze_bytes(directory/'native_sdk_request_body.json',native)
    freeze_bytes(directory/'request_body.json',wire)
    headers=dict(request.headers);headers.pop('content-length',None)
    forwarded=httpx2.Request(request.method,request.url,headers=headers,content=wire,extensions=request.extensions)
    start=time.monotonic();wire_sha=digest(wire);context=recorder.scope_context
    event(recorder.output/'model_attempts.jsonl','attempt_start',logical_call=str(recorder.logical_dir),physical_attempt=recorder.physical_index,
          **context,request_sha256=wire_sha,request_bytes=len(wire),endpoint='/v1/responses',model='gpt-6-astra',
          reasoning_effort='xhigh',usage=None,usd=None,native_sdk_request_sha256=digest(native),stream_transport=True)
    response=None;chunks=[];times=[];receipt_written=False
    try:
        response=recorder.delegate.handle_request(forwarded)
        with (directory/'response_body.bin').open('xb') as raw_file:
            for chunk in response.stream:
                chunks.append(chunk);timing={'elapsed_seconds':time.monotonic()-start,'bytes':len(chunk)};times.append(timing)
                raw_file.write(chunk);raw_file.flush();os.fsync(raw_file.fileno())
                event(directory/'stream_chunks.jsonl','stream_chunk_received',index=len(chunks),**timing,
                      cumulative_bytes=raw_file.tell(),fixture=policy.fixture)
        raw=b''.join(chunks);response.close()
        freeze_bytes(directory/'response_body.bin',raw)
        freeze(directory/'stream_chunk_timing.json',{'chunks':times,'body_bytes':len(raw)})
        headers={k:v for k,v in response.headers.items() if k.lower() in {
            'content-type','x-offline-bridge-request-id','x-request-id','request-id','retry-after','cf-ray'}}
        parsed=terminal_metadata(raw)
        receipt={'http_status':response.status_code,'headers':headers,'elapsed_seconds':time.monotonic()-start,
                 'request_sha256':wire_sha,'response_sha256':digest(raw),'response_bytes':len(raw),
                 'provider_status':parsed.get('status'),'provider_response_id':parsed.get('id'),
                 'usage':parsed.get('usage'),'usage_known':parsed.get('usage') is not None,'usd':None,
                 'credential_fields_retained':False,'native_sdk_request_sha256':digest(native),
                 'stream_transport':True,**context}
        freeze(directory/'receipt.json',receipt);receipt_written=True
        event(recorder.output/'model_attempts.jsonl','attempt_end',logical_call=str(recorder.logical_dir),physical_attempt=recorder.physical_index,**receipt)
        if response.status_code!=200:
            return httpx2.Response(response.status_code,headers=headers,content=raw,request=request)
        require('text/event-stream' in response.headers.get('content-type',''),'Stream request returned no SSE content type')
        final,proof=reconstruct(raw)
        final_bytes=encode(final)
        freeze(directory/'stream_terminal_response.json',final)
        freeze_bytes(directory/'native_json_response_body.json',final_bytes)
        freeze(directory/'stream_reassembly.json',proof|{'raw_sse_sha256':digest(raw),'native_json_response_sha256':digest(final_bytes),
               'native_sdk_request_sha256':digest(native),'actual_stream_wire_sha256':wire_sha,
               'request_object_delta':{'stream':True},'stream_headers_dropped_from_native_json_response':True})
        return httpx2.Response(200,headers={'content-type':'application/json'},content=final_bytes,request=request)
    except BaseException as exc:
        raw=b''.join(chunks)
        if not receipt_written:
            freeze_bytes(directory/'partial_transport_body.bin',raw)
            freeze(directory/'error.json',{'request_sha256':wire_sha,'error_type':type(exc).__name__,
                'http_status':response.status_code if response is not None else None,'partial_transport_sha256':digest(raw),
                'partial_transport_bytes':len(raw),'elapsed_seconds':time.monotonic()-start,'usage':None,'usd':None,**context})
            event(recorder.output/'model_attempts.jsonl','attempt_error',logical_call=str(recorder.logical_dir),physical_attempt=recorder.physical_index,
                  **context,error_type=type(exc).__name__,usage=None,usd=None)
        else:
            freeze(directory/'stream_reassembly_error.json',{'error_type':type(exc).__name__,'raw_sse_sha256':digest(raw),
                'native_output_consumed':False,'automatic_retry':False})
        raise
    finally:
        if response is not None:response.close()


def validate_stream_directory(directory,contract):
    require(sha(directory/'native_sdk_request_body.json')==contract['target_wire_sha256'],'Native SDK wire changed')
    require(sha(directory/'request_body.json')==contract['target_stream_wire_sha256'],'Actual stream wire changed')
    require(stream_wire((directory/'native_sdk_request_body.json').read_bytes())==(directory/'request_body.json').read_bytes(),'Stream modified native fields')
    final,proof=reconstruct((directory/'response_body.bin').read_bytes())
    require(encode(final)==(directory/'native_json_response_body.json').read_bytes()
            and final==json.loads((directory/'stream_terminal_response.json').read_text()),'Reassembled native response changed')
    record=json.loads((directory/'stream_reassembly.json').read_text())
    require(all(record.get(k)==v for k,v in proof.items()) and record['raw_sse_sha256']==sha(directory/'response_body.bin')
            and record['native_json_response_sha256']==sha(directory/'native_json_response_body.json'),'Stream reconstruction evidence differs')
    return final
