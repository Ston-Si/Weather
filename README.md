# Comparateur météo

Quel service météo est le plus fiable pour une ville donnée ? Chaque jour, on
enregistre ce que chaque service prévoit pour J+1 à J+7, puis on compare aux
relevés des stations Météo-France une fois qu'ils sont publiés.

## Fonctionnement

| Étape | Commande | Résultat |
|---|---|---|
| Prévisions du jour | `python3 -m moteur.collecte` | `data/previsions/AAAA-MM-JJ.csv.gz` |
| Relevés des stations | `python3 -m moteur.observations` | `data/observations.csv` |
| Classement | `python3 -m moteur.scores` | `site/data/scores.json` |

Le workflow GitHub Actions (`.github/workflows/collecte.yml`) lance les trois
chaque matin, enregistre les données dans le dépôt et publie `site/` sur
GitHub Pages. Aucune dépendance : Python standard uniquement.

Tests : `python3 -m unittest discover tests`

## Services suivis

- Sans clé : modèles Météo-France, ECMWF, GFS, ICON et UK Met Office (via
  Open-Meteo), et yr.no (MET Norway).
- Avec clé (ignorés tant que la clé manque) : OpenWeatherMap (`OWM_KEY`,
  5 jours) et WeatherAPI (`WEATHERAPI_KEY`, 3 jours). Les clés se déclarent
  dans les *secrets* du dépôt GitHub.
- Avec clé, sur les 20 plus grandes villes seulement : AccuWeather
  (`ACCUWEATHER_KEY`, 5 jours) et Tomorrow.io (`TOMORROW_KEY`, 4 jours). Leurs
  offres gratuites (50 appels par jour, 25 par heure) ne couvrent pas 200
  villes ; leur score « France entière » ne porte donc que sur ces 20 villes.

## Villes

`villes.json` : les 200 communes les plus peuplées de métropole, plus celles
listées dans `EN_PLUS` (`moteur/villes.py`). Pour modifier la liste :
`python3 -m moteur.villes`.

## Méthode et limites

- Une prévision est juste si la température est à ±2 °C du relevé et si elle
  annonce correctement pluie (≥ 1 mm) ou temps sec.
- La référence est la station Météo-France la plus proche ayant mesuré ce
  jour-là, à 30 km au plus ; sa distance est affichée sur le site.
- Les relevés quotidiens Météo-France ne suivent pas exactement le jour civil
  (Tmin de 18 h UTC la veille à 18 h UTC, pluie de 6 h à 6 h UTC), alors que
  les prévisions sont agrégées de minuit à minuit. Le décalage est le même
  pour tous les services, donc le classement reste équitable.
- Les lignes « via Open-Meteo » sont les modèles bruts, pas les applications
  grand public des organismes.
- Un classement par ville demande environ un mois de données pour être stable.
