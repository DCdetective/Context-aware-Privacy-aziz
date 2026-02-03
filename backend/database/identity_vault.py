from sqlalchemy import create_engine, or_
from sqlalchemy.orm import sessionmaker, Session
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
import logging
import uuid as uuid_lib

from database.models import Base, PatientIdentity, MedicalRecord, AuditLog
from utils.config import settings

logger = logging.getLogger(__name__)


class IdentityVault:
    """
    Identity Vault - Local PII storage and management.
    
    CRITICAL PRIVACY COMPONENT:
    - All PII stored here NEVER leaves the local environment
    - Provides UUID ↔ PII mapping
    - Maintains audit trail for compliance
    - Enables re-identification for final output
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize Identity Vault.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path or settings.sqlite_db_path
        self.engine = create_engine(f'sqlite:///{self.db_path}', echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)
        
        # Create tables
        Base.metadata.create_all(self.engine)
        
        logger.info(f"Identity Vault initialized at {self.db_path}")
    
    def _get_session(self) -> Session:
        """Get a database session."""
        return self.SessionLocal()
    
    def _log_audit(
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
        Log an audit entry.
        
        Args:
            session: Database session
            patient_uuid: Patient UUID
            operation: Operation performed
            component: Component performing operation
            pii_accessed: Whether PII was accessed
            cloud_exposed: Whether data was exposed to cloud (should be False)
            details: Additional details
        """
        log = AuditLog(
            log_id=str(uuid_lib.uuid4()),
            patient_uuid=patient_uuid,
            operation=operation,
            component=component,
            pii_accessed=pii_accessed,
            cloud_exposed=cloud_exposed,
            timestamp=datetime.utcnow(),
            details=details
        )
        
        session.add(log)
        # Note: commit is handled by caller
    
    def pseudonymize_patient(
        self,
        patient_name: str,
        age: Optional[int] = None,
        gender: Optional[str] = None,
        component: str = "system"
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
            existing = session.query(PatientIdentity).filter(
                PatientIdentity.patient_name == patient_name
            ).first()
            
            if existing:
                # Update last accessed
                existing.last_accessed = datetime.utcnow()
                existing.access_count += 1
                
                # Update age/gender if provided and different
                if age is not None and existing.age != age:
                    existing.age = age
                if gender is not None and existing.gender != gender:
                    existing.gender = gender
                
                session.commit()
                
                # Log re-identification
                self._log_audit(
                    session=session,
                    patient_uuid=existing.patient_uuid,
                    operation="pseudonymize_existing",
                    component=component,
                    pii_accessed=True,
                    details=f"Retrieved existing UUID for {patient_name}"
                )
                session.commit()
                
                logger.info(f"Retrieved existing UUID for patient: {existing.patient_uuid}")
                return existing.patient_uuid, False
            
            # Create new patient
            new_uuid = str(uuid_lib.uuid4())
            new_patient = PatientIdentity(
                patient_uuid=new_uuid,
                patient_name=patient_name,
                age=age,
                gender=gender,
                created_at=datetime.utcnow(),
                last_accessed=datetime.utcnow(),
                access_count=1
            )
            
            session.add(new_patient)
            session.commit()
            
            # Log creation
            self._log_audit(
                session=session,
                patient_uuid=new_uuid,
                operation="pseudonymize_new",
                component=component,
                pii_accessed=True,
                details=f"Created new UUID for {patient_name}"
            )
            session.commit()
            
            logger.info(f"Created new UUID for patient: {new_uuid}")
            return new_uuid, True
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error in pseudonymize_patient: {str(e)}")
            raise
        finally:
            session.close()
    
    def reidentify_patient(
        self,
        patient_uuid: str,
        component: str = "system"
    ) -> Optional[Dict[str, Any]]:
        """
        Re-identify patient from UUID.
        
        Args:
            patient_uuid: Patient UUID
            component: Component requesting re-identification
            
        Returns:
            Patient identity dictionary or None if not found
        """
        session = self._get_session()
        
        try:
            patient = session.query(PatientIdentity).filter(
                PatientIdentity.patient_uuid == patient_uuid
            ).first()
            
            if not patient:
                logger.warning(f"Patient UUID not found: {patient_uuid}")
                return None
            
            # Update access tracking
            patient.last_accessed = datetime.utcnow()
            patient.access_count += 1
            session.commit()
            
            # Log re-identification
            self._log_audit(
                session=session,
                patient_uuid=patient_uuid,
                operation="reidentify",
                component=component,
                pii_accessed=True,
                details=f"Re-identified patient for {component}"
            )
            session.commit()
            
            identity = {
                'patient_uuid': patient.patient_uuid,
                'patient_name': patient.patient_name,
                'age': patient.age,
                'gender': patient.gender,
                'created_at': patient.created_at.isoformat() if patient.created_at else None,
                'last_accessed': patient.last_accessed.isoformat() if patient.last_accessed else None,
                'access_count': patient.access_count
            }
            
            logger.info(f"Re-identified patient: {patient_uuid}")
            return identity
            
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
        notes: Optional[str] = None,
        component: str = "system"
    ) -> str:
        """
        Store a medical record for a patient.
        
        Args:
            patient_uuid: Patient UUID
            record_type: Type of record ('appointment', 'followup', 'summary')
            symptoms: Patient symptoms
            diagnosis: Diagnosis
            treatment_plan: Treatment plan
            notes: Additional notes
            component: Component storing the record
            
        Returns:
            Record ID
        """
        session = self._get_session()
        
        try:
            record_id = str(uuid_lib.uuid4())
            
            record = MedicalRecord(
                record_id=record_id,
                patient_uuid=patient_uuid,
                record_type=record_type,
                symptoms=symptoms,
                diagnosis=diagnosis,
                treatment_plan=treatment_plan,
                notes=notes,
                created_at=datetime.utcnow()
            )
            
            session.add(record)
            session.commit()
            
            # Log creation
            self._log_audit(
                session=session,
                patient_uuid=patient_uuid,
                operation="store_record",
                component=component,
                pii_accessed=True,
                details=f"Stored {record_type} record"
            )
            session.commit()
            
            logger.info(f"Stored medical record: {record_id} for patient {patient_uuid}")
            return record_id
            
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
        component: str = "system"
    ) -> List[Dict[str, Any]]:
        """
        Retrieve medical records for a patient.
        
        Args:
            patient_uuid: Patient UUID
            record_type: Optional filter by record type
            component: Component requesting records
            
        Returns:
            List of medical records
        """
        session = self._get_session()
        
        try:
            query = session.query(MedicalRecord).filter(
                MedicalRecord.patient_uuid == patient_uuid
            )
            
            if record_type:
                query = query.filter(MedicalRecord.record_type == record_type)
            
            records = query.order_by(MedicalRecord.created_at.desc()).all()
            
            # Log access
            if records:
                self._log_audit(
                    session=session,
                    patient_uuid=patient_uuid,
                    operation="retrieve_records",
                    component=component,
                    pii_accessed=True,
                    details=f"Retrieved {len(records)} records"
                )
                session.commit()
            
            result = [
                {
                    'record_id': r.record_id,
                    'patient_uuid': r.patient_uuid,
                    'record_type': r.record_type,
                    'symptoms': r.symptoms,
                    'diagnosis': r.diagnosis,
                    'treatment_plan': r.treatment_plan,
                    'notes': r.notes,
                    'created_at': r.created_at.isoformat() if r.created_at else None
                }
                for r in records
            ]
            
            logger.info(f"Retrieved {len(result)} records for patient {patient_uuid}")
            return result
            
        except Exception as e:
            logger.error(f"Error retrieving records: {str(e)}")
            raise
        finally:
            session.close()
    
    def get_audit_logs(
        self,
        patient_uuid: Optional[str] = None,
        operation: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve audit logs.
        
        Args:
            patient_uuid: Optional filter by patient UUID
            operation: Optional filter by operation
            limit: Maximum number of logs to return
            
        Returns:
            List of audit logs
        """
        session = self._get_session()
        
        try:
            query = session.query(AuditLog)
            
            if patient_uuid:
                query = query.filter(AuditLog.patient_uuid == patient_uuid)
            
            if operation:
                query = query.filter(AuditLog.operation == operation)
            
            logs = query.order_by(AuditLog.timestamp.desc()).limit(limit).all()
            
            result = [
                {
                    'log_id': log.log_id,
                    'patient_uuid': log.patient_uuid,
                    'operation': log.operation,
                    'component': log.component,
                    'pii_accessed': log.pii_accessed,
                    'cloud_exposed': log.cloud_exposed,
                    'timestamp': log.timestamp.isoformat() if log.timestamp else None,
                    'details': log.details
                }
                for log in logs
            ]
            
            return result
            
        except Exception as e:
            logger.error(f"Error retrieving audit logs: {str(e)}")
            raise
        finally:
            session.close()
    
    def verify_privacy_compliance(self) -> Dict[str, Any]:
        """
        Verify privacy compliance - ensure no PII exposed to cloud.
        
        Returns:
            Compliance report
        """
        session = self._get_session()
        
        try:
            # Check for any cloud exposure
            cloud_exposed = session.query(AuditLog).filter(
                AuditLog.cloud_exposed == True
            ).count()
            
            total_operations = session.query(AuditLog).count()
            total_patients = session.query(PatientIdentity).count()
            
            report = {
                'total_patients': total_patients,
                'total_operations': total_operations,
                'cloud_exposed_count': cloud_exposed,
                'privacy_compliant': cloud_exposed == 0,
                'timestamp': datetime.utcnow().isoformat()
            }
            
            if cloud_exposed > 0:
                logger.error(f"PRIVACY VIOLATION: {cloud_exposed} operations exposed PII to cloud!")
            else:
                logger.info("Privacy compliance verified: No PII exposed to cloud")
            
            return report
            
        finally:
            session.close()


# Global instance
identity_vault = IdentityVault()
