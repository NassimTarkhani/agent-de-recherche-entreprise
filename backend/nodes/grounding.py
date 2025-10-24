import logging
import os

from langchain_core.messages import AIMessage
from tavily import AsyncTavilyClient

from ..classes import InputState, ResearchState

logger = logging.getLogger(__name__)

class GroundingNode:
    """Collecte des données initiales de référence sur l’entreprise."""
    
    def __init__(self) -> None:
        self.tavily_client = AsyncTavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

    async def initial_search(self, state: InputState) -> ResearchState:
        # Ajouter des logs de débogage pour vérifier le gestionnaire WebSocket
        if websocket_manager := state.get('websocket_manager'):
            logger.info("Gestionnaire WebSocket trouvé dans l’état")
        else:
            logger.warning("Aucun gestionnaire WebSocket trouvé dans l’état")
        
        company = state.get('company', 'Entreprise inconnue')
        msg = f"🎯 Démarrage de la recherche pour {company}...\n"
        
        if websocket_manager := state.get('websocket_manager'):
            if job_id := state.get('job_id'):
                await websocket_manager.send_status_update(
                    job_id=job_id,
                    status="processing",
                    message=f"🎯 Démarrage de la recherche pour {company}",
                    result={"step": "Initialisation"}
                )

        site_scrape = {}

        # Tenter l’extraction uniquement si une URL est fournie
        if url := state.get('company_url'):
            msg += f"\n🌐 Exploration du site web de l’entreprise : {url}"
            logger.info(f"Démarrage de l’analyse du site web pour {url}")
            
            # Envoi du statut initial de briefing
            if websocket_manager := state.get('websocket_manager'):
                if job_id := state.get('job_id'):
                    await websocket_manager.send_status_update(
                        job_id=job_id,
                        status="processing",
                        message="Exploration du site web de l’entreprise",
                        result={"step": "Exploration initiale du site"}
                    )

            try:
                logger.info("Lancement de l’exploration Tavily")
                site_extraction = await self.tavily_client.crawl(
                    url=url, 
                    instructions="Trouver toutes les pages permettant de comprendre les activités de l’entreprise, ses produits, services et autres informations pertinentes.",
                    max_depth=1, 
                    max_breadth=50, 
                    extract_depth="advanced"
                )
                
                site_scrape = {}
                for item in site_extraction.get("results", []):
                    if item.get("raw_content"):
                        page_url = item.get("url", url)
                        site_scrape[page_url] = {
                            'raw_content': item.get('raw_content'),
                            'source': 'site_entreprise'
                        }
                
                if site_scrape:
                    logger.info(f"Exploration réussie de {len(site_scrape)} pages du site web")
                    msg += f"\n✅ Exploration réussie de {len(site_scrape)} pages du site web"
                    if websocket_manager := state.get('websocket_manager'):
                        if job_id := state.get('job_id'):
                            await websocket_manager.send_status_update(
                                job_id=job_id,
                                status="processing",
                                message=f"Exploration réussie de {len(site_scrape)} pages du site web",
                                result={"step": "Exploration initiale du site"}
                            )
                else:
                    logger.warning("Aucun contenu trouvé dans les résultats de l’exploration")
                    msg += "\n⚠️ Aucun contenu trouvé lors de l’exploration du site web"
                    if websocket_manager := state.get('websocket_manager'):
                        if job_id := state.get('job_id'):
                            await websocket_manager.send_status_update(
                                job_id=job_id,
                                status="processing",
                                message="⚠️ Aucun contenu trouvé à l’URL fournie",
                                result={"step": "Exploration initiale du site"}
                            )
            except Exception as e:
                error_str = str(e)
                logger.error(f"Erreur lors de l’exploration du site web : {error_str}", exc_info=True)
                error_msg = f"⚠️ Erreur lors de l’exploration du contenu du site web : {error_str}"
                print(error_msg)
                msg += f"\n{error_msg}"
                if websocket_manager := state.get('websocket_manager'):
                    if job_id := state.get('job_id'):
                        await websocket_manager.send_status_update(
                            job_id=job_id,
                            status="website_error",
                            message=error_msg,
                            result={
                                "step": "Exploration initiale du site", 
                                "error": error_str,
                                "continue_research": True  # Continuer la recherche même si l’exploration échoue
                            }
                        )
        else:
            msg += "\n⏩ Aucune URL d’entreprise fournie, passage direct à la phase de recherche"
            if websocket_manager := state.get('websocket_manager'):
                if job_id := state.get('job_id'):
                    await websocket_manager.send_status_update(
                        job_id=job_id,
                        status="processing",
                        message="Aucune URL d’entreprise fournie, passage direct à la phase de recherche",
                        result={"step": "Initialisation"}
                    )

        # Ajouter des informations contextuelles sur les données disponibles
        context_data = {}
        if hq := state.get('hq_location'):
            msg += f"\n📍 Siège social : {hq}"
            context_data["hq_location"] = hq
        if industry := state.get('industry'):
            msg += f"\n🏭 Secteur d’activité : {industry}"
            context_data["industry"] = industry
        
        # Initialiser le ResearchState avec les informations d’entrée
        research_state = {
            # Copier les champs d’entrée
            "company": state.get('company'),
            "company_url": state.get('company_url'),
            "hq_location": state.get('hq_location'),
            "industry": state.get('industry'),
            # Initialiser les champs de recherche
            "messages": [AIMessage(content=msg)],
            "site_scrape": site_scrape,
            # Passer les informations WebSocket
            "websocket_manager": state.get('websocket_manager'),
            "job_id": state.get('job_id')
        }

        # Si une erreur s’est produite lors de l’exploration initiale, la stocker dans l’état
        if "⚠️ Erreur lors de l’exploration du contenu du site web :" in msg:
            research_state["error"] = error_str

        return research_state

    async def run(self, state: InputState) -> ResearchState:
        return await self.initial_search(state)
