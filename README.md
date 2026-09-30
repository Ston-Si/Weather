# Comparateur météo

Quel service météo est le plus fiable pour une commune donnée ? Chaque jour, on
enregistre ce que chaque service prévoit pour J+1 à J+7 à l'emplacement de
chaque station Météo-France, puis on compare aux relevés de la station une
fois qu'ils sont publiés. Chaque commune de métropole est rattachée à la
station la plus proche.

## Fonctionnement

| Étape | Commande | Résultat |
|---|---|---|
| Prévisions du jour | `python3 -m moteur.collecte` | `data/previsions/AAAA-MM-JJ.csv.gz` |
| Relevés et stations | `python3 -m moteur.observations` | `data/observations/AAAA-MM.csv`, `data/stations.json`, `site/data/communes.json` |
| Classement | `python3 -m moteur.scores` | `site/data/scores.json` (national), `site/data/scores/DD.json` (par département) |

Le workflow GitHub Actions (`.github/workflows/collecte.yml`) lance les trois
chaque matin, enregistre les données dans le dépôt et publie `site/` sur
GitHub Pages. Aucune dépendance : Python standard uniquement.

Tests : `python3 -m unittest discover tests`

## Services suivis

- Sans clé : modèles Météo-France, ECMWF, GFS, ICON et UK Met Office (via
  Open-Meteo), et yr.no (MET Norway).
- Avec clé (ignorés tant que la clé manque) : OpenWeatherMap (`OWM_KEY`,
  4 jours) et WeatherAPI (`WEATHERAPI_KEY`, 2 jours). Les clés se déclarent
  dans les *secrets* du dépôt GitHub.
- Avec clé, sur 20 stations seulement (celles des plus grandes villes) :
  AccuWeather (`ACCUWEATHER_KEY`) et Tomorrow.io (`TOMORROW_KEY`), 4 jours.
  Leurs offres gratuites (50 appels par jour, 25 par heure) ne couvrent pas
  toutes les stations ; leur score « France entière » ne porte donc que sur
  ces 20 stations.

## Stations et communes

- `data/stations.json` : les stations ayant relevé les températures ces 20
  derniers jours (environ 1 800), celles des plus grandes villes d'abord. La
  liste est refaite à chaque passage ; la collecte du lendemain s'en sert.
- `communes.csv` : les communes de métropole et leur position. À refaire
  quand la liste des communes change : `python3 -m moteur.communes`.
- Test rapide sur quelques stations : `python3 -m moteur.collecte --stations 5`.

## Méthode et limites

- Une prévision est juste si la température est à ±2 °C du relevé et si elle
  annonce correctement pluie (≥ 1 mm) ou temps sec.
- La référence d'une commune est la station Météo-France en service la plus
  proche, à 30 km au plus ; sa distance est affichée sur le site. Les
  prévisions sont celles de l'emplacement de la station, pas de la commune :
  en montagne ou sur la côte, l'écart peut compter.
- Les relevés quotidiens Météo-France ne suivent pas exactement le jour civil
  (Tmin de 18 h UTC la veille à 18 h UTC, pluie de 6 h à 6 h UTC), alors que
  les prévisions sont agrégées de minuit à minuit. Le décalage est le même
  pour tous les services, donc le classement reste équitable.
- Les lignes « via Open-Meteo » sont les modèles bruts, pas les applications
  grand public des organismes.
- Un classement par station demande environ un mois de données pour être stable.
