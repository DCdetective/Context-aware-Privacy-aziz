# Prompt 2: Local Identity Vault & Database Models

## 📋 PROJECT CONTEXT

**Project Name:** MedShield - A Privacy-Preserving Multi-Agent Medical Assistant

**Core Privacy Principle:** 
NO Personally Identifiable Information (PII) or sensitive medical data may ever leave the trusted local environment. The Local Identity Vault is the ONLY component that stores reversible mappings between real patient identities and pseudonymized UUIDs.

---

## 🎯 THIS PROMPT'S OBJECTIVE

Implement the SQLite-based Local Identity Vault that securely stores patient identity mappings and enables reversible pseudonymization. This is a CRITICAL security component - it must NEVER be exposed to cloud agents.

---

## 🔒 IDENTITY VAULT RESPONSIBILITIES

1. **Store PII Securely:** Patient names, age, gender stored locally only
2. **Generate UUIDs:** Create unique pseudonymized identifiers
3. **Bidirectional Mapping:** Support both pseudonymization and re-identification
4. **Audit Trail:** Log all identity operations for academic demonstration
5. **Isolation:** Ensure complete separation from cloud-facing components

---

## 📝 DETAILED IMPLEMENTATION INSTRUCTIONS

### Step 1: Create Database Models

Create `backend/database/models.py`:

```python
from sqlalchemy import Column, String, Integer, DateTime, Text, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
import uuid

Base = declarative_base()


class PatientIdentity(Base):
    """
    Local-only storage for patient identity information.
    MUST NEVER be exposed to cloud agents.
    """
    __tablename__ = "patient_identities"
    
    # UUID-based identifier (exposed to cloud)
    patient_uuid = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # PII - stored locally only
    patient_name = Column(String(255), nullable=False, index=True)
    age = Column(Integer, nullable=False)
    gender = Column(String(50), nullable=False)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Audit trail
    last_accessed = Column(DateTime(timezone=True))
    access_count = Column(Integer, default=0)
    
    def __repr__(self):
        return f"<PatientIdentity(uuid={self.patient_uuid}, name=REDACTED)>"


class MedicalRecord(Base):
    """
    Local storage for medical records linked to patient UUID.
    Contains PII that must stay local.
    """
    __tablename__ = "medical_records"
    
    record_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    patient_uuid = Column(String(36), nullable=False, index=True)
    
    # Medical information (PII)
    symptoms = Column(Text, nullable=True)
    diagnosis = Column(Text, nullable=True)
    treatment_plan = Column(Text, nullable=True)
    
    # Record metadata
    record_type = Column(String(50), nullable=False)  # 'appointment', 'followup', 'summary'
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self):
        return f"<MedicalRecord(id={self.record_id}, patient={self.patient_uuid}, type={self.record_type})>"


class AuditLog(Base):
    """
    Audit trail for all identity vault operations.
    Critical for academic demonstration and security verification.
    """
    __tablename__ = "audit_logs"
    
    log_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    patient_uuid = Column(String(36), nullable=False, index=True)
    
    # Operation details
    operation = Column(String(100), nullable=False)  # 'pseudonymize', 'reidentify', 'create', 'update'
    component = Column(String(100), nullable=False)  # 'gatekeeper', 'api_route', etc.
    
    # Privacy metadata
    pii_accessed = Column(Boolean, default=False)
    cloud_exposed = Column(Boolean, default=False)  # Should ALWAYS be False
    
    # Timestamps
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    
    # Additional context
    details = Column(Text, nullable=True)
    
    def __repr__(self):
        return f"<AuditLog(operation={self.operation}, component={self.component}, time={self.timestamp})>"
```

### Step 2: Create Identity Vault Manager

Create `backend/database/identity_vault.py`:

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.sql import func
from typing import Optional, Dict, Tuple
from datetime import datetime
import uuid
import logging

from .models import Base, PatientIdentity, MedicalRecord, AuditLog
from ..utils.config import settings

logger = logging.getLogger(__name__)


class IdentityVault:
    """
    Secure local storage for patient identities.
    
    CRITICAL SECURITY COMPONENT:
    - NEVER expose this component to cloud agents
    - NEVER send database contents over network
    - ALWAYS log operations for audit trail
    """
    
    def __init__(self, db_path: str = None):
        """Initialize the identity vault."""
        self.db_path = db_path or settings.sqlite_db_path
        self.engine = create_engine(
            f"sqlite:///{self.db_path}",
            echo=False,
            connect_args={"check_same_thread": False}
        )
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)
        
        # Create all tables
        Base.metadata.create_all(bind=self.engine)
        logger.info(f"Identity Vault initialized at {self.db_path}")
    
    def _get_session(self) -> Session:
        """Get a database session."""
        return self.SessionLocal()
    
    def _log_operation(
        self,
        session: Session,
        patient_uuid: str,
        operation: str,
        component: str,
        pii_accessed: bool = False,
        cloud_exposed: bool = False,
        details: Optional[str] = None
    ):
        """
        Log all vault operations for audit trail.
        
        Args:
            session: Database session
            patient_uuid: Patient UUID
            operation: Type of operation
            component: Component performing operation
            pii_accessed: Whether PII was accessed
            cloud_exposed: Whether data was exposed to cloud (should be False)
            details: Additional context
        """
        audit_log = AuditLog(
            patient_uuid=patient_uuid,
            operation=operation,
            component=component,
            pii_accessed=pii_accessed,
            cloud_exposed=cloud_exposed,
            details=details
        )
        session.add(audit_log)
        logger.info(
            f"AUDIT: {operation} by {component} for patient {patient_uuid[:8]}... "
            f"(PII:{pii_accessed}, Cloud:{cloud_exposed})"
        )
    
    def pseudonymize_patient(
        self,
        patient_name: str,
        age: int,
        gender: str,
        component: str = "unknown"
    ) -> Tuple[str, bool]:
        """
        Create or retrieve UUID for a patient (pseudonymization).
        
        Args:
            patient_name: Real patient name
            age: Patient age
            gender: Patient gender
            component: Component requesting pseudonymization
            
        Returns:
            Tuple of (patient_uuid, is_new_patient)
        """
        session = self._get_session()
        try:
            # Check if patient already exists
            existing = session.query(PatientIdentity).filter_by(
                patient_name=patient_name,
                age=age,
                gender=gender
            ).first()
            
            if existing:
                # Update access metadata
                existing.last_accessed = datetime.utcnow()
                existing.access_count += 1
                session.commit()
                
                self._log_operation(
                    session=session,
                    patient_uuid=existing.patient_uuid,
                    operation="pseudonymize_existing",
                    component=component,
                    pii_accessed=True,
                    cloud_exposed=False,
                    details=f"Retrieved existing UUID for {patient_name}"
                )
                
                logger.info(f"Retrieved existing UUID for patient: {existing.patient_uuid}")
                return existing.patient_uuid, False
            
            # Create new patient identity
            new_patient = PatientIdentity(
                patient_uuid=str(uuid.uuid4()),
                patient_name=patient_name,
                age=age,
                gender=gender,
                last_accessed=datetime.utcnow(),
                access_count=1
            )
            session.add(new_patient)
            session.commit()
            
            self._log_operation(
                session=session,
                patient_uuid=new_patient.patient_uuid,
                operation="pseudonymize_new",
                component=component,
                pii_accessed=True,
                cloud_exposed=False,
                details=f"Created new UUID for {patient_name}"
            )
            
            logger.info(f"Created new UUID for patient: {new_patient.patient_uuid}")
            return new_patient.patient_uuid, True
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error in pseudonymize_patient: {str(e)}")
            raise
        finally:
            session.close()
    
    def reidentify_patient(
        self,
        patient_uuid: str,
        component: str = "unknown"
    ) -> Optional[Dict[str, any]]:
        """
        Retrieve real patient identity from UUID (re-identification).
        
        CRITICAL: This should ONLY be called in the trusted local environment
        for final output generation. NEVER expose results to cloud agents.
        
        Args:
            patient_uuid: Pseudonymized UUID
            component: Component requesting re-identification
            
        Returns:
            Dictionary with patient details or None if not found
        """
        session = self._get_session()
        try:
            patient = session.query(PatientIdentity).filter_by(
                patient_uuid=patient_uuid
            ).first()
            
            if not patient:
                logger.warning(f"Patient UUID not found: {patient_uuid}")
                return None
            
            # Update access metadata
            patient.last_accessed = datetime.utcnow()
            patient.access_count += 1
            session.commit()
            
            self._log_operation(
                session=session,
                patient_uuid=patient_uuid,
                operation="reidentify",
                component=component,
                pii_accessed=True,
                cloud_exposed=False,
                details=f"Retrieved identity for UUID {patient_uuid}"
            )
            
            result = {
                "patient_uuid": patient.patient_uuid,
                "patient_name": patient.patient_name,
                "age": patient.age,
                "gender": patient.gender,
                "created_at": patient.created_at,
                "last_accessed": patient.last_accessed,
                "access_count": patient.access_count
            }
            
            logger.info(f"Re-identified patient: {patient_uuid}")
            return result
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error in reidentify_patient: {str(e)}")
            raise
        finally:
            session.close()
    
    def store_medical_record(
        self,
        patient_uuid: str,
        record_type: str,
        symptoms: Optional[str] = None,
        diagnosis: Optional[str] = None,
        treatment_plan: Optional[str] = None,
        component: str = "unknown"
    ) -> str:
        """
        Store a medical record for a patient.
        
        Args:
            patient_uuid: Patient UUID
            record_type: Type of record ('appointment', 'followup', 'summary')
            symptoms: Patient symptoms
            diagnosis: Medical diagnosis
            treatment_plan: Treatment plan
            component: Component storing the record
            
        Returns:
            record_id: ID of created record
        """
        session = self._get_session()
        try:
            record = MedicalRecord(
                patient_uuid=patient_uuid,
                record_type=record_type,
                symptoms=symptoms,
                diagnosis=diagnosis,
                treatment_plan=treatment_plan
            )
            session.add(record)
            session.commit()
            
            self._log_operation(
                session=session,
                patient_uuid=patient_uuid,
                operation="store_record",
                component=component,
                pii_accessed=True,
                cloud_exposed=False,
                details=f"Stored {record_type} record"
            )
            
            logger.info(f"Stored medical record: {record.record_id} for patient {patient_uuid}")
            return record.record_id
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error storing medical record: {str(e)}")
            raise
        finally:
            session.close()
    
    def get_patient_records(
        self,
        patient_uuid: str,
        record_type: Optional[str] = None,
        component: str = "unknown"
    ) -> list:
        """
        Retrieve medical records for a patient.
        
        Args:
            patient_uuid: Patient UUID
            record_type: Optional filter by record type
            component: Component retrieving records
            
        Returns:
            List of medical records
        """
        session = self._get_session()
        try:
            query = session.query(MedicalRecord).filter_by(patient_uuid=patient_uuid)
            
            if record_type:
                query = query.filter_by(record_type=record_type)
            
            records = query.order_by(MedicalRecord.created_at.desc()).all()
            
            self._log_operation(
                session=session,
                patient_uuid=patient_uuid,
                operation="retrieve_records",
                component=component,
                pii_accessed=True,
                cloud_exposed=False,
                details=f"Retrieved {len(records)} records"
            )
            
            result = []
            for record in records:
                result.append({
                    "record_id": record.record_id,
                    "patient_uuid": record.patient_uuid,
                    "record_type": record.record_type,
                    "symptoms": record.symptoms,
                    "diagnosis": record.diagnosis,
                    "treatment_plan": record.treatment_plan,
                    "created_at": record.created_at
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Error retrieving records: {str(e)}")
            raise
        finally:
            session.close()
    
    def get_audit_trail(
        self,
        patient_uuid: Optional[str] = None,
        limit: int = 100
    ) -> list:
        """
        Retrieve audit trail for demonstration purposes.
        
        Args:
            patient_uuid: Optional filter by patient
            limit: Maximum number of logs to retrieve
            
        Returns:
            List of audit log entries
        """
        session = self._get_session()
        try:
            query = session.query(AuditLog)
            
            if patient_uuid:
                query = query.filter_by(patient_uuid=patient_uuid)
            
            logs = query.order_by(AuditLog.timestamp.desc()).limit(limit).all()
            
            result = []
            for log in logs:
                result.append({
                    "log_id": log.log_id,
                    "patient_uuid": log.patient_uuid,
                    "operation": log.operation,
                    "component": log.component,
                    "pii_accessed": log.pii_accessed,
                    "cloud_exposed": log.cloud_exposed,
                    "timestamp": log.timestamp,
                    "details": log.details
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Error retrieving audit trail: {str(e)}")
            raise
        finally:
            session.close()


# Global instance
identity_vault = IdentityVault()
```

### Step 3: Update Main Application

Update `backend/main.py` to initialize the Identity Vault:

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pathlib import Path
import logging

from utils.config import settings
from database.identity_vault import identity_vault

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="MedShield - Privacy-Preserving Medical Assistant",
    description="A multi-agent system ensuring PII never leaves the local environment",
    version="1.0.0"
)

@app.on_event("startup")
async def startup_event():
    """Initialize system components on startup."""
    logger.info("=" * 60)
    logger.info("🏥 MedShield - Privacy-Preserving Medical Assistant")
    logger.info("=" * 60)
    logger.info("Initializing Local Identity Vault...")
    logger.info(f"Database path: {settings.sqlite_db_path}")
    logger.info("Identity Vault initialized successfully")
    logger.info("=" * 60)

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint for system status."""
    return {
        "status": "healthy",
        "service": "MedShield Backend",
        "version": "1.0.0",
        "components": {
            "identity_vault": "operational"
        }
    }

# Root endpoint
@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the home page."""
    logger.info("Serving home page")
    return HTMLResponse(
        content="<h1>MedShield - Identity Vault Initialized</h1>",
        status_code=200
    )


if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting MedShield Backend on {settings.backend_host}:{settings.backend_port}")
    uvicorn.run(
        "main:app",
        host=settings.backend_host,
        port=settings.backend_port,
        reload=True
    )
```

### Step 4: Create Comprehensive Tests

Create `backend/tests/test_identity_vault.py`:

```python
import pytest
from database.identity_vault import IdentityVault
from database.models import PatientIdentity, MedicalRecord, AuditLog
import os


@pytest.fixture
def test_vault(tmp_path):
    """Create a temporary identity vault for testing."""
    db_path = tmp_path / "test_vault.db"
    vault = IdentityVault(db_path=str(db_path))
    yield vault
    # Cleanup
    if os.path.exists(db_path):
        os.remove(db_path)


def test_vault_initialization(test_vault):
    """Test that the identity vault initializes correctly."""
    assert test_vault is not None
    assert test_vault.engine is not None
    assert test_vault.SessionLocal is not None


def test_pseudonymize_new_patient(test_vault):
    """Test creating a new patient identity."""
    patient_uuid, is_new = test_vault.pseudonymize_patient(
        patient_name="John Doe",
        age=45,
        gender="Male",
        component="test"
    )
    
    assert patient_uuid is not None
    assert len(patient_uuid) == 36  # UUID format
    assert is_new is True


def test_pseudonymize_existing_patient(test_vault):
    """Test retrieving an existing patient identity."""
    # Create patient first
    uuid1, is_new1 = test_vault.pseudonymize_patient(
        patient_name="Jane Smith",
        age=32,
        gender="Female",
        component="test"
    )
    assert is_new1 is True
    
    # Retrieve same patient
    uuid2, is_new2 = test_vault.pseudonymize_patient(
        patient_name="Jane Smith",
        age=32,
        gender="Female",
        component="test"
    )
    
    assert uuid2 == uuid1  # Same UUID
    assert is_new2 is False  # Not a new patient


def test_reidentify_patient(test_vault):
    """Test re-identifying a patient from UUID."""
    # Pseudonymize first
    patient_uuid, _ = test_vault.pseudonymize_patient(
        patient_name="Alice Johnson",
        age=28,
        gender="Female",
        component="test"
    )
    
    # Re-identify
    identity = test_vault.reidentify_patient(
        patient_uuid=patient_uuid,
        component="test"
    )
    
    assert identity is not None
    assert identity["patient_name"] == "Alice Johnson"
    assert identity["age"] == 28
    assert identity["gender"] == "Female"
    assert identity["patient_uuid"] == patient_uuid


def test_reidentify_nonexistent_patient(test_vault):
    """Test re-identifying a non-existent patient."""
    identity = test_vault.reidentify_patient(
        patient_uuid="non-existent-uuid",
        component="test"
    )
    
    assert identity is None


def test_store_medical_record(test_vault):
    """Test storing a medical record."""
    # Create patient first
    patient_uuid, _ = test_vault.pseudonymize_patient(
        patient_name="Bob Williams",
        age=50,
        gender="Male",
        component="test"
    )
    
    # Store record
    record_id = test_vault.store_medical_record(
        patient_uuid=patient_uuid,
        record_type="appointment",
        symptoms="Headache and fever",
        diagnosis="Viral infection",
        treatment_plan="Rest and fluids",
        component="test"
    )
    
    assert record_id is not None
    assert len(record_id) == 36  # UUID format


def test_get_patient_records(test_vault):
    """Test retrieving patient medical records."""
    # Create patient
    patient_uuid, _ = test_vault.pseudonymize_patient(
        patient_name="Carol Davis",
        age=35,
        gender="Female",
        component="test"
    )
    
    # Store multiple records
    test_vault.store_medical_record(
        patient_uuid=patient_uuid,
        record_type="appointment",
        symptoms="Cough",
        component="test"
    )
    
    test_vault.store_medical_record(
        patient_uuid=patient_uuid,
        record_type="followup",
        symptoms="Cough improving",
        component="test"
    )
    
    # Retrieve all records
    records = test_vault.get_patient_records(
        patient_uuid=patient_uuid,
        component="test"
    )
    
    assert len(records) == 2
    assert records[0]["record_type"] in ["appointment", "followup"]


def test_get_patient_records_filtered(test_vault):
    """Test retrieving filtered patient records."""
    # Create patient
    patient_uuid, _ = test_vault.pseudonymize_patient(
        patient_name="David Miller",
        age=40,
        gender="Male",
        component="test"
    )
    
    # Store different types
    test_vault.store_medical_record(
        patient_uuid=patient_uuid,
        record_type="appointment",
        symptoms="Back pain",
        component="test"
    )
    
    test_vault.store_medical_record(
        patient_uuid=patient_uuid,
        record_type="summary",
        diagnosis="Muscle strain",
        component="test"
    )
    
    # Retrieve only appointments
    appointments = test_vault.get_patient_records(
        patient_uuid=patient_uuid,
        record_type="appointment",
        component="test"
    )
    
    assert len(appointments) == 1
    assert appointments[0]["record_type"] == "appointment"


def test_audit_trail_logging(test_vault):
    """Test that audit trail is properly logged."""
    # Perform some operations
    patient_uuid, _ = test_vault.pseudonymize_patient(
        patient_name="Eve Thompson",
        age=29,
        gender="Female",
        component="test"
    )
    
    test_vault.reidentify_patient(
        patient_uuid=patient_uuid,
        component="test"
    )
    
    # Retrieve audit trail
    audit_logs = test_vault.get_audit_trail(patient_uuid=patient_uuid)
    
    assert len(audit_logs) >= 2  # At least pseudonymize and reidentify
    assert all(log["cloud_exposed"] is False for log in audit_logs)
    assert all(log["pii_accessed"] is True for log in audit_logs)


def test_audit_trail_privacy_compliance(test_vault):
    """Test that no operations are marked as cloud-exposed."""
    # Create multiple patients and operations
    for i in range(3):
        patient_uuid, _ = test_vault.pseudonymize_patient(
            patient_name=f"Patient {i}",
            age=30 + i,
            gender="Male" if i % 2 == 0 else "Female",
            component="test"
        )
        
        test_vault.store_medical_record(
            patient_uuid=patient_uuid,
            record_type="appointment",
            symptoms=f"Symptom {i}",
            component="test"
        )
    
    # Check all audit logs
    all_logs = test_vault.get_audit_trail(limit=100)
    
    # CRITICAL: No operation should ever be cloud-exposed
    assert all(log["cloud_exposed"] is False for log in all_logs)
    print(f"✅ Privacy compliance verified: {len(all_logs)} operations, 0 cloud-exposed")
```

---

## ✅ TESTING REQUIREMENTS

### Test 1: Database Creation
```bash
cd backend
python -c "from database.identity_vault import identity_vault; print('Database created successfully')"

# Verify database file exists
ls -la database/identity_vault.db
```

### Test 2: Run All Vault Tests
```bash
cd backend
pytest tests/test_identity_vault.py -v

# Expected: All 11 tests should PASS
```

### Test 3: Manual Pseudonymization Test
```python
# Create test script: backend/test_manual_vault.py
from database.identity_vault import identity_vault

# Pseudonymize a patient
uuid, is_new = identity_vault.pseudonymize_patient(
    patient_name="Test Patient",
    age=30,
    gender="Male",
    component="manual_test"
)

print(f"Patient UUID: {uuid}")
print(f"Is new: {is_new}")

# Re-identify
identity = identity_vault.reidentify_patient(uuid, component="manual_test")
print(f"Identity: {identity}")

# Check audit trail
logs = identity_vault.get_audit_trail(patient_uuid=uuid)
print(f"\nAudit logs: {len(logs)}")
for log in logs:
    print(f"  - {log['operation']} by {log['component']} (Cloud exposed: {log['cloud_exposed']})")
```

Run it:
```bash
cd backend
python test_manual_vault.py
```

### Test 4: Privacy Compliance Verification
```bash
cd backend
pytest tests/test_identity_vault.py::test_audit_trail_privacy_compliance -v -s

# CRITICAL: Must verify that NO operations are marked as cloud-exposed
```

### Test 5: Server Integration Test
```bash
cd backend
python main.py

# In another terminal:
curl http://localhost:8000/health

# Expected JSON should include:
# "components": {"identity_vault": "operational"}
```

---

## 📋 COMPLETION CHECKLIST

- [ ] `models.py` created with PatientIdentity, MedicalRecord, AuditLog
- [ ] `identity_vault.py` created with full CRUD operations
- [ ] `main.py` updated to initialize vault on startup
- [ ] All 11 vault tests created
- [ ] Database file created successfully
- [ ] All tests pass (11/11)
- [ ] Manual vault test works correctly
- [ ] Privacy compliance verified (0 cloud-exposed operations)
- [ ] Server starts with vault operational
- [ ] Audit trail logging works correctly

---

## 🎯 EXPECTED DELIVERABLES

1. Working SQLite database with 3 tables
2. Full identity vault manager with bidirectional mapping
3. Comprehensive audit trail system
4. 11 passing unit tests
5. Privacy compliance verification
6. Integration with FastAPI application

---

## ⚠️ CRITICAL PRIVACY NOTES

- **NEVER** expose `identity_vault` instance to cloud-facing routes
- **ALWAYS** log operations with `cloud_exposed=False`
- **ONLY** use UUIDs when communicating with cloud agents
- **TEST** privacy compliance rigorously before proceeding

---

## 🔄 NEXT PROMPT

After successfully completing and testing this prompt, proceed to:

**Prompt 3: Pinecone Semantic Anchor Store**

This will implement the vector database for storing non-sensitive medical context.
