"""Format-only fallback with original character/UTF-8 spans; no guessed values."""
import copy
import re
from bilingual_review_candidate import span, Rejected, require

NUMBER = r'(?<![\d.\-−])(?P<value>\d+(?:\.\d+)?)/{denom}(?!\d)'
DIGITS = {**{str(i): i for i in range(1, 10)}, **dict(zip('一二三四五六七八九',range(1,10)))}
IDENT = r'[一二三四五六七八九\d]+'
REVIEWER = re.compile(r'^(?:(?:模拟)?(?:审稿人|评审人|评审|Reviewer)\s*(?P<n>'+IDENT+r')(?=\s*[:：]|从|侧重|关注)|第(?P<ord>'+IDENT+r')位(?:模拟)?(?:审稿人|评审人|评审)(?=\s*[:：]|从|侧重|关注))',re.I)
RATING = r'(?:Rating(?:\s*[（(]评分[）)])?|(?:方案)?评分(?:\s*[（(]Rating[）)])?)'
CONF = r'(?:Confidence(?:\s*[（(](?:置信度|信心)[）)])?|(?:审稿)?(?:置信度|信心)(?:\s*[（(]Confidence[）)])?)'
JOINT = r'(?:Rating\s+and\s+Confidence(?:\s*(?:[（(]评分与(?:置信度|信心)[）)]|[｜|]评分与(?:置信度|信心)))?|评分与(?:置信度|信心)(?:\s*[（(]Rating and Confidence[）)])?)'
MARKER = re.compile(r'^(?P<label>(?P<joint>'+JOINT+r')|(?P<rating>'+RATING+r')|(?P<confidence>'+CONF+r'))(?=$|[\s。.:：])',re.I)
META = re.compile(r'^(?:Meta[ -]?Review|Overall\s+(?:Rating|Score)|总评分|综合评分|总体评分|总体评级|元评审|综合评审)',re.I)


def clean_line(raw, start, end):
    # Remove Markdown decoration only, retaining a position map for every character.
    chars=[];positions=[];i=start
    while i<end:
        if raw.startswith('**',i): i+=2;continue
        chars.append(raw[i]);positions.append(i);i+=1
    value=''.join(chars)
    match=re.match(r'^\s*(?:#{1,6}\s*|[-+]\s+)?',value)
    k=match.end();value=value[k:];positions=positions[k:]
    trailing=len(value)-len(value.rstrip());
    if trailing:value=value[:-trailing];positions=positions[:-trailing]
    return {'text':value,'map':positions,'start':start,'end':end}


def number_rows(raw,line,denom):
    rows=[]
    for m in re.finditer(NUMBER.format(denom=denom),line['text']):
        lo=line['map'][m.start('value')];hi=line['map'][m.end('value')-1]+1
        rows.append({'value':float(m.group('value')),'span':span(raw,lo,hi),'line':line,'match':m})
    return rows


def map_review(native):
    raw=native['raw_text'];evidence={'compatible':False,'error':None,'numeric_spans':[], 'excluded_numeric_spans':[]}
    try:
        require(not native.get('reviews') and not native.get('meta_review'),'existing_native_fields_not_replaced')
        lines=[];offset=0
        for original in raw.splitlines(keepends=True):
            lines.append(clean_line(raw,offset,offset+len(original)));offset+=len(original)
        require(not any(META.match(l['text']) for l in lines),'unparsed_meta_or_overall_score_preserves_precedence')
        headers=[]
        for i,line in enumerate(lines):
            m=REVIEWER.match(line['text'])
            if m:
                token=m.group('n') or m.group('ord');headers.append((i,DIGITS.get(token),line))
        require(len(headers)==4 and [h[1] for h in headers]==[1,2,3,4],'requires_four_ordered_unique_explicit_reviewers')
        reviews=[];accepted=[]
        for k,(begin,rid,head) in enumerate(headers):
            stop=headers[k+1][0] if k<3 else len(lines)
            marks=[]
            for i in range(begin+1,stop):
                m=MARKER.match(lines[i]['text'])
                if m:marks.append((i,'joint' if m.group('joint') else ('rating' if m.group('rating') else 'confidence'),m))
            joint=[x for x in marks if x[1]=='joint']
            if joint:
                require(len(joint)==1,'requires_unique_joint_heading')
                first=joint[0][0]
                require(all(x[0]>=first for x in marks),'score_label_before_joint_heading')
                # A rating subsection ends at the first new non-score Markdown
                # heading or horizontal separator. Explanatory lines remain in it;
                # a second scoring basis therefore remains an explicit ambiguity.
                last=stop
                for i in range(first+1,stop):
                    text=lines[i]['text'];original=raw[lines[i]['start']:lines[i]['end']].strip()
                    if text in ('---','***') or (original.startswith(('#','**')) and not MARKER.match(text) and not re.search(r'\d+(?:\.\d+)?/(?:10|5)',text) and original.endswith('**')):
                        last=i;break
                zone=lines[first:last]
                ratings=[row for l in zone for row in number_rows(raw,l,10)]
                confidences=[row for l in zone for row in number_rows(raw,l,5)]
                require(len(ratings)==1,'joint_rating_missing_or_multiple_scoring_bases')
                require(len(confidences)==1,'joint_confidence_missing_or_multiple_values')
                rating,confidence=ratings[0],confidences[0]
                require(rating['span']['character_start']<confidence['span']['character_start'],'rating_confidence_order_reversed')
                # Direct rating value may be preceded only by an explicit scalar
                # rating label, known review basis, or the joint heading itself.
                prefix=rating['line']['text'][:rating['match'].start()]
                prefix=MARKER.sub('',prefix).strip(' 。.:：')
                require(prefix in ('','研究方案','方案评分','完整论文','完整研究论文','评分'),'rating_not_primary_explicit_value')
                cp=confidence['line']['text'][:confidence['match'].start()]
                if confidence['line'] is rating['line']:
                    between=cp[rating['match'].end():]
                    require(re.search(r'(?:置信度|信心|Confidence)\s*[:：]?\s*$',between,re.I) is not None or re.search(r'[；;]\s*$',between) is not None or re.fullmatch(r'[\s，,。.:：]+',between) is not None,'confidence_not_explicit_label_or_ordered_pair')
                else:require(re.fullmatch(CONF+r'\s*[:：]?\s*',cp,re.I) is not None,'separate_joint_confidence_not_explicitly_labeled')
            else:
                require([x[1] for x in marks]==['rating','confidence'],'requires_unique_separate_rating_confidence_labels')
                values=[]
                for i,kind,m in marks:
                    denom=10 if kind=='rating' else 5
                    line=lines[i];tail=line['text'][m.end():].strip(' 。.:：')
                    if not tail:
                        next_lines=[l for l in lines[i+1:stop] if l['text']]
                        require(bool(next_lines),'missing_value_after_heading');line=next_lines[0]
                        prefix_allowed=''
                    else:prefix_allowed=line['text'][:m.end()]
                    numbers=number_rows(raw,line,denom)
                    require(len(numbers)==1,'separate_score_missing_or_multiple_values')
                    value=numbers[0];prefix=line['text'][:value['match'].start()]
                    if prefix_allowed:prefix=prefix[len(prefix_allowed):]
                    require(not prefix.strip(' 。.:：'),'separate_score_not_leading_value')
                    require(not number_rows(raw,line,5 if denom==10 else 10),'score_outside_its_separate_heading')
                    values.append(value)
                rating,confidence=values
            require(0<=rating['value']<=10 and 0<=confidence['value']<=5,'score_out_of_range')
            accepted.extend((rating['span']['character_start'],confidence['span']['character_start']))
            end=lines[stop]['start'] if stop<len(lines) else len(raw)
            reviews.append({'reviewer_id':rid,'text':raw[head['start']:end],'rating':rating['value']})
            evidence['numeric_spans'].append({'reviewer_id':rid,'rating':rating['value'],'confidence':confidence['value'],
                'rating_span':rating['span'],'confidence_span':confidence['span'],
                'reviewer_header_span':span(raw,head['start'],head['end']), 'reviewer_block_span':span(raw,head['start'],end),
                'heading_spans':[span(raw,lines[i]['start'],lines[i]['end']) for i,_,_ in marks]})
        # Only explicit preamble scale legends and non-scoring mathematical /5
        # expressions are excluded. Any extra /10 after reviewer 1 is ambiguous,
        # including overall scores and alternative research/paper scoring bases.
        first_header=headers[0][2]['start']
        for line in lines:
            for denom in (10,5):
                for row in number_rows(raw,line,denom):
                    if row['span']['character_start'] in accepted:continue
                    if denom==10:
                        suffix=line['text'][row['match'].end():]
                        allowed=line['start']<first_header and '评分' in line['text'] and re.match(r'\s*(?:为|表示)',suffix)
                        require(allowed,'extra_rating_or_unparsed_overall_score')
                        reason='explicit_preamble_scale_legend'
                    else:
                        require(not re.search(r'置信度|信心|Confidence',line['text'],re.I),'extra_confidence_value')
                        reason='non_scoring_fraction_outside_rating_sections'
                    evidence['excluded_numeric_spans'].append({'span':row['span'],'context_span':span(raw,line['start'],line['end']),'reason':reason})
        mapped=copy.deepcopy(native);mapped['reviews']=reviews;evidence['compatible']=True
        return mapped,evidence
    except Rejected as exc:
        evidence['error']=str(exc);return copy.deepcopy(native),evidence
