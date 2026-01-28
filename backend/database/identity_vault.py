from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.sql import func
from typing import Optional, Dict, Tuple
from datetime import datetime
import uuid
import logging

from database.models import Base, PatientIdentity, MedicalRecord, AuditLog
from utils.config import settings

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
        
        # Ensure directory exists
        import os
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        
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
                session.commit()
                
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
            session.commit()
            
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
            session.commit()
            
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
            session.commit()
            
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
            session.commit()
            
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
