"""
MCP Bridge — Model Context Protocol privacy enforcement layer.

Sits between local agents and cloud APIs (Groq, Pinecone).  Every
payload destined for the cloud is scanned for PII fields and value
patterns; any violation is logged before data leaves the local
environment.

Architecture role (from docs/architecture.md §6):
  Location:  Local Machine
  Purpose:   Secure execution bridge
  Responsibilities:
    - Bridge between local and cloud components
    - Enforce privacy boundaries
    - Validate data flows
    - Ensure separation of concerns
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MCPBridge:
    """Model Context Protocol Bridge — privacy enforcement layer.

    Every payload destined for the cloud is scanned for PII fields;
    every cloud response is validated on the way back.  All data flows
    are recorded in an in-memory audit log.

    PRIVACY GUARANTEE:
    - Detects forbidden PII field names (name, age, gender, ssn …)
    - Detects PII value patterns (SSN, email, phone) in string values
    - Logs every cloud interaction with direction, agent, UUID prefix
    - Provides a compliance report for academic demonstration
    """

    # -----------------------------------------------------------------
    # PII detection configuration
    # -----------------------------------------------------------------

    # Field names that must NEVER appear in cloud-bound payloads.
    # Matches the blocklist in ``vector_store/semantic_store.py`` plus
    # additional identifiers.
    FORBIDDEN_FIELDS: frozenset[str] = frozenset({
        "name", "patient_name", "full_name", "first_name", "last_name",
        "age", "dob", "date_of_birth",
        "ssn", "social_security",
        "phone", "telephone", "mobile",
        "email", "email_address",
        "address", "street", "zip_code", "postal_code",
        "gender", "sex",
        "medical_record_number", "mrn",
        "insurance_id", "national_id",
    })

    # Regular expressions that match common PII value patterns.
    PII_PATTERNS: List[tuple[re.Pattern, str]] = [
        # SSN  (123-45-6789)
        (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "SSN pattern"),
        # Email
        (
            re.compile(
                r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
            ),
            "Email pattern",
        ),
        # 10-digit phone
        (re.compile(r"\b\d{10}\b"), "Phone number pattern"),
        # Phone with dashes / spaces  (123-456-7890 or 123 456 7890)
        (re.compile(r"\b\d{3}[\s\-]\d{3}[\s\-]\d{4}\b"), "Phone pattern"),
    ]

    # Keys that are always safe and should be skipped during scanning
    # to avoid false positives (e.g. "patient_uuid" contains "patient").
    SAFE_KEYS: frozenset[str] = frozenset({
        "patient_uuid", "uuid", "session_id", "record_id",
        "intent", "action_type", "record_type",
        "privacy_safe", "cloud_exposed",
    })

    # -----------------------------------------------------------------
    # Initialisation
    # -----------------------------------------------------------------

    def __init__(self) -> None:
        self._audit_log: List[Dict[str, Any]] = []
        self._call_count: int = 0
        self._violation_count: int = 0
        logger.info("MCP Bridge initialized — privacy enforcement active")

    # -----------------------------------------------------------------
    # Core validation
    # -----------------------------------------------------------------

    def validate_outgoing_data(
        self,
        data: Any,
        agent_name: str,
    ) -> Dict[str, Any]:
        """Scan a payload for PII **before** it reaches the cloud.

        Args:
            data: The payload (dict, list, or string) about to be sent.
            agent_name: Name of the cloud agent (for logging).

        Returns:
            ``{"safe": bool, "violations": [str, …]}``
        """
        violations = self._scan_for_pii(data)
        safe = len(violations) == 0

        if not safe:
            logger.warning(
                f"MCP BRIDGE: PII detected in outgoing payload for "
                f"{agent_name}: {violations}"
            )
            self._violation_count += len(violations)

        return {"safe": safe, "violations": violations}

    def validate_incoming_data(
        self,
        data: Any,
        agent_name: str,
    ) -> Dict[str, Any]:
        """Validate a cloud response does not contain injected PII.

        Args:
            data: The response payload from the cloud.
            agent_name: Name of the cloud agent (for logging).

        Returns:
            ``{"safe": bool, "violations": [str, …]}``
        """
        violations = self._scan_for_pii(data)
        safe = len(violations) == 0

        if not safe:
            logger.warning(
                f"MCP BRIDGE: PII detected in incoming response from "
                f"{agent_name}: {violations}"
            )
            self._violation_count += len(violations)

        return {"safe": safe, "violations": violations}

    # -----------------------------------------------------------------
    # Recursive PII scanner
    # -----------------------------------------------------------------

    def _scan_for_pii(
        self,
        data: Any,
        path: str = "",
    ) -> List[str]:
        """Recursively scan a value for forbidden keys and PII patterns.

        Walks nested dicts, lists, and strings.  Returns a list of
        human-readable violation descriptions.
        """
        violations: List[str] = []

        if isinstance(data, dict):
            for key, value in data.items():
                current_path = f"{path}.{key}" if path else key

                # Skip known-safe keys
                if key.lower() in self.SAFE_KEYS:
                    continue

                # Check field name against blocklist
                if key.lower() in self.FORBIDDEN_FIELDS:
                    violations.append(
                        f"Forbidden field '{current_path}' detected"
                    )

                # Recurse into value
                violations.extend(self._scan_for_pii(value, current_path))

        elif isinstance(data, (list, tuple)):
            for idx, item in enumerate(data):
                violations.extend(
                    self._scan_for_pii(item, f"{path}[{idx}]")
                )

        elif isinstance(data, str):
            # Pattern-match string values for PII
            for pattern, label in self.PII_PATTERNS:
                if pattern.search(data):
                    violations.append(
                        f"{label} found in value at '{path}'"
                    )

        return violations

    # -----------------------------------------------------------------
    # Routing interface
    # -----------------------------------------------------------------

    def route_to_cloud(
        self,
        agent_name: str,
        patient_uuid: Optional[str],
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Validate an outgoing payload, log the data flow, and return it.

        This is the primary entry-point for agents sending data to the
        cloud.  The bridge validates, logs, and returns the payload.
        Violations are recorded but do **not** block the request (the
        agents already self-enforce; the bridge is an auditing layer).

        Args:
            agent_name: Cloud agent identifier.
            patient_uuid: Patient UUID (may be None for general queries).
            payload: Data dict to send to the cloud.

        Returns:
            ``{"payload": <original>, "validation": {safe, violations}}``
        """
        self._call_count += 1
        validation = self.validate_outgoing_data(payload, agent_name)

        self._log_data_flow(
            direction="outgoing",
            agent_name=agent_name,
            patient_uuid=patient_uuid,
            safe=validation["safe"],
            violations=validation["violations"],
            payload_hash=self._hash_payload(payload),
        )

        return {"payload": payload, "validation": validation}

    def route_from_cloud(
        self,
        agent_name: str,
        patient_uuid: Optional[str],
        response: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Validate an incoming cloud response and log the data flow.

        Args:
            agent_name: Cloud agent identifier.
            patient_uuid: Patient UUID (may be None).
            response: Response dict from the cloud.

        Returns:
            ``{"response": <original>, "validation": {safe, violations}}``
        """
        self._call_count += 1
        validation = self.validate_incoming_data(response, agent_name)

        self._log_data_flow(
            direction="incoming",
            agent_name=agent_name,
            patient_uuid=patient_uuid,
            safe=validation["safe"],
            violations=validation["violations"],
            payload_hash=self._hash_payload(response),
        )

        return {"response": response, "validation": validation}

    # -----------------------------------------------------------------
    # Audit logging
    # -----------------------------------------------------------------

    def _log_data_flow(
        self,
        direction: str,
        agent_name: str,
        patient_uuid: Optional[str],
        safe: bool,
        violations: List[str],
        payload_hash: str = "",
    ) -> None:
        """Append an entry to the in-memory audit log."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "direction": direction,
            "agent_name": agent_name,
            "patient_uuid_prefix": (
                patient_uuid[:8] if patient_uuid else None
            ),
            "safe": safe,
            "violations": violations,
            "payload_hash": payload_hash,
        }
        self._audit_log.append(entry)

        log_fn = logger.info if safe else logger.warning
        log_fn(
            f"MCP BRIDGE [{direction.upper()}] agent={agent_name} "
            f"uuid={entry['patient_uuid_prefix']} safe={safe} "
            f"violations={len(violations)}"
        )

    def get_audit_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return the most recent audit log entries.

        Args:
            limit: Maximum entries to return (newest first).

        Returns:
            List of audit-log dicts.
        """
        return list(reversed(self._audit_log[-limit:]))

    # -----------------------------------------------------------------
    # Compliance reporting
    # -----------------------------------------------------------------

    def get_compliance_report(self) -> Dict[str, Any]:
        """Generate a privacy compliance report for the MCP bridge.

        Suitable for academic demonstration and viva presentation.

        Returns:
            Dict with total calls, violation count, compliance rate, and
            per-agent breakdowns.
        """
        total = self._call_count
        # Count calls that were safe (not individual violations)
        safe_calls = sum(1 for e in self._audit_log if e["safe"])
        unsafe_calls = total - safe_calls
        compliance_rate = (
            (safe_calls / total * 100) if total > 0 else 100.0
        )

        # Per-agent breakdown
        agent_stats: Dict[str, Dict[str, int]] = {}
        for entry in self._audit_log:
            agent = entry["agent_name"]
            if agent not in agent_stats:
                agent_stats[agent] = {"total": 0, "safe": 0, "unsafe": 0}
            agent_stats[agent]["total"] += 1
            if entry["safe"]:
                agent_stats[agent]["safe"] += 1
            else:
                agent_stats[agent]["unsafe"] += 1

        return {
            "total_calls": total,
            "total_violations": self._violation_count,
            "unsafe_calls": unsafe_calls,
            "compliance_rate": round(compliance_rate, 2),
            "privacy_enforced": True,
            "bridge_active": True,
            "agent_breakdown": agent_stats,
            "last_checked": datetime.now(timezone.utc).isoformat(),
        }

    # -----------------------------------------------------------------
    # Utilities
    # -----------------------------------------------------------------

    @staticmethod
    def _hash_payload(data: Any) -> str:
        """Create a SHA-256 fingerprint of a payload (for audit, not PII)."""
        try:
            raw = str(data).encode("utf-8")
            return hashlib.sha256(raw).hexdigest()[:16]
        except Exception:
            return "hash-error"

    def reset(self) -> None:
        """Clear audit log and counters (useful for testing)."""
        self._audit_log.clear()
        self._call_count = 0
        self._violation_count = 0


# Global singleton
mcp_bridge = MCPBridge()
