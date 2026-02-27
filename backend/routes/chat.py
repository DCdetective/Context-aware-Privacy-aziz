from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import logging

from agents.coordinator import coordinator
from database.identity_vault import identity_vault
from mcp.bridge import mcp_bridge

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
    """Process chat message with detailed privacy tracking."""
    try:
        logger.info("=" * 70)
        logger.info(f"CHAT API: Received message")
        logger.info("=" * 70)
        
        # Process through coordinator
        result = coordinator.process_message(
            chat_message.message,
            session_id=chat_message.session_id
        )
        
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("message", "Processing failed"))
        
        # Format privacy details for frontend visualization
        privacy_report = result.get('privacy_report')
        privacy_details = None

        if privacy_report:
            transformations = privacy_report.get('transformations', [])

            # Build original_contains from transformation data for frontend
            original_contains = {"name": None, "age": None, "gender": None}
            for t in transformations:
                field = t.get("field", "").lower()
                if "name" in field:
                    original_contains["name"] = t.get("original")
                elif "age" in field:
                    original_contains["age"] = t.get("original")
                elif "gender" in field:
                    original_contains["gender"] = t.get("original")

            privacy_details = {
                "transformations": transformations,
                "pii_detected": privacy_report.get('pii_removed', 0) > 0,
                "pii_removed": privacy_report.get('pii_removed', 0),
                "cloud_safe": privacy_report.get('cloud_safe', True),
                "original_contains": original_contains,
                "pseudonymized_to": result.get("patient_uuid"),
            }
        
        # Format response
        response = ChatResponse(
            success=result["success"],
            message=result["message"],
            intent=result.get("intent", "general"),
            patient_uuid=result.get("patient_uuid"),
            patient_name=result.get("patient_name"),
            result={
                **result.get("result", {}),
                "privacy_details": privacy_details
            },
            privacy_safe=result.get("privacy_safe", True),
            workflow_steps=result.get("workflow_steps", [])
        )
        
        # Add disambiguation data if present
        if result.get("disambiguation_data"):
            response.result["disambiguation_data"] = result["disambiguation_data"]
        
        # Add session ID
        if result.get("session_id"):
            response.result["session_id"] = result["session_id"]
        
        logger.info("CHAT API: Message processed successfully")
        logger.info("=" * 70)
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in chat API: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.get("/privacy-report")
async def get_privacy_report():
    """
    Get privacy compliance report.
    
    Returns:
        Privacy compliance statistics
    """
    try:
        # Get compliance report from identity vault
        report = identity_vault.verify_privacy_compliance()

        # Get MCP bridge compliance report
        mcp_report = mcp_bridge.get_compliance_report()

        return {
            "success": True,
            "report": report,
            "mcp_bridge": mcp_report,
            "message": "Privacy compliance verified" if report["privacy_compliant"] else "Privacy violations detected"
        }
        
    except Exception as e:
        logger.error(f"Error generating privacy report: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error generating report: {str(e)}")
