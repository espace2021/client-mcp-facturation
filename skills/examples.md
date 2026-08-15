# Exemples d'utilisation

## Exemple 1 : Demande de synthèse financière
**Utilisateur :** Quel est le solde et le taux de recouvrement du client C1024 ?

**Déroulement :**
1. Appel à `top_clients_ca` avec `code_client="C1024"`.
2. Restitution au format standard :
   - Client : STE ABC
   - Chiffre d'affaires : 150 000.000 TND
   - Encaissé : 120 000.000 TND
   - Solde : 30 000.000 TND
   - Taux de recouvrement : 80.00 %
   - Impayés : 2 pièce(s) pour 30 000.000 TND

---

## Exemple 2 : Demande de détail / relevé
**Utilisateur :** Donne-moi le détail des pièces impayées du client C1024.

**Déroulement :**
1. Appel à `detecterAnomalies` avec `code_client="C1024"`.
2. Présentation du relevé ligne par ligne avec les dates, numéros de pièces, montants débit/crédit et dates d'échéance.