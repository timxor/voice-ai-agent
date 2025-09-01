"""
Appointment and provider management service.
"""
from typing import Dict, Any, List


class AppointmentService:
    """Service for managing providers and appointment slots."""
    
    # Fake providers for demonstration
    FAKE_PROVIDERS = [
        {"doctor": "Dr. Frank Smith", "specialty": "Primary Care"},
        {"doctor": "Dr. Jessica Nguyen", "specialty": "Internal Medicine"},
        {"doctor": "Dr. Sarah Chen", "specialty": "Family Medicine"},
    ]

    # Fake appointment slots for demonstration
    FAKE_SLOTS = [
        {"start": "2025-08-22T09:00:00-05:00", "end": "2025-08-22T09:20:00-05:00"},
        {"start": "2025-08-22T10:40:00-05:00", "end": "2025-08-22T11:00:00-05:00"},
        {"start": "2025-08-22T13:30:00-05:00", "end": "2025-08-22T13:50:00-05:00"},
        {"start": "2025-08-23T11:10:00-05:00", "end": "2025-08-23T11:30:00-05:00"},
    ]

    @classmethod
    def get_available_appointments(cls) -> List[Dict[str, Any]]:
        """
        Get all available appointment slots by combining providers and time slots.
        Returns a list of appointment options.
        """
        appointments = []
        for provider in cls.FAKE_PROVIDERS:
            for slot in cls.FAKE_SLOTS:
                appointments.append({
                    "doctor": provider["doctor"],
                    "specialty": provider["specialty"],
                    "start": slot["start"],
                    "end": slot["end"],
                })
        return appointments