# MedShield Live Demonstration Script

## Preparation (Before Demo)

### 1. Environment Setup
- [ ] Start Ollama: `ollama serve`
- [ ] Activate venv: `source .venv/bin/activate`
- [ ] Start backend: `cd backend && python main.py`
- [ ] Open browser: `http://localhost:8000`
- [ ] Open browser console (F12) for logs
- [ ] Prepare terminal for backend logs viewing

### 2. Demo Data
Prepare 3 test patients:
1. **John Doe** - 45, Male, Persistent headache
2. **Jane Smith** - 32, Female, Follow-up for previous condition
3. **Bob Williams** - 50, Male, Summary generation

### 3. Talking Points Ready
- Privacy architecture overview
- Multi-agent workflow
- UUID-based pseudonymization
- Audit trail demonstration

## Demo Flow (15-20 minutes)

### Part 1: System Introduction (2 min)

**Script:**
"Good morning/afternoon. I'm presenting MedShield, a privacy-preserving multi-agent medical assistant for my final year project.

The core innovation is that patient identities NEVER leave the local environment. All cloud-based reasoning operates exclusively on pseudonymized UUIDs.

Let me demonstrate how this works through three key medical actions."

**Actions:**
- Show home page
- Briefly explain the three action cards
- Highlight privacy badge

### Part 2: Appointment Scheduling Demo (5 min)

**Script:**
"Let's start with booking an appointment for a new patient."

**Actions:**
1. Click "Book Appointment"
2. Fill in form:
   - Name: John Doe
   - Age: 45
   - Gender: Male
   - Symptoms: "Persistent headache and dizziness for 3 days"
3. Click "Schedule Appointment"

**While Processing:**
"Notice the loading state - the system is now:
1. Extracting PII using the local Gatekeeper agent
2. Generating a UUID and storing the identity mapping locally
3. Sending ONLY the UUID and semantic context to cloud agents
4. The cloud never sees 'John Doe' - only a UUID like 'a1b2c3d4-...'"

**After Result:**
"See the result:
- Appointment scheduled with real name restored
- UUID is shown for transparency
- Privacy notice confirms cloud agents only saw the UUID
- Check the backend logs..."

**Backend Terminal:**
```
Point out these log entries:
- GATEKEEPER: Starting pseudonymization
- COORDINATOR: Processing request (with UUID)
- WORKER: Executing task (UUID only)
- GATEKEEPER: Re-identifying patient
```

### Part 3: Privacy Verification (3 min)

**Script:**
"Let's verify the privacy guarantee through the audit trail."

**Actions:**
1. Open Python shell:
```python
from database.identity_vault import identity_vault

# Get audit logs
logs = identity_vault.get_audit_trail(limit=20)

# Check for cloud exposure
for log in logs:
    print(f"{log['operation']:20s} | Cloud Exposed: {log['cloud_exposed']}")
```

**Highlight:**
"Every operation is logged. Notice 'cloud_exposed' is False for every single entry. This is our guarantee that NO PII reached the cloud."

### Part 4: Follow-Up Demonstration (4 min)

**Script:**
"Now let's demonstrate context-aware follow-up scheduling using stored semantic context."

**Actions:**
1. Navigate to Follow-Ups page
2. Enter only: Name: "John Doe"
3. Submit

**While Processing:**
"The system:
1. Retrieves the existing UUID for John Doe
2. Fetches semantic medical context from previous visits
3. Schedules follow-up maintaining continuity of care
4. All without exposing identity to cloud agents"

**After Result:**
"Notice:
- Previous visits tracked
- Continuity maintained
- Same UUID used
- No need to re-enter full medical history"

### Part 5: Medical Summary Generation (4 min)

**Script:**
"Finally, let's generate a privacy-safe medical summary."

**Actions:**
1. Navigate to Summaries page
2. Enter: Name: "John Doe"
3. Generate summary

**After Result:**
"The summary shows:
- Total visits count
- Record types
- Generated using cloud reasoning
- But created using UUID-only data
- Identity restored only at final output"

### Part 6: Architecture Explanation (2 min)

**Script:**
"Let me quickly explain the multi-agent architecture."

**Show Diagram (from documentation):**
```
User → Gatekeeper (Local) → [Privacy Boundary] → 
Coordinator (Cloud) → Worker (Cloud) → 
[Privacy Boundary] → Gatekeeper (Local) → User
```

**Explain:**
1. **Gatekeeper:** Privacy guardian, runs locally on Ollama
2. **Identity Vault:** Local SQLite, never networked
3. **Coordinator:** Cloud agent for planning (UUID only)
4. **Worker:** Cloud agent for execution (UUID only)
5. **Semantic Store:** Cloud-safe non-PII context

## Q&A Preparation

### Expected Questions & Answers

**Q: What if the cloud agent tries to access PII?**
A: "Impossible. Cloud agents physically cannot access the Identity Vault - it's a local SQLite database with no network exposure. They only receive UUIDs."

**Q: How do you prevent name leakage in symptoms?**
A: "The Gatekeeper extracts semantic features from symptoms - like 'neurological category' instead of 'John's headache'. Current implementation focuses on medical semantics, not patient identifiers."

**Q: What about GDPR compliance?**
A: "The architecture inherently supports GDPR - PII stays local, we can delete patient records completely, and we maintain audit trails. For production, we'd add explicit consent management."

**Q: Performance concerns with local LLM?**
A: "Yes, Ollama adds latency. For production, we could use faster local models or implement caching. The privacy benefit outweighs the performance cost for sensitive medical data."

**Q: Why not just encrypt data to cloud?**
A: "Encryption protects data in transit, but cloud agents would still need to decrypt to process. Our approach means cloud agents never have the decryption keys - they work with UUIDs only."

**Q: Scalability?**
A: "Current implementation is single-user. For production: PostgreSQL instead of SQLite, add authentication, containerize with Docker, implement caching, add load balancing."

**Q: What if UUID collisions occur?**
A: "We use Python's UUID4 which has negligible collision probability (1 in 2^122). For production, we'd add UUID uniqueness constraints in the database."

## Demo Checklist

### Before Starting
- [ ] All services running
- [ ] Browser open to home page
- [ ] Terminal visible for logs
- [ ] Python shell ready for audit trail demo
- [ ] Backup test data prepared
- [ ] Architecture diagram ready

### During Demo
- [ ] Speak clearly and pace yourself
- [ ] Show UI and logs simultaneously
- [ ] Highlight privacy notices
- [ ] Demonstrate audit trail
- [ ] Keep to 15-20 minute timeline

### After Demo
- [ ] Answer questions confidently
- [ ] Reference documentation if needed
- [ ] Acknowledge limitations honestly
- [ ] Emphasize privacy-first approach

## Backup Plans

### If Ollama Fails
- Switch to TESTING_MODE=true
- Use fallback extraction (regex-based)
- Explain local LLM concept verbally

### If Groq API Fails
- Use cached responses
- Demonstrate with local Worker logic
- Show architecture instead of live processing

### If Demo System Crashes
- Have screenshots prepared
- Have test results printed
- Show recorded video backup

## Success Criteria

✅ Demonstrated complete workflow  
✅ Showed privacy protection in action  
✅ Displayed audit trail verification  
✅ Explained multi-agent architecture  
✅ Handled questions confidently  
✅ Stayed within time limit
