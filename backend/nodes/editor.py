import logging
import os
from typing import Any, Dict

from langchain_core.messages import AIMessage
from openai import AsyncOpenAI

from ..classes import ResearchState
from ..utils.references import format_references_section

logger = logging.getLogger(__name__)

class Editor:
    """Compile les synthèses de chaque section en un rapport final cohérent."""
    
    def __init__(self) -> None:
        self.openai_key = os.getenv("OPENAI_API_KEY")
        if not self.openai_key:
            raise ValueError("La variable d’environnement OPENAI_API_KEY n’est pas définie")
        
        # Configuration d’OpenAI
        self.openai_client = AsyncOpenAI(api_key=self.openai_key)
        
        # Initialisation du dictionnaire de contexte utilisé dans les méthodes
        self.context = {
            "company": "Entreprise inconnue",
            "industry": "Secteur inconnu",
            "hq_location": "Inconnue"
        }

    async def compile_briefings(self, state: ResearchState) -> ResearchState:
        """Compile les différentes synthèses en un rapport final."""
        company = state.get('company', 'Entreprise inconnue')
        
        # Mettre à jour le contexte avec les valeurs de l’état
        self.context = {
            "company": company,
            "industry": state.get('industry', 'Secteur inconnu'),
            "hq_location": state.get('hq_location', 'Inconnue')
        }
        
        # Envoi du statut initial de compilation
        if websocket_manager := state.get('websocket_manager'):
            if job_id := state.get('job_id'):
                await websocket_manager.send_status_update(
                    job_id=job_id,
                    status="processing",
                    message=f"Démarrage de la compilation du rapport pour {company}",
                    result={
                        "step": "Éditeur",
                        "substep": "initialisation"
                    }
                )

        context = {
            "company": company,
            "industry": state.get('industry', 'Secteur inconnu'),
            "hq_location": state.get('hq_location', 'Inconnue')
        }
        
        msg = [f"📑 Compilation du rapport final pour {company}..."]
        
        # Récupération des synthèses individuelles à partir de l’état
        briefing_keys = {
            'company': 'company_briefing',
            'industry': 'industry_briefing',
            'financial': 'financial_briefing',
            'news': 'news_briefing'
        }

        # Envoi du statut de collecte des synthèses
        if websocket_manager := state.get('websocket_manager'):
            if job_id := state.get('job_id'):
                await websocket_manager.send_status_update(
                    job_id=job_id,
                    status="processing",
                    message="Collecte des synthèses de sections",
                    result={
                        "step": "Éditeur",
                        "substep": "collecte_synthèses"
                    }
                )

        individual_briefings = {}
        for category, key in briefing_keys.items():
            if content := state.get(key):
                individual_briefings[category] = content
                msg.append(f"Synthèse {category} trouvée ({len(content)} caractères)")
            else:
                msg.append(f"Aucune synthèse {category} disponible")
                logger.error(f"Clé d’état manquante : {key}")
        
        if not individual_briefings:
            msg.append("\n⚠️ Aucune section de synthèse disponible pour la compilation")
            logger.error("Aucune synthèse trouvée dans l’état")
        else:
            try:
                compiled_report = await self.edit_report(state, individual_briefings, context)
                if not compiled_report or not compiled_report.strip():
                    logger.error("Le rapport compilé est vide !")
                else:
                    logger.info(f"Rapport compilé avec succès ({len(compiled_report)} caractères)")
            except Exception as e:
                logger.error(f"Erreur lors de la compilation du rapport : {e}")
        state.setdefault('messages', []).append(AIMessage(content="\n".join(msg)))
        return state
    
    async def edit_report(self, state: ResearchState, briefings: Dict[str, str], context: Dict[str, Any]) -> str:
        """Assemble les sections en un rapport final et met à jour l’état."""
        try:
            company = self.context["company"]
            
            # Étape 1 : Compilation initiale
            if websocket_manager := state.get('websocket_manager'):
                if job_id := state.get('job_id'):
                    await websocket_manager.send_status_update(
                        job_id=job_id,
                        status="processing",
                        message="Compilation du rapport de recherche initial",
                        result={
                            "step": "Éditeur",
                            "substep": "compilation"
                        }
                    )

            edited_report = await self.compile_content(state, briefings, company)
            if not edited_report:
                logger.error("Échec de la compilation initiale")
                return ""

            # Étape 2 : Nettoyage et déduplication
            if websocket_manager := state.get('websocket_manager'):
                if job_id := state.get('job_id'):
                    await websocket_manager.send_status_update(
                        job_id=job_id,
                        status="processing",
                        message="Nettoyage et organisation du rapport",
                        result={
                            "step": "Éditeur",
                            "substep": "nettoyage"
                        }
                    )

            # Étape 3 : Mise en forme du rapport final
            if websocket_manager := state.get('websocket_manager'):
                if job_id := state.get('job_id'):
                    await websocket_manager.send_status_update(
                        job_id=job_id,
                        status="processing",
                        message="Mise en forme du rapport final",
                        result={
                            "step": "Éditeur",
                            "substep": "mise_en_forme"
                        }
                    )
            final_report = await self.content_sweep(state, edited_report, company)
            
            final_report = final_report or ""
            
            logger.info(f"Rapport final compilé ({len(final_report)} caractères)")
            if not final_report.strip():
                logger.error("Le rapport final est vide !")
                return ""
            
            logger.info("Aperçu du rapport final :")
            logger.info(final_report[:500])
            
            # Mise à jour de l’état avec le rapport final
            state['report'] = final_report
            state['status'] = "editor_complete"
            if 'editor' not in state or not isinstance(state['editor'], dict):
                state['editor'] = {}
            state['editor']['report'] = final_report
            logger.info(f"Taille du rapport dans l’état : {len(state.get('report', ''))}")
            
            if websocket_manager := state.get('websocket_manager'):
                if job_id := state.get('job_id'):
                    await websocket_manager.send_status_update(
                        job_id=job_id,
                        status="editor_complete",
                        message="Rapport de recherche terminé",
                        result={
                            "step": "Éditeur",
                            "report": final_report,
                            "company": company,
                            "is_final": True,
                            "status": "terminé"
                        }
                    )
            
            return final_report
        except Exception as e:
            logger.error(f"Erreur dans edit_report : {e}")
            return ""
    
    async def compile_content(self, state: ResearchState, briefings: Dict[str, str], company: str) -> str:
        """Compilation initiale des sections de recherche."""
        combined_content = "\n\n".join(content for content in briefings.values())
        
        references = state.get('references', [])
        reference_text = ""
        if references:
            logger.info(f"{len(references)} références trouvées à ajouter pendant la compilation")
            
            reference_info = state.get('reference_info', {})
            reference_titles = state.get('reference_titles', {})
            
            logger.info(f"Informations sur les références : {reference_info}")
            logger.info(f"Titres des références : {reference_titles}")
            
            reference_text = format_references_section(references, reference_info, reference_titles)
            logger.info(f"{len(references)} références ajoutées pendant la compilation")
        
        company = self.context["company"]
        industry = self.context["industry"]
        hq_location = self.context["hq_location"]
        
        prompt = f"""Vous compilez un rapport de recherche complet sur {company}.

Synthèses compilées :
{combined_content}

Rédigez un rapport complet et structuré sur {company}, une entreprise du secteur {industry} dont le siège est à {hq_location}, qui :
1. Intègre les informations de toutes les sections sans répétition
2. Préserve les détails importants de chaque section
3. Organise logiquement le contenu et supprime les transitions inutiles
4. Utilise des titres de section clairs

Structure obligatoire :
# Rapport de recherche sur {company}

## Présentation de l’entreprise
[Contenu de l’entreprise avec ### sous-sections]

## Présentation du secteur
[Contenu du secteur avec ### sous-sections]

## Présentation financière
[Contenu financier avec ### sous-sections]

## Actualités
[Contenu des actualités avec ### sous-sections]

Retournez le rapport en **markdown clair**, sans explications ni commentaires."""
        
        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-4.1",
                messages=[
                    {
                        "role": "system",
                        "content": "Vous êtes un rédacteur expert chargé de compiler des synthèses de recherche en rapports d’entreprise complets."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0,
                stream=False
            )
            initial_report = response.choices[0].message.content.strip()
            
            if reference_text:
                initial_report = f"{initial_report}\n\n{reference_text}"
            
            return initial_report
        except Exception as e:
            logger.error(f"Erreur lors de la compilation initiale : {e}")
            return (combined_content or "").strip()
        
    async def content_sweep(self, state: ResearchState, content: str, company: str) -> str:
        """Nettoie le contenu pour supprimer les redondances et incohérences."""
        company = self.context["company"]
        industry = self.context["industry"]
        hq_location = self.context["hq_location"]
        
        prompt = f"""Vous êtes un éditeur de synthèses expert. Vous devez corriger le rapport suivant sur {company}.

Rapport actuel :
{content}

Tâches :
1. Supprimer les informations redondantes
2. Supprimer les éléments non pertinents pour {company}, entreprise du secteur {industry} basée à {hq_location}
3. Supprimer les sections vides
4. Supprimer tout méta-commentaire (“Voici les actualités…”)

Structure obligatoire :
## Présentation de l’entreprise
## Présentation du secteur
## Présentation financière
## Actualités
## Références

Règles :
- Le document doit commencer par : # Rapport de recherche sur {company}
- N’utiliser **que** ces en-têtes ## dans cet ordre exact
- Pas d’autres en-têtes ## autorisés
- Utiliser ### pour les sous-sections
- Les actualités doivent utiliser uniquement des puces (*)
- Aucun bloc de code, ni ligne vide multiple
- Ne pas modifier la section Références

Retournez le rapport nettoyé en markdown parfait, sans explications."""
        
        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-4.1-mini", 
                messages=[
                    {
                        "role": "system",
                        "content": "Vous êtes un formateur markdown expert garantissant la cohérence du document."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0,
                stream=True
            )
            
            accumulated_text = ""
            buffer = ""
            
            async for chunk in response:
                if chunk.choices[0].finish_reason == "stop":
                    websocket_manager = state.get('websocket_manager')
                    if websocket_manager and buffer:
                        job_id = state.get('job_id')
                        if job_id:
                            await websocket_manager.send_status_update(
                                job_id=job_id,
                                status="report_chunk",
                                message="Mise en forme du rapport final",
                                result={
                                    "chunk": buffer,
                                    "step": "Éditeur"
                                }
                            )
                    break
                    
                chunk_text = chunk.choices[0].delta.content
                if chunk_text:
                    accumulated_text += chunk_text
                    buffer += chunk_text
                    
                    if any(char in buffer for char in ['.', '!', '?', '\n']) and len(buffer) > 10:
                        if websocket_manager := state.get('websocket_manager'):
                            if job_id := state.get('job_id'):
                                await websocket_manager.send_status_update(
                                    job_id=job_id,
                                    status="report_chunk",
                                    message="Mise en forme du rapport final",
                                    result={
                                        "chunk": buffer,
                                        "step": "Éditeur"
                                    }
                                )
                        buffer = ""
            
            return (accumulated_text or "").strip()
        except Exception as e:
            logger.error(f"Erreur de mise en forme : {e}")
            return (content or "").strip()

    async def run(self, state: ResearchState) -> ResearchState:
        state = await self.compile_briefings(state)
        # S’assurer que la sortie de l’éditeur est stockée au niveau supérieur et dans “editor”
        if 'report' in state:
            if 'editor' not in state or not isinstance(state['editor'], dict):
                state['editor'] = {}
            state['editor']['report'] = state['report']
        return state
