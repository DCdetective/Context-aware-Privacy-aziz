"""
MedShield Manual E2E Test Script (Prompt 11)

Run this script to manually test the complete user journey.
Usage: python manual_test.py
"""

import asyncio
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set testing mode
os.environ['TESTING_MODE'] = 'true'


async def test_full_journey():
    """Test complete user journey manually."""
    from agents.coordinator import Coordinator
    from agents.session_manager import session_manager
    from database.identity_vault import identity_vault

    coord = Coordinator()
    session_id = session_manager.create_session()

    print("=" * 60)
    print("  MedShield E2E Manual Test")
    print("=" * 60)

    # Pre-create patient for smoother flow
    uuid_val, _ = identity_vault.pseudonymize_patient(
        patient_name="Aziz",
        age=21,
        gender="Male",
        component="manual_test"
    )
    print(f"\n✓ Pre-created patient Aziz (UUID: {uuid_val[:8]}...)")

    # Scenario: Book appointment for Aziz
    messages = [
        ("Hello", "Greeting"),
        ("I need to book an appointment for Aziz", "Start appointment"),
        ("Cardiology", "Provide specialty"),
        ("Tomorrow", "Provide date"),
        ("2 PM", "Provide time"),
        ("Follow-up for chest pain", "Provide reason"),
        ("confirm", "Confirm booking"),
    ]

    print("\n--- Appointment Booking Flow ---\n")

    for msg, description in messages:
        print(f"👤 USER ({description}): {msg}")
        try:
            result = await coord.process_message(session_id, msg)
            response = result.get("response", "No response")
            print(f"🤖 BOT: {response[:200]}")

            if result.get("privacy_events"):
                print(f"🔒 PRIVACY: {len(result['privacy_events'])} transformations")
                for event in result["privacy_events"]:
                    print(f"   {event.get('original', '?')} → {event.get('transformed', '?')}")

            if result.get("requires_action"):
                print("⚠️  Action required from user")
        except Exception as e:
            print(f"❌ Error: {e}")
        print()

    # Follow-up flow
    print("\n--- Follow-up Flow ---\n")

    followup_messages = [
        ("How is Aziz doing?", "Check patient status"),
        ("He's feeling better, the chest pain has gone", "Provide update"),
        ("confirm", "Confirm update"),
    ]

    for msg, description in followup_messages:
        print(f"👤 USER ({description}): {msg}")
        try:
            result = await coord.process_message(session_id, msg)
            response = result.get("response", "No response")
            print(f"🤖 BOT: {response[:200]}")
        except Exception as e:
            print(f"❌ Error: {e}")
        print()

    # Summary flow
    print("\n--- Summary Flow ---\n")

    summary_messages = [
        ("Show me Aziz's complete summary", "Request summary"),
    ]

    for msg, description in summary_messages:
        print(f"👤 USER ({description}): {msg}")
        try:
            result = await coord.process_message(session_id, msg)
            response = result.get("response", "No response")
            print(f"🤖 BOT: {response[:300]}")
        except Exception as e:
            print(f"❌ Error: {e}")
        print()

    print("=" * 60)
    print("  Manual Test Complete")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_full_journey())
