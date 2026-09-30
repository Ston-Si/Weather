"""Relevés des stations Météo-France (données quotidiennes ouvertes, data.gouv.fr).

Pour chaque ville et chaque jour récent, on prend la station la plus proche qui
a mesuré les températures ce jour-là. python3 -m moteur.observations
"""
import csv
import io
import math
import re
from datetime import timedelta

from .commun import (
    COLONNES_OBSERVATIONS, OBSERVATIONS, aujourdhui, charger_villes, ecrire_csv,
    lire_csv, nombre, telecharger, telecharger_json,
)

JEU = "https://www.data.gouv.fr/api/1/datasets/donnees-climatologiques-de-base-quotidiennes/"
DISTANCE_MAX_KM = 30
JOURS_RELUS = 20  # les relevés arrivent avec quelques jours de retard


def distance_km(lat1, lon1, lat2, lon2):
    a = (math.sin(math.radians(lat2 - lat1) / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 6371 * 2 * math.asin(math.sqrt(a))


def fichiers_par_departement():
    """URL du fichier « latest » de chaque département (le nom change chaque année)."""
    fichiers = {}
    for ressource in telecharger_json(JEU)["resources"]:
        trouve = re.search(r"/Q_(\w+?)_latest-[\d-]+_RR-T-Vent\.csv\.gz$", ressource["url"])
        if trouve:
            fichiers[trouve.group(1)] = ressource["url"]
    return fichiers


def departement_meteo(code):
    return "20" if code in ("2A", "2B") else code  # la Corse est un seul fichier


def lire_releves(texte, depuis):
    """Relevés par date (AAAA-MM-JJ) à partir de `depuis` (AAAAMMJJ)."""
    releves = {}
    for ligne in csv.DictReader(io.StringIO(texte), delimiter=";"):
        if ligne["AAAAMMJJ"] < depuis:
            continue
        tmin, tmax = nombre(ligne["TN"]), nombre(ligne["TX"])
        if tmin is None or tmax is None:
            continue
        vent = nombre(ligne["FXY"])  # vent moyen maximal, en m/s
        jour = "%s-%s-%s" % (ligne["AAAAMMJJ"][:4], ligne["AAAAMMJJ"][4:6], ligne["AAAAMMJJ"][6:])
        releves.setdefault(jour, []).append({
            "station": ligne["NUM_POSTE"].strip(),
            "nom_station": ligne["NOM_USUEL"].strip(),
            "lat": float(ligne["LAT"]), "lon": float(ligne["LON"]),
            "tmin": tmin, "tmax": tmax, "pluie": nombre(ligne["RR"]),
            "vent": None if vent is None else vent * 3.6,
        })
    return releves


def plus_proche(ville, releves_du_jour):
    meilleur = None
    for releve in releves_du_jour:
        distance = distance_km(ville["lat"], ville["lon"], releve["lat"], releve["lon"])
        if distance <= DISTANCE_MAX_KM and (meilleur is None or distance < meilleur[0]):
            meilleur = (distance, releve)
    if meilleur is None:
        return None
    distance, releve = meilleur
    return {
        "ville": ville["code"], "station": releve["station"],
        "nom_station": releve["nom_station"], "dist_km": round(distance, 1),
        "tmin": releve["tmin"], "tmax": releve["tmax"],
        "pluie": releve["pluie"], "vent": releve["vent"],
    }


def mettre_a_jour(villes):
    depuis = (aujourdhui() - timedelta(days=JOURS_RELUS)).strftime("%Y%m%d")
    fichiers = fichiers_par_departement()
    releves = {}
    for departement in sorted({departement_meteo(v["dep"]) for v in villes}):
        if departement not in fichiers:
            print("Pas de fichier pour le département %s" % departement)
            continue
        texte = telecharger(fichiers[departement]).decode("utf-8")
        for jour, liste in lire_releves(texte, depuis).items():
            releves.setdefault(jour, []).extend(liste)
    observations = {(o["ville"], o["date"]): o for o in lire_csv(OBSERVATIONS)}
    for jour, liste in releves.items():
        for ville in villes:
            observation = plus_proche(ville, liste)
            if observation:
                observations[(ville["code"], jour)] = dict(observation, date=jour)
    lignes = [observations[cle] for cle in sorted(observations, key=lambda c: (c[1], c[0]))]
    ecrire_csv(OBSERVATIONS, COLONNES_OBSERVATIONS, lignes)
    dernier = max(releves) if releves else "aucun"
    print("%d observations ; dernier jour relevé : %s" % (len(lignes), dernier))


if __name__ == "__main__":
    mettre_a_jour(charger_villes())
