"""
Human-in-the-Loop (HITL) Manager
Handles multi-turn conversations requiring user confirmation.
"""
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)


class HITLManager:
    """Manages human-in-the-loop workflows for confirmations."""
    
    def __init__(self):
        """Initialize HITL Manager."""
        logger.info("HITL Manager initialized")
    
    def generate_medical_questions(
        self,
        intent: str,
        semantic_context: Dict[str, Any]
    ) -> List[str]:
        """
        Generate relevant medical questions before booking.
        
        Args:
            intent: User intent (appointment/followup)
            semantic_context: Semantic medical context
            
        Returns:
            List of 2-3 relevant questions
        """
        symptom_category = semantic_context.get('symptom_category', 'general')
        urgency = semantic_context.get('urgency_level', 'routine')
        
        questions = []
        
        # Base questions
        questions.append("How long have you been experiencing these symptoms?")
        
        # Category-specific questions
        if symptom_category == 'respiratory':
            questions.append("Do you have difficulty breathing or shortness of breath?")
            questions.append("Have you been in contact with anyone who is sick?")
        elif symptom_category == 'cardiac':
            questions.append("Do you experience chest pain or discomfort?")
            questions.append("Do you have a history of heart conditions?")
        elif symptom_category == 'neurological':
            questions.append("Are you experiencing any vision changes or dizziness?")
            questions.append("Have you had any recent head injuries?")
        elif symptom_category == 'digestive':
            questions.append("Are you experiencing nausea or vomiting?")
            questions.append("Any recent dietary changes?")
        else:
            questions.append("On a scale of 1-10, how would you rate your discomfort?")
            questions.append("Have you taken any medication for this?")
        
        # Urgency-based question
        if urgency == 'urgent':
            questions.append("Is this a sudden onset or has it been gradual?")
        
        # Return 2-3 questions
        return questions[:3]
    
    def create_confirmation_summary(
        self,
        intent: str,
        patient_name: str,
        action_data: Dict[str, Any],
        user_responses: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        Create a summary for user confirmation.
        
        Args:
            intent: Action intent
            patient_name: Patient name
            action_data: Action details
            user_responses: User's responses to questions
            
        Returns:
            Formatted confirmation summary
        """
        lines = ["📋 **Confirmation Summary**\n"]
        
        if intent == "appointment":
            lines.append(f"**Patient:** {patient_name}")
            lines.append(f"**Action:** Book New Appointment")
            
            if action_data.get('recommended_doctor'):
                lines.append(f"**Doctor:** {action_data['recommended_doctor']}")
            
            if action_data.get('appointment_date'):
                lines.append(f"**Date:** {action_data['appointment_date']}")
            
            if action_data.get('appointment_time'):
                lines.append(f"**Time:** {action_data['appointment_time']}")
            
            if action_data.get('consultation_duration'):
                lines.append(f"**Duration:** {action_data['consultation_duration']} minutes")
        
        elif intent == "followup":
            lines.append(f"**Patient:** {patient_name}")
            lines.append(f"**Action:** Schedule Follow-up")
            
            if action_data.get('followup_date'):
                lines.append(f"**Date:** {action_data['followup_date']}")
            
            if action_data.get('recommended_doctor'):
                lines.append(f"**Doctor:** {action_data['recommended_doctor']}")
        
        # Add user responses if available
        if user_responses:
            lines.append("\n**Your Responses:**")
            for resp in user_responses:
                lines.append(f"- Q: {resp['question']}")
                lines.append(f"  A: {resp['response']}")
        
        lines.append("\n**Please confirm:** Type 'yes' to proceed or 'no' to cancel.")
        
        return "\n".join(lines)
    
    def parse_confirmation_response(self, message: str) -> bool:
        """
        Parse user's confirmation response.
        
        Args:
            message: User message
            
        Returns:
            True if confirmed, False otherwise
        """
        message_lower = message.lower().strip()
        
        # Positive confirmations
        positive = ['yes', 'confirm', 'ok', 'proceed', 'sure', 'yeah', 'yep', 'correct']
        if any(word in message_lower for word in positive):
            return True
        
        # Negative confirmations
        negative = ['no', 'cancel', 'stop', 'nevermind', 'nope']
        if any(word in message_lower for word in negative):
            return False
        
        return False  # Default to not confirmed


# Global instance
hitl_manager = HITLManager()
