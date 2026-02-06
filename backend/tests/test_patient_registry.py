"""
Tests for Prompt 1: Patient Registry & Persistence Layer.

Covers:
1. Patient creation + UUID + anonymized_name + age_bucket
2. Patient search (partial, case-insensitive)
3. Patient retrieval by UUID (found + not found)
4. Duplicate handling (same name, different UUIDs)
5. Age bucket conversion for all ranges
"""

import pytest
import os
import tempfile

# Ensure testing env
os.environ.setdefault("TESTING_MODE", "true")
os.environ.setdefault("GROQ_API_KEY", "test")
os.environ.setdefault("PINECONE_API_KEY", "test")
os.environ.setdefault("PINECONE_ENVIRONMENT", "test")

from database import identity_vault as iv_module
from database.identity_vault import (
    create_patient,
    search_patients_by_name,
    get_patient_by_uuid,
    get_all_patients,
    update_patient,
    _age_to_bucket,
    reinitialize,
    dispose,
)


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path):
    """Give every test a fresh patients.db."""
    db_path = str(tmp_path / "test_patients.db")
    reinitialize(db_path)
    yield
    dispose()


# ── 1. Test Patient Creation ──────────────────────────────────────────

class TestPatientCreation:
    def test_create_patient_valid(self):
        p = create_patient("Aziz Ahmed", age=21, gender="Male")
        assert p["patient_uuid"] is not None
        assert len(p["patient_uuid"]) == 36  # UUID format
        assert p["real_name"] == "Aziz Ahmed"
        assert p["anonymized_name"].startswith("Patient_")
        assert len(p["anonymized_name"].replace("Patient_", "")) == 3
        assert p["age"] == 21
        assert p["age_bucket"] == "early 20s"
        assert p["gender"] == "Male"
        assert p["created_at"] is not None
        assert p["updated_at"] is not None

    def test_create_patient_with_phone(self):
        p = create_patient("Sara Khan", age=30, gender="Female", phone="555-123-4567")
        assert p["phone"] == "555-123-4567"

    def test_create_patient_without_phone(self):
        p = create_patient("Ali Raza", age=45, gender="Male")
        assert p["phone"] is None

    def test_anonymized_name_is_unique(self):
        p1 = create_patient("John Doe", age=25, gender="Male")
        p2 = create_patient("Jane Doe", age=30, gender="Female")
        assert p1["anonymized_name"] != p2["anonymized_name"]


# ── 2. Test Patient Search ────────────────────────────────────────────

class TestPatientSearch:
    def test_search_by_partial_name(self):
        create_patient("Aziz", age=21, gender="Male")
        create_patient("Aziz Khan", age=25, gender="Male")
        create_patient("Sara", age=30, gender="Female")

        results = search_patients_by_name("Aziz")
        assert len(results) == 2
        names = {r["real_name"] for r in results}
        assert "Aziz" in names
        assert "Aziz Khan" in names

    def test_search_case_insensitive(self):
        create_patient("John Doe", age=40, gender="Male")
        results = search_patients_by_name("john")
        assert len(results) == 1
        assert results[0]["real_name"] == "John Doe"

    def test_search_no_match(self):
        create_patient("Alice", age=28, gender="Female")
        results = search_patients_by_name("Nonexistent")
        assert len(results) == 0

    def test_search_returns_all_fields(self):
        create_patient("Bob Smith", age=50, gender="Male", phone="111-222-3333")
        results = search_patients_by_name("Bob")
        assert len(results) == 1
        r = results[0]
        assert "patient_uuid" in r
        assert "anonymized_name" in r
        assert "age_bucket" in r


# ── 3. Test Patient Retrieval ─────────────────────────────────────────

class TestPatientRetrieval:
    def test_get_by_uuid(self):
        p = create_patient("Carol Davis", age=35, gender="Female")
        fetched = get_patient_by_uuid(p["patient_uuid"])
        assert fetched is not None
        assert fetched["real_name"] == "Carol Davis"
        assert fetched["age"] == 35
        assert fetched["gender"] == "Female"
        assert fetched["patient_uuid"] == p["patient_uuid"]

    def test_get_nonexistent_uuid(self):
        result = get_patient_by_uuid("00000000-0000-0000-0000-000000000000")
        assert result is None

    def test_get_all_patients(self):
        create_patient("P1", age=20, gender="Male")
        create_patient("P2", age=30, gender="Female")
        create_patient("P3", age=40, gender="Male")
        all_p = get_all_patients()
        assert len(all_p) == 3


# ── 4. Test Duplicate Handling ────────────────────────────────────────

class TestDuplicateHandling:
    def test_same_name_different_uuids(self):
        p1 = create_patient("Aziz Ahmed", age=21, gender="Male")
        p2 = create_patient("Aziz Ahmed", age=35, gender="Male")
        assert p1["patient_uuid"] != p2["patient_uuid"]
        assert p1["anonymized_name"] != p2["anonymized_name"]

    def test_search_returns_both_duplicates(self):
        create_patient("Aziz Ahmed", age=21, gender="Male")
        create_patient("Aziz Ahmed", age=35, gender="Male")
        results = search_patients_by_name("Aziz Ahmed")
        assert len(results) == 2


# ── 5. Test Age Bucket Conversion ─────────────────────────────────────

class TestAgeBucketConversion:
    @pytest.mark.parametrize("age,expected", [
        (5, "child"),
        (12, "child"),
        (13, "teenager"),
        (17, "teenager"),
        (18, "early 20s"),
        (25, "early 20s"),
        (26, "late 20s to early 30s"),
        (35, "late 20s to early 30s"),
        (36, "middle-aged"),
        (50, "middle-aged"),
        (51, "senior"),
        (65, "senior"),
        (66, "elderly"),
        (90, "elderly"),
    ])
    def test_age_bucket(self, age, expected):
        assert _age_to_bucket(age) == expected

    def test_age_bucket_in_created_patient(self):
        p = create_patient("Child Patient", age=10, gender="Male")
        assert p["age_bucket"] == "child"

        p2 = create_patient("Senior Patient", age=60, gender="Female")
        assert p2["age_bucket"] == "senior"


# ── 6. Test Update Patient ────────────────────────────────────────────

class TestUpdatePatient:
    def test_update_age_recalculates_bucket(self):
        p = create_patient("Test User", age=21, gender="Male")
        assert p["age_bucket"] == "early 20s"

        updated = update_patient(p["patient_uuid"], age=55)
        assert updated["age"] == 55
        assert updated["age_bucket"] == "senior"

    def test_update_phone(self):
        p = create_patient("Test User", age=30, gender="Female")
        updated = update_patient(p["patient_uuid"], phone="999-888-7777")
        assert updated["phone"] == "999-888-7777"

    def test_update_nonexistent_raises(self):
        with pytest.raises(ValueError):
            update_patient("nonexistent-uuid", age=30)
