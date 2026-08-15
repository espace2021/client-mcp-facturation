"""Chargement des skills côté client.

Sur le modèle des "Agent Skills" : chaque skill se présente sous l'une des
deux formes suivantes.

Méthode 1 — fichier unique   skills/<nom>.md
    Toute la skill (rôle, stratégie, outils, format de sortie, règles) tient
    dans un seul fichier Markdown avec un en-tête (name, description, tools).

Méthode 2 — dossier structuré   skills/<nom>/SKILL.md (+ examples.md,
    procedures.md, reference.md, ...)
    SKILL.md porte le même en-tête (name, description) et le corps essentiel ;
    les fichiers annexes du dossier ne sont chargés qu'à la demande, une fois
    SKILL.md jugé insuffisant.

Dans les deux cas, seul le metadata (name, description, [ressources])
est toujours visible du modèle (peu coûteux en tokens) : le contenu complet
n'est chargé que si le modèle appelle explicitement load_skill(name), une
fois qu'il a jugé la skill pertinente pour la demande ; et un fichier annexe
n'est chargé que via read_skill_resource(name, resource), si besoin d'aller
plus loin que load_skill.

Ce module est indépendant du LLM utilisé Groq : il est
partagé par graph.py, .
"""

from __future__ import annotations

import importlib.util
import re
from dataclasses import dataclass, field
from pathlib import Path

from langchain_core.tools import tool

SKILLS_DIR = Path(__file__).parent / "skills"

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)

@dataclass
class Skill:
    name: str
    description: str
    path: Path
    tools: list[str] = field(default_factory=list)
    resources: dict[str, Path] = field(default_factory=dict)
    _content: str | None = field(default=None, repr=False)
    _module_tools: object | None = field(default=None, repr=False)

    def charger_module_tools(self):
        """Importe dynamiquement le tools.py de cette skill (présent
        uniquement pour certaines skills de type dossier), et met le module
        en cache. Retourne None si la skill n'en a pas.

        Chargement par chemin de fichier (importlib), pas par import
        classique : skills/ est un dossier de données, pas un package Python
        (skills.py, le module, et skills/, le dossier, portent le même nom —
        on ne peut donc pas faire `from skills.<nom> import tools`)."""
        if self._module_tools is not None:
            return self._module_tools
        chemin = self.path.parent / "tools.py"
        if not chemin.exists():
            return None
        spec = importlib.util.spec_from_file_location(
            f"skill_tools_{self.name.replace('-', '_')}", chemin
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self._module_tools = module
        return self._module_tools

    @property
    def content(self) -> str:
        """Contenu complet (fichier unique ou SKILL.md), lu paresseusement."""
        if self._content is None:
            self._content = self.path.read_text(encoding="utf-8")
        return self._content

    def get_resource(self, resource: str) -> str:
        """Contenu d'un fichier annexe (examples.md, procedures.md, ...),
        lu paresseusement. Seules les skills de type dossier en ont."""
        chemin = self.resources.get(resource)
        if chemin is None:
            disponibles = ", ".join(self.resources) or "aucune"
            raise KeyError(
                f"Ressource {resource!r} introuvable pour la skill {self.name!r}. "
                f"Ressources disponibles : {disponibles}"
            )
        return chemin.read_text(encoding="utf-8")

def _parse_frontmatter(texte: str) -> dict:
    match = _FRONTMATTER_RE.match(texte)
    if not match:
        return {}
    brut, _ = match.groups()
    meta: dict = {}
    for ligne in brut.splitlines():
        if ":" not in ligne:
            continue
        cle, _, valeur = ligne.partition(":")
        meta[cle.strip()] = valeur.strip().strip('"')
    return meta

def _indexer(
    fichier: Path,
    skills: dict[str, Skill],
    resources: dict[str, Path] | None = None,
) -> None:
    meta = _parse_frontmatter(fichier.read_text(encoding="utf-8"))
    nom_repli = fichier.parent.name if fichier.name == "SKILL.md" else fichier.stem
    nom = meta.get("name", nom_repli)
    description = meta.get("description", "")
    outils = [o.strip() for o in meta.get("tools", "").split(",") if o.strip()]
    skills[nom] = Skill(
        name=nom,
        description=description,
        path=fichier,
        tools=outils,
        resources=resources or {},
    )

def decouvrir_skills(dossier: Path = SKILLS_DIR) -> dict[str, Skill]:
    """Indexe les skills disponibles (metadata seule), sous les deux formes :

    - Méthode 1 : chaque fichier   skills/<nom>.md
    - Méthode 2 : chaque dossier   skills/<nom>/SKILL.md (+ fichiers annexes)
    """
    skills: dict[str, Skill] = {}
    if not dossier.exists():
        return skills

    # Méthode 1 : fichiers uniques directement sous skills/
    for fichier in sorted(dossier.glob("*.md")):
        _indexer(fichier, skills)

    # Méthode 2 : sous-dossiers contenant un SKILL.md
    for sous_dossier in sorted(p for p in dossier.iterdir() if p.is_dir()):
        skill_md = sous_dossier / "SKILL.md"
        if not skill_md.exists():
            continue
        resources = {
            p.name: p
            for p in sorted(sous_dossier.glob("*.md"))
            if p.name != "SKILL.md"
        }
        _indexer(skill_md, skills, resources=resources)

    return skills

def index_skills(skills: dict[str, Skill]) -> str:
    """Rendu texte (nom + description [+ ressources]) destiné au system
    prompt — coût minime en tokens."""
    if not skills:
        return "(aucune skill disponible)"
    lignes = []
    for s in skills.values():
        ligne = f"- {s.name} : {s.description}"
        if s.resources:
            ligne += f" [ressources : {', '.join(s.resources)}]"
        lignes.append(ligne)
    return "\n".join(lignes)

def creer_outil_load_skill(skills: dict[str, Skill]):
    """Fabrique le tool `load_skill`, point d'entrée pour charger le contenu
    complet d'une skill (fichier unique ou SKILL.md)."""

    @tool
    def load_skill(name: str) -> str:
        """Charge la méthodologie complète d'une skill (rôle, stratégie, outils à
        utiliser, format de sortie, règles) à partir de son nom exact tel
        qu'annoncé dans la section SKILLS DISPONIBLES du system prompt.
        À appeler AVANT d'utiliser les outils MCP dès qu'une demande correspond
        à une skill listée."""
        skill = skills.get(name)
        if skill is None:
            disponibles = ", ".join(skills) or "aucune"
            return f"Skill inconnue : {name!r}. Skills disponibles : {disponibles}"
        return skill.content

    return load_skill

def creer_outil_read_skill_resource(skills: dict[str, Skill]):
    """Fabrique le tool `read_skill_resource`, deuxième niveau de
    "progressive disclosure" : charge à la demande un fichier annexe d'une
    skill de type dossier (examples.md, procedures.md, reference.md, ...),
    seulement si le contenu déjà chargé via load_skill ne suffit pas."""

    @tool
    def read_skill_resource(name: str, resource: str) -> str:
        """Charge un fichier annexe d'une skill de type dossier (ex. examples.md,
        procedures.md, reference.md), listé entre crochets dans SKILLS
        DISPONIBLES ou mentionné dans le contenu renvoyé par load_skill.
        À n'appeler qu'en cas de besoin réel (exemples concrets, procédure
        détaillée, glossaire de champs) — ne pas charger systématiquement
        toutes les ressources d'une skill."""
        skill = skills.get(name)
        if skill is None:
            disponibles = ", ".join(skills) or "aucune"
            return f"Skill inconnue : {name!r}. Skills disponibles : {disponibles}"
        if not skill.resources:
            return f"La skill {name!r} est un fichier unique : aucune ressource annexe."
        try:
            return skill.get_resource(resource)
        except KeyError as exc:
            return str(exc)

    return read_skill_resource

def verifier_outils_skills(skills: dict[str, Skill], outils_mcp) -> dict[str, list[str]]:
    """Garde-fou à appeler juste après la découverte des outils MCP et avant
    de construire le graphe (agent*.py / chat*.py).

    Pour chaque skill dotée d'un tools.py (référence documentée des outils
    MCP qu'elle attend, cf. skills/recommandation-produit/tools.py), appelle
    son verifier_outils_disponibles(outils_mcp) et agrège les résultats.
    Retourne {nom_skill: [outils manquants]} — vide si tout est aligné, ou si
    aucune skill découverte n'a de tools.py.

    Objectif : détecter au démarrage un désalignement entre ce qu'une skill
    attend et ce que le serveur MCP expose réellement (outil renommé, serveur
    pas à jour...), plutôt que de laisser l'agent échouer en plein milieu
    d'une conversation."""
    manquants: dict[str, list[str]] = {}
    for skill in skills.values():
        module = skill.charger_module_tools()
        if module is None or not hasattr(module, "verifier_outils_disponibles"):
            continue
        absents = module.verifier_outils_disponibles(outils_mcp)
        if absents:
            manquants[skill.name] = absents
    return manquants
