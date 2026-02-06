"""
Regex patterns for PII detection.
Used as fallback when local LLM is unavailable.
"""
import re
from typing import List, Dict, Tuple

# ── Phone number patterns ──────────────────────────────────────────────
PHONE_PATTERNS = [
    re.compile(r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b'),          # 555-123-4567 / 555.123.4567 / 555 123 4567
    re.compile(r'\b\(\d{3}\)\s*\d{3}[-.\s]?\d{4}\b'),           # (555) 123-4567
    re.compile(r'\b\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'),  # +1-555-123-4567
]

# ── SSN / ID patterns ─────────────────────────────────────────────────
SSN_PATTERNS = [
    re.compile(r'\b\d{3}[-]?\d{2}[-]?\d{4}\b'),  # 123-45-6789
]

# ── Address patterns ──────────────────────────────────────────────────
ADDRESS_PATTERNS = [
    re.compile(
        r'\b\d{1,5}\s+[\w\s]+(?:St(?:reet)?|Ave(?:nue)?|Blvd|Boulevard|Dr(?:ive)?|Ln|Lane|Rd|Road|Ct|Court|Pl(?:ace)?|Way|Cir(?:cle)?)'
        r'(?:[.,]?\s*(?:Apt|Suite|Unit|#)\s*\w+)?',
        re.IGNORECASE,
    ),
]

# ── Age patterns ──────────────────────────────────────────────────────
AGE_PATTERNS = [
    re.compile(r'\b(\d{1,3})\s*(?:years?\s*old|y/?o|yr?s?\s*old)\b', re.IGNORECASE),
    re.compile(r'\bage[d:]?\s*(\d{1,3})\b', re.IGNORECASE),
]

# ── Known medical / doctor terms that should NOT be anonymized ────────
MEDICAL_TERMS = {
    "dr.", "dr", "doctor", "nurse", "surgeon", "specialist",
    "physician", "therapist", "pharmacist", "paramedic",
}

COMMON_SYMPTOMS = {
    "fever", "cough", "headache", "pain", "nausea", "vomiting",
    "dizziness", "fatigue", "breathing", "chest", "stomach",
    "cold", "flu", "infection", "allergy", "rash", "swelling",
    "bleeding", "fracture", "injury", "diabetes", "asthma",
    "hypertension", "pneumonia", "bronchitis", "migraine",
}

# Words that look like names but are medical terms
MEDICAL_TITLE_PREFIXES = {"dr.", "dr", "doctor", "prof.", "professor"}


def detect_phones(text: str) -> List[Dict]:
    """Detect phone numbers in text."""
    results = []
    for pattern in PHONE_PATTERNS:
        for match in pattern.finditer(text):
            results.append({
                "original": match.group(),
                "type": "phone",
                "start": match.start(),
                "end": match.end(),
            })
    return results


def detect_ssns(text: str) -> List[Dict]:
    """Detect SSN/ID numbers in text."""
    results = []
    for pattern in SSN_PATTERNS:
        for match in pattern.finditer(text):
            value = match.group().replace("-", "")
            # Avoid matching phone numbers (10 digits) or years
            if len(value) == 9:
                results.append({
                    "original": match.group(),
                    "type": "ssn",
                    "start": match.start(),
                    "end": match.end(),
                })
    return results


def detect_addresses(text: str) -> List[Dict]:
    """Detect street addresses in text."""
    results = []
    for pattern in ADDRESS_PATTERNS:
        for match in pattern.finditer(text):
            results.append({
                "original": match.group().strip(),
                "type": "address",
                "start": match.start(),
                "end": match.end(),
            })
    return results


def detect_ages(text: str) -> List[Dict]:
    """Detect explicit age mentions in text."""
    results = []
    for pattern in AGE_PATTERNS:
        for match in pattern.finditer(text):
            age_val = int(match.group(1))
            if 0 <= age_val <= 150:
                results.append({
                    "original": match.group(),
                    "age_value": age_val,
                    "type": "age",
                    "start": match.start(),
                    "end": match.end(),
                })
    return results


def is_medical_term(word: str) -> bool:
    """Check if a word is a known medical term / symptom."""
    return word.lower().strip(".,!?;:") in MEDICAL_TERMS or word.lower().strip(".,!?;:") in COMMON_SYMPTOMS


def is_doctor_reference(text: str, name_start: int) -> bool:
    """
    Check if a detected name is preceded by a doctor title prefix,
    meaning it should NOT be anonymized.
    """
    # Look at the text before the name
    before = text[:name_start].strip().lower()
    for prefix in MEDICAL_TITLE_PREFIXES:
        if before.endswith(prefix):
            return True
    return False
