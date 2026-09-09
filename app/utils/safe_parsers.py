"""Safe parsing utilities providing robust JSON, YAML, and XML decoders with zero-crash guarantees."""
import json
import xml.etree.ElementTree as ET
from typing import Any, Dict, Optional, Tuple
import yaml


def safe_json_loads(data: Any, default: Any = None) -> Tuple[Optional[Any], Optional[str]]:
    """Parse JSON string safely, returning (parsed_object, error_message)."""
    if data is None:
        return default, None
    if isinstance(data, (dict, list)):
        return data, None
    if not isinstance(data, str):
        data = str(data)

    trimmed = data.strip()
    if not trimmed:
        return default, None

    try:
        parsed = json.loads(trimmed)
        return parsed, None
    except json.JSONDecodeError as exc:
        return default, f"JSON parse error at line {exc.lineno}, col {exc.colno}: {exc.msg}"
    except Exception as exc:
        return default, f"Unexpected JSON parse error: {str(exc)}"


def safe_yaml_loads(data: Any, default: Any = None) -> Tuple[Optional[Any], Optional[str]]:
    """Parse YAML string safely, returning (parsed_object, error_message)."""
    if data is None:
        return default, None
    if isinstance(data, (dict, list)):
        return data, None
    if not isinstance(data, str):
        data = str(data)

    trimmed = data.strip()
    if not trimmed:
        return default, None

    try:
        parsed = yaml.safe_load(trimmed)
        return parsed, None
    except yaml.YAMLError as exc:
        return default, f"YAML parse error: {str(exc)}"
    except Exception as exc:
        return default, f"Unexpected YAML parse error: {str(exc)}"


def safe_xml_loads(data: Any, default: Any = None) -> Tuple[Optional[ET.Element], Optional[str]]:
    """Parse XML string safely, returning (root_element, error_message)."""
    if data is None:
        return default, None
    if not isinstance(data, str):
        data = str(data)

    trimmed = data.strip()
    if not trimmed:
        return default, None

    try:
        root = ET.fromstring(trimmed)
        return root, None
    except ET.ParseError as exc:
        return default, f"XML parse error: {str(exc)}"
    except Exception as exc:
        return default, f"Unexpected XML parse error: {str(exc)}"


def safe_decode_payload(raw_bytes: bytes, encoding: str = "utf-8") -> str:
    """Decode raw bytes with automatic encoding fallback."""
    if not raw_bytes:
        return ""
    try:
        return raw_bytes.decode(encoding)
    except (UnicodeDecodeError, LookupError):
        try:
            return raw_bytes.decode("utf-8", errors="replace")
        except Exception:
            return str(raw_bytes)
