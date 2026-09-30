"""Construit communes.csv : toutes les communes de France métropolitaine.

À relancer seulement quand la liste des communes change (fusions au 1er janvier) :
python3 -m moteur.communes
"""
from .commun import COLONNES_COMMUNES, COMMUNES, ecrire_csv, telecharger_json

URL = "https://geo.api.gouv.fr/communes?fields=nom,code,population,centre,codeDepartement"


def construire():
    communes = []
    for commune in telecharger_json(URL):
        if not commune.get("centre") or commune["codeDepartement"].startswith(("97", "98")):
            continue  # outre-mer : pas de prévisions comparables
        lon, lat = commune["centre"]["coordinates"]
        communes.append({
            "code": commune["code"], "nom": commune["nom"],
            "lat": "%.4f" % lat, "lon": "%.4f" % lon,
            "population": commune.get("population") or 0,
        })
    # Les plus peuplées d'abord : c'est l'ordre des suggestions du site.
    communes.sort(key=lambda c: (-c["population"], c["code"]))
    return communes


if __name__ == "__main__":
    communes = construire()
    ecrire_csv(COMMUNES, COLONNES_COMMUNES, communes)
    print("%d communes écrites dans %s" % (len(communes), COMMUNES))
