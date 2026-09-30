"""Compare les prévisions enregistrées aux relevés et écrit les scores du site.

site/data/scores.json porte le classement national ; site/data/scores/DD.json
celui de chaque station du département DD.

Une prévision est « juste » si la température est à ±2 °C du relevé, et si
elle annonce correctement un jour de pluie (au moins 1 mm) ou un jour sec.
python3 -m moteur.scores
"""
import glob
import os

from .commun import (
    OBSERVATIONS, PREVISIONS, SITE, aujourdhui, charger_stations, ecrire_json, lire_csv,
    nombre,
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
    """{station: {source: {échéance: sommes}}}, plus « FR » (toutes), et les jours comparés."""
    releves = {(o["station"], o["date"]): o for o in observations}
    scores, jours = {}, set()
    for prevision in previsions:
        observation = releves.get((prevision["station"], prevision["date"]))
        if observation is None:
            continue
        jours.add(prevision["date"])
        contribution = comparer(prevision, observation)
        for station in (prevision["station"], "FR"):
            sommes = (scores.setdefault(station, {})
                      .setdefault(prevision["source"], {})
                      .setdefault(str(prevision["echeance"]), [0.0] * len(COLONNES)))
            for i, valeur in enumerate(contribution):
                sommes[i] += valeur
    return scores, sorted(jours)


def arrondir(sources):
    return {
        source: {e: [round(v, 2) for v in sommes] for e, sommes in echeances.items()}
        for source, echeances in sources.items()
    }


def construire(stations, previsions, observations):
    """Le résumé national et, par département, les stations avec leurs scores."""
    scores, jours = calculer(previsions, observations)
    departements = {}
    for station in stations:
        # Les deux premiers chiffres d'une station sont son département.
        departements.setdefault(station["code"][:2], {})[station["code"]] = {
            "nom": station["nom"], "scores": arrondir(scores.get(station["code"], {})),
        }
    resume = {
        "maj": aujourdhui().isoformat(),
        "premier_jour": jours[0] if jours else None,
        "dernier_jour": jours[-1] if jours else None,
        "jours": len(jours),
        "stations": len(stations),
        "colonnes": COLONNES,
        "sources": SOURCES,
        "france": arrondir(scores.get("FR", {})),
    }
    return resume, departements


def lire_tout(dossier, motif):
    """Lignes de tous les fichiers du dossier, lues une à une (les prévisions sont volumineuses)."""
    for chemin in sorted(glob.glob(os.path.join(dossier, motif))):
        if os.path.basename(chemin).startswith("._"):  # fichiers parasites macOS
            continue
        yield from lire_csv(chemin)


if __name__ == "__main__":
    resume, departements = construire(
        charger_stations(), lire_tout(PREVISIONS, "*.csv.gz"),
        lire_tout(OBSERVATIONS, "*.csv"))
    ecrire_json(os.path.join(SITE, "scores.json"), resume, separators=(",", ":"))
    for departement, stations in departements.items():
        ecrire_json(os.path.join(SITE, "scores", "%s.json" % departement), stations,
                    separators=(",", ":"))
    print("%d jours comparés, %d stations" % (resume["jours"], resume["stations"]))
