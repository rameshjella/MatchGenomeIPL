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
  view: "home",
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
};

const els = {
  homeView: document.getElementById("homeView"),
  askView: document.getElementById("askView"),
  timeMachineView: document.getElementById("timeMachineView"),
  playerView: document.getElementById("playerView"),
  methodologyView: document.getElementById("methodologyView"),
  statusBanner: document.getElementById("statusBanner"),

  goHomeBtn: document.getElementById("goHomeBtn"),
  goTimeMachineBtn: document.getElementById("goTimeMachineBtn"),
  goAskBtn: document.getElementById("goAskBtn"),
  goPlayerIntelligenceBtn: document.getElementById("goPlayerIntelligenceBtn"),
  goMethodologyBtn: document.getElementById("goMethodologyBtn"),

  exploreMatchBtn: document.getElementById("exploreMatchBtn"),
  openAskBtn: document.getElementById("openAskBtn"),
  goPlayersIntroBtn: document.getElementById("goPlayersIntroBtn"),

  askInput: document.getElementById("askInput"),
  askSubmitBtn: document.getElementById("askSubmitBtn"),
  askExamples: document.getElementById("askExamples"),
  askResults: document.getElementById("askResults"),

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
  predictedTop: document.getElementById("predictedTop"),
  predictedPct: document.getElementById("predictedPct"),
  probabilityBars: document.getElementById("probabilityBars"),
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

  evidenceBlock: document.getElementById("evidenceBlock"),
  distributionBlock: document.getElementById("distributionBlock"),
  technicalEvidenceBlock: document.getElementById("technicalEvidenceBlock"),

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

function capitalize(value) {
  if (!value) return "-";
  return `${value}`.charAt(0).toUpperCase() + `${value}`.slice(1);
}

function setView(view) {
  state.view = view;
  const map = {
    home: els.homeView,
    ask: els.askView,
    time_machine: els.timeMachineView,
    player: els.playerView,
    methodology: els.methodologyView,
  };
  Object.entries(map).forEach(([name, node]) => {
    node.hidden = name !== view;
  });

  const nav = [
    [els.goHomeBtn, view === "home"],
    [els.goTimeMachineBtn, view === "time_machine"],
    [els.goAskBtn, view === "ask"],
    [els.goPlayerIntelligenceBtn, view === "player"],
    [els.goMethodologyBtn, view === "methodology"],
  ];
  nav.forEach(([button, active]) => {
    button.classList.toggle("primary", active);
    button.setAttribute("aria-current", active ? "page" : "false");
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
    panel.hidden = !active;
  });
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
  const query = (els.matchSearchInput.value || "").trim().toLowerCase();
  const teamFilter = (els.teamFilterSelect.value || "").trim();

  const filtered = state.matches.filter((m) => {
    const teamA = teamLabel(m.team_a, "Team A");
    const teamB = teamLabel(m.team_b, "Team B");
    if (teamFilter && teamA !== teamFilter && teamB !== teamFilter) return false;
    if (!query) return true;
    const text = [
      teamA,
      teamB,
      String(m.match_id),
      String(m.match_date || ""),
      String(m.venue || ""),
      String(m.city || ""),
      String(m.match_number || m.season_match_number || ""),
    ]
      .join(" ")
      .toLowerCase();
    return text.includes(query);
  });

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
    const card = document.createElement("button");
    card.type = "button";
    card.className = `match-card ${state.selectedMatchId === Number(m.match_id) ? "active" : ""}`;
    card.innerHTML = `
      <div class='match-teams'><strong>${teamA}</strong><span>vs</span><strong>${teamB}</strong></div>
      <div class='muted'>IPL ${m.season_id} · Match ${m.match_number || m.season_match_number || "-"}</div>
      <div class='muted'>${m.match_date || "Date unavailable"} · ${m.venue || "Venue unavailable"}${m.city ? `, ${m.city}` : ""}</div>
      <div class='muted'>Match ID ${m.match_id}</div>
      ${unresolved ? "<div class='muted'>Unresolved team identity for this record.</div>" : ""}
      <div>Replay this match</div>
    `;
    card.onclick = async () => {
      state.selectedMatchId = Number(m.match_id);
      state.selectedMatch = m;
      const readable = `${matchTitleFromMeta(m)} · IPL ${m.season_id} · Match ${m.match_number || m.season_match_number || "-"} · Match ID ${m.match_id}`;
      els.selectedMatchMeta.textContent = readable;
      renderMatchCards();
      await loadInnings();
    };
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
      return `<div class='prob-row ${topClass}'>
        <span>${outcomeDisplay(label)}</span>
        <div class='bar'><span style='width:${Math.max(2, Math.round(Number(value) * 100))}%'></span></div>
        <strong>${toPct(value)}</strong>
      </div>`;
    })
    .join("");

  const evidence = pred.prediction.evidence || {};
  const lookedAt = (evidence.looked_at || []).map((x) => `<li>${x}</li>`).join("");
  const comparable = Number(evidence.comparable_deliveries || 0);
  const matchup = Number(evidence.matchup_deliveries || 0);
  const reliability = capitalize(pred.prediction.reliability || "unknown");

  els.whyBlock.innerHTML = `
    <h5>Why did MatchGenome predict ${outcomeDisplay(top)}?</h5>
    <p>Prediction combines batter history, bowler history, matchup context, innings pressure, and similar historical states available before this ball.</p>
    <p><strong>Evidence:</strong> ${comparable} comparable deliveries · ${matchup} direct matchup deliveries</p>
    <p><strong>Reliability:</strong> ${reliability}</p>
    ${lookedAt ? `<details><summary>What did it look at?</summary><ul>${lookedAt}</ul></details>` : ""}
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
  `;

  els.distributionBlock.innerHTML = `<h5>Distribution</h5>${entries
    .map(([label, value]) => `<p>${outcomeDisplay(label)}: <strong>${toPct(value)}</strong></p>`)
    .join("")}`;

  els.technicalEvidenceBlock.innerHTML = `
    <p><strong>Model version:</strong> ${pred.prediction.model_version || "-"}</p>
    <p><strong>Chosen evidence level:</strong> ${pred.prediction.chosen_evidence_level || "-"}</p>
    <p><strong>Raw probability vector:</strong> ${JSON.stringify(probs)}</p>
  `;
}

function renderState(pred) {
  const d = pred.delivery;
  const s = pred.pre_delivery_state;
  const selected = state.selectedMatch;
  const title = selected ? matchTitleFromMeta(selected) : `${teamLabel(s.team_batting, "Team A")} vs ${teamLabel(s.team_bowling, "Team B")}`;
  const matchNumber = selected ? selected.match_number || selected.season_match_number : null;

  els.matchTitle.textContent = title;
  els.matchSubline.textContent = `${d.season_id} · Match ${matchNumber || "-"} · Match ID ${d.match_id}`;
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

  renderReplayHeaderMetrics();
}

function renderReveal(reveal) {
  const actual = reveal.actual.actual_outcome;
  const predicted = reveal.comparison.predicted_top_outcome;
  const isCorrect = Boolean(reveal.comparison.is_correct);
  const verdict = isCorrect ? "Correct" : "Incorrect";

  els.actualBlock.className = `actual-block ${isCorrect ? "correct" : "incorrect"}`;
  els.actualBlock.innerHTML = `
    <h5>The Ball Happened</h5>
    <p><strong>${outcomeDisplay(actual).toUpperCase()}</strong></p>
    <p>MatchGenome predicted <strong>${outcomeDisplay(predicted)}</strong>.</p>
    <p><strong>${verdict}</strong></p>
    <p>Total runs: ${reveal.actual.delivery_facts.total_runs} · Wicket: ${reveal.actual.delivery_facts.is_wicket === 1 ? "Yes" : "No"}</p>
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
  if (photo.kind === "local" && photo.url) {
    els.playerPhoto.hidden = false;
    els.playerPhoto.src = photo.url;
    els.playerPhoto.alt = `${payload.player.name} player image`;
    els.playerAvatar.hidden = true;
    if (photo.asset_type === "photo" && photo.is_verified_photo) {
      els.playerPhotoMeta.textContent = "Real verified local player photo.";
    } else {
      els.playerPhotoMeta.textContent = "Local player illustration (not a verified photograph).";
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

  els.playerOverview.innerHTML = `
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
      <div class='panel-block'><h5>Career snapshot</h5>
      ${renderTable([bat], [
        { key: "runs", label: "Runs" },
        { key: "balls", label: "Balls" },
        { key: "strike_rate", label: "SR" },
        { key: "average", label: "Average" },
        { key: "sixes", label: "Sixes" },
      ])}</div>
      <div class='panel-block'><h5>Outcome profile</h5>${renderOutcomeBars(payload.batting_intelligence?.outcome_distribution)}</div>
    `
    : "<p class='muted'>No batting sample for this player.</p>";

  els.playerBowling.innerHTML = hasBowling
    ? `
      <div class='panel-block'><h5>Career snapshot</h5>
      ${renderTable([bowl], [
        { key: "wickets", label: "Wkts" },
        { key: "runs_conceded", label: "Runs" },
        { key: "legal_balls", label: "Balls" },
        { key: "economy", label: "Economy" },
        { key: "strike_rate", label: "Strike Rate" },
      ])}</div>
      <div class='panel-block'><h5>Outcome profile</h5>${renderOutcomeBars(payload.bowling_intelligence?.outcome_distribution)}</div>
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
  if (value === null || value === undefined) return "No answer available.";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return `<p><strong>${value}</strong></p>`;
  }
  if (Array.isArray(value)) {
    return `<ul>${value
      .slice(0, 8)
      .map((item) => `<li>${typeof item === "object" ? JSON.stringify(item) : String(item)}</li>`)
      .join("")}</ul>`;
  }
  return `<pre>${JSON.stringify(value, null, 2)}</pre>`;
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
      return `<article class='ask-result-card'>
        <p class='muted'>Question</p>
        <p><strong>${item.question}</strong></p>
        <p class='muted'>Answer</p>
        ${formatAskValue(item.result?.value)}
        <p class='muted'>Evidence</p>
        <p>${item.result?.label || "Answer from local IPL data."}</p>
        <p class='muted'>${evidence.source || "MatchGenome IPL database"} · ${evidence.scope || ""}</p>
        ${player ? `<div class='row-actions'><button type='button' class='ask-player-link' data-player='${player}'>Open Player Intelligence</button></div>` : ""}
        <details><summary>Query interpretation</summary><pre>${JSON.stringify(item.query_plan || {}, null, 2)}</pre></details>
      </article>`;
    })
    .join("");

  els.askResults.querySelectorAll(".ask-player-link").forEach((button) => {
    button.addEventListener("click", () => {
      const player = button.getAttribute("data-player");
      if (!player) return;
      setRoute({ view: "player", player });
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
  const list = payload.players || [];

  if (!list.length) {
    els.playerSearchResults.innerHTML = "";
    els.playerSearchHint.textContent = "No matching players found.";
    return;
  }

  els.playerSearchHint.textContent = `${list.length} player${list.length === 1 ? "" : "s"} matched.`;
  els.playerSearchResults.innerHTML = "";
  list.forEach((item) => {
    const photo = item.photo || {};
    const kind = photo.asset_type === "photo" && photo.is_verified_photo ? "photo" : photo.kind === "local" ? "illustration" : "avatar";
    const row = document.createElement("button");
    row.type = "button";
    row.className = "search-result";
    row.innerHTML = `<span>${item.player_name}</span><small class='muted'>${kind}</small>`;
    row.onclick = () => setRoute({ view: "player", player: item.player_name });
    els.playerSearchResults.appendChild(row);
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
    els.selectedMatchMeta.textContent = `${matchTitleFromMeta(first)} · IPL ${first.season_id} · Match ${first.match_number || first.season_match_number || "-"} · Match ID ${first.match_id}`;
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

  els.replayPanel.hidden = false;
  els.actualBlock.className = "actual-block";
  els.actualBlock.textContent = "Reveal the ball to see actual outcome.";
  els.predictedTop.textContent = "READY";
  els.predictedPct.textContent = "Before reveal";
  els.probabilityBars.innerHTML = "";
  els.whyBlock.textContent = "Generate a prediction to see the evidence narrative.";
  els.changeBlock.className = "explain-block muted";
  els.changeBlock.textContent = "Prediction change diagnostics will appear after the next ball.";

  setReplayTab("prediction");
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
  if (route.view === "player") {
    setView("player");
    if (route.player) {
      loadPlayer(route.player).catch((err) => setStatus(err.message || "Failed to load player.", "error"));
    } else {
      els.playerPanel.hidden = true;
      els.playerPrompt.hidden = false;
    }
    return;
  }

  if (route.view === "ask") {
    setView("ask");
    return;
  }

  if (route.view === "time_machine") {
    setView("time_machine");
    return;
  }

  if (route.view === "methodology") {
    setView("methodology");
    return;
  }

  setView("home");
}

function attachEvents() {
  els.goHomeBtn.addEventListener("click", () => setRoute({ view: "home" }));
  els.goTimeMachineBtn.addEventListener("click", () => setRoute({ view: "time_machine" }));
  els.goAskBtn.addEventListener("click", () => setRoute({ view: "ask" }));
  els.goPlayerIntelligenceBtn.addEventListener("click", () => setRoute({ view: "player", player: state.activePlayer || "" }));
  els.goMethodologyBtn.addEventListener("click", () => setRoute({ view: "methodology" }));

  els.exploreMatchBtn.addEventListener("click", () => setRoute({ view: "time_machine" }));
  els.openAskBtn.addEventListener("click", () => setRoute({ view: "ask" }));
  els.goPlayersIntroBtn.addEventListener("click", () => setRoute({ view: "player", player: state.activePlayer || "" }));

  els.askSubmitBtn.addEventListener("click", () => runAsk().catch((err) => setStatus(err.message || "Ask failed.", "error")));
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

  els.seasonSelect.addEventListener("change", async () => {
    try {
      await loadMatches();
      await loadInnings();
    } catch (err) {
      setStatus(err.message || "Failed to load season matches.", "error");
    }
  });
  els.matchSearchInput.addEventListener("input", renderMatchCards);
  els.teamFilterSelect.addEventListener("change", renderMatchCards);
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

  els.tabPredictionBtn.addEventListener("click", () => setReplayTab("prediction"));
  els.tabBallByBallBtn.addEventListener("click", () => setReplayTab("ball_by_ball"));
  els.tabEvidenceBtn.addEventListener("click", () => setReplayTab("evidence"));

  els.backToReplayBtn.addEventListener("click", () => setRoute({ view: "time_machine" }));
  els.exploreReplayBtn.addEventListener("click", () => setRoute({ view: "time_machine" }));
  els.closePlayerBtn.addEventListener("click", () => setRoute({ view: "time_machine" }));

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
    setStatus("Loading IPL intelligence workspace...");
    await loadSeasons();
    await loadMatches();
    await loadInnings();
    attachEvents();
    setReplayTab("prediction");
    setPlayerTab("overview");
    setUiState(UiState.SELECT_MATCH);
    syncRoute();
    clearStatus();
  } catch (err) {
    setStatus(err.message || "Unable to initialize the product.", "error");
  }
}

bootstrap();

