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
