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
  sessionId: null,
  sessionMeta: null,
  lastPrediction: null,
  lastReveal: null,
  timeline: [],
};

const els = {
  seasonSelect: document.getElementById("seasonSelect"),
  matchSelect: document.getElementById("matchSelect"),
  inningsSelect: document.getElementById("inningsSelect"),
  startReplayBtn: document.getElementById("startReplayBtn"),
  statusBanner: document.getElementById("statusBanner"),
  replayPanel: document.getElementById("replayPanel"),
  matchTitle: document.getElementById("matchTitle"),
  teamsValue: document.getElementById("teamsValue"),
  inningsValue: document.getElementById("inningsValue"),
  scoreValue: document.getElementById("scoreValue"),
  overBallValue: document.getElementById("overBallValue"),
  timelineTrack: document.getElementById("timelineTrack"),
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
  predictBtn: document.getElementById("predictBtn"),
  revealBtn: document.getElementById("revealBtn"),
  nextBtn: document.getElementById("nextBtn"),
  restartBtn: document.getElementById("restartBtn"),
  actualBlock: document.getElementById("actualBlock"),
  playerPrompt: document.getElementById("playerPrompt"),
  playerPanel: document.getElementById("playerPanel"),
  playerAvatar: document.getElementById("playerAvatar"),
  playerName: document.getElementById("playerName"),
  playerRole: document.getElementById("playerRole"),
  playerOverview: document.getElementById("playerOverview"),
  playerBatting: document.getElementById("playerBatting"),
  playerBowling: document.getElementById("playerBowling"),
  playerMatchups: document.getElementById("playerMatchups"),
  closePlayerBtn: document.getElementById("closePlayerBtn"),
};

function setStatus(message, kind = "info") {
  els.statusBanner.hidden = false;
  els.statusBanner.textContent = message;
  els.statusBanner.style.borderColor = kind === "error" ? "#ef4444" : "#2a3250";
}

function clearStatus() {
  els.statusBanner.hidden = true;
}

function setUiState(nextState) {
  state.uiState = nextState;
  const canPredict = nextState === UiState.READY || nextState === UiState.PREDICTION_REVEALED;
  const canReveal = nextState === UiState.PREDICTION_AVAILABLE;
  els.predictBtn.disabled = !canPredict;
  els.revealBtn.disabled = !canReveal;
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
    global: "Global IPL history",
    batter_bowler: "Batter vs Bowler",
    batter_bowler_type: "Batter vs Bowler type",
    bowler_batter_type: "Bowler vs Batter type",
    batter_type_bowler_type: "Batter type vs Bowler type",
  };
  return map[raw] || raw;
}

function updateTimeline() {
  els.timelineTrack.innerHTML = "";
  state.timeline.slice(-30).forEach((entry) => {
    const dot = document.createElement("div");
    dot.className = `timeline-dot ${entry.status}`;
    dot.title = `O${entry.over}.${entry.ball} ${entry.status}${entry.actual ? ` ${entry.actual}` : ""}`;
    dot.textContent = `${entry.over}.${entry.ball}`;
    els.timelineTrack.appendChild(dot);
  });

  const revealed = state.timeline.filter((x) => x.status !== "pending").length;
  const total = Number(state.sessionMeta?.remaining_deliveries || 0) + revealed;
  els.progressValue.textContent = `${revealed}/${total} revealed`;
  const progress = total > 0 ? Math.round((revealed / total) * 100) : 0;
  els.progressFill.style.width = `${progress}%`;

  const prev = [...state.timeline].reverse().find((x) => x.status !== "pending");
  const last = state.timeline[state.timeline.length - 1] || null;
  els.prevBallValue.textContent = prev ? `Previous: ${prev.over}.${prev.ball} (${prev.actual})` : "Previous: -";
  els.nextBallValue.textContent =
    state.lastPrediction && state.uiState === UiState.PREDICTION_AVAILABLE
      ? `Next: ${state.lastPrediction.delivery.over_number}.${state.lastPrediction.delivery.ball_number}`
      : last && state.uiState === UiState.PREDICTION_REVEALED
        ? `Next: after ${last.over}.${last.ball}`
        : "Next: -";
}

function attachPlayerButton(button, name) {
  button.textContent = name || "-";
  button.disabled = !name;
  button.onclick = () => {
    if (!name) return;
    window.location.hash = `player=${encodeURIComponent(name)}`;
  };
}

function renderPrediction(pred) {
  const probs = pred.prediction.outcome_probabilities;
  const top = pred.prediction.predicted_top_outcome;
  const topValue = probs[top] || 0;

  els.predictedTop.textContent = top === "wicket" ? "Wicket" : `${top} run${top === "1" ? "" : "s"}`;
  els.predictedPct.textContent = toPct(topValue);

  const rows = Object.entries(probs)
    .sort((a, b) => b[1] - a[1])
    .map(([label, value]) => {
      const row = document.createElement("div");
      row.className = `prob-row ${label === top ? "top" : ""}`;
      row.innerHTML = `
        <span>${label}</span>
        <div class="bar"><span style="width:${Math.max(2, value * 100)}%"></span></div>
        <strong>${toPct(value)}</strong>
      `;
      return row;
    });

  els.probabilityBars.innerHTML = "";
  rows.forEach((row) => els.probabilityBars.appendChild(row));

  els.whyBlock.innerHTML = `Most similar evidence came from <strong>${evidenceLabel(pred.prediction.chosen_evidence_level)}</strong>.`;
  els.evidenceBlock.innerHTML = `
    <div>Reliability: <strong>${pred.prediction.reliability}</strong></div>
    <div>Evidence: <strong>${evidenceLabel(pred.prediction.chosen_evidence_level)}</strong></div>
    <div>Sample size: <strong>${pred.prediction.evidence_sample_size}</strong> deliveries</div>
    <div>Model: <strong>${pred.prediction.model_version}</strong></div>
  `;
}

function renderState(pred) {
  const d = pred.delivery;
  const s = pred.pre_delivery_state;

  els.matchTitle.textContent = `Season ${d.season_id} - Match ${d.match_id}`;
  els.teamsValue.textContent = `${s.team_batting} vs ${s.team_bowling}`;
  els.inningsValue.textContent = `${d.innings}`;
  els.scoreValue.textContent = `${s.score}/${s.wickets}`;
  els.overBallValue.textContent = `${d.over_number}.${d.ball_number}`;

  attachPlayerButton(els.batterValue, d.batter);
  attachPlayerButton(els.nonStrikerValue, d.non_striker);
  attachPlayerButton(els.bowlerValue, d.bowler);

  els.phaseValue.textContent = s.phase;
  els.stateScoreValue.textContent = `${s.score}`;
  els.stateWicketsValue.textContent = `${s.wickets}`;
  els.stateBallsValue.textContent = `${s.legal_balls}`;
  els.remainingValue.textContent = String(state.sessionMeta?.current_state?.remaining_deliveries || "-");
}

function renderReveal(reveal) {
  const outcome = reveal.actual.actual_outcome;
  const facts = reveal.actual.delivery_facts;
  const isCorrect = reveal.comparison.is_correct;
  els.actualBlock.className = `actual-block ${isCorrect ? "correct" : "incorrect"}`;
  els.actualBlock.innerHTML = `
    <div><strong>Actual outcome:</strong> ${outcome}</div>
    <div><strong>Total runs:</strong> ${facts.total_runs}</div>
    <div><strong>Wicket:</strong> ${facts.is_wicket === 1 ? "Yes" : "No"}</div>
    <div><strong>Prediction:</strong> ${isCorrect ? "Correct" : "Incorrect"}</div>
  `;
}

function renderTable(items, fields) {
  if (!items || items.length === 0) return "<p class='muted'>No meaningful sample yet.</p>";
  const header = `<tr>${fields.map((f) => `<th>${f.label}</th>`).join("")}</tr>`;
  const body = items
    .map((row) => `<tr>${fields.map((f) => `<td>${row[f.key] ?? "-"}</td>`).join("")}</tr>`)
    .join("");
  return `<table class='mini-table'>${header}${body}</table>`;
}

async function loadPlayer(name) {
  if (!name) {
    els.playerPanel.hidden = true;
    els.playerPrompt.hidden = false;
    return;
  }

  setStatus(`Loading player intelligence for ${name}...`);
  const player = await api.get(`/api/players/${encodeURIComponent(name)}`);
  const header = player.player;
  const photo = header.photo;

  els.playerPrompt.hidden = true;
  els.playerPanel.hidden = false;
  els.playerName.textContent = header.name;
  els.playerRole.textContent = `Role: ${header.role}`;

  if (photo.kind === "local") {
    els.playerAvatar.style.backgroundImage = `url('${photo.url}')`;
    els.playerAvatar.textContent = "";
  } else {
    els.playerAvatar.style.backgroundImage = "none";
    els.playerAvatar.textContent = photo.initials || "?";
  }

  const ov = player.overview;
  els.playerOverview.innerHTML = `
    <div><span>Matches</span><strong>${ov.matches}</strong></div>
    <div><span>Batting runs</span><strong>${ov.batting.runs}</strong></div>
    <div><span>Batting SR</span><strong>${ov.batting.strike_rate ?? "-"}</strong></div>
    <div><span>Batting avg</span><strong>${ov.batting.average ?? "-"}</strong></div>
    <div><span>Bowling wickets</span><strong>${ov.bowling.wickets}</strong></div>
    <div><span>Economy</span><strong>${ov.bowling.economy ?? "-"}</strong></div>
  `;

  els.playerBatting.innerHTML =
    `<p class='muted'>Outcome distribution: ${JSON.stringify(player.batting_intelligence.outcome_distribution)}</p>` +
    renderTable(player.batting_intelligence.by_season, [
      { key: "season_id", label: "Season" },
      { key: "runs", label: "Runs" },
      { key: "balls", label: "Balls" },
      { key: "strike_rate", label: "SR" },
      { key: "boundaries", label: "Boundaries" },
    ]);

  els.playerBowling.innerHTML =
    `<p class='muted'>Outcome distribution: ${JSON.stringify(player.bowling_intelligence.outcome_distribution)}</p>` +
    renderTable(player.bowling_intelligence.by_season, [
      { key: "season_id", label: "Season" },
      { key: "runs_conceded", label: "Runs Conceded" },
      { key: "legal_balls", label: "Legal Balls" },
      { key: "wickets", label: "Wickets" },
      { key: "economy", label: "Economy" },
    ]);

  els.playerMatchups.innerHTML =
    `<h5>Batter vs Bowler</h5>` +
    renderTable(player.matchups.batter_vs_bowler, [
      { key: "opponent", label: "Opponent" },
      { key: "sample_size", label: "Sample" },
      { key: "runs", label: "Runs" },
      { key: "wickets", label: "Wkts" },
      { key: "strike_rate", label: "SR" },
    ]) +
    `<h5>Bowler vs Batter</h5>` +
    renderTable(player.matchups.bowler_vs_batter, [
      { key: "opponent", label: "Opponent" },
      { key: "sample_size", label: "Sample" },
      { key: "runs_conceded", label: "Runs" },
      { key: "wickets", label: "Wkts" },
      { key: "economy", label: "Economy" },
    ]);
  clearStatus();
}

function syncRoute() {
  const hash = window.location.hash.replace(/^#/, "");
  if (!hash.startsWith("player=")) {
    els.playerPanel.hidden = true;
    els.playerPrompt.hidden = false;
    return;
  }
  const name = decodeURIComponent(hash.slice("player=".length));
  loadPlayer(name).catch((err) => setStatus(err.message || "Failed to load player intelligence.", "error"));
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
  els.matchSelect.innerHTML = "";
  state.matches.forEach((m) => els.matchSelect.appendChild(option(`Match ${m.match_id}`, m.match_id)));
  clearStatus();
}

async function loadInnings() {
  const matchId = Number(els.matchSelect.value);
  setStatus("Loading innings...");
  const data = await api.get(`/api/matches/${matchId}/innings`);
  state.innings = data.innings;
  els.inningsSelect.innerHTML = "";
  state.innings.forEach((item) => {
    const label = `Innings ${item.innings} - ${item.team_batting} vs ${item.team_bowling}`;
    els.inningsSelect.appendChild(option(label, item.innings));
  });
  clearStatus();
}

async function refreshSessionMeta() {
  if (!state.sessionId) return;
  state.sessionMeta = await api.get(`/api/replays/${state.sessionId}`);
}

async function startReplay() {
  const matchId = Number(els.matchSelect.value);
  const innings = Number(els.inningsSelect.value);
  setStatus("Creating replay session...");
  const created = await api.post("/api/replays", { match_id: matchId, innings });
  state.sessionId = created.session_id;
  state.sessionMeta = created;
  state.lastPrediction = null;
  state.lastReveal = null;
  state.timeline = [];
  els.replayPanel.hidden = false;
  els.actualBlock.className = "actual-block";
  els.actualBlock.textContent = "Reveal the ball to see actual outcome.";
  updateTimeline();
  setUiState(UiState.READY);
  setStatus("Replay ready. You are standing before the next historical ball.");
}

async function predictNext() {
  if (!state.sessionId) return;
  setStatus("Calculating prediction...");
  const pred = await api.post(`/api/replays/${state.sessionId}/predict`);
  state.lastPrediction = pred;
  state.lastReveal = null;
  renderState(pred);
  renderPrediction(pred);

  const dot = {
    over: pred.delivery.over_number,
    ball: pred.delivery.ball_number,
    status: "pending",
    actual: null,
  };
  if (!state.timeline.find((x) => x.over === dot.over && x.ball === dot.ball)) {
    state.timeline.push(dot);
  }
  await refreshSessionMeta();
  updateTimeline();

  setUiState(UiState.PREDICTION_AVAILABLE);
  setStatus("Prediction locked. Reveal to compare with reality.");
}

async function revealNext() {
  if (!state.sessionId) return;
  setStatus("Revealing actual delivery...");
  const reveal = await api.post(`/api/replays/${state.sessionId}/reveal`);
  state.lastReveal = reveal;
  renderReveal(reveal);

  const last = state.timeline[state.timeline.length - 1];
  if (last) {
    last.actual = reveal.actual.actual_outcome;
    last.status = reveal.comparison.is_correct ? "correct" : "incorrect";
  }

  await refreshSessionMeta();
  updateTimeline();

  if (state.sessionMeta.status === "COMPLETED") {
    setUiState(UiState.COMPLETED);
    setStatus("Innings completed. Restart to replay again.");
  } else {
    setUiState(UiState.PREDICTION_REVEALED);
    clearStatus();
  }
}

async function restartReplay() {
  if (!state.sessionId) return;
  setStatus("Restarting replay...");
  const replay = await api.post(`/api/replays/${state.sessionId}/restart`);
  state.sessionMeta = replay;
  state.lastPrediction = null;
  state.lastReveal = null;
  state.timeline = [];
  els.actualBlock.className = "actual-block";
  els.actualBlock.textContent = "Reveal the ball to see actual outcome.";
  updateTimeline();
  setUiState(UiState.READY);
  setStatus("Replay restarted at original point.");
}

function attachEvents() {
  els.seasonSelect.addEventListener("change", async () => {
    try {
      await loadMatches();
      await loadInnings();
    } catch (err) {
      setUiState(UiState.ERROR);
      setStatus(err.message || "Failed to load matches.", "error");
    }
  });

  els.matchSelect.addEventListener("change", async () => {
    try {
      await loadInnings();
    } catch (err) {
      setUiState(UiState.ERROR);
      setStatus(err.message || "Failed to load innings.", "error");
    }
  });

  els.startReplayBtn.addEventListener("click", async () => {
    try {
      await startReplay();
    } catch (err) {
      setUiState(UiState.ERROR);
      setStatus(err.message || "Could not create replay.", "error");
    }
  });

  els.predictBtn.addEventListener("click", async () => {
    try {
      await predictNext();
    } catch (err) {
      setUiState(String(err.message || "").toLowerCase().includes("completed") ? UiState.COMPLETED : UiState.ERROR);
      setStatus(err.message || "Prediction failed.", "error");
    }
  });

  els.revealBtn.addEventListener("click", async () => {
    try {
      await revealNext();
    } catch (err) {
      setUiState(UiState.ERROR);
      setStatus(err.message || "Reveal failed.", "error");
    }
  });

  els.nextBtn.addEventListener("click", async () => {
    try {
      await predictNext();
    } catch (err) {
      setUiState(UiState.ERROR);
      setStatus(err.message || "Failed to move to next ball.", "error");
    }
  });

  els.restartBtn.addEventListener("click", async () => {
    try {
      await restartReplay();
    } catch (err) {
      setUiState(UiState.ERROR);
      setStatus(err.message || "Restart failed.", "error");
    }
  });

  els.closePlayerBtn.addEventListener("click", () => {
    window.location.hash = "";
  });

  window.addEventListener("hashchange", syncRoute);
}

async function bootstrap() {
  try {
    await loadSeasons();
    await loadMatches();
    await loadInnings();
    setUiState(UiState.SELECT_MATCH);
    setStatus("Select season, match, and innings to start the Time Machine.");
    attachEvents();
    syncRoute();
  } catch (err) {
    setUiState(UiState.ERROR);
    setStatus(err.message || "Unable to initialize app.", "error");
  }
}

bootstrap();

