"""Compare les prévisions enregistrées aux relevés et écrit site/data/scores.json.

Une prévision est « juste » si la température est à ±2 °C du relevé, et si
elle annonce correctement un jour de pluie (au moins 1 mm) ou un jour sec.
python3 -m moteur.scores
"""
import glob
import json
import os

from .commun import (
    OBSERVATIONS, PREVISIONS, SCORES, aujourdhui, charger_villes, lire_csv, nombre,
)
from .sources import SOURCES

TOLERANCE_T = 2.0   # °C
SEUIL_PLUIE = 1.0   # mm : en dessous, le jour compte comme sec

# Sommes et effectifs, pour que le site puisse regrouper plusieurs échéances.
COLONNES = [
    "n_tmax", "ok_tmax", "abs_tmax", "err_tmax",
    "n_tmin", "ok_tmin", "abs_tmin",
    "n_pluie", "ok_pluie",
    "n_vent", "abs_vent",
    "n_proba", "brier",
]


def comparer(prevision, observation):
    """Contribution d'une prévision aux sommes, dans l'ordre de COLONNES."""
    ligne = [0.0] * len(COLONNES)

    def ajouter(prefixe, valeurs):
        debut = COLONNES.index(prefixe)
        for decalage, valeur in enumerate(valeurs):
            ligne[debut + decalage] = valeur

    for nom in ("tmax", "tmin"):
        prevu, releve = nombre(prevision[nom]), nombre(observation[nom])
        if prevu is None or releve is None:
            continue
        erreur = prevu - releve
        valeurs = [1, 1 if abs(erreur) <= TOLERANCE_T else 0, abs(erreur)]
        if nom == "tmax":
            valeurs.append(erreur)
        ajouter("n_" + nom, valeurs)
    pluie_relevee = nombre(observation["pluie"])
    if pluie_relevee is not None:
        a_plu = pluie_relevee >= SEUIL_PLUIE
        pluie_prevue = nombre(prevision["pluie"])
        if pluie_prevue is not None:
            ajouter("n_pluie", [1, 1 if (pluie_prevue >= SEUIL_PLUIE) == a_plu else 0])
        proba = nombre(prevision["proba"])
        if proba is not None:
            ajouter("n_proba", [1, (proba / 100.0 - (1.0 if a_plu else 0.0)) ** 2])
    vent_prevu, vent_releve = nombre(prevision["vent"]), nombre(observation["vent"])
    if vent_prevu is not None and vent_releve is not None:
        ajouter("n_vent", [1, abs(vent_prevu - vent_releve)])
    return ligne


def calculer(previsions, observations):
    """{ville: {source: {échéance: sommes}}}, plus la pseudo-ville « FR » (toutes)."""
    releves = {(o["ville"], o["date"]): o for o in observations}
    scores = {}
    for prevision in previsions:
        observation = releves.get((prevision["ville"], prevision["date"]))
        if observation is None:
            continue
        contribution = comparer(prevision, observation)
        for ville in (prevision["ville"], "FR"):
            sommes = (scores.setdefault(ville, {})
                      .setdefault(prevision["source"], {})
                      .setdefault(str(prevision["echeance"]), [0.0] * len(COLONNES)))
            for i, valeur in enumerate(contribution):
                sommes[i] += valeur
    return scores


def arrondir(scores):
    return {
        ville: {
            source: {e: [round(v, 2) for v in sommes] for e, sommes in echeances.items()}
            for source, echeances in sources.items()
        }
        for ville, sources in scores.items()
    }


def construire(villes, previsions, observations):
    scores = arrondir(calculer(previsions, observations))
    stations = {}
    for observation in sorted(observations, key=lambda o: o["date"]):
        stations[observation["ville"]] = observation  # la plus récente l'emporte
    fiches = [{"code": "FR", "nom": "France entière (%d villes)" % len(villes)}]
    for ville in villes:
        fiche = {"code": ville["code"], "nom": ville["nom"], "dep": ville["dep"]}
        station = stations.get(ville["code"])
        if station:
            fiche["station"] = station["nom_station"]
            fiche["dist_km"] = nombre(station["dist_km"])
        fiches.append(fiche)
    jours = sorted({p["date"] for p in previsions
                    if (p["ville"], p["date"]) in {(o["ville"], o["date"]) for o in observations}})
    return {
        "maj": aujourdhui().isoformat(),
        "premier_jour": jours[0] if jours else None,
        "dernier_jour": jours[-1] if jours else None,
        "jours": len(jours),
        "colonnes": COLONNES,
        "sources": SOURCES,
        "villes": fiches,
        "scores": scores,
    }


def charger_previsions():
    previsions = []
    for chemin in sorted(glob.glob(os.path.join(PREVISIONS, "*.csv.gz"))):
        if os.path.basename(chemin).startswith("._"):  # fichiers parasites macOS
            continue
        previsions.extend(lire_csv(chemin))
    return previsions


if __name__ == "__main__":
    resultat = construire(charger_villes(), charger_previsions(), lire_csv(OBSERVATIONS))
    os.makedirs(os.path.dirname(SCORES), exist_ok=True)
    with open(SCORES, "w", encoding="utf-8") as fichier:
        json.dump(resultat, fichier, ensure_ascii=False, separators=(",", ":"))
    print("%d jours comparés, %d villes avec un score" % (
        resultat["jours"], max(len(resultat["scores"]) - 1, 0)))
