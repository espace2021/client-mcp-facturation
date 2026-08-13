"""
chat.py
-------
Boucle conversationnelle avec l'agent Gemini : la mémoire est conservée d'un
tour à l'autre.

uv run chat.py (quitter : 'quit', 'exit' ou Ctrl-C)
"""

import asyncio
import sys

# Remplacement de ChatGroq par ChatGoogleGenerativeAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_mcp_adapters.client import MultiServerMCPClient

# Importer vos variables adaptées pour Gemini depuis agent.py
from agent import (
    GOOGLE_API_KEY,
    GOOGLE_MODEL,
    MCP_URL,
    RECURSION_LIMIT,
    SYSTEM_PROMPT,
    afficher_trace,
    create_agent,
)

async def main() -> None:

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

    # Instantation du LLM Gemini
    llm = ChatGoogleGenerativeAI(
        model=GOOGLE_MODEL,  # ex: "gemini-2.5-flash"
        google_api_key=GOOGLE_API_KEY,
        temperature=0,
    )

    agent = create_agent(llm, outils, system_prompt=SYSTEM_PROMPT)

    print(f"Assistant facturation (Gemini) — {len(outils)} outils · {MCP_URL}")
    print("Tapez 'quit' pour sortir, 'trace' pour afficher le raisonnement.\n")

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
                {"recursion_limit": RECURSION_LIMIT},
            )
        except Exception as exc:
            print(f"[erreur] {exc}\n")
            historique.pop()
            continue

        if trace_active:
            afficher_trace(resultat["messages"])

        # On réinjecte l'historique complet renvoyé par LangGraph
        historique = resultat["messages"]

        reponse = ""
        for msg in reversed(resultat["messages"]):
            if msg.__class__.__name__ == "AIMessage" and msg.content:
                # Si le contenu est une liste (comportement fréquent avec Gemini/LangChain)
                if isinstance(msg.content, list):
                    text_parts = []
                    for part in msg.content:
                        if isinstance(part, str):
                            text_parts.append(part)
                        elif isinstance(part, dict) and part.get("type") == "text":
                            text_parts.append(part.get("text", ""))
                    
                    contenu_texte = "".join(text_parts).strip()
                # Si le contenu est une simple chaîne de caractères
                elif isinstance(msg.content, str):
                    contenu_texte = msg.content.strip()
                else:
                    contenu_texte = ""

                if contenu_texte:
                    reponse = contenu_texte
                    break

        print(f"\nagent > {reponse}\n")


if __name__ == "__main__":
    asyncio.run(main())