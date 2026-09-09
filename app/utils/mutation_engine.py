"""Combinatorial Payload Mutation & Fuzzing Engine.

Generates boundary-breaking test cases programmatically from baseline payloads or schemas:
- Missing mandatory / required properties.
- Data type inversions (int <-> str, array <-> object, boolean <-> int, etc.).
- Boundary & extreme values (empty strings, huge buffers, integer overflows, negative numbers, SQLi/XSS fuzz probes).
- Null / None injections into non-nullable fields.
"""
import copy
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("app.utils.mutation_engine")

# Extreme boundary probe values
BOUNDARY_STRING_PROBES = [
    "",  # Empty string
    "   ",  # Whitespace only
    "\x00\x00\x00\x00",  # Null byte injection
    "A" * 10000,  # Buffer overflow / huge payload
    "<script>alert('xss')</script>",  # XSS probe
    "' OR 1=1 --",  # SQLi probe
    "{{7*7}}",  # Template injection probe
    "\n\r\t",  # Control characters
]

BOUNDARY_INT_PROBES = [
    0,
    -1,
    -999999999,
    2147483647,  # Max 32-bit signed int
    2147483648,  # 32-bit int overflow
    9223372036854775807,  # Max 64-bit int
    9223372036854775808,  # 64-bit int overflow
]

BOUNDARY_FLOAT_PROBES = [
    0.0,
    -0.0000001,
    -1e308,
    1e308,
    float("inf"),
    float("-inf"),
]


def _format_target_field(parent_path: str, key: str) -> str:
    """Format dot-notation path for a target key."""
    return f"{parent_path}.{key}" if parent_path else key


def mutate_missing_fields(
    payload: Dict[str, Any],
    required_keys: Optional[List[str]] = None,
    parent_path: str = ""
) -> List[Dict[str, Any]]:
    """Generate payload variants with one required or existing key omitted.
    
    Returns list of mutation objects:
    [
        {
            "strategy": "missing_required_field",
            "target_field": "email",
            "description": "Omitted key 'email' from payload",
            "original_value": "user@example.com",
            "mutated_value": None,
            "payload": {...}
        }
    ]
    """
    mutations: List[Dict[str, Any]] = []
    if not isinstance(payload, dict):
        return mutations

    keys_to_omit = required_keys if (required_keys is not None and len(required_keys) > 0) else list(payload.keys())

    for key in keys_to_omit:
        if key in payload:
            mutated = copy.deepcopy(payload)
            orig_val = mutated.pop(key)
            field_path = _format_target_field(parent_path, key)
            mutations.append({
                "strategy": "missing_required_field",
                "target_field": field_path,
                "description": f"Omitted mandatory key '{field_path}' from payload",
                "original_value": orig_val,
                "mutated_value": "[OMITTED]",
                "payload": mutated
            })

    # Recurse into nested objects
    for key, value in payload.items():
        if isinstance(value, dict):
            field_path = _format_target_field(parent_path, key)
            nested_mutations = mutate_missing_fields(value, parent_path=field_path)
            for n_mut in nested_mutations:
                mutated_root = copy.deepcopy(payload)
                mutated_root[key] = n_mut["payload"]
                mutations.append({
                    "strategy": "missing_required_field",
                    "target_field": n_mut["target_field"],
                    "description": n_mut["description"],
                    "original_value": n_mut["original_value"],
                    "mutated_value": "[OMITTED]",
                    "payload": mutated_root
                })

    return mutations


def mutate_type_inversions(
    payload: Dict[str, Any],
    parent_path: str = ""
) -> List[Dict[str, Any]]:
    """Generate payload variants with data types intentionally inverted.
    
    - int -> str ("not_a_number"), bool (True), array ([1, 2])
    - str -> int (999999), bool (False), dict ({"nested": 1})
    - bool -> str ("invalid_bool"), int (42), array ([True])
    - list -> str ("not_a_list"), int (100), dict ({"key": "val"})
    - dict -> str ("not_an_object"), list ([1, 2, 3])
    """
    mutations: List[Dict[str, Any]] = []
    if not isinstance(payload, dict):
        return mutations

    for key, val in payload.items():
        field_path = _format_target_field(parent_path, key)

        if isinstance(val, bool):
            replacements = ["invalid_boolean", 42, ["bad_bool"]]
        elif isinstance(val, int) and not isinstance(val, bool):
            replacements = ["not_a_valid_integer", True, [1, 2, 3], {"unexpected": "object"}]
        elif isinstance(val, float):
            replacements = ["not_a_valid_float", True, "Infinity", [0.1, 0.2]]
        elif isinstance(val, str):
            replacements = [123456, False, ["str_in_array"], {"unexpected": "str_obj"}]
        elif isinstance(val, list):
            replacements = ["not_an_array_string", 9999, {"unexpected": "dict_instead_of_list"}]
        elif isinstance(val, dict):
            replacements = ["not_an_object_string", [1, 2, 3], 9999]
            # Also recurse into nested dict
            nested = mutate_type_inversions(val, parent_path=field_path)
            for n_mut in nested:
                mutated_root = copy.deepcopy(payload)
                mutated_root[key] = n_mut["payload"]
                mutations.append({
                    "strategy": "type_inversion",
                    "target_field": n_mut["target_field"],
                    "description": n_mut["description"],
                    "original_value": n_mut["original_value"],
                    "mutated_value": n_mut["mutated_value"],
                    "payload": mutated_root
                })
        else:
            replacements = ["unrecognized_type_mutation"]

        for rep in replacements:
            mutated = copy.deepcopy(payload)
            mutated[key] = rep
            mutations.append({
                "strategy": "type_inversion",
                "target_field": field_path,
                "description": f"Type inversion at '{field_path}': replaced {type(val).__name__} with {type(rep).__name__}",
                "original_value": val,
                "mutated_value": rep,
                "payload": mutated
            })

    return mutations


def mutate_boundaries(
    payload: Dict[str, Any],
    parent_path: str = ""
) -> List[Dict[str, Any]]:
    """Generate payload variants with boundary, extreme, and fuzz probe values."""
    mutations: List[Dict[str, Any]] = []
    if not isinstance(payload, dict):
        return mutations

    for key, val in payload.items():
        field_path = _format_target_field(parent_path, key)

        if isinstance(val, str):
            for probe in BOUNDARY_STRING_PROBES:
                mutated = copy.deepcopy(payload)
                mutated[key] = probe
                probe_desc = repr(probe) if len(repr(probe)) < 30 else f"{repr(probe)[:25]}...({len(probe)} chars)"
                mutations.append({
                    "strategy": "boundary_extreme_value",
                    "target_field": field_path,
                    "description": f"Boundary string probe at '{field_path}': {probe_desc}",
                    "original_value": val,
                    "mutated_value": probe if len(str(probe)) < 200 else f"{str(probe)[:100]}...[truncated]",
                    "payload": mutated
                })

        elif isinstance(val, int) and not isinstance(val, bool):
            for probe in BOUNDARY_INT_PROBES:
                mutated = copy.deepcopy(payload)
                mutated[key] = probe
                mutations.append({
                    "strategy": "boundary_extreme_value",
                    "target_field": field_path,
                    "description": f"Boundary integer probe at '{field_path}': {probe}",
                    "original_value": val,
                    "mutated_value": probe,
                    "payload": mutated
                })

        elif isinstance(val, float):
            for probe in BOUNDARY_FLOAT_PROBES:
                mutated = copy.deepcopy(payload)
                mutated[key] = probe
                mutations.append({
                    "strategy": "boundary_extreme_value",
                    "target_field": field_path,
                    "description": f"Boundary float probe at '{field_path}': {probe}",
                    "original_value": val,
                    "mutated_value": str(probe),
                    "payload": mutated
                })

        elif isinstance(val, list):
            # Empty list boundary
            mutated_empty = copy.deepcopy(payload)
            mutated_empty[key] = []
            mutations.append({
                "strategy": "boundary_extreme_value",
                "target_field": field_path,
                "description": f"Boundary list probe at '{field_path}': empty list []",
                "original_value": val,
                "mutated_value": [],
                "payload": mutated_empty
            })
            # Huge list boundary
            if val:
                mutated_huge = copy.deepcopy(payload)
                mutated_huge[key] = val * 200
                mutations.append({
                    "strategy": "boundary_extreme_value",
                    "target_field": field_path,
                    "description": f"Boundary list probe at '{field_path}': large array (len={len(mutated_huge[key])})",
                    "original_value": val,
                    "mutated_value": f"[Array with {len(mutated_huge[key])} elements]",
                    "payload": mutated_huge
                })

        elif isinstance(val, dict):
            # Empty dict boundary
            mutated_empty = copy.deepcopy(payload)
            mutated_empty[key] = {}
            mutations.append({
                "strategy": "boundary_extreme_value",
                "target_field": field_path,
                "description": f"Boundary object probe at '{field_path}': empty object {{}}",
                "original_value": val,
                "mutated_value": {},
                "payload": mutated_empty
            })
            # Recurse
            nested = mutate_boundaries(val, parent_path=field_path)
            for n_mut in nested:
                mutated_root = copy.deepcopy(payload)
                mutated_root[key] = n_mut["payload"]
                mutations.append({
                    "strategy": "boundary_extreme_value",
                    "target_field": n_mut["target_field"],
                    "description": n_mut["description"],
                    "original_value": n_mut["original_value"],
                    "mutated_value": n_mut["mutated_value"],
                    "payload": mutated_root
                })

    return mutations


def mutate_null_injections(
    payload: Dict[str, Any],
    parent_path: str = ""
) -> List[Dict[str, Any]]:
    """Generate payload variants with None / null injected into each property."""
    mutations: List[Dict[str, Any]] = []
    if not isinstance(payload, dict):
        return mutations

    for key, val in payload.items():
        field_path = _format_target_field(parent_path, key)
        mutated = copy.deepcopy(payload)
        mutated[key] = None
        mutations.append({
            "strategy": "null_injection",
            "target_field": field_path,
            "description": f"Injected null/None at non-nullable field '{field_path}'",
            "original_value": val,
            "mutated_value": None,
            "payload": mutated
        })

        if isinstance(val, dict):
            nested = mutate_null_injections(val, parent_path=field_path)
            for n_mut in nested:
                mutated_root = copy.deepcopy(payload)
                mutated_root[key] = n_mut["payload"]
                mutations.append({
                    "strategy": "null_injection",
                    "target_field": n_mut["target_field"],
                    "description": n_mut["description"],
                    "original_value": n_mut["original_value"],
                    "mutated_value": None,
                    "payload": mutated_root
                })

    return mutations


def generate_all_mutations(
    baseline_payload: Dict[str, Any],
    schema_definition: Optional[Dict[str, Any]] = None,
    strategies: Optional[List[str]] = None,
    max_count: int = 100
) -> List[Dict[str, Any]]:
    """Master generator synthesizing adversarial payload variants across requested strategies."""
    if not isinstance(baseline_payload, dict):
        return []

    active_strategies = set(strategies) if strategies else {
        "missing_required_field",
        "type_inversion",
        "boundary_extreme_value",
        "null_injection"
    }

    required_keys = []
    if schema_definition and isinstance(schema_definition, dict):
        required_keys = schema_definition.get("required", [])

    collected_mutations: List[Dict[str, Any]] = []

    # 1. Missing required / existing fields
    if "missing_required_field" in active_strategies or "all" in active_strategies:
        collected_mutations.extend(mutate_missing_fields(baseline_payload, required_keys))

    # 2. Type inversions
    if "type_inversion" in active_strategies or "all" in active_strategies:
        collected_mutations.extend(mutate_type_inversions(baseline_payload))

    # 3. Boundary values
    if "boundary_extreme_value" in active_strategies or "all" in active_strategies:
        collected_mutations.extend(mutate_boundaries(baseline_payload))

    # 4. Null injections
    if "null_injection" in active_strategies or "all" in active_strategies:
        collected_mutations.extend(mutate_null_injections(baseline_payload))

    # Deduplicate payloads by string representation
    unique_mutations: List[Dict[str, Any]] = []
    seen_payloads = set()

    for idx, mut in enumerate(collected_mutations, start=1):
        payload_key = str(sorted(mut["payload"].items())) if isinstance(mut["payload"], dict) else str(mut["payload"])
        if payload_key not in seen_payloads:
            seen_payloads.add(payload_key)
            mut["mutation_id"] = f"MUT-{mut['strategy'][:4].upper()}-{idx:03d}"
            mut["expected_status_category"] = "4xx"
            unique_mutations.append(mut)
            if len(unique_mutations) >= max_count:
                break

    return unique_mutations
