# hltv-api
An unofficial python flask api for popular CS2 website hltv.org.

# Installation
**Prerequisites:** Python 3.x (check with `python --version` or `python3 --version`)

```bash
git clone https://github.com/M3MONs/hltv-api.git
cd hltv-api
pip install -r requirements.txt
python app.py
```

# API Endpoints

## Swagger
```
http://127.0.0.1:8000/apidocs/#/
```

## Events

### Get All Events
```http
GET /api/v1/events/
```
Returns all events from HLTV.

### Event Matches
```http
GET /api/v1/events/<id>/<slug>/matches
```
Returns all matches for a specific event.

### Search Events
```http
GET /api/v1/events/search?q=<query>
```
Searches for events by name.

### Discover Event
```http
GET /api/v1/events/discover?url=<event_url>
```
Discovers event details and all grouped events.

### Get Event Details
```http
GET /api/v1/events/details?url=<event_url>
```
Returns event details including grouped events.

### Get Event Tier
```http
GET /api/liquipedia/events/tier?name=<event_name>
```
Returns event tier from Liquipedia (S-tier, A-tier, etc.).

### Get Ongoing Tournaments
```http
GET /api/liquipedia/events/ongoing
```
Returns ongoing S-tier tournaments from Liquipedia.

### Get Completed Tournaments
```http
GET /api/liquipedia/events/completed
```
Returns a static fallback list of recently completed tournaments (not live Liquipedia data).

### Get Liquipedia Ongoing Events Feed
```http
GET /api/liquipedia/results/ongoing-events
```
Returns ongoing tournament names tagged with `source=liquipedia`.

> Legacy compatibility aliases remain available at `/api/v1/events/{tier,ongoing,completed}`
> and `/api/v1/results/ongoing-events`.

## Teams

### Team Rankings
```http
GET /api/v1/teams/rankings
GET /api/v1/teams/rankings/<type>
GET /api/v1/teams/rankings/<type>/<year>/<month>/<day>
```
Returns the HLTV or VALVE team ranking. Available types: `hltv` (default), `valve`.
![ranking](https://github.com/user-attachments/assets/829c924d-7730-468b-be57-75586fb242b2)

### Team Search
```http
GET /api/v1/teams/search/<name>
```
Searches for a team by name.

### Team Profile
```http
GET /api/v1/teams/<id>/<team_name>
```
Returns the team profile.

### Team Matches
```http
GET /api/v1/teams/<id>/matches
GET /api/v1/teams/<id>/matches/<offset>
```
Returns a list of team matches (optionally with an offset).

## Results

### Results
```http
GET /api/v1/results/
GET /api/v1/results/<offset>
```
Returns the results of HLTV matches.
![results](https://github.com/user-attachments/assets/020eb6fb-8c11-409d-a2d6-5685d5a44385)

### Featured Results
```http
GET /api/v1/results/featured
```
Returns featured results.
![results_featured](https://github.com/user-attachments/assets/cc3b7740-6045-4401-83c7-515043b2b794)

## Matches

### Upcoming Matches
```http
GET /api/v1/matches/upcoming
```
Returns upcoming matches.

### Match Details
```http
GET /api/v1/matches/<id>/<match_name>
```
Returns details of the selected match, including `demoUrl`.

## Demos

### Download Demo
```http
GET /api/v1/download/demo/<demo_id>
```
Proxies and streams the demo file download from HLTV (bypassing restrictions).

## Players

### Player Search
```http
GET /api/v1/players/search/<name>
```
Searches for a player by name.

### Player Profile
```http
GET /api/v1/players/<id>/<player_name>
```
Returns the player profile.

### Player Stats Overview
```http
GET /api/v1/players/stats/overview/<id>/<player_name>
```
Returns the player stats overview.

## News

### News
```http
GET /api/v1/news
GET /api/v1/news/<year>/<month>/
```
Returns news from HLTV. If no parameters provided, returns current month's news.
