from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import logging

from agents.gatekeeper import gatekeeper_agent
from agents.coordinator import coordinator
from agents.worker import worker_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/summaries", tags=["summaries"])


class SummaryRequest(BaseModel):
    """Request model for medical summary generation."""
    patient_name: str = Field(..., description="Patient full name")


class SummaryResponse(BaseModel):
    """Response model for medical summary."""
    success: bool
    message: str
    patient_name: Optional[str] = None
    patient_uuid: Optional[str] = None
    summary: Optional[Dict[str, Any]] = None
    record_id: Optional[str] = None


@router.post("/generate", response_model=SummaryResponse)
async def generate_summary(request: SummaryRequest):
    """
    Generate a privacy-safe medical summary.
    
    Workflow:
    1. Lookup patient UUID from name
    2. Coordinator: Plan summary generation
    3. Worker: Generate summary using UUID-only data
    4. Gatekeeper: Re-identify for output
    5. Return summary with patient identity
    """
    try:
        logger.info("=" * 70)
        logger.info("API: MEDICAL SUMMARY GENERATION REQUEST")
        logger.info("=" * 70)
        
        logger.info(f"Step 1: Received summary request for {request.patient_name}")
        
        # Step 2: Lookup patient UUID
        logger.info("Step 2: Looking up patient UUID...")
        user_input = f"Patient Name: {request.patient_name}, Age: 0, Gender: Unknown, Symptoms: Summary request"
        pseudo_data = gatekeeper_agent.pseudonymize_input(user_input)
        
        patient_uuid = pseudo_data["patient_uuid"]
        logger.info(f"         Found UUID: {patient_uuid[:8]}...")
        
        # Step 3: Coordinator planning
        logger.info("Step 3: Invoking Coordinator for summary planning...")
        semantic_context = pseudo_data.get("semantic_context", {})
        
        # Use new coordinator with process_message
        message = f"Patient Name: {request.patient_name}, Request: Generate medical summary"
        coord_result = coordinator.process_message(message)
        
        if not coord_result.get("ready_for_worker"):
            raise HTTPException(status_code=400, detail="Coordination failed")
        
        # Step 4: Worker execution
        logger.info("Step 4: Invoking Worker for summary generation...")
        worker_result = worker_agent.execute_task(
            patient_uuid=patient_uuid,
            action_type="summary",
            execution_plan=coord_result["execution_plan"],
            semantic_context=semantic_context
        )
        
        if not worker_result.get("success"):
            raise HTTPException(status_code=500, detail="Worker execution failed")
        
        # Step 5: Gatekeeper re-identification
        logger.info("Step 5: Invoking Gatekeeper for re-identification...")
        final_output = gatekeeper_agent.reidentify_output(patient_uuid, worker_result)
        
        # Step 6: Format response
        response = SummaryResponse(
            success=True,
            message=f"Medical summary generated for {final_output.get('patient_name')}",
            patient_name=final_output.get("patient_name"),
            patient_uuid=patient_uuid,
            summary=final_output.get("summary"),
            record_id=final_output.get("record_id")
        )
        
        logger.info("=" * 70)
        logger.info("API: SUMMARY GENERATED SUCCESSFULLY")
        logger.info("=" * 70)
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating summary: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")
