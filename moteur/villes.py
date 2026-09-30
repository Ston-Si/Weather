"""Construit villes.json : les communes les plus peuplées de France métropolitaine.

À relancer seulement pour changer la liste : python3 -m moteur.villes [nombre]
"""
import json
import sys

from .commun import VILLES, telecharger_json

URL = "https://geo.api.gouv.fr/communes?fields=nom,code,population,centre,codeDepartement"
# Communes suivies en plus des plus peuplées (codes INSEE).
EN_PLUS = ["45169"]  # Ingré


def construire(nombre=200):
    communes = telecharger_json(URL)
    metropole = [
        c for c in communes
        if c.get("population") and c.get("centre")
        and not c["codeDepartement"].startswith(("97", "98"))  # outre-mer
    ]
    metropole.sort(key=lambda c: -c["population"])
    choisies = metropole[:nombre]
    choisies += [c for c in metropole[nombre:] if c["code"] in EN_PLUS]
    villes = []
    for commune in choisies:
        lon, lat = commune["centre"]["coordinates"]
        villes.append({
            "code": commune["code"],
            "nom": commune["nom"],
            "dep": commune["codeDepartement"],
            "lat": round(lat, 4),
            "lon": round(lon, 4),
        })
    return villes


if __name__ == "__main__":
    villes = construire(int(sys.argv[1]) if len(sys.argv) > 1 else 200)
    with open(VILLES, "w", encoding="utf-8") as fichier:
        json.dump(villes, fichier, ensure_ascii=False, indent=0)
    print("%d villes écrites dans %s" % (len(villes), VILLES))
