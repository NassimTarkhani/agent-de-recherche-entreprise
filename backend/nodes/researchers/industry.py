from typing import Any, Dict

from langchain_core.messages import AIMessage

from ...classes import ResearchState
from .base import BaseResearcher


class IndustryAnalyzer(BaseResearcher):
    def __init__(self) -> None:
        super().__init__()
        self.analyst_type = "industry_analyzer"

    async def analyze(self, state: ResearchState) -> Dict[str, Any]:
        company = state.get('company', 'Unknown Company')
        industry = state.get('industry', 'Unknown Industry')
        msg = [f"🏭 Industry Analyzer analyzing {company} in {industry}"]
        
        # Generate search queries using LLM
        queries = await self.generate_queries(state, """
        Generate queries on the industry analysis of {company} in the {industry} industry such as:
        - Market position
        - Competitors
        - {industry} industry trends and challenges
        - Market size and growth
        """)

        subqueries_msg = "🔍 Subqueries for industry analysis:\n" + "\n".join([f"• {query}" for query in queries])
        messages = state.get('messages', [])
        messages.append(AIMessage(content=subqueries_msg))
        state['messages'] = messages

        # Send queries through WebSocket
        if websocket_manager := state.get('websocket_manager'):
            if job_id := state.get('job_id'):
                await websocket_manager.send_status_update(
                    job_id=job_id,
                    status="processing",
                    message="Industry analysis queries generated",
                    result={
                        "step": "Industry Analyst",
                        "analyst_type": "Industry Analyst",
                        "queries": queries
                    }
                )
        
        industry_data = {}
        
        # Include site_scrape data for industry analysis
        if site_scrape := state.get('site_scrape'):
            msg.append(f"\n📊 Including {len(site_scrape)} pages from company website...")
            industry_data.update(site_scrape)

        # Perform additional research with increased search depth
        try:
            # Store documents with their respective queries
            for query in queries:
                documents = await self.search_documents(state, [query])
                if documents:  # Only process if we got results
                    for url, doc in documents.items():
                        doc['query'] = query  # Associate each document with its query
                        industry_data[url] = doc
            
            msg.append(f"\n✓ Found {len(industry_data)} documents")
            if websocket_manager := state.get('websocket_manager'):
                if job_id := state.get('job_id'):
                    await websocket_manager.send_status_update(
                        job_id=job_id,
                        status="processing",
                        message=f"Used Tavily Search to find {len(industry_data)} documents",
                        result={
                            "step": "Searching",
                            "analyst_type": "Industry Analyst",
                            "queries": queries
                        }
                    )
        except Exception as e:
            msg.append(f"\n⚠️ Error during research: {str(e)}")
        
        # Update state with our findings
        messages = state.get('messages', [])
        messages.append(AIMessage(content="\n".join(msg)))
        state['messages'] = messages
        state['industry_data'] = industry_data
        
        return {
            'message': msg,
            'industry_data': industry_data
        }

    async def run(self, state: ResearchState) -> Dict[str, Any]:
        return await self.analyze(state) 