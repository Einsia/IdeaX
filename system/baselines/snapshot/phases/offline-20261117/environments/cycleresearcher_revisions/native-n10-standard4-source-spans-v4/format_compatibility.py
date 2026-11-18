"""Candidate-only source-span mapping after unchanged official/v2/v3 precedence."""
from format_compatibility_v2 import paper_carrier, has_native_score
from format_compatibility_v3 import review_schema as previous_schema
from strict_format_candidate import map_review
FORMAT_REVISION = 'strict_explicit_source_spans_candidate_v4'


def review_schema(native):
    mapped, previous = previous_schema(native)
    if previous['compatible']:
        return mapped, previous
    mapped, evidence = map_review(native)
    evidence.update(mapping=FORMAT_REVISION, previous_v3_rejection=previous['error'],
        diagnostic_only=True, original_native_numeric_precedence_preserved=True)
    return mapped, evidence
