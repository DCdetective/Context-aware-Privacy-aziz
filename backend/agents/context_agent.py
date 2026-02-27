"""
Context Agent – Stores and retrieves patient interactions using vector storage.

Provides RAG-based context enrichment for the multi-agent pipeline.
Uses mock/in-memory storage for testing, Pinecone for production.
"""

import json
import re
import uuid
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from collections import defaultdict

from rag.embeddings import embedding_generator
from rag.retriever import rag_retriever

logger = logging.getLogger(__name__)

# Try to import Groq for LLM-based refinement (optional)
try:
    from groq import Groq
    from utils.config import settings
    GROQ_AVAILABLE = True
except Exception:
    GROQ_AVAILABLE = False


class ContextAgent:
    """
    Context Agent that stores and retrieves patient interactions.

    Supports:
    - Storing interactions with metadata
    - Retrieving patient history filtered by UUID
    - Semantic search across interactions
    - Generating patient summaries
    - Cross-patient data isolation

    Uses in-memory storage by default (for testing).
    Can be connected to Pinecone for production use.
    """

    def __init__(self, pinecone_config: Optional[dict] = None, embedding_model: Optional[str] = None):
        """
        Initialize Context Agent.

        Args:
            pinecone_config: Optional Pinecone configuration dict.
                             If None, uses in-memory storage.
            embedding_model: Optional embedding model name override.
        """
        self._storage: Dict[str, Dict[str, Any]] = {}  # vector_id -> {values, metadata}
        self._embedder = embedding_generator
        self.dimension = self._embedder.dimension
        self.model = "context-agent-local"  # For backward compatibility

        # Try Groq for summary generation
        self._groq_client = None
        self._groq_model = "llama-3.3-70b-versatile"
        if GROQ_AVAILABLE:
            try:
                self._groq_client = Groq(api_key=settings.groq_api_key)
            except Exception:
                pass

        logger.info("Context Agent initialized (in-memory storage)")

    # ── Store Interaction ─────────────────────────────────────────────

    def store_interaction(
        self,
        patient_uuid: str,
        interaction_type: str,
        content: str,
        metadata: Optional[dict] = None,
        session_id: Optional[str] = None,
        workflow: str = "none"
    ) -> str:
        """
        Store an interaction in the vector store with metadata.

        Args:
            patient_uuid: Anonymized patient UUID
            interaction_type: One of 'symptom', 'appointment', 'followup', 'question'
            content: Already anonymized content text
            metadata: Optional additional metadata
            session_id: Optional session ID
            workflow: Workflow type ('appointment', 'followup', 'summary', 'none')

        Returns:
            vector_id: The ID of the stored vector
        """
        valid_types = {"symptom", "appointment", "followup", "question"}
        if interaction_type not in valid_types:
            raise ValueError(f"Invalid interaction_type: {interaction_type}. Must be one of {valid_types}")

        # Generate embedding
        embedding = self._embedder.generate_embedding(content)

        # Create vector ID
        vector_id = f"{patient_uuid}_{interaction_type}_{uuid.uuid4().hex[:8]}"

        # Build metadata
        vector_metadata = {
            "patient_id": patient_uuid,
            "type": interaction_type,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id or "",
            "workflow": workflow,
        }

        # Merge additional metadata
        if metadata:
            for k, v in metadata.items():
                if k not in vector_metadata:
                    vector_metadata[k] = v

        # Store
        self._storage[vector_id] = {
            "id": vector_id,
            "values": embedding,
            "metadata": vector_metadata,
        }

        logger.info(f"Stored interaction {vector_id} for patient {patient_uuid[:8]}...")
        return vector_id

    # ── Retrieve Patient History ──────────────────────────────────────

    def retrieve_patient_history(
        self,
        patient_uuid: str,
        limit: int = 10,
        interaction_types: Optional[List[str]] = None
    ) -> List[dict]:
        """
        Retrieve a patient's historical interactions.

        Args:
            patient_uuid: Patient UUID to filter by
            limit: Maximum number of records
            interaction_types: Optional list of types to filter

        Returns:
            List of interaction dicts, sorted by timestamp (newest first)
        """
        results = []
        for vid, data in self._storage.items():
            meta = data["metadata"]
            if meta["patient_id"] != patient_uuid:
                continue
            if interaction_types and meta["type"] not in interaction_types:
                continue
            results.append({
                "vector_id": vid,
                "score": 1.0,
                "metadata": dict(meta),
            })

        # Sort by timestamp descending
        results.sort(key=lambda r: r["metadata"].get("timestamp", ""), reverse=True)
        return results[:limit]

    # ── Semantic Search ───────────────────────────────────────────────

    def semantic_search(
        self,
        query: str,
        patient_uuid: Optional[str] = None,
        top_k: int = 5
    ) -> List[dict]:
        """
        Semantic search across stored interactions.

        Args:
            query: Search query text
            patient_uuid: Optional patient UUID to restrict search
            top_k: Number of results to return

        Returns:
            List of matching interactions with similarity scores
        """
        query_embedding = self._embedder.generate_embedding(query)

        scored_results = []
        for vid, data in self._storage.items():
            meta = data["metadata"]
            # Apply patient filter
            if patient_uuid and meta["patient_id"] != patient_uuid:
                continue

            # Compute cosine similarity
            score = self._cosine_similarity(query_embedding, data["values"])
            scored_results.append({
                "vector_id": vid,
                "score": score,
                "metadata": dict(meta),
            })

        # Sort by score descending
        scored_results.sort(key=lambda r: r["score"], reverse=True)
        return scored_results[:top_k]

    # ── Patient Summary ───────────────────────────────────────────────

    def get_patient_summary(self, patient_uuid: str) -> dict:
        """
        Aggregate all patient interactions and generate a summary.

        Args:
            patient_uuid: Patient UUID

        Returns:
            Summary dict with total_interactions, appointments, symptoms,
            follow_ups, and summary_text
        """
        all_interactions = self.retrieve_patient_history(patient_uuid, limit=1000)

        appointments = []
        symptoms = []
        follow_ups = []
        questions = []

        for interaction in all_interactions:
            itype = interaction["metadata"]["type"]
            if itype == "appointment":
                appointments.append(interaction)
            elif itype == "symptom":
                symptoms.append(interaction)
            elif itype == "followup":
                follow_ups.append(interaction)
            elif itype == "question":
                questions.append(interaction)

        # Generate summary text
        summary_text = self._generate_summary_text(
            patient_uuid, all_interactions, appointments, symptoms, follow_ups
        )

        return {
            "total_interactions": len(all_interactions),
            "appointments": appointments,
            "symptoms": symptoms,
            "follow_ups": follow_ups,
            "summary_text": summary_text,
        }

    # ── Metadata Filtering ────────────────────────────────────────────

    def filter_interactions(
        self,
        patient_uuid: str,
        interaction_type: Optional[str] = None,
        timestamp_gte: Optional[str] = None,
        timestamp_lte: Optional[str] = None,
        limit: int = 50
    ) -> List[dict]:
        """
        Filter interactions by metadata criteria.

        Args:
            patient_uuid: Patient UUID
            interaction_type: Optional type filter
            timestamp_gte: Optional minimum timestamp (ISO format)
            timestamp_lte: Optional maximum timestamp (ISO format)
            limit: Maximum results

        Returns:
            Filtered list of interactions
        """
        results = []
        for vid, data in self._storage.items():
            meta = data["metadata"]
            if meta["patient_id"] != patient_uuid:
                continue
            if interaction_type and meta["type"] != interaction_type:
                continue
            if timestamp_gte and meta.get("timestamp", "") < timestamp_gte:
                continue
            if timestamp_lte and meta.get("timestamp", "") > timestamp_lte:
                continue
            results.append({
                "vector_id": vid,
                "score": 1.0,
                "metadata": dict(meta),
            })

        results.sort(key=lambda r: r["metadata"].get("timestamp", ""), reverse=True)
        return results[:limit]

    # ── Context Refinement (for Coordinator integration) ──────────────

    def refine_context(
        self,
        patient_uuid: str,
        intent: str,
        semantic_context: Dict[str, Any],
        medical_info: str
    ) -> Dict[str, Any]:
        """
        Refine context using RAG retrieval and optional LLM reasoning.

        Args:
            patient_uuid: Pseudonymized patient UUID
            intent: User intent
            semantic_context: Semantic medical context
            medical_info: Medical information text

        Returns:
            Refined context with recommendations
        """
        logger.info("=" * 60)
        logger.info("CONTEXT AGENT: Refining context")
        logger.info(f"Patient UUID: {patient_uuid[:8]}...")
        logger.info(f"Intent: {intent}")
        logger.info("=" * 60)

        # Guard against None medical_info
        if not medical_info:
            medical_info = semantic_context.get('symptom_category', 'general medical query') or 'general medical query'

        # Step 1: Retrieve relevant context via RAG
        rag_context = rag_retriever.retrieve_context_for_intent(
            patient_uuid=patient_uuid,
            intent=intent,
            semantic_context=semantic_context,
            medical_info=medical_info
        )

        # Step 2: Format context for LLM
        formatted_context = rag_retriever.format_context_for_llm(rag_context)

        # Step 3: Add memory context
        memory_context = semantic_context.get('memory_context', '')
        has_history = semantic_context.get('has_history', False)

        # Step 4: Try LLM refinement, fallback to rule-based
        if self._groq_client:
            try:
                refined = self._llm_refine(patient_uuid, intent, semantic_context, formatted_context, memory_context)
                refined['rag_context'] = {
                    'patient_history_count': len(rag_context.get('patient_history', [])),
                    'relevant_doctors_count': len(rag_context.get('relevant_doctors', [])),
                    'knowledge_retrieved': len(rag_context.get('relevant_knowledge', []))
                }
                logger.info("CONTEXT AGENT: Context refined successfully (LLM)")
                return refined
            except Exception as e:
                logger.warning(f"LLM refinement failed, using fallback: {e}")

        # Fallback: rule-based refinement
        refined = self._fallback_refinement(semantic_context)
        refined['rag_context'] = {
            'patient_history_count': len(rag_context.get('patient_history', [])),
            'relevant_doctors_count': len(rag_context.get('relevant_doctors', [])),
            'knowledge_retrieved': len(rag_context.get('relevant_knowledge', []))
        }
        logger.info("CONTEXT AGENT: Context refined (fallback)")
        return refined

    # ── Private Helpers ───────────────────────────────────────────────

    def _cosine_similarity(self, vec_a: List[float], vec_b: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            return 0.0
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = sum(a * a for a in vec_a) ** 0.5
        norm_b = sum(b * b for b in vec_b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def _generate_summary_text(
        self,
        patient_uuid: str,
        all_interactions: List[dict],
        appointments: List[dict],
        symptoms: List[dict],
        follow_ups: List[dict]
    ) -> str:
        """Generate human-readable summary text."""
        if not all_interactions:
            return f"No interactions found for patient {patient_uuid[:8]}."

        parts = [f"Patient {patient_uuid[:8]} has {len(all_interactions)} total interactions."]

        if appointments:
            parts.append(f"{len(appointments)} appointment(s).")
        if symptoms:
            parts.append(f"{len(symptoms)} symptom report(s).")
        if follow_ups:
            parts.append(f"{len(follow_ups)} follow-up(s).")

        # Add recent content snippets
        if all_interactions:
            most_recent = all_interactions[0]
            parts.append(
                f"Most recent: {most_recent['metadata']['type']} - "
                f"{most_recent['metadata']['content'][:100]}"
            )

        return " ".join(parts)

    def _llm_refine(self, patient_uuid, intent, semantic_context, formatted_context, memory_context):
        """Refine context using LLM."""
        system_prompt = """You are a medical context refinement assistant.
CRITICAL RULES:
1. Work ONLY with patient UUIDs - NEVER use or generate real names
2. Base recommendations on provided medical knowledge and patient history
3. Return ONLY JSON format"""

        prompt = f"""Analyze this medical context and provide recommendations:

Patient UUID: {patient_uuid}
Intent: {intent}
Semantic Context: {json.dumps(semantic_context)}

{formatted_context}

{memory_context}

Provide JSON with:
- recommended_specialty: medical specialty needed
- recommended_doctor: doctor_id or null
- urgency_assessment: emergency/urgent/routine
- estimated_duration: minutes (integer)
- requires_follow_up: true/false
- reasoning: brief explanation"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
        response = self._groq_client.chat.completions.create(
            model=self._groq_model,
            messages=messages,
            temperature=0.3,
            max_tokens=1024
        )
        text = response.choices[0].message.content
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return json.loads(text)

    def _fallback_refinement(self, semantic_context: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback refinement without LLM."""
        return {
            'recommended_specialty': semantic_context.get('symptom_category', 'general_medicine'),
            'recommended_doctor': None,
            'urgency_assessment': semantic_context.get('urgency_level', 'routine'),
            'estimated_duration': semantic_context.get('estimated_duration', 30),
            'requires_follow_up': False,
            'reasoning': 'Fallback recommendation based on semantic context',
        }


# Also expose a ContextRefinementAgent alias for backward compatibility
class ContextRefinementAgent(ContextAgent):
    """Backward-compatible alias."""
    pass


# Global instance
context_agent = ContextAgent()
