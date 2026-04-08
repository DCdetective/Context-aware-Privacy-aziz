from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
import logging
import json
from datetime import datetime
from utils.config import settings

from agents.coordinator import coordinator
from agents.session_manager import session_manager
from database.identity_vault import identity_vault

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])
DEFAULT_INTENT = "general"
STREAM_CHUNK_SIZE = max(1, int(getattr(settings, "stream_chunk_size", 6)))


EventType = Literal[
    "user_message",
    "assistant_message",
    "stream_chunk",
    "workflow_step",
    "privacy_mask",
    "appointment_card",
    "followup_card",
    "summary_card",
    "hitl_prompt",
    "system_notice",
    "error_event",
]
EVENT_TYPES = {
    "user_message",
    "assistant_message",
    "stream_chunk",
    "workflow_step",
    "privacy_mask",
    "appointment_card",
    "followup_card",
    "summary_card",
    "hitl_prompt",
    "system_notice",
    "error_event",
}


class ChatMessage(BaseModel):
    """Chat message model."""
    message: str = Field(..., min_length=0)
    session_id: Optional[str] = None


class ChatActionRequest(BaseModel):
    action: str
    value: str


class StreamChatRequest(BaseModel):
    message: str = Field(..., min_length=0)
    session_id: Optional[str] = None


class SessionCreateResponse(BaseModel):
    success: bool
    session_id: str


class SessionEventsResponse(BaseModel):
    success: bool
    session_id: str
    events: List[Dict[str, Any]]


class SessionSnapshotResponse(BaseModel):
    success: bool
    session_id: str
    snapshot: Dict[str, Any]


class ChatResponse(BaseModel):
    """Backward-compatible chat response model with event payloads."""
    success: bool
    message: str
    intent: str
    patient_uuid: Optional[str] = None
    patient_name: Optional[str] = None
    session_id: Optional[str] = None
    result: Dict[str, Any]
    privacy_safe: bool
    workflow_steps: List[str]
    events: List[Dict[str, Any]] = []


AGENT_RESPONSIBILITIES = {
    "Gatekeeper": "privacy masking",
    "Coordinator": "routing/planning",
    "Context Agent": "context retrieval",
    "Execution Agent": "task execution",
    "Memory Manager": "save/retrieve history",
    "HITL Manager": "waiting for user confirmation",
}


def _build_privacy_details(result: Dict[str, Any]) -> Dict[str, Any]:
    privacy_report = result.get("privacy_report")
    if not privacy_report:
        return {"transformations": [], "pii_removed": 0, "cloud_safe": True}
    return {
        "transformations": privacy_report.get("transformations", []),
        "pii_removed": privacy_report.get("pii_removed", 0),
        "cloud_safe": privacy_report.get("cloud_safe", True),
    }


def _canonicalize_session_id(session_id: Optional[str]) -> str:
    if session_id:
        exists = session_manager.get_session(session_id)
        if exists:
            return session_id
    return session_manager.create_session()


def _build_workflow_events(workflow_steps: List[str], status: str = "completed") -> List[Dict[str, Any]]:
    events = []
    for idx, step in enumerate(workflow_steps):
        agent = None
        responsibility = None
        for agent_name, agent_resp in AGENT_RESPONSIBILITIES.items():
            if agent_name.lower() in step.lower():
                agent = agent_name
                responsibility = agent_resp
                break
        events.append({
            "event_type": "workflow_step",
            "status": status,
            "agent": agent,
            "payload": {
                "index": idx + 1,
                "step": step,
                "responsibility": responsibility,
                "timestamp": datetime.utcnow().isoformat(),
            },
        })
    return events


def _result_card_event(intent: str, result_payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if intent == "appointment":
        return {"event_type": "appointment_card", "status": "completed", "payload": result_payload}
    if intent == "followup":
        return {"event_type": "followup_card", "status": "completed", "payload": result_payload}
    if intent == "summary":
        return {"event_type": "summary_card", "status": "completed", "payload": result_payload}
    return None


def _persist_events(session_id: str, events: List[Dict[str, Any]]) -> None:
    for event in events:
        event_type = event.get("event_type")
        if event_type not in EVENT_TYPES:
            continue
        session_manager.add_event(
            session_id=session_id,
            event_type=event_type,
            status=event.get("status", "completed"),
            agent=event.get("agent"),
            role=event.get("role"),
            payload=event.get("payload", {}),
        )


def _process_chat_message(message: str, session_id: Optional[str]) -> Dict[str, Any]:
    canonical_session_id = _canonicalize_session_id(session_id)
    session_before = session_manager.get_session(canonical_session_id) or {}

    pre_events = [{
        "event_type": "system_notice",
        "status": "completed",
        "agent": "Memory Manager",
        "payload": {
            "notice": "Memory read completed",
            "operation": "memory_read",
            "timestamp": datetime.utcnow().isoformat(),
        },
    }]
    _persist_events(canonical_session_id, pre_events)

    result = coordinator.process_message(message, session_id=canonical_session_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message", "Processing failed"))

    privacy_details = _build_privacy_details(result)
    result_payload = {
        **result.get("result", {}),
        "privacy_details": privacy_details,
        "patient_name": result.get("patient_name"),
        "session_id": result.get("session_id") or canonical_session_id,
    }

    if result.get("disambiguation_data"):
        result_payload["disambiguation_data"] = result["disambiguation_data"]

    events: List[Dict[str, Any]] = []
    events.extend(pre_events)

    events.extend(_build_workflow_events(result.get("workflow_steps", []), status="completed"))

    for transform in privacy_details.get("transformations", []):
        events.append({
            "event_type": "privacy_mask",
            "status": "completed",
            "agent": "Gatekeeper",
            "payload": {
                "field": transform.get("field"),
                "original": transform.get("original"),
                "transformed": transform.get("transformed"),
                "method": transform.get("method"),
                "timestamp": datetime.utcnow().isoformat(),
            },
        })

    events.append({
        "event_type": "assistant_message",
        "status": "completed",
        "role": "assistant",
        "payload": {"content": result.get("message", "")},
    })

    card_event = _result_card_event(result.get("intent", DEFAULT_INTENT), result_payload)
    if card_event:
        events.append(card_event)

    if result.get("intent") in {"confirmation_required", "awaiting_confirmation", "disambiguation_required"}:
        events.append({
            "event_type": "hitl_prompt",
            "status": "pending",
            "agent": "HITL Manager",
            "payload": {"prompt": result.get("message", "")},
        })

    session_after = session_manager.get_session(canonical_session_id) or {}
    if session_before.get("workflow_stage") != session_after.get("workflow_stage"):
        events.append({
            "event_type": "workflow_step",
            "status": "completed",
            "agent": "Coordinator",
            "payload": {
                "checkpoint": True,
                "from_stage": session_before.get("workflow_stage"),
                "to_stage": session_after.get("workflow_stage"),
                "workflow": session_after.get("active_workflow"),
                "timestamp": datetime.utcnow().isoformat(),
            },
        })

    events.append({
        "event_type": "system_notice",
        "status": "completed",
        "agent": "Memory Manager",
        "payload": {
            "notice": "Memory write completed",
            "operation": "memory_write",
            "timestamp": datetime.utcnow().isoformat(),
        },
    })

    _persist_events(canonical_session_id, events)

    return {
        "chat_response": ChatResponse(
            success=result["success"],
            message=result["message"],
            intent=result.get("intent", DEFAULT_INTENT),
            patient_uuid=result.get("patient_uuid"),
            patient_name=result.get("patient_name"),
            session_id=result.get("session_id") or canonical_session_id,
            result=result_payload,
            privacy_safe=result.get("privacy_safe", True),
            workflow_steps=result.get("workflow_steps", []),
            events=events,
        ),
        "session_id": canonical_session_id,
    }


@router.post("/sessions", response_model=SessionCreateResponse)
async def create_session():
    """Create a canonical chat session."""
    sid = session_manager.create_session()
    return {"success": True, "session_id": sid}


@router.get("/sessions/{session_id}", response_model=SessionSnapshotResponse)
async def get_session_snapshot(session_id: str):
    """Restore full session state for frontend refresh/restart."""
    try:
        snapshot = session_manager.get_session_snapshot(session_id)
        return {"success": True, "session_id": session_id, "snapshot": snapshot}
    except ValueError:
        raise HTTPException(status_code=404, detail="Session not found")
    except Exception as e:
        logger.error(f"Error restoring session snapshot: {e}")
        raise HTTPException(status_code=500, detail="Internal error")


@router.get("/sessions/{session_id}/events", response_model=SessionEventsResponse)
async def get_session_events(session_id: str):
    """Get ordered event timeline for a session."""
    try:
        session = session_manager.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        events = session_manager.list_events(session_id)
        return {"success": True, "session_id": session_id, "events": events}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting session events: {e}")
        raise HTTPException(status_code=500, detail="Internal error")


@router.post("/sessions/{session_id}/actions", response_model=ChatResponse)
async def submit_session_action(session_id: str, action: ChatActionRequest):
    """Submit HITL action value back into the canonical chat pipeline."""
    try:
        if action.action not in {"hitl_response", "confirm", "disambiguation_select"}:
            raise HTTPException(status_code=400, detail="Unsupported action")
        processed = _process_chat_message(action.value, session_id)
        return processed["chat_response"]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting session action: {e}")
        raise HTTPException(status_code=500, detail="Internal error")


@router.post("/message", response_model=ChatResponse)
async def send_message(chat_message: ChatMessage):
    """Process chat message with detailed privacy tracking and event persistence."""
    try:
        processed = _process_chat_message(chat_message.message, chat_message.session_id)
        return processed["chat_response"]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in chat API: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal error")


@router.post("/stream")
async def stream_message(stream_request: StreamChatRequest):
    """Stream structured chat events and assistant chunks for live UI updates."""

    async def event_generator():
        try:
            canonical_session_id = _canonicalize_session_id(stream_request.session_id)

            session_before = session_manager.get_session(canonical_session_id) or {}
            pre_event = {
                "event_type": "system_notice",
                "status": "completed",
                "agent": "Memory Manager",
                "payload": {
                    "notice": "Memory read completed",
                    "operation": "memory_read",
                    "timestamp": datetime.utcnow().isoformat(),
                },
            }
            _persist_events(canonical_session_id, [pre_event])
            yield f"data: {json.dumps(pre_event)}\n\n"

            result = coordinator.process_message(stream_request.message, session_id=canonical_session_id)
            if not result.get("success"):
                error_event = {
                    "event_type": "error_event",
                    "status": "failed",
                    "payload": {"message": result.get("message", "Processing failed")},
                }
                _persist_events(canonical_session_id, [error_event])
                yield f"data: {json.dumps(error_event)}\n\n"
                return

            workflow_events = _build_workflow_events(result.get("workflow_steps", []), status="running")
            for event in workflow_events:
                yield f"data: {json.dumps(event)}\n\n"
                event["status"] = "completed"
                _persist_events(canonical_session_id, [event])
                yield f"data: {json.dumps(event)}\n\n"

            privacy_details = _build_privacy_details(result)
            for transform in privacy_details.get("transformations", []):
                p_event = {
                    "event_type": "privacy_mask",
                    "status": "completed",
                    "agent": "Gatekeeper",
                    "payload": {
                        "field": transform.get("field"),
                        "original": transform.get("original"),
                        "transformed": transform.get("transformed"),
                        "method": transform.get("method"),
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                }
                _persist_events(canonical_session_id, [p_event])
                yield f"data: {json.dumps(p_event)}\n\n"

            final_message = result.get("message", "")
            words = final_message.split()
            chunks = [
                " ".join(words[i:i + STREAM_CHUNK_SIZE]).strip()
                for i in range(0, len(words), STREAM_CHUNK_SIZE)
            ]
            for chunk in chunks:
                chunk_event = {
                    "event_type": "stream_chunk",
                    "status": "running",
                    "role": "assistant",
                    "payload": {"chunk": chunk, "session_id": canonical_session_id},
                }
                _persist_events(canonical_session_id, [chunk_event])
                yield f"data: {json.dumps(chunk_event)}\n\n"

            assistant_event = {
                "event_type": "assistant_message",
                "status": "completed",
                "role": "assistant",
                "payload": {"content": final_message, "session_id": canonical_session_id},
            }
            _persist_events(canonical_session_id, [assistant_event])
            yield f"data: {json.dumps(assistant_event)}\n\n"

            result_payload = {
                **result.get("result", {}),
                "privacy_details": privacy_details,
                "patient_name": result.get("patient_name"),
                "session_id": result.get("session_id") or canonical_session_id,
            }

            card_event = _result_card_event(result.get("intent", DEFAULT_INTENT), result_payload)
            if card_event:
                _persist_events(canonical_session_id, [card_event])
                yield f"data: {json.dumps(card_event)}\n\n"

            if result.get("intent") in {"confirmation_required", "awaiting_confirmation", "disambiguation_required"}:
                hitl_event = {
                    "event_type": "hitl_prompt",
                    "status": "pending",
                    "agent": "HITL Manager",
                    "payload": {"prompt": final_message},
                }
                _persist_events(canonical_session_id, [hitl_event])
                yield f"data: {json.dumps(hitl_event)}\n\n"

            session_after = session_manager.get_session(canonical_session_id) or {}
            if session_before.get("workflow_stage") != session_after.get("workflow_stage"):
                checkpoint_event = {
                    "event_type": "workflow_step",
                    "status": "completed",
                    "agent": "Coordinator",
                    "payload": {
                        "checkpoint": True,
                        "from_stage": session_before.get("workflow_stage"),
                        "to_stage": session_after.get("workflow_stage"),
                        "workflow": session_after.get("active_workflow"),
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                }
                _persist_events(canonical_session_id, [checkpoint_event])
                yield f"data: {json.dumps(checkpoint_event)}\n\n"

            memory_write_event = {
                "event_type": "system_notice",
                "status": "completed",
                "agent": "Memory Manager",
                "payload": {
                    "notice": "Memory write completed",
                    "operation": "memory_write",
                    "timestamp": datetime.utcnow().isoformat(),
                },
            }
            _persist_events(canonical_session_id, [memory_write_event])
            yield f"data: {json.dumps(memory_write_event)}\n\n"

            done_event = {
                "event_type": "system_notice",
                "status": "completed",
                "payload": {
                    "notice": "stream_complete",
                    "session_id": canonical_session_id,
                    "intent": result.get("intent", DEFAULT_INTENT),
                    "workflow_steps": result.get("workflow_steps", []),
                    "privacy_safe": result.get("privacy_safe", True),
                },
            }
            yield f"data: {json.dumps(done_event)}\n\n"
        except Exception as e:
            logger.error(f"Error in stream endpoint: {str(e)}")
            error_event = {
                "event_type": "error_event",
                "status": "failed",
                "payload": {"message": "Internal stream error"},
            }
            yield f"data: {json.dumps(error_event)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/privacy-report")
async def get_privacy_report():
    """
    Get privacy compliance report.

    Returns:
        Privacy compliance statistics
    """
    try:
        report = identity_vault.verify_privacy_compliance()

        return {
            "success": True,
            "report": report,
            "message": "Privacy compliance verified" if report["privacy_compliant"] else "Privacy violations detected",
        }

    except Exception as e:
        logger.error(f"Error generating privacy report: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error generating report: {str(e)}")
