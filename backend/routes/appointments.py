from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
import logging

from agents.gatekeeper import gatekeeper_agent
from agents.coordinator import CoordinatorAgent
from agents.worker import worker_agent

# Deterministic planner for API routes (avoids external LLM calls during tests)
_coordinator = CoordinatorAgent()

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/appointments", tags=["appointments"])


class AppointmentRequest(BaseModel):
    """Request model for appointment scheduling."""
    patient_name: str = Field(..., description="Patient full name")
    age: int = Field(..., ge=0, le=150, description="Patient age")
    gender: str = Field(..., description="Patient gender")
    symptoms: str = Field(..., description="Patient symptoms")


class AppointmentResponse(BaseModel):
    """Response model for appointment scheduling."""
    success: bool
    message: str
    patient_name: Optional[str] = None
    patient_uuid: Optional[str] = None
    appointment_time: Optional[str] = None
    consultation_duration: Optional[int] = None
    urgency_level: Optional[str] = None
    record_id: Optional[str] = None


@router.post("/schedule", response_model=AppointmentResponse)
async def schedule_appointment(request: AppointmentRequest):
    """
    Schedule a new appointment with privacy-preserving workflow.
    
    Workflow:
    1. Gatekeeper: Pseudonymize patient data
    2. Coordinator: Plan appointment scheduling
    3. Worker: Execute appointment booking
    4. Gatekeeper: Re-identify for output
    5. Return user-friendly response
    """
    try:
        logger.info("=" * 70)
        logger.info("API: APPOINTMENT SCHEDULING REQUEST")
        logger.info("=" * 70)
        
        # Step 1: Format input for Gatekeeper
        user_input = f"""
        Patient Name: {request.patient_name}
        Age: {request.age}
        Gender: {request.gender}
        Symptoms: {request.symptoms}
        """
        
        logger.info(f"Step 1: Received appointment request for {request.patient_name}")
        
        # Step 2: Gatekeeper pseudonymization
        logger.info("Step 2: Invoking Gatekeeper for pseudonymization...")
        pseudo_data = gatekeeper_agent.pseudonymize_input(user_input)
        
        patient_uuid = pseudo_data["patient_uuid"]
        semantic_context = pseudo_data["semantic_context"]
        
        logger.info(f"         Pseudonymized to UUID: {patient_uuid[:8]}...")
        
        # Step 3: Coordinator planning (deterministic)
        logger.info("Step 3: Invoking Coordinator for task planning...")
        coord_result = _coordinator.coordinate_request(
            patient_uuid=patient_uuid,
            action_type="appointment",
            semantic_context=semantic_context,
        )
        
        if coord_result.get("success") is False:
            raise HTTPException(status_code=400, detail=coord_result.get("error", "Coordination failed"))
        
        logger.info("         Coordination complete")
        
        # Step 4: Worker execution
        logger.info("Step 4: Invoking Worker for appointment execution...")
        worker_result = worker_agent.execute_task(
            patient_uuid=patient_uuid,
            action_type="appointment",
            execution_plan=coord_result["execution_plan"],
            semantic_context=semantic_context
        )
        
        if not worker_result.get("success"):
            raise HTTPException(status_code=500, detail="Worker execution failed")
        
        logger.info("         Appointment scheduled successfully")
        
        # Step 5: Gatekeeper re-identification
        logger.info("Step 5: Invoking Gatekeeper for re-identification...")
        final_output = gatekeeper_agent.reidentify_output(patient_uuid, worker_result)
        
        logger.info(f"         Re-identified patient: {final_output.get('patient_name')}")
        
        # Step 6: Format response
        response = AppointmentResponse(
            success=True,
            message=f"Appointment scheduled successfully for {final_output.get('patient_name')}",
            patient_name=final_output.get("patient_name"),
            patient_uuid=patient_uuid,
            appointment_time=final_output.get("appointment_time"),
            consultation_duration=final_output.get("consultation_duration"),
            urgency_level=final_output.get("urgency_level"),
            record_id=final_output.get("record_id")
        )
        
        logger.info("=" * 70)
        logger.info("API: APPOINTMENT SCHEDULED SUCCESSFULLY")
        logger.info("=" * 70)
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error scheduling appointment: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")
