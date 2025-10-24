import asyncio
import logging
import os
from typing import Any, Dict, List, Union

import google.generativeai as genai

from ..classes import ResearchState

logger = logging.getLogger(__name__)

class Briefing:
    """Creates briefings for each research category and updates the ResearchState."""
    
    def __init__(self) -> None:
        self.max_doc_length = 8000  # Maximum document content length
        self.gemini_key = os.getenv("GEMINI_API_KEY")
        if not self.gemini_key:
            raise ValueError("La variable d'environnement GEMINI_API_KEY n'est pas définie")
        
        # Configure Gemini
        genai.configure(api_key=self.gemini_key)
        self.gemini_model = genai.GenerativeModel('gemini-2.5-flash')

    async def generate_category_briefing(
        self, docs: Union[Dict[str, Any], List[Dict[str, Any]]], 
        category: str, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        company = context.get('company', 'Unknown')
        industry = context.get('industry', 'Unknown')
        hq_location = context.get('hq_location', 'Unknown')
        logger.info(f"Generating {category} briefing for {company} using {len(docs)} documents")

        # Send category start status
        if websocket_manager := context.get('websocket_manager'):
            if job_id := context.get('job_id'):
                await websocket_manager.send_status_update(
                    job_id=job_id,
                    status="briefing_start",
                    message=f"Génération du briefing {category}",
                    result={
                        "step": "Briefing",
                        "category": category,
                        "total_docs": len(docs)
                    }
                )

        prompts = {
            'company': f"""Rédigez un briefing ciblé sur l'entreprise {company}, une société du secteur {industry} basée à {hq_location}.

        Exigences principales :
        1. Commencez par : "{company} est un[e] [quoi] qui [fait quoi] pour [qui]"
        2. Structurez le briefing en utilisant strictement les en-têtes et listes à puces suivantes :

        ### Produit/Service principal
        * Listez les produits/caractéristiques distincts
        * Incluez uniquement des capacités techniques vérifiées

        ### Équipe dirigeante
        * Listez les membres clés de la direction
        * Indiquez leurs rôles et expertises

        ### Marché cible
        * Listez les publics cibles spécifiques
        * Listez les cas d'utilisation vérifiés
        * Listez les clients/partenaires confirmés

        ### Différenciateurs clés
        * Listez les caractéristiques uniques
        * Listez les avantages prouvés

        ### Modèle économique
        * Présentez la tarification produit/service
        * Listez les canaux de distribution

        3. Chaque puce doit être un fait unique et complet
        4. Ne jamais mentionner "aucune information trouvée" ou "aucune donnée disponible"
        5. Pas de paragraphes, uniquement des puces
        6. Fournissez uniquement le briefing. Aucune explication ni commentaire.
        """,

            'industry': f"""Rédigez un briefing ciblé sur l'industrie pour {company}, entreprise du secteur {industry} basée à {hq_location}.

        Exigences principales :
        1. Structurez en utilisant strictement les en-têtes et listes à puces suivantes :

        ### Aperçu du marché
        * Indiquez le segment de marché exact de {company}
        * Indiquez la taille du marché avec l'année
        * Indiquez le taux de croissance avec la période

        ### Concurrence directe
        * Listez les concurrents directs nommés
        * Listez les produits concurrents spécifiques
        * Indiquez les positions sur le marché

        ### Avantages concurrentiels
        * Listez les caractéristiques techniques uniques
        * Listez les avantages prouvés

        ### Enjeux du marché
        * Listez les défis spécifiques vérifiés

        2. Chaque puce doit être un fait unique (événement) complet.
        3. Pas de paragraphes, uniquement des puces
        4. Ne jamais mentionner "aucune information trouvée" ou "aucune donnée disponible"
        5. Fournissez uniquement le briefing. Aucune explication.
        """,

            'financial': f"""Rédigez un briefing financier ciblé pour {company}, entreprise du secteur {industry} basée à {hq_location}.

        Exigences principales :
        1. Structurez en utilisant ces en-têtes et puces :

        ### Financements & Investissements
        * Montant total des financements avec la date
        * Listez chaque tour de financement avec la date
        * Listez les investisseurs nommés

        ### Modèle de revenus
        * Présentez la tarification produit/service si applicable

        2. Incluez des chiffres précis lorsque possible
        3. Pas de paragraphes, uniquement des puces
        4. Ne jamais mentionner "aucune information trouvée" ou "aucune donnée disponible"
        5. NE PAS répéter le même tour de financement plusieurs fois. SUPPOSEZ que plusieurs annonces le même mois correspondent au même tour.
        6. N'INCLUEZ JAMAIS une fourchette de montant. Utilisez votre jugement pour déterminer le montant exact à partir des informations fournies.
        7. Fournissez uniquement le briefing. Aucune explication ni commentaire.
        """,

            'news': f"""Rédigez un briefing d'actualités ciblé pour {company}, entreprise du secteur {industry} basée à {hq_location}.

        Exigences principales :
        1. Structurez en catégories suivantes avec des puces :

        ### Annonces majeures
        * Lancements de produits/services
        * Nouvelles initiatives

        ### Partenariats
        * Intégrations
        * Collaborations

        ### Reconnaissance
        * Prix
        * Couverture presse

        2. Triez du plus récent au plus ancien
        3. Un événement par puce
        4. Ne pas mentionner "aucune information trouvée" ou "aucune donnée disponible"
        5. N'utilisez pas les en-têtes ### dans la sortie finale, uniquement des puces
        6. Fournissez uniquement le briefing. Ne fournissez pas d'explications ni de commentaires.
        """,
        }
        
        # Normalize docs to a list of (url, doc) tuples
        items = list(docs.items()) if isinstance(docs, dict) else [
            (doc.get('url', f'doc_{i}'), doc) for i, doc in enumerate(docs)
        ]
        # Sort documents by evaluation score (highest first)
        sorted_items = sorted(
            items, 
            key=lambda x: float(x[1].get('evaluation', {}).get('overall_score', '0')), 
            reverse=True
        )
        
        doc_texts = []
        total_length = 0
        for _ , doc in sorted_items:
            title = doc.get('title', '')
            content = doc.get('raw_content') or doc.get('content', '')
            if len(content) > self.max_doc_length:
                content = content[:self.max_doc_length] + "... [content truncated]"
            doc_entry = f"Title: {title}\n\nContent: {content}"
            if total_length + len(doc_entry) < 120000:  # Keep under limit
                doc_texts.append(doc_entry)
                total_length += len(doc_entry)
            else:
                break
        
        separator = "\n" + "-" * 40 + "\n"
        prompt = f"""{prompts.get(category, "Rédigez un briefing ciblé, informatif et pertinent sur l'entreprise : {company} dans le secteur {industry} en vous basant sur les documents fournis.")}

Analysez les documents suivants et extrayez les informations clés. Fournissez uniquement le briefing, sans explication ni commentaire :

{separator}{separator.join(doc_texts)}{separator}

"""

        try:
            logger.info("Envoi du prompt au modèle LLM")
            response = self.gemini_model.generate_content(prompt)
            content = response.text.strip()
            if not content:
                logger.error(f"Réponse vide du LLM pour le briefing {category}")
                return {'content': ''}

            # Send completion status
            if websocket_manager := context.get('websocket_manager'):
                if job_id := context.get('job_id'):
                    await websocket_manager.send_status_update(
                        job_id=job_id,
                        status="briefing_complete",
                        message=f"Briefing {category} complété",
                        result={
                            "step": "Briefing",
                            "category": category
                        }
                    )

            return {'content': content}
        except Exception as e:
            logger.error(f"Erreur lors de la génération du briefing {category}: {e}")
            return {'content': ''}

    async def create_briefings(self, state: ResearchState) -> ResearchState:
        """Create briefings for all categories in parallel."""
        company = state.get('company', 'Unknown Company')
        websocket_manager = state.get('websocket_manager')
        job_id = state.get('job_id')
        
        # Send initial briefing status
        if websocket_manager and job_id:
            await websocket_manager.send_status_update(
                job_id=job_id,
                status="processing",
                message="Starting research briefings",
                result={"step": "Briefing"}
            )

        context = {
            "company": company,
            "industry": state.get('industry', 'Unknown'),
            "hq_location": state.get('hq_location', 'Unknown'),
            "websocket_manager": websocket_manager,
            "job_id": job_id
        }
        logger.info(f"Creating section briefings for {company}")
        
        # Mapping of curated data fields to briefing categories
        categories = {
            'financial_data': ("financial", "financial_briefing"),
            'news_data': ("news", "news_briefing"),
            'industry_data': ("industry", "industry_briefing"),
            'company_data': ("company", "company_briefing")
        }
        
        briefings = {}

        # Create tasks for parallel processing
        briefing_tasks = []
        for data_field, (cat, briefing_key) in categories.items():
            curated_key = f'curated_{data_field}'
            curated_data = state.get(curated_key, {})
            
            if curated_data:
                logger.info(f"Processing {data_field} with {len(curated_data)} documents")
                
                # Create task for this category
                briefing_tasks.append({
                    'category': cat,
                    'briefing_key': briefing_key,
                    'data_field': data_field,
                    'curated_data': curated_data
                })
            else:
                logger.info(f"No data available for {data_field}")
                state[briefing_key] = ""

        # Process briefings in parallel with rate limiting
        if briefing_tasks:
            # Rate limiting semaphore for LLM API
            briefing_semaphore = asyncio.Semaphore(2)  # Limit to 2 concurrent briefings
            
            async def process_briefing(task: Dict[str, Any]) -> Dict[str, Any]:
                """Process a single briefing with rate limiting."""
                async with briefing_semaphore:
                    result = await self.generate_category_briefing(
                        task['curated_data'],
                        task['category'],
                        context
                    )
                    
                    if result['content']:
                        briefings[task['category']] = result['content']
                        state[task['briefing_key']] = result['content']
                        logger.info(f"Briefing {task['data_field']} complété ({len(result['content'])} caractères)")
                    else:
                        logger.error(f"Échec de la génération du briefing pour {task['data_field']}")
                        state[task['briefing_key']] = ""
                    
                    return {
                        'category': task['category'],
                        'success': bool(result['content']),
                        'length': len(result['content']) if result['content'] else 0
                    }

            # Process all briefings in parallel
            results = await asyncio.gather(*[
                process_briefing(task) 
                for task in briefing_tasks
            ])
            
            # Log completion statistics
            successful_briefings = sum(1 for r in results if r['success'])
            total_length = sum(r['length'] for r in results)
            logger.info(f"Generated {successful_briefings}/{len(briefing_tasks)} briefings with total length {total_length}")

        state['briefings'] = briefings
        return state

    async def run(self, state: ResearchState) -> ResearchState:
        return await self.create_briefings(state)
