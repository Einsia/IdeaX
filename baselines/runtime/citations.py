"""Separate explicit numeric program literals from scholarly citations."""
import json
import re

# Chinese prose may directly precede a citation; ASCII identifier indexing may not.
PATTERN=re.compile(r'(?<![A-Za-z0-9_])\[([1-9]\d*(?:\s*,\s*[1-9]\d*)*)\]')
NUMBER=r'-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?'
ROW=r'\[\s*'+NUMBER+r'(?:\s*,\s*'+NUMBER+r')+\s*\]'
MATRIX=re.compile(r'\[\s*'+ROW+r'(?:\s*,\s*'+ROW+r')+\s*\]')


def matrix_spans(text):
    """A complete rectangular 2-D numeric literal includes its middle rows.

    Standalone [2,4] remains a citation. Ragged/nonnumeric bracket groups do not
    qualify; no inference is made from whether a reader digest happens to exist.
    """
    spans=[]
    for match in MATRIX.finditer(text):
        rows=json.loads(match[0])
        if len({len(row) for row in rows})==1:
            spans.append((match.start(),match.end()))
    return spans


def strings(value,path=''):
    if isinstance(value,str):yield path,value
    elif isinstance(value,dict):
        for key,item in value.items():yield from strings(item,path+'.'+key)
    elif isinstance(value,list):
        for i,item in enumerate(value):yield from strings(item,path+'.'+str(i))


def extract(report):
    ids=set();literals=[]
    for path,text in strings(report):
        matrices=matrix_spans(text)
        for match in PATTERN.finditer(text):
            numbers=[int(n.strip()) for n in match[1].split(',')]
            before=text[:match.start()];after=text[match.end():]
            reason=None
            if len(numbers)>1:
                if any(start<=match.start() and match.end()<=end for start,end in matrices):reason='row of explicit rectangular numeric matrix'
                elif re.search(r'\b[A-Za-z_]\w*\(\s*$',before) and re.match(r'\s*\)',after):reason='numeric array passed as explicit function argument'
                elif re.search(r'\b[A-Za-z_]\w*\(\s*'+ROW+r'\s*\)\s*=\s*$',before):reason='numeric array returned by explicit function equation'
                elif re.search(r'(?:应|会|将|预期|期望)输出\s*$',before):reason='explicit predicted numeric output array'
                elif re.search(r'\bfor\s+\w+\s+in\s*$',before):reason='for-loop numeric iterable'
                elif before.endswith('[') or after.startswith(']'):reason='nested numeric matrix'
                elif re.search(r'(?:整数区间为|取值范围为|截到|裁剪到)(?:\s*\[[\d\s,]+\]\s*(?:或|和|、))*\s*$',before):reason='explicit numeric interval'
            if reason:literals.append(dict(path=path,text=match[0],reason=reason,start=match.start()))
            else:ids.update(numbers)
    return sorted(ids),literals
