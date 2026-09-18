# Frontend Reconstruction Baseline Audit (Pre-Implementation)

Date: 2026-09-09
Workspace: `C:\SourceCode\MatchGenomeIPL`

## 1) Existing Route Semantics (hash routing in `web/app.js`)

- `view=home` -> `#homeView`
- `view=ask` -> `#askView`
- `view=matches|fixtures|results` -> `#fixturesView` (tab controls via `tab`)
- `view=teams` -> `#teamsView`
- `view=stats` -> `#statsView` (tab controls via `tab`)
- `view=predict` -> `#predictView`
- `view=replay|time_machine` -> `#timeMachineView`
- `view=player` -> `#playerView`
- `view=methodology` -> `#methodologyView`

Route params in use: `tab`, `player`, `season_id`, `match_id`, `status`, `team`, `origin`, `question`.

## 2) Primary Preserved IDs / Hooks

Top nav + entry:
- `goHomeBtn`, `goMatchesBtn`, `goReplayBtn`, `goAskBtn`, `goTeamsBtn`, `goPlayerIntelligenceBtn`, `goStatsBtn`, `goPredictBtn`

Home:
- `homeAskInput`, `homeAskBtn`, `homeAskPrompts`, `homeSeasonTag`, `homeUpcoming`, `homeLatest`, `homeSeasonStatus`, `homeTopPerformers`, `homeDataStatement`, `homeGenomePath`, `homeSignals`, `homeFeaturedMatch`, `exploreMatchBtn`, `goTeamsIntroBtn`, `goPlayersIntroBtn`, `homeReplaySeasonSelect`, `homeReplayBtn`, `homeDiscoveryStrip`

Ask:
- `askInput`, `askSubmitBtn`, `askExamples`, `askResults`

Matches:
- `fixturesSeasonSelect`, `fixturesTeamInput`, `fixturesStatusSelect`, `fixturesRefreshBtn`, `matchTabFixturesBtn`, `matchTabResultsBtn`, `fixturesList`, `resultsList`, `fixtureDetail`

Teams:
- `teamsSelect`, `teamSeasonSelect`, `teamLoadBtn`, `teamDetails`

Stats:
- `statsSeasonSelect`, `statsRefreshBtn`, tab IDs (`statsTab*`), panel IDs (`statsPanel*`), blocks (`statsOverviewBlock`, `statsBattingBlock`, `statsBowlingBlock`, `statsRecordsBlock`, `statsGraphsBlock`, `pointsTableBlock`)

Replay / Time Machine:
- discovery controls (`seasonSelect`, `matchSearchInput`, `teamFilterSelect`, `inningsSelect`, `matchCards`, `startReplayBtn`)
- replay controls (`predictBtn`, `revealBtn`, `restartBtn`, `nextBtn`, `previousBtn`)
- tabs/panels (`tabPredictionBtn`, `tabBallByBallBtn`, `tabEvidenceBtn`, `panelPrediction`, `panelBallByBall`, `panelEvidence`)
- replay data IDs preserved (`predictedTop`, `predictedPct`, `probabilityBars`, `actualBlock`, `whyBlock`, `changeBlock`, etc.)

Player:
- search (`playerSearchInput`, `playerSearchBtn`, `playerSearchResults`)
- profile (`playerPanel`, `playerPhoto`, `playerAvatar`, `playerName`, `playerRole`, `playerCareerContext`, `playerPhotoMeta`, `playerContextText`)
- actions (`backToReplayBtn`, `exploreReplayBtn`, `closePlayerBtn`)
- tabs and panels (`playerTab*`, `playerPanel*`, `playerOverview`, `playerBatting`, `playerBowling`, `playerMatchups`, `playerSeasons`, `playerPhases`)

## 3) Existing API Calls from Frontend (`web/app.js`)

- `GET /api/seasons`
- `GET /api/seasons/{season_id}/matches`
- `GET /api/fixtures?season_id=&team=&status=`
- `GET /api/results?season_id=&team=`
- `GET /api/matches/{match_id}`
- `GET /api/matches/{match_id}/innings`
- `GET /api/matches/{match_id}/scorecard`
- `GET /api/teams`
- `GET /api/teams/{team}?season_id=`
- `GET /api/stats/overview?season_id=`
- `GET /api/stats/leaderboards?season_id=&limit=`
- `GET /api/stats/top-performers?season_id=&limit=`
- `GET /api/stats/points-table?season_id=`
- `POST /api/ask`
- `GET /api/players?query=&limit=`
- `GET /api/players/{player_name}?session_id=`
- `POST /api/replays` and session endpoints (`/predict`, `/reveal`, `/restart`)

## 4) Baseline Browser/Selenium Validation Run

Command run:
- `python -u scripts/visual_qa_runtime.py`
- `python -u scripts/trust_browser_validation.py`

Result highlights:
- Functional navigation path loads all core surfaces.
- Replay lifecycle runs (select match -> start replay -> predict -> reveal -> evidence/ball-by-ball).
- Ask flow returns answer/trust blocks and supports unsupported-question path.
- No horizontal overflow reported by runtime checks.

Baseline report artifacts:
- `artifacts/visual_qa/visual_qa_report.json`
- `artifacts/trust_browser_validation/*.png`

Required viewport screenshot baseline captured by runtime:
- `1440x900` (`desktop_1440x900_*`)
- `1280x800` (`desktop_1280x800_*`)
- `1024x768` (`tablet_1024x768_*`)
- `768x1024` (`tablet_768x1024_*`)
- `390x844` (`mobile_390x844_*`)

## 5) Structural Areas Marked for Full Composition Replacement

- Home composition (hero, discovery, context, timeline, relationship visualization, future transition)
- Ask composition (intelligence search-first with layered reveal hierarchy)
- Matches surface (event discovery over filter-first list dominance)
- Match detail composition (match story progression vs table-first)
- Teams and Players first viewport hierarchy (identity + arc first)
- Stats first viewport (insight narrative before table inspection)
- Replay composition (prediction theatre + user call + reveal)
- Global shell/nav hierarchy and contextual journey framing

All backend/data/API route semantics remain unchanged.
