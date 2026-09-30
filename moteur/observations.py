"""Relevés des stations Météo-France (données quotidiennes ouvertes, data.gouv.fr).

Enregistre les relevés récents de chaque station, la liste des stations en
service (les points où l'on collecte les prévisions) et la station de référence
de chaque commune. python3 -m moteur.observations
"""
import csv
import io
import math
import os
import re
from datetime import timedelta

from .commun import (
    COLONNES_OBSERVATIONS, COMMUNES, OBSERVATIONS, SITE, STATIONS, aujourdhui,
    ecrire_csv, ecrire_json, lire_csv, nombre, telecharger, telecharger_json,
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
        trouve = re.search(r"/Q_(\d\d)_latest-[\d-]+_RR-T-Vent\.csv\.gz$", ressource["url"])
        if trouve:  # deux chiffres : métropole seulement
            fichiers[trouve.group(1)] = ressource["url"]
    return fichiers


def lire_releves(texte, depuis):
    """Relevés de température à partir de `depuis` (AAAAMMJJ), avec la position des stations."""
    releves = []
    for ligne in csv.DictReader(io.StringIO(texte), delimiter=";"):
        if ligne["AAAAMMJJ"] < depuis:
            continue
        tmin, tmax = nombre(ligne["TN"]), nombre(ligne["TX"])
        if tmin is None or tmax is None:
            continue
        vent = nombre(ligne["FXY"])  # vent moyen maximal, en m/s
        jour = "%s-%s-%s" % (ligne["AAAAMMJJ"][:4], ligne["AAAAMMJJ"][4:6], ligne["AAAAMMJJ"][6:])
        releves.append({
            "station": ligne["NUM_POSTE"].strip(), "date": jour,
            "nom": ligne["NOM_USUEL"].strip(),
            "lat": float(ligne["LAT"]), "lon": float(ligne["LON"]),
            "tmin": tmin, "tmax": tmax, "pluie": nombre(ligne["RR"]),
            "vent": None if vent is None else vent * 3.6,
        })
    return releves


def rattacher(communes, stations):
    """Station la plus proche de chaque commune : {code: (station, km)}, à 30 km au plus."""
    # Cases d'un demi-degré (55 km du nord au sud, 35 km au moins d'est en
    # ouest) : les stations à moins de 30 km sont dans la case ou ses voisines.
    cases = {}
    for station in stations:
        case = (math.floor(station["lat"] * 2), math.floor(station["lon"] * 2))
        cases.setdefault(case, []).append(station)
    rattachements = {}
    for commune in communes:
        lat, lon = float(commune["lat"]), float(commune["lon"])
        meilleur = None
        for i in (-1, 0, 1):
            for j in (-1, 0, 1):
                for station in cases.get((math.floor(lat * 2) + i, math.floor(lon * 2) + j), ()):
                    distance = distance_km(lat, lon, station["lat"], station["lon"])
                    if distance <= DISTANCE_MAX_KM and (meilleur is None or distance < meilleur[1]):
                        meilleur = (station["code"], distance)
        if meilleur:
            rattachements[commune["code"]] = (meilleur[0], round(meilleur[1], 1))
    return rattachements


def stations_en_service(releves, communes):
    """Stations ayant relevé les températures récemment, celles des plus grandes villes d'abord."""
    stations = {}
    for releve in releves:
        stations[releve["station"]] = {
            "code": releve["station"], "nom": releve["nom"],
            "lat": releve["lat"], "lon": releve["lon"],
        }
    rattachements = rattacher(communes, stations.values())
    for commune in communes:  # triées par population décroissante
        if commune["code"] in rattachements:
            station = stations[rattachements[commune["code"]][0]]
            station.setdefault("ville", commune["nom"])
            station.setdefault("population", int(commune["population"]))
    ordre = sorted(stations.values(), key=lambda s: (-s.get("population", 0), s["code"]))
    return ordre, rattachements


def enregistrer_releves(releves):
    """Fusionne les relevés dans un fichier par mois (data/observations/AAAA-MM.csv)."""
    par_mois = {}
    for releve in releves:
        par_mois.setdefault(releve["date"][:7], []).append(releve)
    for mois, nouveaux in par_mois.items():
        chemin = os.path.join(OBSERVATIONS, "%s.csv" % mois)
        lignes = {(l["station"], l["date"]): l for l in lire_csv(chemin)}
        lignes.update({(r["station"], r["date"]): r for r in nouveaux})
        ecrire_csv(chemin, COLONNES_OBSERVATIONS,
                   [lignes[cle] for cle in sorted(lignes, key=lambda c: (c[1], c[0]))])


def mettre_a_jour():
    depuis = (aujourdhui() - timedelta(days=JOURS_RELUS)).strftime("%Y%m%d")
    releves = []
    for departement, url in sorted(fichiers_par_departement().items()):
        releves.extend(lire_releves(telecharger(url).decode("utf-8"), depuis))
    enregistrer_releves(releves)
    communes = lire_csv(COMMUNES)
    stations, rattachements = stations_en_service(releves, communes)
    ecrire_json(STATIONS, stations, indent=0)
    # Pour le site : [code, nom, station, km], les plus peuplées d'abord.
    ecrire_json(os.path.join(SITE, "communes.json"), [
        [c["code"], c["nom"]] + list(rattachements.get(c["code"], ())) for c in communes
    ], separators=(",", ":"))
    dernier = max(r["date"] for r in releves) if releves else "aucun"
    print("%d relevés, %d stations en service, %d communes sur %d rattachées ; "
          "dernier jour relevé : %s" % (
              len(releves), len(stations), len(rattachements), len(communes), dernier))


if __name__ == "__main__":
    mettre_a_jour()
