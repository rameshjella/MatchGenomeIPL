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
      body: payload ? JSON.stringify(payload) : "{}",
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
  evidenceBlock: document.getElementById("evidenceBlock"),
  predictBtn: document.getElementById("predictBtn"),
  revealBtn: document.getElementById("revealBtn"),
  nextBtn: document.getElementById("nextBtn"),
  restartBtn: document.getElementById("restartBtn"),
  actualBlock: document.getElementById("actualBlock"),
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
  const canNext = nextState === UiState.PREDICTION_REVEALED;

  els.predictBtn.disabled = !canPredict;
  els.revealBtn.disabled = !canReveal;
  els.nextBtn.disabled = !canNext;
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

function updateTimeline() {
  els.timelineTrack.innerHTML = "";
  state.timeline.slice(-30).forEach((entry) => {
    const dot = document.createElement("div");
    dot.className = `timeline-dot ${entry.status}`;
    dot.title = `O${entry.over}.${entry.ball} ${entry.status} ${entry.actual || "pending"}`;
    dot.textContent = `${entry.over}.${entry.ball}`;
    els.timelineTrack.appendChild(dot);
  });
}

function renderPrediction(pred) {
  const probs = pred.prediction.outcome_probabilities;
  const top = pred.prediction.predicted_top_outcome;

  els.predictedTop.textContent = top === "wicket" ? "Wicket" : `${top} run${top === "1" ? "" : "s"}`;
  els.predictedPct.textContent = toPct(probs[top] || 0);

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
  rows.forEach((r) => els.probabilityBars.appendChild(r));

  els.evidenceBlock.innerHTML = `
    <div>Reliability: <strong>${pred.prediction.reliability}</strong></div>
    <div>Evidence: <strong>${pred.prediction.chosen_evidence_level}</strong></div>
    <div>Sample size: <strong>${pred.prediction.evidence_sample_size}</strong></div>
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

  els.batterValue.textContent = d.batter;
  els.nonStrikerValue.textContent = d.non_striker || "-";
  els.bowlerValue.textContent = d.bowler;
  els.phaseValue.textContent = s.phase;
  els.stateScoreValue.textContent = `${s.score}`;
  els.stateWicketsValue.textContent = `${s.wickets}`;
  els.stateBallsValue.textContent = `${s.legal_balls}`;
  if (state.sessionMeta?.current_state?.remaining_deliveries != null) {
    els.remainingValue.textContent = `${state.sessionMeta.current_state.remaining_deliveries}`;
  }
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
    <div><strong>Result:</strong> ${isCorrect ? "Correct" : "Incorrect"}</div>
  `;
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
  setUiState(UiState.READY);
  setStatus("Replay ready. Predict the next ball.");
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
  const exists = state.timeline.find((x) => x.over === dot.over && x.ball === dot.ball);
  if (!exists) state.timeline.push(dot);
  updateTimeline();

  setUiState(UiState.PREDICTION_AVAILABLE);
  clearStatus();
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
  updateTimeline();

  state.sessionMeta = await api.get(`/api/replays/${state.sessionId}`);
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
  setUiState(UiState.READY);
  setStatus("Replay restarted.");
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
      if (String(err.message || "").toLowerCase().includes("completed")) {
        setUiState(UiState.COMPLETED);
      } else {
        setUiState(UiState.ERROR);
      }
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
}

async function bootstrap() {
  try {
    await loadSeasons();
    await loadMatches();
    await loadInnings();
    setUiState(UiState.SELECT_MATCH);
    setStatus("Select season, match, and innings to start.");
    attachEvents();
  } catch (err) {
    setUiState(UiState.ERROR);
    setStatus(err.message || "Unable to initialize app.", "error");
  }
}

bootstrap();

