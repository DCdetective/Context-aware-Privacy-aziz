from groq import Groq
import json
import re
from typing import Dict, Any, List, Optional
import logging

from utils.config import settings

logger = logging.getLogger(__name__)


class CoordinatorAgent:
    """
    Cloud Coordinator Agent using Groq API.
    
    PRIVACY GUARANTEE:
    - Receives ONLY pseudonymized UUIDs
    - Works with semantic context (no PII)
    - Plans and delegates tasks to Worker Agent
    - NEVER accesses Identity Vault
    """
    
    def __init__(self):
        """Initialize Coordinator Agent."""
        self.client = Groq(api_key=settings.groq_api_key)
        self.model = "llama-3.3-70b-versatile"  # Updated Groq model (Jan 2026)
        
        logger.info("Coordinator Agent initialized with Groq API")
    
    def _call_groq(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """
        Call Groq LLM with a prompt.
        
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
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.3,
                max_tokens=1024
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Error calling Groq API: {str(e)}")
            raise
    
    def coordinate_request(
        self,
        patient_uuid: str,
        action_type: str,
        semantic_context: Dict[str, Any],
        additional_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Coordinate a medical request by planning and delegating.
        
        Args:
            patient_uuid: Pseudonymized patient identifier
            action_type: Type of action ('appointment', 'followup', 'summary')
            semantic_context: Non-PII medical context
            additional_data: Optional additional data
            
        Returns:
            Coordination result
        """
        logger.info("=" * 60)
        logger.info("COORDINATOR: Processing request")
        logger.info(f"Patient UUID: {patient_uuid[:8]}...")
        logger.info(f"Action Type: {action_type}")
        logger.info("=" * 60)
        
        # Validate action type
        valid_actions = ['appointment', 'followup', 'summary']
        if action_type not in valid_actions:
            logger.error(f"Invalid action type: {action_type}")
            return {
                "success": False,
                "error": f"Unsupported action type. Must be one of: {valid_actions}",
                "patient_uuid": patient_uuid
            }
        
        # Plan the execution
        execution_plan = self._create_execution_plan(
            action_type=action_type,
            semantic_context=semantic_context,
            additional_data=additional_data
        )
        
        logger.info(f"Execution plan created: {execution_plan['steps']}")
        
        # Return coordination result
        result = {
            "patient_uuid": patient_uuid,
            "action_type": action_type,
            "execution_plan": execution_plan,
            "ready_for_worker": True,
            "privacy_safe": True
        }
        
        logger.info("COORDINATOR: Request coordinated successfully")
        logger.info("=" * 60)
        
        return result
    
    def _create_execution_plan(
        self,
        action_type: str,
        semantic_context: Dict[str, Any],
        additional_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create an execution plan for the Worker Agent.
        
        Args:
            action_type: Type of action
            semantic_context: Semantic medical context
            additional_data: Additional data
            
        Returns:
            Execution plan
        """
        system_prompt = f"""You are a medical task planning assistant.
Create an execution plan for a {action_type} request.

CRITICAL RULES:
1. You receive ONLY pseudonymized UUIDs, NO patient names
2. Use semantic context for medical decisions
3. Return ONLY JSON format
4. Supported actions: appointment, followup, summary
5. NEVER create plans for unsupported actions

Return JSON with:
- steps: List of execution steps
- estimated_time: Estimated completion time in minutes
- priority: "routine", "urgent", or "emergency"
- requires_specialist: true/false"""

        prompt = f"""Create execution plan for {action_type}.

Semantic Context: {json.dumps(semantic_context)}
Additional Data: {json.dumps(additional_data or {})}

Return JSON only."""
        
        try:
            response = self._call_groq(prompt, system_prompt)
            
            # Parse JSON
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                plan = json.loads(json_match.group())
            else:
                plan = json.loads(response)
            
            return plan
            
        except Exception as e:
            logger.warning(f"Error creating execution plan: {str(e)}")
            return self._fallback_execution_plan(action_type, semantic_context)
    
    def _fallback_execution_plan(
        self,
        action_type: str,
        semantic_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create a fallback execution plan without LLM.
        
        Args:
            action_type: Type of action
            semantic_context: Semantic context
            
        Returns:
            Fallback execution plan
        """
        urgency = semantic_context.get("urgency_level", "routine")
        
        plans = {
            "appointment": {
                "steps": [
                    "Validate UUID and semantic context",
                    "Determine appropriate time slot",
                    "Allocate medical resources",
                    "Confirm appointment details"
                ],
                "estimated_time": 5,
                "priority": urgency,
                "requires_specialist": semantic_context.get("requires_specialist", False)
            },
            "followup": {
                "steps": [
                    "Retrieve previous semantic context",
                    "Calculate follow-up timing",
                    "Schedule follow-up appointment",
                    "Update care plan"
                ],
                "estimated_time": 3,
                "priority": urgency,
                "requires_specialist": False
            },
            "summary": {
                "steps": [
                    "Gather semantic medical data",
                    "Generate summary structure",
                    "Validate medical completeness",
                    "Format output"
                ],
                "estimated_time": 8,
                "priority": "routine",
                "requires_specialist": False
            }
        }
        
        return plans.get(action_type, plans["appointment"])


# Global instance
coordinator_agent = CoordinatorAgent()
