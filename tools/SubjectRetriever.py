from mcp.server.fastmcp import FastMCP
import asyncio
from Common import SubjectEnumModel

mcp = FastMCP("Subject Retriever")

class SubjectRetriever:
    def __init__(self):
        return

    # Regular synchronous method
    def getSubject(self, text: str) -> str:
        textLower = text.lower()
        if "inteligencia artificial" in textLower or "artificial intelligence" in textLower:
            return  SubjectEnumModel.ArtificialIntelligence
        elif "bases de datos" in textLower or "databases" in textLower:
            return SubjectEnumModel.DatabasesForBigData
        else:
            return SubjectEnumModel.Unknown
        

    # Async wrapper for MCP compatibility
    async def getSubject_async(self, text: str):
        # Run the synchronous method in a thread to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.getSubject, text)


subjectRetriever = SubjectRetriever()
@mcp.tool(
    name="subjectRetriever",
    title="Subject Retriever",
    description="Identifica y devuelve la asignatura principal del prompt proporcionado",
    structured_output= SubjectEnumModel
)
async def analyze(text: str):
    return await subjectRetriever.getSubject_async(text)

if __name__ == "__main__":
    # Test the tool synchronously
    #result = analyzer.analyze("Este es un texo de pruba con erores ortográfico y gramaticales.")
    #print("Synchronous test result:")
    #print(result)

    print("Starting Subject Retriever MCP server...")
    mcp.run()
    print("Server stopped.")
