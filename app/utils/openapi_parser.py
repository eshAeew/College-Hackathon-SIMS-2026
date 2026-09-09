"""OpenAPI 3.0 / 3.1 & Swagger 2.0 Parser and Schema Dereferencer."""
import json
import logging
from typing import Any, Dict, List, Optional, Set, Tuple
import yaml

from app.models.schemas.openapi import (
    DiscoveredOperation,
    DiscoveredParameter,
    OpenApiSpecVersion,
    ParameterLocation,
    ParsedOpenApiSummary,
)

logger = logging.getLogger("app.utils.openapi_parser")


def detect_spec_format_and_parse(content: str) -> Dict[str, Any]:
    """
    Parse a raw string into a dictionary, supporting both JSON and YAML.
    
    Raises:
        ValueError: If content is empty or cannot be parsed.
    """
    if not content or not content.strip():
        raise ValueError("Specification content is empty.")

    cleaned = content.strip()

    # Automatically strip markdown code fences if user copied with ```json / ```yaml / ```
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    # Try JSON parsing first if starts with {
    if cleaned.startswith("{") or cleaned.startswith("["):
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

    # Fallback to YAML parsing
    try:
        parsed = yaml.safe_load(cleaned)
        if isinstance(parsed, dict):
            return parsed
        raise ValueError("Parsed YAML document root must be an object/dictionary.")
    except Exception as e:
        raise ValueError(f"Failed to parse specification (invalid JSON or YAML): {e}")


def detect_spec_version(doc: Dict[str, Any]) -> OpenApiSpecVersion:
    """Detect whether document is OpenAPI 3.0, 3.1, or Swagger 2.0."""
    if "openapi" in doc:
        ver_str = str(doc["openapi"]).strip()
        if ver_str.startswith("3.1"):
            return OpenApiSpecVersion.OPENAPI_3_1
        if ver_str.startswith("3.0") or ver_str.startswith("3."):
            return OpenApiSpecVersion.OPENAPI_3_0
        return OpenApiSpecVersion.OPENAPI_3_0
    elif "swagger" in doc:
        ver_str = str(doc["swagger"]).strip()
        if ver_str.startswith("2."):
            return OpenApiSpecVersion.SWAGGER_2_0
    return OpenApiSpecVersion.UNKNOWN


def resolve_json_ref(ref_path: str, root_doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Resolve internal JSON pointer (e.g. `#/components/schemas/UserDTO` or `#/definitions/Pet`).
    """
    if not ref_path.startswith("#/"):
        return {}

    tokens = ref_path.lstrip("#/").split("/")
    curr = root_doc
    for token in tokens:
        # Handle JSON Pointer encoded slashes and tildes
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(curr, dict) and token in curr:
            curr = curr[token]
        else:
            return {}
    return curr if isinstance(curr, dict) else {}


def dereference_schema(
    schema: Any,
    root_doc: Dict[str, Any],
    seen_refs: Optional[Set[str]] = None
) -> Any:
    """
    Recursively dereference all `$ref` components inside a schema to produce a self-contained JSON Schema.
    """
    if seen_refs is None:
        seen_refs = set()

    if isinstance(schema, dict):
        if "$ref" in schema and isinstance(schema["$ref"], str):
            ref_path = schema["$ref"]
            if ref_path in seen_refs:
                # Prevent circular reference recursion
                return {"type": "object", "description": f"Circular ref to {ref_path}"}
            
            seen_refs.add(ref_path)
            resolved = resolve_json_ref(ref_path, root_doc)
            return dereference_schema(resolved, root_doc, seen_refs.copy())
        
        # Recursively dereference all dict keys and values
        new_dict = {}
        for k, v in schema.items():
            new_dict[k] = dereference_schema(v, root_doc, seen_refs.copy())
        return new_dict

    elif isinstance(schema, list):
        return [dereference_schema(item, root_doc, seen_refs.copy()) for item in schema]

    return schema


def parse_openapi_document(doc: Dict[str, Any]) -> ParsedOpenApiSummary:
    """
    Parse a validated OpenAPI 3.x or Swagger 2.0 document into a ParsedOpenApiSummary model.
    """
    spec_version = detect_spec_version(doc)
    if spec_version == OpenApiSpecVersion.UNKNOWN:
        raise ValueError("Unsupported specification format. Must specify 'openapi: 3.x' or 'swagger: 2.0'.")

    info = doc.get("info", {})
    title = info.get("title", "Untitled API")
    version = info.get("version", "1.0.0")
    description = info.get("description")

    # Extract servers / base paths
    servers: List[str] = []
    if "servers" in doc and isinstance(doc["servers"], list):
        for s in doc["servers"]:
            if isinstance(s, dict) and "url" in s:
                servers.append(s["url"])
    elif "host" in doc:
        schemes = doc.get("schemes", ["https"])
        base_path = doc.get("basePath", "")
        host = doc["host"]
        servers.append(f"{schemes[0]}://{host}{base_path}")

    paths_dict = doc.get("paths", {})
    discovered_ops: List[DiscoveredOperation] = []

    for path_str, path_item in paths_dict.items():
        if not isinstance(path_item, dict):
            continue

        # Common parameters defined at the path level
        common_params = path_item.get("parameters", [])

        for method in ("get", "post", "put", "delete", "patch", "options", "head"):
            if method not in path_item or not isinstance(path_item[method], dict):
                continue

            op_data = path_item[method]
            op_id = op_data.get("operationId")
            summary = op_data.get("summary") or (f"{method.upper()} {path_str}")
            op_desc = op_data.get("description")
            tags = op_data.get("tags", [])

            # Combine and dereference parameters
            all_params_raw = common_params + op_data.get("parameters", [])
            discovered_params: List[DiscoveredParameter] = []
            path_params: Dict[str, Any] = {}
            query_params: Dict[str, Any] = {}
            header_params: Dict[str, str] = {}

            for p_raw in all_params_raw:
                if isinstance(p_raw, dict) and "$ref" in p_raw:
                    p_raw = resolve_json_ref(p_raw["$ref"], doc)

                if not isinstance(p_raw, dict) or "name" not in p_raw or "in" not in p_raw:
                    continue

                p_name = p_raw["name"]
                p_in = p_raw["in"].lower()
                p_req = p_raw.get("required", False)
                p_desc = p_raw.get("description")
                
                # Extract type & default
                schema_info = p_raw.get("schema", {})
                p_type = schema_info.get("type", p_raw.get("type", "string"))
                p_default = schema_info.get("default", p_raw.get("default"))

                if p_in in [loc.value for loc in ParameterLocation]:
                    param_loc = ParameterLocation(p_in)
                    discovered_params.append(
                        DiscoveredParameter(
                            name=p_name,
                            location=param_loc,
                            required=p_req,
                            schema_type=str(p_type),
                            description=p_desc,
                            default_value=p_default
                        )
                    )

                    # Map into default dictionaries
                    placeholder_val = p_default if p_default is not None else (1 if p_type == "integer" else f"sample_{p_name}")
                    if param_loc == ParameterLocation.PATH:
                        path_params[p_name] = placeholder_val
                    elif param_loc == ParameterLocation.QUERY:
                        query_params[p_name] = placeholder_val
                    elif param_loc == ParameterLocation.HEADER:
                        header_params[p_name] = str(placeholder_val)

            # Extract Request Body Schema (OpenAPI 3 vs Swagger 2)
            body_schema = None
            body_type = "json"
            if "requestBody" in op_data:
                rb = op_data["requestBody"]
                if isinstance(rb, dict) and "$ref" in rb:
                    rb = resolve_json_ref(rb["$ref"], doc)
                
                content_map = rb.get("content", {})
                for mime in ("application/json", "application/x-www-form-urlencoded", "multipart/form-data"):
                    if mime in content_map:
                        raw_s = content_map[mime].get("schema", {})
                        body_schema = dereference_schema(raw_s, doc)
                        body_type = "form-data" if "form" in mime else "json"
                        break
            else:
                # Check Swagger 2.0 body parameter
                for p_raw in all_params_raw:
                    if isinstance(p_raw, dict) and p_raw.get("in") == "body" and "schema" in p_raw:
                        body_schema = dereference_schema(p_raw["schema"], doc)
                        body_type = "json"
                        break

            # Extract Response Schemas & Expected Status Code
            response_schemas: Dict[str, Any] = {}
            expected_status = 200

            responses_dict = op_data.get("responses", {})
            for status_code_key, resp_data in responses_dict.items():
                if isinstance(resp_data, dict) and "$ref" in resp_data:
                    resp_data = resolve_json_ref(resp_data["$ref"], doc)

                if not isinstance(resp_data, dict):
                    continue

                # OpenAPI 3 response content
                if "content" in resp_data:
                    json_content = resp_data["content"].get("application/json", {})
                    if "schema" in json_content:
                        response_schemas[str(status_code_key)] = dereference_schema(json_content["schema"], doc)
                elif "schema" in resp_data:
                    # Swagger 2.0 response schema
                    response_schemas[str(status_code_key)] = dereference_schema(resp_data["schema"], doc)

            # Determine default expected status code
            for candidate in ("200", "201", "202", "204"):
                if candidate in responses_dict:
                    expected_status = int(candidate)
                    break

            discovered_ops.append(
                DiscoveredOperation(
                    path=path_str,
                    method=method.upper(),
                    summary=summary,
                    description=op_desc,
                    operation_id=op_id,
                    tags=tags,
                    parameters=discovered_params,
                    path_parameters=path_params,
                    query_parameters=query_params,
                    header_parameters=header_params,
                    request_body_type=body_type,
                    request_body_schema=body_schema,
                    response_schemas=response_schemas,
                    expected_status_code=expected_status
                )
            )

    return ParsedOpenApiSummary(
        title=title,
        version=version,
        spec_version=spec_version,
        description=description,
        servers=servers,
        total_operations=len(discovered_ops),
        operations=discovered_ops
    )
