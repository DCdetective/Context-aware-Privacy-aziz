from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
import logging

from agents.gatekeeper import gatekeeper_agent
from agents.coordinator import coordinator
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
        
        # Step 2: Lookup patient UUID by name
        # For follow-ups, we look up existing patient by name only
        logger.info("Step 2: Looking up patient UUID by name...")
        
        # Look up patient in identity vault by name
        from database.identity_vault import identity_vault
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        
        session = identity_vault._get_session()
        try:
            from database.models import PatientIdentity
            # Find patient by name (case-insensitive)
            patient = session.query(PatientIdentity).filter(
                PatientIdentity.patient_name == request.patient_name
            ).first()
            
            if not patient:
                raise HTTPException(
                    status_code=404, 
                    detail=f"Patient '{request.patient_name}' not found. Please schedule an initial appointment first."
                )
            
            patient_uuid = patient.patient_uuid
            logger.info(f"         Found UUID: {patient_uuid[:8]}...")
        finally:
            session.close()
        
        # Step 3: Retrieve previous semantic context from semantic store
        logger.info("Step 3: Retrieving previous medical context...")
        semantic_context = {}
        # Try to get semantic anchors from the store if available
        try:
            from main import semantic_store
            if semantic_store:
                anchors = semantic_store.retrieve_semantic_anchors(patient_uuid, limit=1)
                if anchors:
                    semantic_context = anchors[0].get("semantic_data", {})
        except:
            logger.warning("Could not retrieve semantic context, using empty context")
            semantic_context = {}
        
        # Step 4: Coordinator planning
        logger.info("Step 4: Invoking Coordinator for follow-up planning...")
        # Use new coordinator with process_message
        message = f"Patient Name: {request.patient_name}, Request: Follow-up appointment"
        coord_result = coordinator.process_message(message)
        
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
