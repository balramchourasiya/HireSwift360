import logging
import math
import os
import re
from collections import Counter
from functools import lru_cache

logger = logging.getLogger(__name__)

_TOKEN_PATTERN = re.compile(r"(?u)\b\w\w+\b")
_STOP_WORDS = frozenset({
    "a", "about", "above", "after", "again", "against", "all", "am", "an",
    "and", "any", "are", "as", "at", "be", "because", "been", "before",
    "being", "below", "between", "both", "but", "by", "can", "could", "did",
    "do", "does", "doing", "down", "during", "each", "few", "for", "from",
    "further", "had", "has", "have", "having", "he", "her", "here", "hers",
    "him", "his", "how", "i", "if", "in", "into", "is", "it", "its", "me",
    "more", "most", "my", "no", "nor", "not", "of", "off", "on", "once",
    "only", "or", "other", "our", "out", "over", "own", "same", "she",
    "should", "so", "some", "such", "than", "that", "the", "their", "them",
    "then", "there", "these", "they", "this", "those", "through", "to",
    "too", "under", "until", "up", "very", "was", "we", "were", "what",
    "when", "where", "which", "while", "who", "whom", "why", "will", "with",
    "would", "you", "your",
})


def _tfidf_similarity(candidate_text: str, job_text: str) -> float:
    documents = []
    for text in (candidate_text, job_text):
        tokens = [token for token in _TOKEN_PATTERN.findall(text.lower()) if token not in _STOP_WORDS]
        documents.append(Counter(
            tokens[index] if size == 1 else f"{tokens[index]} {tokens[index + 1]}"
            for size in (1, 2)
            for index in range(len(tokens) - size + 1)
        ))

    vocabulary = set(documents[0]) | set(documents[1])
    if not vocabulary:
        return 0.0
    if len(vocabulary) > 12000:
        vocabulary = set(sorted(vocabulary, key=lambda term: (
            documents[0][term] + documents[1][term], term
        ), reverse=True)[:12000])

    vectors = []
    for document in documents:
        weights = {
            term: count * (math.log(3 / (1 + sum(term in doc for doc in documents))) + 1)
            for term, count in document.items()
            if term in vocabulary
        }
        norm = math.sqrt(sum(weight * weight for weight in weights.values()))
        vectors.append({term: weight / norm for term, weight in weights.items()} if norm else {})

    return sum(weight * vectors[1].get(term, 0.0) for term, weight in vectors[0].items())

ALIASES = {"embedded c": ["embedded c", "firmware c", "embedded systems"], "rtos": ["rtos", "real time operating system"],
           "microcontrollers": ["microcontroller", "microcontrollers", "mcu"], "c++": ["c++", "cpp"],
           "postgresql": ["postgresql", "postgres", "pgsql"], "javascript": ["javascript", "js"]}

@lru_cache(maxsize=1)
def _embedding_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"))

def semantic_similarity(candidate_text: str, job_text: str) -> tuple[float, str]:
    """Use sentence-transformer embeddings when enabled; otherwise use local TF-IDF similarity."""
    if not candidate_text.strip() or not job_text.strip():
        return 0.0, "Local TF-IDF text similarity"
    if os.getenv("USE_SENTENCE_TRANSFORMERS", "false").lower() == "true":
        try:
            model = _embedding_model()
            vectors = model.encode([candidate_text[:50000], job_text[:20000]], normalize_embeddings=True)
            return round(float(vectors[0] @ vectors[1]) * 100, 1), "SentenceTransformer embeddings"
        except Exception:
            logger.warning(
                "Sentence-transformer matching failed; falling back to local TF-IDF.",
                exc_info=True,
            )
            return round(_tfidf_similarity(candidate_text, job_text) * 100, 1), (
                "Local TF-IDF fallback (sentence-transformer unavailable)"
            )
    return round(_tfidf_similarity(candidate_text, job_text) * 100, 1), "Local TF-IDF text similarity"

def score_candidate(candidate, job):
    required = [s.strip() for s in (job.required_skills or []) if s.strip()]
    skills = [s.lower() for s in (candidate.skills or [])]
    text = (candidate.resume_text or "").lower()
    matched, missing, evidence = [], [], {}
    for skill in required:
        variants = ALIASES.get(skill.lower(), [skill.lower()])
        found = next((v for v in variants if v in skills or re.search(r"(?<![a-z0-9+#.])" + re.escape(v) + r"(?![a-z0-9+#.])", text)), None)
        if found:
            matched.append(skill)
            pos = text.find(found)
            evidence[skill] = (candidate.resume_text[max(0, pos-65):pos+len(found)+100].replace("\n", " ") if pos >= 0 else "Skill listed in extracted profile")
        else: missing.append(skill)
    skill_score = (len(matched) / len(required) * 100) if required else 70.0
    exp_score = 100.0 if job.min_experience <= 0 else min(100.0, candidate.experience_years / job.min_experience * 100)
    education_checks = []
    for value, minimum in [(candidate.tenth_percentage, job.min_10th), (candidate.twelfth_percentage, job.min_12th), (candidate.cgpa, job.min_cgpa)]:
        if minimum is not None: education_checks.append(100.0 if value is not None and value >= minimum else (0.0 if value is not None else 50.0))
    education_score = sum(education_checks) / len(education_checks) if education_checks else 70.0
    semantic, semantic_method = semantic_similarity(
        (candidate.resume_text or "")[:50000],
        ((job.title or "") + " " + (job.description or ""))[:20000],
    )
    weights = {"skills": .45, "experience": .20, "education": .10, "semantic_relevance": .25}
    total = round(skill_score*weights["skills"] + exp_score*weights["experience"] + education_score*weights["education"] + semantic*weights["semantic_relevance"], 1)
    breakdown = {"skills": round(skill_score,1), "experience": round(exp_score,1), "education": round(education_score,1),
                 "semantic_relevance": semantic, "weights": weights, "evidence": evidence,
                 "method": f"{semantic_method} + explicit criteria",
                 "note": "Decision-support only. Review cited resume evidence; scores are not probabilities or hiring decisions."}
    return total, breakdown, matched, missing
