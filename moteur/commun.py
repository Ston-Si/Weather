"""Chemins, requêtes HTTP et lecture/écriture des fichiers de données."""
import csv
import gzip
import io
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMMUNES = os.path.join(RACINE, "communes.csv")
STATIONS = os.path.join(RACINE, "data", "stations.json")
PREVISIONS = os.path.join(RACINE, "data", "previsions")
OBSERVATIONS = os.path.join(RACINE, "data", "observations")
SITE = os.path.join(RACINE, "site", "data")

PARIS = ZoneInfo("Europe/Paris")
# MET Norway exige un User-Agent identifiable ; les autres services l'acceptent.
USER_AGENT = os.environ.get(
    "METEO_USER_AGENT", "comparateur-meteo/1.0 (https://github.com/)"
)

COLONNES_COMMUNES = ["code", "nom", "lat", "lon", "population"]
COLONNES_PREVISIONS = [
    "station", "source", "date", "echeance", "tmin", "tmax", "pluie", "proba", "vent",
]
COLONNES_OBSERVATIONS = ["station", "date", "tmin", "tmax", "pluie", "vent"]


def aujourdhui():
    return datetime.now(PARIS).date()


def telecharger(url, essais=3, pause=2.0):
    """Contenu brut d'une URL (décompressé si gzip), avec quelques essais."""
    derniere = None
    for essai in range(essais):
        try:
            requete = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(requete, timeout=60) as reponse:
                contenu = reponse.read()
            if contenu[:2] == b"\x1f\x8b":
                contenu = gzip.decompress(contenu)
            return contenu
        except urllib.error.HTTPError as erreur:
            derniere = erreur
            # Clé refusée ou requête invalide : réessayer ne sert à rien.
            if erreur.code in (400, 401, 403, 404):
                break
        except (urllib.error.URLError, OSError) as erreur:
            derniere = erreur
        time.sleep(pause * (essai + 1))
    raise RuntimeError("Échec de %s : %s" % (url.split("?")[0], derniere))


def telecharger_json(url, **options):
    return json.loads(telecharger(url, **options).decode("utf-8"))


def charger_stations():
    """Stations suivies : les points où l'on collecte les prévisions."""
    with open(STATIONS, encoding="utf-8") as fichier:
        return json.load(fichier)


def ecrire_json(chemin, contenu, **options):
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    with open(chemin, "w", encoding="utf-8") as fichier:
        json.dump(contenu, fichier, ensure_ascii=False, **options)


def nombre(valeur):
    """Convertit une cellule CSV en float, None si vide ou invalide."""
    if valeur is None or valeur == "":
        return None
    try:
        return float(valeur)
    except ValueError:
        return None


def lire_csv(chemin):
    if not os.path.exists(chemin):
        return []
    ouvrir = gzip.open if chemin.endswith(".gz") else open
    with ouvrir(chemin, "rt", encoding="utf-8", newline="") as fichier:
        return list(csv.DictReader(fichier))


def ecrire_csv(chemin, colonnes, lignes):
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    tampon = io.StringIO()
    ecrivain = csv.DictWriter(tampon, fieldnames=colonnes, lineterminator="\n")
    ecrivain.writeheader()
    for ligne in lignes:
        ecrivain.writerow({c: _cellule(ligne.get(c)) for c in colonnes})
    texte = tampon.getvalue()
    if chemin.endswith(".gz"):
        # mtime=0 : le fichier ne change pas si les données ne changent pas.
        with open(chemin, "wb") as brut:
            with gzip.GzipFile(fileobj=brut, mode="wb", mtime=0) as fichier:
                fichier.write(texte.encode("utf-8"))
    else:
        with open(chemin, "w", encoding="utf-8", newline="") as fichier:
            fichier.write(texte)


def _cellule(valeur):
    if valeur is None:
        return ""
    if isinstance(valeur, float):
        return "%g" % round(valeur, 2)
    return valeur
