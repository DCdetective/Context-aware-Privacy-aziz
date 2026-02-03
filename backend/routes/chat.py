from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import logging

from agents.coordinator import coordinator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatMessage(BaseModel):
    """Chat message model."""
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    """Chat response model."""
    success: bool
    message: str
    intent: str
    patient_uuid: Optional[str] = None
    patient_name: Optional[str] = None
    result: Dict[str, Any]
    privacy_safe: bool
    workflow_steps: List[str]


@router.post("/message", response_model=ChatResponse)
async def send_message(chat_message: ChatMessage):
    """
    Process a chat message through the multi-agent system.
    
    Workflow:
    1. User sends message
    2. Coordinator processes through agents
    3. Return response with results
    """
    try:
        logger.info("=" * 70)
        logger.info(f"CHAT API: Received message")
        logger.info("=" * 70)
        
        # Process through coordinator
        result = coordinator.process_message(chat_message.message)
        
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("message", "Processing failed"))
        
        # Format response
        response = ChatResponse(
            success=result["success"],
            message=result["message"],
            intent=result["intent"],
            patient_uuid=result.get("patient_uuid"),
            patient_name=result.get("patient_name"),
            result=result.get("result", {}),
            privacy_safe=result["privacy_safe"],
            workflow_steps=result.get("workflow_steps", [])
        )
        
        logger.info("CHAT API: Message processed successfully")
        logger.info("=" * 70)
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in chat API: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")
