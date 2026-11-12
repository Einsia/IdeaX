"""Input freezing, anonymization, validation and accounting. No API calls here."""
import copy
import hashlib
import json
import random
import re
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft7Validator, FormatChecker, ValidationError

ROOT = Path(__file__).resolve().parent
DIMS = tuple("NVSFEC")
CORE_DIMS = tuple("NVSF")
REQUIRED = ("task_id", "idea_id", "task_context", "idea_text", "system")
META_FIELDS = ("idea_id", "input_sha256", "rubric_id", "rubric_sha256",
               "pass_id", "evaluated_at", "evaluator")


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def save_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")
    temp.replace(path)


def load_inputs(path):
    text = Path(path).read_text()
    try:
        data = json.loads(text)
        rows = data if isinstance(data, list) else [data]
    except json.JSONDecodeError:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not rows:
        raise ValueError("Empty input")
    seen = set()
    for row in rows:
        Draft7Validator(read_json(ROOT / "input.schema.json")).validate(row)
        if not isinstance(row, dict):
            raise ValueError("Each input must be an object")
        for field in REQUIRED:
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ValueError(f"Required nonempty string: {field}")
        key = (row["task_id"], row["system"], row["idea_id"])
        if key in seen:
            raise ValueError(f"Duplicate task/system/idea key: {key}")
        seen.add(key)
        for field in ("domain", "resource_constraints", "knowledge_cutoff"):
            if field in row and not isinstance(row[field], str):
                raise ValueError(f"{field} must be a string")
        refs = row.get("provided_reference_texts", [])
        if not isinstance(refs, list):
            raise ValueError("provided_reference_texts must be an array")
        ref_ids = set()
        for ref in refs:
            for field in ("reference_id", "text"):
                if not isinstance(ref.get(field), str) or not ref[field].strip():
                    raise ValueError(f"Reference missing {field}")
            if ref["reference_id"] in ref_ids:
                raise ValueError("Duplicate reference ID")
            ref_ids.add(ref["reference_id"])
    return rows


def blind_text(text):
    # Remove only explicit self-assessment verdict tokens, preserving arguments.
    return re.sub(r"(：|:)\s*(?:不通过|通过)([。！!])", r"\1[自评标签已隐藏]\2", text)


def judge_packet(row, blind_id):
    text = blind_text(row["idea_text"])
    return {
        "item_id": blind_id,
        "task_context": row["task_context"],
        "domain": row.get("domain", "unspecified"),
        "resource_constraints": row.get("resource_constraints", "未给出"),
        "knowledge_cutoff": row.get("knowledge_cutoff", "未给出；不可宣称覆盖截至今天的全部研究"),
        "idea_text": "\n".join(f"L{i}: {line}" for i, line in enumerate(text.splitlines(), 1)),
        "provided_reference_texts": row.get("provided_reference_texts", []),
    }


def prepare(source, out, rubric_dir, config_path=None, seed=20261016):
    out, rubric_dir = Path(out), Path(rubric_dir)
    if out.exists():
        raise ValueError("Batch already exists; use a new directory")
    rows = load_inputs(source)
    md = (rubric_dir / "rubric.md").read_bytes()
    rubric = read_json(rubric_dir / "rubric.json")
    if sha(md) != rubric["source_document_sha256"]:
        raise ValueError("rubric.json is out of sync with authoritative rubric.md")
    full_schema = read_json(rubric_dir / "score.schema.json")
    schema = copy.deepcopy(full_schema)
    schema["required"] = [x for x in schema["required"] if x not in META_FIELDS]
    for field in META_FIELDS:
        del schema["properties"][field]
    if schema.get("x-derived-dimension-scores"):
        dimension = schema["$defs"]["dimension"]
        dimension["required"].remove("score")
        del dimension["properties"]["score"]
        dimension["allOf"][0]["then"]["properties"].pop("score")
        dimension["allOf"][0].pop("else")
        # The full stored schema checks N=5 evidence after scores are derived.
        schema["allOf"] = [rule for rule in schema["allOf"]
                           if '"score"' not in json.dumps(rule)]
    Draft7Validator.check_schema(schema)
    config = read_json(config_path or ROOT / "config.json")
    template_path = rubric_dir / "benchmark_prompt.md"
    if not template_path.exists():
        template_path = ROOT / "prompts/judge.md"
    prompt = template_path.read_text().replace("{{RUBRIC}}", md.decode()).replace(
        "{{SCHEMA}}", json.dumps(schema, ensure_ascii=False, separators=(",", ":")))
    order = list(range(len(rows)))
    random.Random(seed).shuffle(order)
    packets, mapping = [], []
    for number, index in enumerate(order, 1):
        row = rows[index]
        packet = judge_packet(row, f"item_{number:03d}")
        packets.append(packet)
        mapping.append({"item_id": packet["item_id"], "source_index": index,
                        "task_id": row["task_id"], "idea_id": row["idea_id"], "system": row["system"],
                        "domain": row.get("domain", "unspecified"),
                        "original_sha256": sha(canonical(row)), "input_sha256": sha(canonical(packet)),
                        "idea_text_sha256": sha(row["idea_text"].encode())})
    out.mkdir(parents=True)
    (out / "rubric.md").write_bytes(md)
    (out / "rubric.json").write_bytes((rubric_dir / "rubric.json").read_bytes())
    (out / "system_prompt.md").write_text(prompt)
    for name, obj in [("inputs.json", rows), ("packets.json", packets), ("mapping.json", mapping),
                      ("config.json", config), ("score.schema.json", full_schema), ("judge.schema.json", schema)]:
        save_json(out / name, obj)
    manifest = {"created_at": now(), "source": str(Path(source).resolve()), "count": len(rows),
                "seed": seed, "rubric_id": rubric["rubric_id"], "protocol": config["protocol_version"],
                "anonymization": "hide generator metadata; mask explicit self-pass/fail labels; preserve original separately",
                "retrieval": "No judge web access. Only supplied text; author citations are not verified papers.",
                "assets": {p.name: sha(p.read_bytes()) for p in out.iterdir() if p.is_file()}}
    save_json(out / "manifest.json", manifest)
    return manifest


def verify_batch(batch):
    batch = Path(batch)
    meta = read_json(batch / "manifest.json")
    for name, digest in meta["assets"].items():
        if sha((batch / name).read_bytes()) != digest:
            raise ValueError(f"Frozen batch changed: {name}")
    return meta


def validate_assessment(obj, packet, schema):
    Draft7Validator(schema, format_checker=FormatChecker()).validate(obj)
    if schema.get("x-facet-aggregation") == "mean_with_weakest_plus_one_cap":
        for dimension in obj["dimensions"].values():
            values = list(dimension["facet_scores"].values())
            expected_score = (None if any(x is None for x in values)
                              else min(sum(values) / len(values), min(values) + 1))
            if not schema.get("x-derived-dimension-scores") and dimension["score"] != expected_score:
                raise ValueError("Dimension score differs from frozen facet aggregation rule")
    if schema.get("x-critical-facet-consistency"):
        actual = {d + k for d, dim in obj["dimensions"].items() if d != "C"
                  for k, v in dim["facet_scores"].items() if v == 1}
        reported = set()
        for issue in obj["critical_issues"]:
            ids = issue["blocking_facet_ids"]
            if any(key[0] not in issue["dimension_ids"] for key in ids):
                raise ValueError("Critical facet is not in issue dimensions")
            reported.update(ids)
        if actual != reported:
            raise ValueError("Confirmed critical issues must exactly cover score-1 scientific facets, not unknowns or conditional risks")
    refs = {r["reference_id"] for r in packet["provided_reference_texts"]}
    expected = "provided_only" if refs else "not_searched"
    if obj["novelty_search_status"] != expected or obj.get("retrieval_log"):
        raise ValueError("Search status is inconsistent with actual provided-only protocol")
    if schema.get("x-facet-aggregation") and not refs:
        if any(x in (1, 5) for x in obj["dimensions"]["N"]["facet_scores"].values()):
            raise ValueError("Novelty extremes require actual reference text in the facet protocol")
    evidence = [e for d in obj["dimensions"].values() for e in d["evidence"]]
    evidence += [e for field in ("critical_issues", "risk_flags") for issue in obj[field] for e in issue["evidence"]]
    for e in evidence:
        if e["kind"] == "retrieved_reference":
            raise ValueError("No retrieval tool was used")
        if e["kind"] == "provided_reference" and e["locator"] not in refs:
            raise ValueError("Evidence refers to a reference not supplied")
        if e["kind"] == "idea_text":
            if not e["locator"].startswith("idea_text:"):
                raise ValueError("idea_text evidence requires a line locator")
            for segment in e["locator"][len("idea_text:"):].split(","):
                match = re.fullmatch(r"L(\d+)(?:-L?(\d+))?", segment.strip())
                if not match:
                    raise ValueError("idea_text evidence requires a line locator")
                start, end = int(match[1]), int(match[2] or match[1])
                if not 1 <= start <= end <= len(packet["idea_text"].splitlines()):
                    raise ValueError("Evidence line is outside visible idea")
    return obj


def derive_assessment_scores(obj, schema):
    result = copy.deepcopy(obj)
    if schema.get("x-derived-dimension-scores"):
        for dimension in result["dimensions"].values():
            values = list(dimension["facet_scores"].values())
            dimension["score"] = (None if any(v is None for v in values)
                                  else min(sum(values)/len(values), min(values)+1))
    return result


def normalize_assessment_envelope(obj, packet, schema):
    """Drop only exact echoed transport labels; never repair scientific fields."""
    result = copy.deepcopy(obj)
    removed = {}
    expected = {key: schema.get(key) for key in
                ("$schema", "title", "type", "required", "additionalProperties")}
    expected["item_id"] = packet["item_id"]
    for key, value in expected.items():
        if key not in schema["properties"] and value is not None and result.get(key) == value:
            removed[key] = result.pop(key)
    return result, removed


def parse_assessment_json(text, packet, schema):
    """Recover only one uniquely determined missing dimensions closing brace.

    No character inside a value changes. The repaired object must exactly match
    the original parsed values at their schema-defined locations and pass every
    scientific validation. All other syntax errors remain errors.
    """
    try:
        return json.loads(text), None
    except json.JSONDecodeError as error:
        def unique(pairs):
            obj = {}
            for key, value in pairs:
                if key in obj:
                    raise ValueError('Duplicate JSON key')
                obj[key] = value
            return obj

        if error.pos != len(text.rstrip()) or not schema.get('x-derived-dimension-scores'):
            raise
        try:
            loose = json.loads(text+'}', object_pairs_hook=unique)
            names = set(schema['properties']['dimensions']['properties'])
            dims = loose['dimensions']
            extras = set(dims)-names
            allowed = {'critical_issues', 'risk_flags', 'domain_checks', 'followup_questions'}
            if not names <= set(dims) or not {'critical_issues','risk_flags','followup_questions'} <= extras <= allowed:
                raise ValueError('Not the recognized missing dimensions closure')
            if extras & set(loose):
                raise ValueError('Ambiguous duplicate top-level fields')
            expected = copy.deepcopy(loose)
            expected['dimensions'] = {k:v for k,v in dims.items() if k in names}
            expected.update({k:dims[k] for k in extras})
            candidates = []
            pattern = r',\s*"(?:critical_issues|risk_flags|domain_checks|followup_questions)"\s*:'
            for match in re.finditer(pattern, text):
                position = match.start()
                corrected = text[:position]+'}'+text[position:]
                try:
                    candidate = json.loads(corrected, object_pairs_hook=unique)
                    if candidate != expected:
                        continue
                    clean, _ = normalize_assessment_envelope(candidate, packet, schema)
                    validate_assessment(clean, packet, schema)
                except (ValueError, TypeError, KeyError, ValidationError):
                    continue
                candidates.append((candidate, position, corrected))
            if len(candidates) != 1:
                raise ValueError('Recovery is not uniquely schema-valid')
            candidate, position, corrected = candidates[0]
            return candidate, dict(policy='one-missing-dimensions-closure-v1', inserted='}',
                                   unicode_offset=position, utf8_byte_offset=len(text[:position].encode()),
                                   raw_text_sha256=sha(text.encode()), normalized_text_sha256=sha(corrected.encode()),
                                   scientific_values_preserved=True)
        except (ValueError, TypeError, KeyError, ValidationError):
            raise error


def usage_cost(usage, model, config, tier="default"):
    """Cached and cache-write tokens are subsets of input; reasoning is a subset of output."""
    if not usage:
        return {"estimated_usd": None, "reason": "usage missing", "actual_billed_usd": None}
    i, o = usage.get("input_tokens"), usage.get("output_tokens")
    if not isinstance(i, int) or not isinstance(o, int) or min(i, o) < 0:
        raise ValueError("Invalid token usage")
    details = usage.get("input_tokens_details") or {}
    cached, written = details.get("cached_tokens", 0), details.get("cache_write_tokens", 0)
    if any(type(x) is not int or x < 0 for x in [cached, written]) or cached + written > i:
        raise ValueError("Invalid cache accounting")
    rates = config["usd_per_million_tokens"].get(model)
    if rates is None or tier not in (None, "default", "standard") or i > config["pricing_max_input_tokens"]:
        return {"estimated_usd": None, "reason": "unpriced model/tier/context", "actual_billed_usd": None}
    cost = ((i-cached-written)*rates["input"] + cached*rates["cached_input"] +
            written*rates["cache_write"] + o*rates["output"])/1_000_000
    return {"estimated_usd": cost, "actual_billed_usd": None,
            "uncached_input_tokens": i-cached-written, "cached_input_tokens": cached,
            "cache_write_tokens": written,
            "cache_write_reported": "cache_write_tokens" in details,
            "reason": config["price_basis"], "rates": rates}


def core_mean(dimensions):
    values = [dimensions[d]["score"] for d in CORE_DIMS]
    return sum(values)/4 if all(v is not None for v in values) else None
