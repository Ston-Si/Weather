"""Un service météo = une fonction qui rend des prévisions quotidiennes normalisées.

Chaque prévision est un dict : ville, source, date (AAAA-MM-JJ, jour local),
tmin/tmax (°C), pluie (mm), proba (% de pluie, ou None), vent (km/h, vent moyen
maximal). Les fonctions `lire_*` sont pures (testées sans réseau).
"""
import json
import os
import time
from collections import defaultdict
from datetime import datetime, timezone

from .commun import PARIS, RACINE, telecharger_json

# Modèles servis par Open-Meteo : ce sont les modèles bruts des organismes, pas
# leurs applications (qui ajoutent leurs propres corrections).
MODELES_OPEN_METEO = {
    "meteofrance": "meteofrance_seamless",
    "ecmwf": "ecmwf_ifs025",
    "gfs": "gfs_seamless",
    "icon": "icon_seamless",
    "ukmo": "ukmo_seamless",
}

SOURCES = {
    "meteofrance": {"nom": "Météo-France", "detail": "modèles AROME/ARPEGE, via Open-Meteo"},
    "ecmwf": {"nom": "ECMWF", "detail": "modèle européen IFS, via Open-Meteo"},
    "gfs": {"nom": "NOAA GFS", "detail": "modèle américain, base de nombreuses applis"},
    "icon": {"nom": "DWD ICON", "detail": "modèle allemand, via Open-Meteo"},
    "ukmo": {"nom": "UK Met Office", "detail": "modèle britannique, via Open-Meteo"},
    "yr": {"nom": "yr.no", "detail": "prévisions de MET Norway"},
    "openweathermap": {"nom": "OpenWeatherMap", "detail": "offre gratuite, jusqu'à 5 jours"},
    "weatherapi": {"nom": "WeatherAPI", "detail": "offre gratuite, jusqu'à 3 jours"},
    "accuweather": {"nom": "AccuWeather",
                    "detail": "offre gratuite : 20 plus grandes villes, jusqu'à 5 jours"},
    "tomorrow": {"nom": "Tomorrow.io",
                 "detail": "offre gratuite : 20 plus grandes villes, jusqu'à 4 jours"},
}

# Les offres gratuites d'AccuWeather (50 appels par jour) et de Tomorrow.io
# (25 par heure) ne couvrent pas toutes les villes : on suit les plus peuplées,
# en gardant de la marge pour relancer une collecte.
VILLES_OFFRE_LIMITEE = 20
LIEUX_ACCUWEATHER = os.path.join(RACINE, "data", "accuweather_lieux.json")


def _jour_local(instant):
    return instant.astimezone(PARIS).date().isoformat()


# --- Open-Meteo -------------------------------------------------------------

def lire_open_meteo(reponse, ville):
    quotidien = reponse.get("daily") or {}
    previsions = []
    for source, modele in MODELES_OPEN_METEO.items():
        def serie(variable):
            return quotidien.get("%s_%s" % (variable, modele)) or []
        for i, date in enumerate(quotidien.get("time") or []):
            def valeur(variable):
                valeurs = serie(variable)
                return valeurs[i] if i < len(valeurs) else None
            tmax = valeur("temperature_2m_max")
            tmin = valeur("temperature_2m_min")
            if tmax is None or tmin is None:
                continue
            previsions.append({
                "ville": ville, "source": source, "date": date,
                "tmin": tmin, "tmax": tmax,
                "pluie": valeur("precipitation_sum"),
                "proba": valeur("precipitation_probability_max"),
                "vent": valeur("wind_speed_10m_max"),
            })
    return previsions


def open_meteo(villes, lot=40):
    previsions = []
    for debut in range(0, len(villes), lot):
        groupe = villes[debut:debut + lot]
        url = (
            "https://api.open-meteo.com/v1/forecast"
            "?latitude=%s&longitude=%s"
            "&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,"
            "precipitation_probability_max,wind_speed_10m_max"
            "&models=%s&timezone=Europe%%2FParis&forecast_days=8"
        ) % (
            ",".join(str(v["lat"]) for v in groupe),
            ",".join(str(v["lon"]) for v in groupe),
            ",".join(MODELES_OPEN_METEO.values()),
        )
        reponses = telecharger_json(url)
        if isinstance(reponses, dict):  # une seule ville : pas de liste
            reponses = [reponses]
        for ville, reponse in zip(groupe, reponses):
            previsions.extend(lire_open_meteo(reponse, ville["code"]))
        time.sleep(1)
    return previsions


# --- yr.no (MET Norway) -----------------------------------------------------

def lire_yr(reponse, ville):
    """Agrège la série horaire puis 6-horaire de MET Norway par jour local."""
    serie = reponse["properties"]["timeseries"]
    instants = [
        datetime.strptime(p["time"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        for p in serie
    ]
    jours = defaultdict(lambda: {"t": [], "pluie": 0.0, "vent": [], "heures": 0})
    for i, point in enumerate(serie):
        if i + 1 < len(serie):
            duree = int((instants[i + 1] - instants[i]).total_seconds() // 3600)
        else:
            duree = 6
        bloc = point["data"].get("next_1_hours" if duree == 1 else "next_6_hours")
        if bloc is None:
            continue
        jour = jours[_jour_local(instants[i])]
        details = point["data"]["instant"]["details"]
        jour["t"].append(details["air_temperature"])
        jour["vent"].append(details["wind_speed"] * 3.6)
        # Les blocs de 6 h donnent aussi les extrêmes de température du bloc.
        for cle in ("air_temperature_max", "air_temperature_min"):
            if cle in bloc.get("details", {}):
                jour["t"].append(bloc["details"][cle])
        jour["pluie"] += bloc.get("details", {}).get("precipitation_amount", 0.0)
        jour["heures"] += duree
    previsions = []
    for date, jour in sorted(jours.items()):
        if jour["heures"] < 21:  # jour incomplet (aujourd'hui, fin de série)
            continue
        previsions.append({
            "ville": ville, "source": "yr", "date": date,
            "tmin": min(jour["t"]), "tmax": max(jour["t"]),
            "pluie": jour["pluie"], "proba": None, "vent": max(jour["vent"]),
        })
    return previsions


def yr(villes):
    previsions = []
    for ville in villes:
        url = "https://api.met.no/weatherapi/locationforecast/2.0/complete?lat=%s&lon=%s" % (
            ville["lat"], ville["lon"])
        previsions.extend(lire_yr(telecharger_json(url), ville["code"]))
        time.sleep(0.1)
    return previsions


# --- OpenWeatherMap (prévision gratuite 5 jours / 3 heures) ------------------

def lire_openweathermap(reponse, ville):
    jours = defaultdict(lambda: {"tmin": [], "tmax": [], "pluie": 0.0, "proba": [], "vent": []})
    for point in reponse.get("list") or []:
        instant = datetime.fromtimestamp(point["dt"], tz=timezone.utc)
        jour = jours[_jour_local(instant)]
        jour["tmin"].append(point["main"]["temp_min"])
        jour["tmax"].append(point["main"]["temp_max"])
        jour["pluie"] += (point.get("rain") or {}).get("3h", 0.0)
        jour["pluie"] += (point.get("snow") or {}).get("3h", 0.0)
        jour["proba"].append(point.get("pop", 0.0) * 100)
        jour["vent"].append(point["wind"]["speed"] * 3.6)
    previsions = []
    for date, jour in sorted(jours.items()):
        if len(jour["tmax"]) < 8:  # 8 pas de 3 h = un jour complet
            continue
        previsions.append({
            "ville": ville, "source": "openweathermap", "date": date,
            "tmin": min(jour["tmin"]), "tmax": max(jour["tmax"]),
            "pluie": jour["pluie"], "proba": max(jour["proba"]), "vent": max(jour["vent"]),
        })
    return previsions


def openweathermap(villes):
    cle = os.environ["OWM_KEY"]
    previsions = []
    for ville in villes:
        url = ("https://api.openweathermap.org/data/2.5/forecast"
               "?lat=%s&lon=%s&units=metric&appid=%s") % (ville["lat"], ville["lon"], cle)
        previsions.extend(lire_openweathermap(telecharger_json(url), ville["code"]))
        time.sleep(1.1)  # offre gratuite : 60 appels par minute
    return previsions


# --- WeatherAPI (offre gratuite : 3 jours) ----------------------------------

def lire_weatherapi(reponse, ville):
    previsions = []
    for jour in reponse.get("forecast", {}).get("forecastday") or []:
        resume = jour["day"]
        previsions.append({
            "ville": ville, "source": "weatherapi", "date": jour["date"],
            "tmin": resume["mintemp_c"], "tmax": resume["maxtemp_c"],
            "pluie": resume.get("totalprecip_mm"),
            "proba": resume.get("daily_chance_of_rain"),
            "vent": resume.get("maxwind_kph"),
        })
    return previsions


def weatherapi(villes):
    cle = os.environ["WEATHERAPI_KEY"]
    previsions = []
    for ville in villes:
        url = "https://api.weatherapi.com/v1/forecast.json?key=%s&q=%s,%s&days=3" % (
            cle, ville["lat"], ville["lon"])
        previsions.extend(lire_weatherapi(telecharger_json(url), ville["code"]))
        time.sleep(0.2)
    return previsions


# --- AccuWeather (offre gratuite : 5 jours, 50 appels par jour) --------------

def lire_accuweather(reponse, ville):
    previsions = []
    for jour in reponse.get("DailyForecasts") or []:
        demi_journees = [jour.get("Day") or {}, jour.get("Night") or {}]

        def valeurs(*chemin):
            trouvees = []
            for bloc in demi_journees:
                for cle in chemin:
                    bloc = (bloc or {}).get(cle)
                if bloc is not None:
                    trouvees.append(bloc)
            return trouvees
        pluies, probas = valeurs("TotalLiquid", "Value"), valeurs("PrecipitationProbability")
        vents = valeurs("Wind", "Speed", "Value")
        previsions.append({
            "ville": ville, "source": "accuweather", "date": jour["Date"][:10],
            "tmin": jour["Temperature"]["Minimum"]["Value"],
            "tmax": jour["Temperature"]["Maximum"]["Value"],
            "pluie": sum(pluies) if pluies else None,
            "proba": max(probas) if probas else None,
            "vent": max(vents) if vents else None,
        })
    return previsions


def accuweather(villes):
    cle = os.environ["ACCUWEATHER_KEY"]
    base = "https://dataservice.accuweather.com"
    # L'identifiant de lieu d'une ville ne change pas : on ne le demande qu'une
    # fois, pour ne pas dépenser un appel de plus par ville chaque jour.
    lieux = {}
    if os.path.exists(LIEUX_ACCUWEATHER):
        with open(LIEUX_ACCUWEATHER, encoding="utf-8") as fichier:
            lieux = json.load(fichier)
    previsions = []
    try:
        for ville in villes[:VILLES_OFFRE_LIMITEE]:
            if ville["code"] not in lieux:
                url = "%s/locations/v1/cities/geoposition/search?apikey=%s&q=%s,%s" % (
                    base, cle, ville["lat"], ville["lon"])
                lieux[ville["code"]] = telecharger_json(url, essais=1)["Key"]
            url = "%s/forecasts/v1/daily/5day/%s?apikey=%s&metric=true&details=true" % (
                base, lieux[ville["code"]], cle)
            previsions.extend(lire_accuweather(telecharger_json(url, essais=1), ville["code"]))
            time.sleep(0.2)
    finally:
        with open(LIEUX_ACCUWEATHER, "w", encoding="utf-8") as fichier:
            json.dump(lieux, fichier, indent=0, sort_keys=True)
    return previsions


# --- Tomorrow.io (offre gratuite : 5 jours horaires, 25 appels par heure) ----

def lire_tomorrow(reponse, ville):
    jours = defaultdict(lambda: {"t": [], "pluie": 0.0, "proba": [], "vent": []})
    for point in (reponse.get("timelines") or {}).get("hourly") or []:
        instant = datetime.strptime(point["time"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
        valeurs = point["values"]
        if valeurs.get("temperature") is None:
            continue
        jour = jours[_jour_local(instant)]
        jour["t"].append(valeurs["temperature"])
        # Neige et grésil en équivalent eau, comme un pluviomètre.
        for cle in ("rainAccumulation", "snowAccumulationLwe", "sleetAccumulationLwe"):
            jour["pluie"] += valeurs.get(cle) or 0.0
        jour["proba"].append(valeurs.get("precipitationProbability") or 0.0)
        jour["vent"].append((valeurs.get("windSpeed") or 0.0) * 3.6)
    previsions = []
    for date, jour in sorted(jours.items()):
        if len(jour["t"]) < 24:  # jour incomplet (aujourd'hui, fin de série)
            continue
        previsions.append({
            "ville": ville, "source": "tomorrow", "date": date,
            "tmin": min(jour["t"]), "tmax": max(jour["t"]),
            "pluie": jour["pluie"], "proba": max(jour["proba"]), "vent": max(jour["vent"]),
        })
    return previsions


def tomorrow(villes):
    cle = os.environ["TOMORROW_KEY"]
    previsions = []
    for ville in villes[:VILLES_OFFRE_LIMITEE]:
        url = ("https://api.tomorrow.io/v4/weather/forecast"
               "?location=%s,%s&timesteps=1h&units=metric&apikey=%s") % (
                   ville["lat"], ville["lon"], cle)
        previsions.extend(lire_tomorrow(telecharger_json(url, essais=1), ville["code"]))
        time.sleep(0.5)  # offre gratuite : 3 appels par seconde
    return previsions


# (fonction, variable d'environnement requise ou None)
COLLECTEURS = [
    (open_meteo, None),
    (yr, None),
    (openweathermap, "OWM_KEY"),
    (weatherapi, "WEATHERAPI_KEY"),
    (accuweather, "ACCUWEATHER_KEY"),
    (tomorrow, "TOMORROW_KEY"),
]
