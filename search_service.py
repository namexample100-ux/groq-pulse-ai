import aiohttp
import logging
from config import TAVILY_API_KEY

log = logging.getLogger(__name__)

class SearchService:
    def __init__(self):
        self.api_url = "https://api.tavily.com/search"

    async def search(self, query: str, search_depth: str = "basic") -> str:
        """Поиск в интернете через Tavily API. Возвращает структурированный текст."""
        if not TAVILY_API_KEY:
            return "⚠️ Ошибка: TAVILY_API_KEY не задан."

        payload = {
            "api_key": TAVILY_API_KEY,
            "query": query,
            "search_depth": search_depth,
            "include_answer": True,
            "max_results": 5
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, json=payload, timeout=30) as response:
                    if response.status == 200:
                        data = await response.json()
                        results = data.get("results", [])
                        
                        # Формируем сводку для ИИ
                        context = "Результаты поиска:\n\n"
                        for res in results:
                            context += f"🔹 {res['title']}\nURL: {res['url']}\nContent: {res['content']}\n\n"
                        
                        return context
                    else:
                        error_text = await response.text()
                        log.error(f"Tavily API Error: {response.status} - {error_text}")
                        return f"⚠️ Ошибка поиска (Status {response.status})."
        except Exception as e:
            log.error(f"Search Exception: {e}")
            return f"⚠️ Ошибка при выполнении поиска: {str(e)}"

# Глобальный экземпляр
search_tool = SearchService()
