
from enum import Enum, IntEnum
from pydantic import BaseModel
from typing import Optional

# Supported subjects and the value sent between MCP tools.
class SubjectEnumModel(IntEnum):
    Unknown = 0,
    DatabasesForBigData = 1,
    ArtificialIntelligence = 2

# Input required to retrieve a student's exam.
class ExamRequestModel(BaseModel):
    subjectId: SubjectEnumModel
    studentId: str
    studentName: Optional[str] = None

# Fields shared by every question-related result.
class ExamQuestionBaseModel(BaseModel):
    questionId: int
    theme: str

# Question data used as input to spelling and grading tools.
class ExamQuestionToGradeModel(ExamQuestionBaseModel):
    question: str
    studentAnswer: Optional[str] = None
    perfectAnswer: Optional[str] = None
    teacherGrade: Optional[float] = None

# Complete exam passed between the retrieval and analysis tools.
class ExamToGradeModel(BaseModel):
    examId: str
    subjectId: SubjectEnumModel
    studentId: str
    questions: list[ExamQuestionToGradeModel]

# LLM grading result for a single exam question.
class ExamGradedQuestionModel(ExamQuestionBaseModel):
    question: str
    studentAnswer: Optional[str] = None
    perfectAnswer: Optional[str] = None
    teacherGrade: Optional[float] = None
    llmGrade: float
    feedback: Optional[str] = None

# Collection of question-level grading results for an exam.
class ExamGradedModel(BaseModel):
    examId: str
    subjectId: SubjectEnumModel
    studentId: str
    questions: list[ExamGradedQuestionModel]

# Spelling and grammar analysis result for one question.
class ExamSpellingCheckedQuestionModel(ExamQuestionBaseModel):
    mistakes: int
    misspelled: list[str]
    suggestions: dict[str, list[str]]
    corrections_suggested: int
    corrected_text: Optional[str] = None

# Collection of spelling and grammar results for an exam.
class ExamSpellingCheckedModel(BaseModel):
    examId: str
    subjectId: SubjectEnumModel
    studentId: str
    questions: list[ExamSpellingCheckedQuestionModel]

# LLM providers/models supported by the grading experiment.
class LLMEnumModel(Enum):
    Cohere = "command-a-reasoning-08-2025"
    Llama = "llama3.1"

# Weight assigned to a theme when calculating the final grade.
class finalGradeRubricQuestionModel(BaseModel):
    theme: str
    percentageWeight: float

# Complete grading rubric for a subject.
class finalGradeRubricModel(BaseModel):
    questions : list[finalGradeRubricQuestionModel]
    misspellingPenaltyPerMistake: Optional[float] = 0.0

# Final grade returned for an exam.
class finalGradedModel(BaseModel):
    examId: str
    subjectId: SubjectEnumModel
    studentId: str
    finalGrade: float


# Generic constants
examsPath = r"..\DataSet\ResultadosPLENTAS_anonimizado_consentimiento"
subjectPaths = {
    SubjectEnumModel.ArtificialIntelligence: "InteligenciaArtificialeIngenieriaDelConocimiento_GII",
    SubjectEnumModel.DatabasesForBigData: "BasesdeDatosparaelBigData_MAV"
}
subjectThemes = {
    SubjectEnumModel.ArtificialIntelligence: ["Tema2", "Tema4", "Tema6", "Tema8"],
    SubjectEnumModel.DatabasesForBigData: ["Tema5", "Tema6", "Tema7", "Tema9", "Tema10"]
}
subjectTeacherGradeColumns = {
    SubjectEnumModel.ArtificialIntelligence: "NotaFinal (sobre 10)",
    SubjectEnumModel.DatabasesForBigData: "NotaDelProfesor"
}
subjectCourseMaterialsPaths = {
    SubjectEnumModel.ArtificialIntelligence: r"..\DataSet\TemasInteligenciaArtificial\pdfs",
    SubjectEnumModel.DatabasesForBigData: r"..\DataSet\TemasBasesdeDatosBigData"
}