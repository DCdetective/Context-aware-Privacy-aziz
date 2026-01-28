from agents.coordinator import coordinator_agent
from agents.worker import worker_agent
from agents.gatekeeper import gatekeeper_agent
from vector_store.mock_semantic_store import MockSemanticStore

# Initialize worker with semantic store
semantic_store = MockSemanticStore()
worker_agent.semantic_store = semantic_store

print("=" * 60)
print("Testing Cloud Agents (Coordinator + Worker)")
print("=" * 60)

# Simulate pseudonymized input from Gatekeeper
user_input = "Patient: Test Cloud Patient, 35, Male. Symptoms: Headache"
pseudo_data = gatekeeper_agent.pseudonymize_input(user_input)

patient_uuid = pseudo_data["patient_uuid"]
semantic_context = pseudo_data["semantic_context"]

print(f"\n[PSEUDONYMIZED DATA]")
print(f"UUID: {patient_uuid}")
print(f"Semantic: {semantic_context}")

# Step 1: Coordinator plans the task
print(f"\n[COORDINATOR]")
coord_result = coordinator_agent.coordinate_request(
    patient_uuid=patient_uuid,
    action_type="appointment",
    semantic_context=semantic_context
)

print(f"Plan created: {coord_result['execution_plan']['steps']}")

# Step 2: Worker executes the task
print(f"\n[WORKER]")
worker_result = worker_agent.execute_task(
    patient_uuid=patient_uuid,
    action_type="appointment",
    execution_plan=coord_result["execution_plan"],
    semantic_context=semantic_context
)

print(f"Success: {worker_result['success']}")
print(f"Action: {worker_result['action']}")
print(f"Appointment Time: {worker_result.get('appointment_time')}")

# Step 3: Gatekeeper re-identifies for output
print(f"\n[RE-IDENTIFICATION]")
final_output = gatekeeper_agent.reidentify_output(patient_uuid, worker_result)

print(f"Patient Name: {final_output.get('patient_name')}")
print(f"Appointment: {final_output.get('appointment_time')}")

print("\n" + "=" * 60)
