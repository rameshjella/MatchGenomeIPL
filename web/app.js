const UiState = {
  SELECT_MATCH: "SELECT_MATCH",
  READY: "READY",
  PREDICTION_AVAILABLE: "PREDICTION_AVAILABLE",
  PREDICTION_REVEALED: "PREDICTION_REVEALED",
  COMPLETED: "COMPLETED",
  ERROR: "ERROR",
};

let revealObserver = null;

const api = {
  async get(path) {
    const res = await fetch(path, { headers: { Accept: "application/json" } });
    const body = await res.json();
    if (!res.ok) throw new Error(body?.error?.message || `Request failed: ${res.status}`);
    return body;
  },
  async post(path, payload) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(payload || {}),
    });
    const body = await res.json();
    if (!res.ok) throw new Error(body?.error?.message || `Request failed: ${res.status}`);
    return body;
  },
};

const state = {
  view: "home",
  matchesTab: "fixtures",
  statsTab: "overview",
  uiState: UiState.SELECT_MATCH,
  replayTab: "prediction",
  playerTab: "overview",
  seasons: [],
  matches: [],
  innings: [],
  selectedMatchId: null,
  selectedMatch: null,
  selectedInnings: null,
  sessionId: null,
  sessionMeta: null,
  lastPrediction: null,
  timeline: [],
  selectedTimelineIndex: -1,
  activePlayer: null,
  playerCapabilities: { hasBatting: false, hasBowling: false },
  hasTeamIdOnlyData: false,
  teams: [],
  teamAssetIndex: {},
  selectedFixtureMatchId: null,
  askContextQuestion: "",
  contextOrigin: "",
  latestSeasonId: null,
  homeSelectedSeason: null,
  userCall: null,
};

const els = {
  homeView: document.getElementById("homeView"),
  predictView: document.getElementById("predictView"),
  askView: document.getElementById("askView"),
  fixturesView: document.getElementById("fixturesView"),
  teamsView: document.getElementById("teamsView"),
  statsView: document.getElementById("statsView"),
  timeMachineView: document.getElementById("timeMachineView"),
  playerView: document.getElementById("playerView"),
  methodologyView: document.getElementById("methodologyView"),
  statusBanner: document.getElementById("statusBanner"),

  goHomeBtn: document.getElementById("goHomeBtn"),
  goMatchesBtn: document.getElementById("goMatchesBtn"),
  goTeamsBtn: document.getElementById("goTeamsBtn"),
  goPredictBtn: document.getElementById("goPredictBtn"),
  goStatsBtn: document.getElementById("goStatsBtn"),
  goReplayBtn: document.getElementById("goReplayBtn"),
  goAskBtn: document.getElementById("goAskBtn"),
  goPlayerIntelligenceBtn: document.getElementById("goPlayerIntelligenceBtn"),

  exploreMatchBtn: document.getElementById("exploreMatchBtn"),
  goTeamsIntroBtn: document.getElementById("goTeamsIntroBtn"),
  goPlayersIntroBtn: document.getElementById("goPlayersIntroBtn"),
  homeAskInput: document.getElementById("homeAskInput"),
  homeAskBtn: document.getElementById("homeAskBtn"),
  homeUpcoming: document.getElementById("homeUpcoming"),
  homeLatest: document.getElementById("homeLatest"),
  homeSeasonStatus: document.getElementById("homeSeasonStatus"),
  homeSeasonTag: document.getElementById("homeSeasonTag"),
  homeDataStatement: document.getElementById("homeDataStatement"),
  homeSignals: document.getElementById("homeSignals"),
  homeGenomePath: document.getElementById("homeGenomePath"),
  homeReplaySeasonSelect: document.getElementById("homeReplaySeasonSelect"),
  homeReplayBtn: document.getElementById("homeReplayBtn"),
  homeAskPrompts: document.getElementById("homeAskPrompts"),
  homeFeaturedMatch: document.getElementById("homeFeaturedMatch"),
  homeTopPerformers: document.getElementById("homeTopPerformers"),
  homeDiscoveryStrip: document.getElementById("homeDiscoveryStrip"),
  homeSeasonTimeline: document.getElementById("homeSeasonTimeline"),
  homeSeasonStory: document.getElementById("homeSeasonStory"),
  homeContextPill: document.getElementById("homeContextPill"),
  contextBreadcrumb: document.getElementById("contextBreadcrumb"),

  askInput: document.getElementById("askInput"),
  askSubmitBtn: document.getElementById("askSubmitBtn"),
  askExamples: document.getElementById("askExamples"),
  askResults: document.getElementById("askResults"),

  fixturesSeasonSelect: document.getElementById("fixturesSeasonSelect"),
  fixturesTeamInput: document.getElementById("fixturesTeamInput"),
  fixturesStatusSelect: document.getElementById("fixturesStatusSelect"),
  fixturesRefreshBtn: document.getElementById("fixturesRefreshBtn"),
  fixturesList: document.getElementById("fixturesList"),
  resultsList: document.getElementById("resultsList"),
  matchTabFixturesBtn: document.getElementById("matchTabFixturesBtn"),
  matchTabResultsBtn: document.getElementById("matchTabResultsBtn"),
  fixtureDetail: document.getElementById("fixtureDetail"),

  predictToReplayBtn: document.getElementById("predictToReplayBtn"),
  predictToPlayersBtn: document.getElementById("predictToPlayersBtn"),
  predictToAskBtn: document.getElementById("predictToAskBtn"),

  teamsSelect: document.getElementById("teamsSelect"),
  teamSeasonSelect: document.getElementById("teamSeasonSelect"),
  teamLoadBtn: document.getElementById("teamLoadBtn"),
  teamDetails: document.getElementById("teamDetails"),

  statsSeasonSelect: document.getElementById("statsSeasonSelect"),
  statsRefreshBtn: document.getElementById("statsRefreshBtn"),
  statsTabOverviewBtn: document.getElementById("statsTabOverviewBtn"),
  statsTabBattingBtn: document.getElementById("statsTabBattingBtn"),
  statsTabBowlingBtn: document.getElementById("statsTabBowlingBtn"),
  statsTabRecordsBtn: document.getElementById("statsTabRecordsBtn"),
  statsTabGraphsBtn: document.getElementById("statsTabGraphsBtn"),
  statsTabPointsBtn: document.getElementById("statsTabPointsBtn"),
  statsPanelOverview: document.getElementById("statsPanelOverview"),
  statsPanelBatting: document.getElementById("statsPanelBatting"),
  statsPanelBowling: document.getElementById("statsPanelBowling"),
  statsPanelRecords: document.getElementById("statsPanelRecords"),
  statsPanelGraphs: document.getElementById("statsPanelGraphs"),
  statsPanelPoints: document.getElementById("statsPanelPoints"),
  statsOverviewBlock: document.getElementById("statsOverviewBlock"),
  statsBattingBlock: document.getElementById("statsBattingBlock"),
  statsBowlingBlock: document.getElementById("statsBowlingBlock"),
  statsRecordsBlock: document.getElementById("statsRecordsBlock"),
  statsGraphsBlock: document.getElementById("statsGraphsBlock"),
  pointsTableBlock: document.getElementById("pointsTableBlock"),
  statsCompareSeasonA: document.getElementById("statsCompareSeasonA"),
  statsCompareSeasonB: document.getElementById("statsCompareSeasonB"),
  statsCompareBtn: document.getElementById("statsCompareBtn"),
  statsCompareBlock: document.getElementById("statsCompareBlock"),

  seasonSelect: document.getElementById("seasonSelect"),
  matchSearchInput: document.getElementById("matchSearchInput"),
  teamFilterSelect: document.getElementById("teamFilterSelect"),
  inningsSelect: document.getElementById("inningsSelect"),
  matchListSummary: document.getElementById("matchListSummary"),
  selectedMatchMeta: document.getElementById("selectedMatchMeta"),
  teamDataNotice: document.getElementById("teamDataNotice"),
  matchCards: document.getElementById("matchCards"),
  startReplayBtn: document.getElementById("startReplayBtn"),

  replayPanel: document.getElementById("replayPanel"),
  replayBanner: document.getElementById("replayBanner"),
  matchTitle: document.getElementById("matchTitle"),
  matchSubline: document.getElementById("matchSubline"),
  replayTeamNotice: document.getElementById("replayTeamNotice"),
  teamsValue: document.getElementById("teamsValue"),
  inningsValue: document.getElementById("inningsValue"),
  scoreValue: document.getElementById("scoreValue"),
  overBallValue: document.getElementById("overBallValue"),
  progressHeaderValue: document.getElementById("progressHeaderValue"),
  accuracyValue: document.getElementById("accuracyValue"),

  tabPredictionBtn: document.getElementById("tabPredictionBtn"),
  tabBallByBallBtn: document.getElementById("tabBallByBallBtn"),
  tabEvidenceBtn: document.getElementById("tabEvidenceBtn"),
  panelPrediction: document.getElementById("panelPrediction"),
  panelBallByBall: document.getElementById("panelBallByBall"),
  panelEvidence: document.getElementById("panelEvidence"),

  batterValue: document.getElementById("batterValue"),
  nonStrikerValue: document.getElementById("nonStrikerValue"),
  bowlerValue: document.getElementById("bowlerValue"),
  phaseValue: document.getElementById("phaseValue"),
  stateScoreValue: document.getElementById("stateScoreValue"),
  stateWicketsValue: document.getElementById("stateWicketsValue"),
  stateBallsValue: document.getElementById("stateBallsValue"),
  stateRrValue: document.getElementById("stateRrValue"),
  stateReqRrValue: document.getElementById("stateReqRrValue"),
  statePressureValue: document.getElementById("statePressureValue"),
  predictedTop: document.getElementById("predictedTop"),
  predictedPct: document.getElementById("predictedPct"),
  probabilityBars: document.getElementById("probabilityBars"),
  userCallOptions: document.getElementById("userCallOptions"),
  userCallSummary: document.getElementById("userCallSummary"),
  whyBlock: document.getElementById("whyBlock"),
  changeBlock: document.getElementById("changeBlock"),
  predictBtn: document.getElementById("predictBtn"),
  revealBtn: document.getElementById("revealBtn"),
  restartBtn: document.getElementById("restartBtn"),
  nextBtn: document.getElementById("nextBtn"),
  previousBtn: document.getElementById("previousBtn"),
  actualBlock: document.getElementById("actualBlock"),

  progressValue: document.getElementById("progressValue"),
  prevBallValue: document.getElementById("prevBallValue"),
  nextBallValue: document.getElementById("nextBallValue"),
  progressFill: document.getElementById("progressFill"),
  timelineTrack: document.getElementById("timelineTrack"),
  ballByBallRows: document.getElementById("ballByBallRows"),
  predictionLedger: document.getElementById("predictionLedger"),

  evidenceBlock: document.getElementById("evidenceBlock"),
  distributionBlock: document.getElementById("distributionBlock"),
  technicalEvidenceBlock: document.getElementById("technicalEvidenceBlock"),

  backToReplayBtn: document.getElementById("backToReplayBtn"),
  playerSearchInput: document.getElementById("playerSearchInput"),
  playerSearchBtn: document.getElementById("playerSearchBtn"),
  playerSearchHint: document.getElementById("playerSearchHint"),
  playerSearchResults: document.getElementById("playerSearchResults"),
  playerDiscovery: document.getElementById("playerDiscovery"),
  playerPrompt: document.getElementById("playerPrompt"),
  playerPanel: document.getElementById("playerPanel"),
  playerPhoto: document.getElementById("playerPhoto"),
  playerAvatar: document.getElementById("playerAvatar"),
  playerName: document.getElementById("playerName"),
  playerRole: document.getElementById("playerRole"),
  playerCareerContext: document.getElementById("playerCareerContext"),
  playerPhotoMeta: document.getElementById("playerPhotoMeta"),
  playerContextText: document.getElementById("playerContextText"),
  exploreReplayBtn: document.getElementById("exploreReplayBtn"),
  closePlayerBtn: document.getElementById("closePlayerBtn"),

  playerTabOverviewBtn: document.getElementById("playerTabOverviewBtn"),
  playerTabBattingBtn: document.getElementById("playerTabBattingBtn"),
  playerTabBowlingBtn: document.getElementById("playerTabBowlingBtn"),
  playerTabMatchupsBtn: document.getElementById("playerTabMatchupsBtn"),
  playerTabSeasonsBtn: document.getElementById("playerTabSeasonsBtn"),
  playerTabPhasesBtn: document.getElementById("playerTabPhasesBtn"),

  playerPanelOverview: document.getElementById("playerPanelOverview"),
  playerPanelBatting: document.getElementById("playerPanelBatting"),
  playerPanelBowling: document.getElementById("playerPanelBowling"),
  playerPanelMatchups: document.getElementById("playerPanelMatchups"),
  playerPanelSeasons: document.getElementById("playerPanelSeasons"),
  playerPanelPhases: document.getElementById("playerPanelPhases"),

  playerOverview: document.getElementById("playerOverview"),
  playerBatting: document.getElementById("playerBatting"),
  playerBowling: document.getElementById("playerBowling"),
  playerMatchups: document.getElementById("playerMatchups"),
  playerSeasons: document.getElementById("playerSeasons"),
  playerPhases: document.getElementById("playerPhases"),
};

function parseRoute() {
  const params = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  return {
    view: params.get("view") || "home",
    tab: params.get("tab") || "",
    player: params.get("player") || "",
    seasonId: params.get("season_id") || "",
    matchId: params.get("match_id") || "",
    status: params.get("status") || "",
    team: params.get("team") || "",
    origin: params.get("origin") || "",
    question: params.get("question") || "",
  };
}

function humanTrustLabel(overallTrust) {
  if (overallTrust === "TRUSTED_OFFICIAL_RECONCILED") return "Official reference reconciled";
  if (overallTrust === "TRUSTED_INTERNAL_WITH_DEFINITION_NOTE") return "Internally validated · official reference reconciled with definition note";
  if (overallTrust === "TRUSTED_INTERNAL") return "Internally validated";
  if (overallTrust === "REFERENCE_LIMITED") return "Internally validated · independent official reference unavailable";
  if (overallTrust === "UNTRUSTED") return "Untrusted";
  return "Internally validated";
}

function setRoute(route) {
  const params = new URLSearchParams();
  Object.entries(route).forEach(([k, v]) => {
    if (v !== undefined && v !== null && String(v) !== "") params.set(k, String(v));
  });
  window.location.hash = params.toString();
}

function normalizeSeason(value) {
  const num = Number(value || 0);
  return Number.isFinite(num) && num > 0 ? num : null;
}

function latestSeasonFromState() {
  const seasons = (state.seasons || []).map((s) => normalizeSeason(s.season_id)).filter(Boolean);
  if (!seasons.length) return null;
  return seasons.sort((a, b) => a - b)[seasons.length - 1];
}

function sanitizeUiError(message, fallback = "MatchGenome could not complete that step right now.") {
  const text = String(message || "").trim();
  if (!text) return fallback;
  const blockedPatterns = [
    /int\(\) argument/i,
    /NoneType/i,
    /Traceback/i,
    /internal_error/i,
    /invalid_request/i,
    /Request failed:/i,
  ];
  if (blockedPatterns.some((pattern) => pattern.test(text))) {
    return fallback;
  }
  return text;
}

function setStatus(message, kind = "info") {
  els.statusBanner.hidden = false;
  const fallback = kind === "error" ? "MatchGenome could not complete that step right now." : String(message || "");
  els.statusBanner.textContent = kind === "error" ? sanitizeUiError(message, fallback) : String(message || "");
  els.statusBanner.style.borderLeftColor = kind === "error" ? "#cc4d4d" : "#5a84ff";
}

function clearStatus() {
  els.statusBanner.hidden = true;
}

function isNumericToken(value) {
  return /^\d+$/.test(String(value || "").trim());
}

function teamLabel(name, fallback) {
  if (!name || !String(name).trim()) return fallback;
  const raw = String(name).trim();
  return isNumericToken(raw) ? `Team ${raw}` : raw;
}

function hasUnresolvedTeamName(teamName) {
  return isNumericToken(teamName);
}

function toPct(value) {
  return `${(Number(value || 0) * 100).toFixed(1)}%`;
}

function toOverNotation(legalBalls) {
  const balls = Number(legalBalls || 0);
  return `${Math.floor(balls / 6)}.${balls % 6}`;
}

function outcomeDisplay(label) {
  if (!label || label === "-") return "-";
  if (label === "wicket") return "Wicket";
  if (label === "3+") return "3+ runs";
  if (label === "0") return "0 runs";
  if (label === "1") return "1 run";
  return `${label} runs`;
}

function metricDisplay(value) {
  return value === null || value === undefined ? "-" : String(value);
}

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function capitalize(value) {
  if (!value) return "-";
  return `${value}`.charAt(0).toUpperCase() + `${value}`.slice(1);
}

function updateContextBreadcrumb() {
  if (!els.contextBreadcrumb) return;
  const bits = [];
  const homeSeason = normalizeSeason(state.homeSelectedSeason || state.latestSeasonId);
  if (homeSeason) bits.push(`IPL ${homeSeason}`);
  if (state.selectedMatch) {
    bits.push(matchTitleFromMeta(state.selectedMatch));
    bits.push(`Match ${state.selectedMatch.match_number || state.selectedMatch.season_match_number || "-"}`);
  }
  if (state.lastPrediction?.delivery) {
    bits.push(`${state.lastPrediction.delivery.over_number}.${state.lastPrediction.delivery.ball_number}`);
  }
  els.contextBreadcrumb.textContent = bits.length ? bits.join(" -> ") : "IPL Chronicle -> Match Moment -> Genome -> Forecast -> Reveal";
}

function setView(view) {
  state.view = view;
  const map = {
    home: els.homeView,
    predict: els.predictView,
    ask: els.askView,
    matches: els.fixturesView,
    teams: els.teamsView,
    stats: els.statsView,
    replay: els.timeMachineView,
    player: els.playerView,
    methodology: els.methodologyView,
  };
  Object.entries(map).forEach(([name, node]) => {
    if (!node) return;
    node.hidden = name !== view;
  });

  const nav = [
    [els.goHomeBtn, view === "home"],
    [els.goMatchesBtn, view === "matches"],
    [els.goTeamsBtn, view === "teams"],
    [els.goPredictBtn, view === "predict"],
    [els.goStatsBtn, view === "stats"],
    [els.goReplayBtn, view === "replay"],
    [els.goAskBtn, view === "ask"],
    [els.goPlayerIntelligenceBtn, view === "player"],
  ];
  nav.forEach(([button, active]) => {
    if (!button) return;
    button.classList.toggle("primary", active);
    button.setAttribute("aria-current", active ? "page" : "false");
  });

  updateContextBreadcrumb();
  installRevealForView(view);
}

function installRevealForView(view) {
  if (!window.IntersectionObserver) return;
  if (revealObserver) {
    revealObserver.disconnect();
  }
  const root = {
    home: els.homeView,
    ask: els.askView,
    matches: els.fixturesView,
    teams: els.teamsView,
    stats: els.statsView,
    replay: els.timeMachineView,
    player: els.playerView,
    predict: els.predictView,
  }[view];
  if (!root) return;

  const nodes = root.querySelectorAll(".reveal-step");
  revealObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("visible");
          revealObserver.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.08, rootMargin: "0px 0px -8% 0px" },
  );

  nodes.forEach((node) => {
    node.classList.add("is-reveal");
    revealObserver.observe(node);
  });
}

function formatMatchCard(item) {
  const winner = item.winner ? `Winner: ${item.winner}` : "Winner: pending";
  const matchId = Number(item.match_id || 0);
  const active = state.selectedFixtureMatchId === matchId ? "active" : "";
  return `
    <article class='panel-block fixture-card ${active}' data-match-id='${matchId}'>
      <div class='match-teams'>
        <strong>${renderTeamLogo(teamLabel(item.team_a, "Team A"))} <span>${teamLabel(item.team_a, "Team A")}</span></strong>
        <span>vs</span>
        <strong><span>${teamLabel(item.team_b, "Team B")}</span> ${renderTeamLogo(teamLabel(item.team_b, "Team B"))}</strong>
      </div>
      <p class='muted'>${item.match_date || "Date unknown"} · IPL ${item.season_id} · Match ${item.match_number || "-"}</p>
      <p class='muted'>${item.venue || "Venue unavailable"}${item.city ? `, ${item.city}` : ""}</p>
      <p class='muted'>${capitalize(item.status)} · ${winner}</p>
      <div class='row-actions'><button type='button' class='fixture-open-chip' data-match-id='${matchId}'>Open match details</button></div>
    </article>
  `;
}

function fixturesRoute(matchId = "") {
  return {
    view: "matches",
    tab: state.matchesTab,
    season_id: Number(els.fixturesSeasonSelect.value || 0) || "",
    status: (els.fixturesStatusSelect.value || "").trim(),
    team: (els.fixturesTeamInput.value || "").trim(),
    match_id: matchId,
  };
}

function setMatchesTab(tab) {
  state.matchesTab = tab === "results" ? "results" : "fixtures";
  if (els.matchTabFixturesBtn) {
    els.matchTabFixturesBtn.classList.toggle("active", state.matchesTab === "fixtures");
  }
  if (els.matchTabResultsBtn) {
    els.matchTabResultsBtn.classList.toggle("active", state.matchesTab === "results");
  }
  els.fixturesList.hidden = state.matchesTab !== "fixtures";
  if (els.resultsList) {
    els.resultsList.hidden = state.matchesTab !== "results";
  }
}

function setStatsTab(tab) {
  const normalized = ["overview", "batting", "bowling", "records", "graphs", "points"].includes(tab) ? tab : "overview";
  state.statsTab = normalized;
  const tabs = [
    [els.statsTabOverviewBtn, els.statsPanelOverview, normalized === "overview"],
    [els.statsTabBattingBtn, els.statsPanelBatting, normalized === "batting"],
    [els.statsTabBowlingBtn, els.statsPanelBowling, normalized === "bowling"],
    [els.statsTabRecordsBtn, els.statsPanelRecords, normalized === "records"],
    [els.statsTabGraphsBtn, els.statsPanelGraphs, normalized === "graphs"],
    [els.statsTabPointsBtn, els.statsPanelPoints, normalized === "points"],
  ];
  tabs.forEach(([btn, panel, active]) => {
    if (!btn || !panel) return;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-selected", active ? "true" : "false");
    panel.hidden = !active;
  });
}

function focusFixtureDetail() {
  els.fixtureDetail.scrollIntoView({ behavior: "smooth", block: "start" });
  els.fixtureDetail.focus({ preventScroll: true });
}

async function loadFixtures() {
  const season = Number(els.fixturesSeasonSelect.value || 0);
  const team = (els.fixturesTeamInput.value || "").trim();
  const status = (els.fixturesStatusSelect.value || "").trim();
  const q = [`season_id=${season}`];
  if (team) q.push(`team=${encodeURIComponent(team)}`);
  if (status) q.push(`status=${encodeURIComponent(status)}`);
  const payload = await api.get(`/api/fixtures?${q.join("&")}`);
  const rows = payload.fixtures || [];
  els.fixturesList.innerHTML = rows.length ? rows.map(formatMatchCard).join("") : "<p class='muted'>No matches found for this filter.</p>";
  els.fixturesList.querySelectorAll(".fixture-card").forEach((node) => {
    node.addEventListener("click", () => {
      const matchId = Number(node.getAttribute("data-match-id") || 0);
      if (!matchId) return;
      state.selectedFixtureMatchId = matchId;
      els.fixturesList.querySelectorAll(".fixture-card").forEach((card) => card.classList.remove("active"));
      node.classList.add("active");
      setRoute(fixturesRoute(matchId));
      loadFixtureDetail(matchId).catch((err) => setStatus(err.message || "Failed to load match details", "error"));
    });
  });
  els.fixturesList.querySelectorAll(".fixture-open-chip").forEach((node) => {
    node.addEventListener("click", (event) => {
      event.stopPropagation();
      const matchId = Number(node.getAttribute("data-match-id") || 0);
      if (!matchId) return;
      setRoute(fixturesRoute(matchId));
      loadFixtureDetail(matchId).catch((err) => setStatus(err.message || "Failed to load match details", "error"));
    });
  });
}

async function loadResults() {
  const season = Number(els.fixturesSeasonSelect.value || 0);
  const team = (els.fixturesTeamInput.value || "").trim();
  const q = [`season_id=${season}`];
  if (team) q.push(`team=${encodeURIComponent(team)}`);
  const payload = await api.get(`/api/results?${q.join("&")}`);
  const rows = payload.results || [];
  if (!els.resultsList) return;
  els.resultsList.innerHTML = rows.length ? rows.map(formatMatchCard).join("") : "<p class='muted'>No completed matches found for this filter.</p>";
  els.resultsList.querySelectorAll(".fixture-card").forEach((node) => {
    node.addEventListener("click", () => {
      const matchId = Number(node.getAttribute("data-match-id") || 0);
      if (!matchId) return;
      state.selectedFixtureMatchId = matchId;
      setRoute(fixturesRoute(matchId));
      loadFixtureDetail(matchId).catch((err) => setStatus(err.message || "Failed to load match details", "error"));
    });
  });
}

async function loadFixtureDetail(matchId) {
  state.selectedFixtureMatchId = Number(matchId || 0) || null;
  const [match, innings, scorecard] = await Promise.all([
    api.get(`/api/matches/${matchId}`),
    api.get(`/api/matches/${matchId}/innings`),
    api.get(`/api/matches/${matchId}/scorecard`),
  ]);
  const meta = match.metadata || {};
  const outcome = meta.outcome || {};
  const toss = meta.toss || {};
  const askContext = state.contextOrigin === "ask" && state.askContextQuestion
    ? `<p class='muted'>Context: reached from Ask - "${escapeHtml(state.askContextQuestion)}"</p>`
    : "";
  const inningsRows = (innings.innings || []);
  const inningsScorecard = Array.isArray(scorecard.innings) ? scorecard.innings : [];
  const firstInnings = inningsRows[0] || null;
  const secondInnings = inningsRows[1] || null;
  const stage = meta.match_type || "IPL";
  const resultLine = outcome.winner
    ? `${teamLabel(outcome.winner, "Winner")} won${outcome.result_margin ? ` by ${outcome.result_margin} ${outcome.result_type || ""}` : ""}`
    : "Result pending";

  const topBatter = inningsScorecard
    .flatMap((item) => item.batting || [])
    .sort((a, b) => Number(b.runs || 0) - Number(a.runs || 0))[0] || null;
  const topBowler = inningsScorecard
    .flatMap((item) => item.bowling || [])
    .sort((a, b) => Number(b.wickets || 0) - Number(a.wickets || 0))[0] || null;

  const turningPlayer = outcome.player_of_match || topBatter?.player || topBowler?.player || "Impact player unavailable";
  const pressureGap = firstInnings && secondInnings ? Math.abs(Number(firstInnings.runs || 0) - Number(secondInnings.runs || 0)) : 0;
  const lowEvidence = !outcome.player_of_match || !topBatter || !topBowler;

  const moments = [
    {
      key: "toss",
      label: "MATCH STATE",
      marker: "PRE-MATCH",
      event: toss.winner ? `${teamLabel(toss.winner, "Unknown")} won toss${toss.decision ? ` and chose ${toss.decision}` : ""}` : "Toss context unavailable",
      impact: "Set opening match conditions",
      player: toss.winner ? teamLabel(toss.winner, "Unknown") : "-",
      signal: "Source: metadata toss record",
      size: "base",
    },
    {
      key: "innings1",
      label: "SETUP",
      marker: firstInnings ? `INN 1 · ${toOverNotation(firstInnings.legal_balls)}` : "INN 1",
      event: firstInnings
        ? `${teamLabel(firstInnings.team_batting, "Team")} posted ${firstInnings.runs}/${firstInnings.wickets}`
        : "First-innings score context unavailable",
      impact: secondInnings ? `Target created for chase (${Number(firstInnings?.runs || 0) + 1})` : "Target context unavailable",
      player: topBatter?.player || "-",
      signal: "Source: innings summary totals",
      size: "base",
    },
    {
      key: "batting_peak",
      label: "SIGNIFICANT MOMENT",
      marker: topBatter ? `${topBatter.balls || "-"} BALLS` : "BATTER PEAK",
      event: topBatter ? `${topBatter.player} scored ${topBatter.runs} (${topBatter.balls})` : "Top batting contribution unavailable",
      impact: topBatter ? `Boundary pressure: ${topBatter.fours || 0} fours, ${topBatter.sixes || 0} sixes` : "Boundary impact unavailable",
      player: topBatter?.player || "-",
      signal: "Source: innings batting scorecard",
      size: "major",
    },
    {
      key: "bowling_peak",
      label: "TURNING POINT",
      marker: topBowler ? `${topBowler.overs || "-"} OVERS` : "BOWLING SPELL",
      event: topBowler ? `${topBowler.player} took ${topBowler.wickets} wickets` : "Top bowling spell unavailable",
      impact: pressureGap ? `Run pressure swing: ${pressureGap} runs` : "Pressure swing unavailable",
      player: topBowler?.player || turningPlayer,
      signal: lowEvidence ? "LIMITED EVIDENCE · partial scorecard support" : "Source: bowling spell + innings pressure",
      size: "major",
    },
    {
      key: "result",
      label: "RESULT",
      marker: "FULL TIME",
      event: resultLine,
      impact: outcome.player_of_match ? `Player of match: ${outcome.player_of_match}` : "Player of match unavailable",
      player: outcome.player_of_match || turningPlayer,
      signal: "Source: official result metadata",
      size: "major",
    },
  ];

  const keyMoment = moments.find((moment) => moment.key === "bowling_peak") || moments[0];

  const renderMoment = (moment) => `
    <article class='match-moment-object ${moment.size === "major" ? "major" : ""}'>
      <p class='eyebrow'>${moment.label}</p>
      <p class='moment-over'>${escapeHtml(moment.marker)}</p>
      <p><strong>${escapeHtml(moment.event)}</strong></p>
      <p class='muted'>Player: ${escapeHtml(moment.player)}</p>
      <p>Impact: ${escapeHtml(moment.impact)}</p>
      <p class='muted'>MatchGenome signal: ${escapeHtml(moment.signal)}</p>
      <div class='row-actions'>
        <button type='button' class='quick-link moment-replay-link'>Replay this moment</button>
        <button type='button' class='quick-link moment-ask-link'>Ask about this moment</button>
        ${moment.player && moment.player !== "-" ? `<button type='button' class='quick-link moment-player-link' data-player='${encodeURIComponent(moment.player)}'>Open player genome</button>` : ""}
      </div>
    </article>
  `;

  const renderRows = (rows, columns) => {
    if (!rows.length) return "<p class='muted'>No rows available.</p>";
    return `<div class='table-wrap'><table class='mini-table'><thead><tr>${columns.map((c) => `<th>${c.label}</th>`).join("")}</tr></thead><tbody>${rows
      .map((row) => `<tr>${columns.map((c) => `<td>${metricDisplay(row[c.key])}</td>`).join("")}</tr>`)
      .join("")}</tbody></table></div>`;
  };
  const teamsLine = `${teamLabel(meta.team_a_display, "Team A")} vs ${teamLabel(meta.team_b_display, "Team B")}`;
  els.fixtureDetail.innerHTML = `
    <p class='eyebrow'>THE MATCH UNFOLDS</p>
    <section class='match-detail-hero'>
      <h4>${teamsLine}</h4>
      <p class='match-stage'>${escapeHtml(stage)}</p>
      <p class='match-result-line'>${escapeHtml(resultLine.toUpperCase())}</p>
      <p class='muted'>${meta.match_date || "Date unknown"} · ${meta.venue || "Venue unknown"}${meta.city ? `, ${meta.city}` : ""}</p>
      <p class='muted'>IPL ${match.season_id} / Match ${meta.match_number || "-"}</p>
      ${askContext}
    </section>

    <section class='match-key-moment'>
      <p class='eyebrow'>KEY MOMENT</p>
      ${renderMoment(keyMoment)}
    </section>

    <section class='match-phase-timeline'>
      <p class='eyebrow'>SIGNIFICANT MOMENTS</p>
      <div class='match-phase-line'>
        ${moments
          .map((moment, index) => `<button type='button' class='match-phase-node ${keyMoment.key === moment.key || (index === 0 && !keyMoment.key) ? "active" : ""} ${moment.size === "major" ? "major" : ""}' data-phase='${moment.key}'>${moment.label}</button>`)
          .join("<span class='phase-divider' aria-hidden='true'></span>")}
      </div>
      <div id='matchMomentStage' class='match-moment-stage'>${renderMoment(keyMoment)}</div>
    </section>

    <section class='match-intelligence-note'>
      <p class='eyebrow'>WHY DID THIS MATTER?</p>
      <p>${lowEvidence ? "LIMITED EVIDENCE" : "STRONG SIGNAL"} · This sequence is built from verified toss/result metadata and innings scorecard evidence, not inferred ball-by-ball events.</p>
      <p class='muted'>Toss: ${teamLabel(toss.winner, "Unknown")} ${toss.decision ? `(${toss.decision})` : ""} · Player of match: ${outcome.player_of_match || "Unavailable"}</p>
    </section>

    <details class='detail-drawer'>
      <summary>Open innings evidence</summary>
      ${inningsScorecard.length
        ? inningsScorecard
            .map(
              (item) => `
          <details class='detail-drawer' ${Number(item.innings) === 1 ? "open" : ""}>
            <summary>Innings ${item.innings} · ${teamLabel(item.batting_team, "Team")} ${item.score?.runs || 0}/${item.score?.wickets || 0} (${item.score?.overs || "0.0"} ov)</summary>
            <p class='muted'>${teamLabel(item.batting_team, "Team A")} batting vs ${teamLabel(item.bowling_team, "Team B")} bowling</p>
            <h6>Batting</h6>
            ${renderRows(item.batting || [], [
              { key: "player", label: "Player" },
              { key: "runs", label: "R" },
              { key: "balls", label: "B" },
              { key: "fours", label: "4s" },
              { key: "sixes", label: "6s" },
              { key: "strike_rate", label: "SR" },
              { key: "status", label: "Status" },
            ])}
            <h6>Bowling</h6>
            ${renderRows(item.bowling || [], [
              { key: "player", label: "Bowler" },
              { key: "overs", label: "Overs" },
              { key: "runs_conceded", label: "Runs" },
              { key: "wickets", label: "Wkts" },
              { key: "dot_balls", label: "Dots" },
              { key: "economy", label: "Econ" },
            ])}
          </details>`,
            )
            .join("")
        : "<p class='muted'>Scorecard is not available for this match.</p>"}
    </details>

    <div class='row-actions'>
      <button type='button' class='primary' id='openFixtureInTimeMachineBtn'>Enter replay</button>
      <button type='button' id='openFixtureStatsBtn'>Explore season</button>
      <button type='button' id='openFixtureAskBtn'>Ask about this moment</button>
    </div>
  `;

  const phaseByKey = Object.fromEntries(moments.map((moment) => [moment.key, moment]));
  const stageNode = document.getElementById("matchMomentStage");
  els.fixtureDetail.querySelectorAll(".match-phase-node").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.getAttribute("data-phase") || "";
      const phase = phaseByKey[key];
      if (!phase || !stageNode) return;
      els.fixtureDetail.querySelectorAll(".match-phase-node").forEach((node) => node.classList.remove("active"));
      button.classList.add("active");
      stageNode.innerHTML = renderMoment(phase);
      bindMomentActions(phase);
    });
  });

  function bindMomentActions(phase) {
    const replayNodes = els.fixtureDetail.querySelectorAll(".moment-replay-link");
    replayNodes.forEach((node) => {
      node.addEventListener("click", () => {
        setRoute({ view: "replay", season_id: match.season_id, match_id: matchId, origin: "matches" });
      });
    });
    const askNodes = els.fixtureDetail.querySelectorAll(".moment-ask-link");
    askNodes.forEach((node) => {
      node.addEventListener("click", () => {
        els.askInput.value = `Why did ${phase.label.toLowerCase()} matter in IPL ${match.season_id} match ${meta.match_number || matchId}?`;
        setRoute({ view: "ask" });
      });
    });
    const playerNodes = els.fixtureDetail.querySelectorAll(".moment-player-link");
    playerNodes.forEach((node) => {
      node.addEventListener("click", () => {
        const player = decodeURIComponent(node.getAttribute("data-player") || "");
        if (!player) return;
        setRoute({ view: "player", player, origin: "matches", question: `${teamsLine} ${phase.label}` });
      });
    });
  }

  bindMomentActions(keyMoment);
  const btn = document.getElementById("openFixtureInTimeMachineBtn");
  const statsBtn = document.getElementById("openFixtureStatsBtn");
  const askBtn = document.getElementById("openFixtureAskBtn");
  if (btn) {
    btn.addEventListener("click", () => {
      setRoute({ view: "replay", season_id: match.season_id, match_id: matchId });
    });
  }
  if (statsBtn) {
    statsBtn.addEventListener("click", () => setRoute({ view: "stats", tab: "overview", season_id: match.season_id }));
  }
  if (askBtn) {
    askBtn.addEventListener("click", () => {
      els.askInput.value = `What was the result of IPL ${match.season_id} match ${meta.match_number || matchId}?`;
      setRoute({ view: "ask" });
    });
  }
  focusFixtureDetail();
}

async function loadTeams() {
  const payload = await api.get("/api/teams");
  state.teams = payload.teams || [];
  buildTeamAssetIndex(state.teams);
  if (state.matches.length) {
    renderMatchCards();
  }
  els.teamsSelect.innerHTML = "";
  state.teams.forEach((t) => els.teamsSelect.appendChild(option(t.team, t.team)));
  if (!els.teamsSelect.value && state.teams.length) {
    els.teamsSelect.value = String(state.teams[0].team);
  }
}

async function loadTeamDetails() {
  const team = String(els.teamsSelect.value || "");
  const season = Number(els.teamSeasonSelect.value || 0);
  if (!team || !season) return;
  const payload = await api.get(`/api/teams/${encodeURIComponent(team)}?season_id=${season}`);
  const info = payload.team || {};
  const seasonInfo = payload.season || {};
  const squad = Array.isArray(payload.squad) ? payload.squad : [];
  const leader = {
    captain: seasonInfo.captain || "Not available for this season",
    coach: seasonInfo.coach || "Not available for this season",
    owner: seasonInfo.owner || "Not available for this season",
  };
  const trust = String(seasonInfo.verification_status || info.verification_status || "unavailable").toLowerCase();
  const trustLabel = trust === "verified" ? "Verified" : trust === "provisional" ? "Provisional" : "Reference unavailable";
  const sourceLabel = seasonInfo.source || info.source || "Local knowledge layer";
  const trustNote = trust === "verified" ? "Leadership from verified season knowledge." : "Verified leadership is not currently available for this season.";
  const askContext = state.contextOrigin === "ask" && state.askContextQuestion
    ? `<p class='muted'>Context: reached from Ask - "${escapeHtml(state.askContextQuestion)}"</p>`
    : "";

  const squadTop = squad.slice(0, 6);
  const seasonTrail = state.seasons
    .slice(-6)
    .map((s) => `<button type='button' class='season-trail-step ${Number(s.season_id) === season ? "active" : ""}' data-season='${s.season_id}'>${s.season_id}</button>`)
    .join("");

  els.teamDetails.innerHTML = `
    <p class='eyebrow'>TEAM -> SEASON -> LEADERSHIP -> PERFORMANCE</p>
    <div class='title-row'>
      <p><strong>${info.name || team}</strong> · Season ${season}</p>
      <span class='trust-chip'>${trustLabel}</span>
    </div>
    <p class='muted'>${info.short_name || "-"} · Home venue ${info.home_venue || "Not available"}</p>
    ${askContext}
    <div class='event-rail'>
      <p><span>Captain</span><strong>${leader.captain}</strong></p>
      <p><span>Coach</span><strong>${leader.coach}</strong></p>
      <p><span>Owner</span><strong>${leader.owner}</strong></p>
      <p><span>Source</span><strong>${sourceLabel}</strong></p>
    </div>
    <div class='season-trail'>${seasonTrail}</div>
    <p class='muted'>${trustNote}</p>
    <h4>Squad signals</h4>
    <div class='entity-row'>
      ${squadTop.length
        ? squadTop
            .map(
              (row) => `<button type='button' class='entity-chip inline-player' data-player='${row.player || ""}'><span>${row.player || "-"}</span><strong>${metricDisplay(row.runs)}R · ${metricDisplay(row.wickets)}W</strong></button>`,
            )
            .join("")
        : "<p class='muted'>No squad sample for this season/team.</p>"}
    </div>
    <details class='detail-drawer'>
      <summary>Open full squad table</summary>
      ${squad.length
      ? `<div class='table-wrap'><table class='mini-table'><thead><tr><th>Player</th><th>Matches</th><th>Innings</th><th>Balls</th><th>Runs</th><th>Wickets</th></tr></thead><tbody>${squad
          .map(
            (row) =>
              `<tr><td><button type='button' class='inline-player' data-player='${row.player || ""}'>${row.player || "-"}</button></td><td>${metricDisplay(row.matches)}</td><td>${metricDisplay(row.innings)}</td><td>${metricDisplay(row.balls)}</td><td>${metricDisplay(row.runs)}</td><td>${metricDisplay(row.wickets)}</td></tr>`,
          )
          .join("")}</tbody></table></div>`
      : "<p class='muted'>No squad sample for this season/team.</p>"}
    </details>
  `;
  els.teamDetails.querySelectorAll(".season-trail-step").forEach((button) => {
    button.addEventListener("click", () => {
      const seasonValue = Number(button.getAttribute("data-season") || 0);
      if (!seasonValue) return;
      els.teamSeasonSelect.value = String(seasonValue);
      loadTeamDetails().catch((err) => setStatus(err.message || "Failed to load team", "error"));
    });
  });
  els.teamDetails.querySelectorAll(".inline-player").forEach((button) => {
    button.addEventListener("click", () => {
      const player = button.getAttribute("data-player");
      if (player) setRoute({ view: "player", player });
    });
  });
}

async function loadStatsWorkspace() {
  const season = Number(els.statsSeasonSelect.value || 0);
  if (!season) return;
  const [overview, board, table] = await Promise.all([
    api.get(`/api/stats/overview?season_id=${season}`),
    api.get(`/api/stats/leaderboards?season_id=${season}&limit=8`),
    api.get(`/api/stats/points-table?season_id=${season}`),
  ]);
  const top = await api.get(`/api/stats/top-performers?season_id=${season}&limit=5`);
  const lb = board.leaderboards || {};
  const cov = overview.coverage || {};
  const trust = cov.trust_dimensions || {};
  const overallTrust = trust.overall_trust || "UNTRUSTED";
  const trustLabel = humanTrustLabel(overallTrust);
  const coverageFlag = cov.metadata_matches && cov.deliveries_matches && cov.metadata_matches >= cov.deliveries_matches ? "High" : "Partial";
  const renderBoard = (title, rows, qualifier = "") => `
    <article class='metric-rail'>
      <h5>${title}</h5>
      ${qualifier ? `<p class='muted'>Qualification: ${qualifier}</p>` : ""}
      <ol class='rank-rail'>${(rows || []).slice(0, 8).map((r) => `<li><span>${r.player}</span><strong>${metricDisplay(r.value)}</strong></li>`).join("") || "<li class='muted'>No verified data.</li>"}</ol>
    </article>
  `;

  els.statsOverviewBlock.innerHTML = `
    <p class='eyebrow'>SEASON ${season}</p>
    <h4>What should you notice?</h4>
    <p class='muted'>${trustLabel}. ${trust.trust_statement || ""}</p>
    <div class='stats-grid'>
      <div><span>Matches</span><strong>${metricDisplay(overview.matches)}</strong></div>
      <div><span>Innings</span><strong>${metricDisplay(overview.innings)}</strong></div>
      <div><span>Runs</span><strong>${metricDisplay(overview.runs)}</strong></div>
      <div><span>Wickets</span><strong>${metricDisplay(overview.wickets)}</strong></div>
      <div><span>Fours</span><strong>${metricDisplay(overview.fours)}</strong></div>
      <div><span>Sixes</span><strong>${metricDisplay(overview.sixes)}</strong></div>
      <div><span>Dot Balls</span><strong>${metricDisplay(overview.dot_balls)}</strong></div>
      <div><span>Dot Ball %</span><strong>${metricDisplay(overview.dot_ball_percentage)}%</strong></div>
    </div>
    <p class='muted'>Coverage confidence: ${coverageFlag} · Deliveries matches ${metricDisplay(cov.deliveries_matches)} · Metadata matches ${metricDisplay(cov.metadata_matches)}.</p>
    <p class='muted'>Definitions: ${overview.definitions?.dot_balls || "-"}; ${overview.definitions?.wickets || "-"}.</p>
  `;

  els.statsBattingBlock.innerHTML = `
    <h4>Batting Leaderboards</h4>
    <div class='intelligence-columns'>
      ${renderBoard("Orange Cap (Runs)", lb.orange_cap_runs)}
      ${renderBoard("Most Sixes", lb.most_sixes)}
      ${renderBoard("Most Fours", lb.most_fours)}
      ${renderBoard("Best Strike Rate", lb.best_strike_rate, board.qualification?.best_strike_rate || "")}
    </div>
  `;

  els.statsBowlingBlock.innerHTML = `
    <h4>Bowling Leaderboards</h4>
    <div class='intelligence-columns'>
      ${renderBoard("Purple Cap (Wickets)", lb.purple_cap_wickets)}
      ${renderBoard("Best Economy", lb.best_economy, board.qualification?.best_economy || "")}
      <article class='metric-rail'>
        <h5>Current Top Bowlers Signal</h5>
        <ol class='rank-rail'>${(top.top_performers?.wickets || []).map((r) => `<li><span>${r.player}</span><strong>${r.value}</strong></li>`).join("") || "<li class='muted'>No verified data.</li>"}</ol>
      </article>
    </div>
  `;

  els.statsRecordsBlock.innerHTML = `
    <h4>Records</h4>
    ${renderBoard("Highest Score", lb.highest_score)}
  `;

  els.statsGraphsBlock.innerHTML = `
    <h4>Graphs</h4>
    <p class='muted'>Interactive trajectory graphs are backed by local data and will appear here as you filter players/teams in upcoming iterations.</p>
    <p class='muted'>Available now: season trajectories in Players and Replay evidence tabs.</p>
  `;

  els.pointsTableBlock.innerHTML = `
    <h4>Points Table</h4>
    <p class='muted'>P: played · W: wins · L: losses · NR: no result · Pts: points · NRR uses all-out full-overs denominator.</p>
    <div class='table-wrap'><table class='mini-table'><thead><tr><th>Team</th><th>P</th><th>W</th><th>L</th><th>NR</th><th>Pts</th><th>NRR</th></tr></thead><tbody>
      ${(table.table || [])
        .map((r) => `<tr><td>${r.team}</td><td>${r.matches}</td><td>${r.wins}</td><td>${r.losses}</td><td>${r.no_result}</td><td>${r.points}</td><td>${r.net_run_rate}</td></tr>`)
        .join("")}
    </tbody></table></div>
  `;
}

async function compareSeasonSignals() {
  if (!els.statsCompareSeasonA || !els.statsCompareSeasonB || !els.statsCompareBlock) return;
  const seasonA = normalizeSeason(els.statsCompareSeasonA.value);
  const seasonB = normalizeSeason(els.statsCompareSeasonB.value);
  if (!seasonA || !seasonB) {
    els.statsCompareBlock.textContent = "Choose two seasons to compare their signals.";
    return;
  }
  const [a, b] = await Promise.all([
    api.get(`/api/stats/overview?season_id=${seasonA}`),
    api.get(`/api/stats/overview?season_id=${seasonB}`),
  ]);
  const rows = [
    ["Runs", Number(a.runs || 0), Number(b.runs || 0)],
    ["Wickets", Number(a.wickets || 0), Number(b.wickets || 0)],
    ["Boundaries", Number(a.fours || 0) + Number(a.sixes || 0), Number(b.fours || 0) + Number(b.sixes || 0)],
    ["Strike Rate", Number(a.average_strike_rate || 0), Number(b.average_strike_rate || 0)],
    ["Dot Ball %", Number(a.dot_ball_percentage || 0), Number(b.dot_ball_percentage || 0)],
  ];
  els.statsCompareBlock.innerHTML = `
    <p class='eyebrow'>COMPARE SEASONS</p>
    <h4>${seasonA} vs ${seasonB}</h4>
    <div class='table-wrap'>
      <table class='mini-table'>
        <thead><tr><th>Signal</th><th>${seasonA}</th><th>${seasonB}</th><th>Shift</th></tr></thead>
        <tbody>
          ${rows
            .map(([label, va, vb]) => {
              const delta = Number(vb) - Number(va);
              const sign = delta > 0 ? "+" : "";
              return `<tr><td>${label}</td><td>${metricDisplay(va)}</td><td>${metricDisplay(vb)}</td><td>${sign}${delta.toFixed(2)}</td></tr>`;
            })
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

async function loadHomeLaunchpad(selectedSeason = null) {
  const latestSeason = normalizeSeason(state.latestSeasonId || latestSeasonFromState());
  const season = normalizeSeason(selectedSeason || state.homeSelectedSeason || latestSeason);
  if (!season) return;
  state.homeSelectedSeason = season;
  state.latestSeasonId = latestSeason || season;

  // Read sequentially to avoid sqlite concurrency misuse surfaced by parallel API fan-out.
  const fixturesPayload = await api.get(`/api/fixtures?season_id=${season}`);
  const resultsPayload = await api.get(`/api/results?season_id=${season}`);
  const topPayload = await api.get(`/api/stats/top-performers?season_id=${season}&limit=1`);
  const tablePayload = await api.get(`/api/stats/points-table?season_id=${season}`);
  const overviewPayload = await api.get(`/api/stats/overview?season_id=${season}`);
  const boardPayload = await api.get(`/api/stats/leaderboards?season_id=${season}&limit=1`);

  const fixtures = fixturesPayload.fixtures || [];
  const upcoming = fixtures.find((row) => row.status === "upcoming" || row.status === "scheduled") || fixtures[0];
  const latest = (resultsPayload.results || []).slice(-1)[0] || null;
  const leader = (tablePayload.table || [])[0] || null;
  const topRun = (((topPayload.top_performers || {}).runs || [])[0]) || null;
  const topWicket = (((topPayload.top_performers || {}).wickets || [])[0]) || null;
  const highestScore = (((boardPayload.leaderboards || {}).highest_score || [])[0]) || null;
  const coverage = overviewPayload.coverage || {};
  const trust = coverage.trust_dimensions || {};
  const trustBadge = humanTrustLabel(trust.overall_trust);
  const totalSeasons = state.seasons.length || 0;
  const viewingHistorical = latestSeason && season !== latestSeason;

  if (els.homeContextPill) {
    els.homeContextPill.textContent = viewingHistorical ? `VIEWING ${season}` : "LATEST CHAPTER";
  }
  if (els.homeSeasonTag) {
    els.homeSeasonTag.textContent = String(season || "-");
  }

  const prompts = [
    "Why did KKR dominate the 2024 final?",
    "Who performs best against spin?",
    "What changed this innings?",
    "What makes this player different?",
    "What is likely to happen next?",
  ];
  if (els.homeAskPrompts) {
    els.homeAskPrompts.innerHTML = prompts.map((text) => `<button type='button' class='quick-link home-prompt'>${escapeHtml(text)}</button>`).join("");
    els.homeAskPrompts.querySelectorAll(".home-prompt").forEach((btn) => {
      btn.addEventListener("click", () => {
        els.askInput.value = btn.textContent || "";
        setRoute({ view: "ask" });
      });
    });
  }

  if (els.homeUpcoming) {
    const summary = upcoming
      ? `${teamLabel(upcoming.team_a, "Team A")} vs ${teamLabel(upcoming.team_b, "Team B")} · ${upcoming.match_date || "Date unavailable"}`
      : "Verified information is not currently available.";
    els.homeUpcoming.textContent = viewingHistorical ? `Historical chapter signal: ${summary}` : `Next chapter signal: ${summary}`;
  }
  if (els.homeLatest) {
    els.homeLatest.textContent = latest
      ? `Latest result: ${teamLabel(latest.team_a, "Team A")} vs ${teamLabel(latest.team_b, "Team B")} · ${latest.winner || "Result pending"}`
      : "Verified information is not currently available.";
  }
  if (els.homeSeasonStatus) {
    els.homeSeasonStatus.textContent = leader
      ? `Champion signal: ${leader.team} · ${leader.points} points (NRR ${leader.net_run_rate})`
      : "Verified information is not currently available.";
  }

  if (els.homeTopPerformers) {
    els.homeTopPerformers.innerHTML = `
      <p class='context-stat'><strong>${topRun ? metricDisplay(topRun.value) : "-"}</strong><span>runs · ${escapeHtml(topRun?.player || "Not available")}</span></p>
      <p class='context-stat'><strong>${topWicket ? metricDisplay(topWicket.value) : "-"}</strong><span>wickets · ${escapeHtml(topWicket?.player || "Not available")}</span></p>
      <p class='context-stat'><strong>${highestScore ? metricDisplay(highestScore.value) : "-"}</strong><span>highest score · ${escapeHtml(highestScore?.player || "Not available")}</span></p>
    `;
  }

  if (els.homeSeasonTimeline) {
    const seasons = [...state.seasons]
      .map((s) => normalizeSeason(s.season_id))
      .filter(Boolean)
      .sort((a, b) => a - b);
    els.homeSeasonTimeline.innerHTML = seasons
      .map((seasonId) => {
        const active = Number(seasonId) === Number(season) ? "active" : "";
        return `<button type='button' class='home-season-node ${active}' data-season='${seasonId}'>${seasonId}</button>`;
      })
      .join("");
    els.homeSeasonTimeline.querySelectorAll(".home-season-node").forEach((button) => {
      button.addEventListener("click", () => {
        const seasonId = normalizeSeason(button.getAttribute("data-season"));
        if (!seasonId) return;
        state.homeSelectedSeason = seasonId;
        if (els.homeReplaySeasonSelect) {
          els.homeReplaySeasonSelect.value = String(seasonId);
        }
        loadHomeLaunchpad(seasonId).catch((err) => setStatus(err.message || "Failed to refresh home chapter", "error"));
      });
    });
  }

  if (els.homeSeasonStory) {
    const keyMoment = latest
      ? `${teamLabel(latest.team_a, "Team A")} vs ${teamLabel(latest.team_b, "Team B")} · ${teamLabel(latest.winner, "Result pending")}`
      : "No completed moment available";
    els.homeSeasonStory.innerHTML = `
      <p class='eyebrow'>SEASON STORY</p>
      <h4>IPL ${season}</h4>
      <div class='season-story-grid'>
        <div><span>Champion</span><strong>${escapeHtml(leader?.team || "Unknown")}</strong></div>
        <div><span>Top performer</span><strong>${escapeHtml(topRun?.player || topWicket?.player || "Unknown")}</strong></div>
        <div><span>Key number</span><strong>${topRun ? metricDisplay(topRun.value) : topWicket ? metricDisplay(topWicket.value) : "-"}</strong></div>
        <div><span>Signature moment</span><strong>${escapeHtml(keyMoment)}</strong></div>
      </div>
      <div class='row-actions'>
        <button type='button' class='quick-link' id='homeExploreSeasonBtn'>Explore season</button>
        <button type='button' class='quick-link' id='homeOpenSeasonReplayBtn'>Enter replay</button>
        <button type='button' class='quick-link' id='homeOpenSeasonPlayerBtn'>Open player genome</button>
      </div>
    `;
    const exploreBtn = document.getElementById("homeExploreSeasonBtn");
    const replayBtn = document.getElementById("homeOpenSeasonReplayBtn");
    const playerBtn = document.getElementById("homeOpenSeasonPlayerBtn");
    if (exploreBtn) {
      exploreBtn.addEventListener("click", () => setRoute({ view: "matches", season_id: season, tab: "results" }));
    }
    if (replayBtn) {
      replayBtn.addEventListener("click", () => setRoute({ view: "replay", season_id: season }));
    }
    if (playerBtn) {
      playerBtn.addEventListener("click", () => setRoute({ view: "player" }));
    }
  }

  if (els.homeDataStatement) {
    const matches = Number(overviewPayload.matches || 0);
    const deliveries = Number(overviewPayload.deliveries || 0);
    els.homeDataStatement.innerHTML = `
      <span><strong>${totalSeasons || "-"}</strong> seasons</span>
      <span><strong>${matches ? matches.toLocaleString("en-IN") : "-"}</strong> matches</span>
      <span><strong>${deliveries ? deliveries.toLocaleString("en-IN") : "-"}</strong> deliveries</span>
      <span class='muted'>One continuous game</span>
    `;
  }

  if (els.homeSignals) {
    const runSignal = topRun ? `${topRun.player} leads runs (${topRun.value}).` : "Run leader unavailable.";
    const wicketSignal = topWicket ? `${topWicket.player} leads wickets (${topWicket.value}).` : "Wicket leader unavailable.";
    const championSignal = leader ? `${leader.team} currently hold the strongest table position (${leader.points} pts).` : "Champion/leader signal unavailable.";
    const coverageSignal = coverage.deliveries_matches
      ? `Season coverage: ${coverage.deliveries_matches} matches in deliveries${coverage.metadata_matches ? `, ${coverage.metadata_matches} with metadata` : ""}.`
      : "Season coverage unavailable.";

    const pathNarrative = {
      player: { title: "Player", detail: runSignal },
      matchup: {
        title: "Matchup",
        detail: upcoming
          ? `${teamLabel(upcoming.team_a, "Team A")} vs ${teamLabel(upcoming.team_b, "Team B")} is the next active matchup context.`
          : "Upcoming matchup context is not currently available.",
      },
      phase: {
        title: "Phase",
        detail: latest
          ? `Latest completed event anchors current phase interpretation for IPL ${latest.season_id || season}.`
          : "Completed match phase context is currently unavailable.",
      },
      pressure: { title: "Pressure", detail: championSignal },
      outcome: { title: "Outcome", detail: wicketSignal },
    };

    const renderHomeSignal = (nodeKey) => {
      const chosen = pathNarrative[nodeKey] || pathNarrative.player;
      els.homeSignals.innerHTML = `
        <div class='signal-line'>
          <p class='eyebrow'>${escapeHtml(chosen.title)} SIGNAL</p>
          <strong>${escapeHtml(chosen.detail)}</strong>
        </div>
        <p class='muted'>${escapeHtml(coverageSignal)}</p>
        <p class='muted'>Trust: ${escapeHtml(trustBadge)}.</p>
      `;
    };

    renderHomeSignal("player");
    if (els.homeGenomePath) {
      els.homeGenomePath.querySelectorAll(".genome-node").forEach((button) => {
        button.onclick = () => {
          const node = button.getAttribute("data-node") || "player";
          els.homeGenomePath.querySelectorAll(".genome-node").forEach((n) => n.classList.remove("active"));
          button.classList.add("active");
          renderHomeSignal(node);
        };
      });
    }
  }

  if (els.homeFeaturedMatch) {
    const featured = upcoming || latest || null;
    if (!featured) {
      els.homeFeaturedMatch.innerHTML = "<p class='eyebrow'>MATCH STORY</p><p class='muted'>Verified match narrative is not currently available.</p>";
    } else {
      const matchId = Number(featured.match_id || 0);
      els.homeFeaturedMatch.innerHTML = `
        <p class='eyebrow'>A MATCH CHANGED HERE</p>
        <div class='match-moment'>
          <strong>${teamLabel(featured.team_a, "Team A")} vs ${teamLabel(featured.team_b, "Team B")}</strong>
          <p>${featured.match_date || "Date unavailable"} · IPL ${featured.season_id} · Match ${featured.match_number || "-"}</p>
          <p>${featured.venue || "Venue unavailable"}${featured.city ? `, ${featured.city}` : ""}</p>
        </div>
        <div class='row-actions'>
          <button type='button' class='primary' id='homeOpenFeaturedMatchBtn'>Open Event Space</button>
          <button type='button' id='homeReplayFeaturedMatchBtn'>Replay the moment</button>
          <button type='button' id='homeAskFeaturedMatchBtn'>Ask this match context</button>
        </div>
      `;
      const openBtn = document.getElementById("homeOpenFeaturedMatchBtn");
      const replayBtn = document.getElementById("homeReplayFeaturedMatchBtn");
      const askBtn = document.getElementById("homeAskFeaturedMatchBtn");
      if (openBtn) openBtn.addEventListener("click", () => setRoute({ view: "matches", match_id: matchId || "", season_id: featured.season_id || "" }));
      if (replayBtn) replayBtn.addEventListener("click", () => setRoute({ view: "replay", match_id: matchId || "", season_id: featured.season_id || "" }));
      if (askBtn) askBtn.addEventListener("click", () => {
        els.askInput.value = `What happened in IPL ${featured.season_id} match ${featured.match_number || matchId}?`;
        setRoute({ view: "ask" });
      });
    }
  }


  if (els.homeDiscoveryStrip) {
    const featuredFinal = latest
      ? `${teamLabel(latest.team_a, "Team A")} vs ${teamLabel(latest.team_b, "Team B")}`
      : "Final context unavailable";
    els.homeDiscoveryStrip.innerHTML = `
      <article class='stream-item'><p class='eyebrow'>01 · RUNS</p><h4>${topRun ? escapeHtml(topRun.player) : "Not available"}</h4><p>${topRun ? `${metricDisplay(topRun.value)} runs` : "No verified signal"}</p></article>
      <article class='stream-item'><p class='eyebrow'>02 · WICKETS</p><h4>${topWicket ? escapeHtml(topWicket.player) : "Not available"}</h4><p>${topWicket ? `${metricDisplay(topWicket.value)} wickets` : "No verified signal"}</p></article>
      <article class='stream-item'><p class='eyebrow'>03 · MATCH</p><h4>${escapeHtml(featuredFinal)}</h4><p>${escapeHtml(latest?.winner || "Result unavailable")}</p></article>
      <article class='stream-item action'><button type='button' class='quick-link' id='homeDiscoveryReplay'>Replay this world -></button><button type='button' class='quick-link' id='homeDiscoveryPlayers'>Open player intelligence -></button><button type='button' class='quick-link' id='homeDiscoveryTeams'>Open team timeline -></button><button type='button' class='quick-link' id='homeDiscoveryStats'>Explore season patterns -></button></article>
    `;
    const map = [
      ["homeDiscoveryReplay", { view: "replay" }],
      ["homeDiscoveryPlayers", { view: "player" }],
      ["homeDiscoveryTeams", { view: "teams" }],
      ["homeDiscoveryStats", { view: "stats", tab: "overview", season_id: season || "" }],
    ];
    map.forEach(([id, route]) => {
      const btn = document.getElementById(id);
      if (btn) btn.addEventListener("click", () => setRoute(route));
    });
  }

  updateContextBreadcrumb();
}

function setReplayTab(tab) {
  state.replayTab = tab;
  const tabs = [
    [els.tabPredictionBtn, els.panelPrediction, tab === "prediction"],
    [els.tabBallByBallBtn, els.panelBallByBall, tab === "ball_by_ball"],
    [els.tabEvidenceBtn, els.panelEvidence, tab === "evidence"],
  ];
  tabs.forEach(([btn, panel, active]) => {
    btn.classList.toggle("active", active);
    panel.hidden = !active;
    btn.setAttribute("aria-selected", active ? "true" : "false");
  });
}

function bindReplayTabTarget(button, tab) {
  if (!button) return;
  let lastTapAt = 0;
  const activate = (event) => {
    if (event) {
      event.preventDefault();
      event.stopPropagation();
    }
    setReplayTab(tab);
  };
  button.addEventListener("pointerup", (event) => {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    lastTapAt = Date.now();
    activate(event);
  });
  button.addEventListener("click", (event) => {
    if (Date.now() - lastTapAt < 300) return;
    activate(event);
  });
  button.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    activate(event);
  });
}

function updateReplayLayoutState() {
  const layout = els.timeMachineView ? els.timeMachineView.querySelector(".time-machine-layout") : null;
  if (!layout) return;
  const active = Boolean(state.sessionId) && !els.replayPanel.hidden;
  layout.classList.toggle("stage-active", active);
}

async function selectMatchInTimeMachine(seasonId, matchId) {
  const season = Number(seasonId || 0);
  const match = Number(matchId || 0);
  if (!season || !match) return;
  const seasonExists = state.seasons.some((x) => Number(x.season_id) === season);
  if (!seasonExists) return;
  if (Number(els.seasonSelect.value) !== season) {
    els.seasonSelect.value = String(season);
    await loadMatches();
  }
  const selected = state.matches.find((m) => Number(m.match_id) === match) || null;
  if (!selected) return;
  await selectTimeMachineMatch(selected);
}

function setPlayerTab(tab) {
  state.playerTab = tab;
  const hasBatting = Boolean(state.playerCapabilities.hasBatting);
  const hasBowling = Boolean(state.playerCapabilities.hasBowling);
  const panels = {
    overview: [els.playerTabOverviewBtn, els.playerPanelOverview, true],
    batting: [els.playerTabBattingBtn, els.playerPanelBatting, hasBatting],
    bowling: [els.playerTabBowlingBtn, els.playerPanelBowling, hasBowling],
    matchups: [els.playerTabMatchupsBtn, els.playerPanelMatchups, true],
    seasons: [els.playerTabSeasonsBtn, els.playerPanelSeasons, hasBatting || hasBowling],
    phases: [els.playerTabPhasesBtn, els.playerPanelPhases, hasBatting || hasBowling],
  };
  Object.entries(panels).forEach(([name, [btn, panel, visible]]) => {
    btn.hidden = !visible;
    const active = visible && name === tab;
    btn.classList.toggle("active", active);
    panel.hidden = !active;
  });
}

function setUiState(nextState) {
  state.uiState = nextState;
  const canPredict = nextState === UiState.READY || nextState === UiState.PREDICTION_REVEALED;
  els.predictBtn.disabled = !canPredict;
  els.nextBtn.disabled = !canPredict;
  els.revealBtn.disabled = nextState !== UiState.PREDICTION_AVAILABLE;

  const dominantMap = {
    predict: canPredict,
    reveal: nextState === UiState.PREDICTION_AVAILABLE,
    next: nextState === UiState.PREDICTION_REVEALED,
  };
  [
    [els.predictBtn, dominantMap.predict],
    [els.revealBtn, dominantMap.reveal],
    [els.nextBtn, dominantMap.next],
  ].forEach(([button, active]) => {
    if (!button) return;
    button.classList.toggle("dominant", Boolean(active));
  });
}

function replayEvidenceStrength(prediction) {
  const reliability = String(prediction?.reliability || "unknown").toLowerCase();
  const sample = Number(prediction?.evidence_sample_size || 0);
  const evidence = prediction?.evidence || {};
  const matchup = Number(evidence.matchup_deliveries || 0);
  const comparable = Number(evidence.comparable_deliveries || 0);
  if (sample < 40 || matchup === 0 || comparable === 0 || reliability === "low") {
    return {
      label: "LIMITED EVIDENCE",
      note: `Direct matchup ${matchup} · Similar situations ${comparable}`,
    };
  }
  if (sample < 120 || reliability === "medium") {
    return {
      label: "MODERATE SIGNAL",
      note: `Direct matchup ${matchup} · Similar situations ${comparable}`,
    };
  }
  return {
    label: "STRONG SIGNAL",
    note: `Direct matchup ${matchup} · Similar situations ${comparable}`,
  };
}

function buildUserCallOptions() {
  if (!els.userCallOptions) return;
  const outcomes = ["0", "1", "2", "4", "6", "wicket"];
  els.userCallOptions.innerHTML = outcomes
    .map((outcome) => {
      const active = state.userCall === outcome ? "active" : "";
      const label = outcome === "wicket" ? "W" : outcome;
      return `<button type='button' class='user-call-option ${active}' data-call='${outcome}'>${label}</button>`;
    })
    .join("");
  els.userCallOptions.querySelectorAll(".user-call-option").forEach((button) => {
    button.addEventListener("click", () => {
      state.userCall = button.getAttribute("data-call") || null;
      buildUserCallOptions();
      if (els.userCallSummary) {
        els.userCallSummary.textContent = state.userCall ? `Your call: ${outcomeDisplay(state.userCall)}` : "Choose your call before reveal.";
      }
    });
  });
}

function renderPredictionLedger() {
  if (!els.predictionLedger) return;
  const revealed = state.timeline.filter((entry) => entry.status !== "pending");
  if (!revealed.length) {
    els.predictionLedger.innerHTML = "Prediction ledger appears after the first reveal.";
    return;
  }
  const youCorrect = revealed.filter((entry) => entry.user_call && entry.user_call === entry.actual).length;
  const modelCorrect = revealed.filter((entry) => entry.status === "correct").length;
  els.predictionLedger.innerHTML = `
    <p class='eyebrow'>PREDICTION LEDGER</p>
    <div class='ledger-stream'>
      ${revealed
        .slice(-10)
        .map((entry) => {
          const userOutcome = entry.user_call ? outcomeDisplay(entry.user_call) : "-";
          const verdict = entry.status === "correct" ? "MODEL CORRECT" : "MODEL MISSED";
          return `<article class='ledger-row'>
            <p><span>Ball</span><strong>${entry.over}.${entry.ball}</strong></p>
            <p><span>Your call</span><strong>${userOutcome}</strong></p>
            <p><span>MatchGenome</span><strong>${outcomeDisplay(entry.predicted)}</strong></p>
            <p><span>Reality</span><strong>${outcomeDisplay(entry.actual)}</strong></p>
            <p><span>Result</span><strong>${verdict}</strong></p>
          </article>`;
        })
        .join("")}
    </div>
    <div class='ask-meta-row'>
      <span class='trust-chip'>Your accuracy ${youCorrect}/${revealed.length}</span>
      <span class='trust-chip'>Model accuracy ${modelCorrect}/${revealed.length}</span>
    </div>
  `;
}

function option(label, value) {
  const opt = document.createElement("option");
  opt.value = String(value);
  opt.textContent = label;
  return opt;
}

function matchTitleFromMeta(meta) {
  if (!meta) return "Team A vs Team B";
  return `${teamLabel(meta.team_a, "Team A")} vs ${teamLabel(meta.team_b, "Team B")}`;
}

function sortUnique(values) {
  return [...new Set(values.filter(Boolean))].sort((a, b) => String(a).localeCompare(String(b)));
}

function normalizeTeamKey(value) {
  const raw = String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]/g, "");
  const aliases = {
    delhidaredevils: "delhicapitals",
    kingsxipunjab: "punjabkings",
    risingpunesupergiants: "risingpunesupergiant",
    gujaratlions: "gujarattitans",
  };
  return aliases[raw] || raw;
}

function initials(value) {
  const parts = String(value || "")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (!parts.length) return "TM";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
}

function buildTeamAssetIndex(teams) {
  const index = {};
  (teams || []).forEach((item) => {
    const keys = [item.team, item.short_name, item.historical_name].map(normalizeTeamKey).filter(Boolean);
    keys.forEach((key) => {
      index[key] = item;
    });
  });
  state.teamAssetIndex = index;
}

function teamAssetForName(name) {
  const key = normalizeTeamKey(name);
  return key ? state.teamAssetIndex[key] || null : null;
}

function renderTeamLogo(name) {
  const asset = teamAssetForName(name);
  const fallback = `<span class='team-logo-fallback'>${initials(name)}</span>`;
  if (asset && asset.logo_asset_path) {
    return `<span class='team-logo-shell'><img class='team-logo' src='${asset.logo_asset_path}' alt='${name} logo' loading='lazy' onerror='this.hidden=true;this.nextElementSibling.hidden=false;' /><span class='team-logo-fallback' hidden>${initials(name)}</span></span>`;
  }
  return fallback;
}

function renderMatchBanner(teamA, teamB) {
  const a = teamAssetForName(teamA);
  const b = teamAssetForName(teamB);
  const banner = (a && a.banner_asset_path) || (b && b.banner_asset_path);
  const fallback = `<div class='team-banner-fallback'>${teamA} vs ${teamB}</div>`;
  if (!banner) return fallback;
  return `<div class='team-banner-shell'><img class='team-banner' src='${banner}' alt='${teamA} vs ${teamB} banner' loading='lazy' onerror='this.hidden=true;this.nextElementSibling.hidden=false;' /><div class='team-banner-fallback' hidden>${teamA} vs ${teamB}</div></div>`;
}

function filteredMatches() {
  const query = (els.matchSearchInput.value || "").trim().toLowerCase();
  const teamFilter = (els.teamFilterSelect.value || "").trim();
  return state.matches.filter((m) => {
    const teamA = teamLabel(m.team_a, "Team A");
    const teamB = teamLabel(m.team_b, "Team B");
    if (teamFilter && teamA !== teamFilter && teamB !== teamFilter) return false;
    if (!query) return true;
    const text = [teamA, teamB, String(m.match_id), String(m.match_date || ""), String(m.venue || ""), String(m.city || ""), String(m.match_number || m.season_match_number || "")]
      .join(" ")
      .toLowerCase();
    return text.includes(query);
  });
}

async function selectTimeMachineMatch(match) {
  state.selectedMatchId = Number(match.match_id);
  state.selectedMatch = match;
  els.selectedMatchMeta.textContent = `${matchTitleFromMeta(match)} · IPL ${match.season_id} · Match ${match.match_number || match.season_match_number || "-"}`;
  if (els.replayBanner) {
    const banner = renderMatchBanner(teamLabel(match.team_a, "Team A"), teamLabel(match.team_b, "Team B"));
    els.replayBanner.hidden = !banner;
    els.replayBanner.innerHTML = banner;
  }
  renderMatchCards();
  await loadInnings();
  updateContextBreadcrumb();
}

async function jumpToReplayWidgets(match) {
  await selectTimeMachineMatch(match);
  if (!state.selectedInnings) return;
  await startReplay();
  els.replayPanel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function applyTeamDataNotice() {
  const msg = "Some matches still include unresolved team IDs. MatchGenome shows original IDs only when verified enrichment is unavailable.";
  els.teamDataNotice.hidden = !state.hasTeamIdOnlyData;
  els.replayTeamNotice.hidden = !state.hasTeamIdOnlyData;
  if (state.hasTeamIdOnlyData) {
    els.teamDataNotice.textContent = msg;
    els.replayTeamNotice.textContent = msg;
  }
}

function renderTeamFilterOptions() {
  const teams = sortUnique(
    state.matches.flatMap((m) => [teamLabel(m.team_a, ""), teamLabel(m.team_b, "")]),
  );
  const current = els.teamFilterSelect.value;
  els.teamFilterSelect.innerHTML = "";
  els.teamFilterSelect.appendChild(option("All teams", ""));
  teams.forEach((name) => els.teamFilterSelect.appendChild(option(name, name)));
  els.teamFilterSelect.value = teams.includes(current) ? current : "";
}

function renderMatchCards() {
  const filtered = filteredMatches();

  els.matchListSummary.textContent = `${filtered.length} match${filtered.length === 1 ? "" : "es"} available`;
  els.matchCards.innerHTML = "";

  if (filtered.length === 0) {
    els.matchCards.innerHTML = "<p class='muted'>No matches found for this filter.</p>";
    return;
  }

  filtered.forEach((m) => {
    const unresolved = hasUnresolvedTeamName(m.team_a) || hasUnresolvedTeamName(m.team_b);
    const teamA = teamLabel(m.team_a, "Team A");
    const teamB = teamLabel(m.team_b, "Team B");
    const card = document.createElement("article");
    card.className = `match-card ${state.selectedMatchId === Number(m.match_id) ? "active" : ""}`;
    card.innerHTML = `
      ${renderMatchBanner(teamA, teamB)}
      <button type='button' class='match-card-select' data-match-id='${m.match_id}'>
        <div class='match-teams'>
          <strong>${renderTeamLogo(teamA)} <span>${teamA}</span></strong>
          <span>vs</span>
          <strong><span>${teamB}</span> ${renderTeamLogo(teamB)}</strong>
        </div>
      </button>
      <div class='muted'>IPL ${m.season_id} · Match ${m.match_number || m.season_match_number || "-"}</div>
      <div class='muted'>${m.match_date || "Date unavailable"} · ${m.venue || "Venue unavailable"}${m.city ? `, ${m.city}` : ""}</div>
      ${unresolved ? "<div class='muted'>Unresolved team identity for this record.</div>" : ""}
      <div class='row-actions'><button type='button' class='replay-chip' data-match-id='${m.match_id}'>Replay this match</button></div>
    `;
    const selectBtn = card.querySelector(".match-card-select");
    const replayBtn = card.querySelector(".replay-chip");
    const selectCard = () => {
      selectTimeMachineMatch(m).catch((err) => setStatus(err.message || "Failed to select match", "error"));
    };
    card.addEventListener("click", (event) => {
      const target = event.target;
      if (target && typeof target.closest === "function" && target.closest(".replay-chip")) return;
      selectCard();
    });
    if (selectBtn) {
      selectBtn.addEventListener("click", selectCard);
    }
    if (replayBtn) {
      replayBtn.addEventListener("click", (event) => {
        event.stopPropagation();
        jumpToReplayWidgets(m).catch((err) => setStatus(err.message || "Could not start replay.", "error"));
      });
    }
    els.matchCards.appendChild(card);
  });
}

function attachPlayerButton(button, name) {
  button.textContent = name || "-";
  button.disabled = !name;
  button.onclick = () => {
    if (!name) return;
    setRoute({ view: "player", player: name });
  };
}

function updateTimeline() {
  els.timelineTrack.innerHTML = "";
  state.timeline.slice(-36).forEach((entry) => {
    const dot = document.createElement("div");
    dot.className = `timeline-dot ${entry.status}`;
    dot.textContent = `${entry.over}.${entry.ball}`;
    dot.title = `${entry.over}.${entry.ball} · ${entry.status}`;
    dot.onclick = () => {
      const idx = state.timeline.findIndex((x) => x.over === entry.over && x.ball === entry.ball);
      state.selectedTimelineIndex = idx;
      renderBallByBallRows();
      setReplayTab("ball_by_ball");
    };
    els.timelineTrack.appendChild(dot);
  });

  const revealed = state.timeline.filter((x) => x.status !== "pending").length;
  const total = revealed + Number(state.sessionMeta?.current_state?.remaining_deliveries || 0);
  els.progressValue.textContent = `${revealed}/${total} revealed`;
  els.progressFill.style.width = `${total > 0 ? Math.round((revealed / total) * 100) : 0}%`;

  const prev = [...state.timeline].reverse().find((x) => x.status !== "pending");
  els.prevBallValue.textContent = prev ? `Previous: ${prev.over}.${prev.ball} (${outcomeDisplay(prev.actual)})` : "Previous: -";
  const next = state.lastPrediction;
  els.nextBallValue.textContent = next
    ? `Next: ${next.delivery.over_number}.${next.delivery.ball_number}`
    : total > 0
      ? "Next: predict to continue"
      : "Next: -";

  els.previousBtn.disabled = revealed === 0;
  renderBallByBallRows();
  renderPredictionLedger();
}

function renderBallByBallRows() {
  const revealed = state.timeline.filter((x) => x.status !== "pending");
  if (!revealed.length) {
    els.ballByBallRows.innerHTML = "<tr><td colspan='6' class='muted'>No deliveries revealed yet.</td></tr>";
    return;
  }

  els.ballByBallRows.innerHTML = revealed
    .map((entry, idx) => {
      const verdict = entry.status === "correct" ? "Correct" : "Incorrect";
      const active = state.selectedTimelineIndex === idx ? "active" : "";
      return `<tr class='timeline-row ${active}' data-row='${idx}'>
        <td>${entry.over}.${entry.ball}</td>
        <td><button class='inline-player' data-player='${entry.batter || ""}'>${entry.batter || "-"}</button></td>
        <td><button class='inline-player' data-player='${entry.bowler || ""}'>${entry.bowler || "-"}</button></td>
        <td>${outcomeDisplay(entry.predicted)}</td>
        <td>${outcomeDisplay(entry.actual)}</td>
        <td><span class='badge ${entry.status}'>${verdict}</span></td>
      </tr>`;
    })
    .join("");

  els.ballByBallRows.querySelectorAll(".inline-player").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      const player = button.getAttribute("data-player");
      if (player) setRoute({ view: "player", player });
    });
  });
}

function renderReplayHeaderMetrics() {
  const current = state.sessionMeta?.current_state || {};
  const summary = state.sessionMeta?.summary || {};
  const revealed = Number(summary.predictions_revealed || 0);
  const correct = Number(summary.correct_predictions || 0);
  const acc = Number(summary.accuracy || 0);
  const remaining = Number(current.remaining_deliveries || 0);
  const total = remaining + revealed;

  els.progressHeaderValue.textContent = total > 0 ? `${revealed}/${total} balls` : "-";
  els.accuracyValue.textContent = revealed > 0 ? `${correct}/${revealed} · ${(acc * 100).toFixed(1)}%` : "-";
}

function renderPrediction(pred) {
  const probs = pred.prediction.outcome_probabilities || {};
  const top = pred.prediction.predicted_top_outcome;
  const topProb = Number(probs[top] || 0);

  els.predictedTop.textContent = outcomeDisplay(top).toUpperCase();
  els.predictedPct.textContent = toPct(topProb);

  const entries = Object.entries(probs).sort((a, b) => Number(b[1]) - Number(a[1]));
  els.probabilityBars.innerHTML = entries
    .map(([label, value]) => {
      const topClass = label === top ? "top" : "";
      return `<div class='prob-node ${topClass}'>
        <span>${label === "wicket" ? "W" : escapeHtml(label)}</span>
        <strong>${toPct(value)}</strong>
      </div>`;
    })
    .join("");

  const evidence = pred.prediction.evidence || {};
  const featureLedger = Array.isArray(evidence.feature_ledger) ? evidence.feature_ledger : [];
  const lookedAt = (evidence.looked_at || []).map((x) => `<li>${x}</li>`).join("");
  const comparable = Number(evidence.comparable_deliveries || 0);
  const matchup = Number(evidence.matchup_deliveries || 0);
  const reliability = capitalize(pred.prediction.reliability || "unknown");
  const strength = replayEvidenceStrength(pred.prediction);

  els.whyBlock.innerHTML = `
    <h5>Why this forecast?</h5>
    <p><span class='trust-chip'>${strength.label}</span></p>
    <p>MatchGenome weighs matchup, phase pressure, recent context, and similar pre-ball situations.</p>
    <p><strong>Evidence strength:</strong> ${strength.note}</p>
    <p><strong>Reliability:</strong> ${reliability}</p>
    ${lookedAt ? `<details><summary>Context factors</summary><ul>${lookedAt}</ul></details>` : ""}
  `;

  const change = pred.prediction.prediction_difference;
  if (change && Array.isArray(change.changed_features) && change.changed_features.length) {
    els.changeBlock.classList.remove("muted");
    els.changeBlock.innerHTML = `<h5>What changed?</h5><ul>${change.changed_features.map((item) => `<li>${item}</li>`).join("")}</ul>`;
  } else {
    els.changeBlock.classList.add("muted");
    els.changeBlock.textContent = "Prediction change diagnostics will appear after consecutive deliveries.";
  }

  els.evidenceBlock.innerHTML = `
    <h5>Answer</h5>
    <p>${outcomeDisplay(top)} at ${toPct(topProb)} probability.</p>
    <h5>Evidence</h5>
    <p>Sample size: ${pred.prediction.evidence_sample_size || 0} · Reliability: ${reliability}</p>
    ${featureLedger.length
      ? `<details><summary>Feature ledger</summary><div class='table-wrap'><table class='mini-table'><thead><tr><th>Feature</th><th>Value</th><th>Sample</th><th>Strength</th><th>Influence</th></tr></thead><tbody>${featureLedger
          .slice(0, 12)
          .map(
            (f) => `<tr><td>${f.feature || "-"}</td><td>${typeof f.value === "object" ? JSON.stringify(f.value) : metricDisplay(f.value)}</td><td>${metricDisplay(f.sample_size)}</td><td>${metricDisplay(f.strength)}</td><td>${metricDisplay(f.influence)}</td></tr>`,
          )
          .join("")}</tbody></table></div></details>`
      : ""}
  `;

  els.distributionBlock.innerHTML = `<h5>Distribution</h5>${entries
    .map(([label, value]) => `<p>${outcomeDisplay(label)}: <strong>${toPct(value)}</strong></p>`)
    .join("")}`;

  els.technicalEvidenceBlock.innerHTML = `
    <p><strong>Evidence profile:</strong> ${pred.prediction.chosen_evidence_level || "-"}</p>
    <p><strong>Historical comparison:</strong> ${comparable} similar situations · ${matchup} direct matchup situations.</p>
    <p><strong>Interpretation:</strong> Forecast uses only pre-ball historical evidence for this context.</p>
  `;
}

function renderState(pred) {
  const d = pred.delivery;
  const s = pred.pre_delivery_state;
  const selected = state.selectedMatch;
  const title = selected ? matchTitleFromMeta(selected) : `${teamLabel(s.team_batting, "Team A")} vs ${teamLabel(s.team_bowling, "Team B")}`;
  const teamA = selected ? teamLabel(selected.team_a, "Team A") : teamLabel(s.team_batting, "Team A");
  const teamB = selected ? teamLabel(selected.team_b, "Team B") : teamLabel(s.team_bowling, "Team B");
  const matchNumber = selected ? selected.match_number || selected.season_match_number : null;

  els.matchTitle.textContent = title;
  els.matchSubline.textContent = `${d.season_id} · Match ${matchNumber || "-"}`;
  els.teamsValue.textContent = title;
  els.inningsValue.textContent = String(d.innings);
  els.scoreValue.textContent = `${s.score}/${s.wickets}`;
  els.overBallValue.textContent = `${d.over_number}.${d.ball_number}`;

  attachPlayerButton(els.batterValue, d.batter);
  attachPlayerButton(els.nonStrikerValue, d.non_striker);
  attachPlayerButton(els.bowlerValue, d.bowler);

  els.phaseValue.textContent = capitalize(s.phase);
  els.stateScoreValue.textContent = String(s.score || 0);
  els.stateWicketsValue.textContent = String(s.wickets || 0);
  els.stateBallsValue.textContent = `${toOverNotation(s.legal_balls || 0)} overs`;
  const snapshot = pred.prediction.feature_snapshot || {};
  els.stateRrValue.textContent = snapshot.current_run_rate !== undefined ? String(snapshot.current_run_rate) : "-";
  els.stateReqRrValue.textContent = snapshot.required_run_rate !== undefined && snapshot.required_run_rate !== null ? String(snapshot.required_run_rate) : "-";
  els.statePressureValue.textContent = snapshot.pressure_gap !== undefined && snapshot.pressure_gap !== null ? String(snapshot.pressure_gap) : "-";

  if (els.replayBanner) {
    const banner = renderMatchBanner(teamA, teamB);
    els.replayBanner.hidden = !banner;
    els.replayBanner.innerHTML = banner;
  }

  renderReplayHeaderMetrics();
  updateContextBreadcrumb();
}

function renderReveal(reveal) {
  const actual = reveal.actual.actual_outcome;
  const predicted = reveal.comparison.predicted_top_outcome;
  const isCorrect = Boolean(reveal.comparison.is_correct);
  const verdict = isCorrect ? "MATCHGENOME CORRECT" : "MATCHGENOME MISSED";
  const prediction = state.lastPrediction?.prediction || null;
  const strength = replayEvidenceStrength(prediction || {});

  els.actualBlock.className = `actual-block ${isCorrect ? "correct" : "incorrect"}`;
  els.actualBlock.innerHTML = `
    <p class='eyebrow'>WHAT ACTUALLY HAPPENED</p>
    <p class='reveal-outcome'><strong>${outcomeDisplay(actual).toUpperCase()}</strong></p>
    <p>${verdict}</p>
    <p>Forecast: ${outcomeDisplay(predicted)} · Reality: ${outcomeDisplay(actual)}</p>
    <p class='muted'>Total runs ${reveal.actual.delivery_facts.total_runs} · Wicket ${reveal.actual.delivery_facts.is_wicket === 1 ? "Yes" : "No"}</p>
  `;

  const difference = predicted === actual
    ? "Historical context aligned with match reality at this point."
    : "This ball diverged from the strongest historical pattern in this context.";
  els.changeBlock.classList.remove("muted");
  els.changeBlock.innerHTML = `
    <h5>What changed? What did MatchGenome identify?</h5>
    <p>${difference}</p>
    <p><span class='trust-chip'>${strength.label}</span> ${strength.note}</p>
    <p class='muted'>Matchup · Phase · Pressure · Recent state all contributed to this interpretation.</p>
  `;
}

function renderTable(items, fields) {
  if (!items || !items.length) return "<p class='muted'>No sample yet.</p>";
  const head = `<tr>${fields.map((field) => `<th>${field.label}</th>`).join("")}</tr>`;
  const body = items
    .map((row) => `<tr>${fields.map((field) => `<td>${metricDisplay(row[field.key])}</td>`).join("")}</tr>`)
    .join("");
  return `<table class='mini-table'><thead>${head}</thead><tbody>${body}</tbody></table>`;
}

function renderOutcomeBars(outcomes) {
  const entries = Object.entries(outcomes || {}).filter(([, count]) => Number(count || 0) > 0);
  if (!entries.length) return "<p class='muted'>No outcome profile available.</p>";
  const total = entries.reduce((sum, [, count]) => sum + Number(count), 0);
  return entries
    .map(([label, count]) => {
      const pct = (Number(count) / total) * 100;
      return `<div class='prob-row'>
        <span>${outcomeDisplay(label)}</span>
        <div class='bar'><span style='width:${Math.max(3, Math.round(pct))}%'></span></div>
        <strong>${Number(count)}</strong>
      </div>`;
    })
    .join("");
}

function topOutcomeFromDistribution(outcomes) {
  const entries = Object.entries(outcomes || {}).map(([label, count]) => [label, Number(count || 0)]);
  entries.sort((a, b) => b[1] - a[1]);
  return entries.length && entries[0][1] > 0 ? entries[0][0] : null;
}

async function loadPlayer(name) {
  if (!name) {
    els.playerPanel.hidden = true;
    els.playerPrompt.hidden = false;
    return;
  }
  setStatus(`Loading player intelligence for ${name}...`);
  els.playerSearchResults.innerHTML = "";

  const suffix = state.sessionId ? `?session_id=${encodeURIComponent(state.sessionId)}` : "";
  const payload = await api.get(`/api/players/${encodeURIComponent(name)}${suffix}`);
  state.activePlayer = payload.player.name;

  const hasBatting = Boolean(payload.sections?.has_batting);
  const hasBowling = Boolean(payload.sections?.has_bowling);
  state.playerCapabilities = { hasBatting, hasBowling };

  els.playerPrompt.hidden = true;
  els.playerPanel.hidden = false;
  els.playerName.textContent = payload.player.name;
  els.playerRole.textContent = `IPL Intelligence · ${payload.player.role_label || "Player"}`;

  const photo = payload.player.photo || {};
  if ((photo.kind === "local" || photo.kind === "remote") && photo.url) {
    els.playerPhoto.hidden = false;
    els.playerPhoto.src = photo.url;
    els.playerPhoto.alt = `${payload.player.name} player image`;
    els.playerAvatar.hidden = true;
    if (photo.asset_type === "photo" && photo.is_verified_photo) {
      els.playerPhotoMeta.textContent = photo.kind === "remote" ? "Verified original player photo from source." : "Real verified local player photo.";
    } else {
      els.playerPhotoMeta.textContent = photo.kind === "remote" ? "Player image from source feed." : "Local player illustration (not a verified photograph).";
    }
  } else {
    els.playerPhoto.hidden = true;
    els.playerAvatar.hidden = false;
    els.playerAvatar.style.setProperty("--avatar-seed", String(photo.seed || 160));
    els.playerAvatar.textContent = photo.initials || "?";
    els.playerPhotoMeta.textContent = "Fallback avatar (no verified photo available).";
  }

  const overview = payload.overview || {};
  const bat = overview.batting || {};
  const bowl = overview.bowling || {};

  els.playerCareerContext.textContent =
    Number(bat.runs || 0) > 0
      ? `${metricDisplay(bat.runs)} runs · SR ${metricDisplay(bat.strike_rate)} · ${metricDisplay(overview.batting_innings)} innings`
      : Number(bowl.wickets || 0) > 0
        ? `${metricDisplay(bowl.wickets)} wickets · Economy ${metricDisplay(bowl.economy)} · ${metricDisplay(overview.bowling_innings)} innings`
        : `${metricDisplay(overview.matches)} matches in dataset`;

  const topBat = topOutcomeFromDistribution(payload.batting_intelligence?.outcome_distribution || {});
  const topBowl = topOutcomeFromDistribution(payload.bowling_intelligence?.outcome_distribution || {});
  const battingPhaseTop = (payload.batting_intelligence?.by_phase || []).slice().sort((a, b) => Number(b.strike_rate || 0) - Number(a.strike_rate || 0))[0];
  const bowlingPhaseTop = (payload.bowling_intelligence?.by_phase || []).slice().sort((a, b) => Number(b.wickets || 0) - Number(a.wickets || 0))[0];

  const insights = [
    topBat ? `Most common batting outcome: ${outcomeDisplay(topBat)}.` : null,
    topBowl ? `Most common bowling outcome: ${outcomeDisplay(topBowl)}.` : null,
    battingPhaseTop ? `Strongest batting phase: ${capitalize(battingPhaseTop.phase)} (SR ${metricDisplay(battingPhaseTop.strike_rate)}).` : null,
    bowlingPhaseTop ? `Strongest bowling phase: ${capitalize(bowlingPhaseTop.phase)} (${metricDisplay(bowlingPhaseTop.wickets)} wickets).` : null,
  ].filter(Boolean);

  const batYears = (payload.batting_intelligence?.by_season || []).map((r) => Number(r.season_id)).filter(Boolean);
  const bowlYears = (payload.bowling_intelligence?.by_season || []).map((r) => Number(r.season_id)).filter(Boolean);
  const years = [...new Set([...batYears, ...bowlYears])].sort((a, b) => a - b);
  const anchorYears = years.length > 5 ? [years[0], years[Math.floor(years.length / 3)], years[Math.floor((2 * years.length) / 3)], years[years.length - 1]] : years;

  els.playerOverview.innerHTML = `
    <p class='eyebrow'>CAREER SIGNAL</p>
    <div class='event-rail'>
      <p><span>Matches</span><strong>${metricDisplay(overview.matches)}</strong></p>
      <p><span>Runs</span><strong>${metricDisplay(bat.runs)}</strong></p>
      <p><span>Wickets</span><strong>${metricDisplay(bowl.wickets)}</strong></p>
      <p><span>Strike rate</span><strong>${metricDisplay(bat.strike_rate)}</strong></p>
    </div>
    <p class='eyebrow'>CAREER EVOLUTION</p>
    <div class='evolution-rail'>${anchorYears.length ? anchorYears.map((y) => `<span>${y}</span>`).join("") : "<span>Season trail unavailable</span>"}</div>
    <div class='stats-grid'>
      <div><span>Matches</span><strong>${metricDisplay(overview.matches)}</strong></div>
      <div><span>Runs</span><strong>${metricDisplay(bat.runs)}</strong></div>
      <div><span>Strike Rate</span><strong>${metricDisplay(bat.strike_rate)}</strong></div>
      <div><span>Wickets</span><strong>${metricDisplay(bowl.wickets)}</strong></div>
      <div><span>Economy</span><strong>${metricDisplay(bowl.economy)}</strong></div>
      <div><span>Boundaries</span><strong>${metricDisplay(bat.boundaries)}</strong></div>
    </div>
    <div class='panel-block'>
      <h5>What stands out</h5>
      ${insights.length ? insights.map((x) => `<p>${x}</p>`).join("") : "<p class='muted'>No strong insight signals yet for this profile.</p>"}
    </div>
  `;

  els.playerBatting.innerHTML = hasBatting
    ? `
      <div class='metric-rail'><h5>Career snapshot</h5>
      ${renderTable([bat], [
        { key: "runs", label: "Runs" },
        { key: "balls", label: "B" },
        { key: "strike_rate", label: "SR" },
        { key: "average", label: "Avg" },
        { key: "sixes", label: "6s" },
      ])}</div>
      <div class='metric-rail'><h5>Outcome profile</h5>${renderOutcomeBars(payload.batting_intelligence?.outcome_distribution)}</div>
    `
    : "<p class='muted'>No batting sample for this player.</p>";

  els.playerBowling.innerHTML = hasBowling
    ? `
      <div class='metric-rail'><h5>Career snapshot</h5>
      ${renderTable([bowl], [
        { key: "wickets", label: "Wkts" },
        { key: "runs_conceded", label: "Runs" },
        { key: "legal_balls", label: "Balls" },
        { key: "economy", label: "Econ" },
        { key: "strike_rate", label: "SR" },
      ])}</div>
      <div class='metric-rail'><h5>Outcome profile</h5>${renderOutcomeBars(payload.bowling_intelligence?.outcome_distribution)}</div>
    `
    : "<p class='muted'>No bowling sample for this player.</p>";

  els.playerMatchups.innerHTML = `
    <div class='panel-block'>
      <h5>Direct batter vs bowler</h5>
      ${renderTable(payload.matchups?.batter_vs_bowler || [], [
        { key: "opponent", label: "Bowler" },
        { key: "sample_size", label: "Balls" },
        { key: "runs", label: "Runs" },
        { key: "wickets", label: "Wkts" },
        { key: "strike_rate", label: "SR" },
      ])}
    </div>
    <div class='panel-block'>
      <h5>Direct bowler vs batter</h5>
      ${renderTable(payload.matchups?.bowler_vs_batter || [], [
        { key: "opponent", label: "Batter" },
        { key: "sample_size", label: "Balls" },
        { key: "runs_conceded", label: "Runs" },
        { key: "wickets", label: "Wkts" },
        { key: "economy", label: "Economy" },
      ])}
    </div>
  `;

  els.playerSeasons.innerHTML = `
    <div class='panel-block'>
      <h5>Batting season trajectory</h5>
      ${renderTable(payload.batting_intelligence?.by_season || [], [
        { key: "season_id", label: "Season" },
        { key: "runs", label: "Runs" },
        { key: "balls", label: "Balls" },
        { key: "strike_rate", label: "SR" },
      ])}
    </div>
    <div class='panel-block'>
      <h5>Bowling season trajectory</h5>
      ${renderTable(payload.bowling_intelligence?.by_season || [], [
        { key: "season_id", label: "Season" },
        { key: "wickets", label: "Wkts" },
        { key: "runs_conceded", label: "Runs" },
        { key: "economy", label: "Economy" },
      ])}
    </div>
  `;

  els.playerPhases.innerHTML = `
    <div class='panel-block'>
      <h5>Batting by phase</h5>
      ${renderTable(payload.batting_intelligence?.by_phase || [], [
        { key: "phase", label: "Phase" },
        { key: "runs", label: "Runs" },
        { key: "balls", label: "Balls" },
        { key: "strike_rate", label: "SR" },
      ])}
    </div>
    <div class='panel-block'>
      <h5>Bowling by phase</h5>
      ${renderTable(payload.bowling_intelligence?.by_phase || [], [
        { key: "phase", label: "Phase" },
        { key: "wickets", label: "Wkts" },
        { key: "runs_conceded", label: "Runs" },
        { key: "economy", label: "Economy" },
      ])}
    </div>
  `;

  const replay = payload.entry_points?.return_to_replay;
  if (replay) {
    const teams = state.selectedMatch ? matchTitleFromMeta(state.selectedMatch) : `Match ID ${replay.match_id}`;
    els.playerContextText.textContent = `Back to ${teams} · Innings ${replay.innings}`;
  } else if (state.sessionMeta) {
    const teams = state.selectedMatch ? matchTitleFromMeta(state.selectedMatch) : `Match ID ${state.sessionMeta.match_id}`;
    els.playerContextText.textContent = `Active replay: ${teams}`;
  } else {
    els.playerContextText.textContent = "No active replay context.";
  }

  setPlayerTab("overview");
  clearStatus();
}

function formatAskValue(value) {
  const maybeStructuredValue = (raw) => {
    if (typeof raw !== "string") return raw;
    const text = raw.trim();
    if (!text || (!["[", "{"].includes(text[0]) || !["]", "}"].includes(text[text.length - 1]))) return raw;
    try {
      return JSON.parse(text.replace(/'/g, '"'));
    } catch {
      return raw;
    }
  };

  value = maybeStructuredValue(value);
  if (value === null || value === undefined) return "<p class='muted'>No answer available.</p>";

  const prettyKey = (key) =>
    String(key || "")
      .replace(/_/g, " ")
      .replace(/\b\w/g, (char) => char.toUpperCase());

  const scalar = (item) => {
    if (item === null || item === undefined) return "-";
    if (typeof item === "string" || typeof item === "number" || typeof item === "boolean") return String(item);
    return null;
  };

  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return `<p class='answer-inline'>${escapeHtml(String(value))}</p>`;
  }

  const renderRankedRows = (rows) => {
    const ranked = (rows || [])
      .map((row) => (typeof row === "object" && row ? row : null))
      .filter(Boolean)
      .filter((row) => row.player || row.team || row.name || row.value !== undefined);
    if (!ranked.length) return "";
    return `<div class='ask-structured-rank'>${ranked
      .slice(0, 10)
      .map((row, index) => {
        const name = row.player || row.team || row.name || row.label || "-";
        const metric = row.value ?? row.runs ?? row.wickets ?? row.points ?? row.score ?? "-";
        return `<p class='ask-rank-row'><span>${index + 1}</span><span>${escapeHtml(String(name))}</span><strong>${escapeHtml(String(metric))}</strong></p>`;
      })
      .join("")}</div>`;
  };

  const renderMatchSummary = (obj) => {
    const hasMatchShape = obj && (obj.team_a || obj.team_b || obj.winner || obj.match_number || obj.margin);
    if (!hasMatchShape) return "";
    return `
      <section class='ask-match-answer'>
        <p class='match-head'>${escapeHtml(teamLabel(obj.team_a, "Team A"))} <span>vs</span> ${escapeHtml(teamLabel(obj.team_b, "Team B"))}</p>
        <p>${escapeHtml(String(obj.winner || "Result pending"))}${obj.margin ? ` · ${escapeHtml(String(obj.margin))}` : ""}</p>
        <p class='muted'>${escapeHtml(String(obj.match_date || "Date unavailable"))} · IPL ${escapeHtml(String(obj.season || obj.season_id || "-"))} · Match ${escapeHtml(String(obj.match_number || "-"))}</p>
      </section>
    `;
  };

  if (Array.isArray(value)) {
    if (!value.length) return "<p class='muted'>No rows available.</p>";
    const rankList = renderRankedRows(value);
    if (rankList) return rankList;
    return `<ul>${value
      .slice(0, 8)
      .map((item) => {
        const normalized = maybeStructuredValue(item);
        const text = scalar(normalized);
        return `<li>${escapeHtml(text !== null ? text : "Structured value")}</li>`;
      })
      .join("")}</ul>`;
  }

  if (typeof value === "object") {
    const matchSummary = renderMatchSummary(value);
    if (matchSummary) return matchSummary;
    if (Array.isArray(value.rows)) {
      const rankList = renderRankedRows(value.rows);
      if (rankList) return rankList;
    }
    if (value.answer && (typeof value.answer === "string" || typeof value.answer === "number")) {
      return `<p class='answer-inline'>${escapeHtml(String(value.answer))}</p>`;
    }
    const entries = Object.entries(value || {});
    return `<div class='ask-kv-list'>${entries
      .slice(0, 12)
      .map(([key, raw]) => {
        const valueText = scalar(raw);
        return `<p><span>${prettyKey(key)}</span><strong>${escapeHtml(valueText !== null ? valueText : "Structured value")}</strong></p>`;
      })
      .join("")}</div>`;
  }

  return `<p class='answer-inline'>${escapeHtml(String(value))}</p>`;
}

function formatPlanFilters(filters) {
  const items = Object.entries(filters || {});
  if (!items.length) return "No filters";
  return items
    .map(([key, value]) => {
      const pretty = String(key).replace(/_/g, " ");
      return `${pretty}: ${Array.isArray(value) ? value.join(", ") : String(value)}`;
    })
    .join(" · ");
}

function formatResolutionEntities(entities) {
  const items = Object.entries(entities || {}).filter(([, value]) => value !== null && value !== undefined && value !== "");
  if (!items.length) return "No explicit entity resolution details.";
  return `<ul>${items
    .map(([key, value]) => `<li><strong>${String(key).replace(/_/g, " ")}:</strong> ${Array.isArray(value) ? value.join(", ") : String(value)}</li>`)
    .join("")}</ul>`;
}

function maybePlayerFromAsk(result) {
  const plan = result.query_plan || {};
  const entities = plan.entities || {};
  if (typeof entities.player === "string") return entities.player;
  if (typeof entities.bowler === "string") return entities.bowler;
  if (Array.isArray(entities.players) && entities.players.length) return entities.players[0];
  const value = result.result?.value;
  if (value && typeof value.batter === "string") return value.batter;
  if (value && typeof value.player_of_match === "string") return value.player_of_match;
  return null;
}

function maybeMatchRouteFromAsk(result) {
  const entities = result.query_plan?.entities || {};
  const value = result.result?.value;
  const season = Number(entities.season || value?.season || value?.season_id || 0) || "";
  const matchId = Number(value?.match_id || 0) || "";
  const team = typeof entities.team === "string" ? entities.team : "";
  const isMatchLike = Boolean(matchId || entities.match_type || value?.team_a || value?.team_b || value?.winner);
  if (!isMatchLike) return null;
  return {
    view: "matches",
    tab: "results",
    season_id: season,
    match_id: matchId,
    status: "completed",
    team,
  };
}

function isCleanPlayerName(name) {
  const value = String(name || "").trim();
  if (!value) return false;
  if (value.startsWith("[") || value.endsWith("]") || value.includes("',") || value.includes(", '") || value.includes("[") || value.includes("]")) return false;
  return true;
}

function normalizePlayerNames(rawName) {
  const value = String(rawName || "").trim();
  if (!value) return [];
  if (value.startsWith("[") && value.endsWith("]")) {
    try {
      const parsed = JSON.parse(value.replace(/'/g, '"'));
      if (Array.isArray(parsed)) {
        return parsed.map((item) => String(item || "").trim()).filter(Boolean);
      }
    } catch {
      return [];
    }
  }
  return [value];
}

function renderAskResults(payload) {
  if (!payload.results || !payload.results.length) {
    els.askResults.innerHTML = "<p class='muted'>No answer generated yet.</p>";
    return;
  }

  els.askResults.innerHTML = payload.results
    .map((item) => {
      const status = item.status || "unsupported";
      if (status !== "ok") {
        return `<article class='ask-result-card'>
          <p><strong>${item.question}</strong></p>
          <p class='muted'>${item.message || "Unsupported query."}</p>
        </article>`;
      }

      const evidence = item.result?.evidence || {};
      const player = maybePlayerFromAsk(item);
      const seasonTrust = evidence.season_trust || {};
      const confidence = evidence.verification_status || (status === "ok" ? "derived" : "unverified");
      const source = evidence.source || "MatchGenome IPL database";
      const sourceUrl = evidence.source_url ? `<a href='${evidence.source_url}' target='_blank' rel='noreferrer noopener'>source</a>` : "local";
      const coverage = evidence.sample_size || evidence.matches || evidence.rows || "Available in local dataset";
      const trustSummary = humanTrustLabel(seasonTrust.overall_trust);

      const entities = item.query_plan?.entities || {};
      const entityButtons = [];
      const matchRoute = maybeMatchRouteFromAsk(item);
      if (typeof entities.team === "string" && entities.team.trim()) {
        entityButtons.push(`<button type='button' class='ask-entity-link' data-route='teams' data-team='${escapeHtml(entities.team)}' data-question='${escapeHtml(item.question || "")}' >Open Team Intelligence</button>`);
      }
      if (matchRoute) {
        entityButtons.push(`<button type='button' class='ask-match-link' data-season='${matchRoute.season_id || ""}' data-match='${matchRoute.match_id || ""}' data-team='${escapeHtml(matchRoute.team || "")}' data-question='${escapeHtml(item.question || "")}' >Open Match Event Space</button>`);
      }
      if (player) {
        entityButtons.push(`<button type='button' class='ask-player-link' data-player='${escapeHtml(player)}' data-question='${escapeHtml(item.question || "")}' >Open Player Dossier</button>`);
      }
      if (Number(entities.season || 0)) {
        entityButtons.push(`<button type='button' class='ask-season-link' data-season='${Number(entities.season)}' data-question='${escapeHtml(item.question || "")}' >Open Season Patterns</button>`);
      }
      return `<article class='ask-result-card'>
        <section class='ask-flow-result'>
          <div class='ask-layer question'>
            <p class='eyebrow'>QUESTION</p>
            <p class='ask-question'>${escapeHtml(item.question || "")}</p>
          </div>
          <div class='ask-layer answer'>
            <p class='eyebrow'>ANSWER</p>
            <div class='answer-lead'>${formatAskValue(item.result?.value)}</div>
          </div>
          <div class='ask-layer interpretation'>
            <p class='eyebrow'>INTERPRETATION</p>
            <p>${item.result?.label || "Answer from verified local IPL evidence."}</p>
          </div>
          <div class='ask-layer context'>
            <p class='eyebrow'>CONTEXT</p>
            <p>Entities: ${formatPlanFilters(item.query_plan?.entities || {})}</p>
          </div>
          <div class='ask-layer evidence'>
            <p class='eyebrow'>EVIDENCE</p>
            <p>Source: ${source} (${sourceUrl})</p>
            <p>Coverage: ${coverage}</p>
            <details><summary>Show evidence and provenance</summary>${formatResolutionEntities((item.result && item.result.evidence) || {})}</details>
          </div>
          <div class='ask-layer trust'>
            <p class='eyebrow'>TRUST</p>
          <div class='ask-meta-row'>
            <span class='trust-chip'>${trustSummary}</span>
            <span class='trust-chip'>Verification: ${confidence}</span>
          </div>
          </div>
          ${entityButtons.length ? `<div class='row-actions'>${entityButtons.join("")}</div>` : ""}
        </section>
      </article>`;
    })
    .join("");

  els.askResults.querySelectorAll(".ask-player-link").forEach((button) => {
    button.addEventListener("click", () => {
      const player = button.getAttribute("data-player");
      const question = button.getAttribute("data-question") || "";
      if (!player) return;
      setRoute({ view: "player", player, origin: "ask", question });
    });
  });
  els.askResults.querySelectorAll(".ask-season-link").forEach((button) => {
    button.addEventListener("click", () => {
      const season = Number(button.getAttribute("data-season") || 0);
      const question = button.getAttribute("data-question") || "";
      setRoute({ view: "stats", tab: "overview", season_id: season || "", origin: "ask", question });
    });
  });
  els.askResults.querySelectorAll(".ask-entity-link").forEach((button) => {
    button.addEventListener("click", () => {
      const team = button.getAttribute("data-team") || "";
      const question = button.getAttribute("data-question") || "";
      setRoute({ view: "teams", team, origin: "ask", question });
    });
  });
  els.askResults.querySelectorAll(".ask-match-link").forEach((button) => {
    button.addEventListener("click", () => {
      const season = Number(button.getAttribute("data-season") || 0);
      const matchId = Number(button.getAttribute("data-match") || 0);
      const team = button.getAttribute("data-team") || "";
      const question = button.getAttribute("data-question") || "";
      setRoute({
        view: "matches",
        tab: "results",
        season_id: season || "",
        match_id: matchId || "",
        status: "completed",
        team,
        origin: "ask",
        question,
      });
    });
  });
}

async function runAsk() {
  const question = (els.askInput.value || "").trim();
  if (!question) {
    setStatus("Type a question before asking MatchGenome.", "error");
    return;
  }
  setStatus("Asking MatchGenome...");
  state.askContextQuestion = question;
  state.contextOrigin = "ask";
  const payload = await api.post("/api/ask", { question });
  renderAskResults(payload);
  clearStatus();
}

async function searchPlayers() {
  const q = (els.playerSearchInput.value || "").trim();
  if (q.length < 2) {
    els.playerSearchResults.innerHTML = "";
    els.playerSearchHint.textContent = "Type at least 2 characters to see matching players.";
    return;
  }

  els.playerSearchHint.textContent = "Searching players...";
  const payload = await api.get(`/api/players?query=${encodeURIComponent(q)}&limit=20`);
  const seen = new Set();
  const list = (payload.players || [])
    .flatMap((item) => {
      const names = normalizePlayerNames(item.player_name);
      return names.map((player_name) => ({ ...item, player_name }));
    })
    .filter((item) => isCleanPlayerName(item.player_name))
    .filter((item) => {
      const key = String(item.player_name || "").toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });

  if (!list.length) {
    els.playerSearchResults.innerHTML = "";
    els.playerSearchHint.textContent = "No matching players found.";
    return;
  }

  els.playerSearchHint.textContent = `${list.length} player${list.length === 1 ? "" : "s"} matched.`;
  els.playerSearchResults.innerHTML = "";
  list.forEach((item) => {
    const photo = item.photo || {};
    const kind = photo.kind === "remote" || photo.asset_type === "photo" ? "photo" : photo.kind === "local" ? "illustration" : "avatar";
    const row = document.createElement("button");
    row.type = "button";
    row.className = "search-result";
    row.innerHTML = `<span>${item.player_name}</span><small class='muted'>${kind}</small>`;
    row.onclick = () => {
      els.playerSearchResults.innerHTML = "";
      els.playerSearchHint.textContent = `Showing ${item.player_name}.`;
      setRoute({ view: "player", player: item.player_name });
    };
    els.playerSearchResults.appendChild(row);
  });
}

async function loadPlayerDiscovery() {
  if (!els.playerDiscovery) return;
  const payload = await api.get("/api/players?limit=12");
  const players = (payload.players || [])
    .flatMap((item) => normalizePlayerNames(item.player_name).map((name) => ({ name, item })))
    .filter((row) => isCleanPlayerName(row.name))
    .slice(0, 8);
  if (!players.length) {
    els.playerDiscovery.innerHTML = "<p class='muted'>Player discovery is not available in this dataset slice.</p>";
    return;
  }
  els.playerDiscovery.innerHTML = `
    <p class='eyebrow'>PLAYER DISCOVERY</p>
    <p class='muted'>Open a real player genome from verified local data.</p>
    <div class='entity-row'>
      ${players
        .map((row) => `<button type='button' class='entity-chip discover-player' data-player='${encodeURIComponent(row.name)}'>${escapeHtml(row.name)}</button>`)
        .join("")}
    </div>
  `;
  els.playerDiscovery.querySelectorAll(".discover-player").forEach((button) => {
    button.addEventListener("click", () => {
      const player = decodeURIComponent(button.getAttribute("data-player") || "");
      if (!player) return;
      setRoute({ view: "player", player });
    });
  });
}

async function loadSeasons() {
  const payload = await api.get("/api/seasons");
  state.seasons = payload.seasons || [];
  els.seasonSelect.innerHTML = "";
  state.seasons.forEach((s) => els.seasonSelect.appendChild(option(`Season ${s.season_id}`, s.season_id)));
}

async function loadMatches() {
  const seasonId = Number(els.seasonSelect.value);
  const payload = await api.get(`/api/seasons/${seasonId}/matches`);
  state.matches = payload.matches || [];
  state.hasTeamIdOnlyData = state.matches.some((m) => hasUnresolvedTeamName(m.team_a) || hasUnresolvedTeamName(m.team_b));
  applyTeamDataNotice();

  renderTeamFilterOptions();

  state.selectedMatch = state.matches.length ? state.matches[0] : null;
  state.selectedMatchId = state.selectedMatch ? Number(state.selectedMatch.match_id) : null;
  if (state.selectedMatch) {
    const first = state.selectedMatch;
    els.selectedMatchMeta.textContent = `${matchTitleFromMeta(first)} · IPL ${first.season_id} · Match ${first.match_number || first.season_match_number || "-"}`;
  } else {
    els.selectedMatchMeta.textContent = "Select a match card to continue.";
  }
  renderMatchCards();
}

async function loadInnings() {
  if (state.selectedMatchId === null) {
    els.inningsSelect.innerHTML = "";
    els.startReplayBtn.disabled = true;
    return;
  }

  const payload = await api.get(`/api/matches/${state.selectedMatchId}/innings`);
  state.innings = payload.innings || [];
  els.inningsSelect.innerHTML = "";
  state.innings.forEach((item) => {
    const text = `Innings ${item.innings}: ${teamLabel(item.team_batting, "Team A")} batting (${item.runs}/${item.wickets})`;
    els.inningsSelect.appendChild(option(text, item.innings));
  });
  state.selectedInnings = state.innings.length ? state.innings[0] : null;
  els.startReplayBtn.disabled = !state.innings.length;
}

async function refreshSessionMeta() {
  if (!state.sessionId) return;
  state.sessionMeta = await api.get(`/api/replays/${state.sessionId}`);
}

async function startReplay() {
  if (state.selectedMatchId === null) return;
  const innings = Number(els.inningsSelect.value);

  setStatus("Creating replay session...");
  const created = await api.post("/api/replays", { match_id: state.selectedMatchId, innings });

  state.sessionId = created.session_id;
  state.sessionMeta = created;
  state.lastPrediction = null;
  state.timeline = [];
  state.selectedTimelineIndex = -1;
  state.userCall = null;

  els.replayPanel.hidden = false;
  updateReplayLayoutState();
  els.actualBlock.className = "actual-block";
  els.actualBlock.textContent = "Reveal the ball to see actual outcome.";
  els.predictedTop.textContent = "READY";
  els.predictedPct.textContent = "Before reveal";
  els.probabilityBars.innerHTML = "";
  els.whyBlock.textContent = "Generate a prediction to see the evidence narrative.";
  els.changeBlock.className = "explain-block muted";
  els.changeBlock.textContent = "Prediction change diagnostics will appear after the next ball.";

  setReplayTab("prediction");
  buildUserCallOptions();
  setUiState(UiState.READY);
  renderReplayHeaderMetrics();
  updateTimeline();
  clearStatus();
}

async function predictNext() {
  if (!state.sessionId) return;
  setStatus("Calculating prediction...");

  const pred = await api.post(`/api/replays/${state.sessionId}/predict`, {});
  state.lastPrediction = pred;
  renderState(pred);
  renderPrediction(pred);

  const exists = state.timeline.find((x) => x.over === pred.delivery.over_number && x.ball === pred.delivery.ball_number);
  if (!exists) {
    state.timeline.push({
      over: pred.delivery.over_number,
      ball: pred.delivery.ball_number,
      batter: pred.delivery.batter,
      bowler: pred.delivery.bowler,
      user_call: state.userCall,
      predicted: pred.prediction.predicted_top_outcome,
      actual: null,
      status: "pending",
    });
  }

  await refreshSessionMeta();
  updateTimeline();
  setUiState(UiState.PREDICTION_AVAILABLE);
  clearStatus();
}

async function revealNext() {
  if (!state.sessionId) return;
  setStatus("Revealing actual delivery...");

  const reveal = await api.post(`/api/replays/${state.sessionId}/reveal`, {});
  renderReveal(reveal);

  const last = state.timeline[state.timeline.length - 1];
  if (last) {
    last.actual = reveal.actual.actual_outcome;
    last.status = reveal.comparison.is_correct ? "correct" : "incorrect";
  }

  await refreshSessionMeta();
  updateTimeline();
  renderReplayHeaderMetrics();

  if (state.sessionMeta?.status === "COMPLETED") {
    setUiState(UiState.COMPLETED);
    setStatus("Replay completed.");
  } else {
    setUiState(UiState.PREDICTION_REVEALED);
    clearStatus();
  }
}

async function restartReplay() {
  if (!state.sessionId) return;
  setStatus("Restarting replay...");
  const payload = await api.post(`/api/replays/${state.sessionId}/restart`, {});
  state.sessionMeta = payload;
  state.timeline = [];
  state.lastPrediction = null;
  state.selectedTimelineIndex = -1;
  state.userCall = null;
  buildUserCallOptions();
  updateReplayLayoutState();

  els.actualBlock.className = "actual-block";
  els.actualBlock.textContent = "Reveal the ball to see actual outcome.";
  els.predictedTop.textContent = "READY";
  els.predictedPct.textContent = "Before reveal";
  els.probabilityBars.innerHTML = "";
  setUiState(UiState.READY);
  updateTimeline();
  clearStatus();
}

function syncRoute() {
  const route = parseRoute();
  state.contextOrigin = route.origin || "";
  if (route.question) state.askContextQuestion = route.question;

  if (route.view === "player") {
    setView("player");
    if (route.player) {
      loadPlayer(route.player)
        .then(() => {
          if (!state.sessionMeta && state.contextOrigin === "ask" && state.askContextQuestion) {
            els.playerContextText.textContent = `Opened from Ask: "${state.askContextQuestion}"`;
          }
        })
        .catch((err) => setStatus(err.message || "Failed to load player.", "error"));
    } else {
      els.playerPanel.hidden = true;
      els.playerPrompt.hidden = false;
      els.playerPrompt.innerHTML = "<p class='eyebrow'>PLAYER DISCOVERY</p><p class='muted'>Choose a player from discovery or search to open a full genome profile.</p>";
    }
    return;
  }

  if (route.view === "ask") {
    setView("ask");
    return;
  }

  if (route.view === "matches" || route.view === "fixtures" || route.view === "results") {
    setView("matches");
    setMatchesTab(route.view === "results" ? "results" : route.tab || "fixtures");
    if (route.seasonId) {
      els.fixturesSeasonSelect.value = String(route.seasonId);
    }
    if (route.status && state.matchesTab === "fixtures") {
      els.fixturesStatusSelect.value = String(route.status);
    } else {
      els.fixturesStatusSelect.value = state.matchesTab === "results" ? "completed" : "";
    }
    if (route.team) {
      els.fixturesTeamInput.value = String(route.team);
    } else {
      els.fixturesTeamInput.value = "";
    }
    state.selectedFixtureMatchId = route.matchId ? Number(route.matchId) : null;
    if (route.matchId) {
      loadFixtureDetail(Number(route.matchId)).catch((err) => setStatus(err.message || "Failed to load match details", "error"));
    } else {
      els.fixtureDetail.innerHTML = "<p class='eyebrow'>MATCH NARRATIVE</p><p class='muted'>Pick a match from the event wall to inspect turning points, score narrative, and contextual actions.</p>";
    }
    loadFixtures().catch((err) => setStatus(err.message || "Failed to load fixtures", "error"));
    loadResults().catch((err) => setStatus(err.message || "Failed to load results", "error"));
    return;
  }

  if (route.view === "predict") {
    setView("predict");
    return;
  }

  if (route.view === "teams") {
    setView("teams");
    if (route.team) {
      const hasTeamOption = Array.from(els.teamsSelect.options || []).some((opt) => String(opt.value) === String(route.team));
      if (hasTeamOption) {
        els.teamsSelect.value = String(route.team);
      }
    }
    if (!els.teamSeasonSelect.value && els.statsSeasonSelect.value) {
      els.teamSeasonSelect.value = String(els.statsSeasonSelect.value);
    }
    if (!els.teamSeasonSelect.value && els.teamSeasonSelect.options.length) {
      els.teamSeasonSelect.value = String(els.teamSeasonSelect.options[0].value || "");
    }
    loadTeamDetails().catch((err) => setStatus(err.message || "Failed to load team", "error"));
    return;
  }

  if (route.view === "stats") {
    setView("stats");
    if (route.seasonId) {
      els.statsSeasonSelect.value = String(route.seasonId);
    }
    setStatsTab(route.tab || state.statsTab || "overview");
    loadStatsWorkspace().catch((err) => setStatus(err.message || "Failed to load stats", "error"));
    return;
  }

  if (route.view === "replay" || route.view === "time_machine") {
    setView("replay");
    updateReplayLayoutState();
    selectMatchInTimeMachine(route.seasonId, route.matchId).catch((err) => setStatus(err.message || "Failed to load match", "error"));
    return;
  }

  if (route.view === "methodology") {
    setView("methodology");
    return;
  }

  setView("home");
  const requested = normalizeSeason(route.seasonId);
  if (requested) {
    state.homeSelectedSeason = requested;
  } else {
    state.homeSelectedSeason = state.latestSeasonId || latestSeasonFromState();
  }
  loadHomeLaunchpad(state.homeSelectedSeason).catch((err) => setStatus(err.message || "Failed to load home context", "error"));
}

function attachEvents() {
  els.goHomeBtn.addEventListener("click", () => setRoute({ view: "home" }));
  els.goMatchesBtn.addEventListener("click", () => setRoute({ view: "matches", tab: state.matchesTab }));
  els.goTeamsBtn.addEventListener("click", () => setRoute({ view: "teams" }));
  els.goPredictBtn.addEventListener("click", () => setRoute({ view: "predict" }));
  els.goStatsBtn.addEventListener("click", () => setRoute({ view: "stats", tab: state.statsTab || "overview" }));
  els.goReplayBtn.addEventListener("click", () => setRoute({ view: "replay" }));
  els.goAskBtn.addEventListener("click", () => setRoute({ view: "ask" }));
  els.goPlayerIntelligenceBtn.addEventListener("click", () => setRoute({ view: "player", player: state.activePlayer || "" }));

  els.exploreMatchBtn.addEventListener("click", () => setRoute({ view: "matches" }));
  if (els.goTeamsIntroBtn) {
    els.goTeamsIntroBtn.addEventListener("click", () => setRoute({ view: "teams" }));
  }
  els.goPlayersIntroBtn.addEventListener("click", () => setRoute({ view: "player", player: state.activePlayer || "" }));
  if (els.homeAskBtn && els.homeAskInput) {
    els.homeAskBtn.addEventListener("click", () => {
      const question = (els.homeAskInput.value || "").trim();
      if (question) {
        els.askInput.value = question;
      }
      setRoute({ view: "ask" });
    });
    els.homeAskInput.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      const question = (els.homeAskInput.value || "").trim();
      if (!question) return;
      els.askInput.value = question;
      setRoute({ view: "ask" });
    });
  }
  if (els.homeReplayBtn) {
    els.homeReplayBtn.addEventListener("click", () => {
      const season = Number(els.homeReplaySeasonSelect?.value || 0);
      setRoute({ view: "replay", season_id: season || "" });
    });
  }
  if (els.homeReplaySeasonSelect) {
    els.homeReplaySeasonSelect.addEventListener("change", () => {
      const season = normalizeSeason(els.homeReplaySeasonSelect.value);
      if (!season) return;
      state.homeSelectedSeason = season;
      loadHomeLaunchpad(season).catch((err) => setStatus(err.message || "Failed to switch chapter", "error"));
    });
  }
  if (els.predictToReplayBtn) {
    els.predictToReplayBtn.addEventListener("click", () => setRoute({ view: "replay" }));
  }
  if (els.predictToPlayersBtn) {
    els.predictToPlayersBtn.addEventListener("click", () => setRoute({ view: "player" }));
  }
  if (els.predictToAskBtn) {
    els.predictToAskBtn.addEventListener("click", () => setRoute({ view: "ask" }));
  }

  els.askSubmitBtn.addEventListener("click", () => runAsk().catch((err) => setStatus(err.message || "Ask failed.", "error")));

  const debouncedFixturesRoute = (() => {
    let timer = null;
    return () => {
      if (timer) window.clearTimeout(timer);
      timer = window.setTimeout(() => setRoute(fixturesRoute()), 180);
    };
  })();
  els.fixturesRefreshBtn.addEventListener("click", () => setRoute(fixturesRoute(state.selectedFixtureMatchId || "")));
  els.fixturesSeasonSelect.addEventListener("change", () => setRoute(fixturesRoute()));
  els.fixturesStatusSelect.addEventListener("change", () => {
    state.matchesTab = "fixtures";
    setRoute(fixturesRoute());
  });
  els.fixturesTeamInput.addEventListener("input", debouncedFixturesRoute);
  if (els.matchTabFixturesBtn) {
    els.matchTabFixturesBtn.addEventListener("click", () => {
      state.matchesTab = "fixtures";
      setRoute(fixturesRoute(state.selectedFixtureMatchId || ""));
    });
  }
  if (els.matchTabResultsBtn) {
    els.matchTabResultsBtn.addEventListener("click", () => {
      state.matchesTab = "results";
      setRoute(fixturesRoute(state.selectedFixtureMatchId || ""));
    });
  }
  els.teamLoadBtn.addEventListener("click", () => loadTeamDetails().catch((err) => setStatus(err.message || "Failed to load team", "error")));
  els.teamsSelect.addEventListener("change", () => loadTeamDetails().catch((err) => setStatus(err.message || "Failed to load team", "error")));
  els.teamSeasonSelect.addEventListener("change", () => loadTeamDetails().catch((err) => setStatus(err.message || "Failed to load team", "error")));
  els.statsRefreshBtn.addEventListener("click", () => loadStatsWorkspace().catch((err) => setStatus(err.message || "Failed to load stats", "error")));
  els.statsSeasonSelect.addEventListener("change", () => loadStatsWorkspace().catch((err) => setStatus(err.message || "Failed to load stats", "error")));
  if (els.statsCompareBtn) {
    els.statsCompareBtn.addEventListener("click", () => compareSeasonSignals().catch((err) => setStatus(err.message || "Failed to compare seasons", "error")));
  }
  if (els.statsCompareSeasonA) {
    els.statsCompareSeasonA.addEventListener("change", () => compareSeasonSignals().catch((err) => setStatus(err.message || "Failed to compare seasons", "error")));
  }
  if (els.statsCompareSeasonB) {
    els.statsCompareSeasonB.addEventListener("change", () => compareSeasonSignals().catch((err) => setStatus(err.message || "Failed to compare seasons", "error")));
  }
  const statsTabs = [
    [els.statsTabOverviewBtn, "overview"],
    [els.statsTabBattingBtn, "batting"],
    [els.statsTabBowlingBtn, "bowling"],
    [els.statsTabRecordsBtn, "records"],
    [els.statsTabGraphsBtn, "graphs"],
    [els.statsTabPointsBtn, "points"],
  ];
  statsTabs.forEach(([btn, tab]) => {
    if (!btn) return;
    btn.addEventListener("click", () => setRoute({ view: "stats", tab, season_id: Number(els.statsSeasonSelect.value || 0) || "" }));
  });
  els.askInput.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      runAsk().catch((err) => setStatus(err.message || "Ask failed.", "error"));
    }
  });
  els.askExamples.querySelectorAll("button[data-prompt]").forEach((button) => {
    button.addEventListener("click", () => {
      els.askInput.value = button.getAttribute("data-prompt") || "";
      runAsk().catch((err) => setStatus(err.message || "Ask failed.", "error"));
    });
  });
  document.querySelectorAll(".ask-domain-strip button[data-route]").forEach((button) => {
    button.addEventListener("click", () => {
      const route = button.getAttribute("data-route") || "";
      if (!route) return;
      const map = {
        player: { view: "player" },
        teams: { view: "teams" },
        matches: { view: "matches" },
        stats: { view: "stats", tab: "overview", season_id: Number(els.statsSeasonSelect.value || 0) || "" },
        replay: { view: "replay" },
      };
      setRoute(map[route] || { view: "ask" });
    });
  });

  els.seasonSelect.addEventListener("change", async () => {
    try {
      await loadMatches();
      await loadInnings();
    } catch (err) {
      setStatus(err.message || "Failed to load season matches.", "error");
    }
  });
  els.matchSearchInput.addEventListener("input", renderMatchCards);
  els.teamFilterSelect.addEventListener("change", () => {
    renderMatchCards();
    if (!(els.teamFilterSelect.value || "").trim()) return;
    const firstMatch = filteredMatches()[0];
    if (!firstMatch) return;
    jumpToReplayWidgets(firstMatch).catch((err) => setStatus(err.message || "Could not start replay.", "error"));
  });
  els.inningsSelect.addEventListener("change", () => {
    const innings = Number(els.inningsSelect.value);
    state.selectedInnings = state.innings.find((x) => Number(x.innings) === innings) || null;
    els.startReplayBtn.disabled = !state.selectedInnings;
  });

  els.startReplayBtn.addEventListener("click", () => startReplay().catch((err) => setStatus(err.message || "Could not start replay.", "error")));
  els.predictBtn.addEventListener("click", () => predictNext().catch((err) => setStatus(err.message || "Prediction failed.", "error")));
  els.nextBtn.addEventListener("click", () => predictNext().catch((err) => setStatus(err.message || "Prediction failed.", "error")));
  els.revealBtn.addEventListener("click", () => revealNext().catch((err) => setStatus(err.message || "Reveal failed.", "error")));
  els.restartBtn.addEventListener("click", () => restartReplay().catch((err) => setStatus(err.message || "Restart failed.", "error")));
  els.previousBtn.addEventListener("click", () => setReplayTab("ball_by_ball"));

  bindReplayTabTarget(els.tabPredictionBtn, "prediction");
  bindReplayTabTarget(els.tabBallByBallBtn, "ball_by_ball");
  bindReplayTabTarget(els.tabEvidenceBtn, "evidence");

  els.backToReplayBtn.addEventListener("click", () => setRoute({ view: "replay" }));
  els.exploreReplayBtn.addEventListener("click", () => setRoute({ view: "replay" }));
  els.closePlayerBtn.addEventListener("click", () => {
    state.activePlayer = null;
    setRoute({ view: "player", player: "" });
  });

  els.playerSearchBtn.addEventListener("click", () => searchPlayers().catch((err) => setStatus(err.message || "Player search failed.", "error")));
  els.playerSearchInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") searchPlayers().catch((err) => setStatus(err.message || "Player search failed.", "error"));
  });

  els.playerTabOverviewBtn.addEventListener("click", () => setPlayerTab("overview"));
  els.playerTabBattingBtn.addEventListener("click", () => setPlayerTab("batting"));
  els.playerTabBowlingBtn.addEventListener("click", () => setPlayerTab("bowling"));
  els.playerTabMatchupsBtn.addEventListener("click", () => setPlayerTab("matchups"));
  els.playerTabSeasonsBtn.addEventListener("click", () => setPlayerTab("seasons"));
  els.playerTabPhasesBtn.addEventListener("click", () => setPlayerTab("phases"));

  window.addEventListener("hashchange", syncRoute);
}

async function bootstrap() {
  try {
    setStatus("Loading MatchGenome...");
    await loadSeasons();
    state.latestSeasonId = latestSeasonFromState();
    state.homeSelectedSeason = state.latestSeasonId;
    await loadMatches();
    await loadInnings();
    await loadTeams();
    [els.fixturesSeasonSelect, els.statsSeasonSelect, els.teamSeasonSelect, els.homeReplaySeasonSelect].forEach((node) => {
      if (!node) return;
      node.innerHTML = "";
      state.seasons.forEach((s) => node.appendChild(option(`Season ${s.season_id}`, s.season_id)));
    });
    if (state.latestSeasonId) {
      [els.seasonSelect, els.fixturesSeasonSelect, els.statsSeasonSelect, els.teamSeasonSelect, els.homeReplaySeasonSelect].forEach((node) => {
        if (node) node.value = String(state.latestSeasonId);
      });
    }
    if (els.statsCompareSeasonA && els.statsCompareSeasonB) {
      els.statsCompareSeasonA.innerHTML = "";
      els.statsCompareSeasonB.innerHTML = "";
      state.seasons.forEach((s) => {
        els.statsCompareSeasonA.appendChild(option(`Season ${s.season_id}`, s.season_id));
        els.statsCompareSeasonB.appendChild(option(`Season ${s.season_id}`, s.season_id));
      });
      const latest = state.latestSeasonId || normalizeSeason(els.statsSeasonSelect.value);
      const prev = state.seasons.length > 1 ? normalizeSeason(state.seasons[state.seasons.length - 2].season_id) : latest;
      if (latest) els.statsCompareSeasonB.value = String(latest);
      if (prev) els.statsCompareSeasonA.value = String(prev);
    }
    await loadPlayerDiscovery();
    if (els.fixturesStatusSelect) {
      els.fixturesStatusSelect.value = "";
    }
    attachEvents();
    buildUserCallOptions();
    setReplayTab("prediction");
    setPlayerTab("overview");
    setStatsTab("overview");
    setUiState(UiState.SELECT_MATCH);
    await compareSeasonSignals();
    syncRoute();
    clearStatus();
  } catch (err) {
    setStatus(err.message || "Unable to initialize the product.", "error");
  }
}

bootstrap();

