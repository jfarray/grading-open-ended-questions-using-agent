from mcp.server.fastmcp import FastMCP
import language_tool_python
import asyncio

from Common import ExamQuestionToGradeModel, ExamSpellingCheckedQuestionModel, ExamToGradeModel, ExamSpellingCheckedModel

mcp = FastMCP("Spelling and Grammar Checker")

class SpellingGrammarAnalyzer:
    def __init__(self, grammarCheckerLanguage='es-ES'):
        self.grammar_tool = language_tool_python.LanguageTool(grammarCheckerLanguage)

    def analyzeAnswer(self, question: ExamQuestionToGradeModel) -> ExamSpellingCheckedQuestionModel:
        text = question.studentAnswer or ""

        matches = self.grammar_tool.check(text)

        errors = []
        misspelled = []
        suggestions = {}

        for m in matches:
            error_text = text[m.offset:m.offset + m.errorLength]

            # Filtrar solo errores reales (no estilo)
            if m.ruleIssueType in ("misspelling", "grammar"):
                errors.append({
                    "text": error_text,
                    "message": m.message,
                    "suggestions": m.replacements
                })

                # Mantener compatibilidad con tu modelo antiguo
                if m.ruleIssueType == "misspelling":
                    misspelled.append(error_text)
                    suggestions[error_text] = m.replacements

        corrected_text = language_tool_python.utils.correct(text, matches)

        return ExamSpellingCheckedQuestionModel(
            questionId=question.questionId,
            theme=question.theme,
            mistakes=len(errors),
            misspelled=misspelled,
            suggestions=suggestions,
            corrections_suggested=len(matches),
            corrected_text=corrected_text
        )
    
    def analyze(self, examRequest: ExamToGradeModel) -> ExamSpellingCheckedModel:

        result = ExamSpellingCheckedModel(
            examId=examRequest.examId,
            subjectId=examRequest.subjectId,
            studentId=examRequest.studentId,
            questions=[]
        )

        for question in examRequest.questions:
            if question.studentAnswer:
                answerResult = self.analyzeAnswer(question)
                result.questions.append(answerResult)

        return result

    # Async wrapper for MCP compatibility
    async def analyze_async(self, examRequest: ExamToGradeModel):
        # Run the synchronous method in a thread to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.analyze, examRequest)
    

spanishAnalyzer = SpellingGrammarAnalyzer(grammarCheckerLanguage='es-ES')
@mcp.tool(
    name="spellGrammarAnalyzer",
    title="Spell and Grammar Analyzer",
    description="Analiza ortografía y gramática del examen proporcionado",
    structured_output=ExamSpellingCheckedModel
)
async def analyze(examRequest: ExamToGradeModel) -> ExamSpellingCheckedModel:
    return await spanishAnalyzer.analyze_async(examRequest)

debug = False
if debug:
    # Test the tool synchronously
    examRequest = ExamToGradeModel(
        examId="EXAM_1_2",
        subjectId=2,
        studentId="1",
        questions=[
            ExamQuestionToGradeModel(
                questionId=1,
                theme="Tema 1",
                question="",
                studentAnswer="el algoritmo a* es un algoritmo perteneciente a la familia de algoritmos de búsqueda, que es utilizado para calcular el recorrido mínimo entre dos puntos de un grafo ponderado.  un ejemplo común mente usado es en las aplicaciones de viajes, en donde se debe ir desde un punto a hacia un punto b pasando por diversas calles con varias cuadras (pesos) y sentido.  la diferencia fundamental con los algoritmos de búsqueda en anchura (bfs) o en profundidad (dfs) es que en cada estado se emplea una función heurística para determinar el candidato con el menor recorrido hacia el nodo meta. dicha función depende de la naturaleza del problema, pero por dar un ejemplo, podría utilizarse la distancia euclidiana entre dos puntos.  el algoritmo se considera óptimo cuando se garantiza siempre el menor recorrido entre el nodo inicial y el nodo meta. para ello, el valor heurístico de cada estado debe garantizar siempre el recorrido mínimo hacia el nodo meta.",
                #studentAnswer="Diría que depende del momento.",
                perfectAnswer="",
                teacherGrade=10.0
            )
        ]
    )
    result = spanishAnalyzer.analyze(examRequest)
    print("Synchronous test result:")
    print(result)

if __name__ == "__main__":
    # Test the tool synchronously
    #result = analyzer.analyze("Este es un texo de pruba con erores ortográfico y gramaticales.")
    #print("Synchronous test result:")
    #print(result)

    print("Starting Spelling and Grammar Checker MCP server...")
    mcp.run()
    print("Server stopped.")
