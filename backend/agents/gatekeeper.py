import ollama
import json
import re
from typing import Dict, Any, Optional, Tuple
import logging

from utils.config import settings
from database.identity_vault import identity_vault

logger = logging.getLogger(__name__)


class GatekeeperAgent:
    """
    Local Gatekeeper Agent using Ollama (Llama 3.1).
    
    CRITICAL PRIVACY COMPONENT:
    - Detects and extracts PII from user input
    - Pseudonymizes identities using UUID mapping
    - Extracts semantic (non-PII) medical context
    - Ensures NO PII reaches cloud agents
    """
    
    def __init__(self):
        """Initialize Gatekeeper Agent."""
        self.model = settings.ollama_model
        self.host = settings.ollama_host
        
        logger.info(f"Gatekeeper Agent initialized with model: {self.model}")
        logger.info(f"Ollama host: {self.host}")
    
    def _call_ollama(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """
        Call Ollama LLM with a prompt.
        
        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            
        Returns:
            LLM response text
        """
        try:
            messages = []
            
            if system_prompt:
                messages.append({
                    "role": "system",
                    "content": system_prompt
                })
            
            messages.append({
                "role": "user",
                "content": prompt
            })
            
            response = ollama.chat(
                model=self.model,
                messages=messages
            )
            
            return response['message']['content']
            
        except Exception as e:
            logger.error(f"Error calling Ollama: {str(e)}")
            raise
    
    def extract_pii(self, user_message: str) -> Dict[str, Any]:
        """
        Extract PII from natural language user message.
        
        Args:
            user_message: Raw user input from chatbot
            
        Returns:
            Dictionary with extracted PII
        """
        logger.info("Extracting PII from user message...")
        
        system_prompt = """You are a medical information extraction assistant.
Extract patient details from the input and return ONLY a JSON object with these fields:
- patient_name: Full name of the patient (string, or null if not mentioned)
- age: Age as an integer (or null if not mentioned)
- gender: Gender (Male/Female/Other, or null if not mentioned)
- medical_info: Medical symptoms, conditions, or reason for contact (string)

IMPORTANT: If information is not explicitly mentioned, use null. Do not guess.

Return ONLY valid JSON, no additional text."""
        
        prompt = f"""Extract patient information from this message:

"{user_message}"

Return JSON format only."""
        
        try:
            response = self._call_ollama(prompt, system_prompt)
            
            # Parse JSON from response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                pii_data = json.loads(json_match.group())
            else:
                pii_data = json.loads(response)
            
            # Ensure all fields exist
            pii_data.setdefault('patient_name', None)
            pii_data.setdefault('age', None)
            pii_data.setdefault('gender', None)
            pii_data.setdefault('medical_info', user_message)
            
            logger.info(f"Extracted PII: {pii_data.get('patient_name', 'No name found')}")
            return pii_data
            
        except Exception as e:
            logger.error(f"Error extracting PII: {str(e)}")
            # Fallback: return minimal structure
            return {
                'patient_name': None,
                'age': None,
                'gender': None,
                'medical_info': user_message
            }
    
    def extract_intent(self, user_message: str) -> str:
        """
        Extract user intent from message.
        
        Args:
            user_message: User input message
            
        Returns:
            Intent: 'appointment', 'followup', 'summary', or 'general'
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
            
            # Validate intent
            valid_intents = ['appointment', 'followup', 'summary', 'general']
            for intent in valid_intents:
                if intent in response:
                    return intent
            
            return 'general'
            
        except Exception as e:
            logger.error(f"Error extracting intent: {str(e)}")
            return 'general'
    
    def extract_semantic_context(self, medical_info: str) -> Dict[str, Any]:
        """
        Extract non-PII semantic medical context.
        
        This extracts medical information that is safe to store
        in the cloud (Pinecone) without revealing patient identity.
        
        Args:
            medical_info: Medical information string
            
        Returns:
            Dictionary with semantic (non-PII) medical context
        """
        system_prompt = """Extract semantic medical features from the description.
Return ONLY JSON with these fields (no PII like names/exact ages):
- symptom_category: General category (e.g., "respiratory", "cardiac", "neurological", "general")
- urgency_level: "routine", "urgent", or "emergency"
- requires_specialist: true or false
- estimated_duration: estimated consultation time in minutes (15, 30, 45, or 60)

Return ONLY valid JSON."""
        
        prompt = f"""Analyze this medical information and extract semantic features:

Medical Info: {medical_info}

Return JSON only."""
        
        try:
            response = self._call_ollama(prompt, system_prompt)
            
            # Parse JSON
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                semantic_data = json.loads(json_match.group())
            else:
                semantic_data = json.loads(response)
            
            # Validate no PII leaked
            semantic_str = json.dumps(semantic_data).lower()
            if any(term in semantic_str for term in ['name', 'age', 'years old']):
                logger.warning("PII detected in semantic extraction, using fallback")
                return self._fallback_semantic_extraction(medical_info)
            
            return semantic_data
            
        except Exception as e:
            logger.warning(f"Error in semantic extraction: {str(e)}")
            return self._fallback_semantic_extraction(medical_info)
    
    def _fallback_semantic_extraction(self, medical_info: str) -> Dict[str, Any]:
        """
        Fallback semantic extraction without LLM.
        
        Args:
            medical_info: Medical information
            
        Returns:
            Basic semantic context
        """
        info_lower = medical_info.lower()
        
        # Determine category
        category = "general"
        if any(term in info_lower for term in ['cough', 'breathing', 'lung', 'respiratory']):
            category = "respiratory"
        elif any(term in info_lower for term in ['heart', 'cardiac', 'chest pain']):
            category = "cardiac"
        elif any(term in info_lower for term in ['headache', 'dizzy', 'neurological', 'brain']):
            category = "neurological"
        elif any(term in info_lower for term in ['stomach', 'digestive', 'nausea', 'abdominal']):
            category = "digestive"
        
        # Determine urgency
        urgency = "routine"
        if any(term in info_lower for term in ['emergency', 'severe', 'critical', 'immediately']):
            urgency = "emergency"
        elif any(term in info_lower for term in ['urgent', 'acute', 'sudden', 'quickly']):
            urgency = "urgent"
        
        return {
            "symptom_category": category,
            "urgency_level": urgency,
            "requires_specialist": urgency in ["urgent", "emergency"],
            "estimated_duration": 30
        }
    
    def pseudonymize_input(self, user_message: str) -> Dict[str, Any]:
        """Compatibility helper used by older scripts.

        Returns pseudonymized payload suitable for cloud agents:
        {patient_uuid, semantic_context, intent}

        In `TESTING_MODE`, this avoids Ollama calls entirely to keep tests fast
        and deterministic.
        """
        if settings.testing_mode:
            # Minimal, deterministic extraction: handle patterns like
            # "Patient Name: X\nAge: 45\nGender: Male\nSymptoms: ..."
            # Capture up to comma or newline to avoid swallowing the rest of the line.
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
            gatekeeper_output = self.process_message(user_message)
            pii = gatekeeper_output.get("pii", {})
            semantic_context = gatekeeper_output.get("semantic_context", {})
            intent = gatekeeper_output.get("intent", "general")

        if pii.get("patient_name"):
            patient_uuid, _ = identity_vault.pseudonymize_patient(
                patient_name=pii.get("patient_name"),
                age=pii.get("age"),
                gender=pii.get("gender"),
                component="gatekeeper",
            )
        else:
            patient_uuid = "temp-uuid-" + str(hash(user_message))[:8]

        return {
            "patient_uuid": patient_uuid,
            "semantic_context": semantic_context,
            "intent": intent,
            "cloud_safe": True,
        }

    def reidentify_output(self, patient_uuid: str, cloud_result: Dict[str, Any]) -> Dict[str, Any]:
        """Compatibility helper to re-attach identity info for UI output."""
        final = dict(cloud_result or {})

        if patient_uuid and not patient_uuid.startswith("temp-uuid"):
            identity = identity_vault.reidentify_patient(patient_uuid=patient_uuid, component="gatekeeper")
            if identity:
                final.setdefault("patient_uuid", patient_uuid)
                final["patient_name"] = identity.get("patient_name")
                final["patient_age"] = identity.get("age")
                final["patient_gender"] = identity.get("gender")

        return final

    def process_message(self, user_message: str) -> Dict[str, Any]:
        """
        Main processing pipeline for incoming user messages.
        
        Workflow:
        1. Extract PII from message
        2. Extract intent
        3. Extract semantic context
        4. Return structured data for coordinator
        
        Args:
            user_message: Raw user input
            
        Returns:
            Processed message data ready for cloud agents
        """
        logger.info("=" * 60)
        logger.info("GATEKEEPER: Processing user message")
        logger.info("=" * 60)
        
        # Step 1: Extract PII
        pii_data = self.extract_pii(user_message)
        logger.info(f"Step 1: PII extracted")
        
        # Step 2: Extract intent
        intent = self.extract_intent(user_message)
        logger.info(f"Step 2: Intent identified: {intent}")
        
        # Step 3: Extract semantic context
        semantic_context = self.extract_semantic_context(pii_data['medical_info'])
        logger.info(f"Step 3: Semantic context extracted")
        
        # Step 4: Prepare output
        processed_data = {
            'pii': pii_data,
            'intent': intent,
            'semantic_context': semantic_context,
            'original_message': user_message,
            'cloud_safe': True
        }
        
        logger.info("GATEKEEPER: Message processed successfully")
        logger.info("=" * 60)
        
        return processed_data


# Global instance
gatekeeper_agent = GatekeeperAgent()
