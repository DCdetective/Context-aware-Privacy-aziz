"""
Execution Agent – Handles appointment booking workflow and task execution.

Provides:
- Appointment booking with validation
- Date/time parsing (natural language)
- Specialty validation
- Doctor assignment from synthetic data
- Follow-up and summary execution
"""

import json
import re
import uuid
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# Try imports - graceful fallback for testing
try:
    from groq import Groq
    from utils.config import settings
    GROQ_AVAILABLE = True
except Exception:
    GROQ_AVAILABLE = False

try:
    from rag.synthetic_data import synthetic_data_loader
    SYNTHETIC_DATA_AVAILABLE = True
except Exception:
    SYNTHETIC_DATA_AVAILABLE = False

try:
    from database.identity_vault import identity_vault
    VAULT_AVAILABLE = True
except Exception:
    VAULT_AVAILABLE = False

# Known specialties
VALID_SPECIALTIES = {
    "cardiology", "general_medicine", "general", "neurology", "respiratory",
    "pediatrics", "orthopedics", "dermatology", "gastroenterology",
    "endocrinology", "oncology", "urology", "psychiatry", "ophthalmology",
}

# Specialty aliases
SPECIALTY_ALIASES = {
    "heart": "cardiology", "cardiac": "cardiology",
    "brain": "neurology", "neurological": "neurology", "headache": "neurology",
    "breathing": "respiratory", "lung": "respiratory", "pulmonology": "respiratory",
    "skin": "dermatology",
    "bone": "orthopedics", "joint": "orthopedics",
    "stomach": "gastroenterology", "digestive": "gastroenterology", "gi": "gastroenterology",
    "children": "pediatrics", "child": "pediatrics",
    "general medicine": "general_medicine", "gp": "general_medicine",
    "hormone": "endocrinology", "diabetes": "endocrinology",
}


class ExecutionAgent:
    """
    Execution Agent that handles appointment booking and task execution.

    Supports:
    - Complete appointment workflow with validation
    - Natural language date/time parsing
    - Specialty validation against hospital system
    - Doctor assignment from synthetic data
    - Follow-up scheduling
    - Summary generation
    """

    def __init__(self):
        """Initialize Execution Agent."""
        self.model = "rule-based"
        self._groq_client = None

        if GROQ_AVAILABLE:
            try:
                self._groq_client = Groq(api_key=settings.groq_api_key)
                self.model = "llama-3.3-70b-versatile"
            except Exception:
                pass

        self._appointments: Dict[str, Dict[str, Any]] = {}
        logger.info("Execution Agent initialized")

    # ── Appointment Booking ───────────────────────────────────────────

    async def book_appointment(
        self,
        patient_uuid: str,
        doctor_specialty: str,
        preferred_date: str,
        preferred_time: str,
        reason: str,
        additional_info: Optional[dict] = None
    ) -> dict:
        """
        Execute appointment booking.

        Args:
            patient_uuid: Patient UUID
            doctor_specialty: Medical specialty
            preferred_date: Preferred date string
            preferred_time: Preferred time string
            reason: Reason for visit
            additional_info: Optional additional info (doctor assignment etc.)

        Returns:
            Booking result dict
        """
        appointment_id = f"APT-{uuid.uuid4().hex[:8].upper()}"

        doctor = additional_info.get("doctor", {}) if additional_info else {}
        if not doctor:
            doctor = self.assign_doctor(doctor_specialty)

        # Store appointment
        appointment = {
            "appointment_id": appointment_id,
            "patient_uuid": patient_uuid,
            "specialty": doctor_specialty,
            "date": preferred_date,
            "time": preferred_time,
            "reason": reason,
            "doctor": doctor,
            "status": "confirmed",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._appointments[appointment_id] = appointment

        # Store in identity vault if available
        if VAULT_AVAILABLE:
            try:
                identity_vault.store_medical_record(
                    patient_uuid=patient_uuid,
                    record_type="appointment",
                    symptoms=reason,
                    notes=f"Appointment {appointment_id}: {doctor_specialty} with {doctor.get('name', 'TBD')} on {preferred_date} at {preferred_time}",
                    component="execution_agent"
                )
            except Exception as e:
                logger.warning(f"Failed to store record in vault: {e}")

        return {
            "success": True,
            "appointment_id": appointment_id,
            "confirmation": appointment,
            "message": f"Appointment booked successfully! ID: {appointment_id}. "
                       f"{doctor.get('name', 'Doctor')} ({doctor_specialty}) on {preferred_date} at {preferred_time}."
        }

    # ── Validation Methods ────────────────────────────────────────────

    def validate_specialty(self, specialty: str) -> bool:
        """Check if specialty is valid."""
        s = specialty.lower().strip()
        if s in VALID_SPECIALTIES:
            return True
        if s in SPECIALTY_ALIASES:
            return True
        # Check synthetic data
        if SYNTHETIC_DATA_AVAILABLE:
            mapping = synthetic_data_loader.doctors.get("specialty_mapping", {})
            if s in mapping:
                return True
        return False

    def normalize_specialty(self, specialty: str) -> str:
        """Normalize specialty name to canonical form."""
        s = specialty.lower().strip()
        if s in VALID_SPECIALTIES:
            return s
        if s in SPECIALTY_ALIASES:
            return SPECIALTY_ALIASES[s]
        if SYNTHETIC_DATA_AVAILABLE:
            mapping = synthetic_data_loader.doctors.get("specialty_mapping", {})
            if s in mapping:
                return mapping[s]
        return s

    def get_available_specialties(self) -> List[str]:
        """Get list of available specialties."""
        specs = list(VALID_SPECIALTIES)
        if SYNTHETIC_DATA_AVAILABLE:
            doctors = synthetic_data_loader.doctors.get("doctors", [])
            for d in doctors:
                s = d.get("specialty", "")
                if s and s not in specs:
                    specs.append(s)
        return sorted(specs)

    def parse_date(self, date_str: str) -> dict:
        """
        Parse natural language date string.

        Returns: {"valid": bool, "date": str (YYYY-MM-DD), "error": str}
        """
        today = datetime.now().date()
        s = date_str.lower().strip()

        # Natural language dates
        if s in ("today",):
            return {"valid": True, "date": today.isoformat(), "error": ""}
        if s in ("tomorrow", "tmrw"):
            d = today + timedelta(days=1)
            return {"valid": True, "date": d.isoformat(), "error": ""}

        # "next Monday", "next Tuesday", etc.
        days_map = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                    "friday": 4, "saturday": 5, "sunday": 6}
        for day_name, day_num in days_map.items():
            if day_name in s:
                days_ahead = (day_num - today.weekday()) % 7
                if days_ahead == 0:
                    days_ahead = 7  # Next week
                d = today + timedelta(days=days_ahead)
                return {"valid": True, "date": d.isoformat(), "error": ""}

        # "next week"
        if "next week" in s:
            d = today + timedelta(days=7)
            return {"valid": True, "date": d.isoformat(), "error": ""}

        # Try parsing specific date formats
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%B %d, %Y", "%B %d %Y",
                     "%b %d, %Y", "%b %d %Y", "%d %B %Y", "%d %b %Y"):
            try:
                parsed = datetime.strptime(date_str.strip(), fmt).date()
                if parsed < today:
                    return {"valid": False, "date": "", "error": "Date must be in the future. Please provide a future date."}
                return {"valid": True, "date": parsed.isoformat(), "error": ""}
            except ValueError:
                continue

        return {"valid": False, "date": "", "error": f"Could not parse date '{date_str}'. Please use a format like 'Tomorrow', 'next Monday', or 'YYYY-MM-DD'."}

    def parse_time(self, time_str: str) -> dict:
        """
        Parse natural language time string.
        Business hours: 9 AM - 5 PM.

        Returns: {"valid": bool, "time": str (HH:MM), "error": str}
        """
        s = time_str.lower().strip()

        # Natural language times
        if s in ("morning",):
            return {"valid": True, "time": "09:00", "error": ""}
        if s in ("afternoon",):
            return {"valid": True, "time": "14:00", "error": ""}
        if s in ("evening",):
            return {"valid": False, "time": "", "error": "Evening appointments are outside business hours (9 AM - 5 PM). Please choose a time between 9 AM and 5 PM."}

        # Parse "2 PM", "2:00 PM", "14:00", etc.
        # Pattern: "H:MM AM/PM" or "H AM/PM"
        match = re.match(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?', s, re.IGNORECASE)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2)) if match.group(2) else 0
            ampm = match.group(3)

            if ampm:
                ampm = ampm.lower().replace('.', '')
                if ampm == 'pm' and hour != 12:
                    hour += 12
                elif ampm == 'am' and hour == 12:
                    hour = 0

            # Validate business hours (9-17)
            if hour < 9 or hour >= 17:
                return {"valid": False, "time": "",
                        "error": f"Time {hour}:{minute:02d} is outside business hours (9 AM - 5 PM). Please choose a valid time."}

            return {"valid": True, "time": f"{hour:02d}:{minute:02d}", "error": ""}

        return {"valid": False, "time": "", "error": f"Could not parse time '{time_str}'. Please use format like '2 PM', '14:00', or 'morning'."}

    # ── Doctor Assignment ─────────────────────────────────────────────

    def assign_doctor(self, specialty: str) -> dict:
        """
        Assign a doctor based on specialty.

        Args:
            specialty: Medical specialty

        Returns:
            Doctor info dict
        """
        normalized = self.normalize_specialty(specialty)

        if SYNTHETIC_DATA_AVAILABLE:
            doctors = synthetic_data_loader.get_doctor_by_specialty(normalized)
            if doctors:
                doctor = doctors[0]
                return {
                    "doctor_id": doctor.get("doctor_id", ""),
                    "name": doctor.get("name", ""),
                    "specialty": doctor.get("specialty", normalized),
                    "available_days": doctor.get("available_days", []),
                    "consultation_duration": doctor.get("consultation_duration", 30),
                }

        # Fallback
        return {
            "doctor_id": f"DOC-{uuid.uuid4().hex[:4].upper()}",
            "name": f"Dr. Available ({normalized})",
            "specialty": normalized,
            "available_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
            "consultation_duration": 30,
        }

    # ── Follow-up Methods (Prompt 7) ─────────────────────────────────

    async def get_patient_followup(
        self,
        patient_uuid: str,
        question: str = None
    ) -> dict:
        """
        Retrieve patient status and history for follow-up.

        Returns: {
            "patient_info": dict,
            "recent_appointments": List[dict],
            "recent_symptoms": List[dict],
            "follow_up_summary": str,
            "requires_update": bool
        }
        """
        from agents.context_agent import context_agent

        # Get all patient history filtered by UUID
        all_history = context_agent.retrieve_patient_history(patient_uuid, limit=100)

        # Categorize interactions
        appointments = [h for h in all_history if h["metadata"]["type"] == "appointment"]
        symptoms = [h for h in all_history if h["metadata"]["type"] == "symptom"]
        followups = [h for h in all_history if h["metadata"]["type"] == "followup"]

        # Build patient info
        patient_info = {"patient_uuid": patient_uuid}
        if VAULT_AVAILABLE:
            try:
                identity = identity_vault.reidentify_patient(patient_uuid, component="execution_agent")
                if identity:
                    patient_info["patient_name"] = identity.get("patient_name")
                    patient_info["age"] = identity.get("age")
                    patient_info["gender"] = identity.get("gender")
            except Exception:
                pass

        # Generate summary text
        summary_parts = []
        if not all_history:
            summary_parts.append(f"No history found for patient {patient_uuid[:8]}.")
            follow_up_summary = " ".join(summary_parts)
            return {
                "patient_info": patient_info,
                "recent_appointments": [],
                "recent_symptoms": [],
                "recent_followups": [],
                "follow_up_summary": follow_up_summary,
                "requires_update": False,
                "total_interactions": 0,
                "no_history": True,
            }

        summary_parts.append(f"Patient {patient_uuid[:8]} has {len(all_history)} interactions.")
        if appointments:
            summary_parts.append(f"{len(appointments)} appointment(s).")
            most_recent_apt = appointments[0]
            summary_parts.append(
                f"Most recent appointment: {most_recent_apt['metadata']['content'][:100]}"
            )
        if symptoms:
            summary_parts.append(f"{len(symptoms)} symptom report(s).")
        if followups:
            summary_parts.append(f"{len(followups)} follow-up(s).")

        follow_up_summary = " ".join(summary_parts)

        # If a question was asked, try to find relevant data
        if question:
            relevant = context_agent.semantic_search(question, patient_uuid=patient_uuid, top_k=3)
            if relevant:
                follow_up_summary += " Relevant findings: " + "; ".join(
                    r["metadata"]["content"][:80] for r in relevant
                )

        return {
            "patient_info": patient_info,
            "recent_appointments": appointments[:5],
            "recent_symptoms": symptoms[:5],
            "recent_followups": followups[:5],
            "follow_up_summary": follow_up_summary,
            "requires_update": bool(question and "update" in (question or "").lower()),
            "total_interactions": len(all_history),
            "no_history": False,
        }

    async def update_patient_status(
        self,
        patient_uuid: str,
        status_update: str,
        medical_notes: str = None
    ) -> dict:
        """
        Update patient's medical status.
        Stores in context agent (vector store) with proper metadata.

        Returns result dict.
        """
        from agents.context_agent import context_agent

        # Extract status details from update text
        updates_extracted = self._extract_status_updates(status_update)

        # Store the follow-up update as a new interaction
        vector_id = context_agent.store_interaction(
            patient_uuid=patient_uuid,
            interaction_type="followup",
            content=f"Status update: {status_update}",
            metadata={
                "update_type": "status_update",
                "notes": medical_notes or "",
                "updates": str(updates_extracted),
            }
        )

        # Also store in vault if available
        record_id = None
        if VAULT_AVAILABLE:
            try:
                record_id = identity_vault.store_medical_record(
                    patient_uuid=patient_uuid,
                    record_type="followup",
                    treatment_plan=status_update,
                    notes=medical_notes or "",
                    component="execution_agent"
                )
            except Exception as e:
                logger.warning(f"Failed to store in vault: {e}")

        return {
            "success": True,
            "patient_uuid": patient_uuid,
            "vector_id": vector_id,
            "record_id": record_id,
            "updates_extracted": updates_extracted,
            "message": f"Status update stored for patient {patient_uuid[:8]}."
        }

    def _extract_status_updates(self, text: str) -> List[dict]:
        """Extract structured status updates from natural language text."""
        updates = []
        text_lower = text.lower()

        # Detect improvement
        improvement_words = ["better", "improved", "recovering", "gone", "resolved", "cleared"]
        worsening_words = ["worse", "worsening", "increased", "severe", "not improving"]

        # Common symptoms to look for
        symptom_words = ["fever", "cough", "headache", "pain", "nausea", "fatigue",
                         "dizziness", "rash", "swelling", "breathing"]

        for symptom in symptom_words:
            if symptom in text_lower:
                status = "unknown"
                if any(w in text_lower for w in improvement_words):
                    # Check if "still has" or "but" modifies this symptom
                    # e.g., "fever is gone but still has cough"
                    # Simple heuristic: check proximity
                    idx = text_lower.index(symptom)
                    context_before = text_lower[max(0, idx - 40):idx]
                    context_after = text_lower[idx:min(len(text_lower), idx + 40)]

                    if any(w in context_before or w in context_after for w in ["still", "but", "however"]):
                        if any(w in context_after for w in improvement_words):
                            status = "improved"
                        elif any(w in context_after for w in ["still"]):
                            status = "ongoing"
                        else:
                            status = "ongoing"
                    else:
                        status = "improved"
                if any(w in text_lower for w in worsening_words):
                    idx = text_lower.index(symptom)
                    context_after = text_lower[idx:min(len(text_lower), idx + 40)]
                    if any(w in context_after for w in worsening_words):
                        status = "worsened"

                # Refined: "gone" near symptom means resolved
                idx = text_lower.index(symptom)
                nearby = text_lower[max(0, idx - 20):min(len(text_lower), idx + 30)]
                if "gone" in nearby or "resolved" in nearby or "cleared" in nearby:
                    status = "resolved"
                elif "still" in nearby:
                    status = "ongoing"

                updates.append({
                    "symptom": symptom,
                    "status": status,
                })

        if not updates:
            # Generic update
            updates.append({
                "symptom": "general",
                "status": "updated",
                "detail": text[:200]
            })

        return updates

    # ── Legacy execute_task (backward compatibility) ──────────────────

    def execute_task(
        self,
        patient_uuid: str,
        intent: str,
        refined_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a medical task (legacy interface)."""
        logger.info(f"EXECUTION AGENT: Executing {intent} for {patient_uuid[:8]}...")

        rag_context = refined_context.get('rag_context', {})

        if intent == "appointment":
            return self._handle_appointment(patient_uuid, refined_context)
        elif intent == "followup":
            return self._handle_followup(patient_uuid, refined_context)
        elif intent == "summary":
            return self._handle_summary(patient_uuid, refined_context)
        else:
            return self._handle_general(patient_uuid, refined_context)

    def _handle_appointment(self, patient_uuid: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
        urgency = ctx.get('urgency_assessment', 'routine')
        if urgency == "emergency":
            apt_time = datetime.now() + timedelta(hours=2)
        elif urgency == "urgent":
            apt_time = datetime.now() + timedelta(days=1)
        else:
            apt_time = datetime.now() + timedelta(days=7)

        duration = ctx.get('estimated_duration', 30)

        if VAULT_AVAILABLE:
            record_id = identity_vault.store_medical_record(
                patient_uuid=patient_uuid, record_type="appointment",
                symptoms=f"Category: {ctx.get('recommended_specialty', 'general')}",
                notes=ctx.get('reasoning', ''), component="execution_agent")
        else:
            record_id = str(uuid.uuid4())

        return {
            "success": True, "intent": "appointment", "patient_uuid": patient_uuid,
            "appointment_time": apt_time.isoformat(), "consultation_duration": duration,
            "urgency_level": urgency,
            "recommended_specialty": ctx.get('recommended_specialty'),
            "recommended_doctor": ctx.get('recommended_doctor'),
            "record_id": record_id,
            "message": f"Appointment scheduled for patient {patient_uuid[:8]}..."
        }

    def _handle_followup(self, patient_uuid: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
        followup_time = datetime.now() + timedelta(days=14)

        if VAULT_AVAILABLE:
            record_id = identity_vault.store_medical_record(
                patient_uuid=patient_uuid, record_type="followup",
                treatment_plan="Follow-up based on previous visit",
                notes=ctx.get('reasoning', ''), component="execution_agent")
            records = identity_vault.get_patient_records(patient_uuid)
        else:
            record_id = str(uuid.uuid4())
            records = []

        return {
            "success": True, "intent": "followup", "patient_uuid": patient_uuid,
            "followup_time": followup_time.isoformat(),
            "previous_visits": len(records), "record_id": record_id,
            "message": f"Follow-up scheduled for patient {patient_uuid[:8]}..."
        }

    def _handle_summary(self, patient_uuid: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
        if VAULT_AVAILABLE:
            records = identity_vault.get_patient_records(patient_uuid)
            record_id = identity_vault.store_medical_record(
                patient_uuid=patient_uuid, record_type="summary",
                diagnosis=f"Patient {patient_uuid[:8]}... has {len(records)} records.",
                component="execution_agent")
        else:
            records = []
            record_id = str(uuid.uuid4())

        return {
            "success": True, "intent": "summary", "patient_uuid": patient_uuid,
            "summary": {"total_visits": len(records),
                        "summary_text": f"Patient {patient_uuid[:8]}... has {len(records)} records."},
            "record_id": record_id,
            "message": f"Summary generated for patient {patient_uuid[:8]}..."
        }

    def _handle_general(self, patient_uuid: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "success": True, "intent": "general", "patient_uuid": patient_uuid,
            "message": "I can help with appointments, follow-ups, or summaries. What would you like?",
            "suggestions": ["Book an appointment", "Schedule a follow-up", "Generate summary"]
        }


# Global instance
execution_agent = ExecutionAgent()
