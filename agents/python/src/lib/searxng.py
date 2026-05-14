import httpx
from typing import List, Dict, Any
from .state import Resource

async def search_searxng(query: str, max_results: int = 15) -> List[Resource]:
    """
    Search using the custom SearxNG OpenService API.
    URL: https://tciai.openservice.in.th/searxng/search
    """
    url = f"https://tciai.openservice.in.th/searxng/search"
    params = {
        "q": query,
        "format": "json"
    }
    
    resources = []
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            results = data.get("results", [])
            
            for item in results[:max_results]:
                title = item.get("title", "")
                url = item.get("url", "")
                content = item.get("content", "")
                
                # Combine snippet and content if available
                snippet = item.get("parsed_url", {}).get("netloc", "")
                full_desc = f"[{snippet}] {content}"
                
                resources.append({
                    "url": url,
                    "title": f"[SearxNG] {title}",
                    "description": full_desc,
                    "resource_type": "web",
                    "source": "searxng"
                })
    except Exception as e:
        print(f"SearxNG Search Error for query '{query}': {e}")
        
    return resources
