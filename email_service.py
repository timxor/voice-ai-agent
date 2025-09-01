"""
Email service for sending appointment confirmations.
"""
import resend
from typing import Dict, Any, Optional, cast
from config import RESEND_FROM, BOOKING_RECIPIENTS
from models import IntakeState


class EmailService:
    """Service for sending email notifications."""

    @staticmethod
    def send_confirmation_email(appointment: Dict[str, Any], state: IntakeState) -> Optional[str]:
        """
        Send appointment confirmation email.
        Returns None on success, error message on failure.
        """
        try:
            subject = f"New Appointment — {appointment.get('doctor')} @ {appointment.get('start')}"
            html = f"""
            <h2>Tim's Voice AI Agent — New Appointment Reserved</h2>
            <p><strong>Patient:</strong> {state.data.get('patient_name')}<br/>
            <strong>DOB:</strong> {state.data.get('date_of_birth')}<br/>
            <strong>Phone:</strong> {state.data.get('phone')}<br/>
            <strong>Email:</strong> {state.data.get('email') or '—'}<br/>
            <strong>Insurance:</strong> {state.data.get('insurance_payer_name')} (ID: {state.data.get('insurance_payer_id')})<br/>
            <strong>Referral:</strong> {state.data.get('has_referral')}<br/>
            <strong>Referring Physician:</strong> {state.data.get('referring_physician') or '—'}<br/>
            <strong>Chief Complaint:</strong> {state.data.get('chief_complaint')}<br/>
            <strong>Address:</strong> {state.data.get('address')}<br/>
            <strong>Address Valid:</strong> {state.data.get('address_is_valid')}</p>
            <p><strong>Doctor:</strong> {appointment.get('doctor')}<br/>
            <strong>Specialty:</strong> {appointment.get('specialty') or '—'}<br/>
            <strong>Start:</strong> {appointment.get('start')}<br/>
            <strong>End:</strong> {appointment.get('end')}</p>
            """
            payload: Dict[str, Any] = {
                "from": RESEND_FROM,
                "to": BOOKING_RECIPIENTS,
                "subject": subject,
                "html": html
            }
            resend.Emails.send(cast(Dict[str, Any], payload))
            return None
        except Exception as e:
            return str(e)
