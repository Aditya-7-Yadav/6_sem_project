import torch
import re
from sentence_transformers import SentenceTransformer, util
from transformers import pipeline
import math


class LongAnswerGrader:
    def __init__(self,
                 embed_model_name="BAAI/bge-small-en-v1.5",
                 nli_model_name="roberta-large-mnli",
                 max_marks=5):

        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        self.embed_model = SentenceTransformer(embed_model_name, device=self.device)

        self.nli = pipeline(
            "text-classification",
            model=nli_model_name,
            device=0 if self.device == "cuda" else -1,
            return_all_scores=True
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

    def _safe_nli_output(self, output):
        if isinstance(output, dict):
            return [output]
        if isinstance(output, list) and len(output) == 1 and isinstance(output[0], list):
            return output[0]
        return output

    # ---------------------------
    # Core Scores
    # ---------------------------

    def semantic_similarity(self, model_answer, student_answer):
        emb = self.embed_model.encode(
            [model_answer, student_answer],
            convert_to_tensor=True
        )
        sim = util.cos_sim(emb[0], emb[1]).item()
        return max(0.0, min(1.0, sim))

    def entailment_score(self, model_answer, student_answer):
        sentences = self._split_sentences(model_answer)
        if not sentences:
            return 0.0

        scores = []

        for sent in sentences:
            result = self.nli({
                "text": sent,
                "text_pair": student_answer
            })

            result = self._safe_nli_output(result)

            entail = 0.0
            for r in result:
                if "entail" in r["label"].lower():
                    entail = r["score"]
                    break

            scores.append(entail)

        return sum(scores) / len(scores) if scores else 0.0


    def keyword_overlap(self, student_answer, model_answer):
        student_tokens = self._tokens(student_answer)
        model_tokens = self._tokens(model_answer)

        if not model_tokens:
            return 1.0

        overlap = len(student_tokens & model_tokens)
        coverage = overlap / len(model_tokens)

        if coverage >= 0.7:
            return 1.0
        elif coverage >= 0.5:
            return 0.7
        else:
            return coverage

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

            if sim > 0.75:
                covered += 1

        return covered / len(model_sentences)

    def length_penalty(self, student_answer, model_answer):
        student_len = len(self._tokens(student_answer))
        model_len = len(self._tokens(model_answer))

        if model_len == 0:
            return 1.0

        ratio = student_len / model_len

        if ratio < 0.6:
            return 0.8
        elif ratio < 0.75:
            return 0.9
        else:
            return 1.0

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
        ent = self.entailment_score(model_answer, student_answer)
        kw = self.keyword_overlap(student_answer, model_answer)
        comp = self.completeness(student_answer, model_answer)
        length_factor = self.length_penalty(student_answer, model_answer)

        base_score = (
            0.30 * sem +
            0.30 * (ent + 0.7) +
            0.25 * comp +
            0.15 * kw
        )

        penalty = 1.0

        if sem < 0.3:
            penalty *= 0.7

        if ent < 0.025:
            penalty *= 0.1

        if comp < 0.4:
            penalty *= 0.7

        penalty *= length_factor

        final_score = base_score * penalty

        raw_marks = final_score * self.max_marks
        marks_awarded = self._round_half(raw_marks)

        return {
            "final_score": round(final_score, 3),
            "marks_awarded": marks_awarded,
            "details": {
                "semantic": round(sem, 3),
                "entailment": round(ent, 3),
                "completeness": round(comp, 3),
                "keywords": round(kw, 3),
                "length_factor": round(length_factor, 3),
                "penalty": round(penalty, 3)
            }
        }