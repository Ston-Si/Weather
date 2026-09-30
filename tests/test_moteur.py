"""Tests sans réseau : python3 -m unittest discover tests"""
import unittest
from datetime import date

from moteur import observations, scores, sources
from moteur.collecte import avec_echeance


def prevision(**champs):
    base = {"station": "69029001", "source": "ecmwf", "date": "2026-10-02", "echeance": 1,
            "tmin": "10", "tmax": "20", "pluie": "0", "proba": "", "vent": "15"}
    base.update(champs)
    return base


def observation(**champs):
    base = {"station": "69029001", "date": "2026-10-02",
            "tmin": "10", "tmax": "20", "pluie": "0", "vent": "15"}
    base.update(champs)
    return base


def valeur(ligne, colonne):
    return ligne[scores.COLONNES.index(colonne)]


class TestScores(unittest.TestCase):
    def test_temperature_dans_la_tolerance(self):
        ligne = scores.comparer(prevision(tmax="22", tmin="7.5"), observation())
        self.assertEqual(valeur(ligne, "ok_tmax"), 1)   # écart de 2 °C : juste
        self.assertEqual(valeur(ligne, "ok_tmin"), 0)   # écart de 2,5 °C : faux
        self.assertEqual(valeur(ligne, "err_tmax"), 2)  # biais signé (trop chaud)
        self.assertEqual(valeur(ligne, "abs_tmin"), 2.5)

    def test_pluie_oui_non(self):
        juste = scores.comparer(prevision(pluie="3"), observation(pluie="5"))
        faux = scores.comparer(prevision(pluie="3"), observation(pluie="0.4"))
        self.assertEqual(valeur(juste, "ok_pluie"), 1)
        self.assertEqual(valeur(faux, "ok_pluie"), 0)  # 0,4 mm compte comme sec

    def test_brier(self):
        ligne = scores.comparer(prevision(proba="80"), observation(pluie="5"))
        self.assertEqual(valeur(ligne, "n_proba"), 1)
        self.assertAlmostEqual(valeur(ligne, "brier"), 0.04)

    def test_valeurs_manquantes_non_comptees(self):
        ligne = scores.comparer(prevision(vent="", pluie=""), observation(pluie=""))
        self.assertEqual(valeur(ligne, "n_vent"), 0)
        self.assertEqual(valeur(ligne, "n_pluie"), 0)
        self.assertEqual(valeur(ligne, "n_tmax"), 1)

    def test_calcul_par_station_et_france(self):
        previsions = [prevision(), prevision(date="2026-10-03", tmax="30"),
                      prevision(date="2026-10-09")]  # pas de relevé : ignorée
        releves = [observation(), observation(date="2026-10-03")]
        resultat, jours = scores.calculer(previsions, releves)
        sommes = resultat["69029001"]["ecmwf"]["1"]
        self.assertEqual(valeur(sommes, "n_tmax"), 2)
        self.assertEqual(valeur(sommes, "ok_tmax"), 1)
        self.assertEqual(resultat["FR"], resultat["69029001"])
        self.assertEqual(jours, ["2026-10-02", "2026-10-03"])

    def test_construire(self):
        stations = [{"code": "69029001", "nom": "LYON-BRON"},
                    {"code": "20004002", "nom": "AJACCIO"}]
        resume, departements = scores.construire(stations, [prevision()], [observation()])
        self.assertEqual((resume["jours"], resume["stations"]), (1, 2))
        self.assertEqual(resume["france"], departements["69"]["69029001"]["scores"])
        self.assertEqual(departements["20"]["20004002"], {"nom": "AJACCIO", "scores": {}})


class TestCollecte(unittest.TestCase):
    def test_echeances_gardees(self):
        jour = date(2026, 10, 1)
        previsions = [{"date": "2026-10-01"}, {"date": "2026-10-02"},
                      {"date": "2026-10-08"}, {"date": "2026-10-09"}]
        self.assertEqual([p["echeance"] for p in avec_echeance(previsions, jour)], [1, 7])


class TestSources(unittest.TestCase):
    def test_open_meteo(self):
        reponse = {"daily": {
            "time": ["2026-10-01", "2026-10-02"],
            "temperature_2m_max_ecmwf_ifs025": [20.0, None],
            "temperature_2m_min_ecmwf_ifs025": [10.0, 9.0],
            "precipitation_sum_ecmwf_ifs025": [1.5, 0.0],
            "precipitation_probability_max_ecmwf_ifs025": [60, 5],
            "wind_speed_10m_max_ecmwf_ifs025": [12.0, 8.0],
        }}
        previsions = sources.lire_open_meteo(reponse, "69123")
        self.assertEqual(len(previsions), 1)  # jour sans tmax et modèles absents ignorés
        self.assertEqual(previsions[0]["source"], "ecmwf")
        self.assertEqual(previsions[0]["proba"], 60)

    def test_yr_jour_complet_seulement(self):
        serie = []
        for heure in range(24):  # 1er octobre, heure d'été : 22 h UTC la veille
            jour, h = ("2026-09-30", 22 + heure) if heure < 2 else ("2026-10-01", heure - 2)
            serie.append({"time": "%sT%02d:00:00Z" % (jour, h), "data": {
                "instant": {"details": {"air_temperature": 10 + heure % 12, "wind_speed": 5}},
                "next_1_hours": {"details": {"precipitation_amount": 0.5}},
            }})
        serie.append({"time": "2026-10-01T22:00:00Z", "data": {
            "instant": {"details": {"air_temperature": 9, "wind_speed": 2}},
            "next_6_hours": {"details": {"precipitation_amount": 1.0}},
        }})
        previsions = sources.lire_yr({"properties": {"timeseries": serie}}, "69123")
        self.assertEqual([p["date"] for p in previsions], ["2026-10-01"])
        self.assertEqual(previsions[0]["tmax"], 21)
        self.assertAlmostEqual(previsions[0]["pluie"], 12.0)
        self.assertAlmostEqual(previsions[0]["vent"], 18.0)

    def test_openweathermap(self):
        points = [{"dt": 1790805600 + 10800 * i,  # 2026-09-30 22:00 UTC = minuit à Paris
                   "main": {"temp_min": 8 + i, "temp_max": 9 + i},
                   "wind": {"speed": 10}, "pop": 0.1 * i,
                   "rain": {"3h": 1.0} if i == 3 else None} for i in range(9)]
        previsions = sources.lire_openweathermap({"list": points}, "69123")
        self.assertEqual(len(previsions), 1)  # le 9e pas tombe sur un jour incomplet
        self.assertEqual(previsions[0]["date"], "2026-10-01")
        self.assertEqual((previsions[0]["tmin"], previsions[0]["tmax"]), (8, 16))
        self.assertEqual(previsions[0]["pluie"], 1.0)
        self.assertAlmostEqual(previsions[0]["proba"], 70)

    def test_weatherapi(self):
        reponse = {"forecast": {"forecastday": [{"date": "2026-10-01", "day": {
            "mintemp_c": 9.1, "maxtemp_c": 18.2, "totalprecip_mm": 0.3,
            "daily_chance_of_rain": 40, "maxwind_kph": 22.0}}]}}
        previsions = sources.lire_weatherapi(reponse, "69123")
        self.assertEqual(previsions[0]["tmax"], 18.2)
        self.assertEqual(previsions[0]["proba"], 40)

    def test_accuweather(self):
        reponse = {"DailyForecasts": [{
            "Date": "2026-10-01T07:00:00+02:00",
            "Temperature": {"Minimum": {"Value": 9.0}, "Maximum": {"Value": 19.5}},
            "Day": {"PrecipitationProbability": 30, "TotalLiquid": {"Value": 1.2},
                    "Wind": {"Speed": {"Value": 14.8}}},
            "Night": {"PrecipitationProbability": 55, "TotalLiquid": {"Value": 0.8},
                      "Wind": {"Speed": {"Value": 9.3}}}}]}
        previsions = sources.lire_accuweather(reponse, "69123")
        self.assertEqual(previsions[0]["date"], "2026-10-01")
        self.assertEqual((previsions[0]["tmin"], previsions[0]["tmax"]), (9.0, 19.5))
        self.assertAlmostEqual(previsions[0]["pluie"], 2.0)
        self.assertEqual((previsions[0]["proba"], previsions[0]["vent"]), (55, 14.8))

    def test_tomorrow_jour_complet_seulement(self):
        points = [{"time": "2026-09-30T%02d:00:00Z" % h if h < 24
                   else "2026-10-01T%02d:00:00Z" % (h - 24),
                   "values": {"temperature": 10 + h % 12, "windSpeed": 5,
                              "rainAccumulation": 0.5, "precipitationProbability": h}}
                  for h in range(22, 48)]  # de minuit (Paris) le 1er à 1 h le 2
        previsions = sources.lire_tomorrow({"timelines": {"hourly": points}}, "69123")
        self.assertEqual([p["date"] for p in previsions], ["2026-10-01"])
        self.assertEqual((previsions[0]["tmin"], previsions[0]["tmax"]), (10, 21))
        self.assertAlmostEqual(previsions[0]["pluie"], 12.0)
        self.assertAlmostEqual(previsions[0]["vent"], 18.0)
        self.assertEqual(previsions[0]["proba"], 45)


class TestObservations(unittest.TestCase):
    TEXTE = (
        "NUM_POSTE;NOM_USUEL;LAT;LON;ALTI;AAAAMMJJ;RR;TN;TX;FXY\n"
        "69029001;LYON-BRON;45.7265;4.9369;197;20261002;1.2;10.0;20.0;5.0\n"
        "69299001;LYON-ST EXUPERY;45.7264;5.0778;235;20261002;0.0;9.0;19.0;\n"
        "69000001;SANS TEMPERATURE;45.76;4.84;170;20261002;0.0;;;\n"
        "69029001;LYON-BRON;45.7265;4.9369;197;20260901;0.0;12.0;25.0;4.0\n"
    )

    def test_lecture(self):
        releves = observations.lire_releves(self.TEXTE, "20260925")
        # Relevé ancien et station sans température écartés.
        self.assertEqual([r["station"] for r in releves], ["69029001", "69299001"])
        self.assertEqual(releves[0]["date"], "2026-10-02")
        self.assertAlmostEqual(releves[0]["vent"], 18.0)  # 5 m/s en km/h
        self.assertIsNone(releves[1]["vent"])

    def test_rattachement_et_ordre_des_stations(self):
        releves = observations.lire_releves(self.TEXTE, "20260925")
        communes = [
            {"code": "69123", "nom": "Lyon", "lat": "45.7580", "lon": "4.8351",
             "population": "519127"},
            {"code": "69299", "nom": "Colombier-Saugnieu", "lat": "45.7170", "lon": "5.1030",
             "population": "2700"},
            {"code": "29019", "nom": "Brest", "lat": "48.3900", "lon": "-4.4900",
             "population": "140000"},
        ]
        stations, rattachements = observations.stations_en_service(releves, communes)
        self.assertEqual(rattachements["69123"][0], "69029001")
        self.assertTrue(7 < rattachements["69123"][1] < 10)
        self.assertEqual(rattachements["69299"][0], "69299001")
        self.assertNotIn("29019", rattachements)  # aucune station à moins de 30 km
        # La station de la plus grande ville passe en premier.
        self.assertEqual([s["ville"] for s in stations], ["Lyon", "Colombier-Saugnieu"])


if __name__ == "__main__":
    unittest.main()
