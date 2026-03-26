import torch
import re
from sentence_transformers import SentenceTransformer, util
from transformers import pipeline

# 1-0.7 -> 1 mark, 0.7-0.33-> 0.5marks
class ShortAnswerGrader:
    def __init__(self,embed_model_name="BAAI/bge-small-en-v1.5",nli_model_name="roberta-large-mnli",threshold=0.7):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        self.embed_model = SentenceTransformer(embed_model_name, device=self.device)

        self.nli = pipeline(
            "text-classification",
            model=nli_model_name,
            device=0 if self.device == "cuda" else -1,
            return_all_scores=True
        )

        self.keyword_weight = 0.6
        self.semantic_weight = 0.2
        self.entailment_weight = 0.2

        self.threshold = threshold


    def _normalize(self, text):
        return re.sub(r"\s+", " ", text.lower()).strip()

    def _keyword_score(self, student_answer, keywords):
        """
        keywords format:
        {
            "throw": ["throw", "throws", "thrown"],
            "exception": ["exception", "error"]
        }
        """
        student = self._normalize(student_answer)

        total = len(keywords)
        if total == 0:
            return 1.0

        covered = 0

        for group, synonyms in keywords.items():
            found = False
            for word in synonyms:
                if re.search(rf"\b{re.escape(word.lower())}\b", student):
                    found = True
                    break
            if found:
                covered += 1

        coverage = covered / total

        if coverage >= 0.6:
            return 1.0
        else:
            return coverage

    # BAAI/bge-small-en-v1.5
    def _semantic_score(self, student_answer, model_answer):
        emb = self.embed_model.encode(
            [student_answer, model_answer],
            convert_to_tensor=True
        )
        sim = util.cos_sim(emb[0], emb[1]).item()
        return max(0.0, min(1.0, sim))

    #NLI, Changed DeBERTa To RoBERTa keep it that way
    def _entailment_score(self, student_answer, model_answer):
        result = self.nli(
            {
                "text": student_answer,
                "text_pair": model_answer
            }
        )
        #list of dicts
        if isinstance(result, list) and isinstance(result[0], dict):
            for r in result:
                label = r["label"].lower()
                if "entail" in label:
                    return r["score"]

        #nested list
        if isinstance(result, list) and isinstance(result[0], list):
            for r in result[0]:
                label = r["label"].lower()
                if "entail" in label:
                    return r["score"]

        #single dict
        if isinstance(result, dict):
            if "entail" in result["label"].lower():
                return result["score"]

        return 0.0

    # Main evaluation function

    def evaluate(self, student_answer, model_answer, keywords):
        # Returns final score and marks for a 1-mark question.

        if not student_answer.strip():
            return {
                "final_score": 0.0,
                "marks_awarded": 0,
                "details": {}
            }

        keyword_score = self._keyword_score(student_answer, keywords)
        semantic_score = self._semantic_score(student_answer, model_answer)
        entailment_score = self._entailment_score(student_answer, model_answer)

        final_score = (
            keyword_score * self.keyword_weight +
            semantic_score * self.semantic_weight +
            entailment_score * self.entailment_weight
        )

        if final_score >= self.threshold:
            marks_awarded = 1
        elif final_score >= 0.33:
            marks_awarded = 0.5
        else:
            marks_awarded = 0

        return {
            "final_score": round(final_score, 3),
            "marks_awarded": marks_awarded,
            "details": {
                "keyword_score": round(keyword_score, 3),
                "semantic_score": round(semantic_score, 3),
                "entailment_score": round(entailment_score, 3)
            }
        }