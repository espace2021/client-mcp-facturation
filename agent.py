"""
agent.py
--------
Agent ReAct client du serveur MCP Facturation avec Google Gemini.

Le serveur MCP tourne de son côté (port 8000).

Commandes :
  uv run agent.py --outils          # Inventaire des outils, sans LLM
  uv run agent.py "question"        # Poser une question
  uv run agent.py                   # Lancer les questions de test (Golden set)
"""

import asyncio
import os
import sys
import time

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.agents import create_agent

load_dotenv()

MCP_URL = os.getenv("MCP_URL", "http://127.0.0.1:8000/mcp")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GOOGLE_MODEL = os.getenv("GOOGLE_MODEL", "gemini-2.5-flash")

# Vérification basique de la clé API
GOOGLE_OK = bool(GOOGLE_API_KEY) and len(GOOGLE_API_KEY) > 20

RECURSION_LIMIT = 15  # garde-fou anti-boucle

# =========================================================
# SYSTEM PROMPT — à versionner comme du code
# =========================================================
SYSTEM_PROMPT = """Tu es l'assistant commercial de la société, connecté au système de facturation.

Tu aides à consulter, analyser et gérer les données commerciales (articles, clients, réglements, facturation).

Tu disposes d'outils de gestion du catalogue articles et de consultation des réglements clients.
Les descriptions des outils te sont fournies : lis-les attentivement avant de choisir un outil.

DONNÉES ET RAISONNEMENT
- Les données retournées par les outils sont les sources de vérité.
- Tu dois exploiter les données brutes retournées par les outils pour répondre aux questions.
- Tu peux analyser, filtrer, regrouper et effectuer des calculs directement à partir des observations fournies.
- Effectue toi-même tous les calculs demandés à partir des données disponibles.
- Ne demande pas à l'utilisateur de calculer à ta place.

RÈGLES D'IDENTIFICATION
- Ne devine JAMAIS un identifiant.
- Pour agir sur un article cité par son nom, appelle d'abord l'outil de recherche afin d'obtenir son id_article exact.
- Utilise uniquement les identifiants retournés par les outils.

RÈGLES SUR LES DONNÉES
- N'invente jamais un prix, un stock, une référence, un montant ou une information client.
- Si une information n'existe pas dans les résultats des outils ou dans les données disponibles, indique clairement que tu ne la possèdes pas.
- Une liste vide signifie "aucun résultat trouvé", pas une erreur.
- En cas de résultat vide, tente une recherche avec un mot-clé plus court ou plus général avant d'abandonner.

ANALYSE COMMERCIALE
À partir des données brutes fournies, tu peux calculer :
- totaux
- sommes
- moyennes
- écarts
- évolutions
- soldes
- indicateurs commerciaux

Règles de calcul du chiffre d'affaires :
- Le chiffre d'affaires correspond uniquement à la somme des débits des pièces de type "Facture de vente".
- Ne jamais additionner les règlements.
- Ne jamais additionner les avoirs.
- Ne jamais additionner les écritures de régularisation.

MÉMOIRE DE CONVERSATION
- Tu conserves le contexte des échanges précédents dans la conversation.
- Utilise les informations déjà obtenues lors des tours précédents lorsque cela est pertinent.
- Ne redemande pas une information déjà fournie ou déjà récupérée dans la conversation.
- Si une nouvelle question dépend d'un résultat précédent, réutilise ce résultat au lieu de recommencer inutilement.

RÈGLES D'ÉCRITURE DANS LE SYSTÈME
- Les outils de création, modification ou suppression changent des données réelles.
- Avant toute opération d'écriture :
  1. Présente un récapitulatif clair.
  2. Indique toutes les valeurs concernées.
  3. Demande une confirmation explicite de l'utilisateur.
- N'exécute jamais une écriture sans confirmation claire.
- Les opérations de lecture et d'analyse ne nécessitent aucune confirmation.

FORMAT DES RÉPONSES
- Réponds toujours en français.
- Sois concise, précise et chiffrée.
- Utilise les montants en TND HT.
- Cite les désignations exactes des articles.
- Pour les calculs, indique brièvement la méthode utilisée et le résultat.
"""


# =========================================================
# TRACE ReAct
# =========================================================
def afficher_trace(messages: list) -> dict:
    """Reconstitue la boucle Thought → Action → Observation."""
    outils_utilises, etape = [], 0

    for msg in messages:
        type_msg = msg.__class__.__name__

        if type_msg == "AIMessage":
            # Normalisation du contenu (str ou list) en une seule chaîne de caractères
            raw_content = msg.content
            if isinstance(raw_content, list):
                # Si c'est une liste de blocs, on extrait le texte de chaque bloc
                text_parts = [
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in raw_content
                ]
                content_str = "".join(text_parts).strip()
            else:
                content_str = str(raw_content or "").strip()

            if content_str:
                print(f" Thought      : {content_str[:200]}")

            for appel in getattr(msg, "tool_calls", []) or []:
                etape += 1
                outils_utilises.append(appel["name"])
                print(f" Action  [{etape}] : {appel['name']}({appel['args']})")

        elif type_msg == "ToolMessage":
            observation = str(msg.content).replace("\n", " ")
            suite = "…" if len(observation) > 220 else ""
            print(f" Observation  : {observation[:220]}{suite}")

    return {"tools_used": outils_utilises, "steps": etape}


# =========================================================
# AGENT
# =========================================================
async def interroger(agent, question: str) -> dict:
    print(f"\n{'=' * 72}\nQuestion : {question}\n{'-' * 72}")

    debut = time.time()

    try:
        resultat = await agent.ainvoke(
            {"messages": [("user", question)]},
            {"recursion_limit": RECURSION_LIMIT},
        )
    except Exception as exc:
        print(f" ÉCHEC : {exc}")
        return {
            "answer": "",
            "tools_used": [],
            "steps": 0,
            "duration_s": time.time() - debut,
        }

    duree = time.time() - debut
    trace = afficher_trace(resultat["messages"])

    reponse = ""
    for msg in reversed(resultat["messages"]):
        if msg.__class__.__name__ == "AIMessage":
            raw_content = msg.content
            if isinstance(raw_content, list):
                text_parts = [
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in raw_content
                ]
                content_str = "".join(text_parts).strip()
            else:
                content_str = str(raw_content or "").strip()

            if content_str:
                reponse = content_str
                break

    print(f"{'-' * 72}\nRéponse : {reponse}")
    print(
        f"[{trace['steps']} appel(s) · {duree:.1f}s · outils : {trace['tools_used'] or 'aucun'}]"
    )

    return {"answer": reponse, **trace, "duration_s": duree}


async def main() -> None:
    # Connexion au serveur MCP distant.
    client = MultiServerMCPClient(
        {"facturation": {"url": MCP_URL, "transport": "streamable_http"}}
    )

    try:
        outils = await client.get_tools()
    except Exception as exc:
        print(
            f"Serveur MCP injoignable sur {MCP_URL}\n {type(exc).__name__}:{exc}"
        )
        print("\nCôté serveur, vérifier que server.py tourne :")
        print(" uv run server.py     # streamable-http, port 8000")
        sys.exit(1)

    print(f"{len(outils)} outil(s) découvert(s) sur {MCP_URL} :")
    for outil in outils:
        print(
            f" - {outil.name:<26} {(outil.description or '').splitlines()[0]}"
        )

    if "--outils" in sys.argv:
        return

    if not GOOGLE_OK:
        print(
            "\nClé Google manquante. Renseigner GOOGLE_API_KEY dans le fichier .env"
        )
        print(
            "Les outils ci-dessus sont bien exposés, mais l'agent ne peut pas raisonner sans LLM."
        )
        sys.exit(1)

    # Instanciation de Gemini
    llm = ChatGoogleGenerativeAI(
        model=GOOGLE_MODEL, api_key=GOOGLE_API_KEY, temperature=0
    )

    # Utilisation du ReAct Agent de LangGraph
    agent = create_agent(llm, outils, system_prompt=SYSTEM_PROMPT)

    questions = [a for a in sys.argv[1:] if not a.startswith("--")]

    if questions:
        for question in questions:
            await interroger(agent, question)
        return

    # Golden set par défaut si aucune question n'est passée en CLI
    golden_set = [
        "Quels sont les articles disponibles dans le catalogue ?",
        "Chercher les factures impayées du client 'Karim Ben Salah' ?",
    ]

    print(f"\n{'=' * 72}\nLancement du Golden Set ({len(golden_set)} questions)\n{'-' * 72}")
    for q in golden_set:
        await interroger(agent, q)


if __name__ == "__main__":
    asyncio.run(main())