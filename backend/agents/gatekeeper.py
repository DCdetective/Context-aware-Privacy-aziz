"""
Privacy Agent (Gatekeeper) – Intercepts and anonymizes PII before cloud services.

Provides:
    Gatekeeper class with anonymize_text, deanonymize_text, detect_pii_entities
    Privacy event streaming
    Patient linking
    Local LLM integration with regex fallback

Also keeps the legacy GatekeeperAgent class for backward compatibility.
"""

import json
import re
import logging
import threading
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timezone

from utils.pii_patterns import (
    detect_phones, detect_ssns, detect_addresses, detect_ages,
    is_doctor_reference, MEDICAL_TITLE_PREFIXES,
)

logger = logging.getLogger(__name__)


# ── Age bucket conversion (shared) ────────────────────────────────────

def _age_to_bucket(age: int) -> str:
    """Convert exact age to privacy-safe age bucket."""
    if age <= 12:
        return "child"
    elif age <= 17:
        return "teenager"
    elif age <= 25:
        return "early 20s"
    elif age <= 35:
        return "late 20s to early 30s"
    elif age <= 50:
        return "middle-aged"
    elif age <= 65:
        return "senior"
    else:
        return "elderly"


# ── Gatekeeper (Prompt 3) ─────────────────────────────────────────────

class Gatekeeper:
    """
    Privacy Agent that intercepts all data before it goes to cloud services
    and anonymizes PII in real-time.

    Supports:
    - Local LLM integration for PII detection (with regex fallback)
    - Bidirectional anonymize / deanonymize
    - Privacy event streaming
    - Patient linking (consistent anonymized names)
    """

    def __init__(self, local_llm_config: Optional[dict] = None):
        """
        Initialize with optional local LLM config.

        Args:
            local_llm_config: dict with keys 'host' and 'model' for Ollama.
                              If None, regex-only fallback is used.
        """
        self._lock = threading.Lock()
        self._llm_available = False
        self._ollama = None
        self._model = None

        if local_llm_config:
            try:
                import ollama
                self._ollama = ollama
                self._model = local_llm_config.get("model", "llama3.1")
                # Quick connectivity check
                ollama.list()
                self._llm_available = True
                logger.info(f"Gatekeeper: local LLM available ({self._model})")
            except Exception as e:
                logger.warning(f"Gatekeeper: local LLM unavailable, using regex fallback ({e})")
                self._llm_available = False

        # Bidirectional mapping: patient_uuid -> {real_name, anonymized_name}
        self._mappings: Dict[str, Dict[str, str]] = {}
        # Reverse: anonymized_name -> patient_uuid
        self._reverse_map: Dict[str, str] = {}
        # Name -> patient_uuid quick lookup
        self._name_to_uuid: Dict[str, str] = {}
        # Privacy event log
        self._events: List[dict] = []

        # Counter for generating anonymous IDs when no patient_uuid given
        self._anon_counter = 0

        logger.info("Gatekeeper initialized")

    # ── Patient Linking ───────────────────────────────────────────────

    def register_patient(self, patient_uuid: str, real_name: str, anonymized_name: str):
        """Register a known patient mapping for consistent anonymization."""
        with self._lock:
            self._mappings[patient_uuid] = {
                "real_name": real_name,
                "anonymized_name": anonymized_name,
            }
            self._reverse_map[anonymized_name] = patient_uuid
            self._name_to_uuid[real_name.lower()] = patient_uuid

    def _get_anon_name_for_patient(self, patient_uuid: str) -> str:
        """Get anonymized name for a known patient."""
        mapping = self._mappings.get(patient_uuid)
        if mapping:
            return mapping["anonymized_name"]
        return f"Patient_{patient_uuid[:8]}"

    def _resolve_name_to_patient(self, name: str) -> Optional[str]:
        """Try to resolve a detected name to a known patient_uuid."""
        return self._name_to_uuid.get(name.lower())

    def _get_or_create_anon(self, name: str, patient_uuid: Optional[str] = None) -> Tuple[str, Optional[str]]:
        """
        Get or create an anonymized name.
        Returns (anonymized_name, patient_uuid_or_None).
        """
        # If patient_uuid provided, use registered mapping
        if patient_uuid and patient_uuid in self._mappings:
            return self._mappings[patient_uuid]["anonymized_name"], patient_uuid

        # Try to resolve name to existing patient
        resolved_uuid = self._resolve_name_to_patient(name)
        if resolved_uuid:
            return self._mappings[resolved_uuid]["anonymized_name"], resolved_uuid

        # If patient_uuid given but not registered, generate deterministic name
        if patient_uuid:
            anon_name = f"Patient_{patient_uuid[:8]}"
            self.register_patient(patient_uuid, name, anon_name)
            return anon_name, patient_uuid

        # Unknown patient – generate temporary anon name
        with self._lock:
            self._anon_counter += 1
            anon_name = f"Patient_UNK{self._anon_counter:03d}"
        return anon_name, None

    # ── PII Detection ─────────────────────────────────────────────────

    def detect_pii_entities(self, text: str) -> List[dict]:
        """
        Detect PII entities in text: names, ages, phones, addresses, SSNs.

        Returns list of dicts with keys: original, type, start, end, (age_value for ages).
        """
        entities: List[dict] = []

        # Phones
        entities.extend(detect_phones(text))

        # SSNs
        entities.extend(detect_ssns(text))

        # Addresses
        entities.extend(detect_addresses(text))

        # Ages
        entities.extend(detect_ages(text))

        # Names – regex heuristic: capitalized words that aren't medical terms
        entities.extend(self._detect_names_regex(text))

        # Sort by position (start), remove overlapping
        entities.sort(key=lambda e: e["start"])
        entities = self._remove_overlapping(entities)

        return entities

    def _detect_names_regex(self, text: str) -> List[dict]:
        """Detect likely person names via capitalized-word heuristic."""
        results = []
        # Match sequences of capitalized words (first + optional last name)
        name_pattern = re.compile(r'\b([A-Z][a-z]{1,20}(?:\s+[A-Z][a-z]{1,20})*)\b')

        # Words to skip (medical terms, common words, etc.)
        skip_words = {
            "the", "and", "for", "but", "not", "you", "all", "can",
            "her", "was", "one", "our", "out", "are", "has", "his",
            "how", "its", "may", "who", "did", "get", "let", "say",
            # Medical
            "Patient", "Doctor", "Nurse", "Surgeon", "Specialist",
            "Hospital", "Clinic", "Medical", "Health", "Treatment",
            "Diagnosis", "Symptoms", "Appointment", "Emergency",
            "Respiratory", "Cardiac", "Neurological", "Routine",
            "Urgent", "Critical", "Severe", "Chronic", "Acute",
            # Common sentence starters
            "Hello", "Please", "Thank", "Thanks", "Yes", "No",
            "Book", "Schedule", "Need", "Want", "Have", "Call",
            "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
            "Saturday", "Sunday", "January", "February", "March",
            "April", "May", "June", "July", "August", "September",
            "October", "November", "December", "Today", "Tomorrow",
        }

        for match in name_pattern.finditer(text):
            candidate = match.group()
            # Skip single-word matches that are in skip list
            words = candidate.split()
            if len(words) == 1 and words[0] in skip_words:
                continue
            # Skip if all words are skip words
            if all(w in skip_words for w in words):
                continue
            # Skip if preceded by doctor title (don't anonymize doctor names)
            if is_doctor_reference(text, match.start()):
                continue
            # Skip very short single names (likely not a person)
            if len(words) == 1 and len(words[0]) <= 2:
                continue

            results.append({
                "original": candidate,
                "type": "name",
                "start": match.start(),
                "end": match.end(),
            })

        return results

    def _remove_overlapping(self, entities: List[dict]) -> List[dict]:
        """Remove overlapping entities, keeping longer matches."""
        if not entities:
            return entities
        result = [entities[0]]
        for ent in entities[1:]:
            prev = result[-1]
            if ent["start"] >= prev["end"]:
                result.append(ent)
            elif (ent["end"] - ent["start"]) > (prev["end"] - prev["start"]):
                result[-1] = ent
        return result

    # ── Anonymize ─────────────────────────────────────────────────────

    def anonymize_text(self, text: str, patient_uuid: Optional[str] = None) -> dict:
        """
        Anonymize PII in text.

        Returns:
            {
                "anonymized_text": "Patient_123, early 20s...",
                "privacy_events": [
                    {"original": "Aziz", "transformed": "Patient_123", "type": "name"},
                    ...
                ]
            }
        """
        entities = self.detect_pii_entities(text)
        privacy_events: List[dict] = []

        # Process from end to start so indices remain valid
        result = text
        for ent in reversed(entities):
            original = ent["original"]
            ent_type = ent["type"]
            transformed = original  # default: no change

            if ent_type == "name":
                anon_name, resolved_uuid = self._get_or_create_anon(original, patient_uuid)
                transformed = anon_name
            elif ent_type == "age":
                age_val = ent.get("age_value", 0)
                transformed = _age_to_bucket(age_val)
            elif ent_type == "phone":
                transformed = "PHONE_XXX"
            elif ent_type == "address":
                transformed = "residential area"
            elif ent_type == "ssn":
                transformed = "SSN_REDACTED"

            if transformed != original:
                result = result[:ent["start"]] + transformed + result[ent["end"]:]
                privacy_events.append({
                    "original": original,
                    "transformed": transformed,
                    "type": ent_type,
                })

        # Emit privacy event
        if privacy_events:
            event = {
                "event_type": "privacy_transformation",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "patient_uuid": patient_uuid,
                "transformations": [
                    {
                        "original": pe["original"],
                        "transformed": pe["transformed"],
                        "pii_type": pe["type"],
                        "action": "anonymized",
                    }
                    for pe in privacy_events
                ],
            }
            self._events.append(event)

        return {
            "anonymized_text": result,
            "privacy_events": privacy_events,
        }

    # ── Deanonymize ───────────────────────────────────────────────────

    def deanonymize_text(self, text: str, patient_uuid: str) -> str:
        """
        Convert Patient_XXX back to real name (for local display only).
        """
        mapping = self._mappings.get(patient_uuid)
        if not mapping:
            return text

        anon_name = mapping["anonymized_name"]
        real_name = mapping["real_name"]

        result = text.replace(anon_name, real_name)
        return result

    # ── Privacy Event Access ──────────────────────────────────────────

    def get_privacy_events(self) -> List[dict]:
        """Return all recorded privacy events."""
        return list(self._events)

    def clear_privacy_events(self):
        """Clear event log."""
        self._events.clear()

    # ── Convenience / Integration ─────────────────────────────────────

    def process_for_cloud(self, text: str, patient_uuid: Optional[str] = None) -> dict:
        """Anonymize text before sending to cloud LLM."""
        return self.anonymize_text(text, patient_uuid)

    def process_for_storage(self, text: str, patient_uuid: Optional[str] = None) -> dict:
        """Anonymize text before storing in Pinecone."""
        return self.anonymize_text(text, patient_uuid)

    def process_for_display(self, text: str, patient_uuid: str) -> str:
        """Deanonymize text for local display."""
        return self.deanonymize_text(text, patient_uuid)


# ── Legacy GatekeeperAgent class (backward compatibility) ─────────────

class GatekeeperAgent:
    """
    Legacy Gatekeeper Agent.
    Kept for backward compatibility with existing code (main.py, tests, etc.).
    """

    def __init__(self):
        self.model = "llama3.1"
        self.host = "http://localhost:11434"
        try:
            from utils.config import settings
            self.model = settings.ollama_model
            self.host = settings.ollama_host
        except Exception:
            pass
        logger.info(f"GatekeeperAgent initialized with model: {self.model}")

    def _call_ollama(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        try:
            import ollama
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            response = ollama.chat(model=self.model, messages=messages)
            return response['message']['content']
        except Exception as e:
            logger.error(f"Error calling Ollama: {e}")
            raise

    def extract_pii(self, user_message: str) -> Dict[str, Any]:
        logger.info("Extracting PII from user message...")
        system_prompt = """You are a medical information extraction assistant.
Extract patient details from the input and return ONLY a JSON object with these fields:
- patient_name: Full name of the patient (string, or null if not mentioned)
- age: Age as an integer (or null if not mentioned)
- gender: Gender (Male/Female/Other, or null if not mentioned)
- medical_info: Medical symptoms, conditions, or reason for contact (string)

IMPORTANT: If information is not explicitly mentioned, use null. Do not guess.
Return ONLY valid JSON, no additional text."""

        prompt = f'Extract patient information from this message:\n\n"{user_message}"\n\nReturn JSON format only.'
        try:
            response = self._call_ollama(prompt, system_prompt)
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            pii_data = json.loads(json_match.group()) if json_match else json.loads(response)
            pii_data.setdefault('patient_name', None)
            pii_data.setdefault('age', None)
            pii_data.setdefault('gender', None)
            pii_data.setdefault('medical_info', user_message)
            return pii_data
        except Exception:
            return {'patient_name': None, 'age': None, 'gender': None, 'medical_info': user_message}

    def extract_intent(self, user_message: str) -> str:
        system_prompt = """You are an intent classifier for a medical chatbot.
Classify the user's intent into ONE of these categories:
- appointment: User wants to book a new appointment
- followup: User wants to schedule a follow-up visit
- summary: User wants a medical summary or record
- general: General query or unclear intent
Return ONLY the intent word, nothing else."""
        prompt = f'Classify the intent of this message:\n\n"{user_message}"\n\nReturn only: appointment, followup, summary, or general'
        try:
            response = self._call_ollama(prompt, system_prompt).strip().lower()
            for intent in ['appointment', 'followup', 'summary', 'general']:
                if intent in response:
                    return intent
            return 'general'
        except Exception:
            return 'general'

    def extract_semantic_context(self, medical_info: str) -> Dict[str, Any]:
        system_prompt = """Extract semantic medical features from the description.
Return ONLY JSON with these fields (no PII like names/exact ages):
- symptom_category: General category (e.g., "respiratory", "cardiac", "neurological", "general")
- urgency_level: "routine", "urgent", or "emergency"
- requires_specialist: true or false
- estimated_duration: estimated consultation time in minutes (15, 30, 45, or 60)
Return ONLY valid JSON."""
        prompt = f"Analyze this medical information and extract semantic features:\n\nMedical Info: {medical_info}\n\nReturn JSON only."
        try:
            response = self._call_ollama(prompt, system_prompt)
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            data = json.loads(json_match.group()) if json_match else json.loads(response)
            s = json.dumps(data).lower()
            if any(t in s for t in ['name', 'age', 'years old']):
                return self._fallback_semantic_extraction(medical_info)
            return data
        except Exception:
            return self._fallback_semantic_extraction(medical_info)

    def _fallback_semantic_extraction(self, medical_info: str) -> Dict[str, Any]:
        info = medical_info.lower()
        cat = "general"
        if any(t in info for t in ['cough', 'breathing', 'lung', 'respiratory']):
            cat = "respiratory"
        elif any(t in info for t in ['heart', 'cardiac', 'chest pain']):
            cat = "cardiac"
        elif any(t in info for t in ['headache', 'dizzy', 'neurological', 'brain']):
            cat = "neurological"
        elif any(t in info for t in ['stomach', 'digestive', 'nausea', 'abdominal']):
            cat = "digestive"
        urg = "routine"
        if any(t in info for t in ['emergency', 'severe', 'critical', 'immediately']):
            urg = "emergency"
        elif any(t in info for t in ['urgent', 'acute', 'sudden', 'quickly']):
            urg = "urgent"
        return {"symptom_category": cat, "urgency_level": urg,
                "requires_specialist": urg in ["urgent", "emergency"], "estimated_duration": 30}

    def _convert_age_to_group(self, age: Optional[int]) -> str:
        if age is None:
            return "Unknown"
        return _age_to_bucket(age)

    def create_privacy_report(self, pii_data: Dict[str, Any], patient_uuid: str,
                              semantic_context: Dict[str, Any]) -> Dict[str, Any]:
        transformations = []
        if pii_data.get('patient_name'):
            transformations.append({
                "field": "Patient Name", "original": pii_data['patient_name'],
                "transformed": f"Patient_{patient_uuid[:8]}", "method": "UUID Pseudonymization",
            })
        if pii_data.get('age'):
            transformations.append({
                "field": "Age", "original": str(pii_data['age']),
                "transformed": self._convert_age_to_group(pii_data['age']),
                "method": "Age Group Masking",
            })
        if pii_data.get('gender'):
            transformations.append({
                "field": "Gender", "original": pii_data['gender'],
                "transformed": pii_data['gender'], "method": "Retained (non-identifying)",
            })
        transformations.append({
            "field": "Medical Information", "original": "Contains patient details",
            "transformed": f"Semantic category: {semantic_context.get('symptom_category', 'general')}",
            "method": "Semantic Extraction",
        })
        return {
            "transformations": transformations,
            "pii_removed": len([t for t in transformations if t["method"] in ["UUID Pseudonymization", "Age Group Masking"]]),
            "cloud_safe": True, "patient_uuid": patient_uuid,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def pseudonymize_input(self, user_message: str) -> Dict[str, Any]:
        try:
            from utils.config import settings
            testing = settings.testing_mode
        except Exception:
            testing = True

        if testing:
            name_match = re.search(r"patient\s*name\s*:\s*([^,\n]+)", user_message, re.IGNORECASE)
            age_match = re.search(r"age\s*:\s*(\d+)", user_message, re.IGNORECASE)
            gender_match = re.search(r"gender\s*:\s*([^,\n]+)", user_message, re.IGNORECASE)
            symptoms_match = re.search(r"symptoms\s*:\s*(.+)", user_message, re.IGNORECASE | re.DOTALL)
            pii = {
                "patient_name": name_match.group(1).strip() if name_match else None,
                "age": int(age_match.group(1)) if age_match else None,
                "gender": gender_match.group(1).strip() if gender_match else None,
                "medical_info": symptoms_match.group(1).strip() if symptoms_match else user_message,
            }
            semantic_context = self._fallback_semantic_extraction(pii["medical_info"])
            intent = "general"
        else:
            out = self.process_message(user_message)
            pii = out.get("pii", {})
            semantic_context = out.get("semantic_context", {})
            intent = out.get("intent", "general")

        if pii.get("patient_name"):
            from database.identity_vault import identity_vault
            patient_uuid, _ = identity_vault.pseudonymize_patient(
                patient_name=pii["patient_name"], age=pii.get("age"),
                gender=pii.get("gender"), component="gatekeeper",
            )
        else:
            patient_uuid = "temp-uuid-" + str(hash(user_message))[:8]

        return {"patient_uuid": patient_uuid, "semantic_context": semantic_context,
                "intent": intent, "cloud_safe": True}

    def reidentify_output(self, patient_uuid: str, cloud_result: Dict[str, Any]) -> Dict[str, Any]:
        final = dict(cloud_result or {})
        if patient_uuid and not patient_uuid.startswith("temp-uuid"):
            from database.identity_vault import identity_vault
            identity = identity_vault.reidentify_patient(patient_uuid=patient_uuid, component="gatekeeper")
            if identity:
                final.setdefault("patient_uuid", patient_uuid)
                final["patient_name"] = identity.get("patient_name")
                final["patient_age"] = identity.get("age")
                final["patient_gender"] = identity.get("gender")
        return final

    def process_message(self, user_message: str) -> Dict[str, Any]:
        """
        Process user message: extract PII, intent, and semantic context.
        Uses a SINGLE combined LLM call for speed, with regex fallback.
        """
        logger.info("GATEKEEPER: Processing user message")

        # Try single combined LLM call for all extractions at once
        pii_data = None
        intent = None
        semantic_context = None

        try:
            combined = self._extract_all_combined(user_message)
            if combined:
                pii_data = combined.get('pii', {})
                intent = combined.get('intent', 'general')
                semantic_context = combined.get('semantic_context', {})
        except Exception as e:
            logger.warning(f"Combined extraction failed, using sequential fallback: {e}")

        # Fallback: individual calls if combined failed
        if pii_data is None:
            pii_data = self.extract_pii(user_message)
        if intent is None:
            intent = self.extract_intent(user_message)
        if semantic_context is None:
            semantic_context = self.extract_semantic_context(pii_data.get('medical_info', user_message))

        # Ensure defaults
        pii_data.setdefault('patient_name', None)
        pii_data.setdefault('age', None)
        pii_data.setdefault('gender', None)
        pii_data.setdefault('medical_info', user_message)

        privacy_report = None
        if pii_data.get('patient_name'):
            temp_uuid = str(abs(hash(pii_data['patient_name'])))[:8]
            privacy_report = self.create_privacy_report(pii_data, temp_uuid, semantic_context)

        return {
            'pii': pii_data, 'intent': intent, 'semantic_context': semantic_context,
            'privacy_report': privacy_report, 'original_message': user_message, 'cloud_safe': True,
        }

    def _extract_all_combined(self, user_message: str) -> Optional[Dict[str, Any]]:
        """
        Extract PII, intent, and semantic context in a SINGLE LLM call.
        Returns None if LLM is unavailable.
        """
        system_prompt = """You are a medical information extraction assistant.
From the user message, extract ALL of the following in a single JSON response:

{
  "pii": {
    "patient_name": "Full name or null",
    "age": integer or null,
    "gender": "Male/Female/Other or null",
    "medical_info": "medical symptoms/conditions/reason"
  },
  "intent": "appointment|followup|summary|general",
  "semantic_context": {
    "symptom_category": "respiratory|cardiac|neurological|digestive|general",
    "urgency_level": "routine|urgent|emergency",
    "requires_specialist": true/false,
    "estimated_duration": 15|30|45|60
  }
}

RULES:
- If info is not mentioned, use null
- Do not guess names or ages
- intent: appointment=booking new visit, followup=check on existing patient, summary=medical history request, general=anything else
- Return ONLY valid JSON, no extra text"""

        prompt = f'Extract from this message:\n\n"{user_message}"\n\nReturn JSON only.'

        try:
            response = self._call_ollama(prompt, system_prompt)
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                # Validate structure
                if 'pii' in data and 'intent' in data:
                    # Sanitize: ensure no PII leaks into semantic_context
                    sc = data.get('semantic_context', {})
                    sc_str = json.dumps(sc).lower()
                    if any(t in sc_str for t in ['name', 'years old']):
                        data['semantic_context'] = self._fallback_semantic_extraction(
                            data['pii'].get('medical_info', user_message)
                        )
                    return data
            return None
        except Exception:
            return None


# Global instance (legacy)
gatekeeper_agent = GatekeeperAgent()
