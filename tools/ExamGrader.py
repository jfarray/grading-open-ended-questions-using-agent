from collections import defaultdict
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from langchain_cohere import ChatCohere
from langchain_community.llms import Cohere, Ollama
from langchain_core.prompts import PromptTemplate, ChatPromptTemplate, SystemMessagePromptTemplate
from langchain_classic.retrievers import MultiQueryRetriever, ContextualCompressionRetriever
from langchain_classic.retrievers.document_compressors import LLMChainFilter
from langchain_classic.chains import create_retrieval_chain
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_community.document_loaders import DirectoryLoader, PyPDFLoader
from langchain_community.vectorstores import Chroma, FAISS
#from langchain_community.embeddings import CohereEmbeddings
from langchain_cohere import CohereEmbeddings
from langchain_core.output_parsers import StrOutputParser
#from langchain_classic.embeddings import HuggingFaceEmbeddings, OllamaEmbeddings
from langchain_community.embeddings import HuggingFaceEmbeddings

from mcp.server.fastmcp import FastMCP
from dataclasses import dataclass
import asyncio
from Common import (ExamGradedModel, ExamGradedQuestionModel, ExamQuestionToGradeModel, ExamToGradeModel, SubjectEnumModel, LLMEnumModel,
                    subjectThemes, subjectCourseMaterialsPaths)
from config.settings import settings

mcp = FastMCP("Exam Grader")

class ExamGrader:
    def __init__(self, llmType: LLMEnumModel = LLMEnumModel.Cohere):
        self.llm_type = llmType
        self.retrieval_type = "MultiQuery"
        documentsPath = subjectCourseMaterialsPaths[SubjectEnumModel.ArtificialIntelligence]

        if settings.exam_grader_mode == "llm":
            self.PrepareLLMAndRetrievals(llmType, documentsPath, self.retrieval_type)

    # Prepares a retraival chain for all subjects and each Theme separately
    def PrepareLLMAndRetrievals(self, llmType: LLMEnumModel, documentsPath: str, retrievalType: str="SingleQuery"):
        print(f"{ExamGrader.__name__}: Preparing LLM and Retrievals...")
        self.retrievals = defaultdict(dict) # subject -> theme -> components
        isASingleFile = True

        for subjectId in SubjectEnumModel:
            if subjectId == SubjectEnumModel.Unknown:
                continue
            documentsPath = subjectCourseMaterialsPaths[subjectId]

            for theme in subjectThemes[subjectId]:
                themePath = f"{documentsPath}\\{theme}.pdf"
                print(themePath)
        
                if (llmType == LLMEnumModel.Cohere):
                    retriever, llmChain, retrievalLlmChain = self.PrepareLLMAndRetrieval_Cohere(themePath, isASingleFile, retrievalType)
                elif (llmType == LLMEnumModel.Llama):
                    retriever, llmChain, retrievalLlmChain = self.PrepareLLMAndRetrieval_Llama(themePath, isASingleFile, retrievalType)
                else:
                    raise ValueError("Unsupported LLM type")
                
                # Store the retriever and chains for later use
                self.retrievals[subjectId][theme] = {
                    "retriever": retriever,
                    "llmChain": llmChain,
                    "retrievalLlmChain": retrievalLlmChain,
                }

                # TODO: Delete
                # break  # For testing, only process the first theme

    def PrepareLLMAndRetrieval_Cohere(self,documentsPath: str, isASingleFile: bool, retrievalType: str="SingleQuery"):
        api_key = settings.cohere_api_key
        modelName = LLMEnumModel.Cohere.value
        chatLlm = ChatCohere(model=modelName, cohere_api_key=api_key, temperature=0.5)

        # Define the chat prompt template
        systemMessage = SystemMessagePromptTemplate.from_template("""
        Atendiendo solamente al contexto proporcionado, ¿Que nota entre 0 y 10 tendría el alumno a la pregunta de examen {question}?\n
        El contexto proporcionado es el siguiente:
        <context>{context}</context>
                                                                
        Responda solamente con la nota redondeada a 2 decimales. No se requiere justificación.
        """)

        chat_template = ChatPromptTemplate.from_messages(
            [
                systemMessage,
                ("human", "La respuesta del alumno es: {input}")
            ]
        )

        # Load the documents
        if isASingleFile:
            loader = PyPDFLoader(documentsPath)
        else:
            loader = DirectoryLoader(documentsPath, glob="**/*.pdf", loader_cls=PyPDFLoader)
        docs =  loader.load_and_split()
    
        # Create the vector store
        embeddings = CohereEmbeddings(cohere_api_key=api_key, model="embed-v4.0")
        vector = FAISS.from_documents(docs, embeddings)

        # Create the retrieval chain
        document_chain = create_stuff_documents_chain(chatLlm, chat_template, output_parser=StrOutputParser())
        if retrievalType == "SingleQuery":
            retriever = vector.as_retriever()
        elif retrievalType == "MultiQuery":
            retriever = MultiQueryRetriever.from_llm(retriever=vector.as_retriever(), llm=chatLlm)
        elif retrievalType == "ContextualCompressionRetriever":
            filterPrompt = PromptTemplate.from_template("¿Is the context <context>{context}</context> relevant to the question \"{question}\"?. Response Yes or No")
            _filter = LLMChainFilter.from_llm(chatLlm,filterPrompt)
            retriever = ContextualCompressionRetriever(
                base_compressor=_filter, base_retriever=vector.as_retriever()
            )

        retrieval_chain = create_retrieval_chain(retriever, document_chain)
        #return retrieval_chain | StrOutputParser()
        return (retriever, chat_template | chatLlm | StrOutputParser(), retrieval_chain)

    def PrepareLLMAndRetrieval_Llama(self, documentsPath: str, isASingleFile: bool, retrievalType: str="SingleQuery"):
        modelName = LLMEnumModel.Llama.value
        chatLlm = Ollama(model=modelName, stop=["<|eot_id|>"], temperature=0.5)

        # Define the chat prompt template
        systemTemplate = """
        Eres un profesor que tiene que corregir preguntas de exámenes.
        Responda con la frase "La puntuación es: " seguida de la puntuación obtenida por el alumno entre 0 y 10 redondeada a 2 decimales.
        La puntuación es 0 cuando la respuesta es totalmente incorrecta y 10 cuando es perfecta.
        La pregunta a corregir es: 
        "{question}"
        Para poner la puntuación debes tener solamente en cuenta el siguiente temario:
        {context}
        """

        template = f"""
        <|begin_of_text|>
        <|start_header_id|>system<|end_header_id|>
        "{systemTemplate}"
        <|eot_id|>
        <|start_header_id|>user<|end_header_id|>
        Responda con la frase "La puntuación es: " seguida de la puntuación obtenida por el alumno entre 0 y 10 redondeada a 2 decimales.
        La respuesta del alumno que tienes que corregir es: "{{input}}"
        <|eot_id|>
        <|start_header_id|>assistant<|end_header_id|>
        """

        # Added prompt template
        prompt = PromptTemplate(
            input_variables=["question", "input"],
            template=template
        )

        # Load the documents
        if isASingleFile:
            loader = PyPDFLoader(documentsPath)
        else:
            loader = DirectoryLoader(documentsPath, glob="**/*.pdf", loader_cls=PyPDFLoader)
        docs =  loader.load_and_split()
    
        # Create the vector store
        # OllamaEmbedings
        #LlamaEmbeddings = OllamaEmbeddings(model="Llama:text")
        # HuggingFaceEmbeddings
        LlamaEmbeddingsModelId = "sentence-transformers/all-mpnet-base-v2"
        LlamaEmbeddings = HuggingFaceEmbeddings(model_name=LlamaEmbeddingsModelId)
        vector = Chroma.from_documents(documents=docs, embedding=LlamaEmbeddings, persist_directory="chroma_db_Llama")
        
        # Create the retrieval chain
        document_chain = create_stuff_documents_chain(chatLlm, prompt, output_parser=StrOutputParser())
        if retrievalType == "SingleQuery":
            retriever = vector.as_retriever()
        elif retrievalType == "MultiQuery":
            retriever = MultiQueryRetriever.from_llm(retriever=vector.as_retriever(), llm=chatLlm)
        elif retrievalType == "ContextualCompressionRetriever":
            filterPrompt = PromptTemplate.from_template("¿Is the context <context>{context}</context> relevant to the question \"{question}\"?. Response Yes or No")
            _filter = LLMChainFilter.from_llm(chatLlm,filterPrompt)
            retriever = ContextualCompressionRetriever(
                base_compressor=_filter, base_retriever=vector.as_retriever()
            )

        retrieval_chain = create_retrieval_chain(retriever, document_chain)
        return (retriever, prompt | chatLlm | StrOutputParser(), retrieval_chain)

    def getGradeFromLlmResponse(self, response: str) -> float:
        # Extract the grade from the LLM response
        try:
            prefix = "La puntuación es: "
            if prefix in response:
                gradeStr = response.split(prefix)[1].strip()
                grade = float(gradeStr)
                return grade
            else:
                print(f"Unexpected response format: {response}")
                return 0.11
        except Exception as e:
            print(f"Error extracting grade from response '{response}': {e}")
            return 0.22
        
    def gradeExam(self, exam: ExamToGradeModel) -> ExamGradedModel:
        questions = list[ExamGradedQuestionModel]()
        for i in range(len(exam.questions)):
            questionModel: ExamQuestionToGradeModel = exam.questions[i]
            question = questionModel.question
            correctAnswer = questionModel.perfectAnswer.strip().lower()
            studentAnswer = questionModel.studentAnswer.strip().lower()

            # Use the retrieval chain to get the grade
            retrievalLlmChain = self.retrievals[exam.subjectId][questionModel.theme]["retrievalLlmChain"]
            response = retrievalLlmChain.invoke(
                {"question": question, 
                 "input": studentAnswer}
            )
            llmGradeResponse = response["answer"]
            print(f"Grading question {questionModel.questionId}: Response from LLM: {llmGradeResponse}")
            llmGrade = self.getGradeFromLlmResponse(llmGradeResponse)

            questions.append(ExamGradedQuestionModel(
                questionId=questionModel.questionId,
                question=questionModel.question,
                theme=questionModel.theme,
                perfectAnswer=questionModel.perfectAnswer,
                studentAnswer=questionModel.studentAnswer,
                teacherGrade=questionModel.teacherGrade,
                llmGrade=llmGrade,
                feedback=None
            ))
        
        return ExamGradedModel(
            examId=exam.examId,
            subjectId=exam.subjectId,
            studentId=exam.studentId,
            questions=questions
        )
    
    def gradeExamTest(self, exam: ExamToGradeModel) -> ExamGradedModel:
        if not exam.questions:
            raise ValueError("Cannot grade an exam without questions.")

        questions = list[ExamGradedQuestionModel]()
        for i in range(len(exam.questions)):
            questionModel: ExamQuestionToGradeModel = exam.questions[i]
            question = questionModel.question
            studentAnswer = questionModel.studentAnswer.strip().lower()
            # For testing, assign a grade based on a random number from 0 to 10
            llmGrade = round((i+1) * 10 / len(exam.questions), 2)

            questions.append(ExamGradedQuestionModel(
                questionId=questionModel.questionId,
                question=questionModel.question,
                theme=questionModel.theme,
                perfectAnswer=questionModel.perfectAnswer,
                studentAnswer=questionModel.studentAnswer,
                teacherGrade=questionModel.teacherGrade,
                llmGrade=llmGrade,
                feedback=None
            ))
        
        return ExamGradedModel(
            examId=exam.examId,
            subjectId=exam.subjectId,
            studentId=exam.studentId,
            questions=questions
        )
    
    # Async wrapper for MCP compatibility
    async def gradeExam_async(self, examRequest: ExamToGradeModel) -> ExamGradedModel:
        # Run the synchronous method in a thread to avoid blocking
        loop = asyncio.get_event_loop()
        grader = self.gradeExam if settings.exam_grader_mode == "llm" else self.gradeExamTest
        response = await loop.run_in_executor(None, grader, examRequest)
        return response
        
    
examGrader = ExamGrader(llmType = LLMEnumModel.Llama)
@mcp.tool(
    name="ExamGrader",
    title="Exam Grader",
    description="Corrige cada pregunta del examen proporcionado y devuelve las calificaciones." \
    "Recibe las preguntas, respuestas perfectas y respuestas del estudiante.",
    structured_output=ExamGradedModel
)
async def gradeExam(examRequest: ExamToGradeModel):
    return await examGrader.gradeExam_async(examRequest)

# For testing purposes
debug = False
if debug:
    response = examGrader.gradeExam(ExamToGradeModel(
        examId="EXAM123",
        subjectId=SubjectEnumModel.ArtificialIntelligence,
        studentId="1",
        questions=[
            ExamQuestionToGradeModel(
                questionId=1,
                question="¿A qué familia de algoritmos pertenece el algoritmo A*? ¿Qué diferencia fundamental existe entre este algoritmo y los algoritmos de búsqueda en anchura o de búsqueda en profundidad? ¿Qué considera A* para evaluar un nodo? ¿Cuándo es óptimo el algoritmo y qué condición se tiene que dar en todos los estados del problema para que sea óptimo?",
                theme="Tema2",
                perfectAnswer="The capital is Madrid.",
                studentAnswer="pertenece a la familia de algoritmos de búsqueda informada.  la principal diferencia es que este algoritmo se basa en información heurística para llegar antes y más eficientemente al resultado. por otro lado las búsquedas en anchura  o en profundidad recorren el árbol de diferentes maneras sin tener en cuenta otra información hasta que llegan a la solución.  para evaluar el nodo a* considera g(n), el costo hasta el nodo actual mas una estimación hasta el nodo objetivo h(n).  se considerara que  es optimo el algoritmo si cumple  la condición de admisibilidad, la ruta más corta hasta nodo objetivo y la condicion de consistencia que indica que la estimación no superará el costo real hasta el objetivo. en el caso de que se cumpla la condición de consistencia en todos los pasos hasta la solución  se considerará que el problema es óptimo.",
                teacherGrade=10.0
            ),
            ExamQuestionToGradeModel(
                questionId=2,
                question="¿A qué familia de algoritmos pertenece el algoritmo A*? ¿Qué diferencia fundamental existe entre este algoritmo y los algoritmos de búsqueda en anchura o de búsqueda en profundidad? ¿Qué considera A* para evaluar un nodo? ¿Cuándo es óptimo el algoritmo y qué condición se tiene que dar en todos los estados del problema para que sea óptimo?",
                theme="Tema2",
                perfectAnswer="The current president is Pedro Sánchez.",
                studentAnswer="el algoritmo a* es un algoritmo perteneciente a la familia de algoritmos de búsqueda, que es utilizado para calcular el recorrido mínimo entre dos puntos de un grafo ponderado.  un ejemplo común mente usado es en las aplicaciones de viajes, en donde se debe ir desde un punto a hacia un punto b pasando por diversas calles con varias cuadras (pesos) y sentido.  la diferencia fundamental con los algoritmos de búsqueda en anchura (bfs) o en profundidad (dfs) es que en cada estado se emplea una función heurística para determinar el candidato con el menor recorrido hacia el nodo meta. dicha función depende de la naturaleza del problema, pero por dar un ejemplo, podría utilizarse la distancia euclidiana entre dos puntos.  el algoritmo se considera óptimo cuando se garantiza siempre el menor recorrido entre el nodo inicial y el nodo meta. para ello, el valor heurístico de cada estado debe garantizar siempre el recorrido mínimo hacia el nodo meta.",
                teacherGrade=10.0
            )
        ]
    ))
    print("Synchronous test result:")
    print(response)


if __name__ == "__main__":
    print("Starting Exam Grader MCP server...")
    mcp.run()
