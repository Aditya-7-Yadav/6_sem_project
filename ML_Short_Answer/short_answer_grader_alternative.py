import torch
import re
from sentence_transformers import SentenceTransformer, util
from transformers import pipeline


class ShortAnswerGrader:
    def __init__(self, embed_model_name="BAAI/bge-small-en-v1.5", threshold=0.7):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        # Embedding model
        self.embed_model = SentenceTransformer(embed_model_name, device=self.device)

        # NLI model (light but strong)
        self.nli = pipeline(
            "text-classification",
            model="MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli",
            device=0 if self.device == "cuda" else -1,
            top_k=None
        )

        self.threshold = threshold

    # ---------------------------
    # Utilities
    # ---------------------------

    def _normalize(self, text):
        return re.sub(r"\s+", " ", text.lower()).strip()

    # ---------------------------
    # Keyword Score
    # ---------------------------

    def _keyword_score(self, student_answer, keywords):
        student = self._normalize(student_answer)

        total = len(keywords)
        if total == 0:
            return 1.0

        covered = 0

        for _, synonyms in keywords.items():
            for word in synonyms:
                if re.search(rf"\b{re.escape(word.lower())}\b", student):
                    covered += 1
                    break

        coverage = covered / total
        return 1.0 if coverage >= 0.6 else coverage

    # ---------------------------
    # Semantic Similarity
    # ---------------------------

    def _semantic_score(self, student_answer, model_answer):
        emb = self.embed_model.encode(
            [student_answer, model_answer],
            convert_to_tensor=True
        )
        sim = util.cos_sim(emb[0], emb[1]).item()
        return max(0.0, min(1.0, sim))

    # ---------------------------
    # NLI Score (NEW 🔥)
    # ---------------------------

    def _nli_score(self, student_answer, model_answer):
        text = model_answer + " </s></s> " + student_answer
        result = self.nli(text)

        # Flatten output
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

    # ---------------------------
    # Main Evaluation
    # ---------------------------

    def evaluate(self, student_answer, model_answer, keywords):

        if not student_answer.strip():
            return {
                "final_score": 0.0,
                "marks_awarded": 0,
                "details": {}
            }

        keyword_score = self._keyword_score(student_answer, keywords)
        semantic_score = self._semantic_score(student_answer, model_answer)
        nli_score, contradiction = self._nli_score(student_answer, model_answer)

        # 🔥 Improved scoring (balanced)
        final_score = (
            0.4 * keyword_score +
            0.4 * semantic_score +
            0.2 * nli_score
        )

        # 🔥 Contradiction penalty
        if contradiction > 0.6:
            final_score *= 0.2

        # 🔥 Penalize very short vague answers
        if len(student_answer.split()) < 3:
            final_score *= 0.8

        # ---------------------------
        # Marks logic
        # ---------------------------

        if final_score >= 0.75:
            marks_awarded = 1
        elif final_score >= 0.45:
            marks_awarded = 0.5
        else:
            marks_awarded = 0

        return {
            "final_score": round(final_score, 3),
            "marks_awarded": marks_awarded,
            "details": {
                "keyword_score": round(keyword_score, 3),
                "semantic_score": round(semantic_score, 3),
                "nli_score": round(nli_score, 3),
                "contradiction": round(contradiction, 3)
            }
        }
