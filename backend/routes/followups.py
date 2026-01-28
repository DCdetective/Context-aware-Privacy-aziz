from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
import logging

from agents.gatekeeper import gatekeeper_agent
from agents.coordinator import coordinator_agent
from agents.worker import worker_agent
from database.identity_vault import identity_vault

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/followups", tags=["followups"])


class FollowUpRequest(BaseModel):
    """Request model for follow-up scheduling."""
    patient_name: str = Field(..., description="Patient full name")


class FollowUpResponse(BaseModel):
    """Response model for follow-up scheduling."""
    success: bool
    message: str
    patient_name: Optional[str] = None
    patient_uuid: Optional[str] = None
    followup_time: Optional[str] = None
    previous_visits: Optional[int] = None
    continuity_maintained: Optional[bool] = None
    record_id: Optional[str] = None


@router.post("/schedule", response_model=FollowUpResponse)
async def schedule_followup(request: FollowUpRequest):
    """
    Schedule a follow-up appointment using stored context.
    
    Workflow:
    1. Lookup patient UUID from name
    2. Retrieve semantic context from previous visits
    3. Coordinator: Plan follow-up
    4. Worker: Execute follow-up scheduling
    5. Gatekeeper: Re-identify for output
    """
    try:
        logger.info("=" * 70)
        logger.info("API: FOLLOW-UP SCHEDULING REQUEST")
        logger.info("=" * 70)
        
        logger.info(f"Step 1: Received follow-up request for {request.patient_name}")
        
        # Step 2: Lookup patient UUID (requires basic identity info)
        # We need at least name to identify the patient
        # In a real system, you might require age/gender for disambiguation
        logger.info("Step 2: Looking up patient UUID...")
        
        # Create a minimal pseudonymization call to get UUID
        # This is a simplified approach - in production, you'd need better patient lookup
        user_input = f"Patient Name: {request.patient_name}, Age: 0, Gender: Unknown, Symptoms: Follow-up request"
        pseudo_data = gatekeeper_agent.pseudonymize_input(user_input)
        
        patient_uuid = pseudo_data["patient_uuid"]
        logger.info(f"         Found UUID: {patient_uuid[:8]}...")
        
        # Step 3: Retrieve previous semantic context
        logger.info("Step 3: Retrieving previous medical context...")
        semantic_context = pseudo_data.get("semantic_context", {})
        
        # Step 4: Coordinator planning
        logger.info("Step 4: Invoking Coordinator for follow-up planning...")
        coord_result = coordinator_agent.coordinate_request(
            patient_uuid=patient_uuid,
            action_type="followup",
            semantic_context=semantic_context
        )
        
        if not coord_result.get("ready_for_worker"):
            raise HTTPException(status_code=400, detail="Coordination failed")
        
        # Step 5: Worker execution
        logger.info("Step 5: Invoking Worker for follow-up execution...")
        worker_result = worker_agent.execute_task(
            patient_uuid=patient_uuid,
            action_type="followup",
            execution_plan=coord_result["execution_plan"],
            semantic_context=semantic_context
        )
        
        if not worker_result.get("success"):
            raise HTTPException(status_code=500, detail="Worker execution failed")
        
        # Step 6: Gatekeeper re-identification
        logger.info("Step 6: Invoking Gatekeeper for re-identification...")
        final_output = gatekeeper_agent.reidentify_output(patient_uuid, worker_result)
        
        # Step 7: Format response
        response = FollowUpResponse(
            success=True,
            message=f"Follow-up scheduled successfully for {final_output.get('patient_name')}",
            patient_name=final_output.get("patient_name"),
            patient_uuid=patient_uuid,
            followup_time=final_output.get("followup_time"),
            previous_visits=final_output.get("previous_visits"),
            continuity_maintained=final_output.get("continuity_maintained"),
            record_id=final_output.get("record_id")
        )
        
        logger.info("=" * 70)
        logger.info("API: FOLLOW-UP SCHEDULED SUCCESSFULLY")
        logger.info("=" * 70)
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error scheduling follow-up: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")
