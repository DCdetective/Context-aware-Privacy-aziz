import json
from pathlib import Path
from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)


class SyntheticDataLoader:
    """
    Loader for synthetic hospital data.
    
    All data is synthetic and safe for cloud storage.
    NO real patient information is included.
    """
    
    def __init__(self, data_dir: str = "synthetic_data"):
        """
        Initialize synthetic data loader.
        
        Args:
            data_dir: Directory containing synthetic data files
        """
        # Try to find synthetic_data directory
        # First try relative to current directory
        data_path = Path(data_dir)
        if not data_path.exists():
            # Try relative to parent directory (for tests running from backend/)
            data_path = Path("..") / data_dir
            if not data_path.exists():
                # Try relative to project root
                data_path = Path(__file__).parent.parent.parent / data_dir
        
        self.data_dir = data_path
        self._doctors = None
        self._policies = None
        self._medical_knowledge = None
        self._appointment_rules = None
        self._example_cases = None
        
        logger.info(f"Synthetic data loader initialized from {self.data_dir}")
    
    def _load_json(self, filename: str) -> Dict[str, Any]:
        """Load JSON file."""
        file_path = self.data_dir / filename
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading {filename}: {str(e)}")
            return {}
    
    @property
    def doctors(self) -> Dict[str, Any]:
        """Get doctors data."""
        if self._doctors is None:
            self._doctors = self._load_json("doctors.json")
        return self._doctors
    
    @property
    def policies(self) -> Dict[str, Any]:
        """Get hospital policies."""
        if self._policies is None:
            self._policies = self._load_json("hospital_policies.json")
        return self._policies
    
    @property
    def medical_knowledge(self) -> Dict[str, Any]:
        """Get medical knowledge base."""
        if self._medical_knowledge is None:
            self._medical_knowledge = self._load_json("medical_knowledge.json")
        return self._medical_knowledge
    
    @property
    def appointment_rules(self) -> Dict[str, Any]:
        """Get appointment rules."""
        if self._appointment_rules is None:
            self._appointment_rules = self._load_json("appointment_rules.json")
        return self._appointment_rules
    
    @property
    def example_cases(self) -> Dict[str, Any]:
        """Get example cases."""
        if self._example_cases is None:
            self._example_cases = self._load_json("example_cases.json")
        return self._example_cases
    
    def get_doctor_by_specialty(self, specialty: str) -> List[Dict[str, Any]]:
        """
        Get doctors by specialty.
        
        Args:
            specialty: Medical specialty
            
        Returns:
            List of matching doctors
        """
        doctors_data = self.doctors.get("doctors", [])
        return [d for d in doctors_data if d.get("specialty") == specialty]
    
    def get_specialty_for_symptoms(self, symptom_category: str) -> str:
        """
        Get recommended specialty for symptom category.
        
        Args:
            symptom_category: Symptom category
            
        Returns:
            Recommended specialty
        """
        knowledge = self.medical_knowledge.get("symptom_categories", {})
        category_info = knowledge.get(symptom_category, {})
        specialists = category_info.get("typical_specialists", ["general_medicine"])
        return specialists[0] if specialists else "general_medicine"
    
    def classify_urgency(self, medical_info: str) -> str:
        """
        Classify urgency based on medical information.
        
        Args:
            medical_info: Medical information text
            
        Returns:
            Urgency level: 'emergency', 'urgent', or 'routine'
        """
        info_lower = medical_info.lower()
        urgency_data = self.medical_knowledge.get("urgency_classification", {})
        
        # Check emergency keywords
        emergency_keywords = urgency_data.get("emergency_keywords", [])
        if any(keyword in info_lower for keyword in emergency_keywords):
            return "emergency"
        
        # Check urgent keywords
        urgent_keywords = urgency_data.get("urgent_keywords", [])
        if any(keyword in info_lower for keyword in urgent_keywords):
            return "urgent"
        
        return "routine"
    
    def get_consultation_duration(self, specialty: str, urgency: str) -> int:
        """
        Get recommended consultation duration.
        
        Args:
            specialty: Medical specialty
            urgency: Urgency level
            
        Returns:
            Duration in minutes
        """
        # Check policies first
        policies = self.policies.get("consultation_duration", {})
        
        if urgency == "emergency":
            return policies.get("emergency", 60)
        
        # Get duration from doctor specialty
        doctors = self.get_doctor_by_specialty(specialty)
        if doctors:
            return doctors[0].get("consultation_duration", 30)
        
        return 30  # Default
    
    def get_all_synthetic_documents(self) -> List[Dict[str, Any]]:
        """
        Get all synthetic data as documents for RAG ingestion.
        
        Returns:
            List of documents with content and metadata
        """
        documents = []
        
        # Add doctor information
        for doctor in self.doctors.get("doctors", []):
            documents.append({
                "content": f"Doctor {doctor['name']} specializes in {doctor['specialty']}. "
                          f"Available on {', '.join(doctor['available_days'])}. "
                          f"Consultation duration: {doctor['consultation_duration']} minutes.",
                "metadata": {
                    "type": "doctor",
                    "specialty": doctor["specialty"],
                    "doctor_id": doctor["doctor_id"]
                }
            })
        
        # Add symptom category information
        for category, info in self.medical_knowledge.get("symptom_categories", {}).items():
            documents.append({
                "content": f"{category.capitalize()} symptoms include: {', '.join(info['common_symptoms'])}. "
                          f"Urgency indicators: {', '.join(info['urgency_indicators'])}. "
                          f"Recommended specialists: {', '.join(info['typical_specialists'])}.",
                "metadata": {
                    "type": "medical_knowledge",
                    "category": category
                }
            })
        
        # Add example cases
        for case in self.example_cases.get("example_cases", []):
            documents.append({
                "content": f"Example case: {case['scenario']}. "
                          f"Recommended specialty: {case['recommended_specialty']}. "
                          f"Urgency: {case['urgency']}. Notes: {case['notes']}",
                "metadata": {
                    "type": "example_case",
                    "case_id": case["case_id"],
                    "urgency": case["urgency"]
                }
            })
        
        logger.info(f"Generated {len(documents)} synthetic documents for RAG")
        return documents


# Global instance
synthetic_data_loader = SyntheticDataLoader()
