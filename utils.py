"""
Utility functions for the voice AI agent.
"""
import json
from typing import Dict, Any, Union, Optional
from models import CALL_STATE


def normalize_event_to_dict(event: Any) -> Dict[str, Any]:
    """Convert various event formats to a dictionary."""
    if isinstance(event, dict):
        return event
    if isinstance(event, (str, bytes, bytearray)):
        try:
            return json.loads(event if isinstance(event, str) else event.decode())
        except Exception:
            return {"type": "unknown", "raw": repr(event)}

    model_dump = getattr(event, "model_dump", None)
    if callable(model_dump):
        try:
            return model_dump()
        except Exception:
            pass

    data_attr = getattr(event, "data", None)
    if isinstance(data_attr, dict):
        return data_attr

    json_method = getattr(event, "json", None)
    if callable(json_method):
        try:
            return json.loads(event.json())
        except Exception:
            pass

    return {"type": "unknown", "raw": repr(event)}


def safe_parse_arguments(args: Union[str, Dict[str, Any], None]) -> Dict[str, Any]:
    """Safely parse function call arguments from various formats."""
    if args is None:
        return {}
    if isinstance(args, dict):
        return args
    if isinstance(args, (str, bytes, bytearray)):
        try:
            return json.loads(args if isinstance(args, str) else args.decode())
        except Exception:
            return {}
    return {}


def get_callers_full_name_for_stream(stream_sid: Optional[str]) -> Optional[str]:
    """Get the caller's full name from the call state."""
    if not stream_sid:
        return None
    state = CALL_STATE.get(stream_sid)
    return state.data.get("patient_name") if state else None


async def safe_task(coro):
    """Execute a coroutine with error handling."""
    try:
        await coro
    except Exception as e:
        pass
        # Print the full exception to get more details
        # print(f"Task error: {e}", flush=True)
