import torch
import re
from sentence_transformers import SentenceTransformer, util
from transformers import pipeline

# 1-0.7 -> 1 mark, 0.7-0.33-> 0.5marks
class ShortAnswerGrader:
    def __init__(self, embed_model_name="BAAI/bge-small-en-v1.5", nli_model_name="roberta-large-mnli", threshold=0.7):
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


def segment_short_answers(text):
    if not text:
        return []

    answers = []
    buffer = ''

    for line in text.replace('\r', '\n').split('\n'):
        trimmed = line.strip()
        if not trimmed:
            if buffer:
                answers.append(buffer.strip())
                buffer = ''
            continue

        if re.match(r'^\d+[.)]|^[a-zA-Z]\)', trimmed):
            if buffer:
                answers.append(buffer.strip())
            buffer = re.sub(r'^\d+[.)]\s*', '', trimmed)
            continue

        buffer = f"{buffer} {trimmed}" if buffer else trimmed

    if buffer:
        answers.append(buffer.strip())

    if not answers and text.strip():
        answers.append(text.strip())

    return [answer for answer in answers if answer]


def _simple_tokens(text):
    return re.findall(r'\b[a-z0-9]+\b', text.lower())


def simple_similarity(student_answer, model_answer):
    student_tokens = set(_simple_tokens(student_answer))
    model_tokens = _simple_tokens(model_answer)

    if not model_tokens:
        return 1.0 if not student_tokens else 0.3

    unique_model_tokens = set(model_tokens)
    matched = sum(1 for token in unique_model_tokens if token in student_tokens)
    coverage = matched / len(unique_model_tokens)
    length_ratio = (
        min(len(student_tokens), len(unique_model_tokens)) /
        max(len(student_tokens), len(unique_model_tokens), 1)
    )

    similarity = min(1.0, coverage * 0.7 + length_ratio * 0.3)
    return similarity


def evaluate_sections(student_text, model_text):
    student_text = student_text or ''
    model_text = model_text or ''
    student_sections = segment_short_answers(student_text)
    model_sections = segment_short_answers(model_text)

    if not student_sections:
        student_sections = ['']
    if not model_sections:
        model_sections = ['']

    per_question_scores = []
    for idx, section in enumerate(student_sections):
        reference = model_sections[idx] if idx < len(model_sections) else model_text
        similarity = simple_similarity(section, reference)
        per_question_scores.append({
            'question_index': idx + 1,
            'score': round(similarity * 100, 1),
            'feedback': (
                'Excellent alignment' if similarity >= 0.85 else
                'Add more key points to match the model answer' if similarity >= 0.5 else
                'Need to elaborate on the main concepts.'
            )
        })

    total_score = (
        sum(item['score'] for item in per_question_scores) / len(per_question_scores)
        if per_question_scores else 0
    )

    return {
        'total_score': round(total_score, 1),
        'per_question_scores': per_question_scores,
        'feedback': [item['feedback'] for item in per_question_scores],
    }
