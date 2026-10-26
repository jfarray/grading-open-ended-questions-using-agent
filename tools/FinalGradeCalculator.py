from mcp.server.fastmcp import FastMCP
import asyncio

from Common import ExamGradedModel, ExamGradedQuestionModel, ExamSpellingCheckedQuestionModel, ExamToGradeModel, ExamSpellingCheckedModel, finalGradeRubricModel, finalGradeRubricQuestionModel, finalGradedModel

mcp = FastMCP("Final Grade Calculator")

class FinalGradeCalculator:
    def __init__(self):
        return
    
    def getRubricForSubject(self, subjectId: int) -> finalGradeRubricModel:
        # For simplicity, we return a hardcoded rubric. In a real implementation, this could be retrieved from a database or file.
        if subjectId == 1:  # DatabasesForBigData
            return finalGradeRubricModel(
                questions=[
                    finalGradeRubricQuestionModel(theme="Tema5", percentageWeight=0.20),
                    finalGradeRubricQuestionModel(theme="Tema6", percentageWeight=0.20),
                    finalGradeRubricQuestionModel(theme="Tema7", percentageWeight=0.20),
                    finalGradeRubricQuestionModel(theme="Tema9", percentageWeight=0.20),
                    finalGradeRubricQuestionModel(theme="Tema10", percentageWeight=0.20)
                ],
                misspellingPenaltyPerMistake=0.5
            )
        elif subjectId == 2:  # ArtificialIntelligence
            return finalGradeRubricModel(
                questions=[
                    finalGradeRubricQuestionModel(theme="Tema2", percentageWeight=0.20),
                    finalGradeRubricQuestionModel(theme="Tema4", percentageWeight=0.30),
                    finalGradeRubricQuestionModel(theme="Tema6", percentageWeight=0.20),
                    finalGradeRubricQuestionModel(theme="Tema8", percentageWeight=0.30)
                ],
                misspellingPenaltyPerMistake=0.5
            )
        else:
            return finalGradeRubricModel(questions=[], misspellingPenaltyPerMistake=0.5)

    # Regular synchronous method
    def gradeQuestion(self, 
        questionRubric: finalGradeRubricQuestionModel, 
        questionGraded: ExamGradedQuestionModel,
        questionSpellingChecked: ExamSpellingCheckedQuestionModel | None,
        misspellingPenaltyPerMistake: float) -> float:
        
        # calculate the spelling errors penalty
        spellingPenalty = (
            questionSpellingChecked.mistakes * misspellingPenaltyPerMistake
            if questionSpellingChecked else 0.0
        )

        # calculate the final grade for the question
        grade = (questionGraded.llmGrade * questionRubric.percentageWeight) - spellingPenalty
        
        # apply penalty. Ensure grade is not negative
        return grade if grade >= 0 else 0.0

    def gradeExam(self, 
            examGraded: ExamGradedModel,
            examSpellingChecked: ExamSpellingCheckedModel) -> float:
        
        # Get the grading rubric for the subject
        examRubric = self.getRubricForSubject(examGraded.subjectId)

        totalGrade = 0.0
        for questionRubric in examRubric.questions:
            # find the corresponding graded question and spelling checked question
            questionGraded = next((q for q in examGraded.questions if q.theme == questionRubric.theme), None)
            questionSpellingChecked = next((q for q in examSpellingChecked.questions if q.theme == questionRubric.theme), None)    

            if questionGraded is None:
                raise ValueError(f"No hay calificación para la pregunta del tema {questionRubric.theme}.")

            totalGrade += self.gradeQuestion(
                questionRubric,
                questionGraded,
                questionSpellingChecked,
                examRubric.misspellingPenaltyPerMistake or 0.0
            )

        return round(max(0.0, min(10.0, totalGrade)), 2)

    # Async wrapper for MCP compatibility
    async def grade_async(self, 
        examGraded: ExamGradedModel,
        examSpellingChecked: ExamSpellingCheckedModel) -> float:

        # Run the synchronous method in a thread to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.gradeExam, examGraded, examSpellingChecked)
    

finalGradeCalculator = FinalGradeCalculator()
@mcp.tool(
    name="finalGradeCalculator",
    title="Final Grade Calculator",
    description="Calcula la calificación final del examen",
    structured_output=finalGradedModel
)
async def grade(examGraded: ExamGradedModel,
            examSpellingChecked: ExamSpellingCheckedModel) -> finalGradedModel:
    finalGrade = await finalGradeCalculator.grade_async(examGraded, examSpellingChecked)
    return finalGradedModel(
        examId=examGraded.examId,
        subjectId=examGraded.subjectId,
        studentId=examGraded.studentId,
        finalGrade=finalGrade
    )

if __name__ == "__main__":
    # Test the tool synchronously
    #result = analyzer.analyze("Este es un texo de pruba con erores ortográfico y gramaticales.")
    #print("Synchronous test result:")
    #print(result)

    print("Starting Final Grade Calculator MCP server...")
    mcp.run()
    print("Server stopped.")
