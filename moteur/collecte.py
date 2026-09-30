"""Collecte quotidienne : enregistre ce que chaque service prévoit pour J+1 à J+7.

python3 -m moteur.collecte [--villes N]
"""
import os
import sys
from datetime import date

from .commun import (
    COLONNES_PREVISIONS, PREVISIONS, aujourdhui, charger_villes, ecrire_csv, lire_csv,
)
from .sources import COLLECTEURS

ECHEANCE_MAX = 7


def avec_echeance(previsions, jour):
    """Garde les prévisions de J+1 à J+7 et leur ajoute l'échéance en jours."""
    gardees = []
    for prevision in previsions:
        echeance = (date.fromisoformat(prevision["date"]) - jour).days
        if 1 <= echeance <= ECHEANCE_MAX:
            gardees.append(dict(prevision, echeance=echeance))
    return gardees


def collecter(villes, jour):
    chemin = os.path.join(PREVISIONS, "%s.csv.gz" % jour.isoformat())
    # Si la collecte est relancée le même jour, on garde les sources déjà
    # obtenues quand une source échoue cette fois-ci.
    par_source = {}
    for ligne in lire_csv(chemin):
        par_source.setdefault(ligne["source"], []).append(ligne)
    echecs = []
    for collecteur, variable in COLLECTEURS:
        if variable and not os.environ.get(variable):
            print("%-16s ignoré (pas de clé %s)" % (collecteur.__name__, variable))
            continue
        try:
            previsions = avec_echeance(collecteur(villes), jour)
        except Exception as erreur:  # une source en panne ne bloque pas les autres
            echecs.append(collecteur.__name__)
            print("%-16s ÉCHEC : %s" % (collecteur.__name__, erreur))
            continue
        for source in {p["source"] for p in previsions}:
            par_source[source] = [p for p in previsions if p["source"] == source]
        print("%-16s %d prévisions" % (collecteur.__name__, len(previsions)))
    lignes = [l for source in sorted(par_source) for l in par_source[source]]
    ecrire_csv(chemin, COLONNES_PREVISIONS, lignes)
    print("%d lignes dans %s" % (len(lignes), chemin))
    return echecs


if __name__ == "__main__":
    villes = charger_villes()
    if "--villes" in sys.argv:
        villes = villes[:int(sys.argv[sys.argv.index("--villes") + 1])]
    collecter(villes, aujourdhui())
