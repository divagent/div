from tavily import AsyncTavilyClient
from app.config import get_settings_singleton
settings = get_settings_singleton()

tavily_client = AsyncTavilyClient(api_key=settings.TAVILY_API_KEY)


async def search_web_tool(query: str):
    """
    Searches the live web for news, macro trends, and recent financial events.
    """
    try:
        # 'search_depth="advanced"' provides more detailed context for financial analysis
        search_result = await tavily_client.search(query, search_depth="advanced", max_results=3)
        
        # We clean the output so the LLM doesn't get overwhelmed with raw JSON
        results = search_result.get("results", [])
        cleaned_context = "\n\n".join([
            f"Source: {r['url']}\nContent: {r['content']}" 
            for r in results
        ])
        
        return {"data": cleaned_context}
    except Exception as e:
        return {"error": f"Web search failed: {str(e)}"}
    
   