import pytest
from agents.gatekeeper import gatekeeper_agent


def test_age_group_conversion():
    """Test age to age group conversion."""
    assert gatekeeper_agent._convert_age_to_group(10) == "child"
    assert gatekeeper_agent._convert_age_to_group(15) == "teenager"
    assert gatekeeper_agent._convert_age_to_group(21) == "early 20s"
    assert gatekeeper_agent._convert_age_to_group(45) == "late 40s to early 50s"
    assert gatekeeper_agent._convert_age_to_group(70) == "senior"
    assert gatekeeper_agent._convert_age_to_group(None) == "Unknown"


def test_privacy_report_generation():
    """Test privacy transformation report."""
    pii_data = {
        'patient_name': 'Aziz Ahmed',
        'age': 21,
        'gender': 'Male',
        'medical_info': 'fever and cough'
    }
    
    semantic_context = {
        'symptom_category': 'respiratory',
        'urgency_level': 'routine'
    }
    
    report = gatekeeper_agent.create_privacy_report(
        pii_data=pii_data,
        patient_uuid='12345678',
        semantic_context=semantic_context
    )
    
    assert report['cloud_safe'] is True
    assert report['pii_removed'] >= 2
    assert len(report['transformations']) >= 3
    
    # Check name transformation
    name_transform = next(
        t for t in report['transformations'] 
        if t['field'] == 'Patient Name'
    )
    assert name_transform['original'] == 'Aziz Ahmed'
    assert 'Patient_' in name_transform['transformed']
    
    # Check age transformation
    age_transform = next(
        t for t in report['transformations'] 
        if t['field'] == 'Age'
    )
    assert age_transform['original'] == '21'
    assert age_transform['transformed'] == 'early 20s'


def test_privacy_flow_with_report():
    """Test complete privacy flow includes report."""
    message = "Book appointment for Aziz Ahmed, age 21, male, has fever"
    
    result = gatekeeper_agent.process_message(message)
    
    assert 'privacy_report' in result
    if result.get('privacy_report'):
        report = result['privacy_report']
        assert report['cloud_safe'] is True
        assert len(report['transformations']) > 0
