const UiState = {
  SELECT_MATCH: "SELECT_MATCH",
  READY: "READY",
  PREDICTION_AVAILABLE: "PREDICTION_AVAILABLE",
  PREDICTION_REVEALED: "PREDICTION_REVEALED",
  COMPLETED: "COMPLETED",
  ERROR: "ERROR",
};

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
  uiState: UiState.SELECT_MATCH,
  seasons: [],
  matches: [],
  innings: [],
  selectedMatchId: null,
  sessionId: null,
  sessionMeta: null,
  lastPrediction: null,
  timeline: [],
  view: "home",
  activePlayer: null,
  replayTab: "prediction",
  playerTab: "overview",
  selectedMatch: null,
  selectedInnings: null,
  selectedTimelineIndex: -1,
  playerCapabilities: { hasBatting: false, hasBowling: false },
  hasTeamIdOnlyData: false,
};

const els = {
  homeView: document.getElementById("homeView"),
  methodologyView: document.getElementById("methodologyView"),
  goHomeBtn: document.getElementById("goHomeBtn"),
  seasonSelect: document.getElementById("seasonSelect"),
  inningsSelect: document.getElementById("inningsSelect"),
  matchSearchInput: document.getElementById("matchSearchInput"),
  selectedMatchMeta: document.getElementById("selectedMatchMeta"),
  matchCards: document.getElementById("matchCards"),
  startReplayBtn: document.getElementById("startReplayBtn"),
  exploreMatchBtn: document.getElementById("exploreMatchBtn"),
  goPlayersIntroBtn: document.getElementById("goPlayersIntroBtn"),
  productIntro: document.getElementById("productIntro"),
  matchListSummary: document.getElementById("matchListSummary"),
  teamDataNotice: document.getElementById("teamDataNotice"),
  statusBanner: document.getElementById("statusBanner"),
  timeMachineView: document.getElementById("timeMachineView"),
  playerView: document.getElementById("playerView"),
  goTimeMachineBtn: document.getElementById("goTimeMachineBtn"),
  goPlayerIntelligenceBtn: document.getElementById("goPlayerIntelligenceBtn"),
  goMethodologyBtn: document.getElementById("goMethodologyBtn"),
  openFeaturedReplayBtn: document.getElementById("openFeaturedReplayBtn"),
  replayPanel: document.getElementById("replayPanel"),
  tabPredictionBtn: document.getElementById("tabPredictionBtn"),
  tabBallByBallBtn: document.getElementById("tabBallByBallBtn"),
  tabEvidenceBtn: document.getElementById("tabEvidenceBtn"),
  panelPrediction: document.getElementById("panelPrediction"),
  panelBallByBall: document.getElementById("panelBallByBall"),
  panelEvidence: document.getElementById("panelEvidence"),
  matchTitle: document.getElementById("matchTitle"),
  matchSubline: document.getElementById("matchSubline"),
  replayTeamNotice: document.getElementById("replayTeamNotice"),
  teamsValue: document.getElementById("teamsValue"),
  inningsValue: document.getElementById("inningsValue"),
  scoreValue: document.getElementById("scoreValue"),
  overBallValue: document.getElementById("overBallValue"),
  progressHeaderValue: document.getElementById("progressHeaderValue"),
  accuracyValue: document.getElementById("accuracyValue"),
  timelineTrack: document.getElementById("timelineTrack"),
  ballByBallRows: document.getElementById("ballByBallRows"),
  progressValue: document.getElementById("progressValue"),
  progressFill: document.getElementById("progressFill"),
  prevBallValue: document.getElementById("prevBallValue"),
  nextBallValue: document.getElementById("nextBallValue"),
  batterValue: document.getElementById("batterValue"),
  nonStrikerValue: document.getElementById("nonStrikerValue"),
  bowlerValue: document.getElementById("bowlerValue"),
  phaseValue: document.getElementById("phaseValue"),
  stateScoreValue: document.getElementById("stateScoreValue"),
  stateWicketsValue: document.getElementById("stateWicketsValue"),
  stateBallsValue: document.getElementById("stateBallsValue"),
  remainingValue: document.getElementById("remainingValue"),
  predictedTop: document.getElementById("predictedTop"),
  predictedPct: document.getElementById("predictedPct"),
  probabilityBars: document.getElementById("probabilityBars"),
  whyBlock: document.getElementById("whyBlock"),
  evidenceBlock: document.getElementById("evidenceBlock"),
  distributionBlock: document.getElementById("distributionBlock"),
  technicalEvidenceBlock: document.getElementById("technicalEvidenceBlock"),
  predictBtn: document.getElementById("predictBtn"),
  revealBtn: document.getElementById("revealBtn"),
  nextBtn: document.getElementById("nextBtn"),
  previousBtn: document.getElementById("previousBtn"),
  restartBtn: document.getElementById("restartBtn"),
  actualBlock: document.getElementById("actualBlock"),
  backToReplayBtn: document.getElementById("backToReplayBtn"),
  playerSearchInput: document.getElementById("playerSearchInput"),
  playerSearchBtn: document.getElementById("playerSearchBtn"),
  playerSearchHint: document.getElementById("playerSearchHint"),
  playerSearchResults: document.getElementById("playerSearchResults"),
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
  battingTitle: document.getElementById("battingTitle"),
  bowlingTitle: document.getElementById("bowlingTitle"),
  playerBatting: document.getElementById("playerBatting"),
  playerBowling: document.getElementById("playerBowling"),
  playerMatchups: document.getElementById("playerMatchups"),
  playerSeasons: document.getElementById("playerSeasons"),
  playerPhases: document.getElementById("playerPhases"),
  closePlayerBtn: document.getElementById("closePlayerBtn"),
};

function parseRoute() {
  const params = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  return {
    view: params.get("view") || "home",
    player: params.get("player") || "",
  };
}

function setRoute(route) {
  const params = new URLSearchParams();
  Object.entries(route).forEach(([k, v]) => {
    if (v !== undefined && v !== null && String(v) !== "") params.set(k, String(v));
  });
  window.location.hash = params.toString();
}

function setStatus(message, kind = "info") {
  els.statusBanner.hidden = false;
  els.statusBanner.textContent = message;
  els.statusBanner.style.borderColor = kind === "error" ? "#ef4444" : "#2a3250";
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

function applyTeamDataNotice() {
  const msg = "Some matches still include unresolved team IDs. MatchGenome shows the original code only when verified enrichment is unavailable.";
  els.teamDataNotice.hidden = !state.hasTeamIdOnlyData;
  els.replayTeamNotice.hidden = !state.hasTeamIdOnlyData;
  if (state.hasTeamIdOnlyData) {
    els.teamDataNotice.textContent = msg;
    els.replayTeamNotice.textContent = msg;
  }
}

function matchTitleFromMeta(meta) {
  if (!meta) return "Team A vs Team B";
  return `${teamLabel(meta.team_a, "Team A")} vs ${teamLabel(meta.team_b, "Team B")}`;
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

function capitalize(value) {
  return value ? `${value}`.charAt(0).toUpperCase() + `${value}`.slice(1) : "-";
}

function metricDisplay(value) {
  return value === null || value === undefined ? "-" : String(value);
}

function photoMetaLabel(photo) {
  if (!photo) return "No image metadata.";
  if (photo.kind === "placeholder") return "Fallback avatar (no verified player image available).";
  if (photo.asset_type === "photo" && photo.is_verified_photo) return "Verified local player photo.";
  return "Local player illustration (not a real photograph).";
}

function setView(view) {
  state.view = view;
  const isHome = view === "home";
  const isTimeMachine = view === "time_machine";
  const isPlayer = view === "player";
  const isMethodology = view === "methodology";

  els.homeView.hidden = !isHome;
  els.timeMachineView.hidden = !isTimeMachine;
  els.playerView.hidden = !isPlayer;
  els.methodologyView.hidden = !isMethodology;

  const nav = [
    [els.goHomeBtn, isHome],
    [els.goTimeMachineBtn, isTimeMachine],
    [els.goPlayerIntelligenceBtn, isPlayer],
    [els.goMethodologyBtn, isMethodology],
  ];
  nav.forEach(([btn, active]) => {
    btn.classList.toggle("primary", active);
    btn.setAttribute("aria-current", active ? "page" : "false");
  });
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
    btn.setAttribute("aria-selected", active ? "true" : "false");
    panel.hidden = !active;
  });
}

function setPlayerTab(tab, hasBatting, hasBowling, hasSeasonData, hasPhaseData) {
  state.playerTab = tab;
  const map = {
    overview: [els.playerTabOverviewBtn, els.playerPanelOverview],
    batting: [els.playerTabBattingBtn, els.playerPanelBatting],
    bowling: [els.playerTabBowlingBtn, els.playerPanelBowling],
    matchups: [els.playerTabMatchupsBtn, els.playerPanelMatchups],
    seasons: [els.playerTabSeasonsBtn, els.playerPanelSeasons],
    phases: [els.playerTabPhasesBtn, els.playerPanelPhases],
  };
  Object.entries(map).forEach(([name, [btn, panel]]) => {
    const active = name === tab;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-selected", active ? "true" : "false");
    panel.hidden = !active;
  });
  els.playerTabBattingBtn.hidden = !hasBatting;
  els.playerTabBowlingBtn.hidden = !hasBowling;
  els.playerTabSeasonsBtn.hidden = !hasSeasonData;
  els.playerTabPhasesBtn.hidden = !hasPhaseData;
}

function setUiState(nextState) {
  state.uiState = nextState;
  const canPredict = nextState === UiState.READY || nextState === UiState.PREDICTION_REVEALED;
  els.predictBtn.disabled = !canPredict;
  els.revealBtn.disabled = nextState !== UiState.PREDICTION_AVAILABLE;
  els.nextBtn.disabled = nextState !== UiState.PREDICTION_REVEALED;
}

function option(label, value) {
  const opt = document.createElement("option");
  opt.value = String(value);
  opt.textContent = label;
  return opt;
}

function toPct(value) {
  return `${(value * 100).toFixed(1)}%`;
}

function evidenceLabel(raw) {
  const map = {
    global: "Overall IPL historical context",
    batter_bowler: "Direct batter vs bowler history",
    batter_bowler_type: "Batter vs similar bowler type history",
    bowler_batter_type: "Bowler vs similar batter type history",
    batter_type_bowler_type: "Similar batter type vs bowler type history",
  };
  return map[raw] || raw;
}

function sampleTier(sample) {
  if (sample >= 120) return "high";
  if (sample >= 40) return "medium";
  if (sample >= 12) return "low";
  return "small";
}

function sampleLabel(sample) {
  const tier = sampleTier(sample);
  if (tier === "high") return "High confidence";
  if (tier === "medium") return "Medium confidence";
  if (tier === "low") return "Low confidence";
  return "Small sample";
}

function attachPlayerButton(button, name) {
  button.textContent = name || "-";
  button.disabled = !name;
  button.onclick = () => {
    if (!name) return;
    setRoute({ view: "player", player: name });
  };
}

function renderMatchCards() {
  const needle = (els.matchSearchInput.value || "").trim().toLowerCase();
  const filtered = state.matches.filter((m) => {
    if (!needle) return true;
    return [m.team_a, m.team_b, String(m.match_id)].join(" ").toLowerCase().includes(needle);
  });

  els.matchCards.innerHTML = "";
  els.matchListSummary.textContent = `${filtered.length} match${filtered.length === 1 ? "" : "es"} available`;
  if (filtered.length === 0) {
    els.matchCards.innerHTML = "<p class='muted'>No matches found for this filter.</p>";
    return;
  }

  filtered.forEach((m) => {
    const teamA = teamLabel(m.team_a, "Team A");
    const teamB = teamLabel(m.team_b, "Team B");
    const unresolved = hasUnresolvedTeamName(m.team_a) || hasUnresolvedTeamName(m.team_b);
    const card = document.createElement("button");
    card.type = "button";
    card.className = `match-card ${state.selectedMatchId === m.match_id ? "active" : ""}`;
    card.innerHTML = `
      <div class='match-teams'>
        <strong>${teamA}</strong>
        <span>vs</span>
        <strong>${teamB}</strong>
      </div>
      <div class='match-meta'>IPL ${m.season_id}${m.match_date ? ` · ${m.match_date}` : ""} · Match ${m.match_number || m.season_match_number}${m.is_super_over_match ? " · Super Over" : ""}</div>
      <div class='match-meta'>${m.venue || "Venue unavailable"}${m.city ? `, ${m.city}` : ""}</div>
      <div class='match-id'>Match ID ${m.match_id} · ${m.innings_count} innings · ${m.deliveries} deliveries</div>
      <div class='match-open'>Open Match</div>
      ${unresolved ? "<div class='match-note'>Team names unavailable in source schema (ID-based).</div>" : ""}
    `;
    card.onclick = async () => {
      state.selectedMatchId = Number(m.match_id);
      state.selectedMatch = m;
      els.selectedMatchMeta.textContent = `${matchTitleFromMeta(m)} · IPL ${m.season_id} · Match ${m.match_number || m.season_match_number} · Match ID ${m.match_id}`;
      renderMatchCards();
      await loadInnings();
    };
    els.matchCards.appendChild(card);
  });
}

function updateTimeline() {
  els.timelineTrack.innerHTML = "";
  state.timeline.slice(-30).forEach((entry) => {
    const dot = document.createElement("div");
    dot.className = `timeline-dot ${entry.status}`;
    dot.textContent = `${entry.over}.${entry.ball}`;
    dot.title = `O${entry.over}.${entry.ball} · ${entry.status.toUpperCase()}${entry.actual ? ` · ${outcomeDisplay(entry.actual)}` : ""}`;
    dot.setAttribute("role", "button");
    dot.setAttribute("tabindex", "0");
    dot.onclick = () => {
      const idx = state.timeline.findIndex((x) => x.over === entry.over && x.ball === entry.ball);
      if (idx >= 0) state.selectedTimelineIndex = idx;
      renderBallByBallRows();
      setReplayTab("ball_by_ball");
    };
    dot.onkeydown = (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        dot.click();
      }
    };
    els.timelineTrack.appendChild(dot);
  });

  const revealed = state.timeline.filter((x) => x.status !== "pending").length;
  const total = Number(state.sessionMeta?.remaining_deliveries || 0) + revealed;
  els.progressValue.textContent = `${revealed}/${total} revealed`;
  els.progressFill.style.width = `${total > 0 ? Math.round((revealed / total) * 100) : 0}%`;
  els.previousBtn.disabled = revealed === 0;

  const prev = [...state.timeline].reverse().find((x) => x.status !== "pending");
  const last = state.timeline[state.timeline.length - 1] || null;
  els.prevBallValue.textContent = prev ? `Previous: ${prev.over}.${prev.ball} (${outcomeDisplay(prev.actual)})` : "Previous: -";
  els.nextBallValue.textContent =
    state.lastPrediction && state.uiState === UiState.PREDICTION_AVAILABLE
      ? `Next: ${state.lastPrediction.delivery.over_number}.${state.lastPrediction.delivery.ball_number}`
      : last && state.uiState === UiState.PREDICTION_REVEALED
        ? `Next: after ${last.over}.${last.ball}`
        : "Next: -";

  renderBallByBallRows();
}

function renderBallByBallRows() {
  if (!state.timeline.length) {
    els.ballByBallRows.innerHTML = "<tr><td colspan='6' class='muted'>No deliveries revealed yet.</td></tr>";
    return;
  }

  const rows = state.timeline
    .filter((entry) => entry.status !== "pending")
    .map((entry, index) => {
      const result = entry.status === "correct" ? "Correct" : "Incorrect";
      const active = state.selectedTimelineIndex === index ? "active" : "";
      return `<tr class='timeline-row ${active}' data-index='${index}'>
        <td>${entry.over}.${entry.ball}</td>
        <td><button class='inline-player' data-player='${entry.batter || ""}'>${entry.batter || "-"}</button></td>
        <td><button class='inline-player' data-player='${entry.bowler || ""}'>${entry.bowler || "-"}</button></td>
        <td>${outcomeDisplay(entry.predicted || "-")}</td>
        <td>${outcomeDisplay(entry.actual || "-")}</td>
        <td><span class='badge ${entry.status}'>${result}</span></td>
      </tr>`;
    })
    .join("");

  els.ballByBallRows.innerHTML = rows || "<tr><td colspan='6' class='muted'>No deliveries revealed yet.</td></tr>";
  els.ballByBallRows.querySelectorAll(".timeline-row").forEach((row) => {
    row.addEventListener("click", () => {
      state.selectedTimelineIndex = Number(row.getAttribute("data-index"));
      renderBallByBallRows();
    });
  });
  els.ballByBallRows.querySelectorAll(".inline-player").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      const name = button.getAttribute("data-player");
      if (name) setRoute({ view: "player", player: name });
    });
  });
}

function renderPrediction(pred) {
  const probs = pred.prediction.outcome_probabilities;
  const top = pred.prediction.predicted_top_outcome;
  const sample = Number(pred.prediction.evidence_sample_size || 0);

  els.predictedTop.textContent = outcomeDisplay(top).toUpperCase();
  els.predictedPct.textContent = toPct(Number(probs[top] || 0));

  els.probabilityBars.innerHTML = "";
  Object.entries(probs)
    .sort((a, b) => b[1] - a[1])
    .forEach(([label, value]) => {
      const row = document.createElement("div");
      row.className = `prob-row ${label === top ? "top" : ""}`;
      row.innerHTML = `<span>${outcomeDisplay(label)}</span><div class='bar'><span style='width:${Math.max(2, value * 100)}%'></span></div><strong>${toPct(value)}</strong>`;
      els.probabilityBars.appendChild(row);
    });

  els.whyBlock.innerHTML =
    `<strong>Why?</strong><br />` +
    `${outcomeDisplay(top)} was most likely because comparable historical deliveries most often ended with that result.<br />` +
    `<strong>${sample}</strong> comparable deliveries · <strong>${sampleLabel(sample)}</strong>`;

  els.evidenceBlock.innerHTML =
    `<div>Primary evidence source: <strong>${evidenceLabel(pred.prediction.chosen_evidence_level)}</strong></div>` +
    `<div>Reliability: <strong>${capitalize(pred.prediction.reliability)}</strong></div>` +
    `<div>Historical sample: <strong>${sample}</strong> deliveries</div>`;

  els.distributionBlock.innerHTML =
    `<div><strong>Outcome distribution</strong></div>` +
    Object.entries(probs)
      .map(([label, value]) => `<div>${outcomeDisplay(label)}: <strong>${toPct(Number(value || 0))}</strong></div>`)
      .join("");

  els.technicalEvidenceBlock.innerHTML =
    `<div>Evidence level key: <strong>${pred.prediction.chosen_evidence_level}</strong></div>` +
    `<div>Model version: <strong>${pred.prediction.model_version}</strong></div>` +
    `<div>Probability vector: <strong>${JSON.stringify(probs)}</strong></div>`;
}

function renderReplayHeaderMetrics() {
  const remaining = Number(state.sessionMeta?.current_state?.remaining_deliveries ?? 0);
  const revealed = Number(state.sessionMeta?.predictions_revealed ?? 0);
  const total = remaining + revealed;
  els.progressHeaderValue.textContent = total > 0 ? `${revealed}/${total} balls` : "-";

  const summary = state.sessionMeta?.summary || {};
  const revealedCount = Number(summary.predictions_revealed || 0);
  const correctCount = Number(summary.correct_predictions || 0);
  const acc = Number(summary.accuracy || 0);
  els.accuracyValue.textContent = revealedCount > 0 ? `${correctCount}/${revealedCount} · ${(acc * 100).toFixed(1)}%` : "-";

  return remaining;
}

function renderState(pred) {
  const d = pred.delivery;
  const s = pred.pre_delivery_state;
  const matchMeta = state.selectedMatch;
  const title = matchMeta ? matchTitleFromMeta(matchMeta) : `${teamLabel(s.team_batting, "Team A")} vs ${teamLabel(s.team_bowling, "Team B")}`;
  els.matchTitle.textContent = title;
  const matchNo = matchMeta?.season_match_number ? `Match ${matchMeta.season_match_number}` : `Match ID ${d.match_id}`;
  els.matchSubline.textContent = `${d.season_id} · ${matchNo} · Match ID ${d.match_id}`;
  els.teamsValue.textContent = title;
  els.inningsValue.textContent = String(d.innings);
  els.scoreValue.textContent = `${s.score}/${s.wickets}`;
  els.overBallValue.textContent = `${d.over_number}.${d.ball_number}`;
  const remaining = renderReplayHeaderMetrics();

  attachPlayerButton(els.batterValue, d.batter);
  attachPlayerButton(els.nonStrikerValue, d.non_striker);
  attachPlayerButton(els.bowlerValue, d.bowler);

  els.phaseValue.textContent = s.phase;
  els.stateScoreValue.textContent = String(s.score);
  els.stateWicketsValue.textContent = String(s.wickets);
  els.stateBallsValue.textContent = `${s.legal_balls} (${toOverNotation(s.legal_balls)} overs)`;
  els.remainingValue.textContent = String(remaining || "-");
}

function renderReveal(reveal) {
  const outcome = reveal.actual.actual_outcome;
  const correct = Boolean(reveal.comparison.is_correct);
  const verdict = correct ? "Correct" : "Incorrect";
  const predicted = reveal.comparison?.predicted_top_outcome;
  els.actualBlock.className = `actual-block ${correct ? "correct" : "incorrect"}`;
  els.actualBlock.innerHTML =
    `<div class='reveal-title'>Actual Outcome: <strong>${outcomeDisplay(outcome)}</strong></div>` +
    `<div>Prediction: <strong>${outcomeDisplay(predicted)}</strong></div>` +
    `<div>Result: <strong>${verdict}</strong></div>` +
    `<div>Total runs: ${reveal.actual.delivery_facts.total_runs} · Wicket: ${reveal.actual.delivery_facts.is_wicket === 1 ? "Yes" : "No"}</div>`;
}

function renderTable(items, fields) {
  if (!items || items.length === 0) return "<p class='muted'>No meaningful sample yet.</p>";
  const head = `<tr>${fields.map((f) => `<th>${f.label}</th>`).join("")}</tr>`;
  const body = items.map((row) => `<tr>${fields.map((f) => `<td>${row[f.key] ?? "-"}</td>`).join("")}</tr>`).join("");
  return `<table class='mini-table'>${head}${body}</table>`;
}

function renderTrendRows(items, metricKey, formatter) {
  if (!items || items.length === 0) return "<p class='muted'>No trend data available.</p>";
  const max = Math.max(...items.map((x) => Number(x[metricKey] || 0)), 0);
  return items
    .map((item) => {
      const value = Number(item[metricKey] || 0);
      const width = max > 0 ? Math.max(4, Math.round((value / max) * 100)) : 4;
      const label = item.season_id || item.phase;
      return `<div class='trend-row'><span>${label}</span><div class='bar'><span style='width:${width}%'></span></div><strong>${formatter(value, item)}</strong></div>`;
    })
    .join("");
}

function renderOutcome(outcomes) {
  const rows = Object.entries(outcomes || {});
  const total = rows.reduce((n, [, v]) => n + Number(v || 0), 0);
  if (!total) return "<p class='muted'>No outcome profile available.</p>";
  return rows
    .map(([label, count]) => {
      const pct = (Number(count) * 100) / total;
      return `<div class='trend-row'><span>${label}</span><div class='bar'><span style='width:${Math.max(3, Math.round(pct))}%'></span></div><strong>${count} (${pct.toFixed(1)}%)</strong></div>`;
    })
    .join("");
}

function renderMatchups(items, fields) {
  if (!items || items.length === 0) return "<p class='muted'>No meaningful matchup sample yet.</p>";
  const head = `<tr>${fields.map((f) => `<th>${f.label}</th>`).join("")}<th>Reliability</th></tr>`;
  const body = items
    .map((row) => {
      const sample = Number(row.sample_size || 0);
      const tier = row.evidence_tier || sampleTier(sample);
      return `<tr>${fields.map((f) => `<td>${row[f.key] ?? "-"}</td>`).join("")}<td><span class='badge ${tier}'>${sampleLabel(sample)}</span></td></tr>`;
    })
    .join("");
  return `<table class='mini-table'>${head}${body}</table>`;
}

function metricTile(label, value) {
  return `<div><span>${label}</span><strong>${value ?? "-"}</strong></div>`;
}

function topOutcomeFromDistribution(outcomes) {
  const items = Object.entries(outcomes || {}).map(([k, v]) => [k, Number(v || 0)]);
  items.sort((a, b) => b[1] - a[1]);
  return items.length && items[0][1] > 0 ? String(items[0][0]) : null;
}

function strongestBattingPhase(byPhase) {
  if (!byPhase || !byPhase.length) return null;
  const ranked = [...byPhase].sort((a, b) => Number(b.strike_rate || 0) - Number(a.strike_rate || 0));
  return ranked[0];
}

function strongestBowlingPhase(byPhase) {
  if (!byPhase || !byPhase.length) return null;
  const ranked = [...byPhase].sort((a, b) => Number(b.wickets || 0) - Number(a.wickets || 0));
  return ranked[0];
}

function peakSeason(battingBySeason, bowlingBySeason) {
  const battingPeak = battingBySeason && battingBySeason.length ? [...battingBySeason].sort((a, b) => Number(b.runs || 0) - Number(a.runs || 0))[0] : null;
  if (battingPeak && Number(battingPeak.runs || 0) > 0) return `Peak batting season: ${battingPeak.season_id} (${battingPeak.runs} runs)`;
  const bowlingPeak = bowlingBySeason && bowlingBySeason.length ? [...bowlingBySeason].sort((a, b) => Number(b.wickets || 0) - Number(a.wickets || 0))[0] : null;
  if (bowlingPeak && Number(bowlingPeak.wickets || 0) > 0) return `Peak bowling season: ${bowlingPeak.season_id} (${bowlingPeak.wickets} wickets)`;
  return null;
}

async function loadPlayer(name) {
  if (!name) {
    els.playerPanel.hidden = true;
    els.playerPrompt.hidden = false;
    return;
  }
  setStatus(`Loading player intelligence for ${name}...`);
  const suffix = state.sessionId ? `?session_id=${encodeURIComponent(state.sessionId)}` : "";
  const payload = await api.get(`/api/players/${encodeURIComponent(name)}${suffix}`);
  const header = payload.player;
  const hasBatting = Boolean(payload.sections?.has_batting);
  const hasBowling = Boolean(payload.sections?.has_bowling);
  const hasSeasonData = hasBatting || hasBowling;
  const hasPhaseData = hasBatting || hasBowling;
  state.playerCapabilities = { hasBatting, hasBowling };
  state.activePlayer = name;

  els.playerPrompt.hidden = true;
  els.playerPanel.hidden = false;
  els.playerName.textContent = header.name;
  const roleText = header.role_label ? ` · ${header.role_label}` : "";
  els.playerRole.textContent = `IPL Intelligence Profile${roleText}`;

  if (header.photo.kind === "local" && header.photo.url) {
    els.playerPhoto.hidden = false;
    els.playerPhoto.src = header.photo.url;
    els.playerPhoto.alt = `${header.name} player image`;
    els.playerAvatar.hidden = true;
  } else {
    els.playerPhoto.hidden = true;
    els.playerPhoto.src = "/assets/players/placeholder.svg";
    els.playerPhoto.alt = "";
    els.playerAvatar.hidden = false;
    els.playerAvatar.style.backgroundImage = "none";
    els.playerAvatar.style.setProperty("--avatar-seed", String(header.photo.seed || 140));
    els.playerAvatar.textContent = header.photo.initials || "?";
  }
  els.playerPhotoMeta.textContent = photoMetaLabel(header.photo);

  const ov = payload.overview;
  const battingPeak = strongestBattingPhase(payload.batting_intelligence?.by_phase || []);
  const bowlingPeak = strongestBowlingPhase(payload.bowling_intelligence?.by_phase || []);
  const topBattingOutcome = topOutcomeFromDistribution(payload.batting_intelligence?.outcome_distribution || {});
  const topBowlingOutcome = topOutcomeFromDistribution(payload.bowling_intelligence?.outcome_distribution || {});
  const peak = peakSeason(payload.batting_intelligence?.by_season || [], payload.bowling_intelligence?.by_season || []);

  els.playerCareerContext.textContent =
    Number(ov.batting.runs || 0) > 0
      ? `${metricDisplay(ov.batting.runs)} runs · ${metricDisplay(ov.batting.strike_rate)} SR over ${metricDisplay(ov.batting.balls)} balls`
      : Number(ov.bowling.wickets || 0) > 0
        ? `${metricDisplay(ov.bowling.wickets)} wickets · ${metricDisplay(ov.bowling.economy)} economy over ${metricDisplay(ov.bowling.legal_balls)} balls`
        : `${metricDisplay(ov.matches)} matches in dataset`;

  const insights = [
    battingPeak ? `Strongest batting phase: ${capitalize(battingPeak.phase)} (${metricDisplay(battingPeak.strike_rate)} SR)` : null,
    bowlingPeak ? `Strongest bowling phase: ${capitalize(bowlingPeak.phase)} (${metricDisplay(bowlingPeak.wickets)} wickets)` : null,
    peak,
    topBattingOutcome ? `Most common batting outcome: ${outcomeDisplay(topBattingOutcome)}` : topBowlingOutcome ? `Most common bowling outcome: ${outcomeDisplay(topBowlingOutcome)}` : null,
  ].filter(Boolean);

  els.playerOverview.innerHTML =
    `<div class='stats-grid'>
      ${metricTile("Matches", ov.matches)}
      ${metricTile("Batting runs", ov.batting.runs)}
      ${metricTile("Batting SR", ov.batting.strike_rate)}
      ${metricTile("Wickets", ov.bowling.wickets)}
      ${metricTile("Economy", ov.bowling.economy)}
      ${metricTile("Boundaries", ov.batting.boundaries)}
    </div>
    <div class='insight-list'>
      <h5>What stands out</h5>
      ${insights.length ? insights.map((item) => `<p>${item}</p>`).join("") : "<p>No strong trend signal yet for this player in the current dataset.</p>"}
    </div>`;

  els.battingTitle.hidden = !hasBatting;
  els.bowlingTitle.hidden = !hasBowling;

  els.playerBatting.innerHTML = hasBatting
    ? `<div class='stats-grid'>
         ${metricTile("Runs", ov.batting.runs)}
         ${metricTile("Balls", ov.batting.balls)}
         ${metricTile("Strike rate", ov.batting.strike_rate)}
         ${metricTile("Average", ov.batting.average)}
         ${metricTile("Fours", ov.batting.fours)}
         ${metricTile("Sixes", ov.batting.sixes)}
         ${metricTile("Dot ball %", ov.batting.dot_ball_rate)}
       </div>
       <h5>Batting outcome profile</h5>${renderOutcome(payload.batting_intelligence.outcome_distribution)}`
    : "";

  els.playerBowling.innerHTML = hasBowling
    ? `<div class='stats-grid'>
         ${metricTile("Wickets", ov.bowling.wickets)}
         ${metricTile("Runs conceded", ov.bowling.runs_conceded)}
         ${metricTile("Legal balls", ov.bowling.legal_balls)}
         ${metricTile("Economy", ov.bowling.economy)}
         ${metricTile("Strike rate", ov.bowling.strike_rate)}
         ${metricTile("Dot ball %", ov.bowling.dot_ball_rate)}
       </div>
       <h5>Bowling outcome profile</h5>${renderOutcome(payload.bowling_intelligence.outcome_distribution)}`
    : "";

  els.playerMatchups.innerHTML =
    `<p class='muted'>Direct matchups use player-versus-player records. Type matchups broaden to batting/bowling style evidence.</p>` +
    `<h5>Direct: Batter vs Bowler</h5>${renderMatchups(payload.matchups.batter_vs_bowler, [
      { key: "opponent", label: "Bowler" },
      { key: "sample_size", label: "Balls" },
      { key: "runs", label: "Runs" },
      { key: "wickets", label: "Wkts" },
      { key: "strike_rate", label: "SR" },
    ])}` +
    `<h5>Direct: Bowler vs Batter</h5>${renderMatchups(payload.matchups.bowler_vs_batter, [
      { key: "opponent", label: "Batter" },
      { key: "sample_size", label: "Balls" },
      { key: "runs_conceded", label: "Runs" },
      { key: "wickets", label: "Wkts" },
      { key: "economy", label: "Economy" },
    ])}` +
    `<h5>Type evidence: Batter vs Bowler Type</h5>${renderMatchups(payload.matchups.batter_vs_bowler_type, [
      { key: "opponent_type", label: "Bowler type" },
      { key: "sample_size", label: "Balls" },
      { key: "runs", label: "Runs" },
      { key: "wickets", label: "Wkts" },
      { key: "strike_rate", label: "SR" },
    ])}` +
    `<h5>Type evidence: Bowler vs Batter Type</h5>${renderMatchups(payload.matchups.bowler_vs_batter_type, [
      { key: "opponent_type", label: "Batter type" },
      { key: "sample_size", label: "Balls" },
      { key: "runs_conceded", label: "Runs" },
      { key: "wickets", label: "Wkts" },
      { key: "economy", label: "Economy" },
    ])}`;

  els.playerSeasons.innerHTML =
    `<h5>Batting trend by season</h5>${renderTrendRows(payload.batting_intelligence.by_season, "runs", (v) => `${v} runs`)}` +
    `${renderTable(payload.batting_intelligence.by_season, [
      { key: "season_id", label: "Season" },
      { key: "runs", label: "Runs" },
      { key: "balls", label: "Balls" },
      { key: "strike_rate", label: "SR" },
      { key: "dot_ball_rate", label: "Dot %" },
    ])}` +
    `<h5>Bowling trend by season</h5>${renderTrendRows(payload.bowling_intelligence.by_season, "wickets", (v) => `${v} wkts`)}` +
    `${renderTable(payload.bowling_intelligence.by_season, [
      { key: "season_id", label: "Season" },
      { key: "wickets", label: "Wkts" },
      { key: "runs_conceded", label: "Runs" },
      { key: "economy", label: "Economy" },
      { key: "strike_rate", label: "SR" },
    ])}`;

  els.playerPhases.innerHTML =
    `<h5>Batting by phase</h5>${renderTable(payload.batting_intelligence.by_phase, [
      { key: "phase", label: "Phase" },
      { key: "runs", label: "Runs" },
      { key: "balls", label: "Balls" },
      { key: "strike_rate", label: "SR" },
      { key: "dot_ball_rate", label: "Dot %" },
    ])}` +
    `<h5>Bowling by phase</h5>${renderTable(payload.bowling_intelligence.by_phase, [
      { key: "phase", label: "Phase" },
      { key: "wickets", label: "Wkts" },
      { key: "runs_conceded", label: "Runs" },
      { key: "economy", label: "Economy" },
      { key: "dot_ball_rate", label: "Dot %" },
    ])}`;

  const replay = payload.entry_points?.return_to_replay;
  if (replay) {
    const teams = state.selectedMatch ? matchTitleFromMeta(state.selectedMatch) : `Match ID ${replay.match_id}`;
    els.playerContextText.textContent = `From replay: ${teams} · ${replay.season_id} · Innings ${replay.innings}`;
    els.backToReplayBtn.textContent = `Return to Replay`;
    els.exploreReplayBtn.textContent = `Back to ${teams}`;
  } else {
    els.playerContextText.textContent = state.sessionMeta
      ? `Current replay: ${state.selectedMatch ? matchTitleFromMeta(state.selectedMatch) : `Match ID ${state.sessionMeta.match_id}`} · Innings ${state.sessionMeta.innings}`
      : "No active replay context.";
    els.backToReplayBtn.textContent = "Return to Time Machine";
    els.exploreReplayBtn.textContent = "Explore in Time Machine";
  }

  setPlayerTab("overview", hasBatting, hasBowling, hasSeasonData, hasPhaseData);
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
  const data = await api.get(`/api/players?query=${encodeURIComponent(q)}&limit=20`);
  els.playerSearchResults.innerHTML = "";
  if (!data.players || data.players.length === 0) {
    els.playerSearchHint.textContent = "No players matched. Try a different spelling.";
    return;
  }
  els.playerSearchHint.textContent = `${data.players.length} player${data.players.length === 1 ? "" : "s"} matched.`;
  data.players.forEach((item) => {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "search-result";
    const badge = item.photo.asset_type === "photo" && item.photo.is_verified_photo ? "photo" : item.photo.kind === "local" ? "illustration" : "avatar";
    row.innerHTML = `<span>${item.player_name}</span><small>${badge}</small>`;
    row.onclick = () => setRoute({ view: "player", player: item.player_name });
    els.playerSearchResults.appendChild(row);
  });
}

async function loadSeasons() {
  setStatus("Loading seasons...");
  const data = await api.get("/api/seasons");
  state.seasons = data.seasons;
  els.seasonSelect.innerHTML = "";
  state.seasons.forEach((s) => els.seasonSelect.appendChild(option(`Season ${s.season_id}`, s.season_id)));
  clearStatus();
}

async function loadMatches() {
  const seasonId = Number(els.seasonSelect.value);
  setStatus("Loading matches...");
  const data = await api.get(`/api/seasons/${seasonId}/matches`);
  state.matches = data.matches;
  state.hasTeamIdOnlyData = state.matches.some((m) => hasUnresolvedTeamName(m.team_a) || hasUnresolvedTeamName(m.team_b));
  applyTeamDataNotice();
  state.selectedMatchId = data.matches.length ? Number(data.matches[0].match_id) : null;
  state.selectedMatch = data.matches.length ? data.matches[0] : null;
  renderMatchCards();
  if (state.selectedMatchId !== null) {
    const first = data.matches[0];
    els.selectedMatchMeta.textContent = `${matchTitleFromMeta(first)} · IPL ${first.season_id} · Match ${first.match_number || first.season_match_number} · Match ID ${first.match_id}`;
  }
  clearStatus();
}

async function loadInnings() {
  if (state.selectedMatchId === null) {
    els.inningsSelect.innerHTML = "";
    els.startReplayBtn.disabled = true;
    return;
  }
  const data = await api.get(`/api/matches/${state.selectedMatchId}/innings`);
  state.innings = data.innings;
  els.inningsSelect.innerHTML = "";
  state.innings.forEach((item) => {
    els.inningsSelect.appendChild(
      option(`Innings ${item.innings}: ${teamLabel(item.team_batting, "Team A")} batting (${item.runs}/${item.wickets})`, item.innings),
    );
  });
  state.selectedInnings = state.innings.length ? state.innings[0] : null;
  els.startReplayBtn.disabled = state.innings.length === 0;
}

async function refreshSessionMeta() {
  if (!state.sessionId) return;
  state.sessionMeta = await api.get(`/api/replays/${state.sessionId}`);
}

async function startReplay() {
  if (state.selectedMatchId === null) return;
  const innings = Number(els.inningsSelect.value);
  state.selectedInnings = state.innings.find((x) => Number(x.innings) === innings) || null;
  setStatus("Creating replay session...");
  const created = await api.post("/api/replays", { match_id: state.selectedMatchId, innings });
  state.sessionId = created.session_id;
  state.sessionMeta = created;
  state.lastPrediction = null;
  state.timeline = [];
  state.selectedTimelineIndex = -1;
  els.replayPanel.hidden = false;
  if (state.selectedMatch) {
    els.matchTitle.textContent = matchTitleFromMeta(state.selectedMatch);
    els.matchSubline.textContent = `IPL ${state.selectedMatch.season_id} · Match ${state.selectedMatch.match_number || state.selectedMatch.season_match_number} · Match ID ${state.selectedMatch.match_id}`;
  }
  els.teamsValue.textContent = state.selectedMatch ? matchTitleFromMeta(state.selectedMatch) : "-";
  els.inningsValue.textContent = state.selectedInnings ? String(state.selectedInnings.innings) : "-";
  els.scoreValue.textContent = "0/0";
  els.overBallValue.textContent = "0.0";
  els.progressHeaderValue.textContent = "0/0 balls";
  els.accuracyValue.textContent = "-";
  els.whyBlock.innerHTML = "<strong>MATCHGENOME PREDICTS</strong><br />Press <strong>Predict Next Ball</strong> to lock the pre-reveal prediction for the next historical delivery.";
  els.predictedTop.textContent = "READY";
  els.predictedPct.textContent = "Before reveal";
  els.probabilityBars.innerHTML = "";
  els.actualBlock.className = "actual-block";
  els.actualBlock.textContent = "Reveal the ball to see actual outcome.";
  setReplayTab("prediction");
  setUiState(UiState.READY);
  updateTimeline();
  setStatus("Replay ready. Predict the next historical ball.");
}

async function predictNext() {
  if (!state.sessionId) return;
  setStatus("Calculating prediction...");
  const pred = await api.post(`/api/replays/${state.sessionId}/predict`);
  state.lastPrediction = pred;
  renderState(pred);
  renderPrediction(pred);
  if (!state.timeline.find((x) => x.over === pred.delivery.over_number && x.ball === pred.delivery.ball_number)) {
    state.timeline.push({
      over: pred.delivery.over_number,
      ball: pred.delivery.ball_number,
      batter: pred.delivery.batter,
      nonStriker: pred.delivery.non_striker,
      bowler: pred.delivery.bowler,
      predicted: pred.prediction.predicted_top_outcome,
      status: "pending",
      actual: null,
    });
  }
  await refreshSessionMeta();
  updateTimeline();
  setUiState(UiState.PREDICTION_AVAILABLE);
  setStatus("Prediction locked. Reveal to compare expectation vs reality.");
}

async function revealNext() {
  if (!state.sessionId) return;
  setStatus("Revealing actual delivery...");
  const reveal = await api.post(`/api/replays/${state.sessionId}/reveal`);
  renderReveal(reveal);
  const last = state.timeline[state.timeline.length - 1];
  if (last) {
    last.actual = reveal.actual.actual_outcome;
    last.status = reveal.comparison.is_correct ? "correct" : "incorrect";
  }
  await refreshSessionMeta();
  renderReplayHeaderMetrics();
  updateTimeline();
  setUiState(state.sessionMeta.status === "COMPLETED" ? UiState.COMPLETED : UiState.PREDICTION_REVEALED);
  setStatus(state.sessionMeta.status === "COMPLETED" ? "Innings completed." : "Reveal complete. Continue when ready.");
}

async function restartReplay() {
  if (!state.sessionId) return;
  const replay = await api.post(`/api/replays/${state.sessionId}/restart`);
  state.sessionMeta = replay;
  state.lastPrediction = null;
  state.timeline = [];
  state.selectedTimelineIndex = -1;
  els.actualBlock.className = "actual-block";
  els.actualBlock.textContent = "Reveal the ball to see actual outcome.";
  updateTimeline();
  setUiState(UiState.READY);
  setStatus("Replay restarted.");
}

function syncRoute() {
  const route = parseRoute();
  if (route.view === "home") {
    setView("home");
    return;
  }
  if (route.view === "methodology") {
    setView("methodology");
    return;
  }
  if (route.view === "player") {
    setView("player");
    if (!route.player) {
      els.playerPanel.hidden = true;
      els.playerPrompt.hidden = false;
      return;
    }
    loadPlayer(route.player).catch((err) => setStatus(err.message || "Failed to load player intelligence.", "error"));
    return;
  }
  setView("time_machine");
}

function attachEvents() {
  els.exploreMatchBtn.addEventListener("click", () => {
    setRoute({ view: "time_machine" });
    document.getElementById("timeMachineView")?.scrollIntoView({ behavior: "smooth", block: "start" });
    els.seasonSelect.focus();
  });
  els.goPlayersIntroBtn.addEventListener("click", () => setRoute({ view: "player", player: state.activePlayer || "" }));
  els.openFeaturedReplayBtn.addEventListener("click", () => {
    setRoute({ view: "time_machine" });
    if (state.matches.length > 0 && state.selectedMatchId === null) {
      state.selectedMatchId = Number(state.matches[0].match_id);
    }
  });

  els.seasonSelect.addEventListener("change", async () => {
    try {
      await loadMatches();
      await loadInnings();
    } catch (err) {
      setStatus(err.message || "Failed to load matches.", "error");
    }
  });
  els.matchSearchInput.addEventListener("input", renderMatchCards);
  els.inningsSelect.addEventListener("change", () => {
    state.selectedInnings = state.innings.find((x) => Number(x.innings) === Number(els.inningsSelect.value)) || null;
    els.startReplayBtn.disabled = !els.inningsSelect.value;
  });

  els.startReplayBtn.addEventListener("click", () => startReplay().catch((err) => setStatus(err.message || "Could not start replay.", "error")));
  els.predictBtn.addEventListener("click", () => predictNext().catch((err) => setStatus(err.message || "Prediction failed.", "error")));
  els.revealBtn.addEventListener("click", () => revealNext().catch((err) => setStatus(err.message || "Reveal failed.", "error")));
  els.nextBtn.addEventListener("click", () => predictNext().catch((err) => setStatus(err.message || "Next failed.", "error")));
  els.previousBtn.addEventListener("click", () => {
    const revealed = state.timeline.filter((x) => x.status !== "pending");
    if (!revealed.length) return;
    state.selectedTimelineIndex = Math.max(0, revealed.length - 1);
    setReplayTab("ball_by_ball");
    renderBallByBallRows();
  });
  els.restartBtn.addEventListener("click", () => restartReplay().catch((err) => setStatus(err.message || "Restart failed.", "error")));

  els.tabPredictionBtn.addEventListener("click", () => setReplayTab("prediction"));
  els.tabBallByBallBtn.addEventListener("click", () => setReplayTab("ball_by_ball"));
  els.tabEvidenceBtn.addEventListener("click", () => setReplayTab("evidence"));

  els.goHomeBtn.addEventListener("click", () => setRoute({ view: "home" }));
  els.goTimeMachineBtn.addEventListener("click", () => setRoute({ view: "time_machine" }));
  els.goPlayerIntelligenceBtn.addEventListener("click", () => setRoute({ view: "player", player: state.activePlayer || "" }));
  els.goMethodologyBtn.addEventListener("click", () => setRoute({ view: "methodology" }));
  els.backToReplayBtn.addEventListener("click", () => setRoute({ view: "time_machine" }));
  els.exploreReplayBtn.addEventListener("click", () => setRoute({ view: "time_machine" }));
  els.closePlayerBtn.addEventListener("click", () => setRoute({ view: "time_machine" }));

  const applyPlayerTab = (tab) => {
    const hasBatting = Boolean(state.playerCapabilities?.hasBatting);
    const hasBowling = Boolean(state.playerCapabilities?.hasBowling);
    setPlayerTab(tab, hasBatting, hasBowling, hasBatting || hasBowling, hasBatting || hasBowling);
  };
  els.playerTabOverviewBtn.addEventListener("click", () => applyPlayerTab("overview"));
  els.playerTabBattingBtn.addEventListener("click", () => applyPlayerTab("batting"));
  els.playerTabBowlingBtn.addEventListener("click", () => applyPlayerTab("bowling"));
  els.playerTabMatchupsBtn.addEventListener("click", () => applyPlayerTab("matchups"));
  els.playerTabSeasonsBtn.addEventListener("click", () => applyPlayerTab("seasons"));
  els.playerTabPhasesBtn.addEventListener("click", () => applyPlayerTab("phases"));

  els.playerSearchBtn.addEventListener("click", () => searchPlayers().catch((err) => setStatus(err.message || "Player search failed.", "error")));
  els.playerSearchInput.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    searchPlayers().catch((err) => setStatus(err.message || "Player search failed.", "error"));
  });

  window.addEventListener("hashchange", syncRoute);
}

async function bootstrap() {
  try {
    await loadSeasons();
    await loadMatches();
    await loadInnings();
    attachEvents();
    setReplayTab("prediction");
    setUiState(UiState.SELECT_MATCH);
    setStatus("Open Time Machine to predict before reveal, then compare with the actual historical ball.");
    syncRoute();
  } catch (err) {
    setStatus(err.message || "Unable to initialize app.", "error");
  }
}

bootstrap();

