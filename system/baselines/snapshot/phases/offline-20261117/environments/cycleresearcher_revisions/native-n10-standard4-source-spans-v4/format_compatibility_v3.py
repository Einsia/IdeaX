"""Original native/v2 precedence, then strict deterministic bilingual fallback."""
from format_compatibility_v2 import paper_carrier, has_native_score
from format_compatibility_v2 import review_schema as review_schema_v2
from bilingual_review_candidate import map_review

FORMAT_REVISION = 'strict_bilingual_four_reviewers_v1'


def review_schema(native):
    mapped, previous = review_schema_v2(native)
    if previous['compatible']:
        return mapped, previous
    mapped, evidence = map_review(native)
    evidence = {**evidence, 'mapping': FORMAT_REVISION, 'diagnostic_only': False,
                'previous_v2_rejection': previous['error'],
                'original_native_numeric_precedence_preserved': True}
    return mapped, evidence
