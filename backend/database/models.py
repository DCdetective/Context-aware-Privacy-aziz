from sqlalchemy import Column, String, Integer, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
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
    age = Column(Integer, nullable=True)
    gender = Column(String(50), nullable=True)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Audit trail
    last_accessed = Column(DateTime(timezone=True))
    access_count = Column(Integer, default=0)
    
    # Relationships
    medical_records = relationship("MedicalRecord", back_populates="patient")
    audit_logs = relationship("AuditLog", back_populates="patient")
    
    def __repr__(self):
        return f"<PatientIdentity(uuid={self.patient_uuid}, name=REDACTED)>"


class MedicalRecord(Base):
    """
    Local storage for medical records linked to patient UUID.
    Contains PII that must stay local.
    """
    __tablename__ = "medical_records"
    
    record_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    patient_uuid = Column(String(36), ForeignKey('patient_identities.patient_uuid'), nullable=False, index=True)
    
    # Medical information (PII)
    symptoms = Column(Text, nullable=True)
    diagnosis = Column(Text, nullable=True)
    treatment_plan = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    
    # Record metadata
    record_type = Column(String(50), nullable=False)  # 'appointment', 'followup', 'summary'
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationship
    patient = relationship("PatientIdentity", back_populates="medical_records")
    
    def __repr__(self):
        return f"<MedicalRecord(id={self.record_id}, patient={self.patient_uuid}, type={self.record_type})>"


class AuditLog(Base):
    """
    Audit trail for all identity vault operations.
    Critical for academic demonstration and security verification.
    """
    __tablename__ = "audit_logs"
    
    log_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    patient_uuid = Column(String(36), ForeignKey('patient_identities.patient_uuid'), nullable=False, index=True)
    
    # Operation details
    operation = Column(String(100), nullable=False)  # 'pseudonymize', 'reidentify', 'create', 'update'
    component = Column(String(100), nullable=False)  # 'gatekeeper', 'coordinator', etc.
    
    # Privacy metadata
    pii_accessed = Column(Boolean, default=False)
    cloud_exposed = Column(Boolean, default=False)  # Should ALWAYS be False
    
    # Timestamps
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    
    # Additional context
    details = Column(Text, nullable=True)
    
    # Relationship
    patient = relationship("PatientIdentity", back_populates="audit_logs")
    
    def __repr__(self):
        return f"<AuditLog(operation={self.operation}, component={self.component}, time={self.timestamp})>"
