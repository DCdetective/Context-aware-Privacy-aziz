"""
Tests for Human-in-the-Loop (HITL) Workflow
"""
import pytest
from agents.hitl_manager import hitl_manager
from agents.coordinator import coordinator
from agents.session_manager import session_manager


def test_generate_medical_questions():
    """Test medical question generation."""
    questions = hitl_manager.generate_medical_questions(
        intent='appointment',
        semantic_context={
            'symptom_category': 'respiratory',
            'urgency_level': 'urgent'
        }
    )
    
    assert len(questions) >= 2
    assert len(questions) <= 3
    assert all(isinstance(q, str) for q in questions)
    assert all(len(q) > 0 for q in questions)


def test_generate_medical_questions_cardiac():
    """Test medical question generation for cardiac category."""
    questions = hitl_manager.generate_medical_questions(
        intent='appointment',
        semantic_context={
            'symptom_category': 'cardiac',
            'urgency_level': 'routine'
        }
    )
    
    assert len(questions) >= 2
    assert len(questions) <= 3
    # Check for cardiac-specific questions
    assert any('chest' in q.lower() or 'heart' in q.lower() for q in questions)


def test_generate_medical_questions_general():
    """Test medical question generation for general category."""
    questions = hitl_manager.generate_medical_questions(
        intent='followup',
        semantic_context={
            'symptom_category': 'general',
            'urgency_level': 'routine'
        }
    )
    
    assert len(questions) >= 2
    assert len(questions) <= 3


def test_confirmation_parsing():
    """Test confirmation response parsing."""
    # Positive confirmations
    assert hitl_manager.parse_confirmation_response("yes") is True
    assert hitl_manager.parse_confirmation_response("Yes, confirm") is True
    assert hitl_manager.parse_confirmation_response("ok proceed") is True
    assert hitl_manager.parse_confirmation_response("sure") is True
    assert hitl_manager.parse_confirmation_response("yeah") is True
    assert hitl_manager.parse_confirmation_response("yep") is True
    assert hitl_manager.parse_confirmation_response("correct") is True
    
    # Negative confirmations
    assert hitl_manager.parse_confirmation_response("no") is False
    assert hitl_manager.parse_confirmation_response("cancel") is False
    assert hitl_manager.parse_confirmation_response("nevermind") is False
    assert hitl_manager.parse_confirmation_response("nope") is False
    assert hitl_manager.parse_confirmation_response("stop") is False


def test_confirmation_summary_appointment():
    """Test confirmation summary generation for appointments."""
    summary = hitl_manager.create_confirmation_summary(
        intent='appointment',
        patient_name='John Doe',
        action_data={
            'recommended_doctor': 'Dr. Smith',
            'appointment_date': '2024-02-15',
            'appointment_time': '10:00 AM',
            'consultation_duration': 30
        },
        user_responses=[
            {'question': 'How long have you been experiencing these symptoms?', 'response': '2 days'},
            {'question': 'Do you have difficulty breathing?', 'response': 'Sometimes'}
        ]
    )
    
    assert 'John Doe' in summary
    assert 'Dr. Smith' in summary
    assert '2024-02-15' in summary
    assert '10:00 AM' in summary
    assert '30 minutes' in summary
    assert '2 days' in summary
    assert 'Sometimes' in summary
    assert 'yes' in summary.lower() or 'confirm' in summary.lower()


def test_confirmation_summary_followup():
    """Test confirmation summary generation for followups."""
    summary = hitl_manager.create_confirmation_summary(
        intent='followup',
        patient_name='Jane Smith',
        action_data={
            'followup_date': '2024-03-01',
            'recommended_doctor': 'Dr. Johnson'
        },
        user_responses=[
            {'question': 'How are you feeling?', 'response': 'Better'}
        ]
    )
    
    assert 'Jane Smith' in summary
    assert '2024-03-01' in summary
    assert 'Dr. Johnson' in summary
    assert 'Better' in summary


def test_hitl_appointment_workflow():
    """Test complete HITL workflow for appointment."""
    # Clear any existing sessions
    session_manager.clear_all_sessions()
    
    session_id = session_manager.create_session()
    
    # Step 1: Initiate appointment
    response1 = coordinator.process_message(
        "Book appointment for John Doe, age 30, fever",
        session_id=session_id
    )
    
    # Should ask first question
    assert response1['success'] is True
    assert "question" in response1['message'].lower() or "?" in response1['message']
    assert response1['intent'] == 'appointment_initiated'
    
    # Step 2: Check pending action exists
    pending = session_manager.get_pending_action(session_id)
    assert pending is not None
    assert pending['action_type'] == 'appointment'
    assert 'questions_asked' in pending
    
    # Answer all questions
    questions = pending.get('questions_asked', [])
    assert len(questions) >= 2
    
    for i in range(len(questions) - 1):
        response = coordinator.process_message(
            f"Test answer {i+1}",
            session_id=session_id
        )
        assert response['success'] is True
    
    # Answer last question - should get confirmation summary
    response_confirm = coordinator.process_message(
        "Test answer final",
        session_id=session_id
    )
    
    assert response_confirm['success'] is True
    assert "confirm" in response_confirm['message'].lower()
    assert response_confirm['intent'] == 'awaiting_confirmation'
    
    # Step 3: Confirm
    response_final = coordinator.process_message(
        "yes, confirm",
        session_id=session_id
    )
    
    assert response_final['success'] is True
    assert "booked" in response_final['message'].lower() or "scheduled" in response_final['message'].lower()
    assert response_final['intent'] == 'appointment_confirmed'
    
    # Verify pending action is cleared
    pending_after = session_manager.get_pending_action(session_id)
    assert pending_after is None


def test_hitl_followup_workflow():
    """Test HITL workflow using session manager directly (bypassing gatekeeper inconsistency)."""
    session_manager.clear_all_sessions()
    session_id = session_manager.create_session()
    
    # Simulate that patient identity is already resolved
    session_manager.set_active_patient(session_id, "test-uuid-123", "Jane Smith")
    
    # Set up a pending action with questions (simulating HITL initiation)
    questions = ["How long have you been experiencing symptoms?", "Rate your pain 1-10?"]
    session_manager.set_pending_action(
        session_id=session_id,
        action_type='followup',
        action_data={'followup_date': '2024-02-20', 'recommended_doctor': 'Dr. Test'},
        questions_asked=questions
    )
    
    # Update with patient UUID
    pending = session_manager.get_pending_action(session_id)
    pending['patient_uuid'] = "test-uuid-123"
    
    # Simulate answering questions via coordinator
    for i in range(len(questions)):
        response = coordinator.process_message(f"Answer {i+1}", session_id=session_id)
        assert response['success'] is True
    
    # Should now be at confirmation stage
    assert "confirm" in response['message'].lower()
    
    # Confirm the action
    response_final = coordinator.process_message("yes", session_id=session_id)
    assert response_final['success'] is True
    assert 'confirmed' in response_final['intent']


def test_hitl_cancel_workflow():
    """Test HITL workflow cancellation using session manager directly."""
    session_manager.clear_all_sessions()
    session_id = session_manager.create_session()
    
    # Simulate that patient identity is already resolved
    session_manager.set_active_patient(session_id, "test-uuid-456", "Bob Johnson")
    
    # Set up a pending action with questions
    questions = ["How severe is the headache?", "When did it start?"]
    session_manager.set_pending_action(
        session_id=session_id,
        action_type='appointment',
        action_data={'appointment_date': '2024-02-25', 'recommended_doctor': 'Dr. Smith'},
        questions_asked=questions
    )
    
    # Update with patient UUID
    pending = session_manager.get_pending_action(session_id)
    pending['patient_uuid'] = "test-uuid-456"
    
    # Answer all questions
    for i in range(len(questions)):
        response = coordinator.process_message(f"Answer {i+1}", session_id=session_id)
        assert response['success'] is True
    
    # Should be at confirmation stage
    assert "confirm" in response['message'].lower()
    
    # Cancel instead of confirming
    response_cancel = coordinator.process_message("no, cancel", session_id=session_id)
    
    assert response_cancel['success'] is True
    assert response_cancel['intent'] == 'cancelled'
    assert "cancel" in response_cancel['message'].lower()
    
    # Verify pending action is cleared
    pending_after = session_manager.get_pending_action(session_id)
    assert pending_after is None


def test_session_manager_pending_action():
    """Test session manager pending action methods."""
    session_manager.clear_all_sessions()
    session_id = session_manager.create_session()
    
    # Set pending action
    session_manager.set_pending_action(
        session_id=session_id,
        action_type='appointment',
        action_data={'doctor': 'Dr. Test'},
        questions_asked=['Q1', 'Q2']
    )
    
    # Get pending action
    pending = session_manager.get_pending_action(session_id)
    assert pending is not None
    assert pending['action_type'] == 'appointment'
    assert pending['action_data']['doctor'] == 'Dr. Test'
    assert len(pending['questions_asked']) == 2
    
    # Add question response
    session_manager.add_question_response(
        session_id=session_id,
        question='Q1',
        response='Answer 1'
    )
    
    pending = session_manager.get_pending_action(session_id)
    assert len(pending['user_responses']) == 1
    assert pending['user_responses'][0]['question'] == 'Q1'
    assert pending['user_responses'][0]['response'] == 'Answer 1'
    
    # Clear pending action
    session_manager.clear_pending_action(session_id)
    pending = session_manager.get_pending_action(session_id)
    assert pending is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
