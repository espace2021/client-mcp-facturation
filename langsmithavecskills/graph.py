"""
graph.py
--------
"""

import os

from langchain_core.messages import SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from dotenv import load_dotenv
from load_skills import (
    creer_outil_load_skill,
    creer_outil_read_skill_resource,
    decouvrir_skills,
    index_skills,
)


load_dotenv()

RECURSION_LIMIT = 15

MCP_URL = os.getenv("MCP_URL", "http://127.0.0.1:8000/mcp")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_MODEL = os.getenv("GOOGLE_MODEL", "gemini-2.5-flash")

SKILLS = decouvrir_skills()

SYSTEM_PROMPT = """Tu es l'assistant commercial de la société, connecté au système de facturation.

RÈGLES
- Ne devine jamais un identifiant : utilise l'outil de recherche pour l'obtenir.
- N'invente jamais un prix, un stock, une référence ou un montant.
- Une liste vide signifie « aucun résultat », pas une erreur.
- Réponds en français, de façon concise et chiffrée. Montants en TND HT.

GESTION DU CONTEXTE DE CONVERSATION
- Traite chaque nouvelle question de façon indépendante par défaut.
- Ne relie une question à un échange précédent que si elle contient un indice explicite de continuité (« celui-ci », « ce dernier », « et son stock ? », « la même chose pour... », etc.).
- En l'absence d'un tel indice, considère qu'il s'agit d'un nouveau sujet sans rapport avec ce qui précède, même si le thème général se ressemble.

SKILLS DISPONIBLES
{index_skills(SKILLS)}

Avant de traiter une demande qui correspond à une des skills ci-dessus,
appelle load_skill(name) pour charger sa méthodologie complète — obligatoire
avant tout appel d'outil MCP lié à cette skill. Si la skill liste des
ressources entre crochets (ex. [ressources : examples.md, procedures.md]),
n'appelle read_skill_resource(name, resource) que si tu as réellement besoin
d'exemples concrets, d'une procédure détaillée ou d'un glossaire — ne charge
pas les ressources par défaut.
"""



def derniere_reponse(messages: list) -> str:
    for msg in reversed(messages):
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
    return reponse

def construire_graphe(outils):
    outils_skills = [
        creer_outil_load_skill(SKILLS),
        creer_outil_read_skill_resource(SKILLS),
    ]
    tous_les_outils = list(outils) + outils_skills

    llm = ChatGoogleGenerativeAI(
        model=GOOGLE_MODEL,
        google_api_key=GOOGLE_API_KEY,
        temperature=0,
    )
    llm_avec_outils = llm.bind_tools(tous_les_outils)

    tool_node = ToolNode(outils)

    def appeler_modele(state: MessagesState):
        messages = state["messages"]
        if not messages or messages[0].__class__.__name__ != "SystemMessage":
            messages = [SystemMessage(content=SYSTEM_PROMPT)] + list(messages)
        reponse = llm_avec_outils.invoke(messages)
        return {"messages": [reponse]}

    def route_apres_agent(state: MessagesState):
        dernier = state["messages"][-1]
        if getattr(dernier, "tool_calls", None):
            return "tools"
        return END

    graphe = StateGraph(MessagesState)
    graphe.add_node("agent", appeler_modele)
    graphe.add_node("tools", tool_node)
    graphe.add_edge(START, "agent")
    graphe.add_conditional_edges(
        "agent", route_apres_agent, {"tools": "tools", END: END}
    )
    graphe.add_edge("tools", "agent")

    return graphe.compile(checkpointer=InMemorySaver())