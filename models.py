"""
Data models for the voice AI agent.
"""
import json
from typing import Dict, Any
from config import REQUIRED_FIELDS


class IntakeState:
    """Manages the state of patient intake information during a call."""
    
    def __init__(self):
        self.data: Dict[str, Any] = {k: None for k in REQUIRED_FIELDS.keys()}

    def update(self, **kwargs):
        """Update the intake state with new data."""
        self.data.update(**kwargs)

    def is_complete(self) -> bool:
        """Check if all required fields have been collected."""
        required = [
            "patient_name",
            "date_of_birth",
            "insurance_payer_name",
            "insurance_payer_id",
            "has_referral",
            "chief_complaint",
            "address",
            "address_is_valid",
            "phone",
            "appointment_slot",
        ]
        if self.data.get("has_referral") is True:
            required.append("referring_physician")
        return all(self.data.get(k) not in (None, "") for k in required)

    def to_json(self) -> str:
        """Convert the intake state to JSON string."""
        return json.dumps(self.data, ensure_ascii=False)


# Global call state storage
CALL_STATE: Dict[str, IntakeState] = {}