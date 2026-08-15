"""
chat.py
-------
Boucle conversationnelle avec l'agent Gemini : la mémoire est conservée d'un
tour à l'autre.

uv run chat.py (quitter : 'quit', 'exit' ou Ctrl-C)
"""

import asyncio
import sys
import uuid

# Remplacement de ChatGroq par ChatGoogleGenerativeAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_mcp_adapters.client import MultiServerMCPClient

# Importer vos variables adaptées pour Gemini depuis graph.py
from graph import (
    MCP_URL,
    GOOGLE_API_KEY,
    RECURSION_LIMIT,
    construire_graphe,
    derniere_reponse,
)

async def get_agent() :
    """
    Crée et retourne un agent Gemini configuré avec les outils et le client MCP.
    """
    if not GOOGLE_API_KEY:
        print("Clé Gemini manquante. Renseigner GOOGLE_API_KEY dans .env")
        sys.exit(1)

    client = MultiServerMCPClient(
        {"facturation": {"url": MCP_URL, "transport": "streamable_http"}}
    )

    try:
        outils = await client.get_tools()
    except Exception as exc:
        print(f"Serveur MCP injoignable sur {MCP_URL} — {exc}")
        sys.exit(1)

    agent = construire_graphe(outils)
    return agent

async def main() -> None:

    # Cas pour langsmith
    agent = await get_agent()
   
    thread_id = str(uuid.uuid4())
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": RECURSION_LIMIT,
    }

    historique = []  # ← la mémoire de la conversation
    trace_active = False

    while True:
        try:
            question = input("vous > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not question:
            continue

        if question.lower() in {"quit", "exit", "q"}:
            break

        if question.lower() == "trace":
            trace_active = not trace_active
            print(f"[trace {'activée' if trace_active else 'désactivée'}]\n")
            continue

        historique.append(("user", question))

        try:
            resultat = await agent.ainvoke(
                {"messages": historique},
                config=config  #  paramètre nommé
            )
        except Exception as exc:
            print(f"[erreur] {exc}\n")
            historique.pop()
            continue

        # On réinjecte l'historique complet renvoyé par LangGraph
        historique = resultat["messages"]

        reponse = derniere_reponse(resultat["messages"])

        print(f"\nagent > {reponse}\n")


if __name__ == "__main__":
    asyncio.run(main())