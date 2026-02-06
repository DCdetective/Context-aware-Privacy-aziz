"""
Patient Registry – Persistent patient storage with anonymization.

Provides:
    create_patient, search_patients_by_name, get_patient_by_uuid,
    get_all_patients, update_patient

Also keeps the legacy IdentityVault class so existing code (main.py,
gatekeeper, coordinator, tests) continues to work without changes.
"""

from sqlalchemy import create_engine, or_
from sqlalchemy.orm import sessionmaker, Session, scoped_session
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
import logging
import uuid as uuid_lib
import string
import random
import threading
import os

from database.models import Base, Patient, PatientIdentity, MedicalRecord, AuditLog

logger = logging.getLogger(__name__)

# ── Anonymization helpers ──────────────────────────────────────────────

_anon_lock = threading.Lock()
_used_codes: set = set()


def _age_to_bucket(age: int) -> str:
    """Convert exact age to privacy-safe age bucket."""
    if age <= 12:
        return "child"
    elif age <= 17:
        return "teenager"
    elif age <= 25:
        return "early 20s"
    elif age <= 35:
        return "late 20s to early 30s"
    elif age <= 50:
        return "middle-aged"
    elif age <= 65:
        return "senior"
    else:
        return "elderly"


def _generate_anon_code(existing_codes: set) -> str:
    """Generate a unique 3-character alphanumeric code."""
    chars = string.ascii_uppercase + string.digits
    with _anon_lock:
        for _ in range(10000):
            code = "".join(random.choices(chars, k=3))
            if code not in existing_codes:
                existing_codes.add(code)
                return code
    raise RuntimeError("Could not generate unique anonymized code")


# ── Patient Registry (Prompt 1 API) ───────────────────────────────────

_DB_DIR = os.path.join(os.path.dirname(__file__))
_PATIENTS_DB_PATH = os.path.join(_DB_DIR, "patients.db")


def _get_engine(db_path: Optional[str] = None):
    path = db_path or _PATIENTS_DB_PATH
    engine = create_engine(
        f"sqlite:///{path}",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    return engine


# Module-level engine / session factory (lazy-init for testability)
_engine = None
_SessionFactory = None
_init_lock = threading.Lock()


def _ensure_initialized(db_path: Optional[str] = None):
    global _engine, _SessionFactory
    if _SessionFactory is not None and db_path is None:
        return
    with _init_lock:
        if _SessionFactory is not None and db_path is None:
            return
        _engine = _get_engine(db_path)
        _SessionFactory = scoped_session(sessionmaker(bind=_engine))
        Base.metadata.create_all(_engine)
        # Preload existing anonymized codes so we never duplicate
        session = _SessionFactory()
        try:
            existing = session.query(Patient.anonymized_name).all()
            for (name,) in existing:
                code = name.replace("Patient_", "")
                _used_codes.add(code)
        except Exception:
            pass
        finally:
            session.close()


def _get_session(db_path: Optional[str] = None) -> Session:
    _ensure_initialized(db_path)
    return _SessionFactory()


def reinitialize(db_path: Optional[str] = None):
    """Re-initialize the module-level DB (useful for tests)."""
    global _engine, _SessionFactory
    with _init_lock:
        if _SessionFactory is not None:
            _SessionFactory.remove()
        if _engine is not None:
            _engine.dispose()
        _engine = _get_engine(db_path)
        _SessionFactory = scoped_session(sessionmaker(bind=_engine))
        Base.metadata.create_all(_engine)
        _used_codes.clear()
        session = _SessionFactory()
        try:
            existing = session.query(Patient.anonymized_name).all()
            for (name,) in existing:
                code = name.replace("Patient_", "")
                _used_codes.add(code)
        except Exception:
            pass
        finally:
            session.close()


def dispose():
    """Dispose engine (for test cleanup)."""
    global _engine, _SessionFactory
    with _init_lock:
        if _SessionFactory is not None:
            _SessionFactory.remove()
            _SessionFactory = None
        if _engine is not None:
            _engine.dispose()
            _engine = None
        _used_codes.clear()


# ── Public API (Prompt 1) ─────────────────────────────────────────────

def create_patient(
    real_name: str,
    age: int,
    gender: str,
    phone: Optional[str] = None,
) -> dict:
    """
    Create a new patient with automatic anonymization.

    Returns dict with all patient fields.
    """
    _ensure_initialized()
    session = _get_session()
    try:
        anon_code = _generate_anon_code(_used_codes)
        anonymized_name = f"Patient_{anon_code}"
        age_bucket = _age_to_bucket(age)

        patient = Patient(
            patient_uuid=str(uuid_lib.uuid4()),
            real_name=real_name,
            anonymized_name=anonymized_name,
            age=age,
            age_bucket=age_bucket,
            gender=gender,
            phone=phone,
        )
        session.add(patient)
        session.commit()
        session.refresh(patient)
        result = patient.to_dict()
        logger.info(f"Created patient {patient.patient_uuid} ({anonymized_name})")
        return result
    except Exception as e:
        session.rollback()
        logger.error(f"Error creating patient: {e}")
        raise
    finally:
        session.close()


def search_patients_by_name(name: str) -> List[dict]:
    """
    Search patients by partial, case-insensitive name match.
    """
    _ensure_initialized()
    session = _get_session()
    try:
        patients = (
            session.query(Patient)
            .filter(Patient.real_name.ilike(f"%{name}%"))
            .all()
        )
        return [p.to_dict() for p in patients]
    except Exception as e:
        logger.error(f"Error searching patients: {e}")
        raise
    finally:
        session.close()


def get_patient_by_uuid(patient_uuid: str) -> Optional[dict]:
    """
    Retrieve a patient by UUID.  Returns None if not found.
    """
    _ensure_initialized()
    session = _get_session()
    try:
        patient = session.query(Patient).filter(
            Patient.patient_uuid == patient_uuid
        ).first()
        return patient.to_dict() if patient else None
    except Exception as e:
        logger.error(f"Error getting patient by UUID: {e}")
        raise
    finally:
        session.close()


def get_all_patients() -> List[dict]:
    """Return all patients."""
    _ensure_initialized()
    session = _get_session()
    try:
        patients = session.query(Patient).all()
        return [p.to_dict() for p in patients]
    except Exception as e:
        logger.error(f"Error getting all patients: {e}")
        raise
    finally:
        session.close()


def update_patient(patient_uuid: str, **kwargs) -> dict:
    """
    Update patient fields.  Recalculates age_bucket if age changes.
    Returns updated patient dict.  Raises ValueError if not found.
    """
    _ensure_initialized()
    session = _get_session()
    try:
        patient = session.query(Patient).filter(
            Patient.patient_uuid == patient_uuid
        ).first()
        if patient is None:
            raise ValueError(f"Patient not found: {patient_uuid}")

        for key, value in kwargs.items():
            if hasattr(patient, key):
                setattr(patient, key, value)

        # Recalculate age bucket if age changed
        if "age" in kwargs:
            patient.age_bucket = _age_to_bucket(kwargs["age"])

        session.commit()
        session.refresh(patient)
        return patient.to_dict()
    except ValueError:
        raise
    except Exception as e:
        session.rollback()
        logger.error(f"Error updating patient: {e}")
        raise
    finally:
        session.close()


# ── Legacy IdentityVault class (kept for backward compatibility) ──────

class IdentityVault:
    """
    Identity Vault – Local PII storage and management.

    CRITICAL PRIVACY COMPONENT:
    - All PII stored here NEVER leaves the local environment
    - Provides UUID ↔ PII mapping
    - Maintains audit trail for compliance
    - Enables re-identification for final output
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.path.join(_DB_DIR, "identity_vault.db")
        self.engine = create_engine(
            f"sqlite:///{self.db_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )
        self.SessionLocal = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)
        logger.info(f"Identity Vault initialized at {self.db_path}")

    def _get_session(self) -> Session:
        return self.SessionLocal()

    def _log_audit(
        self,
        session: Session,
        patient_uuid: str,
        operation: str,
        component: str,
        pii_accessed: bool = False,
        cloud_exposed: bool = False,
        details: Optional[str] = None,
    ):
        log = AuditLog(
            log_id=str(uuid_lib.uuid4()),
            patient_uuid=patient_uuid,
            operation=operation,
            component=component,
            pii_accessed=pii_accessed,
            cloud_exposed=cloud_exposed,
            timestamp=datetime.utcnow(),
            details=details,
        )
        session.add(log)

    def pseudonymize_patient(
        self,
        patient_name: str,
        age: Optional[int] = None,
        gender: Optional[str] = None,
        component: str = "system",
    ) -> Tuple[str, bool]:
        session = self._get_session()
        try:
            existing = session.query(PatientIdentity).filter(
                PatientIdentity.patient_name == patient_name
            ).first()
            if existing:
                existing.last_accessed = datetime.utcnow()
                existing.access_count += 1
                if age is not None and existing.age != age:
                    existing.age = age
                if gender is not None and existing.gender != gender:
                    existing.gender = gender
                session.commit()
                self._log_audit(session, existing.patient_uuid, "pseudonymize_existing", component, True, False,
                                f"Retrieved existing UUID for {patient_name}")
                session.commit()
                return existing.patient_uuid, False

            new_uuid = str(uuid_lib.uuid4())
            new_patient = PatientIdentity(
                patient_uuid=new_uuid,
                patient_name=patient_name,
                age=age,
                gender=gender,
                created_at=datetime.utcnow(),
                last_accessed=datetime.utcnow(),
                access_count=1,
            )
            session.add(new_patient)
            session.commit()
            self._log_audit(session, new_uuid, "pseudonymize_new", component, True, False,
                            f"Created new UUID for {patient_name}")
            session.commit()
            return new_uuid, True
        except Exception as e:
            session.rollback()
            logger.error(f"Error in pseudonymize_patient: {e}")
            raise
        finally:
            session.close()

    def reidentify_patient(self, patient_uuid: str, component: str = "system") -> Optional[Dict[str, Any]]:
        session = self._get_session()
        try:
            patient = session.query(PatientIdentity).filter(
                PatientIdentity.patient_uuid == patient_uuid
            ).first()
            if not patient:
                return None
            patient.last_accessed = datetime.utcnow()
            patient.access_count += 1
            session.commit()
            self._log_audit(session, patient_uuid, "reidentify", component, True, False,
                            f"Re-identified patient for {component}")
            session.commit()
            return {
                "patient_uuid": patient.patient_uuid,
                "patient_name": patient.patient_name,
                "age": patient.age,
                "gender": patient.gender,
                "created_at": patient.created_at.isoformat() if patient.created_at else None,
                "last_accessed": patient.last_accessed.isoformat() if patient.last_accessed else None,
                "access_count": patient.access_count,
            }
        except Exception as e:
            session.rollback()
            logger.error(f"Error in reidentify_patient: {e}")
            raise
        finally:
            session.close()

    def store_medical_record(self, patient_uuid: str, record_type: str, symptoms: Optional[str] = None,
                             diagnosis: Optional[str] = None, treatment_plan: Optional[str] = None,
                             notes: Optional[str] = None, component: str = "system") -> str:
        session = self._get_session()
        try:
            record_id = str(uuid_lib.uuid4())
            record = MedicalRecord(
                record_id=record_id, patient_uuid=patient_uuid, record_type=record_type,
                symptoms=symptoms, diagnosis=diagnosis, treatment_plan=treatment_plan,
                notes=notes, created_at=datetime.utcnow(),
            )
            session.add(record)
            session.commit()
            self._log_audit(session, patient_uuid, "store_record", component, True, False,
                            f"Stored {record_type} record")
            session.commit()
            return record_id
        except Exception as e:
            session.rollback()
            logger.error(f"Error storing medical record: {e}")
            raise
        finally:
            session.close()

    def get_patient_records(self, patient_uuid: str, record_type: Optional[str] = None,
                            component: str = "system") -> List[Dict[str, Any]]:
        session = self._get_session()
        try:
            query = session.query(MedicalRecord).filter(MedicalRecord.patient_uuid == patient_uuid)
            if record_type:
                query = query.filter(MedicalRecord.record_type == record_type)
            records = query.order_by(MedicalRecord.created_at.desc()).all()
            if records:
                self._log_audit(session, patient_uuid, "retrieve_records", component, True, False,
                                f"Retrieved {len(records)} records")
                session.commit()
            return [
                {
                    "record_id": r.record_id, "patient_uuid": r.patient_uuid,
                    "record_type": r.record_type, "symptoms": r.symptoms,
                    "diagnosis": r.diagnosis, "treatment_plan": r.treatment_plan,
                    "notes": r.notes,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in records
            ]
        except Exception as e:
            logger.error(f"Error retrieving records: {e}")
            raise
        finally:
            session.close()

    def get_audit_trail(self, patient_uuid: Optional[str] = None, operation: Optional[str] = None,
                        limit: int = 100) -> List[Dict[str, Any]]:
        return self.get_audit_logs(patient_uuid=patient_uuid, operation=operation, limit=limit)

    def get_audit_logs(self, patient_uuid: Optional[str] = None, operation: Optional[str] = None,
                       limit: int = 100) -> List[Dict[str, Any]]:
        session = self._get_session()
        try:
            query = session.query(AuditLog)
            if patient_uuid:
                query = query.filter(AuditLog.patient_uuid == patient_uuid)
            if operation:
                query = query.filter(AuditLog.operation == operation)
            logs = query.order_by(AuditLog.timestamp.desc()).limit(limit).all()
            return [
                {
                    "log_id": l.log_id, "patient_uuid": l.patient_uuid,
                    "operation": l.operation, "component": l.component,
                    "pii_accessed": l.pii_accessed, "cloud_exposed": l.cloud_exposed,
                    "timestamp": l.timestamp.isoformat() if l.timestamp else None,
                    "details": l.details,
                }
                for l in logs
            ]
        except Exception as e:
            logger.error(f"Error retrieving audit logs: {e}")
            raise
        finally:
            session.close()

    def find_patients_by_name(self, patient_name: str, component: str = "system") -> List[Dict[str, Any]]:
        session = self._get_session()
        try:
            patients = session.query(PatientIdentity).filter(
                PatientIdentity.patient_name.ilike(f"%{patient_name}%")
            ).all()
            if patients:
                self._log_audit(session, "search", "search_by_name", component, True, False,
                                f"Found {len(patients)} patients matching '{patient_name}'")
                session.commit()
            return [
                {
                    "patient_uuid": p.patient_uuid, "patient_name": p.patient_name,
                    "age": p.age, "gender": p.gender,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                    "last_accessed": p.last_accessed.isoformat() if p.last_accessed else None,
                    "access_count": p.access_count,
                }
                for p in patients
            ]
        except Exception as e:
            logger.error(f"Error searching patients by name: {e}")
            raise
        finally:
            session.close()

    def resolve_patient_identity(self, patient_name: str, age: Optional[int] = None,
                                 gender: Optional[str] = None, component: str = "system") -> Dict[str, Any]:
        session = self._get_session()
        try:
            matching = session.query(PatientIdentity).filter(
                PatientIdentity.patient_name == patient_name
            ).all()
            if len(matching) == 0:
                return {
                    "status": "needs_confirmation",
                    "message": f"No patient found with name '{patient_name}'. Create new patient?",
                    "patient_name": patient_name, "age": age, "gender": gender,
                    "action_required": "confirm_new_patient",
                }
            elif len(matching) == 1:
                p = matching[0]
                p.last_accessed = datetime.utcnow()
                p.access_count += 1
                if age is not None and p.age != age:
                    p.age = age
                if gender is not None and p.gender != gender:
                    p.gender = gender
                session.commit()
                self._log_audit(session, p.patient_uuid, "resolve_identity_unique", component, True, False,
                                f"Auto-resolved to UUID: {p.patient_uuid}")
                session.commit()
                return {
                    "status": "resolved", "patient_uuid": p.patient_uuid,
                    "patient_name": p.patient_name, "age": p.age, "gender": p.gender,
                    "message": f"Resolved to existing patient {p.patient_uuid}",
                }
            else:
                candidates = [
                    {
                        "patient_uuid": p.patient_uuid, "patient_name": p.patient_name,
                        "age": p.age, "gender": p.gender,
                        "last_accessed": p.last_accessed.isoformat() if p.last_accessed else None,
                        "access_count": p.access_count,
                    }
                    for p in matching
                ]
                self._log_audit(session, "ambiguous", "resolve_identity_ambiguous", component, True, False,
                                f"Found {len(matching)} patients named '{patient_name}'")
                session.commit()
                return {
                    "status": "needs_disambiguation",
                    "message": f"Found {len(matching)} patients named '{patient_name}'. Please select:",
                    "candidates": candidates, "action_required": "select_patient_uuid",
                }
        except Exception as e:
            session.rollback()
            logger.error(f"Error resolving patient identity: {e}")
            raise
        finally:
            session.close()

    def confirm_new_patient(self, patient_name: str, age: Optional[int] = None,
                            gender: Optional[str] = None, component: str = "system") -> str:
        patient_uuid, _ = self.pseudonymize_patient(patient_name=patient_name, age=age, gender=gender,
                                                     component=component)
        return patient_uuid

    def verify_privacy_compliance(self) -> Dict[str, Any]:
        session = self._get_session()
        try:
            cloud_exposed = session.query(AuditLog).filter(AuditLog.cloud_exposed == True).count()
            total_ops = session.query(AuditLog).count()
            total_patients = session.query(PatientIdentity).count()
            return {
                "total_patients": total_patients, "total_operations": total_ops,
                "cloud_exposed_count": cloud_exposed, "privacy_compliant": cloud_exposed == 0,
                "timestamp": datetime.utcnow().isoformat(),
            }
        finally:
            session.close()


# Global instance (used by main.py and other modules)
identity_vault = IdentityVault()
