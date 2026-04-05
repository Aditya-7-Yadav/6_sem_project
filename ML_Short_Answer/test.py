from short_answer_grader import ShortAnswerGrader

grader = ShortAnswerGrader()

model_answer = "The break statement is used to terminate a loop immediately."
student_answer = "break stops the loop instantly."

keywords = {
    "break": ["break"],
    "loop": ["loop", "iteration"],
    "terminate": ["terminate", "stop", "end"]
}

result = grader.evaluate(student_answer, model_answer, keywords)

print(result)

#Old
# {'final_score': 0.775, 'marks_awarded': 1, 'details': {'keyword_score': 0.667, 'semantic_score': 0.889, 'entailment_score': 0.985}}
# Because we instantly is correct but not keywords we get low keyword score.

#New
# {'final_score': 0.975, 'marks_awarded': 1, 'details': {'keyword_score': 1.0, 'semantic_score': 0.889, 'entailment_score': 0.985}}
    # if 60%>= keywords used we return 1 in keywords_score