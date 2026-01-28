import ollama
import json
import re
from typing import Dict, Any, Tuple, List, Optional
import logging

from database.identity_vault import identity_vault
from vector_store.mock_semantic_store import MockSemanticStore
from utils.config import settings

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
    
    def __init__(self, semantic_store=None):
        """Initialize Gatekeeper Agent."""
        self.model = settings.ollama_model
        self.host = settings.ollama_host
        self.semantic_store = semantic_store
        
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
    
    def extract_patient_info(self, user_input: str) -> Dict[str, Any]:
        """
        Extract patient information from natural language input.
        
        Args:
            user_input: Raw user input containing patient details
            
        Returns:
            Dictionary with extracted patient information
        """
        logger.info("Extracting patient information from input...")
        
        system_prompt = """You are a medical information extraction assistant.
Extract patient details from the input and return ONLY a JSON object with these fields:
- patient_name: Full name of the patient
- age: Age as an integer
- gender: Gender (Male/Female/Other)
- symptoms: Description of symptoms or medical condition

Return ONLY valid JSON, no additional text."""
        
        prompt = f"""Extract patient information from this text:

"{user_input}"

Return JSON format only."""
        
        try:
            response = self._call_ollama(prompt, system_prompt)
            
            # Parse JSON from response
            # Clean up response to extract JSON
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                patient_info = json.loads(json_match.group())
            else:
                patient_info = json.loads(response)
            
            logger.info(f"Extracted patient info: {patient_info.get('patient_name', 'Unknown')}")
            return patient_info
            
        except Exception as e:
            logger.error(f"Error extracting patient info: {str(e)}")
            # Fallback: try to extract using regex
            return self._fallback_extraction(user_input)
    
    def _fallback_extraction(self, text: str) -> Dict[str, Any]:
        """
        Fallback extraction using regex patterns.
        
        Args:
            text: Input text
            
        Returns:
            Extracted patient information
        """
        logger.warning("Using fallback extraction method")
        
        info = {
            "patient_name": "Unknown Patient",
            "age": 0,
            "gender": "Unknown",
            "symptoms": text
        }
        
        # Try to extract name patterns (expanded patterns)
        name_patterns = [
            r"(?:Patient Name|Name):\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+?)(?:\n|,|$)",  # Structured format with proper end
            r"(?:name is |named |patient |I'm |I am )([A-Z][a-z]+ [A-Z][a-z]+)",
            r"Patient:\s*([A-Z][a-z]+ [A-Z][a-z]+)",  # Patient: Name format
            r"([A-Z][a-z]+ [A-Z][a-z]+)(?:,| is| -)"
        ]
        
        for pattern in name_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                info["patient_name"] = match.group(1).strip()
                break
        
        # Try to extract age (expanded patterns)
        age_patterns = [
            r"Age:\s*(\d{1,3})",  # Structured format
            r"(\d{1,3})\s*(?:years old|yr|y\.o\.|age)",
            r",\s*(\d{1,3})\s*(?:years old|,|$)"
        ]
        
        for pattern in age_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                info["age"] = int(match.group(1))
                break
        
        # Try to extract gender (expanded patterns)
        gender_patterns = [
            r"Gender:\s*(Female|Male|Other)",  # Structured format - Female first to match before Male
            r"\b(female|woman|girl)\b",
            r"\b(male|man|boy)\b"
        ]
        
        for pattern in gender_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                gender_text = match.group(1).lower()
                if "female" in gender_text or "woman" in gender_text or "girl" in gender_text:
                    info["gender"] = "Female"
                elif "male" in gender_text or "man" in gender_text or "boy" in gender_text:
                    info["gender"] = "Male"
                else:
                    info["gender"] = match.group(1).capitalize()
                break
        
        # Try to extract symptoms
        symptoms_match = re.search(r"Symptoms?:\s*(.+?)(?:\n|$)", text, re.IGNORECASE | re.DOTALL)
        if symptoms_match:
            info["symptoms"] = symptoms_match.group(1).strip()
        
        return info
    
    def pseudonymize_input(self, user_input: str) -> Dict[str, Any]:
        """
        Main pseudonymization pipeline.
        
        1. Extract patient PII from input
        2. Generate/retrieve UUID from Identity Vault
        3. Extract semantic medical context
        4. Return pseudonymized data structure
        
        Args:
            user_input: Raw user input
            
        Returns:
            Dictionary with pseudonymized data
        """
        logger.info("=" * 60)
        logger.info("GATEKEEPER: Starting pseudonymization pipeline")
        logger.info("=" * 60)
        
        # Step 1: Extract PII
        patient_info = self.extract_patient_info(user_input)
        logger.info(f"Step 1: Extracted PII for {patient_info['patient_name']}")
        
        # Step 2: Pseudonymize using Identity Vault
        patient_uuid, is_new = identity_vault.pseudonymize_patient(
            patient_name=patient_info['patient_name'],
            age=patient_info['age'],
            gender=patient_info['gender'],
            component="gatekeeper_agent"
        )
        logger.info(f"Step 2: Pseudonymized to UUID: {patient_uuid}")
        logger.info(f"         New patient: {is_new}")
        
        # Step 3: Extract semantic context (non-PII)
        semantic_context = self.extract_semantic_context(patient_info)
        logger.info(f"Step 3: Extracted semantic context")
        
        # Step 4: Store semantic anchors if store is available
        if self.semantic_store:
            try:
                anchor_id = self.semantic_store.store_semantic_anchor(
                    patient_uuid=patient_uuid,
                    anchor_type="medical_context",
                    semantic_data=semantic_context
                )
                logger.info(f"Step 4: Stored semantic anchor: {anchor_id}")
            except Exception as e:
                logger.warning(f"Could not store semantic anchor: {str(e)}")
        
        # Step 5: Create pseudonymized output
        pseudonymized_data = {
            "patient_uuid": patient_uuid,
            "is_new_patient": is_new,
            "semantic_context": semantic_context,
            "original_has_pii": True,
            "cloud_safe": True
        }
        
        logger.info("=" * 60)
        logger.info("GATEKEEPER: Pseudonymization complete")
        logger.info(f"UUID: {patient_uuid}")
        logger.info(f"Cloud-safe: {pseudonymized_data['cloud_safe']}")
        logger.info("=" * 60)
        
        return pseudonymized_data
    
    def extract_semantic_context(self, patient_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract non-PII semantic medical context.
        
        This method extracts medical information that is safe to store
        in the cloud (Pinecone) without revealing patient identity.
        
        Args:
            patient_info: Patient information dictionary
            
        Returns:
            Dictionary with semantic (non-PII) medical context
        """
        symptoms = patient_info.get('symptoms', '')
        
        # Use LLM to extract semantic features
        system_prompt = """Extract semantic medical features from symptoms.
Return ONLY JSON with these fields (no PII like names/ages):
- symptom_category: General category (e.g., "respiratory", "cardiac", "neurological")
- urgency_level: "routine", "urgent", or "emergency"
- requires_specialist: true/false
- estimated_consultation_time: minutes (integer)

Return ONLY valid JSON."""
        
        prompt = f"""Analyze these symptoms and extract semantic features:

Symptoms: {symptoms}

Return JSON only."""
        
        try:
            response = self._call_ollama(prompt, system_prompt)
            
            # Parse JSON
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                semantic_data = json.loads(json_match.group())
            else:
                semantic_data = json.loads(response)
            
            # Ensure no PII leaked
            semantic_str = json.dumps(semantic_data).lower()
            if any(term in semantic_str for term in ['name', 'age', 'gender']):
                logger.warning("PII detected in semantic extraction, using fallback")
                return self._fallback_semantic_extraction(symptoms)
            
            return semantic_data
            
        except Exception as e:
            logger.warning(f"Error in semantic extraction: {str(e)}")
            return self._fallback_semantic_extraction(symptoms)
    
    def _fallback_semantic_extraction(self, symptoms: str) -> Dict[str, Any]:
        """
        Fallback semantic extraction without LLM.
        
        Args:
            symptoms: Symptom description
            
        Returns:
            Basic semantic context
        """
        # Simple keyword-based categorization
        symptoms_lower = symptoms.lower()
        
        category = "general"
        if any(term in symptoms_lower for term in ['cough', 'breathing', 'chest']):
            category = "respiratory"
        elif any(term in symptoms_lower for term in ['heart', 'cardiac', 'chest pain']):
            category = "cardiac"
        elif any(term in symptoms_lower for term in ['headache', 'dizzy', 'neurological']):
            category = "neurological"
        
        urgency = "routine"
        if any(term in symptoms_lower for term in ['severe', 'emergency', 'critical']):
            urgency = "emergency"
        elif any(term in symptoms_lower for term in ['urgent', 'acute', 'sudden']):
            urgency = "urgent"
        
        return {
            "symptom_category": category,
            "urgency_level": urgency,
            "requires_specialist": urgency in ["urgent", "emergency"],
            "estimated_consultation_time": 30
        }
    
    def reidentify_output(self, patient_uuid: str, cloud_response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Re-identify patient for final output display.
        
        This is the ONLY place where pseudonymized data is converted
        back to real patient identity before presenting to the user.
        
        Args:
            patient_uuid: Pseudonymized patient UUID
            cloud_response: Response from cloud agents
            
        Returns:
            Response with real patient identity restored
        """
        logger.info("=" * 60)
        logger.info("GATEKEEPER: Re-identifying patient for output")
        logger.info("=" * 60)
        
        # Retrieve real identity from vault
        identity = identity_vault.reidentify_patient(
            patient_uuid=patient_uuid,
            component="gatekeeper_agent"
        )
        
        if not identity:
            logger.error(f"Could not re-identify patient: {patient_uuid}")
            return cloud_response
        
        # Merge identity with cloud response
        output = {
            **cloud_response,
            "patient_name": identity["patient_name"],
            "patient_age": identity["age"],
            "patient_gender": identity["gender"],
            "reidentified": True
        }
        
        logger.info(f"Re-identified patient: {identity['patient_name']}")
        logger.info("=" * 60)
        
        return output


# Global instance
gatekeeper_agent = GatekeeperAgent()
