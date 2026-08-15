# Procédures opérationnelles - Recouvrement Client

## Procédure 1 : Traitement d'une demande de situation globale
1. Vérifier si le code client est fourni dans la demande.
2. Si le code client est absent, demander confirmation à l'utilisateur.
3. Exécuter l'outil `top_clients_ca`.
4. Formater la réponse selon la structure standard définie dans `sKILL.md`.

## Procédure 2 : Escalade en cas d'erreur ou d'absence de données
1. Si l'outil `top_clients_ca` renvoie un statut d'échec ou d'erreur, interroger `clients_retard_paiement`.
2. Si la demande concerne une analyse approfondie des flux, solliciter `analyserReglements`.
3. Si le client reste introuvable dans tous les systèmes, demander à l'utilisateur de valider le matricule/code client.