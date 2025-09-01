
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class CallState:
    """
    Mutable per-call state shared between the Twilio receiver and the
    OpenAI sender tasks.
    """
    stream_sid: Optional[str] = None
    latest_media_timestamp: int = 0  # ms (from Twilio media events)
    last_assistant_item: Optional[str] = None
    mark_queue: List[str] = field(default_factory=list)
    response_start_timestamp_twilio: Optional[int] = None  # ms
