"""
Input Validators for MedShield.

Provides validation utilities for user input, patient data,
and API request parameters.
"""

import re
from typing import Optional, Dict, Any, List


def validate_patient_name(name: str) -> Dict[str, Any]:
    """
    Validate a patient name.

    Args:
        name: Patient name string

    Returns:
        Dict with 'valid' (bool) and 'error' (str) keys
    """
    if not name or not name.strip():
        return {"valid": False, "error": "Patient name cannot be empty."}

    name = name.strip()
    if len(name) < 2:
        return {"valid": False, "error": "Patient name must be at least 2 characters."}

    if len(name) > 255:
        return {"valid": False, "error": "Patient name must not exceed 255 characters."}

    # Allow letters, spaces, hyphens, apostrophes
    if not re.match(r"^[A-Za-z\s\-']+$", name):
        return {"valid": False, "error": "Patient name contains invalid characters."}

    return {"valid": True, "error": ""}


def validate_age(age: int) -> Dict[str, Any]:
    """
    Validate a patient age.

    Args:
        age: Patient age as integer

    Returns:
        Dict with 'valid' (bool) and 'error' (str) keys
    """
    if not isinstance(age, int):
        return {"valid": False, "error": "Age must be an integer."}

    if age < 0:
        return {"valid": False, "error": "Age cannot be negative."}

    if age > 150:
        return {"valid": False, "error": "Age exceeds maximum allowed value (150)."}

    return {"valid": True, "error": ""}


def validate_gender(gender: str) -> Dict[str, Any]:
    """
    Validate a patient gender.

    Args:
        gender: Patient gender string

    Returns:
        Dict with 'valid' (bool) and 'error' (str) keys
    """
    valid_genders = {"male", "female", "other", "prefer not to say"}

    if not gender or not gender.strip():
        return {"valid": False, "error": "Gender cannot be empty."}

    if gender.strip().lower() not in valid_genders:
        return {
            "valid": False,
            "error": f"Invalid gender. Must be one of: {', '.join(sorted(valid_genders))}"
        }

    return {"valid": True, "error": ""}


def validate_message(message: str) -> Dict[str, Any]:
    """
    Validate a chat message.

    Args:
        message: User message string

    Returns:
        Dict with 'valid' (bool) and 'error' (str) keys
    """
    if not message or not message.strip():
        return {"valid": False, "error": "Message cannot be empty."}

    if len(message) > 5000:
        return {"valid": False, "error": "Message exceeds maximum length (5000 characters)."}

    return {"valid": True, "error": ""}


def validate_session_id(session_id: Optional[str]) -> Dict[str, Any]:
    """
    Validate a session ID format.

    Args:
        session_id: Session UUID string (optional)

    Returns:
        Dict with 'valid' (bool) and 'error' (str) keys
    """
    if session_id is None:
        return {"valid": True, "error": ""}  # Optional field

    uuid_pattern = re.compile(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
        re.IGNORECASE
    )

    if not uuid_pattern.match(session_id):
        return {"valid": False, "error": "Invalid session ID format. Must be a valid UUID."}

    return {"valid": True, "error": ""}


def sanitize_input(text: str) -> str:
    """
    Sanitize user input by removing potentially dangerous characters.

    Args:
        text: Raw user input

    Returns:
        Sanitized text string
    """
    if not text:
        return ""

    # Remove null bytes
    text = text.replace('\x00', '')

    # Strip leading/trailing whitespace
    text = text.strip()

    return text
