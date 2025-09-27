from typing import Any, Dict

from langchain_core.messages import AIMessage

from ...classes import ResearchState
from .base import BaseResearcher


class NewsScanner(BaseResearcher):
    def __init__(self) -> None:
        super().__init__()
        self.analyst_type = "news_analyzer"

    async def analyze(self, state: ResearchState) -> Dict[str, Any]:
        company = state.get('company', 'Unknown Company')
        msg = [f"📰 News Scanner analyzing {company}"]
        
        # Generate search queries using LLM
        queries = await self.generate_queries(state, """
        Generate queries on the recent news coverage of {company} such as:
        - Recent company announcements
        - Press releases
        - New partnerships
        """)

        subqueries_msg = "🔍 Subqueries for news analysis:\n" + "\n".join([f"• {query}" for query in queries])
        messages = state.get('messages', [])
        messages.append(AIMessage(content=subqueries_msg))
        state['messages'] = messages
        
        news_data = {}
        
        # Include site_scrape data for news analysis
        if site_scrape := state.get('site_scrape'):
            msg.append(f"\n📊 Including {len(site_scrape)} pages from company website...")
            news_data.update(site_scrape)

        # Perform additional research with recent time filter
        try:
            # Store documents with their respective queries
            for query in queries:
                documents = await self.search_documents(state, [query])
                if documents:  # Only process if we got results
                    for url, doc in documents.items():
                        doc['query'] = query  # Associate each document with its query
                        news_data[url] = doc
            
            msg.append(f"\n✓ Found {len(news_data)} documents")
            if websocket_manager := state.get('websocket_manager'):
                if job_id := state.get('job_id'):
                    await websocket_manager.send_status_update(
                        job_id=job_id,
                        status="processing",
                        message=f"Used Tavily Search to find {len(news_data)} documents",
                        result={
                            "step": "Searching",
                            "analyst_type": "News Scanner",
                            "queries": queries
                        }
                    )
        except Exception as e:
            msg.append(f"\n⚠️ Error during research: {str(e)}")
        
        # Update state with our findings
        messages = state.get('messages', [])
        messages.append(AIMessage(content="\n".join(msg)))
        state['messages'] = messages
        state['news_data'] = news_data
        
        return {
            'message': msg,
            'news_data': news_data
        }

    async def run(self, state: ResearchState) -> Dict[str, Any]:
        return await self.analyze(state) 