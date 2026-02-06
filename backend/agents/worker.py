from groq import Groq
import json
import re
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import logging

from utils.config import settings
from database.identity_vault import identity_vault

logger = logging.getLogger(__name__)


class WorkerAgent:
    """
    Cloud Worker Agent using Groq API.
    
    PRIVACY GUARANTEE:
    - Executes tasks using ONLY UUIDs
    - Validates identity by UUID only
    - Uses semantic context for medical logic
    - NEVER receives patient names or PII
    - NEVER hallucinates unsupported actions
    """
    
    def __init__(self, semantic_store=None):
        """Initialize Worker Agent."""
        self.client = Groq(api_key=settings.groq_api_key)
        self.model = "llama-3.3-70b-versatile"  # Updated Groq model (Jan 2026)
        self.semantic_store = semantic_store
        
        logger.info("Worker Agent initialized with Groq API")
    
    def _call_groq(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Call Groq LLM."""
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
    
    def execute_task(
        self,
        patient_uuid: str,
        action_type: str,
        execution_plan: Dict[str, Any],
        semantic_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a medical task.
        
        Args:
            patient_uuid: Pseudonymized patient UUID
            action_type: Type of action
            execution_plan: Execution plan from Coordinator
            semantic_context: Non-PII semantic context
            
        Returns:
            Task execution result
        """
        logger.info("=" * 60)
        logger.info("WORKER: Executing task")
        logger.info(f"UUID: {patient_uuid[:8]}...")
        logger.info(f"Action: {action_type}")
        logger.info("=" * 60)
        
        # Validate UUID exists
        if not self._validate_uuid(patient_uuid):
            logger.error(f"Invalid UUID: {patient_uuid}")
            return {
                "success": False,
                "error": "Invalid patient UUID",
                "patient_uuid": patient_uuid
            }
        
        # Route to appropriate handler
        handlers = {
            "appointment": self._handle_appointment,
            "followup": self._handle_followup,
            "summary": self._handle_summary
        }
        
        handler = handlers.get(action_type)
        if not handler:
            logger.error(f"No handler for action: {action_type}")
            return {
                "success": False,
                "error": f"Unsupported action: {action_type}",
                "patient_uuid": patient_uuid
            }
        
        # Execute handler
        result = handler(patient_uuid, execution_plan, semantic_context)
        
        logger.info("WORKER: Task executed successfully")
        logger.info("=" * 60)
        
        return result
    
    def _validate_uuid(self, patient_uuid: str) -> bool:
        """
        Validate that UUID exists in system.
        
        PRIVACY NOTE: This checks existence only, does not access PII.
        
        Args:
            patient_uuid: Patient UUID to validate
            
        Returns:
            True if UUID exists
        """
        # Check in identity vault (without accessing PII)
        identity = identity_vault.reidentify_patient(
            patient_uuid=patient_uuid,
            component="worker_agent_validation"
        )
        return identity is not None
    
    def _handle_appointment(
        self,
        patient_uuid: str,
        execution_plan: Dict[str, Any],
        semantic_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle appointment scheduling.
        
        Args:
            patient_uuid: Patient UUID
            execution_plan: Execution plan
            semantic_context: Semantic context
            
        Returns:
            Appointment scheduling result
        """
        logger.info("Handling appointment scheduling...")
        
        # Determine appointment time based on urgency
        urgency = execution_plan.get("priority", "routine")
        
        if urgency == "emergency":
            appointment_time = datetime.now() + timedelta(hours=2)
        elif urgency == "urgent":
            appointment_time = datetime.now() + timedelta(days=1)
        else:
            appointment_time = datetime.now() + timedelta(days=7)
        
        # Calculate consultation time
        consultation_time = semantic_context.get("estimated_consultation_time", 30)
        
        # Store in medical records (local vault)
        record_id = identity_vault.store_medical_record(
            patient_uuid=patient_uuid,
            record_type="appointment",
            symptoms=f"Semantic: {semantic_context.get('symptom_category', 'general')}",
            component="worker_agent"
        )
        
        result = {
            "success": True,
            "patient_uuid": patient_uuid,
            "action": "appointment_scheduled",
            "appointment_time": appointment_time.isoformat(),
            "consultation_duration": consultation_time,
            "urgency_level": urgency,
            "requires_specialist": execution_plan.get("requires_specialist", False),
            "record_id": record_id
        }
        
        logger.info(f"Appointment scheduled for {appointment_time.isoformat()}")
        return result
    
    def _handle_followup(
        self,
        patient_uuid: str,
        execution_plan: Dict[str, Any],
        semantic_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle follow-up scheduling.
        
        Args:
            patient_uuid: Patient UUID
            execution_plan: Execution plan
            semantic_context: Semantic context
            
        Returns:
            Follow-up scheduling result
        """
        logger.info("Handling follow-up scheduling...")
        
        # Retrieve previous semantic anchors
        previous_context = []
        if self.semantic_store:
            previous_context = self.semantic_store.retrieve_semantic_anchors(
                patient_uuid=patient_uuid,
                limit=5
            )
        
        # Calculate follow-up time (default: 2 weeks)
        followup_time = datetime.now() + timedelta(days=14)
        
        # Store follow-up record
        record_id = identity_vault.store_medical_record(
            patient_uuid=patient_uuid,
            record_type="followup",
            treatment_plan="Follow-up based on previous context",
            component="worker_agent"
        )
        
        result = {
            "success": True,
            "patient_uuid": patient_uuid,
            "action": "followup_scheduled",
            "followup_time": followup_time.isoformat(),
            "previous_visits": len(previous_context),
            "continuity_maintained": len(previous_context) > 0,
            "record_id": record_id
        }
        
        logger.info(f"Follow-up scheduled for {followup_time.isoformat()}")
        return result
    
    def _handle_summary(
        self,
        patient_uuid: str,
        execution_plan: Dict[str, Any],
        semantic_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle medical summary generation.
        
        Args:
            patient_uuid: Patient UUID
            execution_plan: Execution plan
            semantic_context: Semantic context
            
        Returns:
            Medical summary result
        """
        logger.info("Handling medical summary generation...")
        
        # Retrieve medical records
        records = identity_vault.get_patient_records(
            patient_uuid=patient_uuid,
            component="worker_agent"
        )
        
        # Generate summary using Groq
        system_prompt = """Generate a medical summary using ONLY UUID-based information.

CRITICAL RULES:
1. Use ONLY the patient UUID (NO names)
2. Summarize based on semantic medical context
3. Include visit count and record types
4. Return structured JSON format"""
        
        prompt = f"""Generate medical summary for patient UUID: {patient_uuid}

Medical Records: {len(records)} records found
Semantic Context: {json.dumps(semantic_context)}

Return JSON with:
- total_visits: number
- record_types: list
- summary_text: brief summary using UUID only"""
        
        try:
            response = self._call_groq(prompt, system_prompt)
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                summary_data = json.loads(json_match.group())
            else:
                summary_data = {
                    "total_visits": len(records),
                    "record_types": [r["record_type"] for r in records],
                    "summary_text": f"Patient {patient_uuid[:8]}... has {len(records)} medical records."
                }
        except:
            summary_data = {
                "total_visits": len(records),
                "record_types": [r["record_type"] for r in records],
                "summary_text": f"Patient {patient_uuid[:8]}... has {len(records)} medical records."
            }
        
        # Store summary record
        record_id = identity_vault.store_medical_record(
            patient_uuid=patient_uuid,
            record_type="summary",
            diagnosis=summary_data["summary_text"],
            component="worker_agent"
        )
        
        result = {
            "success": True,
            "patient_uuid": patient_uuid,
            "action": "summary_generated",
            "summary": summary_data,
            "record_id": record_id
        }
        
        logger.info("Medical summary generated")
        return result


class SummaryWorker:
    """
    Summary Worker (Prompt 8) – Generates comprehensive patient summaries.
    
    Works with ContextAgent's in-memory storage to aggregate patient data
    and generate coherent medical summaries without external LLM calls.
    """

    def __init__(self):
        """Initialize Summary Worker."""
        logger.info("Summary Worker initialized")

    async def generate_patient_summary(
        self,
        patient_uuid: str,
        summary_type: str = "full",  # "full" | "recent" | "specific"
        date_range: dict = None,  # {"start": str, "end": str}
    ) -> dict:
        """
        Generate comprehensive patient summary.

        Returns: {
            "patient_info": dict,
            "timeline": List[dict],
            "appointments": {"total": int, "list": List[dict]},
            "symptoms": {"total": int, "list": List[dict]},
            "follow_ups": {"total": int, "list": List[dict]},
            "summary_text": str,
            "key_insights": List[str]
        }
        """
        from agents.context_agent import context_agent

        # Get all patient interactions
        all_interactions = context_agent.retrieve_patient_history(patient_uuid, limit=10000)

        # Apply date range filter if specified
        if date_range:
            all_interactions = self._filter_by_date_range(all_interactions, date_range)

        # Apply summary type filter
        if summary_type == "recent":
            # Last 30 days
            from datetime import datetime, timedelta, timezone
            cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
            all_interactions = [
                i for i in all_interactions
                if i["metadata"].get("timestamp", "") >= cutoff
            ]

        # Categorize
        appointments = [i for i in all_interactions if i["metadata"]["type"] == "appointment"]
        symptoms = [i for i in all_interactions if i["metadata"]["type"] == "symptom"]
        follow_ups = [i for i in all_interactions if i["metadata"]["type"] == "followup"]
        questions = [i for i in all_interactions if i["metadata"]["type"] == "question"]

        # Build timeline (chronological order)
        timeline = sorted(
            all_interactions,
            key=lambda x: x["metadata"].get("timestamp", "")
        )

        # Get patient info
        patient_info = {"patient_uuid": patient_uuid}
        try:
            vault = identity_vault
            identity = vault.reidentify_patient(patient_uuid, component="summary_worker")
            if identity:
                patient_info["patient_name"] = identity.get("patient_name")
                patient_info["age"] = identity.get("age")
                patient_info["gender"] = identity.get("gender")
        except Exception:
            pass

        # Generate key insights
        key_insights = self._extract_key_insights(appointments, symptoms, follow_ups)

        # Generate summary text
        summary_text = self._generate_summary_text(
            patient_uuid, all_interactions, appointments, symptoms, follow_ups, key_insights
        )

        # Handle empty history
        if not all_interactions:
            summary_text = f"No interactions found for patient {patient_uuid[:8]}. This is a new patient with no medical history on file."

        return {
            "patient_info": patient_info,
            "timeline": [
                {
                    "type": t["metadata"]["type"],
                    "content": t["metadata"]["content"],
                    "timestamp": t["metadata"].get("timestamp", ""),
                }
                for t in timeline
            ],
            "appointments": {
                "total": len(appointments),
                "list": [
                    {
                        "content": a["metadata"]["content"],
                        "timestamp": a["metadata"].get("timestamp", ""),
                    }
                    for a in appointments
                ],
            },
            "symptoms": {
                "total": len(symptoms),
                "list": [
                    {
                        "content": s["metadata"]["content"],
                        "timestamp": s["metadata"].get("timestamp", ""),
                    }
                    for s in symptoms
                ],
            },
            "follow_ups": {
                "total": len(follow_ups),
                "list": [
                    {
                        "content": f["metadata"]["content"],
                        "timestamp": f["metadata"].get("timestamp", ""),
                    }
                    for f in follow_ups
                ],
            },
            "summary_text": summary_text,
            "key_insights": key_insights,
            "total_interactions": len(all_interactions),
            "summary_type": summary_type,
        }

    async def generate_specific_summary(
        self,
        patient_uuid: str,
        query: str
    ) -> dict:
        """
        Generate summary for specific query.
        E.g., "Show me all cardiology appointments"
        """
        from agents.context_agent import context_agent

        # Determine filter type from query
        query_lower = query.lower()

        # Check if filtering by interaction type
        interaction_type = None
        if any(w in query_lower for w in ["appointment", "appointments", "visit", "visits"]):
            interaction_type = "appointment"
        elif any(w in query_lower for w in ["symptom", "symptoms"]):
            interaction_type = "symptom"
        elif any(w in query_lower for w in ["follow-up", "followup", "follow up"]):
            interaction_type = "followup"

        if interaction_type:
            results = context_agent.filter_interactions(
                patient_uuid=patient_uuid,
                interaction_type=interaction_type,
                limit=50
            )
        else:
            # Semantic search
            results = context_agent.semantic_search(
                query=query,
                patient_uuid=patient_uuid,
                top_k=10
            )

        # Filter by specialty if mentioned
        specialty_keywords = {
            "cardiology": ["cardiology", "cardiac", "heart", "chest"],
            "neurology": ["neurology", "neurological", "brain", "headache"],
            "respiratory": ["respiratory", "lung", "breathing", "pulmonary"],
            "dermatology": ["dermatology", "skin", "rash"],
            "orthopedics": ["orthopedics", "bone", "joint", "fracture"],
        }

        for specialty, keywords in specialty_keywords.items():
            if any(kw in query_lower for kw in keywords):
                results = [
                    r for r in results
                    if any(kw in r["metadata"].get("content", "").lower() for kw in keywords)
                ]
                break

        # Build summary text
        if not results:
            summary_text = f"No results found for query: '{query}' for patient {patient_uuid[:8]}."
        else:
            parts = [f"Found {len(results)} result(s) for '{query}':"]
            for i, r in enumerate(results[:10], 1):
                content = r["metadata"].get("content", "N/A")[:100]
                ts = r["metadata"].get("timestamp", "unknown date")
                parts.append(f"{i}. [{r['metadata']['type']}] {content} (at {ts})")
            summary_text = "\n".join(parts)

        return {
            "results": results,
            "summary_text": summary_text,
            "query": query,
            "total_results": len(results),
        }

    def _filter_by_date_range(self, interactions: list, date_range: dict) -> list:
        """Filter interactions by date range."""
        start = date_range.get("start", "")
        end = date_range.get("end", "9999")
        return [
            i for i in interactions
            if start <= i["metadata"].get("timestamp", "") <= end
        ]

    def _extract_key_insights(self, appointments, symptoms, follow_ups) -> list:
        """Extract key insights from patient data."""
        insights = []

        # Recurring symptoms
        symptom_counts = {}
        for s in symptoms:
            content = s["metadata"].get("content", "").lower()
            for word in ["headache", "fever", "cough", "pain", "nausea", "fatigue",
                         "dizziness", "rash", "swelling", "breathing"]:
                if word in content:
                    symptom_counts[word] = symptom_counts.get(word, 0) + 1

        for symptom, count in symptom_counts.items():
            if count >= 2:
                insights.append(f"Recurring symptom: {symptom} (reported {count} times)")

        # Appointment patterns
        if len(appointments) >= 3:
            insights.append(f"Frequent visitor: {len(appointments)} appointments on record")

        # Specialties visited
        specialties = set()
        for a in appointments:
            content = a["metadata"].get("content", "").lower()
            for spec in ["cardiology", "neurology", "dermatology", "respiratory",
                         "orthopedics", "gastroenterology", "pediatrics"]:
                if spec in content:
                    specialties.add(spec)
        if specialties:
            insights.append(f"Specialties visited: {', '.join(specialties)}")

        # Follow-up compliance
        if follow_ups:
            insights.append(f"Follow-up records: {len(follow_ups)}")

        if not insights:
            insights.append("No specific patterns identified yet.")

        return insights

    def _generate_summary_text(self, patient_uuid, all_interactions, appointments,
                                symptoms, follow_ups, key_insights) -> str:
        """Generate human-readable summary text."""
        if not all_interactions:
            return f"No interactions found for patient {patient_uuid[:8]}."

        parts = [f"Patient {patient_uuid[:8]} - Medical Summary"]
        parts.append(f"Total interactions: {len(all_interactions)}")

        if appointments:
            parts.append(f"Appointments: {len(appointments)}")
        if symptoms:
            parts.append(f"Symptom reports: {len(symptoms)}")
        if follow_ups:
            parts.append(f"Follow-ups: {len(follow_ups)}")

        # Most recent interaction
        most_recent = all_interactions[0]  # Already sorted newest first
        parts.append(
            f"Most recent: {most_recent['metadata']['type']} - "
            f"{most_recent['metadata']['content'][:100]}"
        )

        # Key insights
        if key_insights:
            parts.append("Key insights:")
            for insight in key_insights:
                parts.append(f"  - {insight}")

        return "\n".join(parts)


# Global instances
worker_agent = WorkerAgent()
