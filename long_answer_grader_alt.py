import torch
import re
from sentence_transformers import SentenceTransformer, util
from transformers import pipeline
import math


class LongAnswerGrader:
    def __init__(self,
                 embed_model_name="BAAI/bge-small-en-v1.5",
                 nli_model_name="MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli",
                 max_marks=5):

        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        self.embed_model = SentenceTransformer(embed_model_name, device=self.device)

        self.nli = pipeline(
            "text-classification",
            model=nli_model_name,
            device=0 if self.device == "cuda" else -1,
            top_k=None
        )

        self.max_marks = max_marks

    # ---------------------------
    # Utilities
    # ---------------------------

    def _tokens(self, text):
        return set(re.findall(r"\b[a-z0-9]+\b", text.lower()))

    def _split_sentences(self, text):
        return [s.strip() for s in re.split(r"[.?!]", text) if s.strip()]

    def _round_half(self, value):
        return math.ceil(value * 2) / 2

    # ---------------------------
    # Core Scores
    # ---------------------------

    def semantic_similarity(self, model_answer, student_answer):
        emb = self.embed_model.encode(
            [model_answer, student_answer],
            convert_to_tensor=True
        )
        return max(0.0, min(1.0, util.cos_sim(emb[0], emb[1]).item()))

    # 🔥 NEW: Better NLI (entailment + contradiction)
    def nli_score(self, model_answer, student_answer):
        text = model_answer + " </s></s> " + student_answer
        result = self.nli(text)

        while isinstance(result, list) and len(result) == 1:
            result = result[0]

        entail, contra = 0.0, 0.0

        for r in result:
            label = r["label"].lower()
            if "entail" in label:
                entail = r["score"]
            elif "contra" in label:
                contra = r["score"]

        return entail, contra

    # 🔥 IMPROVED keyword coverage
    def keyword_overlap(self, student_answer, model_answer):
        student_tokens = self._tokens(student_answer)
        model_tokens = self._tokens(model_answer)

        if not model_tokens:
            return 1.0

        return len(student_tokens & model_tokens) / len(model_tokens)

    # 🔥 IMPROVED completeness (concept coverage)
    def completeness(self, student_answer, model_answer):
        model_sentences = self._split_sentences(model_answer)

        if not model_sentences:
            return 1.0

        covered = 0

        for sent in model_sentences:
            emb = self.embed_model.encode(
                [sent, student_answer],
                convert_to_tensor=True
            )
            sim = util.cos_sim(emb[0], emb[1]).item()

            if sim > 0.65:  # relaxed threshold
                covered += 1

        return covered / len(model_sentences)

    def length_factor(self, student_answer, model_answer):
        student_len = len(student_answer.split())
        model_len = len(model_answer.split())

        if model_len == 0:
            return 1.0

        ratio = student_len / model_len

        if ratio < 0.4:
            return 0.6
        elif ratio < 0.7:
            return 0.85
        elif ratio <= 3:
            return 1.0
        else:
            return 0.9

    # ---------------------------
    # Final Evaluation
    # ---------------------------

    def evaluate(self, student_answer, model_answer):

        if not student_answer.strip():
            return {
                "final_score": 0,
                "marks_awarded": 0,
                "details": {}
            }

        sem = self.semantic_similarity(model_answer, student_answer)
        nli, contra = self.nli_score(model_answer, student_answer)
        kw = self.keyword_overlap(student_answer, model_answer)
        comp = self.completeness(student_answer, model_answer)
        length = self.length_factor(student_answer, model_answer)

        # 🔥 CLEAN scoring (no hacks)
        base_score = (
            0.35 * sem +
            0.25 * nli +
            0.20 * comp +
            0.20 * kw
        )

        # 🔥 Apply penalties
        if contra > 0.6:
            base_score *= 0.3

        final_score = base_score * length

        raw_marks = final_score * self.max_marks
        marks_awarded = self._round_half(raw_marks)

        return {
            "final_score": round(final_score, 3),
            "marks_awarded": marks_awarded,
            "details": {
                "semantic": round(sem, 3),
                "nli": round(nli, 3),
                "contradiction": round(contra, 3),
                "completeness": round(comp, 3),
                "keywords": round(kw, 3),
                "length_factor": round(length, 3)
            }
        }
