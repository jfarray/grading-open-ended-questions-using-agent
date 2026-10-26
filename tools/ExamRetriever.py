from mcp.server.fastmcp import FastMCP
from dataclasses import dataclass
import asyncio
from Common import (SubjectEnumModel, ExamRequestModel, ExamToGradeModel, ExamQuestionToGradeModel,
    examsPath, subjectPaths, subjectThemes, subjectTeacherGradeColumns)

import pandas as pd

mcp = FastMCP("Exam Retriever")

class ExamRetriever:
    

    def __init__(self):
        return

    # Returns questions and teacher's answers for a given subject and theme
    def getQuestionsForSubject(self, subjectId: SubjectEnumModel, theme: str) -> tuple[str, str]:
        if subjectId == SubjectEnumModel.Unknown:
            return ("", "") 
        
        # Open the file and read questions
        questionsFilePath = f"{examsPath}\\{subjectPaths[subjectId]}\\Preguntas{theme}.txt"
        try:
            fileStream = open(questionsFilePath, 'r', encoding="utf-8")
            lines = fileStream.readlines()
            question = ""
            answer = ""
            isquestion = True
            for line in lines:
                if line.strip() == "":
                    continue

                if isquestion:
                    question += line.strip() + " "
                else:
                    answer += line.strip() + " "
                
                isquestion = not isquestion
            fileStream.close()
            return (question.strip(), answer.strip())
        except FileNotFoundError:
            print(f"Questions file not found: {questionsFilePath}")
            return ("", "")
        except Exception as e:
            print(f"Error reading questions file {questionsFilePath}: {e}")
            return ("", "")
    
    # Returns student's answers for a given subject and theme
    def getSudentAnswersForSubject(self, subjectId: SubjectEnumModel, theme: str, studentId: str) -> tuple[str, str]:
        if subjectId == SubjectEnumModel.Unknown:
            return ("", "")

        # Open the file and read answers
        studentAnswersFile = f"{subjectPaths[subjectId]}_{theme}.csv"
        answersFilePath = f"{examsPath}\\{subjectPaths[subjectId]}\\{studentAnswersFile}"
        
        try:
            studentAnswers = pd.read_csv(answersFilePath,
                        sep=",", encoding="utf-8", dtype=str)
            
            studentRow = studentAnswers[studentAnswers['ID'] == studentId]
            if studentRow.empty:
                print(f"No answers found for student Dni {studentId} in file {answersFilePath}")
                return ("", "")
            answer = studentRow.iloc[0]['RespuestaEstudiante']
            try:
                teacherTotalGrade = studentRow.iloc[0][subjectTeacherGradeColumns[subjectId]]
            except KeyError:
                print(f"Teacher grade column not found for subject {subjectId}")
                teacherTotalGrade = ""
            return (answer.strip(), teacherTotalGrade.strip())
        except FileNotFoundError:
            print(f"Answers file not found: {answersFilePath}")
            return ("", "")
        except Exception as e:
            print(f"Error reading answers file {answersFilePath}: {e}")
            return ("", "")

    def getQuestionAndAnswerForSubject(self, examRequest: ExamRequestModel) -> ExamToGradeModel:

        if examRequest.subjectId == SubjectEnumModel.Unknown:
            return []
        
        questions = list[ExamQuestionToGradeModel]()
        questionId = 1
        for theme in subjectThemes[examRequest.subjectId]:
            print(f"Processing {theme} for subject {examRequest.subjectId.name}")
            (question, perfectAnswer) = self.getQuestionsForSubject(examRequest.subjectId, theme)

            # convert studentId to string for lookup
            studentIdStr = str(examRequest.studentId)
            (answer, teacherTotalGrade) = self.getSudentAnswersForSubject(examRequest.subjectId, theme, studentIdStr)

            questions.append(ExamQuestionToGradeModel(
                questionId=questionId,
                question=question,
                theme=theme,
                perfectAnswer=perfectAnswer,
                studentAnswer=answer,
                teacherGrade=float(teacherTotalGrade) if teacherTotalGrade != "" else None
            ))
            questionId += 1

            #break  # For testing, only process the first theme

        return ExamToGradeModel(
            examId=f"EXAM_{examRequest.studentId}_{examRequest.subjectId.name}",
            subjectId=examRequest.subjectId,
            studentId=examRequest.studentId,
            questions=questions
        )
        
    # Regular synchronous method
    def getExam(self, examRequest: ExamRequestModel) -> ExamToGradeModel:
        # Retrieve exam questions based on subject and themes
        return self.getQuestionAndAnswerForSubject(examRequest)

    # Async wrapper for MCP compatibility
    async def getExam_async(self, examRequest: ExamRequestModel) -> ExamToGradeModel:
        # Run the synchronous method in a thread to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.getExam, examRequest)


examRetriever = ExamRetriever()
@mcp.tool(
    name="ExamRetriever",
    title="Exam Retriever",
    description="Obtiene el exámen para la asignatura y estudiante especificados",
    structured_output=ExamToGradeModel
)
async def getExam(examRequest: ExamRequestModel) -> ExamToGradeModel:
    try:
        print(f"Received exam request: SubjectId={examRequest.subjectId}, studentId={examRequest.studentId}")
        return await examRetriever.getExam_async(examRequest)
    except Exception as e:
        print(f"Error in getExam tool: {e}")
        raise e

# For testing purposes
debug = False
if debug:
    response = examRetriever.getExam(ExamRequestModel(
        subjectId=2,
        studentId="1",
        studentName="Juan Pérez"
    ))
    print("Synchronous test result:")
    print(response)



if __name__ == "__main__":
    print("Starting Exam Retriever MCP server...")
    mcp.run()
