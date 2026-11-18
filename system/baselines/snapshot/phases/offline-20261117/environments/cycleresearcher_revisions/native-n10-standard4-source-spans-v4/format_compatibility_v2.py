"""Strict, disclosed format compatibility; every extracted value points to raw bytes."""
import copy
import re


def span(raw, start, end):
    return {'character_start': start, 'character_end': end,
            'utf8_byte_start': len(raw[:start].encode('utf-8')),
            'utf8_byte_end': len(raw[:end].encode('utf-8')),
            'raw_text': raw[start:end]}


def numeric(value):
    try:
        float(value)
        return True
    except (ValueError, TypeError):
        return False


def has_native_score(review):
    return numeric(review.get('meta_review', {}).get('rating')) or any(
        numeric(r.get('rating')) for r in review.get('reviews', []))


def paper_carrier(paper):
    raw = paper['generated_text']
    latex = paper.get('latex')
    if isinstance(latex, str) and latex.strip():
        return latex, {'carrier_key': 'latex', 'mapping': 'official_native_parser',
                       'span': None, 'diagnostic': None}
    # A fence must occupy a complete line. Nested/duplicate or unclosed fences are ambiguous.
    fences = list(re.finditer(r'^```([^\r\n]*)\r?\n?|^```$', raw, re.M))
    openers = [i for i, m in enumerate(fences) if m.group(1).strip() == 'latex']
    reason = 'no_unique_complete_latex_fence'
    if len(openers) == 1:
        i = openers[0]
        if i + 1 < len(fences) and not fences[i + 1].group(1).strip():
            start, end = fences[i].end(), fences[i + 1].start()
            body = raw[start:end]
            titles = list(re.finditer(r'\\title\{[^{}]+\}', body))
            abstracts = list(re.finditer(r'\\begin\{abstract\}(.*?)\\end\{abstract\}', body, re.S))
            if (len(titles) == 1 and body.count('\\title{') == 1
                    and len(abstracts) == 1 and body.count('\\begin{abstract}') == 1
                    and body.count('\\end{abstract}') == 1 and abstracts[0].group(1).strip()):
                return body, {'carrier_key': 'generated_text_latex_span',
                              'mapping': 'strict_single_complete_latex_fence_v1',
                              'span': span(raw, start, end), 'diagnostic': None}
            reason = 'latex_title_or_abstract_not_unique_and_complete'
    return raw, {'carrier_key': 'generated_text', 'mapping': 'entire_original_response',
                 'span': span(raw, 0, len(raw)), 'diagnostic': reason}


def native_rating_spans(raw):
    """Audit the native parser's boxed sections; never change their numeric behavior."""
    result = []
    for kind, pattern in [('meta_review', r'\\boxed_review\{(.*?)\n}'),
                          ('reviews', r'\\boxed_simreviewers\{(.*?)\n}')]:
        box = re.search(pattern, raw, re.S)
        if not box:
            continue
        for match in re.finditer(r'## Rating:\s+(.*?)(?=##|\Z)', box.group(1), re.S):
            number = re.search(r'(\d+(?:\.\d+)?)', match.group(1))
            if number:
                start = box.start(1) + match.start(1) + number.start()
                result.append({'section': kind, 'rating': float(number.group()),
                               'rating_span': span(raw, start, start + len(number.group()))})
    return result


def review_schema(native):
    raw = native['raw_text']
    if has_native_score(native):
        return copy.deepcopy(native), {'mapping': 'official_native_parser',
            'compatible': True, 'error': None, 'numeric_spans': native_rating_spans(raw)}
    failure = {'mapping': 'strict_markdown_four_reviewers_v1', 'compatible': False,
               'error': None, 'numeric_spans': []}
    def reject(reason):
        failure['error'] = reason
        return copy.deepcopy(native), failure
    # Do not silently ignore an unparsed meta-rating that could take precedence.
    if re.search(r'^\s*(?:#+\s*)?\*{0,2}(?:Meta[ -]?Review|Overall\s+(?:Rating|Score))\b', raw, re.I | re.M):
        return reject('unparsed_meta_review_or_overall_rating')
    headers = list(re.finditer(r'^\*\*Reviewer ([1-4]):[^\r\n]+\*\*[ \t]*\r?$', raw, re.M))
    all_headers = list(re.finditer(r'^\s*(?:#+\s*)?\*{0,2}Reviewer\s+\d+\b', raw, re.I | re.M))
    if len(headers) != 4 or len(all_headers) != 4 or [m.group(1) for m in headers] != ['1', '2', '3', '4']:
        return reject('requires_exactly_four_ordered_unique_reviewer_headers')
    reviews = []
    for index, header in enumerate(headers):
        end = headers[index + 1].start() if index < 3 else len(raw)
        block = raw[header.end():end]
        markers = list(re.finditer(r'^\*\*Rating and Confidence\.\*\*[ \t]*\r?$', block, re.M))
        if len(markers) != 1:
            return reject('reviewer_' + str(index + 1) + '_requires_unique_rating_heading')
        start = header.end() + markers[0].end()
        line = re.match(r'\s*\*\*(\d+(?:\.\d+)?)/10\b([^\r\n]*)', raw[start:end])
        if not line or len(re.findall(r'\d+(?:\.\d+)?/10\b', line.group())) != 1:
            return reject('reviewer_' + str(index + 1) + '_ambiguous_or_missing_primary_rating')
        confidence = list(re.finditer(r'\bConfidence:\s*(\d+(?:\.\d+)?)/5\b', line.group()))
        if len(confidence) != 1 or not 0 <= float(line.group(1)) <= 10:
            return reject('reviewer_' + str(index + 1) + '_invalid_rating_or_confidence_format')
        if not 0 <= float(confidence[0].group(1)) <= 5:
            return reject('reviewer_' + str(index + 1) + '_confidence_out_of_range')
        rating_start = start + line.start(1)
        confidence_start = start + confidence[0].start(1)
        reviews.append({'reviewer_id': index + 1, 'text': raw[header.start():end],
                        'rating': float(line.group(1))})
        failure['numeric_spans'].append({'reviewer_id': index + 1, 'rating': float(line.group(1)),
            'rating_span': span(raw, rating_start, rating_start + len(line.group(1))),
            'confidence': float(confidence[0].group(1)),
            'confidence_span': span(raw, confidence_start, confidence_start + len(confidence[0].group(1))),
            'reviewer_block_span': span(raw, header.start(), end)})
    effective = copy.deepcopy(native)
    effective['reviews'] = reviews
    failure['compatible'] = True
    return effective, failure
