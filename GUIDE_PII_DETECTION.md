# 🔍 PII Detection Guide - How to Ensure Your Appointments Contain PII

## Overview

MedShield uses a privacy-preserving architecture where **PII (Personally Identifiable Information)** is detected, extracted, and pseudonymized **locally** before any data goes to the cloud. This guide explains how to ensure your appointment inputs contain the proper PII fields.

---

## What is PII in MedShield?

**PII (Personally Identifiable Information)** includes:
1. **Patient Name** - Full name that identifies the person
2. **Age** - Numerical age value
3. **Gender** - Male/Female/Other
4. **Symptoms** - Medical description (not technically PII but required)

---

## ✅ How the Frontend Form Ensures PII

Your appointment form (`/appointment`) **already collects all required PII correctly**:

```html
<!-- From frontend/templates/appointment.html -->
<input type="text" id="patientName" name="patient_name" required>
<input type="number" id="age" name="age" required>
<select id="gender" name="gender" required>
<textarea id="symptoms" name="symptoms" required>
```

### What the Form Sends:
```json
{
  "patient_name": "John Doe",
  "age": 45,
  "gender": "Male",
  "symptoms": "Severe chest pain and shortness of breath"
}
```

This is **automatically converted** to the format the Gatekeeper expects:
```
Patient Name: John Doe
Age: 45
Gender: Male
Symptoms: Severe chest pain and shortness of breath
```

---

## 🔍 How PII Detection Works

### Step 1: Gatekeeper Receives Input
The `gatekeeper_agent` receives the structured text from the API.

### Step 2: PII Extraction (Two Methods)

#### Method A: Ollama LLM (Primary)
- Uses local Ollama model (llama3.2:3b)
- AI extracts patient info intelligently
- Handles natural language

#### Method B: Regex Fallback (Backup)
If Ollama fails, regex patterns extract PII:

```python
# Name patterns (MUST BE CAPITALIZED)
"Patient Name: John Doe"
"Name: Jane Smith"
"I am Sarah Johnson"

# Age patterns
"Age: 45"
"45 years old"
"age: 32"

# Gender patterns
"Gender: Male"
"female"
"man"
```

### Step 3: Pseudonymization
```
John Doe → UUID: e7b3c8d9-4f2a-11ee-be56-0242ac120002
Age: 45 → Stored locally in SQLite
Gender: Male → Stored locally in SQLite
```

### Step 4: Semantic Extraction (Non-PII)
```json
{
  "symptom_category": "cardiac",
  "urgency_level": "emergency",
  "requires_specialist": true,
  "estimated_consultation_time": 60
}
```
☁️ **This semantic data (NO PII) goes to Pinecone cloud database**

---

## ⚠️ Common PII Detection Issues

### Issue 1: Lowercase Names Won't Match
```
❌ BAD:  "Patient Name: john doe"
✅ GOOD: "Patient Name: John Doe"
```

**Why?** Regex patterns look for capitalized names to distinguish from regular words.

**Solution:** Your HTML form already handles this - users type normally, and it's submitted as-is. The Ollama LLM can handle lowercase, but regex fallback cannot.

### Issue 2: Missing Fields
```
❌ BAD:  Only name provided, no age or gender
✅ GOOD: All fields filled: Name, Age, Gender, Symptoms
```

**Why?** Incomplete data results in "Unknown Patient" or default values.

**Solution:** Your form uses `required` attributes - perfect! ✅

### Issue 3: Symbols in Names
```
❌ BAD:  "Dr. John Doe Jr."  (may confuse regex)
✅ GOOD: "John Doe"
```

**Solution:** Ollama LLM handles this, but regex fallback may struggle.

---

## 🧪 Testing PII Detection

### Test Your Input Format

Run the validator I created:
```bash
python tmp_rovodev_pii_validator.py "Patient Name: John Doe, Age: 45, Gender: Male, Symptoms: chest pain"
```

### Expected Output:
```
🔍 1. Checking for PATIENT NAME (PII)...
   ✅ Found name: 'John Doe'

🔍 2. Checking for AGE (PII)...
   ✅ Found age: 45

🔍 3. Checking for GENDER (PII)...
   ✅ Found gender: 'Male'

🔍 4. Checking for SYMPTOMS...
   ✅ Found symptoms: 'chest pain'

✅ EXCELLENT! Your input contains all required PII fields!
```

---

## 📋 Valid Input Examples

### Example 1: Web Form (Current System) ✅
```
Patient Name: John Doe
Age: 45
Gender: Male
Symptoms: Severe chest pain and shortness of breath
```
**Status:** ✅ Perfect! This is what your frontend sends.

### Example 2: JSON Format ✅
```json
{
  "patient_name": "Jane Smith",
  "age": 32,
  "gender": "Female",
  "symptoms": "Persistent headache and dizziness"
}
```
**Status:** ✅ Works! But frontend doesn't use this.

### Example 3: Natural Language ✅ (If using chat)
```
I am Sarah Johnson, 28 years old, female. 
I've been experiencing severe back pain for the past week.
```
**Status:** ✅ Works with Ollama LLM!

### Example 4: Incomplete ❌
```
John Doe has a headache
```
**Status:** ❌ Missing age and gender!

---

## 🔒 Privacy Flow After PII Detection

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. USER FILLS FORM                                              │
│    Name: John Doe, Age: 45, Gender: Male                        │
│    Symptoms: Chest pain                                         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. GATEKEEPER (LOCAL) - PII Detection & Pseudonymization        │
│    ✓ Extracts: "John Doe", 45, "Male"                          │
│    ✓ Creates UUID: e7b3c8d9...                                  │
│    ✓ Stores PII in LOCAL SQLite                                │
│    ✓ Extracts semantic: {"symptom_category": "cardiac"}        │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. PINECONE CLOUD - Only Non-PII Semantic Data                 │
│    ✓ Stores: UUID + semantic features                          │
│    ✗ NO NAME, NO AGE, NO GENDER                                │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. GROQ CLOUD AGENTS - Only See UUID                           │
│    ✓ Coordinator: Plans with UUID + semantic context           │
│    ✓ Worker: Executes with UUID + semantic context             │
│    ✗ NEVER SEE: "John Doe", age, or gender                     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 5. GATEKEEPER (LOCAL) - Re-identification                       │
│    ✓ Retrieves "John Doe" from LOCAL SQLite using UUID         │
│    ✓ Returns: "Appointment for John Doe at 2PM"                │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🎯 Quick Checklist for PII

When submitting an appointment, ensure:

- [x] **Full Name** is provided (First + Last, capitalized)
- [x] **Age** is a valid number (0-150)
- [x] **Gender** is selected (Male/Female/Other)
- [x] **Symptoms** are described

**Your frontend form already ensures this!** ✅

---

## 🔧 Troubleshooting

### Problem: "Unknown Patient" appears in results

**Cause:** PII extraction failed

**Solution:**
1. Check if Ollama is running: `ollama list`
2. Ensure model is loaded: `ollama pull llama3.2:3b`
3. Check logs for extraction errors
4. Verify name is capitalized

### Problem: Appointments not storing in Pinecone

**Cause:** Testing mode enabled (we fixed this!)

**Solution:**
1. ✅ Already fixed: `TESTING_MODE=false` in .env
2. ✅ Already fixed: Environment variable updated
3. ✅ Pinecone connection tested and working

### Problem: Ollama out of memory

**Cause:** Model too large for available RAM

**Solution:**
1. ✅ Already fixed: Changed to `llama3.2:3b` (smaller model)
2. Download: `ollama pull llama3.2:3b`
3. Fallback: System uses regex extraction if Ollama fails

---

## 📊 Verification Commands

### 1. Test PII Detection
```bash
python tmp_rovodev_pii_validator.py "Patient Name: John Doe, Age: 45, Gender: Male, Symptoms: chest pain"
```

### 2. Check Pinecone Stats
```bash
python -c "import sys; sys.path.insert(0, 'backend'); from vector_store.semantic_store import semantic_store; print(semantic_store.get_store_stats())"
```

### 3. Check Configuration
```bash
python tmp_rovodev_verify_config.py
```

---

## 🎓 Summary

**Your system already handles PII correctly!** ✅

1. ✅ Frontend form collects all required PII fields
2. ✅ Gatekeeper extracts and pseudonymizes PII locally
3. ✅ Only semantic (non-PII) data goes to Pinecone
4. ✅ Privacy is preserved throughout the workflow

**The key issue was TESTING_MODE, which we've already fixed!**

Now your appointments ARE being stored in Pinecone cloud database with proper privacy guarantees.

---

## 📞 Need Help?

If you want to verify PII detection for a specific input:
```bash
python tmp_rovodev_pii_validator.py "Your input text here"
```

This will show exactly what PII fields were detected and any issues.
