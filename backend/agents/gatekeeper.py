import ollama
import json
import re
from typing import Dict, Any, Optional, Tuple
import logging
from datetime import datetime, timezone

from utils.config import settings
from database.identity_vault import identity_vault

logger = logging.getLogger(__name__)


class GatekeeperAgent:
    """
    Local Gatekeeper Agent using Ollama.

    CRITICAL PRIVACY COMPONENT:
    - Detects and extracts ALL PII from user input (name, age, gender,
      phone, email, address, DOB, SSN, insurance ID, etc.)
    - Pseudonymizes identities using UUID mapping
    - Extracts semantic (non-PII) medical context
    - Ensures NO PII reaches cloud agents

    Extraction strategy (in order):
      1. Ollama LLM call — best for natural language
      2. Regex fallback  — reliable catch-all when Ollama is unavailable
    """

    def __init__(self):
        self.model = settings.ollama_model
        self.host = settings.ollama_host
        logger.info(f"Gatekeeper Agent initialized with model: {self.model}")
        logger.info(f"Ollama host: {self.host}")

    # ------------------------------------------------------------------
    # Ollama integration
    # ------------------------------------------------------------------

    def _call_ollama(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = ollama.chat(model=self.model, messages=messages)
            return response['message']['content']

        except Exception as e:
            logger.error(f"Error calling Ollama: {str(e)}")
            raise

    # ------------------------------------------------------------------
    # Regex-based PII extraction (fallback + testing mode)
    # ------------------------------------------------------------------

    def _regex_extract_pii(self, user_message: str) -> Dict[str, Any]:
        """
        Comprehensive regex-based PII extraction.

        Handles both unstructured natural language and structured
        form-style input ("Patient Name: X, Age: 35, ...").
        Used as the fallback when Ollama is unavailable, and as the
        primary extractor in TESTING_MODE.
        """
        result: Dict[str, Any] = {
            'patient_name': None,
            'age': None,
            'gender': None,
            'phone': None,
            'email': None,
            'address': None,
            'date_of_birth': None,
            'ssn': None,
            'insurance_id': None,
            'medical_info': user_message,
        }

        # ---- PHONE ----
        phone_match = re.search(
            r'\b(?:\+1[\s.\-]?)?\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}\b'
            r'|\b\d{10}\b',
            user_message,
        )
        if phone_match:
            result['phone'] = phone_match.group(0).strip()

        # ---- EMAIL ----
        email_match = re.search(
            r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b',
            user_message,
        )
        if email_match:
            result['email'] = email_match.group(0)

        # ---- SSN ----
        ssn_match = re.search(r'\b\d{3}-\d{2}-\d{4}\b', user_message)
        if ssn_match:
            result['ssn'] = ssn_match.group(0)

        # ---- DATE OF BIRTH ----
        dob_match = re.search(
            r'(?:dob|date\s+of\s+birth|born\s+on|birthday)\s*[:\-]?\s*'
            r'([A-Za-z0-9/\-,\s]{4,20})',
            user_message, re.IGNORECASE,
        )
        if not dob_match:
            # ISO / US date formats that appear standalone
            dob_match = re.search(
                r'\b(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})\b',
                user_message,
            )
        if dob_match:
            grp = dob_match.lastindex or 1
            result['date_of_birth'] = dob_match.group(grp).strip()

        # ---- INSURANCE ID ----
        ins_match = re.search(
            r'(?:insurance\s*(?:id|no|#)|insurance\s+policy\s*(?:number|no|id|#)?'
            r'|policy\s*(?:number|no|id|#)|member\s*(?:id|no|#))'
            r'\s*[:\-]?\s*(?:is\s+)?([A-Z0-9\-]{4,20})',
            user_message, re.IGNORECASE,
        )
        if ins_match:
            val = ins_match.group(1).strip()
            # Reject common English words that are not IDs
            if not re.match(r'^(?:is|the|of|for|my|a|an)$', val, re.IGNORECASE):
                result['insurance_id'] = val

        # ---- MRN ----
        mrn_match = re.search(
            r'(?:mrn|medical\s*record\s*(?:number|no|#)?)\s*[:\-]?\s*([A-Z0-9\-]{4,20})',
            user_message, re.IGNORECASE,
        )
        if mrn_match:
            result.setdefault('mrn', mrn_match.group(1).strip())

        # ---- AGE ----
        age_match = (
            re.search(
                r'(?:age[d]?|i am|i\'m|she is|he is|she\'s|he\'s|patient is|am)\s*:?\s*(\d{1,3})'
                r'(?:\s*(?:years?\s*old|yr\s*old|yo))?',
                user_message, re.IGNORECASE,
            )
            or re.search(r'\b(\d{1,3})\s*(?:years?\s*old|yr\s*old|y\.?o\.?)\b', user_message, re.IGNORECASE)
            or re.search(r'\bage\s*[:\-]\s*(\d{1,3})\b', user_message, re.IGNORECASE)
        )
        if age_match:
            try:
                candidate = int(age_match.group(1))
                if 0 < candidate < 130:          # Sanity check
                    result['age'] = candidate
            except (ValueError, IndexError):
                pass

        # ---- GENDER ----
        gender_match = re.search(
            r'(?:gender|sex)\s*[:\-]\s*(male|female|other|non-binary|prefer not to say)',
            user_message, re.IGNORECASE,
        )
        if gender_match:
            raw = gender_match.group(1).lower()
            result['gender'] = raw.capitalize()
        else:
            # Pronoun / keyword inference
            fem = re.search(r'\b(she|her|female|woman|girl)\b', user_message, re.IGNORECASE)
            mas = re.search(r'\b(he|him|his|male|man|boy)\b', user_message, re.IGNORECASE)
            if fem and not mas:
                result['gender'] = 'Female'
            elif mas and not fem:
                result['gender'] = 'Male'

        # ---- NAME ----
        # Use [ \t]+ (not \s+) to prevent capturing across newlines / commas.
        # Priority 1: explicit labelled patterns
        name_match = re.search(
            r'(?:patient\s*name|full\s*name|name)\s*[:\-]\s*'
            r'([A-Za-z][a-z]+(?:[ \t]+[A-Za-z][a-z]+){0,3})',
            user_message, re.IGNORECASE,
        )
        if not name_match:
            # Priority 2: natural-language triggers
            name_match = re.search(
                r'(?:my name is|i am|i\'m|for(?:[ \t]+patient)?|this is)[ \t]+'
                r'([A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+){0,3})',
                user_message,
            )
        if not name_match:
            # Priority 3: title-case two-word sequence (last resort, same line only)
            name_match = re.search(
                r'\b([A-Z][a-z]{1,20}(?:[ \t]+[A-Z][a-z]{1,20}){1,3})\b',
                user_message,
            )
        if name_match:
            result['patient_name'] = name_match.group(1).strip()

        # ---- MEDICAL INFO ----
        symptoms_match = re.search(
            r'(?:symptoms?|complaint|complaining of|suffering from|'
            r'condition|problem|issue|pain|ache|diagnosed with)[:\s]+(.+)',
            user_message, re.IGNORECASE | re.DOTALL,
        )
        if symptoms_match:
            result['medical_info'] = symptoms_match.group(1).strip()

        return result

    # ------------------------------------------------------------------
    # PII extraction (LLM + regex fallback)
    # ------------------------------------------------------------------

    def extract_pii(self, user_message: str) -> Dict[str, Any]:
        """
        Extract ALL PII from a natural language message.

        Uses Ollama LLM for best coverage; falls back to regex when the
        LLM is unavailable or returns unparseable output.

        Returns a dict with: patient_name, age, gender, phone, email,
        address, date_of_birth, ssn, insurance_id, medical_info.
        """
        logger.info("Extracting PII from user message...")

        system_prompt = """You are a medical PII extraction specialist.
Extract ALL personally identifiable information from the input and return ONLY a JSON object with these fields:
- patient_name: Full name of the patient (string, or null if not mentioned)
- age: Age as an integer (or null if not mentioned)
- gender: Gender (Male/Female/Other, or null if not mentioned)
- phone: Phone number if mentioned (string, or null)
- email: Email address if mentioned (string, or null)
- address: Street or postal address if mentioned (string, or null)
- date_of_birth: Date of birth if mentioned (string, or null)
- ssn: Social security number if mentioned (string, or null)
- insurance_id: Insurance ID, policy number, or member ID if mentioned (string, or null)
- medical_info: Medical symptoms, conditions, or reason for contact (string — always populate this)

IMPORTANT:
- Extract EVERY piece of PII present, not just names.
- If a field is not mentioned, use null (do NOT guess or infer).
- medical_info must always contain the health-related portion of the message.

Return ONLY valid JSON, no additional text."""

        prompt = f"""Extract ALL PII from this message:

"{user_message}"

Return JSON only."""

        try:
            response = self._call_ollama(prompt, system_prompt)

            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            pii_data = json.loads(json_match.group() if json_match else response)

            # Ensure every expected key exists
            for field in [
                'patient_name', 'age', 'gender', 'phone', 'email',
                'address', 'date_of_birth', 'ssn', 'insurance_id',
            ]:
                pii_data.setdefault(field, None)
            pii_data.setdefault('medical_info', user_message)

            # Coerce age to int if the LLM returned a string
            if pii_data.get('age') is not None:
                try:
                    pii_data['age'] = int(pii_data['age'])
                except (ValueError, TypeError):
                    pii_data['age'] = None

            found = [k for k in ['patient_name', 'age', 'gender', 'phone', 'email',
                                  'address', 'date_of_birth', 'ssn', 'insurance_id']
                     if pii_data.get(k)]
            logger.info(f"PII extracted via LLM: {found}")
            return pii_data

        except Exception as e:
            logger.warning(f"Ollama PII extraction failed ({e}), using regex fallback")
            return self._regex_extract_pii(user_message)

    # ------------------------------------------------------------------
    # Intent extraction
    # ------------------------------------------------------------------

    def extract_intent(self, user_message: str) -> str:
        """
        Classify user intent: 'appointment', 'followup', 'summary', or 'general'.
        """
        system_prompt = """You are an intent classifier for a medical chatbot.
Classify the user's intent into ONE of these categories:
- appointment: User wants to book a new appointment
- followup: User wants to schedule a follow-up visit
- summary: User wants a medical summary or record
- general: General query or unclear intent

Return ONLY the intent word, nothing else."""

        prompt = f"""Classify the intent of this message:

"{user_message}"

Return only: appointment, followup, summary, or general"""

        try:
            response = self._call_ollama(prompt, system_prompt).strip().lower()
            for intent in ['appointment', 'followup', 'summary', 'general']:
                if intent in response:
                    return intent
            return 'general'

        except Exception as e:
            logger.error(f"Error extracting intent: {str(e)}")
            return self._fallback_intent_extraction(user_message)

    def _fallback_intent_extraction(self, user_message: str) -> str:
        """Keyword-based intent fallback when Ollama is unavailable."""
        msg = user_message.lower()
        if any(w in msg for w in ['follow up', 'follow-up', 'followup', 'check-up', 'review']):
            return 'followup'
        if any(w in msg for w in ['appointment', 'book', 'schedule', 'see a doctor',
                                    'consult', 'visit', 'register']):
            return 'appointment'
        if any(w in msg for w in ['summary', 'report', 'records', 'history',
                                   'generate', 'medical report']):
            return 'summary'
        return 'general'

    # ------------------------------------------------------------------
    # Semantic context extraction
    # ------------------------------------------------------------------

    def extract_semantic_context(self, medical_info: str) -> Dict[str, Any]:
        """
        Extract non-PII semantic medical context safe for cloud storage.

        Returns symptom_category, urgency_level, requires_specialist,
        estimated_duration — NO identifying information.
        """
        system_prompt = """Extract semantic medical features from the description.
Return ONLY JSON with these fields (absolutely no PII — no names, ages, phone numbers, emails):
- symptom_category: General category (e.g., "respiratory", "cardiac", "neurological",
  "digestive", "musculoskeletal", "dermatological", "urological", "psychiatric",
  "endocrine", "ophthalmological", "general")
- urgency_level: "routine", "urgent", or "emergency"
- requires_specialist: true or false
- estimated_duration: estimated consultation time in minutes (15, 30, 45, or 60)

Return ONLY valid JSON."""

        prompt = f"""Analyze this medical information and extract semantic features:

Medical Info: {medical_info}

Return JSON only."""

        try:
            response = self._call_ollama(prompt, system_prompt)

            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            semantic_data = json.loads(json_match.group() if json_match else response)

            # Validate — check whether any PII leaked into the semantic output
            semantic_str = json.dumps(semantic_data).lower()
            pii_leak_terms = [
                'name', 'age', 'years old', 'phone', 'email', 'address',
                'ssn', 'insurance', 'birth', '@',
            ]
            if any(term in semantic_str for term in pii_leak_terms):
                logger.warning("PII detected in semantic extraction output — using fallback")
                return self._fallback_semantic_extraction(medical_info)

            return semantic_data

        except Exception as e:
            logger.warning(f"Semantic extraction error: {str(e)}, using fallback")
            return self._fallback_semantic_extraction(medical_info)

    def _fallback_semantic_extraction(self, medical_info: str) -> Dict[str, Any]:
        """
        Keyword-based semantic extraction.

        Covers a broad vocabulary so that it works for any real-world
        symptom description, not just synthetic dataset keywords.
        """
        info_lower = medical_info.lower()

        # --- Category detection (order matters — more specific first) ---
        category = "general"

        if any(t in info_lower for t in [
            'heart', 'cardiac', 'chest pain', 'palpitation', 'arrhythmia',
            'blood pressure', 'hypertension', 'angina', 'coronary',
        ]):
            category = "cardiac"

        elif any(t in info_lower for t in [
            'headache', 'migraine', 'dizzy', 'dizziness', 'neurological',
            'brain', 'seizure', 'epilepsy', 'stroke', 'numbness', 'tremor',
            'memory', 'confusion', 'fainting', 'vertigo',
        ]):
            category = "neurological"

        elif any(t in info_lower for t in [
            'cough', 'breathing', 'breathe', 'lung', 'respiratory',
            'inhale', 'exhale', 'asthma', 'bronchitis', 'pneumonia',
            'shortness of breath', 'wheezing', 'oxygen', 'throat',
        ]):
            category = "respiratory"

        elif any(t in info_lower for t in [
            'stomach', 'abdominal', 'abdomen', 'digestive', 'nausea',
            'vomiting', 'diarrhea', 'constipation', 'bowel', 'intestine',
            'liver', 'pancreas', 'acid reflux', 'gastric', 'bloating',
        ]):
            category = "digestive"

        elif any(t in info_lower for t in [
            'bone', 'joint', 'muscle', 'back pain', 'knee', 'shoulder',
            'hip', 'fracture', 'sprain', 'arthritis', 'spine', 'neck',
            'ortho', 'ligament', 'tendon', 'wrist', 'ankle', 'foot',
        ]):
            category = "musculoskeletal"

        elif any(t in info_lower for t in [
            'skin', 'rash', 'itch', 'derma', 'acne', 'wound', 'burn',
            'blister', 'hives', 'eczema', 'psoriasis', 'lesion', 'mole',
        ]):
            category = "dermatological"

        elif any(t in info_lower for t in [
            'kidney', 'urine', 'bladder', 'urinary', 'prostate',
            'uti', 'urination', 'renal',
        ]):
            category = "urological"

        elif any(t in info_lower for t in [
            'anxiety', 'depression', 'mental', 'stress', 'panic',
            'psychiatric', 'psycho', 'mood', 'bipolar', 'ocd',
            'ptsd', 'insomnia', 'sleep', 'fatigue',
        ]):
            category = "psychiatric"

        elif any(t in info_lower for t in [
            'diabetes', 'thyroid', 'hormone', 'insulin', 'blood sugar',
            'glucose', 'metabolism', 'endocrine', 'obesity', 'weight',
        ]):
            category = "endocrine"

        elif any(t in info_lower for t in [
            'eye', 'vision', 'sight', 'blind', 'cataract', 'glaucoma',
            'retina', 'pupil', 'glasses', 'blur',
        ]):
            category = "ophthalmological"

        # --- Urgency detection ---
        urgency = "routine"
        if any(t in info_lower for t in [
            'emergency', 'severe', 'critical', 'immediately', 'unbearable',
            'can\'t breathe', 'cannot breathe', 'unconscious', 'bleeding heavily',
            'heart attack', 'stroke', 'seizure', 'chest pain radiating',
        ]):
            urgency = "emergency"
        elif any(t in info_lower for t in [
            'urgent', 'acute', 'sudden', 'quickly', 'worsening', 'high fever',
            'persistent', 'difficulty breathing', 'rapidly',
        ]):
            urgency = "urgent"

        return {
            "symptom_category": category,
            "urgency_level": urgency,
            "requires_specialist": urgency in ["urgent", "emergency"],
            "estimated_duration": 30,
        }

    # ------------------------------------------------------------------
    # Age group masking
    # ------------------------------------------------------------------

    def _convert_age_to_group(self, age: Optional[int]) -> str:
        if age is None:
            return "Unknown"
        if age < 13:
            return "child"
        elif age < 18:
            return "teenager"
        elif age < 25:
            return "early 20s"
        elif age < 35:
            return "late 20s to early 30s"
        elif age < 45:
            return "late 30s to early 40s"
        elif age < 55:
            return "late 40s to early 50s"
        elif age < 65:
            return "late 50s to early 60s"
        else:
            return "senior"

    # ------------------------------------------------------------------
    # Privacy report
    # ------------------------------------------------------------------

    def create_privacy_report(
        self,
        pii_data: Dict[str, Any],
        patient_uuid: str,
        semantic_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Build a privacy transformation report covering ALL detected PII types.
        Shows exactly what was found and how it was handled.
        """
        transformations = []

        # --- Name → UUID ---
        if pii_data.get('patient_name'):
            transformations.append({
                "field": "Patient Name",
                "original": pii_data['patient_name'],
                "transformed": f"Patient_{patient_uuid[:8]}",
                "method": "UUID Pseudonymization",
            })

        # --- Age → group ---
        if pii_data.get('age') is not None:
            age_group = self._convert_age_to_group(pii_data['age'])
            transformations.append({
                "field": "Age",
                "original": str(pii_data['age']),
                "transformed": age_group,
                "method": "Age Group Masking",
            })

        # --- Gender (retained, non-identifying alone) ---
        if pii_data.get('gender'):
            transformations.append({
                "field": "Gender",
                "original": pii_data['gender'],
                "transformed": pii_data['gender'],
                "method": "Retained (non-identifying)",
            })

        # --- Phone → redacted ---
        if pii_data.get('phone'):
            transformations.append({
                "field": "Phone Number",
                "original": pii_data['phone'],
                "transformed": "[REDACTED]",
                "method": "PII Redaction",
            })

        # --- Email → redacted ---
        if pii_data.get('email'):
            transformations.append({
                "field": "Email Address",
                "original": pii_data['email'],
                "transformed": "[REDACTED]",
                "method": "PII Redaction",
            })

        # --- Address → redacted ---
        if pii_data.get('address'):
            transformations.append({
                "field": "Address",
                "original": pii_data['address'],
                "transformed": "[REDACTED]",
                "method": "PII Redaction",
            })

        # --- Date of Birth → redacted ---
        if pii_data.get('date_of_birth'):
            transformations.append({
                "field": "Date of Birth",
                "original": pii_data['date_of_birth'],
                "transformed": "[REDACTED]",
                "method": "PII Redaction",
            })

        # --- SSN → redacted ---
        if pii_data.get('ssn'):
            transformations.append({
                "field": "Social Security Number",
                "original": pii_data['ssn'],
                "transformed": "[REDACTED]",
                "method": "PII Redaction",
            })

        # --- Insurance ID → redacted ---
        if pii_data.get('insurance_id'):
            transformations.append({
                "field": "Insurance ID",
                "original": pii_data['insurance_id'],
                "transformed": "[REDACTED]",
                "method": "PII Redaction",
            })

        # --- MRN → redacted ---
        if pii_data.get('mrn'):
            transformations.append({
                "field": "Medical Record Number",
                "original": pii_data['mrn'],
                "transformed": "[REDACTED]",
                "method": "PII Redaction",
            })

        # --- Medical info → semantic only ---
        transformations.append({
            "field": "Medical Information",
            "original": "Contains patient health details",
            "transformed": f"Semantic category: {semantic_context.get('symptom_category', 'general')}",
            "method": "Semantic Extraction",
        })

        # Count all PII fields that were present (gender is retained, not redacted)
        redacted_fields = [
            'patient_name', 'age', 'phone', 'email',
            'address', 'date_of_birth', 'ssn', 'insurance_id', 'mrn',
        ]
        pii_removed = sum(1 for f in redacted_fields if pii_data.get(f) is not None)

        return {
            "transformations": transformations,
            "pii_removed": pii_removed,
            "cloud_safe": True,
            "patient_uuid": patient_uuid,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # Main pipeline entry point
    # ------------------------------------------------------------------

    def process_message(self, user_message: str) -> Dict[str, Any]:
        """
        Main processing pipeline for incoming user messages.

        Steps:
          1. Extract ALL PII (LLM → regex fallback)
          2. Extract intent
          3. Extract semantic context (non-PII)
          4. Generate privacy report whenever any PII is detected
          5. Return structured data for the coordinator
        """
        logger.info("=" * 60)
        logger.info("GATEKEEPER: Processing user message")
        logger.info("=" * 60)

        # Step 1: Extract ALL PII
        pii_data = self.extract_pii(user_message)
        logger.info("Step 1: PII extracted")

        # Step 2: Extract intent
        intent = self.extract_intent(user_message)
        logger.info(f"Step 2: Intent identified: {intent}")

        # Step 3: Extract semantic context
        semantic_context = self.extract_semantic_context(pii_data['medical_info'])
        logger.info("Step 3: Semantic context extracted")

        # Step 4: Generate privacy report when ANY PII is detected
        _pii_check_fields = [
            'patient_name', 'age', 'gender', 'phone', 'email',
            'address', 'date_of_birth', 'ssn', 'insurance_id', 'mrn',
        ]
        has_pii = any(pii_data.get(f) for f in _pii_check_fields)

        privacy_report = None
        if has_pii:
            # Use actual UUID if name is known; otherwise use a hash-based placeholder
            if pii_data.get('patient_name'):
                temp_uuid = str(abs(hash(pii_data['patient_name'])))[:8]
            else:
                temp_uuid = str(abs(hash(user_message)))[:8]

            privacy_report = self.create_privacy_report(
                pii_data=pii_data,
                patient_uuid=temp_uuid,
                semantic_context=semantic_context,
            )

        # Step 5: Prepare output
        processed_data = {
            'pii': pii_data,
            'intent': intent,
            'semantic_context': semantic_context,
            'privacy_report': privacy_report,
            'original_message': user_message,
            'cloud_safe': True,
        }

        logger.info("GATEKEEPER: Message processed successfully")
        logger.info("=" * 60)

        return processed_data

    # ------------------------------------------------------------------
    # Compatibility helpers (used by API route modules)
    # ------------------------------------------------------------------

    def pseudonymize_input(self, user_message: str) -> Dict[str, Any]:
        """
        Pseudonymize a message and return a cloud-safe payload.

        In TESTING_MODE the Ollama call is skipped; regex extraction is
        used instead so tests are fast and deterministic.  Intent is
        inferred from keywords in that case.
        """
        if settings.testing_mode:
            pii = self._regex_extract_pii(user_message)
            semantic_context = self._fallback_semantic_extraction(pii["medical_info"])
            intent = self._fallback_intent_extraction(user_message)
        else:
            gatekeeper_output = self.process_message(user_message)
            pii = gatekeeper_output.get("pii", {})
            semantic_context = gatekeeper_output.get("semantic_context", {})
            intent = gatekeeper_output.get("intent", "general")

        if pii.get("patient_name"):
            patient_uuid, _ = identity_vault.pseudonymize_patient(
                patient_name=pii["patient_name"],
                age=pii.get("age"),
                gender=pii.get("gender"),
                component="gatekeeper",
            )
        else:
            patient_uuid = "temp-uuid-" + str(abs(hash(user_message)))[:8]

        return {
            "patient_uuid": patient_uuid,
            "semantic_context": semantic_context,
            "intent": intent,
            "cloud_safe": True,
        }

    def reidentify_output(
        self, patient_uuid: str, cloud_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Re-attach identity info for UI output (compatibility helper)."""
        final = dict(cloud_result or {})

        if patient_uuid and not patient_uuid.startswith("temp-uuid"):
            identity = identity_vault.reidentify_patient(
                patient_uuid=patient_uuid, component="gatekeeper"
            )
            if identity:
                final.setdefault("patient_uuid", patient_uuid)
                final["patient_name"] = identity.get("patient_name")
                final["patient_age"] = identity.get("age")
                final["patient_gender"] = identity.get("gender")

        return final


# Global singleton
gatekeeper_agent = GatekeeperAgent()
