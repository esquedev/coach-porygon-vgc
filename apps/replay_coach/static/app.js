(function () {
  "use strict";

  const state = {
    app: null,
    activeStep: "home",
    activeCoachTab: "advice",
    lang: localStorage.getItem("porygon_lang") || "es",
    style: localStorage.getItem("porygon_style") || "vgc",
    qreBeta: Math.max(0.5, Math.min(20.0, Number(localStorage.getItem("porygon_qre_beta")) || 4.0)),
    qreFormulaOpen: false,
    mdScoutLoaded: false,
    rawReplayText: "",
    bo3Replays: [],
    bo3GamesMeta: [],
    activeGameIndex: 0,
    bo3TurnCache: {},
    previewData: null,
    selectedRosterId: { t1: null, t2: null },
    searchQuery: { t1: "", t2: "" },
    t1Validation: null,
    t2Validation: null,
    t2Inference: null,
    t2UserSpreads: {},
    currentTurn: 1,
    turnResults: {},
    pipelineLogs: [],
    matchSummary: null,
    activeStream: null,
    autoPausedTurns: {},
    playerPaused: true,
    jsErrors: [],
    lastBugReport: null,
    prevStepBeforePrep: "home",
    prep: {
      kind: "speed_tiers",
      topN: 50,
      usePaste: false,
      token: null,
      filename: "",
      generating: false,
      meta: null,
    },
    leadLab: {
      t1UsePaste: false,
      t2Mode: "full", // "full" | "scout"
      t2UsePaste: false,
      scoutReplays: [],
      t2Inference: null,
      t2UserSpreads: {},
      running: false,
      activeStream: null,
      jobId: null,
      jobMeta: null,
      result: null,
      selectedLead1: null,
      selectedLead2: null,
      selectedBench1: 0,
      selectedBench2: 0,
      deepAudit: null,
      deepAuditReqSeq: 0,
      playbookMode: "by_mine", // "by_mine" (1 Own Lead vs Top Opp Leads) | "by_opp" (1 Opp Lead vs Top Own Leads)
      playbookSelectedIdx: null,
      batchAuditsByKey: {},
      vaultOpen: false,
      vaultRuns: [],
      vaultTotal: 0,
      vaultT1Teams: [],
      vaultFilterAdv: "",
      vaultFilterT1: "",
      vaultSearch: "",
      cacheHit: null,
      cachedDeepAuditKeys: new Set(),
      currentMatchupHash: "",
      lookupTimer: null,
    },
  };

  const STAT_KEYS = ["hp", "atk", "def", "spa", "spd", "spe"];
  const STAT_LABELS = { hp: "HP", atk: "Atk", def: "Def", spa: "SpA", spd: "SpD", spe: "Spe" };
  const NATURE_MODS = {
    Lonely: ["atk", "def"], Brave: ["atk", "spe"], Adamant: ["atk", "spa"], Naughty: ["atk", "spd"],
    Bold: ["def", "atk"], Relaxed: ["def", "spe"], Impish: ["def", "spa"], Lax: ["def", "spd"],
    Timid: ["spe", "atk"], Hasty: ["spe", "def"], Jolly: ["spe", "spa"], Naive: ["spe", "spd"],
    Modest: ["spa", "atk"], Mild: ["spa", "def"], Quiet: ["spa", "spe"], Rash: ["spa", "spd"],
    Calm: ["spd", "atk"], Gentle: ["spd", "def"], Sassy: ["spd", "spe"], Careful: ["spd", "spa"],
  };

  function getNatureDelta(natureName, statKey) {
    const pair = NATURE_MODS[natureName || ""];
    if (!pair) return 0;
    if (pair[0] === statKey) return 1;
    if (pair[1] === statKey) return -1;
    return 0;
  }

  function calcChampionsL50Stat(statKey, baseVal, spVal, natureName) {
    const b = Number(baseVal || 80);
    const sp = Number(spVal || 0);
    if (statKey === "hp") return b + sp + 75;
    const d = getNatureDelta(natureName, statKey);
    const mult = d > 0 ? 1.1 : d < 0 ? 0.9 : 1.0;
    return Math.floor((b + sp + 20) * mult);
  }

  window.addEventListener("error", (ev) => {
    if (ev && ev.message) state.jsErrors.push(`${ev.message} (${ev.lineno || 0})`);
  });
  window.addEventListener("unhandledrejection", (ev) => {
    if (ev && ev.reason) state.jsErrors.push(`PromiseRejection: ${String(ev.reason)}`);
  });

  const $ = (id) => document.getElementById(id);

  function profileKey() {
    return `${state.lang}_${state.style}`;
  }

  function normStr(s) {
    return String(s || "")
      .toLowerCase()
      .replace(/[^a-z0-9]/g, "");
  }

  // Exact Logit Quantal Response Equilibrium (LQRE) fixed-point solver matching
  // `src/engine/solver/game_theory.py:solve_quantal_response` (< 0.5 ms in browser).
  function _stableSoftmax(logits) {
    let maxVal = -Infinity;
    for (let i = 0; i < logits.length; i += 1) {
      if (logits[i] > maxVal) maxVal = logits[i];
    }
    const exps = new Float64Array(logits.length);
    let sum = 0.0;
    for (let i = 0; i < logits.length; i += 1) {
      const e = Math.exp(Math.max(-500.0, Math.min(500.0, logits[i] - maxVal)));
      exps[i] = e;
      sum += e;
    }
    const denom = sum > 0.0 ? sum : 1.0;
    for (let i = 0; i < logits.length; i += 1) exps[i] /= denom;
    return exps;
  }

  function solveLogitQreClient(U, betaRaw, maxIter, damping, tol) {
    const M = (U && U.length) || 0;
    const N = M > 0 && U[0] ? U[0].length : 0;
    if (M === 0 || N === 0) return { p: [], q: [], expected_value: 0.0 };
    const beta = Math.max(0.01, Number(betaRaw || 4.0));
    const iters = maxIter || 250;
    const alpha = damping || 0.35;
    const eps = tol || 1e-7;
    let p = new Float64Array(M);
    let q = new Float64Array(N);
    for (let i = 0; i < M; i += 1) p[i] = 1.0 / M;
    for (let j = 0; j < N; j += 1) q[j] = 1.0 / N;

    const pU = new Float64Array(N);
    const Uq = new Float64Array(M);
    for (let it = 0; it < iters; it += 1) {
      for (let j = 0; j < N; j += 1) {
        let acc = 0.0;
        for (let i = 0; i < M; i += 1) acc += p[i] * U[i][j];
        pU[j] = -beta * acc;
      }
      const qTarget = _stableSoftmax(pU);
      const qNext = new Float64Array(N);
      for (let j = 0; j < N; j += 1) qNext[j] = (1.0 - alpha) * q[j] + alpha * qTarget[j];

      for (let i = 0; i < M; i += 1) {
        let acc = 0.0;
        const row = U[i];
        for (let j = 0; j < N; j += 1) acc += row[j] * qNext[j];
        Uq[i] = beta * acc;
      }
      const pTarget = _stableSoftmax(Uq);
      const pNext = new Float64Array(M);
      let diff = 0.0;
      for (let i = 0; i < M; i += 1) {
        pNext[i] = (1.0 - alpha) * p[i] + alpha * pTarget[i];
        diff = Math.max(diff, Math.abs(pNext[i] - p[i]));
      }
      for (let j = 0; j < N; j += 1) {
        diff = Math.max(diff, Math.abs(qNext[j] - q[j]));
      }
      p = pNext;
      q = qNext;
      if (diff < eps) break;
    }

    let ev = 0.0;
    for (let i = 0; i < M; i += 1) {
      const row = U[i];
      for (let j = 0; j < N; j += 1) ev += p[i] * row[j] * q[j];
    }
    return { p: Array.from(p), q: Array.from(q), expected_value: ev };
  }
  window.__porygonSolveLogitQre = solveLogitQreClient;

  function getTurnLiveQre(data) {
    if (!data || !data.qre_matrix || !data.qre_matrix.U || !data.qre_matrix.U.length) return null;
    if (data._cachedQreBeta === state.qreBeta && data._cachedQreRes) return data._cachedQreRes;
    const res = solveLogitQreClient(data.qre_matrix.U, state.qreBeta);
    data._cachedQreBeta = state.qreBeta;
    data._cachedQreRes = res;
    return res;
  }

  function getLeadLabLiveQre(res) {
    if (!res || !res.payoff_matrix || !res.payoff_matrix.length) return null;
    if (res._cachedQreBeta === state.qreBeta && res._cachedQreRes) return res._cachedQreRes;
    const qRes = solveLogitQreClient(res.payoff_matrix, state.qreBeta, 180, 0.35, 1e-6);
    res._cachedQreBeta = state.qreBeta;
    res._cachedQreRes = qRes;
    return qRes;
  }

  function renderQreBetaControlHtml(scope) {
    const isEs = state.lang === "es";
    const isSci = state.style === "scientific";
    const beta = state.qreBeta;
    const presets = isSci
      ? [
          { v: 1.0, lbl: "β=1.0" },
          { v: 4.0, lbl: "β=4.0" },
          { v: 8.0, lbl: "β=8.0" },
          { v: 16.0, lbl: "β=16.0" },
        ]
      : isEs
        ? [
            { v: 1.0, lbl: "Casual (1)" },
            { v: 4.0, lbl: "Ladder (4)" },
            { v: 8.0, lbl: "Top Cut (8)" },
            { v: 16.0, lbl: "Óptimo (16)" },
          ]
        : [
            { v: 1.0, lbl: "Casual (1)" },
            { v: 4.0, lbl: "Ladder (4)" },
            { v: 8.0, lbl: "Top Cut (8)" },
            { v: 16.0, lbl: "Optimal (16)" },
          ];
    const presetBtns = presets
      .map(
        (pr) =>
          `<button type="button" class="qre-preset-btn ${Math.abs(beta - pr.v) < 0.25 ? "active" : ""}" data-qre-preset="${pr.v}">${escapeHtml(pr.lbl)}</button>`
      )
      .join("");

    const titleLbl = isSci
      ? (isEs ? "LQRE Racionalidad (β):" : "LQRE Rationality (β):")
      : (isEs ? "Nivel del rival humano:" : "Human rival precision:");
    const valLbl = isSci
      ? `β = ${beta.toFixed(1)}`
      : beta <= 2.0
        ? (isEs ? `Casual (${beta.toFixed(1)})` : `Casual (${beta.toFixed(1)})`)
        : beta <= 5.5
          ? (isEs ? `Ladder (${beta.toFixed(1)})` : `Ladder (${beta.toFixed(1)})`)
          : beta <= 11.0
            ? (isEs ? `Top Cut (${beta.toFixed(1)})` : `Top Cut (${beta.toFixed(1)})`)
            : (isEs ? `Élite (${beta.toFixed(1)})` : `Elite (${beta.toFixed(1)})`);
    const helpBtnLbl = isSci
      ? (isEs ? "? Fórmula LQRE" : "? LQRE Formula")
      : (isEs ? "? ¿Cómo funciona?" : "? How it works");

    const formulaBody = isSci
      ? isEs
        ? `<div class="qre-formula-math">pᵢ ∝ exp(+β · Σⱼ Uᵢⱼ qⱼ) &nbsp;|&nbsp; qⱼ ∝ exp(−β · Σᵢ pᵢ Uᵢⱼ)</div>
           <div><strong>Interpretación LQRE:</strong> β &gt; 0 es la inversa de temperatura de racionalidad acotada. Cuando <strong>β → 0</strong> ambos jugadores eligen casi al azar (uniforme); con <strong>β ≈ 4</strong> modela errores humanos típicos de ladder; cuando <strong>β → ∞</strong> converge al Equilibrio de Nash exacto sin ruido.</div>`
        : `<div class="qre-formula-math">pᵢ ∝ exp(+β · Σⱼ Uᵢⱼ qⱼ) &nbsp;|&nbsp; qⱼ ∝ exp(−β · Σᵢ pᵢ Uᵢⱼ)</div>
           <div><strong>LQRE Interpretation:</strong> β &gt; 0 is the bounded-rationality inverse temperature. As <strong>β → 0</strong> play approaches uniform random; <strong>β ≈ 4</strong> models strong ladder human error; as <strong>β → ∞</strong> probabilities converge toward exact zero-noise Nash Equilibrium.</div>`
      : isEs
        ? `<div><strong>¿Cómo leer la Probabilidad Humana?</strong> Este control ajusta qué tan disciplinado es tu rival. Un valor <strong>bajo (1–2)</strong> asume un rival de ladder que hace clics arriesgados o impredecibles; <strong>4</strong> refleja juego competitivo estándar; <strong>8–16</strong> refleja un jugador de Regional Top Cut que casi siempre encuentra las mejores respuestas del turno.</div>`
        : `<div><strong>How to read Human Likeliness:</strong> This slider adjusts how disciplined your opponent is. A <strong>low setting (1–2)</strong> models an unpredictable ladder opponent taking wild reads; <strong>4</strong> models solid competitive play; <strong>8–16</strong> models a Regional Top Cut specialist who almost always clicks the strongest turn responses.</div>`;

    return `<div class="qre-beta-bar" data-qre-scope="${escapeHtml(scope)}">
      <div class="qre-beta-top">
        <div class="qre-beta-slider-wrap">
          <strong style="font-size:11px;white-space:nowrap">${escapeHtml(titleLbl)}</strong>
          <input class="qre-beta-slider" type="range" min="0.5" max="20.0" step="0.5" value="${beta.toFixed(1)}" aria-label="${escapeHtml(titleLbl)}" />
          <span class="qre-beta-val">${escapeHtml(valLbl)}</span>
        </div>
        <div class="qre-presets">
          ${presetBtns}
          <button type="button" class="btn btn-ghost btn-xs qre-help-toggle">${escapeHtml(helpBtnLbl)}</button>
        </div>
      </div>
      <div class="qre-formula-card" style="display:${state.qreFormulaOpen ? "block" : "none"}">${formulaBody}</div>
    </div>`;
  }

  function bindQreBetaControl(rootEl, onChange) {
    if (!rootEl) return;
    const slider = rootEl.querySelector(".qre-beta-slider");
    if (slider) {
      slider.addEventListener("input", () => {
        const nextVal = Math.max(0.5, Math.min(20.0, Number(slider.value) || 4.0));
        state.qreBeta = nextVal;
        localStorage.setItem("porygon_qre_beta", String(nextVal));
        onChange();
      });
    }
    rootEl.querySelectorAll(".qre-preset-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const nextVal = Math.max(0.5, Math.min(20.0, Number(btn.dataset.qrePreset) || 4.0));
        state.qreBeta = nextVal;
        localStorage.setItem("porygon_qre_beta", String(nextVal));
        onChange();
      });
    });
    const toggle = rootEl.querySelector(".qre-help-toggle");
    if (toggle) {
      toggle.addEventListener("click", () => {
        state.qreFormulaOpen = !state.qreFormulaOpen;
        onChange();
      });
    }
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function spritePairHtml(spriteUrl, itemSpriteUrl, speciesName, itemName) {
    const monImg = spriteUrl
      ? `<img class="mon-sprite" src="${escapeHtml(spriteUrl)}" alt="${escapeHtml(speciesName)}" loading="lazy" />`
      : "";
    const itemImg = itemSpriteUrl
      ? `<img class="item-sprite" src="${escapeHtml(itemSpriteUrl)}" title="${escapeHtml(itemName || "")}" alt="${escapeHtml(itemName || "")}" loading="lazy" />`
      : "";
    return `<span class="sprite-pair">${monImg}${itemImg}</span>`;
  }

  function getTermInfo(termKey, fallbackLabel, useShort) {
    const termRoot = (state.app && state.app.terminology) || {};
    const terms = termRoot.terms || {};
    const aliases = termRoot.aliases || {};
    const canon = terms[termKey] ? termKey : aliases[termKey] || termKey;
    const byLang = terms[canon] && terms[canon][state.lang];
    const entry = byLang && byLang[state.style];
    if (!entry) {
      return { label: fallbackLabel || termKey, tooltip: "" };
    }
    return {
      label: (useShort ? entry.short : entry.label) || entry.label || fallbackLabel || termKey,
      tooltip: entry.desc || "",
    };
  }

  function postToShowdown(payload) {
    const frame = $("showdown-iframe");
    if (frame && frame.contentWindow) {
      frame.contentWindow.postMessage(payload, "*");
    }
  }

  // -------------------------------------------------------------------------
  // Navigation & Full 4-Mode Translation (ES/EN x VGC/Scientific)
  // -------------------------------------------------------------------------
  function setStep(stepName) {
    if (stepName === "prep" && state.activeStep !== "prep") {
      state.prevStepBeforePrep = state.activeStep || "home";
    }
    state.activeStep = stepName;
    ["home", "setup", "pipeline", "review", "prep", "lead-lab", "analytics", "md-scout", "team-db"].forEach((s) => {
      const view = $(`view-${s}`);
      if (view) view.classList.toggle("active", s === stepName);
    });
    ["setup", "pipeline", "review"].forEach((s) => {
      const btn = $(`nav-step-${s}`);
      if (btn) btn.classList.toggle("active", s === stepName);
    });
    const bo3Sub = $("bo3-stepper-bar");
    const isBo3 = stepName === "setup" || stepName === "pipeline" || stepName === "review";
    if (bo3Sub) bo3Sub.style.display = isBo3 ? "block" : "none";

    // Sync topbar Quick Tool Switcher active pill & brand Home highlight
    const activeHubKey =
      stepName === "home"
        ? "home"
        : isBo3
          ? "bo3"
          : stepName === "lead-lab"
            ? "lead-lab"
            : stepName === "analytics"
              ? "analytics"
              : stepName === "md-scout"
                ? "md-scout"
                : stepName === "team-db"
                  ? "team-db"
                  : stepName === "prep"
                    ? (state.prep.kind === "damage_matrix" ? "damage" : "speed")
                    : "home";
    if ($("btn-go-home")) $("btn-go-home").classList.toggle("active", activeHubKey === "home");
    ["speed", "damage", "bo3", "lead-lab", "analytics", "md-scout", "team-db"].forEach((k) => {
      const pill = $(`nav-hub-${k}`);
      if (pill) pill.classList.toggle("active", k === activeHubKey);
    });
    if (stepName === "review") {
      requestAnimationFrame(syncCoachPanelHeight);
    }
  }

  const COACH_TABS = ["advice", "details", "matrix", "board", "graph"];

  function syncCoachPanelHeight() {
    const playerPanel = $("review-player-panel");
    const coachPanel = $("review-coach-panel");
    if (!playerPanel || !coachPanel) return;
    if (window.innerWidth <= 1100) {
      coachPanel.style.height = "";
      return;
    }
    const h = playerPanel.offsetHeight;
    if (h > 200) {
      coachPanel.style.height = `${h}px`;
    }
  }

  function setCoachTab(tabName) {
    state.activeCoachTab = COACH_TABS.includes(tabName) ? tabName : "advice";
    COACH_TABS.forEach((t) => {
      const btn = $(`tab-btn-${t}`);
      if (btn) btn.classList.toggle("active", t === state.activeCoachTab);
    });
    if (state.turnResults[state.currentTurn]) {
      renderTurnPanel(state.turnResults[state.currentTurn]);
    }
    syncCoachPanelHeight();
  }

  function updateKOptions() {
    const sel = $("setup-k-select");
    if (!sel) return;
    const isEs = state.lang === "es";
    const isCpu = state.app && state.app.device_type === "cpu";
    const curVal = sel.value || String((state.app && state.app.recommended_k) || 128);
    const opts = isCpu
      ? [
          { v: "32", es: "Rápido CPU (K=32 · ~3–6s/turno)", en: "CPU Fast (K=32 · ~3–6s/turn)" },
          { v: "64", es: "Balanceado CPU (K=64 · recomendado)", en: "CPU Balanced (K=64 · recommended)" },
          { v: "128", es: "Alto CPU (K=128 · más lento)", en: "CPU High (K=128 · slower)" },
          { v: "256", es: "Torneo (K=256 · muy lento en CPU)", en: "Tournament (K=256 · very slow on CPU)" },
        ]
      : [
          { v: "64", es: "Rápido (K=64 · ~1–2s/turno)", en: "Fast (K=64 · ~1–2s/turn)" },
          { v: "128", es: "Balanceado (K=128 · recomendado)", en: "Balanced (K=128 · recommended)" },
          { v: "256", es: "Torneo (K=256 · ~8–12s/turno)", en: "Tournament (K=256 · ~8–12s/turn)" },
          { v: "512", es: "Profundo (K=512 · ~25–35s/turno)", en: "Deep (K=512 · ~25–35s/turn)" },
        ];
    sel.innerHTML = opts
      .map((o) => `<option value="${o.v}">${escapeHtml(isEs ? o.es : o.en)}</option>`)
      .join("");
    if (opts.some((o) => o.v === curVal)) {
      sel.value = curVal;
    } else {
      sel.value = String((state.app && state.app.recommended_k) || 128);
    }
  }

  function updatePlayPauseButton() {
    const btn = $("btn-play-pause");
    if (!btn) return;
    const isEs = state.lang === "es";
    if (state.playerPaused) {
      btn.innerHTML = `<svg width="11" height="11" viewBox="0 0 12 12" fill="currentColor" style="vertical-align:-1px;margin-right:4px" aria-hidden="true"><polygon points="2,1 11,6 2,11"/></svg>${isEs ? "Reproducir" : "Play"}`;
    } else {
      btn.innerHTML = `<svg width="11" height="11" viewBox="0 0 12 12" fill="currentColor" style="vertical-align:-1px;margin-right:4px" aria-hidden="true"><rect x="2" y="1" width="3" height="10"/><rect x="7" y="1" width="3" height="10"/></svg>${isEs ? "Pausar" : "Pause"}`;
    }
  }

  function applyAllTranslations() {
    const isEs = state.lang === "es";
    const isSci = state.style === "scientific";

    $("btn-lang-es").classList.toggle("active", isEs);
    $("btn-lang-en").classList.toggle("active", !isEs);
    $("btn-style-vgc").classList.toggle("active", !isSci);
    $("btn-style-sci").classList.toggle("active", isSci);
    $("btn-style-sci").textContent = isEs ? "Científico" : "Scientific";

    $("lbl-step-1").textContent = isEs ? "Partida y Equipos" : "Match & Teams";
    $("lbl-step-2").textContent = isEs ? "Ejecución" : "Pipeline";
    $("lbl-step-3").textContent = isEs ? "Revisión" : "Review";

    $("lbl-setup-replay-title").textContent = isEs
      ? "Configurar Replay y Equipos Full OTS (Regulation M-C)"
      : "Configure Replay & Full OTS Teams (Regulation M-C)";
    $("btn-toggle-raw-replay").textContent = isEs ? "Pegar Log / HTML" : "Paste Log / HTML";
    $("btn-load-sample").textContent = isEs ? "Partida de Ejemplo" : "Sample Match";
    $("lbl-dropzone-title").textContent = isEs
      ? "Arrastra aquí 1 a 3 Replays (Bo1 o serie Bo3: .html, .log, .txt)"
      : "Drop 1 to 3 Replay files (Bo1 or Bo3 series: .html, .log, .txt)";
    $("lbl-dropzone-sub").textContent = isEs
      ? "Sube Game 1, Game 2 y Game 3 juntos para combinar todas las pistas de daño y velocidad en un solo 66-SP rival"
      : "Upload Game 1, Game 2, and Game 3 together to pool all damage & speed clues into one shared 66-SP opponent sheet";
    $("lbl-pick-file").textContent = isEs ? "Seleccionar replay(s)" : "Choose replay(s)";
    $("btn-change-replay").textContent = isEs ? "Cambiar replay(s)" : "Change replay(s)";
    $("lbl-pov-select").textContent = isEs ? "Perspectiva:" : "Coach POV:";
    $("lbl-k-select").textContent = getTermInfo("rng_samples", "RNG", true).label + ":";
    if ($("lbl-two-ply")) {
      $("lbl-two-ply").textContent = isEs ? "2-Ply (Turn+2)" : "2-Ply Lookahead";
    }
    $("lbl-launch-btn").textContent = isEs ? "Iniciar Análisis Tensor Core →" : "Run Tensor Core Analysis →";

    ["t1", "t2"].forEach((side) => {
      $(`${side}-search-input`).placeholder = isEs
        ? "Filtrar por Pokémon o nombre (ej. Charizard Garchomp)..."
        : "Filter by Pokémon or team name (e.g. Charizard Garchomp)...";
      if ($(`btn-${side}-infer`)) {
        $(`btn-${side}-infer`).textContent =
          side === "t2"
            ? (isEs ? "Resolver 66-SP" : "Solve 66-SP")
            : (isEs ? "Resolver 66-SP" : "Solve 66-SP");
      }
      $(`btn-${side}-toggle-paste`).textContent = isEs ? "Pegar OTS" : "Paste OTS";
      $(`btn-${side}-clear`).textContent = isEs ? "Limpiar" : "Clear";
      $(`btn-${side}-validate`).textContent = isEs ? "Aplicar" : "Apply";
    });
    if ($("btn-t2-autofill-all")) {
      $("btn-t2-autofill-all").textContent = isEs ? "Auto-Completar" : "Auto-Fill Defaults";
    }
    if ($("btn-t2-save-ephemeral")) {
      $("btn-t2-save-ephemeral").textContent = isEs ? "Guardar en Biblioteca" : "Save to Library";
    }
    if ($("t2-clamped-sp-hint")) {
      $("t2-clamped-sp-hint").textContent = isEs
        ? "Los límites bloqueados (🔒) y acotados provienen de daño/velocidad reales del replay y no se pueden anular. Ajusta los SP restantes libremente."
        : "Locked (🔒) and bounded intervals come directly from observed replay damage & speed proofs and cannot be overridden. Adjust remaining SP freely.";
    }

    $("lbl-pipeline-title").textContent = isEs
      ? "Ejecución del Pipeline Tensor Core"
      : "Tensor Core Pipeline Execution";
    $("btn-cancel-stream").textContent = isEs ? "Detener" : "Stop";
    $("btn-restart-stream").textContent = isEs ? "Reiniciar" : "Restart";
    updatePipelineActionButtons();
    $("lbl-done-acc").textContent = isEs ? "PRECISIÓN" : "ACCURACY";
    $("lbl-start-replay-btn").textContent = isEs ? "Ver Replay Sincronizado ▶" : "Start Synchronized Review ▶";

    $("lbl-bar-acc").textContent = isEs ? "PRECISIÓN" : "ACCURACY";
    $("lbl-autopause").textContent = isEs ? "Auto-Pausa en errores" : "Auto-Pause on mistakes";
    $("lbl-export-csv").textContent = isEs ? "Exportar CSV" : "Export CSV";
    $("btn-back-to-log").textContent = "Log";
    updatePlayPauseButton();
    $("btn-flip-pov").textContent = isEs ? "Invertir" : "Flip";
    $("btn-recompute-turn").textContent = isEs ? "Recalcular" : "Recompute";

    if ($("tab-btn-advice")) $("tab-btn-advice").textContent = isEs ? "Resumen" : "Summary";
    if ($("tab-btn-details")) {
      $("tab-btn-details").textContent = isSci
        ? (isEs ? "Auditoría" : "Audit")
        : (isEs ? "Claves" : "Takeaways");
    }
    if ($("tab-btn-matrix")) {
      $("tab-btn-matrix").textContent = isSci
        ? "Nash / IEDS"
        : (isEs ? "Jugadas" : "Plays");
    }
    if ($("tab-btn-board")) $("tab-btn-board").textContent = isEs ? "Tablero" : "Board";
    if ($("tab-btn-graph")) $("tab-btn-graph").textContent = isEs ? "Curva" : (isSci ? "Curve" : "Graph");

    if ($("lbl-prep-btn")) {
      $("lbl-prep-btn").textContent = isEs ? "Herramientas Prep" : "Prep Tools";
    }
    if ($("lbl-nav-speed")) $("lbl-nav-speed").textContent = isEs ? "Velocidades" : "Speed Tiers";
    if ($("lbl-nav-damage")) $("lbl-nav-damage").textContent = isEs ? "Daño & KO" : "Damage Calcs";
    if ($("lbl-nav-bo3")) $("lbl-nav-bo3").textContent = "Bo3 Coach";
    if ($("lbl-nav-lead-lab")) $("lbl-nav-lead-lab").textContent = isEs ? "Lead Lab 90×90" : "90×90 Lead Lab";
    if ($("lbl-nav-analytics")) $("lbl-nav-analytics").textContent = isEs ? "Analítica" : "Analytics";
    if ($("lbl-bo3-subtag")) $("lbl-bo3-subtag").textContent = isEs ? "🧠 BO3 REPLAY COACH" : "🧠 BO3 REPLAY COACH";

    // Home Hub Hero + 4 CTA Cards bilingual copy
    if ($("lbl-home-title")) {
      $("lbl-home-title").textContent = isEs
        ? "Coach Porygon VGC — Command Hub"
        : "Coach Porygon VGC — Command Hub";
    }
    if ($("lbl-home-sub")) {
      $("lbl-home-sub").textContent = isEs
        ? "Suite competitiva local de Regulation M-C: tablas móviles offline Base64, auditoría Bo3 con Equilibrio de Nash / IEDS y Laboratorio Turno 1 de 90×90 modos."
        : "Local Regulation M-C competitive suite: offline Base64 mobile prep tables, Bo3 Nash / IEDS replay audits, and a Factored 90×90 Turn-1 Lead & Bring Lab.";
    }
    if ($("lbl-cta1-badge")) $("lbl-cta1-badge").textContent = isEs ? "HTML DINÁMICO · OFFLINE" : "DYNAMIC HTML · OFFLINE";
    if ($("lbl-cta1-title")) $("lbl-cta1-title").textContent = isEs ? "Speed Tiers Dinámicos" : "Dynamic Speed Tiers";
    if ($("lbl-cta1-desc")) {
      $("lbl-cta1-desc").textContent = isEs
        ? "Genera una tabla interactiva de velocidades Lv.50 (31 IVs) contra el Top 50 DuckDB con Tailwind, Icy Wind, Choice Scarf, Unburden, climas y cambios de Mega al instante."
        : "Generate an interactive Lv.50 (31-IV) Speed Tiers table vs Top 50 DuckDB with Tailwind, Icy Wind, Choice Scarf, Unburden, Weather, and Mega speed shifts.";
    }
    if ($("lbl-cta1-meta")) $("lbl-cta1-meta").textContent = isEs ? "1-Click HTML móvil Base64 · Cero IA" : "1-Click Mobile Base64 HTML · Zero-AI";

    if ($("lbl-cta2-badge")) $("lbl-cta2-badge").textContent = isEs ? "16 ROLLS SMOGON · OFFLINE" : "SMOGON 16-ROLL · OFFLINE";
    if ($("lbl-cta2-title")) $("lbl-cta2-title").textContent = isEs ? "Matriz de Daño & KOs" : "Damage & KO Matrix";
    if ($("lbl-cta2-desc")) {
      $("lbl-cta2-desc").textContent = isEs
        ? "Precalcula todos los rangos OHKO/2HKO exactos de tu equipo con Smogon Champions (5 Climas × 5 Campos × Pantallas) y llévalos en un HTML autónomo al torneo."
        : "Pre-compute exact Smogon Champions 16-roll OHKO/2HKO ranges across all 5 Weathers × 5 Terrains & Screens and export a single-file tournament HTML.";
    }
    if ($("lbl-cta2-meta")) $("lbl-cta2-meta").textContent = isEs ? "1-Click HTML móvil Base64 · Cero IA" : "1-Click Mobile Base64 HTML · Zero-AI";

    if ($("lbl-cta3-badge")) $("lbl-cta3-badge").textContent = isEs ? "TENSOR CORE · BO1 / BO3" : "TENSOR CORE · BO1 / BO3";
    if ($("lbl-cta3-title")) $("lbl-cta3-title").textContent = "Bo3 Replay Coach";
    if ($("lbl-cta3-desc")) {
      $("lbl-cta3-desc").textContent = isEs
        ? "Sube 1 a 3 replays de Showdown, deduce el 66-SP rival con límites exactos bloqueados y audita cada turno con el reproductor oficial sincronizado, IEDS, Nash y CVaR₁₀."
        : "Upload 1–3 Showdown replays, infer opponent 66-SP with locked deterministic bounds, and audit every turn alongside the synced Showdown player, IEDS, Nash & CVaR₁₀.";
    }
    if ($("lbl-cta3-meta")) $("lbl-cta3-meta").textContent = isEs ? "Reproductor Showdown + Explicación VGC/Científica" : "Synced Showdown Player + VGC / Scientific Coach";

    if ($("lbl-cta4-badge")) $("lbl-cta4-badge").textContent = isEs ? "NUEVO · 90×90 (8,100 MODOS)" : "NEW · 90×90 (8,100 MODES)";
    if ($("lbl-cta4-title")) $("lbl-cta4-title").textContent = isEs ? "Simulador de Leads Turno 1" : "Turn-1 Lead & Bring Lab";
    if ($("lbl-cta4-desc")) {
      $("lbl-cta4-desc").textContent = isEs
        ? "Enfrenta dos equipos de 6 Pokémon (66-SP o OTS + logs Bo3) y simula el Turno 1 para los 15×15 leads × 6×6 bancas en GPU para obtener tu Equilibrio de Nash de Team Preview."
        : "Pit any two 6-Pokémon teams (Full 66-SP or OTS + Bo3 scouting logs) and simulate Turn 1 across all 15×15 leads × 6×6 benches on GPU for your Team-Preview Nash Equilibrium.";
    }
    if ($("lbl-cta4-meta")) $("lbl-cta4-meta").textContent = isEs ? "Heatmap 15×15 en vivo + Drilldown 6×6 + Audit K=128" : "Live 15×15 Heatmap + 6×6 Drilldown + Deep K=128 Audit";

    if ($("lbl-cta5-badge")) $("lbl-cta5-badge").textContent = isEs ? "TELEMETRÍA LOCAL · CSV POR EQUIPO" : "LOCAL TELEMETRY · PER-TEAM CSV";
    if ($("lbl-cta5-title")) $("lbl-cta5-title").textContent = isEs ? "Analítica de Sesiones y Torneos Bo3" : "Bo3 Session & Tournament Analytics";
    if ($("lbl-cta5-desc")) {
      $("lbl-cta5-desc").textContent = isEs
        ? "Crea carpetas por equipo, registra tus partidas auditadas desde Bo3 Coach y sigue tu Win Rate, curva de precisión Nash, errores por fase (Lead / Mid / Endgame) y efectividad por par de Leads."
        : "Create team folders, log your audited Bo3 Coach matches, and track your Win Rate, Nash accuracy trendline, phase mistakes (Lead / Mid / Endgame), and Turn-1 lead pair win rates.";
    }
    if ($("lbl-cta5-meta")) $("lbl-cta5-meta").textContent = isEs ? "Guía paso a paso + Carpetas locales en data/telemetry/" : "Step-by-step walkthrough + Local folders in data/telemetry/";

    // Lead Lab bilingual labels
    if ($("lbl-ll-title")) {
      $("lbl-ll-title").textContent = isEs
        ? "🎯 Simulador de Leads & Brings Turno 1 (90×90 Nash)"
        : "🎯 Turn-1 Lead & Bring Lab (Factored 90×90 Nash)";
    }
    if ($("lbl-ll-launch")) {
      $("lbl-ll-launch").textContent = state.leadLab.running
        ? (isEs ? "Simulando..." : "Simulating...")
        : (isEs ? "Simular 90×90 Leads →" : "Run 90×90 Lead Nash →");
    }
    if ($("btn-ll-cancel")) $("btn-ll-cancel").textContent = isEs ? "■ Detener" : "■ Stop";
    if ($("btn-ll-cancel-bar")) $("btn-ll-cancel-bar").textContent = isEs ? "■ Detener" : "■ Stop";
    if ($("ll-compute-mode")) {
      const cm = $("ll-compute-mode");
      const opts = cm.options;
      if (opts && opts.length >= 3) {
        opts[0].textContent = isEs ? "⚡ Híbrido (GPU + CPU)" : "⚡ Hybrid (GPU + CPU)";
        opts[1].textContent = isEs ? "🚀 Solo GPU (CUDA)" : "🚀 GPU Only (CUDA)";
        opts[2].textContent = isEs ? "🧵 CPU Paralelo (Multi-Hilo)" : "🧵 CPU Parallel (Multi-Thread)";
      }
    }
    if ($("lbl-ll-t1-title")) $("lbl-ll-t1-title").textContent = isEs ? "Tu Equipo (trainer_1 · 66-SP)" : "Your Team (trainer_1 · Full 66-SP)";
    if ($("lbl-ll-t2-title")) $("lbl-ll-t2-title").textContent = isEs ? "Equipo Rival (trainer_2)" : "Opponent Team (trainer_2)";
    if ($("btn-ll-t2-mode-full")) $("btn-ll-t2-mode-full").textContent = "Full 66-SP";
    if ($("btn-ll-t2-mode-scout")) $("btn-ll-t2-mode-scout").textContent = isEs ? "OTS + Logs Bo3" : "OTS + Bo3 Logs";
    if ($("lbl-ll-scout-hint")) {
      $("lbl-ll-scout-hint").textContent = isEs
        ? "Sube 1 a 3 replays Bo3 del rival (.html, .log, .txt) para acotar su 66-SP con Smogon Champions"
        : "Upload 1–3 opponent Bo3 replays (.html, .log, .txt) to infer clamped 66-SP via Smogon Champions";
    }
    if ($("lbl-ll-scout-pick")) $("lbl-ll-scout-pick").textContent = isEs ? "Seleccionar logs Bo3" : "Select Bo3 Logs";
    if ($("lbl-ll-solve-sp")) $("lbl-ll-solve-sp").textContent = isEs ? "Resolver 66-SP Rival" : "Solve Opponent 66-SP";
    if ($("lbl-ll-podium-t1")) $("lbl-ll-podium-t1").textContent = isEs ? "🏆 Mejores Brings (Equilibrio de Nash 90×90)" : "🏆 Optimal Brings (Global 90×90 Nash)";
    if ($("lbl-ll-podium-t2")) $("lbl-ll-podium-t2").textContent = isEs ? "🛡 Brings Más Peligrosos del Rival & Tu Counter" : "🛡 Opponent Top Brings & Best Counter-Lead";
    if ($("lbl-ll-heatmap-title")) {
      $("lbl-ll-heatmap-title").textContent = isEs
        ? "Mapa de Calor de Leads (15×15 · Click en cualquier celda para ver sus 6×6 bancas)"
        : "Lead-Pair Heatmap (15×15 · Click any cell to inspect its 6×6 Back-2 bench matrix)";
    }
    if ($("lbl-ll-leg-win")) $("lbl-ll-leg-win").textContent = isEs ? "+ Ventaja T1" : "+ T1 Adv";
    if ($("lbl-ll-leg-even")) $("lbl-ll-leg-even").textContent = isEs ? "Parejo" : "Even";
    if ($("lbl-ll-leg-lose")) $("lbl-ll-leg-lose").textContent = isEs ? "- Ventaja Rival" : "- Opp Adv";
    if ($("lbl-ll-deep-btn")) {
      $("lbl-ll-deep-btn").textContent = isEs
        ? "⚡ Auditoría Profunda Turno 1 (Sin Poda · K=128)"
        : "⚡ Run Deep Unpruned Turn-1 Audit (K=128)";
    }
    if ($("lbl-ll-vault-btn")) $("lbl-ll-vault-btn").textContent = isEs ? "Matchup Vault" : "Matchup Vault";
    if ($("lbl-ll-vault-title")) {
      $("lbl-ll-vault-title").textContent = isEs
        ? "📚 Matchup Vault — Simulaciones 90×90 Guardadas (DuckDB)"
        : "📚 Matchup Vault — Saved 90×90 Sweeps (DuckDB)";
    }
    if ($("ll-vault-search")) {
      $("ll-vault-search").placeholder = isEs
        ? "Buscar por Pokémon, nombre de equipo o etiqueta (ej. Incineroar, Regional)..."
        : "Search by Pokémon, team name, or tag (e.g. Incineroar, Regional)...";
    }
    if ($("btn-ll-adv-all")) $("btn-ll-adv-all").textContent = isEs ? "Todos" : "All";
    if ($("btn-ll-adv-win")) $("btn-ll-adv-win").textContent = isEs ? "+ Ventaja" : "+ Advantage";
    if ($("btn-ll-adv-even")) $("btn-ll-adv-even").textContent = isEs ? "Parejo" : "Even";
    if ($("btn-ll-adv-lose")) $("btn-ll-adv-lose").textContent = isEs ? "- Desventaja" : "- Disadvantage";
    renderLeadLabCacheHitBar();
    renderLeadLabVaultT1Select();
    if (state.leadLab.vaultOpen) renderLeadLabVaultList();
    updateLegalFooterAndModalCopy();
    if ($("btn-prep-back")) {
      $("btn-prep-back").textContent = isEs ? "← Volver al Hub" : "← Back to Hub";
    }
    if ($("lbl-prep-heading")) {
      $("lbl-prep-heading").textContent = isEs
        ? "Herramientas Prep Offline (Cero IA)"
        : "Offline Mobile Prep Tools (Zero-AI)";
    }
    if ($("btn-prep-kind-speed")) {
      $("btn-prep-kind-speed").textContent = isEs ? "⚡ Velocidades" : "⚡ Speed Tiers";
    }
    if ($("btn-prep-kind-damage")) {
      $("btn-prep-kind-damage").textContent = isEs ? "💥 Matriz de Daño" : "💥 Damage & KO Matrix";
    }
    if ($("btn-prep-toggle-paste")) {
      $("btn-prep-toggle-paste").textContent = state.prep.usePaste
        ? (isEs ? "Usar DuckDB" : "Use Saved Roster")
        : (isEs ? "Pegar 66-SP" : "Paste 66-SP");
    }
    if ($("lbl-prep-generate")) {
      $("lbl-prep-generate").textContent = state.prep.generating
        ? (isEs ? "Calculando..." : "Computing...")
        : (isEs ? "Generar" : "Generate");
    }
    if ($("lbl-nav-md-scout")) $("lbl-nav-md-scout").textContent = "Reg M-D";
    if ($("lbl-cta6-badge")) {
      $("lbl-cta6-badge").textContent = isEs ? "PREVIEW M-D · HTML BASE64 OFFLINE" : "REG M-D PREVIEW · OFFLINE BASE64";
    }
    if ($("lbl-cta6-title")) {
      $("lbl-cta6-title").textContent = isEs ? "Scout del Meta Regulation M-D" : "Regulation M-D Meta Scout";
    }
    if ($("lbl-cta6-desc")) {
      $("lbl-cta6-desc").textContent = isEs
        ? "Tier List proyectada combinando los añadidos oficiales confirmados de Regulation M-D y la ola de pronóstico comunitario, cruzados contra equipos reales Top Cut de DuckDB (incl. LAIC 2027)."
        : "Projected Tier List combining confirmed Regulation M-D additions and the community forecast wave, cross-referenced against real DuckDB Top Cut teams (incl. LAIC 2027).";
    }
    if ($("lbl-cta6-meta")) {
      $("lbl-cta6-meta").textContent = isEs
        ? "Confirmados vs. Rumor · 6 Blueprints DuckDB · 1-Click HTML"
        : "Confirmed vs. Rumored · 6 DuckDB Blueprints · 1-Click HTML";
    }
    if ($("btn-md-scout-back")) $("btn-md-scout-back").textContent = isEs ? "← Volver al Hub" : "← Back to Hub";
    if ($("lbl-md-scout-heading")) {
      $("lbl-md-scout-heading").textContent = isEs
        ? "🔮 Scout del Meta Regulation M-D (HTML Offline Base64)"
        : "🔮 Regulation M-D Meta Scout (Offline Base64 HTML)";
    }
    if ($("lbl-md-scout-download")) {
      $("lbl-md-scout-download").textContent = isEs ? "⬇ Descargar HTML Offline" : "⬇ Download Offline HTML";
    }
    if ($("lbl-prep-download")) {
      $("lbl-prep-download").textContent = isEs
        ? "⬇ Descargar HTML Offline"
        : "⬇ Download Offline HTML";
    }
    if ($("lbl-prep-paste-hint")) {
      $("lbl-prep-paste-hint").textContent = isEs
        ? "Pega cualquier Showdown Paste Reg M-C (66-SP o OTS)"
        : "Paste any Regulation M-C 66-SP or OTS Showdown team";
    }
    if ($("prep-paste-name")) {
      $("prep-paste-name").placeholder = isEs
        ? "Nombre del equipo (ej. Rain Archaludon Reg M-C)"
        : "Team display name (e.g. Rain Archaludon Reg M-C)";
    }
    if ($("lbl-prep-empty-title")) {
      $("lbl-prep-empty-title").textContent = isEs
        ? "Generador Instantáneo de Tablas Móviles Offline"
        : "Instant Offline Mobile Prep Generator";
    }
    if ($("lbl-prep-empty-sub")) {
      $("lbl-prep-empty-sub").textContent = isEs
        ? "Calcula Velocidades Lv.50 (31 IVs) y Matrices de Daño con 16 rolls exactos de Smogon Champions (5 Climas × 5 Campos) sin suscripción de IA y descárgalos en un solo HTML Base64 para tu teléfono."
        : "Compute exact Lv.50 31-IV Speed Tiers and Smogon Champions 16-roll Damage Matrices (all 5 Weathers × 5 Terrains) with zero AI subscription and download a single-file Base64 HTML for your phone.";
    }
    if ($("lbl-analytics-modal-title")) {
      $("lbl-analytics-modal-title").textContent = isEs
        ? "📊 Analítica de Sesiones y Torneos Bo3"
        : "📊 Bo3 Session & Tournament Analytics";
    }
    if ($("lbl-analytics-sub")) {
      $("lbl-analytics-sub").textContent = isEs
        ? "Registra tus partidas por carpeta de equipo en data/telemetry/ y detecta tendencias de precisión, leads y errores por fase."
        : "Log audited replays by team folder in data/telemetry/ to track Win Rate, accuracy trends, lead performance, and phase mistakes.";
    }
    if ($("analytics-new-team-input")) {
      $("analytics-new-team-input").placeholder = isEs
        ? "Nueva carpeta (ej. mi_equipo_v1)"
        : "New folder (e.g. my_team_v1)";
    }
    if ($("btn-analytics-create-team")) $("btn-analytics-create-team").textContent = isEs ? "+ Crear" : "+ Create";
    if ($("btn-analytics-toggle-guide")) $("btn-analytics-toggle-guide").textContent = isEs ? "? Cómo funciona" : "? How it works";
    if ($("btn-analytics-hide-guide")) $("btn-analytics-hide-guide").textContent = isEs ? "Ocultar" : "Hide";
    if ($("lbl-analytics-guide-title")) {
      $("lbl-analytics-guide-title").textContent = isEs
        ? "🧭 Guía Rápida: Cómo usar Analítica y Telemetría de Sesiones"
        : "🧭 Quick Walkthrough: How Session Analytics & Telemetry Work";
    }
    if ($("btn-analytics-go-bo3")) {
      $("btn-analytics-go-bo3").textContent = isEs ? "🧠 Ir a Bo3 Replay Coach →" : "🧠 Open Bo3 Replay Coach →";
    }
    if ($("lbl-analytics-storage-note")) {
      $("lbl-analytics-storage-note").textContent = isEs
        ? "Los CSVs se guardan 100% localmente en data/telemetry/<equipo>/battles_telemetry.csv (sin nube)."
        : "CSVs are stored 100% locally in data/telemetry/<team>/battles_telemetry.csv (no cloud upload).";
    }
    if ($("btn-refresh-analytics")) {
      $("btn-refresh-analytics").textContent = isEs ? "Actualizar" : "Refresh";
    }
    renderAnalyticsGuideSteps();
    if (state.activeStep === "analytics") {
      loadAndRenderAnalytics();
    }
    if ($("lbl-bug-btn")) $("lbl-bug-btn").textContent = isEs ? "Reportar Bug" : "Report Bug";
    if ($("btn-open-bug-modal")) {
      const bugTip = isEs ? "Reportar Bug / Log Diagnóstico" : "Report Bug / Diagnostic Log";
      $("btn-open-bug-modal").title = bugTip;
      $("btn-open-bug-modal").setAttribute("aria-label", bugTip);
    }
    $("lbl-bug-modal-title").textContent = isEs
      ? "Reportar Bug / Generar Log Diagnóstico"
      : "Report Bug / Generate Diagnostic Log";
    $("lbl-bug-modal-desc").textContent = isEs
      ? "Describe qué ocurrió o qué turno se ve extraño. Se incluirá automáticamente el estado del turno, hardware, replay y últimos logs del Tensor Core."
      : "Describe what went wrong or which turn looks off. Hardware, replay context, active turn verdict, and recent Tensor Core logs are attached automatically.";
    $("bug-user-message").placeholder = isEs
      ? "Ej. En el Turno 5 bajo Sol el motor recomendó una jugada inesperada..."
      : "e.g. On Turn 5 in Sun the engine recommended an unexpected line...";
    $("btn-generate-bug-log").textContent = isEs ? "Generar Bug Log" : "Generate Bug Log";
    $("link-email-bug-log").textContent = isEs
      ? "Enviar correo a esquedevil94@gmail.com"
      : "Email esquedevil94@gmail.com";
    $("btn-download-bug-log").textContent = isEs ? "Descargar .md" : "Download .md";
    $("btn-copy-bug-log").textContent = isEs ? "Copiar" : "Copy";

    updateKOptions();
    renderBo3GameTabs();
    renderSavedTeamsList("t1");
    renderSavedTeamsList("t2");
    populatePrepRosterSelect();
    renderOtsMonGrid("t1-ots-mon-grid", "t1-sp-status", state.t1Validation);
    if (state.t2Inference) {
      renderClampedSpPanel();
    } else {
      renderOtsMonGrid("t2-ots-mon-grid", "t2-sp-status", state.t2Validation);
    }
    renderPipelineLogs();
    if (state.matchSummary) {
      renderMatchSummaryUI(state.matchSummary);
    }
    if (state.turnResults[state.currentTurn]) {
      renderTurnPanel(state.turnResults[state.currentTurn]);
    }
    renderTimeline();
    updateLeadLabControlsUI();
    if (state.leadLab.t2Inference) {
      renderLeadLabClampedSpPanel();
    }
    if (state.leadLab.result) {
      renderLeadLabPodium(state.leadLab.result);
      renderLeadLabDrilldown();
    }
  }

  // -------------------------------------------------------------------------
  // Step 1: Searchable Saved Teams Picker + Safe Clear vs Confirmed DB Delete
  // -------------------------------------------------------------------------
  function computeReplayOverlap(roster, side) {
    if (!state.previewData) return 0;
    const prevList =
      side === "t1" ? state.previewData.trainer_1_preview : state.previewData.trainer_2_preview;
    if (!prevList || !prevList.length) return 0;
    const prevSet = new Set(prevList.map((m) => normStr(m.species)));
    let hits = 0;
    (roster.species || []).forEach((sp) => {
      const n = normStr(sp);
      if (prevSet.has(n)) hits += 1;
    });
    return hits;
  }

  function renderSavedTeamsList(side) {
    const box = $(`${side}-saved-teams`);
    if (!box) return;
    const isEs = state.lang === "es";
    const rosters = (state.app && state.app.rosters) || [];
    const rawQ = (state.searchQuery[side] || "").trim().toLowerCase();
    const tokens = rawQ ? rawQ.split(/\s+/).filter(Boolean) : [];

    // Filter by multi-token match across display_name, trainer_hint, and all 6 Pokémon species
    const filtered = rosters
      .map((r) => ({ roster: r, overlap: computeReplayOverlap(r, side) }))
      .filter(({ roster }) => {
        if (!tokens.length) return true;
        const haystack = [
          roster.display_name || "",
          roster.trainer_hint || "",
          ...(roster.species || []),
        ]
          .join(" ")
          .toLowerCase();
        return tokens.every((tok) => haystack.includes(tok));
      })
      .sort((a, b) => b.overlap - a.overlap);

    if (!filtered.length) {
      box.innerHTML = `<div class="muted-xs" style="padding:6px 8px">${
        rosters.length
          ? (isEs ? "Ningún equipo guardado coincide con ese filtro." : "No saved team matches that filter.")
          : (isEs ? "No hay equipos guardados aún. Usa 'Pegar OTS' para añadir uno." : "No saved teams yet. Click 'Paste OTS' to add one.")
      }</div>`;
      return;
    }

    const delLabel = isEs ? "Eliminar" : "Delete";
    const delTitle = isEs ? "Eliminar permanentemente de DuckDB" : "Permanently delete from DuckDB";

    box.innerHTML = filtered
      .map(({ roster, overlap }) => {
        const isSel = state.selectedRosterId[side] === roster.roster_id;
        const spIcons = (roster.species_sprites || [])
          .map((m) =>
            m.sprite_url
              ? `<img class="mini-sprite" src="${escapeHtml(m.sprite_url)}" title="${escapeHtml(m.species)}" alt="${escapeHtml(m.species)}" loading="lazy" />`
              : `<span class="muted-xs">${escapeHtml(m.species)}</span>`
          )
          .join("");
        const overlapHtml =
          overlap > 0
            ? `<span class="match-badge">${overlap}/6 ${isEs ? "match" : "match"}</span>`
            : "";
        return `<div class="saved-team-item ${isSel ? "selected" : ""}" data-select-side="${side}" data-roster-id="${escapeHtml(roster.roster_id)}">
          <div class="saved-team-main">
            <div class="saved-team-name">${escapeHtml(roster.display_name)}${overlapHtml}</div>
            <div class="saved-team-sprites">${spIcons}</div>
          </div>
          <button class="btn-db-del" type="button" data-delete-side="${side}" data-roster-id="${escapeHtml(roster.roster_id)}" data-roster-name="${escapeHtml(roster.display_name)}" title="${delTitle}">${delLabel}</button>
        </div>`;
      })
      .join("");

    // Wire click-to-select team
    box.querySelectorAll("[data-select-side]").forEach((row) => {
      row.addEventListener("click", (ev) => {
        if (ev.target && ev.target.closest("[data-delete-side]")) return;
        const rid = row.dataset.rosterId;
        selectSavedRoster(side, rid);
      });
    });

    // Wire explicit confirmed DB delete (which ALSO clears active selection & sprites if selected!)
    box.querySelectorAll("[data-delete-side]").forEach((btn) => {
      btn.addEventListener("click", async (ev) => {
        ev.stopPropagation();
        const rid = btn.dataset.rosterId;
        const rname = btn.dataset.rosterName || rid;
        const confirmMsg = isEs
          ? `¿Eliminar permanentemente "${rname}" de tu base de datos DuckDB?`
          : `Permanently delete "${rname}" from your DuckDB database?`;
        if (!window.confirm(confirmMsg)) return;

        const res = await fetch("/api/rosters/delete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ roster_id: rid }),
        });
        const d = await res.json();
        if (d.rosters && state.app) {
          state.app.rosters = d.rosters;
          // Clear whichever card(s) had this deleted roster loaded!
          ["t1", "t2"].forEach((s) => {
            if (state.selectedRosterId[s] === rid) {
              clearSideSelection(s);
            } else {
              renderSavedTeamsList(s);
            }
          });
        }
      });
    });
  }

  function selectSavedRoster(side, rosterId) {
    const rosters = (state.app && state.app.rosters) || [];
    const found = rosters.find((r) => r.roster_id === rosterId);
    if (!found) return;
    state.selectedRosterId[side] = found.roster_id;
    $(`${side}-paste-input`).value = found.paste_text;
    $(`${side}-paste-drawer`).style.display = "none";
    if (side === "t2") {
      state.t2Inference = null;
      state.t2UserSpreads = {};
      if ($("t2-clamped-sp-panel")) $("t2-clamped-sp-panel").style.display = "none";
      if ($("t2-ots-mon-grid")) $("t2-ots-mon-grid").style.display = "flex";
    }
    renderSavedTeamsList(side);
    validateAndRenderSide(side, found.paste_text);
  }

  function clearSideSelection(side) {
    state.selectedRosterId[side] = null;
    $(`${side}-paste-input`).value = "";
    if (side === "t1") {
      state.t1Validation = null;
    } else {
      state.t2Validation = null;
      state.t2Inference = null;
      state.t2UserSpreads = {};
      if ($("t2-clamped-sp-panel")) $("t2-clamped-sp-panel").style.display = "none";
      if ($("t2-ots-mon-grid")) $("t2-ots-mon-grid").style.display = "flex";
    }
    renderSavedTeamsList(side);
    renderOtsMonGrid(`${side}-ots-mon-grid`, `${side}-sp-status`, null);
  }

  // -------------------------------------------------------------------------
  // Bo3 Game Switcher & Ephemeral Clamped 66-SP Slider Workbench
  // -------------------------------------------------------------------------
  function renderBo3GameTabs() {
    const isEs = state.lang === "es";
    // Source of truth: in Step 1 (setup), ALWAYS render freshly staged `state.bo3GamesMeta`
    // so a previously analyzed 2-game match in `state.app.bo3_games` never hides a new 3-game upload!
    const setupGames = state.bo3GamesMeta || [];
    const activeGames =
      (state.app && state.app.bo3_games && state.app.bo3_games.length
        ? state.app.bo3_games
        : setupGames) || [];

    // 1. Setup Queue Strip: always visible when >= 1 game is loaded, with +Agregar Juego (up to 3), × remove, & Limpiar
    const setupEl = $("setup-bo3-tabs");
    if (setupEl) {
      if (!setupGames.length) {
        setupEl.style.display = "none";
        setupEl.innerHTML = "";
      } else {
        const canAddMore = state.bo3Replays.length < 3 && state.rawReplayText !== "__SAMPLE__";
        const chipsHtml = setupGames
          .map((g, idx) => {
            const isAct = idx === state.activeGameIndex;
            const resCls = g.is_t1_win ? "win" : g.winner ? "loss" : "unk";
            const resTxt = g.is_t1_win ? "W" : g.winner ? "L" : "—";
            const lbl = isEs ? `Juego ${g.game_index}` : `Game ${g.game_index}`;
            const rmBtn =
              state.bo3Replays.length > 0
                ? `<button type="button" class="bo3-remove-x" data-bo3-remove="${idx}" title="${isEs ? "Quitar este juego" : "Remove this game"}">&times;</button>`
                : "";
            return `<span class="bo3-chip-wrap">
              <button type="button" class="bo3-tab-btn ${isAct ? "active" : ""}" data-bo3-idx="${idx}" title="${escapeHtml(g.filename || lbl)}">
                <span>${lbl}</span>
                <span class="bo3-res-dot ${resCls}">${resTxt}</span>
                <span class="muted-xs">${g.num_turns}t</span>
              </button>
              ${rmBtn}
            </span>`;
          })
          .join("");
        const addBtnHtml = canAddMore
          ? `<button type="button" class="btn btn-greatball btn-xs" id="btn-bo3-add-game">+ ${
              isEs ? `Agregar Juego (${setupGames.length}/3)` : `Add Game (${setupGames.length}/3)`
            }</button>`
          : `<span class="cyber-pill cyan-pill">${isEs ? "Serie completa (3/3)" : "Full Bo3 (3/3)"}</span>`;
        const clearBtnHtml = `<button type="button" class="btn btn-ghost btn-xs" id="btn-bo3-clear-series">${
          isEs ? "Limpiar serie" : "Clear series"
        }</button>`;
        setupEl.style.display = "flex";
        setupEl.innerHTML = `${chipsHtml}<span class="bo3-queue-actions">${addBtnHtml}${clearBtnHtml}</span>`;
        setupEl.querySelectorAll("[data-bo3-idx]").forEach((btn) => {
          btn.addEventListener("click", () => switchBo3Game(parseInt(btn.dataset.bo3Idx, 10)));
        });
        setupEl.querySelectorAll("[data-bo3-remove]").forEach((btn) => {
          btn.addEventListener("click", () => removeBo3ReplayAt(parseInt(btn.dataset.bo3Remove, 10)));
        });
        const addBtn = $("btn-bo3-add-game");
        if (addBtn) {
          addBtn.addEventListener("click", () => {
            const inp = $("replay-add-file-input");
            if (inp) inp.click();
          });
        }
        const clrBtn = $("btn-bo3-clear-series");
        if (clrBtn) {
          clrBtn.addEventListener("click", () => clearBo3Series());
        }
      }
    }

    // 2. Pipeline & Review Game Switcher Tabs
    const runContainers = [$("pipeline-bo3-tabs"), $("review-bo3-tabs")];
    if (activeGames.length <= 1) {
      runContainers.forEach((el) => {
        if (el) {
          el.style.display = "none";
          el.innerHTML = "";
        }
      });
      return;
    }

    const html = activeGames
      .map((g, idx) => {
        const isAct = idx === state.activeGameIndex;
        const resCls = g.is_t1_win ? "win" : g.winner ? "loss" : "unk";
        const resTxt = g.is_t1_win ? "W" : g.winner ? "L" : "—";
        const lbl = isEs ? `Juego ${g.game_index}` : `Game ${g.game_index}`;
        return `<button type="button" class="bo3-tab-btn ${isAct ? "active" : ""}" data-bo3-idx="${idx}" title="${escapeHtml(g.filename || lbl)}">
          <span>${lbl}</span>
          <span class="bo3-res-dot ${resCls}">${resTxt}</span>
          <span class="muted-xs">${g.num_turns}t</span>
        </button>`;
      })
      .join("");

    runContainers.forEach((el) => {
      if (!el) return;
      el.style.display = el.classList.contains("bo3-tabs-inline") ? "inline-flex" : "flex";
      el.innerHTML = html;
      el.querySelectorAll("[data-bo3-idx]").forEach((btn) => {
        btn.addEventListener("click", () => switchBo3Game(parseInt(btn.dataset.bo3Idx, 10)));
      });
    });
  }

  function clearBo3Series() {
    state.bo3Replays = [];
    state.bo3GamesMeta = [];
    state.rawReplayText = "";
    state.previewData = null;
    state.activeGameIndex = 0;
    state.bo3TurnCache = {};
    state.t2Inference = null;
    state.t2UserSpreads = {};
    if (state.app) state.app.bo3_games = [];
    if ($("replay-dropzone")) $("replay-dropzone").style.display = "block";
    if ($("detected-match-bar")) $("detected-match-bar").style.display = "none";
    if ($("btn-launch-analysis")) $("btn-launch-analysis").disabled = true;
    renderBo3GameTabs();
    if ($("setup-status-msg")) {
      $("setup-status-msg").textContent =
        state.lang === "es"
          ? "Serie limpiada. Arrastra o selecciona 1 a 3 replays (.html, .log, .txt)."
          : "Series cleared. Drop or select 1 to 3 replay files (.html, .log, .txt).";
    }
  }

  async function removeBo3ReplayAt(idx) {
    if (!state.bo3Replays.length || idx < 0 || idx >= state.bo3Replays.length) return;
    const remaining = state.bo3Replays.filter((_, i) => i !== idx);
    if (!remaining.length) {
      clearBo3Series();
      return;
    }
    const pov = ($("setup-pov-select") && $("setup-pov-select").value) || null;
    await handleBo3ReplayFiles(remaining, false, pov);
  }

  async function switchBo3Game(targetIdx) {
    if (targetIdx === state.activeGameIndex) return;
    if (state.activeStep === "setup" || !state.app || !state.app.bo3_games || !state.app.bo3_games.length) {
      state.activeGameIndex = targetIdx;
      const g = state.bo3GamesMeta[targetIdx];
      if (g && $("detected-turns-label")) {
        $("detected-turns-label").textContent = `${g.num_turns} ${state.lang === "es" ? "turnos" : "turns"}`;
      }
      renderBo3GameTabs();
      return;
    }

    // Save current game's computed turn results into client Bo3 cache
    state.bo3TurnCache[state.activeGameIndex] = {
      turnResults: state.turnResults,
      pipelineLogs: state.pipelineLogs,
      matchSummary: state.matchSummary,
      currentTurn: state.currentTurn,
      autoPausedTurns: state.autoPausedTurns,
    };

    if (state.activeStream) {
      await cancelActiveStream();
    }

    const res = await fetch("/api/bo3/select-game", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ game_index: targetIdx }),
    });
    const summary = await res.json();
    if (summary.error) {
      $("setup-status-msg").textContent = `Error: ${summary.error}`;
      return;
    }

    state.app = summary;
    state.activeGameIndex = summary.active_game_index || 0;
    const cached = state.bo3TurnCache[state.activeGameIndex];
    if (cached) {
      state.turnResults = cached.turnResults || {};
      state.pipelineLogs = cached.pipelineLogs || [];
      state.matchSummary = cached.matchSummary || null;
      state.currentTurn = cached.currentTurn || 1;
      state.autoPausedTurns = cached.autoPausedTurns || {};
    } else {
      state.turnResults = {};
      state.pipelineLogs = [];
      state.matchSummary = null;
      state.currentTurn = 1;
      state.autoPausedTurns = {};
    }

    renderBo3GameTabs();
    updateReviewHeaderMeta();
    $("showdown-iframe").src = `/api/replay-player?ts=${Date.now()}`;
    renderPipelineLogs();
    renderTimeline();

    if (cached && Object.keys(cached.turnResults || {}).length >= (summary.replay ? summary.replay.num_turns : 1)) {
      if (cached.matchSummary) renderMatchSummaryUI(cached.matchSummary);
      if (state.activeStep === "review") {
        selectTurn(state.currentTurn || 1, true, false);
      }
    } else if (state.activeStep === "pipeline" || state.activeStep === "review") {
      setStep("pipeline");
      openPipelineStream(1);
    }
  }

  function updateClampedStatusBadge() {
    const statusEl = $("t2-sp-status");
    const inf = state.t2Inference;
    if (!statusEl || !inf || !inf.pokemon) return;
    const isEs = state.lang === "es";
    let allComplete = true;
    let remainingTotal = 0;
    inf.pokemon.forEach((m) => {
      const sp = state.t2UserSpreads[m.base_species] || m.default_spread || {};
      const sum = STAT_KEYS.reduce((acc, k) => acc + Number(sp[k] || 0), 0);
      if (sum !== 66) {
        allComplete = false;
        remainingTotal += Math.max(0, 66 - sum);
      }
    });
    if (allComplete) {
      statusEl.className = "sp-status ok";
      statusEl.textContent = isEs
        ? `${inf.pokemon.length} Pokémon · 66-SP Resuelto`
        : `${inf.pokemon.length} Pokémon · 66-SP Solved`;
    } else {
      statusEl.className = "sp-status warn";
      statusEl.textContent = isEs
        ? `Faltan ${remainingTotal} SP por asignar`
        : `${remainingTotal} SP left to assign`;
    }
  }

  function renderClampedSpPanel() {
    const panel = $("t2-clamped-sp-panel");
    const grid = $("t2-ots-mon-grid");
    const list = $("t2-clamped-sp-list");
    const inf = state.t2Inference;
    if (!panel || !list) return;

    if (!inf || !inf.pokemon || !inf.pokemon.length) {
      panel.style.display = "none";
      if (grid) grid.style.display = "flex";
      return;
    }

    const isEs = state.lang === "es";
    panel.style.display = "block";
    if (grid) grid.style.display = "none";

    const gLbl = inf.games_pooled > 1 ? `Bo3 (${inf.games_pooled}G)` : "Bo1 (1G)";
    if ($("t2-solver-meta-badge")) {
      $("t2-solver-meta-badge").textContent = `${gLbl} · OTS 66-SP`;
    }
    if ($("t2-solver-meta-sub")) {
      $("t2-solver-meta-sub").textContent = `${inf.total_smogon_calcs} calcs · ${inf.elapsed_ms}ms`;
    }

    list.innerHTML = inf.pokemon
      .map((m, mIdx) => {
        const spObj = state.t2UserSpreads[m.base_species] || Object.assign({}, m.default_spread);
        state.t2UserSpreads[m.base_species] = spObj;
        const totSp = STAT_KEYS.reduce((a, k) => a + Number(spObj[k] || 0), 0);
        const remSp = 66 - totSp;
        const budCls = remSp === 0 ? "ok" : "warn";
        const budTxt = remSp === 0 ? "66 / 66 SP" : isEs ? `${totSp}/66 (Faltan ${remSp})` : `${totSp}/66 (${remSp} left)`;

        const rowsHtml = STAT_KEYS.map((sk) => {
          const b = (m.bounds && m.bounds[sk]) || { min_sp: 0, max_sp: 32, locked: false, status: "unobserved", evidence: [] };
          const curVal = Number(spObj[sk] || 0);
          const l50 = calcChampionsL50Stat(sk, (m.base_stats || {})[sk], curVal, m.nature);
          const natDelta = getNatureDelta(m.nature, sk);
          const natCls = natDelta > 0 ? "nat-up" : natDelta < 0 ? "nat-down" : "";
          const natMark = natDelta > 0 ? "+" : natDelta < 0 ? "-" : "";

          let pillTxt = "";
          if (b.locked) pillTxt = `🔒 ${b.min_sp}`;
          else if (b.status === "bounded") pillTxt = `${b.min_sp}..${b.max_sp}`;
          else pillTxt = isEs ? "Libre" : "Open";

          const evTooltip = (b.evidence && b.evidence.length)
            ? b.evidence.join("\n")
            : (isEs ? "Sin restricción directa en el replay — ajusta libremente dentro del presupuesto de 66 SP." : "No direct replay constraint — adjust freely within the 66-SP budget.");

          const leftPct = (b.min_sp / 32.0) * 100.0;
          const widthPct = b.locked ? 4.0 : Math.max(3.0, ((b.max_sp - b.min_sp) / 32.0) * 100.0);

          return `<div class="sp-stat-row">
            <span class="sp-stat-lbl ${natCls}">${STAT_LABELS[sk]}${natMark}</span>
            <span class="sp-bound-pill ${b.status}" title="${escapeHtml(evTooltip)}">${escapeHtml(pillTxt)}</span>
            <div class="sp-slider-wrap">
              <div class="sp-track-bg">
                <div class="sp-track-feasible ${b.locked ? "pinned" : ""}" style="left:${leftPct.toFixed(1)}%;width:${Math.min(100 - leftPct, widthPct).toFixed(1)}%"></div>
              </div>
              <input type="range" class="sp-range"
                min="0" max="32" step="1" value="${curVal}"
                data-mon-idx="${mIdx}" data-species="${escapeHtml(m.base_species)}" data-stat="${sk}"
                data-min-sp="${b.min_sp}" data-max-sp="${b.max_sp}"
                ${b.locked ? "disabled" : ""} />
            </div>
            <span class="sp-val-cell" id="sp-val-${mIdx}-${sk}">${curVal} SP</span>
            <span class="sp-l50-cell" id="sp-l50-${mIdx}-${sk}">(${l50})</span>
          </div>`;
        }).join("");

        return `<div class="sp-mon-card" data-sp-card="${mIdx}">
          <div class="sp-mon-head">
            <div class="sp-mon-head-left">
              ${spritePairHtml(m.sprite_url, m.item_sprite_url, m.base_species, m.item)}
              <div class="ots-row-info">
                <div class="ots-row-name">${escapeHtml(m.base_species)} <span class="muted-xs">· ${escapeHtml(m.nature || "")}</span></div>
                <div class="ots-row-sub">${escapeHtml(m.item || "No Item")} · ${escapeHtml(m.ability || "")} · ${escapeHtml((m.moves || []).join(", "))}</div>
              </div>
            </div>
            <div class="sp-mon-head-right">
              <span class="sp-budget-pill ${budCls}" id="sp-budget-${mIdx}">${budTxt}</span>
              <button type="button" class="btn btn-ghost btn-xs" data-reset-mon="${escapeHtml(m.base_species)}" title="${isEs ? "Restaurar spread sugerido dentro de los límites" : "Reset to suggested default spread within clamps"}">↺</button>
            </div>
          </div>
          <div class="sp-rows">${rowsHtml}</div>
        </div>`;
      })
      .join("");

    // Wire strict clamped slider input listeners (zero full DOM rebuild during drag)
    list.querySelectorAll(".sp-range").forEach((inp) => {
      inp.addEventListener("input", () => {
        const mIdx = parseInt(inp.dataset.monIdx, 10);
        const spName = inp.dataset.species;
        const sk = inp.dataset.stat;
        const minSp = parseInt(inp.dataset.minSp, 10);
        const maxSp = parseInt(inp.dataset.maxSp, 10);
        const mon = state.t2Inference.pokemon[mIdx];
        const curObj = state.t2UserSpreads[spName];
        if (!mon || !curObj) return;

        let rawV = parseInt(inp.value, 10);
        // 1. Strictly enforce deterministic inferred bounds [minSp, maxSp]
        let clamped = Math.max(minSp, Math.min(maxSp, rawV));
        // 2. Strictly enforce 66-SP total budget ceiling
        const otherSum = STAT_KEYS.reduce((a, k) => a + (k === sk ? 0 : Number(curObj[k] || 0)), 0);
        const budgetCap = Math.max(minSp, Math.min(maxSp, 66 - otherSum));
        clamped = Math.min(clamped, budgetCap);

        if (clamped !== rawV) {
          inp.value = String(clamped);
        }
        curObj[sk] = clamped;

        const l50 = calcChampionsL50Stat(sk, (mon.base_stats || {})[sk], clamped, mon.nature);
        const valCell = $(`sp-val-${mIdx}-${sk}`);
        const l50Cell = $(`sp-l50-${mIdx}-${sk}`);
        if (valCell) valCell.textContent = `${clamped} SP`;
        if (l50Cell) l50Cell.textContent = `(${l50})`;

        const totSp = STAT_KEYS.reduce((a, k) => a + Number(curObj[k] || 0), 0);
        const remSp = 66 - totSp;
        const bPill = $(`sp-budget-${mIdx}`);
        if (bPill) {
          bPill.className = `sp-budget-pill ${remSp === 0 ? "ok" : "warn"}`;
          bPill.textContent =
            remSp === 0
              ? "66 / 66 SP"
              : state.lang === "es"
                ? `${totSp}/66 (Faltan ${remSp})`
                : `${totSp}/66 (${remSp} left)`;
        }
        updateClampedStatusBadge();
      });
    });

    // Wire per-mon reset button
    list.querySelectorAll("[data-reset-mon]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const spName = btn.dataset.resetMon;
        const mon = state.t2Inference.pokemon.find((x) => x.base_species === spName);
        if (!mon) return;
        state.t2UserSpreads[spName] = Object.assign({}, mon.default_spread);
        renderClampedSpPanel();
      });
    });

    updateClampedStatusBadge();
  }

  async function runBo3OpponentInference(t2OtsPasteOverride) {
    const isEs = state.lang === "es";
    if (!state.bo3Replays.length && !state.rawReplayText) {
      $("setup-status-msg").textContent = isEs
        ? "Primero carga 1 a 3 replays para resolver el 66-SP rival."
        : "Load 1 to 3 replays first before solving opponent 66-SP.";
      return;
    }

    const btn = $("btn-t2-infer");
    const prevTxt = btn ? btn.textContent : "";
    if (btn) {
      btn.disabled = true;
      btn.textContent = isEs ? "Resolviendo..." : "Solving...";
    }
    try {
      const pov = $("setup-pov-select") ? $("setup-pov-select").value || null : null;
      const t1Paste = $("t1-paste-input") ? $("t1-paste-input").value || "" : "";
      const t2OtsPaste =
        t2OtsPasteOverride !== undefined
          ? t2OtsPasteOverride
          : ($("t2-paste-input") ? $("t2-paste-input").value || "" : "");

      const res = await fetch("/api/bo3/infer-sp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          replays: state.bo3Replays.length ? state.bo3Replays : null,
          use_sample: state.rawReplayText === "__SAMPLE__" && !state.bo3Replays.length,
          pov_trainer: pov,
          t1_roster_id: state.selectedRosterId.t1 || null,
          t1_paste_text: t1Paste || null,
          t2_ots_paste_text: t2OtsPaste || null,
        }),
      });
      const d = await res.json();
      if (!d.ok) {
        if (d.missing_ots) {
          $("t2-paste-drawer").style.display = "block";
          $("setup-status-msg").textContent = isEs
            ? "Este replay no incluye |showteam|. Pega el OTS sin EVs del rival (Especie, Objeto, Habilidad, Naturaleza, Movimientos) y pulsa Aplicar."
            : "This replay does not contain |showteam|. Paste the opponent's EV-less OTS (Species, Item, Ability, Nature, Moves) and click Apply.";
        } else {
          $("setup-status-msg").textContent = `Error: ${d.error || "66-SP solver failed"}`;
        }
        return;
      }

      state.selectedRosterId.t2 = null;
      state.t2Inference = d;
      state.t2UserSpreads = {};
      (d.pokemon || []).forEach((m) => {
        state.t2UserSpreads[m.base_species] = Object.assign({}, m.active_spread || m.default_spread);
      });
      state.t2Validation = d.validation || null;
      $("t2-paste-drawer").style.display = "none";
      renderSavedTeamsList("t2");
      renderClampedSpPanel();

      $("setup-status-msg").textContent = isEs
        ? `66-SP resuelto para ${d.trainer_2_name} (${d.games_pooled} partida(s) · ${d.total_smogon_calcs} calcs Smogon en ${d.elapsed_ms}ms). Ajusta los sliders si lo deseas y pulsa "Iniciar Análisis Tensor Core".`
        : `Solved 66-SP bounds for ${d.trainer_2_name} (${d.games_pooled} game(s) · ${d.total_smogon_calcs} Smogon calcs in ${d.elapsed_ms}ms). Adjust open SP sliders if desired and click "Run Tensor Core Analysis".`;
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = prevTxt || (isEs ? "Resolver 66-SP" : "Solve 66-SP");
      }
    }
  }

  function renderOtsMonGrid(containerId, statusId, validation) {
    const list = $(containerId);
    const statusEl = $(statusId);
    if (!list || !statusEl) return;
    if (!validation || !validation.pokemon || !validation.pokemon.length) {
      list.innerHTML = `<div class="ots-row"><span class="muted-sm">${
        state.lang === "es"
          ? "Ningún equipo seleccionado. Elige uno de la lista o usa 'Pegar OTS'."
          : "No team selected. Pick one above or click 'Paste OTS'."
      }</span></div>`;
      statusEl.className = "sp-status warn";
      statusEl.textContent = state.lang === "es" ? "Sin OTS" : "No OTS";
      return;
    }

    if (validation.valid) {
      statusEl.className = "sp-status ok";
      statusEl.textContent =
        validation.mode === "evless_ots"
          ? `${validation.count} Pokémon · OTS (0 SP)`
          : `${validation.count} Pokémon · 66-SP OK`;
    } else {
      statusEl.className = "sp-status warn";
      statusEl.textContent = `${validation.count} Pokémon · ${(validation.warnings || [])[0] || "SP"}`;
    }

    list.innerHTML = validation.pokemon
      .map((m) => {
        const spStr = Object.entries(m.spread || {})
          .filter(([, v]) => v > 0)
          .map(([k, v]) => `${v} ${k.toUpperCase()}`)
          .join(" / ");
        return `<div class="ots-row" title="${escapeHtml((m.moves || []).join(" · "))}\n${escapeHtml(m.nature || "")} (${escapeHtml(spStr)})">
          <div class="ots-row-left">
            ${spritePairHtml(m.sprite_url, m.item_sprite_url, m.species, m.item)}
            <div class="ots-row-info">
              <div class="ots-row-name">${escapeHtml(m.species)}</div>
              <div class="ots-row-sub">${escapeHtml(m.item || "No Item")} · ${escapeHtml(m.ability || "")} · ${escapeHtml((m.moves || []).join(", "))}</div>
            </div>
          </div>
          <div class="ots-row-right">
            <div class="ots-sp-tag">${m.total_sp} SP</div>
            <div class="muted-xs">${escapeHtml(m.nature || "")}</div>
          </div>
        </div>`;
      })
      .join("");
  }

  async function validateAndRenderSide(side, pasteText) {
    if (!pasteText || !pasteText.trim()) {
      if (side === "t1") state.t1Validation = null;
      else state.t2Validation = null;
      renderOtsMonGrid(`${side}-ots-mon-grid`, `${side}-sp-status`, null);
      return;
    }
    const res = await fetch("/api/rosters/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ paste_text: pasteText }),
    });
    const val = await res.json();
    if (side === "t1") state.t1Validation = val;
    else state.t2Validation = val;

    // If user pasted an EV-less OTS for trainer_2 while replays are loaded, auto-solve 66-SP bounds!
    if (
      side === "t2" &&
      val &&
      val.mode === "evless_ots" &&
      val.has_full_ots_metadata &&
      (state.bo3Replays.length > 0 || state.rawReplayText)
    ) {
      await runBo3OpponentInference(pasteText);
      return;
    }

    if (side === "t2") {
      state.t2Inference = null;
      state.t2UserSpreads = {};
      if ($("t2-clamped-sp-panel")) $("t2-clamped-sp-panel").style.display = "none";
      if ($("t2-ots-mon-grid")) $("t2-ots-mon-grid").style.display = "flex";
    }
    renderOtsMonGrid(`${side}-ots-mon-grid`, `${side}-sp-status`, val);
  }

  async function renderPreviewBanner(prev) {
    state.previewData = prev;
    state.bo3GamesMeta = prev.games || [];
    state.activeGameIndex = prev.active_game_index || 0;
    state.bo3TurnCache = {};
    if (state.app) {
      state.app.bo3_games = [];
    }
    state.t2Inference = null;
    state.t2UserSpreads = {};

    $("replay-dropzone").style.display = "none";
    $("raw-replay-box").style.display = "none";
    $("detected-match-bar").style.display = "flex";

    $("detected-format-badge").textContent = prev.format_name || "Regulation M-C";
    $("detected-players-label").textContent = `${prev.trainer_1_name} vs. ${prev.trainer_2_name}`;
    const gamesBadge = prev.games_count > 1 ? `Bo3 (${prev.games_count}G) · ` : "";
    $("detected-turns-label").textContent = `${gamesBadge}${prev.num_turns} ${state.lang === "es" ? "turnos" : "turns"}`;

    $("t1-card-title").textContent = `${prev.trainer_1_name} (trainer_1)`;
    $("t2-card-title").textContent = `${prev.trainer_2_name} (trainer_2)`;

    const povSel = $("setup-pov-select");
    povSel.innerHTML = "";
    [prev.trainer_1_name, prev.trainer_2_name].forEach((name, idx) => {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      if (idx === 0) opt.selected = true;
      povSel.appendChild(opt);
    });

    renderBo3GameTabs();

    if (prev.suggested_t1_roster_id) {
      selectSavedRoster("t1", prev.suggested_t1_roster_id);
    } else {
      renderSavedTeamsList("t1");
    }

    $("btn-launch-analysis").disabled = false;

    // Auto-run Zero-AI Clamped 66-SP Solver whenever |showteam| OTS is present in the replay(s)!
    if (prev.has_showteam_ots) {
      $("t2-paste-input").value = prev.trainer_2_evless_ots_paste || "";
      renderSavedTeamsList("t2");
      await runBo3OpponentInference(prev.trainer_2_evless_ots_paste || "");
      return;
    }

    if (prev.suggested_t2_roster_id) {
      selectSavedRoster("t2", prev.suggested_t2_roster_id);
    } else {
      renderSavedTeamsList("t2");
      renderOtsMonGrid("t2-ots-mon-grid", "t2-sp-status", null);
    }

    $("setup-status-msg").textContent =
      state.lang === "es"
        ? `Replay detectado (${prev.num_turns} turnos). Selecciona tu equipo y pega el OTS del rival o elige uno guardado.`
        : `Replay ready (${prev.num_turns} turns). Confirm your 66-SP roster and paste the opponent's OTS or pick a saved sheet.`;
  }

  async function handleBo3ReplayFiles(replayItems, useSample, povOverride) {
    if (!useSample && (!replayItems || !replayItems.length)) return;
    if (useSample) {
      state.bo3Replays = [];
      state.rawReplayText = "__SAMPLE__";
    } else {
      state.bo3Replays = replayItems.slice(0, 3);
      state.rawReplayText = state.bo3Replays[0].raw_input;
    }

    const res = await fetch("/api/bo3/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        replays: state.bo3Replays,
        use_sample: !!useSample,
        pov_trainer: povOverride || null,
      }),
    });
    const data = await res.json();
    if (data.error) {
      $("setup-status-msg").textContent = `Error: ${data.error}`;
      return;
    }
    // Sync client replay array with exact backend chronological order (Game 1 -> Game 2 -> Game 3)
    if (
      !useSample &&
      Array.isArray(data.sorted_order) &&
      data.sorted_order.length === state.bo3Replays.length
    ) {
      const reordered = data.sorted_order
        .map((origIdx) => state.bo3Replays[origIdx])
        .filter(Boolean);
      if (reordered.length === state.bo3Replays.length) {
        state.bo3Replays = reordered;
        state.rawReplayText = state.bo3Replays[0].raw_input;
      }
    }
    await renderPreviewBanner(data);
  }

  async function handleReplayInput(rawText, useSample, povOverride) {
    if (useSample) {
      return handleBo3ReplayFiles([], true, povOverride);
    }
    if (!rawText || !rawText.trim()) return;
    return handleBo3ReplayFiles([{ filename: "Game 1", raw_input: rawText }], false, povOverride);
  }

  // -------------------------------------------------------------------------
  // Step 2: Live Pipeline Console & Real Server-Side Cancellation
  // -------------------------------------------------------------------------
  function workerHardwareClass(workerLabel) {
    const w = String(workerLabel || "").toUpperCase();
    if (w.startsWith("GPU")) return "hw-gpu";
    if (w.startsWith("CPU")) return "hw-cpu";
    return "hw-balancer";
  }

  function renderLiveWorkersStrip(activeWorkers) {
    const strip = $("live-workers-strip");
    if (!strip) return;
    if (!activeWorkers || !activeWorkers.length) {
      strip.style.display = "none";
      strip.innerHTML = "";
      return;
    }
    strip.style.display = "flex";
    const isEs = state.lang === "es";
    strip.innerHTML = activeWorkers
      .map((w) => {
        const cls = workerHardwareClass(w.worker);
        const doneCls = w.state === "idle" || w.state === "done_turn" ? "hw-done" : "";
        const hwShort = w.hardware_device ? ` · ${w.hardware_device}` : "";
        const statusTxt =
          w.state === "idle"
            ? (isEs ? `T${w.turn} ✓` : `T${w.turn} ✓`)
            : `T${w.turn} · ${w.phase || "SIM"} ${Number(w.pct || 0)}%`;
        return `<span class="worker-chip ${cls} ${doneCls}"><strong>${escapeHtml(w.worker)}</strong><span>${escapeHtml(hwShort)}</span><span>→ ${escapeHtml(statusTxt)}</span></span>`;
      })
      .join("");
  }

  function renderPipelineLogs() {
    const feed = $("pipeline-log-feed");
    if (!feed) return;
    const pk = profileKey();
    const isEs = state.lang === "es";

    if (state.activeStream && (!state.pipelineLogs || !state.pipelineLogs.length)) {
      feed.innerHTML = `<div class="log-waiting-banner">${
        isEs
          ? "⚙️ Trabajadores GPU + CPU ejecutando cada turno una sola vez en paralelo. Esperando a que terminen todos los hilos para reconstruir y mostrar el log completo en orden (Turno 1 → N) con etiqueta de hardware..."
          : "⚙️ GPU + CPU workers are computing each turn strictly once in parallel. Waiting for all workers to finish before reconstructing and displaying the complete ordered log (Turn 1 → N) with hardware tags..."
      }</div>`;
      return;
    }

    // Group strictly by turn (0 = scheduler summary first, then Turn 1 -> N ascending) so turn headers NEVER repeat
    const orderedEntries = [...(state.pipelineLogs || [])].sort((a, b) => {
      const ta = Number(a.turn || 0);
      const tb = Number(b.turn || 0);
      if (ta !== tb) return ta - tb;
      return 0;
    });

    let html = "";
    let lastTurn = -1;

    orderedEntries.forEach((entry) => {
      const tNum = Number(entry.turn || 0);
      const wLbl = String(entry.compute_worker || "BALANCER");
      const hwDev = String(entry.hardware_device || "");
      const hwCls = workerHardwareClass(wLbl);

      if (tNum > 0 && tNum !== lastTurn) {
        lastTurn = tNum;
        const hwBadgeTxt = hwDev ? `${wLbl} · ${hwDev}` : wLbl;
        html += `<div class="log-turn-header">
          <span>${isEs ? `Turno ${tNum}` : `Turn ${tNum}`}</span>
          <span class="log-hw-badge ${hwCls}">${escapeHtml(hwBadgeTxt)}</span>
        </div>`;
      }
      const msg = (entry.messages && (entry.messages[pk] || entry.messages.es_vgc)) || entry.error || "";
      html += `<div class="log-line">
        <span class="log-hw-badge ${hwCls}">${escapeHtml(wLbl)}</span>
        <span class="log-phase ${escapeHtml(entry.phase)}">${escapeHtml(entry.phase)}</span>
        <span>${escapeHtml(msg)}</span>
      </div>`;
    });

    feed.innerHTML = html;
    feed.scrollTop = feed.scrollHeight;
  }

  function renderMatchSummaryUI(summary) {
    if (!summary) return;
    state.matchSummary = summary;
    const isEs = state.lang === "es";
    const bc = summary.badge_counts || {};

    $("done-acc-val").textContent = `${summary.accuracy_pct.toFixed(1)}%`;
    $("bar-acc-val").textContent = `${summary.accuracy_pct.toFixed(1)}%`;

    const chips = [
      { cls: "optimal", sym: "!!", cnt: bc.optimal || 0 },
      { cls: "good", sym: "!", cnt: bc.good || 0 },
      { cls: "inaccuracy", sym: "?!", cnt: bc.inaccuracy || 0 },
      { cls: "mistake", sym: "?", cnt: bc.weak_dominated || 0 },
      { cls: "blunder", sym: "??", cnt: bc.strict_dominated || 0 },
    ]
      .filter((b) => b.cnt > 0)
      .map((b) => `<span class="grade-chip ${b.cls}">${b.sym} ${b.cnt}</span>`)
      .join("");

    $("done-badges-strip").innerHTML = chips;
    $("bar-badge-counters").innerHTML = chips;

    const totM = (summary.total_timelines / 1e6).toFixed(2);
    $("done-meta-text").textContent = isEs
      ? `${summary.total_turns} turnos · ${totM}M sims · ${summary.total_elapsed_s}s`
      : `${summary.total_turns} turns · ${totM}M sims · ${summary.total_elapsed_s}s`;

    $("lbl-turning-point").textContent = isEs
      ? `Momento Clave: T${summary.turning_point_turn}`
      : `Turning Point: T${summary.turning_point_turn}`;
  }

  function getNextUncomputedTurn() {
    const rep = state.app && state.app.replay;
    if (!rep || !rep.turn_numbers || !rep.turn_numbers.length) return 1;
    const nextT = rep.turn_numbers.find((t) => !state.turnResults[t]);
    return nextT || null;
  }

  function computeClientMatchSummary() {
    const results = Object.values(state.turnResults).sort((a, b) => a.turn - b.turn);
    if (!results.length) return null;
    const counts = { optimal: 0, good: 0, inaccuracy: 0, weak_dominated: 0, strict_dominated: 0 };
    let worstTurn = results[0].turn;
    let worstReg = -1;
    let totTimelines = 0;
    let totElapsed = 0;
    let accSum = 0;
    results.forEach((tr) => {
      const act = tr.actual_action || {};
      const reg = Math.max(0, Number(act.nash_regret || 0));
      const vk = tr.verdict_key || "good";
      if (counts[vk] !== undefined) counts[vk] += 1;
      accSum += 100.0 * Math.exp(-2.2 * reg);
      if (reg > worstReg) {
        worstReg = reg;
        worstTurn = tr.turn;
      }
      totTimelines += Number(tr.total_timelines || 0);
      totElapsed += Number(tr.elapsed_s || 0);
    });
    return {
      accuracy_pct: Math.round((accSum / results.length) * 10) / 10,
      badge_counts: counts,
      turning_point_turn: worstTurn,
      turning_point_regret: Math.round(worstReg * 1000) / 1000,
      total_turns: results.length,
      total_timelines: totTimelines,
      total_elapsed_s: Math.round(totElapsed * 100) / 100,
    };
  }

  function updatePipelineActionButtons() {
    const isEs = state.lang === "es";
    const isRunning = !!state.activeStream;
    const nextT = getNextUncomputedTurn();
    const hasCompleted = Object.keys(state.turnResults).length > 0;

    const btnCancel = $("btn-cancel-stream");
    const btnResume = $("btn-resume-stream");
    const btnRestart = $("btn-restart-stream");
    if (!btnCancel || !btnResume || !btnRestart) return;

    btnCancel.style.display = isRunning ? "inline-flex" : "none";
    btnRestart.style.display = !isRunning && state.app && state.app.replay ? "inline-flex" : "none";

    if (!isRunning && hasCompleted && nextT !== null) {
      btnResume.style.display = "inline-flex";
      btnResume.textContent = isEs ? `Continuar (T${nextT}) ▶` : `Resume (T${nextT}) ▶`;
    } else {
      btnResume.style.display = "none";
    }
  }

  async function cancelActiveStream() {
    if (state.activeStream) {
      state.activeStream.close();
      state.activeStream = null;
    }
    try {
      await fetch("/api/analyze/cancel", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    } catch (_) {}
    $("live-status-dot").className = "status-dot error";
    $("live-tile-badge").textContent = state.lang === "es" ? "DETENIDO" : "STOPPED";
    $("live-tile-text").textContent =
      state.lang === "es"
        ? "Análisis detenido. Pulsa Continuar para retomar donde quedó o Reiniciar desde el Turno 1."
        : "Analysis stopped. Click Resume to continue where it left off or Restart from Turn 1.";
    if (Object.keys(state.turnResults).length > 0) {
      $("nav-step-review").disabled = false;
      const partial = computeClientMatchSummary();
      if (partial) renderMatchSummaryUI(partial);
    }
    updatePipelineActionButtons();
  }

  function openPipelineStream(startTurn) {
    if (!state.app || !state.app.replay) return;
    if (state.activeStream) {
      try { state.activeStream.close(); } catch (_) {}
      state.activeStream = null;
    }
    const numMc = parseInt($("setup-k-select").value || "128", 10);
    const twoPly = $("chk-two-ply") && $("chk-two-ply").checked ? 1 : 0;
    const computeMode = ($("setup-compute-mode") && $("setup-compute-mode").value) || "auto";
    const isResume = startTurn > 1;
    const alreadyDoneTurns = isResume
      ? Object.keys(state.turnResults).map((k) => parseInt(k, 10)).filter((n) => Number.isFinite(n)).sort((a, b) => a - b)
      : [];

    if (!isResume) {
      state.turnResults = {};
      state.pipelineLogs = [];
      state.matchSummary = null;
      state.autoPausedTurns = {};
      $("pipeline-progress-fill").style.width = "0%";
      $("pipeline-progress-pill").textContent = `0 / ${state.app.replay.num_turns}`;
    }

    $("pipeline-done-banner").style.display = "none";
    $("pipeline-sub-meta").textContent = `${state.app.replay.trainer_1_name} vs. ${state.app.replay.trainer_2_name} · K=${numMc}${twoPly ? " · 2-Ply" : ""} · ${computeMode.toUpperCase()} · ${state.app.device}`;
    $("live-status-dot").className = "status-dot running";
    $("live-tile-badge").textContent = isResume ? `T${startTurn}` : "RUNNING";
    $("live-tile-text").textContent =
      state.lang === "es"
        ? (isResume ? `Reanudando turnos pendientes desde T${startTurn}...` : "Planificando turnos únicos en balanceador híbrido GPU+CPU...")
        : (isResume ? `Resuming remaining turns from T${startTurn}...` : "Scheduling unique turns across Hybrid GPU+CPU balancer...");
    renderLiveWorkersStrip([]);

    const skipParam = alreadyDoneTurns.length ? `&skip_turns=${encodeURIComponent(alreadyDoneTurns.join(","))}` : "";
    const es = new EventSource(`/api/analyze/stream?num_mc=${numMc}&start_turn=${startTurn}&two_ply=${twoPly}&compute_mode=${encodeURIComponent(computeMode)}${skipParam}`);
    state.activeStream = es;
    updatePipelineActionButtons();
    renderPipelineLogs();

    function mergeReconstructedLogs(newLogs) {
      const byTurn = new Map();
      const schedulerEntries = [];
      const combined = isResume ? [...(state.pipelineLogs || []), ...(newLogs || [])] : [...(newLogs || [])];
      combined.forEach((entry) => {
        const tn = Number(entry.turn || 0);
        if (tn === 0) {
          schedulerEntries.push(entry);
        } else {
          if (!byTurn.has(tn)) byTurn.set(tn, []);
          byTurn.get(tn).push(entry);
        }
      });
      // On Resume, if a turn was re-received replace cleanly; keep only latest scheduler header
      const merged = [];
      if (schedulerEntries.length) {
        merged.push(schedulerEntries[schedulerEntries.length - 1]);
      }
      Array.from(byTurn.keys())
        .sort((a, b) => a - b)
        .forEach((tn) => {
          // Deduplicate identical (turn, phase) within each turn
          const seenPhase = new Set();
          byTurn.get(tn).forEach((ent) => {
            const pkKey = `${tn}:${ent.phase}`;
            if (!seenPhase.has(pkKey)) {
              seenPhase.add(pkKey);
              merged.push(ent);
            }
          });
        });
      state.pipelineLogs = merged;
    }

    es.addEventListener("scheduler", (ev) => {
      try {
        const plan = JSON.parse(ev.data || "{}");
        const isEs = state.lang === "es";
        const gpuTxt = plan.use_gpu ? `GPU (${plan.gpu_device_name || state.app.device})` : "0 GPU";
        const cpuTxt = `${plan.cpu_workers || 0} CPU`;
        $("live-tile-badge").textContent = String(plan.mode || "auto").toUpperCase();
        $("live-tile-text").textContent = isEs
          ? `Balanceador listo: ${gpuTxt} + ${cpuTxt} · ${plan.total_scheduled_turns || (plan.turns || []).length} turnos únicos (esperando fin para reconstruir log ordenado)`
          : `Balancer ready: ${gpuTxt} + ${cpuTxt} · ${plan.total_scheduled_turns || (plan.turns || []).length} unique turns (waiting for join to reconstruct ordered log)`;
      } catch (_) {}
    });

    es.addEventListener("worker_progress", (ev) => {
      try {
        const snap = JSON.parse(ev.data || "{}");
        const doneCnt = alreadyDoneTurns.length + Number(snap.completed_count || 0);
        const totCnt = Number(snap.total_turns || state.app.replay.num_turns || 1);
        const pct = Math.min(100, Math.round((doneCnt / Math.max(1, totCnt)) * 100));
        $("pipeline-progress-fill").style.width = `${pct}%`;
        $("pipeline-progress-pill").textContent = `${Math.min(doneCnt, totCnt)} / ${totCnt}`;
        $("live-status-dot").className = "status-dot running";
        $("live-tile-badge").textContent = `${Math.min(doneCnt, totCnt)}/${totCnt}`;
        const activeList = snap.active_workers || [];
        renderLiveWorkersStrip(activeList);
        const summaryActive = activeList
          .map((w) => `[${w.worker}: T${w.turn}${w.state === "idle" ? " ✓" : ` ${w.pct || 0}%`}]`)
          .join("  ");
        if (summaryActive) {
          $("live-tile-text").textContent = summaryActive;
        }
      } catch (_) {}
    });

    es.addEventListener("error", (ev) => {
      if (ev.data) {
        try {
          const payload = JSON.parse(ev.data);
          state.pipelineLogs.push({
            turn: payload.turn || 0,
            phase: "ERROR",
            compute_worker: payload.compute_worker || "ENGINE",
            messages: {
              es_vgc: `Error en turno ${payload.turn}: ${payload.error}`,
              en_vgc: `Error on turn ${payload.turn}: ${payload.error}`,
              es_scientific: `Error en turno ${payload.turn}: ${payload.error}`,
              en_scientific: `Error on turn ${payload.turn}: ${payload.error}`,
            },
          });
          renderPipelineLogs();
          $("live-status-dot").className = "status-dot error";
          $("live-tile-badge").textContent = "ERROR";
          $("live-tile-text").textContent = payload.error || "Engine error";
        } catch (_) {}
      }
    });

    es.addEventListener("cancelled", (ev) => {
      es.close();
      state.activeStream = null;
      renderLiveWorkersStrip([]);
      try {
        const payload = JSON.parse((ev && ev.data) || "{}");
        (payload.ordered_turns || []).forEach((tr) => {
          state.turnResults[tr.turn] = tr;
        });
        if (payload.reconstructed_logs && payload.reconstructed_logs.length) {
          mergeReconstructedLogs(payload.reconstructed_logs);
        }
      } catch (_) {}
      $("live-status-dot").className = "status-dot error";
      $("live-tile-badge").textContent = state.lang === "es" ? "DETENIDO" : "STOPPED";
      renderPipelineLogs();
      renderTimeline();
      updatePipelineActionButtons();
    });

    es.addEventListener("done", (ev) => {
      const payload = JSON.parse(ev.data || "{}");
      es.close();
      state.activeStream = null;
      renderLiveWorkersStrip([]);

      // Hydrate strictly ordered turns (T1 -> TN) reconstructed AFTER all workers joined
      (payload.ordered_turns || []).forEach((tr) => {
        state.turnResults[tr.turn] = tr;
      });
      if (payload.reconstructed_logs) {
        mergeReconstructedLogs(payload.reconstructed_logs);
      }

      const totCnt = state.app.replay.num_turns;
      const doneCnt = Object.keys(state.turnResults).length;
      $("pipeline-progress-fill").style.width = `${Math.min(100, Math.round((doneCnt / Math.max(1, totCnt)) * 100))}%`;
      $("pipeline-progress-pill").textContent = `${doneCnt} / ${totCnt}`;
      $("live-status-dot").className = "status-dot done";
      $("live-tile-badge").textContent = "DONE";
      const sStats = payload.scheduler_stats;
      const schedTxt = sStats
        ? ` (${sStats.gpu_turns} GPU · ${sStats.cpu_turns} CPU · ${sStats.elapsed_s}s)`
        : "";
      $("live-tile-text").textContent =
        (state.lang === "es"
          ? "Todos los hilos finalizaron · Log reconstruido en orden (T1 → TN)."
          : "All workers finished · Log reconstructed in order (T1 → TN).") + schedTxt;

      renderPipelineLogs();
      renderTimeline();
      $("nav-step-pipeline").classList.add("done");
      $("nav-step-review").disabled = false;
      $("pipeline-done-banner").style.display = "flex";
      const fullSummary = isResume ? computeClientMatchSummary() : (payload.match_summary || computeClientMatchSummary());
      if (fullSummary) {
        renderMatchSummaryUI(fullSummary);
      }
      updatePipelineActionButtons();
      selectTurn(1, false, false);
    });

    es.onerror = () => {
      if (state.activeStream === es) {
        es.close();
        state.activeStream = null;
        updatePipelineActionButtons();
      }
    };
  }

  async function launchPipelineAnalysis() {
    if (state.activeStream) {
      await cancelActiveStream();
    }

    // Verify all 6 opponent Pokémon sum to exactly 66 SP when in Clamped Slider mode
    if (state.t2Inference && state.t2Inference.pokemon) {
      const incomplete = state.t2Inference.pokemon.filter((m) => {
        const sp = state.t2UserSpreads[m.base_species] || {};
        return STAT_KEYS.reduce((a, k) => a + Number(sp[k] || 0), 0) !== 66;
      });
      if (incomplete.length > 0) {
        const names = incomplete.map((m) => m.base_species).join(", ");
        $("setup-status-msg").textContent =
          state.lang === "es"
            ? `Completa exactamente 66 SP para: ${names} (o pulsa "Auto-Completar").`
            : `Assign exactly 66 SP for: ${names} (or click "Auto-Fill Defaults").`;
        return;
      }
    }

    const pov = $("setup-pov-select").value || null;
    const t1Id = state.selectedRosterId.t1 || null;
    const t2Id = state.t2Inference ? null : (state.selectedRosterId.t2 || null);
    const t1Paste = $("t1-paste-input").value || "";
    const t2Paste = state.t2Inference ? "" : ($("t2-paste-input").value || "");

    const loadRes = await fetch("/api/bo3/load", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        replays: state.bo3Replays.length ? state.bo3Replays : null,
        pov_trainer: pov,
        t1_roster_id: t1Id,
        t2_roster_id: t2Id,
        t1_paste_text: t1Paste,
        t2_paste_text: t2Paste,
        t2_user_spreads: state.t2Inference ? state.t2UserSpreads : null,
        active_game_index: state.activeGameIndex || 0,
        t1_save_meta: {
          save_to_db: $("t1-save-db-check").checked,
          display_name: $("t1-save-name").value,
        },
        t2_save_meta: {
          save_to_db: $("t2-save-db-check").checked,
          display_name: $("t2-save-name").value,
        },
      }),
    });
    const appSummary = await loadRes.json();
    if (appSummary.error) {
      $("setup-status-msg").textContent = `Error: ${appSummary.error}`;
      return;
    }
    state.app = appSummary;
    state.bo3TurnCache = {};
    state.activeGameIndex = appSummary.active_game_index || 0;
    renderSavedTeamsList("t1");
    renderSavedTeamsList("t2");
    populatePrepRosterSelect();
    renderBo3GameTabs();

    $("nav-step-pipeline").disabled = false;
    $("nav-step-setup").classList.add("done");
    setStep("pipeline");

    $("showdown-iframe").src = `/api/replay-player?ts=${Date.now()}`;
    updateReviewHeaderMeta();
    openPipelineStream(1);
  }

  // -------------------------------------------------------------------------
  // Step 3: Clean Tabbed Review Workspace
  // -------------------------------------------------------------------------
  function updateReviewHeaderMeta() {
    if (!state.app || !state.app.replay) return;
    const rep = state.app.replay;
    $("match-title").textContent = `${rep.trainer_1_name} vs. ${rep.trainer_2_name}`;
    $("ots-match-indicator").textContent = rep.format_name || "Reg M-C";

    const tSel = $("telemetry-team-select");
    tSel.innerHTML = "";
    const tList =
      state.app.telemetry_teams && state.app.telemetry_teams.length
        ? state.app.telemetry_teams
        : ["my_team"];
    tList.forEach((tf) => {
      const opt = document.createElement("option");
      opt.value = tf;
      opt.textContent = tf;
      tSel.appendChild(opt);
    });
  }

  function getActiveCommentary(tr) {
    if (!tr) return null;
    const vars = tr.commentary_variants || {};
    return vars[profileKey()] || tr.commentary;
  }

  function renderTimeline() {
    const container = $("turn-pills");
    if (!container) return;
    container.innerHTML = "";
    const rep = state.app && state.app.replay;
    if (!rep) return;

    rep.turn_numbers.forEach((t) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "turn-pill" + (t === state.currentTurn ? " active" : "");
      const tr = state.turnResults[t];
      const com = getActiveCommentary(tr);
      const badgeHtml = com
        ? `<span class="sym ${com.badge_class}">${escapeHtml(com.symbol)}</span>`
        : `<span class="muted-xs">·</span>`;
      btn.innerHTML = `<span>T${t}</span>${badgeHtml}`;
      btn.onclick = () => selectTurn(t, true, false);
      container.appendChild(btn);
    });
  }

  function buildEvalChartSvg() {
    const rep = state.app && state.app.replay;
    if (!rep || !rep.turn_numbers.length) return "";
    const turns = rep.turn_numbers;
    const w = 600, h = 92, padX = 20, padY = 14;
    const midY = h / 2;

    let inner = `<line x1="${padX}" y1="${midY}" x2="${w - padX}" y2="${midY}" stroke="#253249" stroke-dasharray="4 4" stroke-width="1"/>`;
    const pts = [];
    turns.forEach((t, idx) => {
      const tr = state.turnResults[t];
      if (!tr) return;
      const x = turns.length === 1 ? w / 2 : padX + (idx / (turns.length - 1)) * (w - 2 * padX);
      const clamped = Math.max(-3.0, Math.min(3.0, tr.nash_value));
      const y = midY - (clamped / 3.0) * (midY - padY);
      pts.push({ t, x, y, tr });
    });

    if (pts.length >= 2) {
      const d = pts.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ");
      inner += `<path d="${d}" fill="none" stroke="#3b82f6" stroke-width="2"/>`;
    }

    const colorMap = {
      optimal: "#4ade80",
      good: "#60a5fa",
      inaccuracy: "#facc15",
      mistake: "#fb923c",
      blunder: "#f87171",
    };

    pts.forEach((p) => {
      const com = getActiveCommentary(p.tr) || {};
      const c = colorMap[com.badge_class] || "#60a5fa";
      const r = p.t === state.currentTurn ? 5.5 : 3.5;
      inner += `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="${r}" fill="${c}" stroke="#0b101b" stroke-width="1.5" style="cursor:pointer" data-chart-turn="${p.t}"><title>T${p.t}: ${p.tr.nash_value.toFixed(2)} (${escapeHtml(com.badge || "")})</title></circle>`;
    });

    return `<svg class="eval-svg" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">${inner}</svg>`;
  }

  function renderTurnPanel(data) {
    if (!data || !state.app || !state.app.replay) return;
    const isEs = state.lang === "es";
    const isSci = state.style === "scientific";
    const com = getActiveCommentary(data) || data.commentary;
    const act = data.actual_action;
    const best = (data.top_actions && data.top_actions[0]) || act;
    const f = data.field;
    const rep = state.app.replay;

    $("coach-panel-title").textContent = isEs ? `Turno ${data.turn}` : `Turn ${data.turn}`;
    const headBadge = $("coach-head-badge");
    if (headBadge && com) {
      headBadge.style.display = "inline-flex";
      headBadge.className = `verdict-pill ${com.badge_class || ""}`;
      headBadge.textContent = `${com.symbol || ""} ${com.badge || ""}`.trim();
    }
    const workerSuffix = data.compute_worker ? ` · ${data.compute_worker}` : "";
    $("turn-compute-meta").textContent = isSci
      ? `[${data.matrix_shape[0]}×${data.matrix_shape[1]}] · ${(data.total_timelines / 1000).toFixed(0)}k · ${data.elapsed_s}s${workerSuffix}`
      : `${data.elapsed_s}s${workerSuffix}`;

    const fieldTags = [];
    if (f.weather) fieldTags.push(`${f.weather} ${f.weather_turns}t`);
    if (f.terrain) fieldTags.push(`${f.terrain} ${f.terrain_turns}t`);
    if (f.trick_room_turns > 0) fieldTags.push(`Trick Room ${f.trick_room_turns}t`);
    if (f.t1_tailwind > 0) fieldTags.push(`Tailwind T1 ${f.t1_tailwind}t`);
    if (f.t2_tailwind > 0) fieldTags.push(`Tailwind T2 ${f.t2_tailwind}t`);
    const fieldStr = fieldTags.length ? fieldTags.join(" · ") : (isEs ? "Campo limpio" : "Clean field");

    const sameAsBest = best && JSON.stringify(best.choice_pair) === JSON.stringify(act.choice_pair);
    const lossVal = act.nash_regret;
    const fmtScore = (v) => `${v >= 0 ? "+" : ""}${v.toFixed(isSci ? 3 : 2)}`;
    const liveQre = getTurnLiveQre(data);
    const getLiveT1QrePct = (row) => {
      if (liveQre && typeof row.row_idx === "number" && row.row_idx >= 0 && row.row_idx < liveQre.p.length) {
        return liveQre.p[row.row_idx] * 100.0;
      }
      return Number(row.qre_pct || 0);
    };
    const getLiveT2QrePct = (row) => {
      if (liveQre && typeof row.col_idx === "number" && row.col_idx >= 0 && row.col_idx < liveQre.q.length) {
        return liveQre.q[row.col_idx] * 100.0;
      }
      return Number(row.qre_pct || 0);
    };

    const activeT1SpritesHtml = ((data.board && data.board.trainer_1) || [])
      .filter((m) => m.role === "Active" && m.sprite_url)
      .slice(0, 2)
      .map((m) => `<img src="${escapeHtml(m.sprite_url)}" alt="${escapeHtml(m.species)}" title="${escapeHtml(m.species)}" />`)
      .join("");

    const tPunish = getTermInfo("security_floor", isEs ? "Counter más fuerte" : "Counter That Punishes", true);
    const showPunish = act.worst_counter_desc && act.worst_counter_desc !== "N/A";
    const punishHtml = showPunish
      ? `<div class="punish-callout" title="${escapeHtml(tPunish.tooltip)}">
          <span><strong>${escapeHtml(tPunish.label)}:</strong> ${escapeHtml(act.worst_counter_desc)}</span>
          <span class="compare-delta">${fmtScore(act.security_floor)}</span>
        </div>`
      : "";

    const heroHtml = `
      <div class="verdict-hero ${com.badge_class}">
        <div class="verdict-row">
          <span class="verdict-pill ${com.badge_class}">${escapeHtml(com.symbol)} ${escapeHtml(com.badge)}</span>
          <span class="muted-xs">${escapeHtml(fieldStr)} · #${act.rank}/${act.total_actions}</span>
        </div>
        <div class="verdict-headline">${escapeHtml(com.headline)}</div>

        <div class="tactical-compare-grid ${sameAsBest ? "single" : ""}">
          <div class="tactical-play-card played">
            <div class="tactical-card-head">
              <span>${isEs ? "Tu jugada" : "Your play"}</span>
              <span class="compare-delta">${fmtScore(act.risk_ev)}</span>
            </div>
            <div class="tactical-card-sprites">
              ${activeT1SpritesHtml}
              <span class="tactical-play-desc">${escapeHtml(act.desc)}</span>
            </div>
          </div>
          ${
            !sameAsBest
              ? `<div class="tactical-play-card best">
                  <div class="tactical-card-head">
                    <span>${isEs ? "Recomendada #1" : "#1 Recommended"}</span>
                    <span class="compare-delta">${fmtScore(best.risk_ev)} (${lossVal > 0 ? "-" : ""}${lossVal.toFixed(isSci ? 3 : 2)})</span>
                  </div>
                  <div class="tactical-card-sprites">
                    ${activeT1SpritesHtml}
                    <span class="tactical-play-desc">${escapeHtml(best.desc)}</span>
                  </div>
                </div>`
              : ""
          }
        </div>
        ${punishHtml}
      </div>
    `;

    const fallbackPillarMap = isSci
      ? {
          material: { label: isEs ? "Ventaja Material (ΔHP + ΔKO)" : "Material (ΔHP + ΔKO)", desc: "" },
          threat: { label: isEs ? "Amenaza Letal Ponderada por Velocidad" : "Speed-Weighted Lethal Threat", desc: "" },
          malposition: { label: isEs ? "Atrapamiento Posicional y Escape a Banca" : "Positional Trap & Escape Equity", desc: "" },
          restriction: { label: isEs ? "Restricción del Espacio de Acciones" : "Action-Space Restriction", desc: "" },
          status_boost: { label: isEs ? "Valor de Estados y Modificadores de Stat" : "Role-Weighted Status & Boosts", desc: "" },
          two_turn_prime: { label: isEs ? "Valor Diferido de 2 Turnos (Cond. a HP)" : "HP-Gated 2-Turn Primed Value", desc: "" },
          resources: { label: isEs ? "Economía de Escudos y Recursos" : "Shield & Resource Economy", desc: "" },
          field_tempo: { label: isEs ? "Tempo de Campo y Turnos Restantes" : "Turn-Scaled Field & Tempo", desc: "" },
        }
      : {
          material: { label: isEs ? "Vida y KOs" : "HP & KOs (Material)", desc: "" },
          threat: { label: isEs ? "Amenaza de KO" : "Lethal KO Pressure", desc: "" },
          malposition: { label: isEs ? "Posicionamiento y Cambios" : "Pinned Matchups & Safe Switches", desc: "" },
          restriction: { label: isEs ? "Bloqueo de Jugadas" : "Move Locks (Choice / Taunt / Protect)", desc: "" },
          status_boost: { label: isEs ? "Estados y Boosts" : "Status & Stat Boosts", desc: "" },
          two_turn_prime: { label: isEs ? "Golpe Cargado (Próx. Turno)" : "Primed Next-Turn Threats", desc: "" },
          resources: { label: isEs ? "Sash, Mega y Objetos" : "Shields, Items & Mega Reserve", desc: "" },
          field_tempo: { label: isEs ? "Speed Control, Clima y Campo" : "Speed Control, Weather & Field", desc: "" },
        };
    const glossaryPillars = (state.app && state.app.glossary && state.app.glossary.pillars) || {};
    const getPillarInfo = (pkey) => {
      const regEntry = glossaryPillars[pkey] && glossaryPillars[pkey][state.lang] && glossaryPillars[pkey][state.lang][state.style];
      if (regEntry && regEntry.label) return { label: regEntry.label, desc: regEntry.desc || "" };
      return fallbackPillarMap[pkey] || { label: pkey, desc: "" };
    };

    const tVal = getTermInfo("nash_value", "Turn Advantage", false);
    const tLoss = getTermInfo("nash_regret", "Play Cost", false);
    const tCvar = getTermInfo("cvar_10", "Bad-Luck Floor", false);
    const tSurv = getTermInfo("ieds_survivors", "Viable Plays", false);
    const kpiStripHtml = `
      <div class="kpi-strip">
        <div class="kpi-card" title="${escapeHtml(tVal.tooltip)}">
          <div class="kpi-name">${escapeHtml(tVal.label)}</div>
          <div class="kpi-value">${fmtScore(data.nash_value)}</div>
        </div>
        <div class="kpi-card" title="${escapeHtml(tLoss.tooltip)}">
          <div class="kpi-name">${escapeHtml(tLoss.label)}</div>
          <div class="kpi-value">${act.nash_regret.toFixed(isSci ? 3 : 2)}</div>
        </div>
        <div class="kpi-card" title="${escapeHtml(tCvar.tooltip)}">
          <div class="kpi-name">${escapeHtml(tCvar.label)}</div>
          <div class="kpi-value">${fmtScore(act.cvar10)}</div>
        </div>
        <div class="kpi-card" title="${escapeHtml(tSurv.tooltip)}">
          <div class="kpi-name">${escapeHtml(tSurv.label)}</div>
          <div class="kpi-value">${data.ieds.t1_strict}/${data.ieds.t1_total}</div>
        </div>
      </div>
    `;

    let tabHtml = "";

    if (state.activeCoachTab === "advice") {
      const tMix = getTermInfo("nash_mix", "Mix %", true);
      const tQre = getTermInfo("human_qre", "Human %", true);
      const top3 = (data.top_actions || []).slice(0, 3);
      const top3Html = top3
        .map(
          (r, i) => `<div class="top3-row ${r.is_played ? "is-played" : ""}">
            <span class="top3-rank">#${i + 1}</span>
            <span class="top3-desc">${escapeHtml(r.desc)}</span>
            <span class="top3-meta">${fmtScore(r.risk_ev)} · ${r.nash_pct.toFixed(0)}% / ${getLiveT1QrePct(r).toFixed(0)}%</span>
          </div>`
        )
        .join("");

      const eqDrv = (data.equity_breakdown && data.equity_breakdown.top_drivers) || [];
      const eqChips = eqDrv
        .slice(0, 3)
        .map((d) => {
          const v = Number(d.value || 0);
          const cls = v > 0.02 ? "pos" : v < -0.02 ? "neg" : "";
          const pInfo = getPillarInfo(d.pillar);
          return `<span class="eq-chip ${cls}" title="${escapeHtml(pInfo.desc || pInfo.label)}">${v >= 0 ? "+" : ""}${v.toFixed(2)} ${escapeHtml(pInfo.label)}</span>`;
        })
        .join("");
      const bulletCount = (com.bullets || []).length;

      tabHtml = `
        ${heroHtml}
        ${kpiStripHtml}
        <div class="subhead">${isEs ? `Top 3 líneas (${tMix.label} / ${tQre.label})` : `Top 3 lines (${tMix.label} / ${tQre.label})`}</div>
        <div class="top3-list">${top3Html}</div>
        <div class="coach-summary-footer">
          <div style="display:flex;align-items:center;gap:5px;flex-wrap:wrap">${eqChips}</div>
          <div class="hud-bridge-row">
            <button class="btn btn-ghost btn-xs" type="button" data-hud-bridge="prep">⚡ Prep</button>
            <button class="btn btn-ghost btn-xs" type="button" data-hud-bridge="lead-lab">🎯 Leads</button>
            ${
              bulletCount > 0
                ? `<button class="btn btn-ghost btn-xs" type="button" data-jump-coach-tab="details">${
                    isEs ? `Ver ${bulletCount} claves →` : `View ${bulletCount} takeaways →`
                  }</button>`
                : ""
            }
          </div>
        </div>
      `;
    } else if (state.activeCoachTab === "details") {
      const bullets = com.bullets || [];
      const bulletsHtml = bullets
        .map(
          (b) => `<li class="advice-item ${b.tone}">
            <div class="advice-tag">${escapeHtml(b.tag)}</div>
            <div class="advice-text">${escapeHtml(b.text)}</div>
          </li>`
        )
        .join("");

      const eqP = (data.equity_breakdown && data.equity_breakdown.nash_pillars) || null;
      const eqEntries = eqP
        ? Object.entries(eqP).filter(([, val]) => Math.abs(Number(val || 0)) >= 0.01)
        : [];
      const maxAbs = Math.max(0.25, ...eqEntries.map(([, val]) => Math.abs(Number(val || 0))));
      const eqBarHtml = eqEntries.length
        ? `<div class="pillar-tug-box">
            <div class="subhead" style="margin:0 0 2px">${
              isSci
                ? (isEs ? "Desglose 8 Pilares de Equidad (U_risk)" : "8-Pillar Victory Equity Breakdown")
                : (isEs ? "Por qué gana la jugada recomendada (8 Pilares)" : "Why the recommended play wins (8 Pillars)")
            }</div>
            ${eqEntries
              .map(([k, val]) => {
                const n = Number(val || 0);
                const pctW = Math.min(50, Math.round((Math.abs(n) / maxAbs) * 50));
                const cls = n >= 0 ? "pos" : "neg";
                const pInfo = getPillarInfo(k);
                return `<div class="pillar-tug-row" title="${escapeHtml(pInfo.desc || pInfo.label)}">
                  <span class="pillar-tug-lbl">${escapeHtml(pInfo.label)}</span>
                  <div class="pillar-tug-track">
                    <div class="pillar-tug-mid"></div>
                    <div class="pillar-tug-fill ${cls}" style="width:${pctW}%"></div>
                  </div>
                  <span class="pillar-tug-val ${cls}">${n >= 0 ? "+" : ""}${n.toFixed(2)}</span>
                </div>`;
              })
              .join("")}
          </div>`
        : "";

      tabHtml = `
        <div class="subhead">${isEs ? `Claves tácticas — Turno ${data.turn}` : `Tactical takeaways — Turn ${data.turn}`}</div>
        <ul class="advice-list ${bullets.length <= 2 ? "single-col" : ""}">${bulletsHtml}</ul>
        ${eqBarHtml}
      `;
    } else if (state.activeCoachTab === "matrix") {
      const tRisk = getTermInfo("risk_utility", "Score", true);
      const tCvarShort = getTermInfo("cvar_10", "10% RNG", true);
      const tMix = getTermInfo("nash_mix", "Mix %", true);
      const tQre = getTermInfo("human_qre", "Human %", true);

      const tableRows = [...(data.top_actions || [])];
      if (!tableRows.some((r) => r.is_played)) {
        tableRows.push(act);
      }

      const actionsHtml = tableRows
        .map((r, idx) => {
          const okLbl = isSci ? "SURV" : (isEs ? "VIABLE" : "OK");
          const badLbl = isSci ? `DOM R${r.strict_dominated_by ? r.strict_dominated_by.round : "?"}` : (isEs ? "SUPERADA" : "OUTCLASSED");
          const stPill = r.survived_strict_ieds
            ? `<span class="status-pill-sm ok">${okLbl}</span>`
            : `<span class="status-pill-sm bad">${badLbl}</span>`;
          const rk = r.is_played && idx >= data.top_actions.length ? `#${act.rank}` : `#${idx + 1}`;
          const mixPct = Number(r.nash_pct || 0);
          const humPct = getLiveT1QrePct(r);
          return `<tr class="${r.is_played ? "played-row" : ""}">
            <td>${rk}</td>
            <td>${escapeHtml(r.desc)}</td>
            <td>${stPill}</td>
            <td class="num">${fmtScore(r.risk_ev)}</td>
            <td class="num">${fmtScore(r.cvar10)}</td>
            <td class="num"><span class="prob-mini-wrap"><span class="prob-mini-track"><span class="prob-mini-fill" style="width:${Math.min(100, mixPct).toFixed(0)}%"></span></span>${mixPct.toFixed(1)}%</span></td>
            <td class="num"><span class="prob-mini-wrap"><span class="prob-mini-track"><span class="prob-mini-fill human" style="width:${Math.min(100, humPct).toFixed(0)}%"></span></span>${humPct.toFixed(1)}%</span></td>
          </tr>`;
        })
        .join("");

      const elimRows = (data.ieds.sample_eliminations || [])
        .map(
          (e) => `<tr>
            <td>R${e.round}</td>
            <td>${escapeHtml(e.eliminated)}</td>
            <td>${escapeHtml(e.dominated_by)}</td>
            <td class="num">+${e.worst_margin.toFixed(2)} / +${e.mean_margin.toFixed(2)}</td>
          </tr>`
        )
        .join("");

      tabHtml = `
        ${renderQreBetaControlHtml("review-matrix")}
        <table class="data-table">
          <thead>
            <tr>
              <th>#</th>
              <th>${isEs ? "Jugada" : "Play"}</th>
              <th title="${escapeHtml(tSurv.tooltip)}">${escapeHtml(getTermInfo("ieds_survivors", "Estado", true).label)}</th>
              <th class="num" title="${escapeHtml(tRisk.tooltip)}">${escapeHtml(tRisk.label)}</th>
              <th class="num" title="${escapeHtml(tCvarShort.tooltip)}">${escapeHtml(tCvarShort.label)}</th>
              <th class="num" title="${escapeHtml(tMix.tooltip)}">${escapeHtml(tMix.label)}</th>
              <th class="num" title="${escapeHtml(tQre.tooltip)}">${escapeHtml(tQre.label)}</th>
            </tr>
          </thead>
          <tbody>${actionsHtml}</tbody>
        </table>

        <details class="inspector">
          <summary>${
            isSci
              ? (isEs ? `Inspector IEDS (${data.ieds.t1_strict_elim} dominadas en ${data.ieds.strict_rounds} rondas)` : `IEDS Inspector (${data.ieds.t1_strict_elim} dominated in ${data.ieds.strict_rounds} rounds)`)
              : (isEs ? `Jugadas descartadas (${data.ieds.t1_strict_elim} siempre inferiores)` : `Pruned plays (${data.ieds.t1_strict_elim} always outclassed)`)
          }</summary>
          <div style="margin-top:6px">
            ${
              elimRows
                ? `<table class="data-table">
                    <thead><tr><th>R</th><th>${isEs ? "Descartada" : "Eliminated"}</th><th>${isEs ? "Superada por" : "Beaten by"}</th><th class="num">Min / Avg</th></tr></thead>
                    <tbody>${elimRows}</tbody>
                  </table>`
                : `<span class="muted-sm">${isEs ? "Ninguna jugada fue estrictamente superada." : "No play was strictly outclassed."}</span>`
            }
          </div>
        </details>
      `;
    } else if (state.activeCoachTab === "board") {
      const renderSide = (title, mons) => {
        const rows = (mons || [])
          .map((m) => {
            const boosts = [];
            if (m.atk_boost) boosts.push(`Atk${m.atk_boost > 0 ? "+" : ""}${m.atk_boost}`);
            if (m.spa_boost) boosts.push(`SpA${m.spa_boost > 0 ? "+" : ""}${m.spa_boost}`);
            if (m.spd_boost) boosts.push(`SpD${m.spd_boost > 0 ? "+" : ""}${m.spd_boost}`);
            const bStr = boosts.length ? ` [${boosts.join(",")}]` : "";
            const protTag = m.protect_prev ? " 🛡" : "";
            const otsBadge = m.ots_verified
              ? `<span class="ots-verified-chip" title="${isEs ? "Movimientos verificados desde OTS oficial del replay / paste" : "Moves verified from official replay |showteam| OTS / paste"}">OTS ✓</span>`
              : "";
            const movesLine =
              m.moves && m.moves.length
                ? `<div class="board-mon-moves">${m.moves.map((mv) => `<span class="board-move-pill">${escapeHtml(mv)}</span>`).join("")}</div>`
                : "";
            return `<div class="board-mon ${m.hp_cur <= 0 ? "fainted" : ""}">
              <div class="board-mon-top">
                <span class="board-mon-left">
                  ${spritePairHtml(m.sprite_url, m.item_sprite_url, m.species, m.item)}
                  <span><strong>${m.role === "Active" ? "ACT" : "BNC"}</strong> ${escapeHtml(m.species)}${escapeHtml(bStr)}${protTag} ${otsBadge}</span>
                </span>
                <span class="muted-xs">${m.hp_pct}% · ${m.spe} Spe${m.ability ? ` · ${escapeHtml(m.ability)}` : ""}</span>
              </div>
              ${movesLine}
            </div>`;
          })
          .join("");
        return `<div class="side-card"><div class="side-head">${escapeHtml(title)}</div>${rows}</div>`;
      };

      const koEntries = Object.entries(act.ko_probs_vs_actual_opp || {});
      const koStrip = koEntries.length
        ? `<div class="equity-drivers-strip">
            <span class="muted-xs" style="font-weight:700">${isEs ? "Prob. KO:" : "KO Odds:"}</span>
            ${koEntries
              .map(([sp, pct]) => `<span class="eq-chip">${escapeHtml(sp)} ${Number(pct).toFixed(0)}%</span>`)
              .join("")}
          </div>`
        : "";

      tabHtml = `
        <div class="subhead" style="display:flex;justify-content:space-between;align-items:center">
          <span>${isEs ? `Tablero al inicio del Turno ${data.turn}` : `Board at start of Turn ${data.turn}`}</span>
          <span class="muted-xs" style="text-transform:none">${escapeHtml(fieldStr)}</span>
        </div>
        <div class="board-columns">
          ${renderSide(rep.trainer_1_name, data.board.trainer_1)}
          ${renderSide(rep.trainer_2_name, data.board.trainer_2)}
        </div>
        ${koStrip}
      `;
    } else {
      const valLabel = getTermInfo("nash_value", "Turn Advantage", false).label;
      const oppHumLbl = isSci ? "QRE" : (isEs ? "Hum." : "Hum.");
      const oppTopRows = (data.opp_top_actions || [])
        .slice(0, 4)
        .map(
          (o, idx) => `<div class="opp-top-row ${o.is_played ? "is-played" : ""}">
            <span><strong>#${idx + 1}</strong> ${escapeHtml(o.desc)}${o.is_played ? ` <span class="muted-xs">(${isEs ? "jugada" : "played"})</span>` : ""}</span>
            <span class="top3-meta">${o.nash_pct.toFixed(0)}% · ${oppHumLbl} ${getLiveT2QrePct(o).toFixed(0)}%</span>
          </div>`
        )
        .join("");

      tabHtml = `
        <div class="subhead">${escapeHtml(valLabel)} — ${isEs ? "Evolución de la partida (click en un punto para saltar)" : "Match progression (click any dot to jump)"}</div>
        <div class="graph-svg-box">${buildEvalChartSvg()}</div>
        <div class="subhead">${isEs ? `Respuestas principales del rival (Turno ${data.turn})` : `Top opponent responses (Turn ${data.turn})`}</div>
        <div class="opp-top-strip">${oppTopRows || `<span class="muted-xs">—</span>`}</div>
      `;
    }

    const body = $("coach-panel-body");
    body.innerHTML = tabHtml;
    body.scrollTop = 0;
    body.querySelectorAll("circle[data-chart-turn]").forEach((el) => {
      el.addEventListener("click", () => selectTurn(parseInt(el.dataset.chartTurn, 10), true, false));
    });
    body.querySelectorAll("[data-jump-coach-tab]").forEach((el) => {
      el.addEventListener("click", () => setCoachTab(el.dataset.jumpCoachTab));
    });
    body.querySelectorAll("[data-hud-bridge]").forEach((el) => {
      el.addEventListener("click", () => {
        if (el.dataset.hudBridge === "prep") openPrepToolsView("speed_tiers");
        else if (el.dataset.hudBridge === "lead-lab") openLeadLabView();
      });
    });
    bindQreBetaControl(body, () => {
      renderTurnPanel(data);
      if (state.leadLab.result) renderLeadLabPodium(state.leadLab.result);
    });
    syncCoachPanelHeight();
  }

  async function selectTurn(turnNum, syncShowdown, forceRecompute) {
    const rep = state.app && state.app.replay;
    if (!rep) return;
    const clamped = Math.max(1, Math.min(rep.num_turns, turnNum));
    state.currentTurn = clamped;
    $("current-turn-label").textContent = `${state.lang === "es" ? "Turno" : "Turn"} ${clamped} / ${rep.num_turns}`;
    if (syncShowdown) {
      $("autopause-toast").style.display = "none";
      postToShowdown({ type: "SEEK_TURN", turn: clamped });
    }
    renderTimeline();

    if (!forceRecompute && state.turnResults[clamped]) {
      renderTurnPanel(state.turnResults[clamped]);
      return;
    }

    const numMc = parseInt($("setup-k-select").value || "128", 10);
    const twoPly = $("chk-two-ply") && $("chk-two-ply").checked ? 1 : 0;
    $("coach-panel-title").textContent = `${state.lang === "es" ? "Calculando Turno" : "Computing Turn"} ${clamped}...`;
    const res = await fetch(`/api/analyze/turn?turn=${clamped}&num_mc=${numMc}&two_ply=${twoPly}`);
    const data = await res.json();
    if (!data.error) {
      state.turnResults[clamped] = data;
      if (state.currentTurn === clamped) {
        renderTurnPanel(data);
      }
      renderTimeline();
    }
  }

  // -------------------------------------------------------------------------
  // Event Listeners & Keyboard Shortcuts
  // -------------------------------------------------------------------------
  window.addEventListener("message", (ev) => {
    const msg = ev.data || {};
    if (msg.type === "IFRAME_HEIGHT" && typeof msg.height === "number") {
      const frame = $("showdown-iframe");
      const wrap = frame && frame.parentElement;
      const clampedH = Math.max(372, Math.min(680, Math.ceil(msg.height)));
      if (frame) frame.style.height = `${clampedH}px`;
      if (wrap) wrap.style.minHeight = `${clampedH}px`;
      requestAnimationFrame(syncCoachPanelHeight);
      return;
    }
    if (msg.type === "PLAYER_READY") {
      if (typeof msg.paused === "boolean") {
        state.playerPaused = msg.paused;
        updatePlayPauseButton();
      }
      const spSel = $("player-speed-select");
      if (spSel && spSel.value) {
        postToShowdown({ type: "SET_SPEED", speed: spSel.value });
      }
      return;
    }
    if (msg.type === "PLAYER_STATE" && typeof msg.paused === "boolean") {
      state.playerPaused = msg.paused;
      updatePlayPauseButton();
      return;
    }
    if (msg.type === "TURN_CHANGED" && typeof msg.turn === "number" && msg.turn >= 1) {
      if (typeof msg.paused === "boolean") {
        state.playerPaused = msg.paused;
        updatePlayPauseButton();
      }
      if (msg.turn !== state.currentTurn) {
        selectTurn(msg.turn, false, false);
        const tr = state.turnResults[msg.turn];
        if (
          $("chk-autopause-mistakes").checked &&
          tr &&
          !state.autoPausedTurns[msg.turn] &&
          ["inaccuracy", "weak_dominated", "strict_dominated"].includes(tr.verdict_key)
        ) {
          state.autoPausedTurns[msg.turn] = true;
          postToShowdown({ type: "PAUSE" });
          const com = getActiveCommentary(tr) || {};
          $("autopause-toast-text").textContent =
            state.lang === "es"
              ? `Auto-pausa en Turno ${msg.turn} [${com.symbol} ${com.badge}]: revisa la jugada recomendada antes de continuar.`
              : `Auto-paused on Turn ${msg.turn} [${com.symbol} ${com.badge}]: review the recommended line before continuing.`;
          $("autopause-toast").style.display = "flex";
        }
      }
    }
  });

  window.addEventListener("keydown", (ev) => {
    if (state.activeStep !== "review") return;
    const tag = (ev.target && ev.target.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
    if (ev.key === "ArrowLeft") {
      ev.preventDefault();
      selectTurn(state.currentTurn - 1, true, false);
    } else if (ev.key === "ArrowRight") {
      ev.preventDefault();
      selectTurn(state.currentTurn + 1, true, false);
    } else if (ev.key === " ") {
      ev.preventDefault();
      $("autopause-toast").style.display = "none";
      postToShowdown({ type: "TOGGLE_PLAY" });
    }
  });

  ["setup", "pipeline", "review"].forEach((s) => {
    $(`nav-step-${s}`).onclick = () => {
      if (!$(`nav-step-${s}`).disabled) setStep(s);
    };
  });

  COACH_TABS.forEach((t) => {
    const btn = $(`tab-btn-${t}`);
    if (btn) btn.onclick = () => setCoachTab(t);
  });

  if (typeof ResizeObserver !== "undefined" && $("review-player-panel")) {
    const ro = new ResizeObserver(() => syncCoachPanelHeight());
    ro.observe($("review-player-panel"));
  }
  window.addEventListener("resize", syncCoachPanelHeight);

  $("btn-lang-es").onclick = () => {
    state.lang = "es";
    localStorage.setItem("porygon_lang", "es");
    applyAllTranslations();
  };
  $("btn-lang-en").onclick = () => {
    state.lang = "en";
    localStorage.setItem("porygon_lang", "en");
    applyAllTranslations();
  };
  $("btn-style-vgc").onclick = () => {
    state.style = "vgc";
    localStorage.setItem("porygon_style", "vgc");
    applyAllTranslations();
  };
  $("btn-style-sci").onclick = () => {
    state.style = "scientific";
    localStorage.setItem("porygon_style", "scientific");
    applyAllTranslations();
  };

  // Chrome-duplicate-safe filename comparator: `match.html` (0) < `match (1).html` (1) < `match (2).html` (2)
  function compareReplayFilenames(nameA, nameB) {
    const splitDup = (fn) => {
      const s = String(fn || "").replace(/\.(html?|log|txt)$/i, "");
      const m = s.match(/^(.*?)\s*\((\d+)\)$/);
      return m ? { base: m[1].trim().toLowerCase(), num: parseInt(m[2], 10) } : { base: s.trim().toLowerCase(), num: 0 };
    };
    const a = splitDup(nameA);
    const b = splitDup(nameB);
    const cmp = a.base.localeCompare(b.base, undefined, { numeric: true });
    return cmp !== 0 ? cmp : a.num - b.num;
  }

  // Multi-File Drag & Drop + File Input + Append Mode (1 to 3 Showdown Replays: Bo1 or Bo3)
  async function readUploadedFiles(fileList, appendMode) {
    const arr = Array.from(fileList || []);
    arr.sort((a, b) => compareReplayFilenames(a.name, b.name));
    const newItems = [];
    for (const f of arr) {
      newItems.push({ filename: f.name, raw_input: await f.text() });
    }
    if (!newItems.length) return;

    let combined = appendMode && state.rawReplayText !== "__SAMPLE__" ? [...state.bo3Replays] : [];
    const seenTexts = new Set(combined.map((it) => (it.raw_input || "").trim()));
    for (const it of newItems) {
      const clean = (it.raw_input || "").trim();
      if (!clean || seenTexts.has(clean)) continue;
      if (combined.length >= 3) break;
      seenTexts.add(clean);
      combined.push(it);
    }
    if (combined.length) {
      const pov = appendMode && $("setup-pov-select") ? $("setup-pov-select").value || null : null;
      await handleBo3ReplayFiles(combined, false, pov);
    }
  }

  const dz = $("replay-dropzone");
  dz.addEventListener("dragover", (e) => {
    e.preventDefault();
    dz.classList.add("dragover");
  });
  dz.addEventListener("dragleave", () => dz.classList.remove("dragover"));
  dz.addEventListener("drop", async (e) => {
    e.preventDefault();
    dz.classList.remove("dragover");
    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length) {
      await readUploadedFiles(e.dataTransfer.files, false);
    }
  });

  $("replay-file-input").onchange = async (e) => {
    if (e.target.files && e.target.files.length) {
      await readUploadedFiles(e.target.files, false);
      e.target.value = "";
    }
  };

  if ($("replay-add-file-input")) {
    $("replay-add-file-input").onchange = async (e) => {
      if (e.target.files && e.target.files.length) {
        await readUploadedFiles(e.target.files, true);
        e.target.value = "";
      }
    };
  }

  $("btn-change-replay").onclick = () => {
    $("replay-dropzone").style.display = "block";
  };

  $("btn-toggle-raw-replay").onclick = () => {
    const box = $("raw-replay-box");
    box.style.display = box.style.display === "none" ? "block" : "none";
  };

  $("btn-parse-raw-replay").onclick = async () => {
    const rawText = ($("raw-replay-textarea") && $("raw-replay-textarea").value) || "";
    if (!rawText.trim()) return;
    const trimmed = rawText.trim();
    if (state.bo3Replays.length > 0 && state.bo3Replays.length < 3 && state.rawReplayText !== "__SAMPLE__") {
      const exists = state.bo3Replays.some((it) => (it.raw_input || "").trim() === trimmed);
      if (!exists) {
        const nextIdx = state.bo3Replays.length + 1;
        const combined = [...state.bo3Replays, { filename: `Game ${nextIdx}`, raw_input: rawText }];
        const pov = ($("setup-pov-select") && $("setup-pov-select").value) || null;
        $("raw-replay-textarea").value = "";
        await handleBo3ReplayFiles(combined, false, pov);
        return;
      }
    }
    await handleReplayInput(rawText, false, null);
  };

  $("btn-load-sample").onclick = () => {
    handleBo3ReplayFiles([], true, "treces_gc");
  };

  $("setup-pov-select").onchange = (e) => {
    if (state.bo3Replays.length) {
      handleBo3ReplayFiles(state.bo3Replays, false, e.target.value);
    } else {
      handleReplayInput(
        state.rawReplayText === "__SAMPLE__" ? "" : state.rawReplayText,
        state.rawReplayText === "__SAMPLE__",
        e.target.value
      );
    }
  };

  // Ephemeral Clamped 66-SP Workbench Actions (Auto-Fill & Optional Save to DuckDB Library)
  if ($("btn-t2-autofill-all")) {
    $("btn-t2-autofill-all").onclick = () => {
      if (!state.t2Inference || !state.t2Inference.pokemon) return;
      state.t2Inference.pokemon.forEach((m) => {
        state.t2UserSpreads[m.base_species] = Object.assign({}, m.default_spread);
      });
      renderClampedSpPanel();
    };
  }

  if ($("btn-t2-save-ephemeral")) {
    $("btn-t2-save-ephemeral").onclick = async () => {
      if (!state.t2Inference || !state.t2Inference.pokemon) return;
      const isEs = state.lang === "es";
      const oppName = state.t2Inference.trainer_2_name || "Opponent";
      const defaultTitle = `${oppName} — Solved 66-SP`;
      const displayName = window.prompt(
        isEs
          ? "Nombre para guardar esta hoja 66-SP en tu biblioteca DuckDB:"
          : "Display name to save this 66-SP opponent sheet to your DuckDB library:",
        defaultTitle
      );
      if (!displayName || !displayName.trim()) return;

      // Build finalized paste from current clamped slider values
      const blocks = state.t2Inference.pokemon.map((m) => {
        const sp = state.t2UserSpreads[m.base_species] || m.default_spread;
        const header = m.item ? `${m.base_species} @ ${m.item}` : m.base_species;
        const spParts = STAT_KEYS.filter((k) => Number(sp[k] || 0) > 0).map(
          (k) => `${sp[k]} ${STAT_LABELS[k]}`
        );
        const lines = [header, `Ability: ${m.ability || "None"}`, "Level: 50"];
        if (spParts.length) lines.push(`EVs: ${spParts.join(" / ")}`);
        lines.push(`${m.nature || "Serious"} Nature`);
        (m.moves || []).slice(0, 4).forEach((mv) => lines.push(`- ${mv}`));
        return lines.join("\n");
      });
      const pasteText = blocks.join("\n\n");
      const rosterId = `${normStr(oppName) || "opp"}_${Date.now().toString(36)}`;
      const res = await fetch("/api/rosters", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          roster_id: rosterId,
          display_name: displayName.trim(),
          trainer_hint: oppName,
          paste_text: pasteText,
        }),
      });
      const d = await res.json();
      if (d.rosters && state.app) {
        state.app.rosters = d.rosters;
        renderSavedTeamsList("t1");
        renderSavedTeamsList("t2");
        $("setup-status-msg").textContent = isEs
          ? `Guardado "${displayName.trim()}" en tu biblioteca DuckDB.`
          : `Saved "${displayName.trim()}" to your DuckDB library.`;
      }
    };
  }

  // Side-by-side OTS Search, 66-SP Solver, Clear, and Inline Paste controls
  async function autoInferSideFromReplay(side) {
    if (side === "t2") {
      return runBo3OpponentInference();
    }
    const isEs = state.lang === "es";
    if (!state.rawReplayText) {
      $("setup-status-msg").textContent = isEs
        ? "Primero carga un replay para resolver el 66-SP."
        : "Load a replay first before running the 66-SP solver.";
      return;
    }
    const btn = $(`btn-${side}-infer`);
    const prevTxt = btn ? btn.textContent : "";
    if (btn) {
      btn.disabled = true;
      btn.textContent = isEs ? "Resolviendo..." : "Solving...";
    }
    try {
      const pov = $("setup-pov-select") ? $("setup-pov-select").value || null : null;
      const res = await fetch("/api/rosters/infer-from-replay", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          raw_input: state.rawReplayText === "__SAMPLE__" ? "" : state.rawReplayText,
          use_sample: state.rawReplayText === "__SAMPLE__",
          pov_trainer: pov,
          side: side,
        }),
      });
      const d = await res.json();
      if (!d.ok) {
        $("setup-status-msg").textContent = `Error: ${d.error || "Solver failed"}`;
        return;
      }
      state.selectedRosterId[side] = null;
      $(`${side}-paste-input`).value = d.paste_text || "";
      if (side === "t1") state.t1Validation = d.validation;
      else state.t2Validation = d.validation;
      renderSavedTeamsList(side);
      renderOtsMonGrid(`${side}-ots-mon-grid`, `${side}-sp-status`, d.validation);
      $("setup-status-msg").textContent = isEs
        ? `66-SP resuelto para ${d.trainer_name} (${d.inferred_count} Pokémon desde OTS + telemetría del replay).`
        : `Solved 66-SP for ${d.trainer_name} (${d.inferred_count} Pokémon from OTS + replay telemetry).`;
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = prevTxt || (isEs ? "Resolver 66-SP" : "Solve 66-SP");
      }
    }
  }

  ["t1", "t2"].forEach((side) => {
    $(`${side}-search-input`).addEventListener("input", (e) => {
      state.searchQuery[side] = e.target.value || "";
      renderSavedTeamsList(side);
    });

    if ($(`btn-${side}-infer`)) {
      $(`btn-${side}-infer`).onclick = () => autoInferSideFromReplay(side);
    }

    $(`btn-${side}-clear`).onclick = () => {
      clearSideSelection(side);
    };

    $(`btn-${side}-toggle-paste`).onclick = () => {
      const dr = $(`${side}-paste-drawer`);
      dr.style.display = dr.style.display === "none" ? "block" : "none";
    };

    $(`btn-${side}-validate`).onclick = () => {
      state.selectedRosterId[side] = null;
      renderSavedTeamsList(side);
      validateAndRenderSide(side, $(`${side}-paste-input`).value);
    };

    $(`${side}-paste-input`).addEventListener("input", () => {
      state.selectedRosterId[side] = null;
      renderSavedTeamsList(side);
    });
  });

  $("btn-launch-analysis").onclick = () => launchPipelineAnalysis();
  $("btn-cancel-stream").onclick = () => cancelActiveStream();
  $("btn-resume-stream").onclick = () => {
    const nextT = getNextUncomputedTurn();
    openPipelineStream(nextT || 1);
  };
  $("btn-restart-stream").onclick = () => openPipelineStream(1);

  $("btn-start-synced-replay").onclick = () => {
    setStep("review");
    selectTurn(1, true, false);
    setTimeout(() => postToShowdown({ type: "PLAY", turn: 1 }), 350);
  };

  $("btn-resume-replay").onclick = () => {
    $("autopause-toast").style.display = "none";
    postToShowdown({ type: "PLAY" });
  };

  $("btn-jump-turning-point").onclick = () => {
    if (state.matchSummary && state.matchSummary.turning_point_turn) {
      setStep("review");
      selectTurn(state.matchSummary.turning_point_turn, true, false);
    }
  };

  $("btn-back-to-log").onclick = () => setStep("pipeline");
  $("btn-prev-turn").onclick = () => selectTurn(state.currentTurn - 1, true, false);
  $("btn-next-turn").onclick = () => selectTurn(state.currentTurn + 1, true, false);
  $("btn-play-pause").onclick = () => {
    $("autopause-toast").style.display = "none";
    postToShowdown({ type: "TOGGLE_PLAY" });
  };
  $("btn-flip-pov").onclick = () => postToShowdown({ type: "SWITCH_VIEWPOINT" });
  if ($("player-speed-select")) {
    $("player-speed-select").onchange = (e) => {
      postToShowdown({ type: "SET_SPEED", speed: e.target.value });
    };
  }
  $("btn-recompute-turn").onclick = () => selectTurn(state.currentTurn, false, true);

  $("btn-export-telemetry").onclick = async () => {
    const tf = $("telemetry-team-select").value || "char_y_v4";
    const res = await fetch("/api/telemetry/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        team_folder: tf,
        turn_results: state.turnResults,
        lang: state.lang,
        style: state.style,
      }),
    });
    const d = await res.json();
    if (d.ok) {
      $("stream-status").textContent =
        state.lang === "es"
          ? `CSV guardado (${d.turns_written}t)`
          : `CSV saved (${d.turns_written}t)`;
    } else if (d.error) {
      $("stream-status").textContent = `CSV Error: ${d.error}`;
    }
  };

  // Session / Bo3 Tournament Analytics Dashboard Modal
  function buildSessionAccuracySvg(matches) {
    const pts = (matches || [])
      .slice()
      .reverse()
      .filter((m) => m.accuracy_pct != null);
    if (!pts.length) {
      return `<div class="muted-xs" style="padding:12px 0">${
        state.lang === "es"
          ? "Exporta partidas analizadas a CSV para ver la curva de precisión."
          : "Export analyzed matches to CSV to populate the accuracy trend."
      }</div>`;
    }
    const w = 520, h = 92, padX = 18, padY = 14;
    let inner = `<line x1="${padX}" y1="${h / 2}" x2="${w - padX}" y2="${h / 2}" stroke="#253249" stroke-dasharray="4 4" stroke-width="1"/>`;
    const coords = pts.map((m, i) => {
      const x = pts.length === 1 ? w / 2 : padX + (i / (pts.length - 1)) * (w - 2 * padX);
      const y = h - padY - (Math.max(0, Math.min(100, m.accuracy_pct)) / 100.0) * (h - 2 * padY);
      return { x, y, m };
    });
    if (coords.length >= 2) {
      const d = coords.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ");
      inner += `<path d="${d}" fill="none" stroke="#3b82f6" stroke-width="2"/>`;
    }
    coords.forEach((p) => {
      const c = p.m.is_win ? "#4ade80" : "#f87171";
      inner += `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="4" fill="${c}" stroke="#0b101b" stroke-width="1.5"><title>${escapeHtml(p.m.trainer_2)}: ${p.m.accuracy_pct}% (${p.m.is_win ? "W" : "L"})</title></circle>`;
    });
    return `<svg class="eval-svg" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">${inner}</svg>`;
  }

  function renderAnalyticsGuideSteps() {
    const box = $("analytics-guide-steps");
    if (!box) return;
    const isEs = state.lang === "es";
    const steps = isEs
      ? [
          {
            n: 1,
            t: "Crea o elige una carpeta de equipo",
            d: "Escribe un nombre arriba (ej. rain_archaludon_v1) y pulsa '+ Crear'. Coach Porygon crea automáticamente data/telemetry/<equipo>/battles_telemetry.csv por ti.",
          },
          {
            n: 2,
            t: "Audita tus partidas en Bo3 Coach",
            d: "Abre 🧠 Bo3 Replay Coach, carga 1 a 3 replays (o la partida de ejemplo) y ejecuta el Tensor Core para calcular Nash Regret, insignias (!! / ! / ?! / ? / ??) y eventos RNG.",
          },
          {
            n: 3,
            t: "Pulsa 'Exportar CSV' en el Paso 3",
            d: "En la barra superior del Paso 3 elige tu carpeta de equipo y haz click en 'Exportar CSV'. Cada partida se deduplica por match_id y actualiza tus gráficas al instante.",
          },
        ]
      : [
          {
            n: 1,
            t: "Create or pick a team folder",
            d: "Type a team folder name above (e.g. rain_archaludon_v1) and click '+ Create'. Coach Porygon initializes data/telemetry/<team>/battles_telemetry.csv automatically.",
          },
          {
            n: 2,
            t: "Audit replays in Bo3 Coach",
            d: "Open 🧠 Bo3 Replay Coach, load 1–3 Showdown replays (or the built-in Sample Match), and run the Tensor Core to grade turns with Nash Regret, badges (!! / ! / ?! / ? / ??), and RNG flags.",
          },
          {
            n: 3,
            t: "Click 'Export CSV' in Step 3 Review",
            d: "Select your team folder in Step 3's top toolbar and click 'Export CSV'. Matches deduplicate cleanly by match_id and immediately populate your Win Rate, Accuracy curve & Lead stats here.",
          },
        ];
    box.innerHTML = steps
      .map(
        (s) => `<div class="analytics-step-card">
          <div class="analytics-step-head">
            <span class="analytics-step-num">${s.n}</span>
            <span>${escapeHtml(s.t)}</span>
          </div>
          <div class="analytics-step-desc">${escapeHtml(s.d)}</div>
        </div>`
      )
      .join("");
  }

  async function createTelemetryTeamFolder(rawName) {
    const isEs = state.lang === "es";
    const msgEl = $("analytics-action-msg");
    const name = String(rawName || "").trim();
    if (!name) {
      if (msgEl) {
        msgEl.style.display = "block";
        msgEl.textContent = isEs
          ? "Escribe un nombre para la carpeta (ej. mi_equipo_v1)."
          : "Enter a folder name first (e.g. my_team_v1).";
      }
      return;
    }
    try {
      const res = await fetch("/api/telemetry/create-team", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ team_folder: name }),
      });
      const d = await res.json();
      if (!res.ok || !d.ok) {
        if (msgEl) {
          msgEl.style.display = "block";
          msgEl.textContent = `Error: ${d.error || "Could not create folder"}`;
        }
        return;
      }
      if (state.app) state.app.telemetry_teams = d.teams || [];
      updateReviewHeaderMeta();
      if ($("analytics-new-team-input")) $("analytics-new-team-input").value = "";
      if (msgEl) {
        msgEl.style.display = "block";
        msgEl.textContent = d.created
          ? (isEs
              ? `Carpeta '${d.team_folder}' creada en ${d.csv_path}. ¡Ahora audita una partida en Bo3 Coach y pulsa 'Exportar CSV'!`
              : `Folder '${d.team_folder}' created at ${d.csv_path}. Now audit a replay in Bo3 Coach and click 'Export CSV'!`)
          : (isEs
              ? `La carpeta '${d.team_folder}' ya existía (${d.csv_path}).`
              : `Folder '${d.team_folder}' already exists (${d.csv_path}).`);
      }
      await loadAndRenderAnalytics(d.team_folder);
    } catch (err) {
      if (msgEl) {
        msgEl.style.display = "block";
        msgEl.textContent = `Error: ${String(err)}`;
      }
    }
  }

  async function loadAndRenderAnalytics(teamOverride) {
    const isEs = state.lang === "es";
    const sel = $("analytics-team-select");
    const body = $("analytics-dashboard-body");
    const guidePanel = $("analytics-guide-panel");
    if (!body) return;
    body.innerHTML = `<div class="muted-sm">${isEs ? "Cargando sesiones..." : "Loading session analytics..."}</div>`;

    const reqTeam = teamOverride || (sel && sel.value) || "all";
    const res = await fetch(`/api/telemetry/summary?team=${encodeURIComponent(reqTeam)}`);
    const d = await res.json();
    if (!d.ok) {
      body.innerHTML = `<div class="muted-sm">Error: ${escapeHtml(d.error || "Unknown")}</div>`;
      return;
    }

    const teams = d.teams || [];
    if (state.app) state.app.telemetry_teams = teams;
    if (sel) {
      sel.innerHTML =
        `<option value="all">${isEs ? "Todos los equipos" : "All teams"}</option>` +
        teams.map((tf) => `<option value="${escapeHtml(tf)}">${escapeHtml(tf)}</option>`).join("");
      sel.value = teams.includes(d.team_folder) ? d.team_folder : "all";
    }

    if (!d.total_matches) {
      if (guidePanel) guidePanel.style.display = "block";
      const hasFolders = teams.length > 0;
      const folderHint = hasFolders
        ? (isEs
            ? `Tienes ${teams.length} carpeta(s) lista(s) (${teams.join(", ")}), pero todavía sin partidas exportadas.`
            : `You have ${teams.length} folder(s) ready (${teams.join(", ")}), with 0 exported matches so far.`)
        : (isEs
            ? "Todavía no existe ninguna carpeta en data/telemetry/. Crea tu primera carpeta de equipo aquí abajo en 1 click:"
            : "No folders exist in data/telemetry/ yet. Create your first team folder below in 1 click:");

      body.innerHTML = `<div class="analytics-empty-hero">
        <div class="analytics-empty-title">${
          hasFolders
            ? (isEs ? "Aún no hay partidas exportadas en esta carpeta" : "No exported matches in this folder yet")
            : (isEs ? "Empieza tu Diario de Telemetría VGC" : "Start Your Local VGC Telemetry Log")
        }</div>
        <div class="muted-sm" style="max-width:620px">${escapeHtml(folderHint)}</div>
        ${
          !hasFolders
            ? `<div class="analytics-empty-create">
                <input type="text" id="analytics-empty-folder-input" class="analytics-folder-input" placeholder="${isEs ? "Ej. mi_equipo_reg_mc" : "e.g. my_reg_mc_team"}" />
                <button class="btn btn-emerald" id="btn-analytics-empty-create" type="button">${isEs ? "+ Crear mi primera carpeta" : "+ Create First Team Folder"}</button>
              </div>`
            : ""
        }
        <div class="btn-row" style="margin-top:6px">
          <button class="btn btn-greatball" id="btn-analytics-empty-bo3" type="button">${isEs ? "🧠 Ir a Bo3 Replay Coach →" : "🧠 Open Bo3 Replay Coach →"}</button>
        </div>
      </div>`;

      if ($("btn-analytics-empty-create")) {
        $("btn-analytics-empty-create").onclick = () => {
          const v = ($("analytics-empty-folder-input") && $("analytics-empty-folder-input").value) || "my_reg_mc_team";
          createTelemetryTeamFolder(v);
        };
      }
      if ($("btn-analytics-empty-bo3")) {
        $("btn-analytics-empty-bo3").onclick = () => openBo3CoachView();
      }
      return;
    }

    const mp = d.mistakes_by_phase || {};
    const maxPhase = Math.max(1, mp.lead || 0, mp.midgame || 0, mp.endgame || 0);
    const phaseRows = [
      { lbl: isEs ? "Turn 1 (Lead)" : "Turn 1 (Lead)", val: mp.lead || 0 },
      { lbl: isEs ? "Mid-Game (T2–T4)" : "Mid-Game (T2–T4)", val: mp.midgame || 0 },
      { lbl: isEs ? "Endgame (T5+)" : "Endgame (T5+)", val: mp.endgame || 0 },
    ]
      .map(
        (r) => `<div class="phase-bar-row">
          <span class="phase-bar-label">${escapeHtml(r.lbl)}</span>
          <div class="phase-bar-track"><div class="phase-bar-fill" style="width:${Math.round((100 * r.val) / maxPhase)}%"></div></div>
          <span class="phase-bar-val">${r.val}</span>
        </div>`
      )
      .join("");

    const leadRows = (d.lead_stats || [])
      .map(
        (l) => `<tr>
          <td>${escapeHtml(l.lead)}</td>
          <td class="num">${l.wins}-${l.games - l.wins}</td>
          <td class="num">${l.win_rate_pct.toFixed(0)}%</td>
        </tr>`
      )
      .join("");

    const matchRows = (d.matches || [])
      .slice(0, 25)
      .map((m) => {
        const resCls = m.is_win ? "win" : (m.winner && m.winner !== "Unknown" ? "loss" : "unk");
        const resTxt = m.is_win ? "WIN" : (m.winner && m.winner !== "Unknown" ? "LOSS" : "—");
        return `<tr>
          <td class="muted-xs">${escapeHtml((m.timestamp || "").slice(0, 16))}</td>
          <td>${escapeHtml(m.trainer_1)} vs. <strong>${escapeHtml(m.trainer_2)}</strong></td>
          <td><span class="result-pill ${resCls}">${resTxt}</span></td>
          <td class="num">${m.turns}</td>
          <td class="num">${m.accuracy_pct != null ? `${m.accuracy_pct.toFixed(1)}%` : "—"}</td>
          <td class="num">${m.variance_events}</td>
        </tr>`;
      })
      .join("");

    body.innerHTML = `
      <div class="kpi-strip">
        <div class="kpi-card">
          <div class="kpi-name">${isEs ? "Win Rate" : "Win Rate"}</div>
          <div class="kpi-value">${d.win_rate_pct.toFixed(1)}% <span class="muted-xs">(${d.wins}-${d.losses})</span></div>
        </div>
        <div class="kpi-card">
          <div class="kpi-name">${isEs ? "Precisión Promedio" : "Avg Accuracy"}</div>
          <div class="kpi-value">${d.avg_accuracy_pct != null ? `${d.avg_accuracy_pct.toFixed(1)}%` : "—"}</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-name">${isEs ? "Partidas / Turnos" : "Matches / Turns"}</div>
          <div class="kpi-value">${d.total_matches} <span class="muted-xs">(${d.total_turns}t)</span></div>
        </div>
        <div class="kpi-card">
          <div class="kpi-name">${isEs ? "Eventos de RNG" : "Variance Events"}</div>
          <div class="kpi-value">${d.total_variance_events}</div>
        </div>
      </div>

      <div class="subhead">${isEs ? "Tendencia de Precisión por Partida" : "Per-Match Accuracy Trend"}</div>
      ${buildSessionAccuracySvg(d.matches)}

      <div class="analytics-grid-2">
        <div class="analytics-card">
          <div class="subhead" style="margin-top:0">${isEs ? "Errores por Fase del Juego" : "Mistakes by Game Phase"}</div>
          ${phaseRows}
        </div>
        <div class="analytics-card">
          <div class="subhead" style="margin-top:0">${isEs ? "Rendimiento por Lead (Turno 1)" : "Lead Pair Performance (Turn 1)"}</div>
          ${
            leadRows
              ? `<table class="data-table"><thead><tr><th>Lead</th><th class="num">W-L</th><th class="num">WR</th></tr></thead><tbody>${leadRows}</tbody></table>`
              : `<div class="muted-xs">${isEs ? "Sin datos de leads aún." : "No lead data yet."}</div>`
          }
        </div>
      </div>

      <div class="subhead">${isEs ? "Historial de Partidas Exportadas" : "Exported Match History"}</div>
      <table class="data-table">
        <thead>
          <tr>
            <th>${isEs ? "Fecha" : "Date"}</th>
            <th>${isEs ? "Cruce" : "Matchup"}</th>
            <th>${isEs ? "Res." : "Res."}</th>
            <th class="num">${isEs ? "Turnos" : "Turns"}</th>
            <th class="num">${isEs ? "Prec." : "Acc."}</th>
            <th class="num">RNG</th>
          </tr>
        </thead>
        <tbody>${matchRows}</tbody>
      </table>
    `;
  }

  function openAnalyticsView() {
    setStep("analytics");
    renderAnalyticsGuideSteps();
    loadAndRenderAnalytics();
  }

  if ($("btn-refresh-analytics")) $("btn-refresh-analytics").onclick = () => loadAndRenderAnalytics();
  if ($("analytics-team-select")) {
    $("analytics-team-select").onchange = (e) => loadAndRenderAnalytics(e.target.value);
  }
  if ($("btn-analytics-create-team")) {
    $("btn-analytics-create-team").onclick = () => {
      createTelemetryTeamFolder($("analytics-new-team-input") ? $("analytics-new-team-input").value : "");
    };
  }
  if ($("analytics-new-team-input")) {
    $("analytics-new-team-input").addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") {
        ev.preventDefault();
        createTelemetryTeamFolder($("analytics-new-team-input").value);
      }
    });
  }
  if ($("btn-analytics-toggle-guide")) {
    $("btn-analytics-toggle-guide").onclick = () => {
      const p = $("analytics-guide-panel");
      if (!p) return;
      p.style.display = p.style.display === "none" ? "block" : "none";
    };
  }
  if ($("btn-analytics-hide-guide")) {
    $("btn-analytics-hide-guide").onclick = () => {
      if ($("analytics-guide-panel")) $("analytics-guide-panel").style.display = "none";
    };
  }
  if ($("btn-analytics-go-bo3")) {
    $("btn-analytics-go-bo3").onclick = () => openBo3CoachView();
  }

  // Bug Report Modal & Direct Email Workflow
  function openBugModal() {
    $("bug-modal").style.display = "flex";
    $("bug-user-message").focus();
  }

  function closeBugModal() {
    $("bug-modal").style.display = "none";
  }

  $("btn-open-bug-modal").onclick = openBugModal;
  $("btn-close-bug-modal").onclick = closeBugModal;
  $("bug-modal").addEventListener("click", (ev) => {
    if (ev.target === $("bug-modal")) closeBugModal();
  });

  $("btn-generate-bug-log").onclick = async () => {
    const isEs = state.lang === "es";
    const userMsg = $("bug-user-message").value || "";
    const curTr = state.turnResults[state.currentTurn] || null;
    const com = curTr ? getActiveCommentary(curTr) : null;
    const pk = profileKey();
    const recentLogs = state.pipelineLogs.slice(-25).map((e) => {
      const m = (e.messages && (e.messages[pk] || e.messages.en_scientific || e.messages.es_vgc)) || "";
      return `[T${e.turn || 0} ${e.phase}] ${m}`;
    });

    const curTurnSummary = curTr
      ? {
          symbol: com ? com.symbol : "",
          badge: com ? com.badge : "",
          field: curTr.field || {},
          played: (curTr.actual_action && curTr.actual_action.desc) || "",
          opp_played: (curTr.actual_action && curTr.actual_action.opp_actual_desc) || "",
          recommended: (curTr.top_actions && curTr.top_actions[0] && curTr.top_actions[0].desc) || "",
          matrix_shape: curTr.matrix_shape,
          total_timelines: curTr.total_timelines,
        }
      : null;

    $("bug-status-msg").textContent = isEs ? "Generando bug log..." : "Generating bug log...";
    const res = await fetch("/api/bug-report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: userMsg,
        context: {
          active_step: state.activeStep,
          lang: state.lang,
          style: state.style,
          num_mc: parseInt($("setup-k-select").value || "128", 10),
          current_turn: state.currentTurn,
          current_turn_summary: curTurnSummary,
          recent_pipeline_logs: recentLogs,
          js_errors: state.jsErrors.slice(-10),
          user_agent: navigator.userAgent,
        },
      }),
    });
    const d = await res.json();
    if (!d.ok) {
      $("bug-status-msg").textContent = `Error: ${d.error || "Unknown"}`;
      return;
    }

    state.lastBugReport = d;
    $("bug-status-msg").textContent = isEs
      ? `Bug log guardado en ${d.file_path} — listo para enviar a ${d.recipient}.`
      : `Bug log saved to ${d.file_path} — ready to email to ${d.recipient}.`;
    $("bug-log-preview").textContent = d.report_text;
    $("bug-log-preview").style.display = "block";
    $("link-email-bug-log").href = d.mailto_url;
    $("link-email-bug-log").style.display = "inline-flex";
    $("btn-download-bug-log").style.display = "inline-flex";
    $("btn-copy-bug-log").style.display = "inline-flex";
  };

  $("btn-download-bug-log").onclick = () => {
    if (!state.lastBugReport) return;
    const blob = new Blob([state.lastBugReport.report_text], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = state.lastBugReport.filename || "coach_porygon_bug_log.md";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  $("btn-copy-bug-log").onclick = async () => {
    if (!state.lastBugReport) return;
    try {
      await navigator.clipboard.writeText(state.lastBugReport.report_text);
      $("bug-status-msg").textContent =
        state.lang === "es" ? "Log copiado al portapapeles." : "Bug log copied to clipboard.";
    } catch (_) {}
  };

  // -------------------------------------------------------------------------
  // Dedicated Topbar View: Zero-AI Offline Base64 Prep Tools
  // -------------------------------------------------------------------------
  function populatePrepRosterSelect() {
    const sel = $("prep-roster-select");
    if (!sel) return;
    const isEs = state.lang === "es";
    const rosters = (state.app && state.app.rosters) || [];
    const prevVal = sel.value;
    if (!rosters.length) {
      sel.innerHTML = `<option value="">${isEs ? "(Sin equipos DuckDB)" : "(No saved rosters)"}</option>`;
      return;
    }
    sel.innerHTML = rosters
      .map((r) => `<option value="${escapeHtml(r.roster_id)}">${escapeHtml(r.display_name || r.roster_id)}</option>`)
      .join("");
    if (prevVal && rosters.some((r) => r.roster_id === prevVal)) {
      sel.value = prevVal;
    } else if (state.selectedRosterId.t1 && rosters.some((r) => r.roster_id === state.selectedRosterId.t1)) {
      sel.value = state.selectedRosterId.t1;
    }
  }

  function updatePrepControlsUI() {
    const isSpeed = state.prep.kind === "speed_tiers";
    if ($("btn-prep-kind-speed")) $("btn-prep-kind-speed").classList.toggle("active", isSpeed);
    if ($("btn-prep-kind-damage")) $("btn-prep-kind-damage").classList.toggle("active", !isSpeed);
    if ($("prep-paste-drawer")) $("prep-paste-drawer").style.display = state.prep.usePaste ? "flex" : "none";
    if ($("prep-roster-select")) $("prep-roster-select").style.display = state.prep.usePaste ? "none" : "inline-block";
    if ($("btn-prep-toggle-paste")) {
      const isEs = state.lang === "es";
      $("btn-prep-toggle-paste").textContent = state.prep.usePaste
        ? (isEs ? "Usar DuckDB" : "Use Saved Roster")
        : (isEs ? "Pegar 66-SP" : "Paste 66-SP");
    }
    if ($("btn-prep-generate")) {
      $("btn-prep-generate").disabled = state.prep.generating;
    }
    if ($("lbl-prep-generate")) {
      const isEs = state.lang === "es";
      $("lbl-prep-generate").textContent = state.prep.generating
        ? (isEs ? "Calculando..." : "Computing...")
        : (isEs ? "Generar" : "Generate");
    }
    const dl = $("btn-prep-download");
    if (dl) {
      if (state.prep.token) {
        dl.href = `/api/prep-tools/download?token=${encodeURIComponent(state.prep.token)}`;
        dl.setAttribute("download", state.prep.filename || "prep_tool_mobile.html");
        dl.classList.remove("disabled");
        dl.setAttribute("aria-disabled", "false");
      } else {
        dl.href = "#";
        dl.classList.add("disabled");
        dl.setAttribute("aria-disabled", "true");
      }
    }
  }

  async function generatePrepToolPreview() {
    const isEs = state.lang === "es";
    const statusEl = $("prep-status-msg");
    const pillEl = $("prep-meta-pill");
    const rosterId = $("prep-roster-select") ? $("prep-roster-select").value : "";
    const pasteText = $("prep-paste-input") ? $("prep-paste-input").value.trim() : "";
    const teamName = $("prep-paste-name") ? $("prep-paste-name").value.trim() : "";
    const topN = parseInt(($("prep-topn-select") && $("prep-topn-select").value) || "50", 10);
    state.prep.topN = topN;

    if (state.prep.usePaste && !pasteText) {
      if (statusEl) {
        statusEl.textContent = isEs
          ? "Pega un equipo 66-SP de Regulation M-C antes de generar."
          : "Paste a Regulation M-C 66-SP team before generating.";
      }
      return;
    }
    if (!state.prep.usePaste && !rosterId) {
      if (statusEl) {
        statusEl.textContent = isEs
          ? "No hay equipos guardados en DuckDB. Usa 'Pegar 66-SP'."
          : "No saved DuckDB rosters found. Click 'Paste 66-SP'.";
      }
      return;
    }

    state.prep.generating = true;
    updatePrepControlsUI();
    if (statusEl) {
      statusEl.textContent =
        state.prep.kind === "damage_matrix"
          ? (isEs
              ? `Precomputando 16 rolls exactos con Smogon Champions (Top ${topN}, 5 Climas × 5 Campos)...`
              : `Pre-computing exact Smogon Champions 16-roll tables (Top ${topN}, 5 Weathers × 5 Terrains)...`)
          : (isEs
              ? `Generando tabla de velocidades Lv.50 (Top ${topN} DuckDB)...`
              : `Building Lv.50 31-IV Speed Tiers (Top ${topN} DuckDB)...`);
    }

    try {
      const payload = {
        kind: state.prep.kind,
        top_n: topN,
        lang: state.lang,
      };
      if (state.prep.usePaste) {
        payload.paste_text = pasteText;
        if (teamName) payload.team_name = teamName;
      } else {
        payload.roster_id = rosterId;
      }

      const res = await fetch("/api/prep-tools/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const d = await res.json();
      if (!res.ok || !d.ok) {
        if (statusEl) statusEl.textContent = `Error: ${d.error || "Generation failed"}`;
        return;
      }

      state.prep.token = d.token;
      state.prep.filename = d.filename;
      state.prep.meta = d;
      if ($("prep-empty-state")) $("prep-empty-state").style.display = "none";
      const frame = $("prep-preview-iframe");
      if (frame) {
        frame.style.display = "block";
        frame.src = d.preview_url;
      }
      if (statusEl) {
        const cacheNote = d.cached ? (isEs ? " · caché" : " · cached") : ` · ${(d.elapsed_ms / 1000).toFixed(2)}s`;
        statusEl.textContent = isEs
          ? `Listo: ${d.team_name} — 100% offline Base64 (${d.size_kb} KB${cacheNote})`
          : `Ready: ${d.team_name} — 100% offline Base64 (${d.size_kb} KB${cacheNote})`;
      }
      if (pillEl) {
        pillEl.style.display = "inline-flex";
        pillEl.textContent =
          d.kind === "damage_matrix"
            ? `Top ${d.top_n} · ${Number(d.calc_count || 0).toLocaleString()} Smogon calcs · ${d.size_kb} KB`
            : `Top ${d.top_n} / ${Number(d.meta_count || 0).toLocaleString()} teams · ${d.size_kb} KB`;
      }
    } catch (err) {
      if (statusEl) statusEl.textContent = `Error: ${String(err)}`;
    } finally {
      state.prep.generating = false;
      updatePrepControlsUI();
    }
  }

  function openPrepToolsView(targetKind) {
    if (targetKind === "speed_tiers" || targetKind === "damage_matrix") {
      state.prep.kind = targetKind;
    }
    populatePrepRosterSelect();
    setStep("prep");
    updatePrepControlsUI();
    if (!state.prep.usePaste && $("prep-roster-select") && $("prep-roster-select").value) {
      generatePrepToolPreview();
    }
  }

  if ($("btn-open-prep-view")) $("btn-open-prep-view").onclick = () => openPrepToolsView();
  if ($("btn-prep-back")) {
    $("btn-prep-back").onclick = () => setStep("home");
  }
  if ($("btn-prep-kind-speed")) {
    $("btn-prep-kind-speed").onclick = () => {
      state.prep.kind = "speed_tiers";
      setStep("prep");
      updatePrepControlsUI();
      if (!state.prep.usePaste || ($("prep-paste-input") && $("prep-paste-input").value.trim())) {
        generatePrepToolPreview();
      }
    };
  }
  if ($("btn-prep-kind-damage")) {
    $("btn-prep-kind-damage").onclick = () => {
      state.prep.kind = "damage_matrix";
      setStep("prep");
      updatePrepControlsUI();
      if (!state.prep.usePaste || ($("prep-paste-input") && $("prep-paste-input").value.trim())) {
        generatePrepToolPreview();
      }
    };
  }
  if ($("btn-prep-toggle-paste")) {
    $("btn-prep-toggle-paste").onclick = () => {
      state.prep.usePaste = !state.prep.usePaste;
      updatePrepControlsUI();
    };
  }
  if ($("btn-prep-generate")) $("btn-prep-generate").onclick = generatePrepToolPreview;
  if ($("prep-roster-select")) {
    $("prep-roster-select").onchange = () => {
      if (!state.prep.usePaste) generatePrepToolPreview();
    };
  }
  if ($("prep-topn-select")) {
    $("prep-topn-select").onchange = () => {
      if (state.prep.token) generatePrepToolPreview();
    };
  }

  // -------------------------------------------------------------------------
  // Coach Porygon VGC Cyber-Tactical Hub Navigation & 4 CTA Cards
  // -------------------------------------------------------------------------
  function openBo3CoachView() {
    if (state.turnResults && Object.keys(state.turnResults).length > 0 && state.matchSummary) {
      setStep("review");
    } else {
      setStep("setup");
    }
  }

  function openLeadLabView() {
    populateLeadLabRosterSelects();
    setStep("lead-lab");
    updateLeadLabControlsUI();
    refreshLeadLabVault();
    scheduleLeadLabCacheLookup(0);
  }

  function openMdScoutView() {
    setStep("md-scout");
    const frame = $("md-scout-iframe");
    if (frame && !state.mdScoutLoaded) {
      frame.src = "/api/reg-md-scout";
      state.mdScoutLoaded = true;
    }
  }

  // -------------------------------------------------------------------------
  // Split DuckDB Own vs. Rival Team Database Explorer (7th Hub CTA Card)
  // -------------------------------------------------------------------------
  state.teamDb = {
    scope: "own",
    archetype: "",
    regulation: "",
    q: "",
    minElo: "",
    rosters: [],
  };

  function openTeamDbView() {
    setStep("team-db");
    refreshTeamDb();
  }

  async function refreshTeamDb() {
    const tdb = state.teamDb;
    const qs = new URLSearchParams();
    if (tdb.scope && tdb.scope !== "all") qs.set("scope", tdb.scope);
    if (tdb.archetype) qs.set("archetype", tdb.archetype);
    if (tdb.regulation) qs.set("regulation", tdb.regulation);
    if (tdb.q) qs.set("q", tdb.q);
    if (tdb.minElo) qs.set("min_elo", tdb.minElo);
    try {
      const res = await fetch(`/api/rosters/search?${qs.toString()}`);
      const data = await res.json();
      if (!res.ok || !data.ok) return;
      tdb.rosters = data.rosters || [];
      if ($("tdb-count-own")) $("tdb-count-own").textContent = String(data.own_count || 0);
      if ($("tdb-count-rival")) $("tdb-count-rival").textContent = String(data.rival_count || 0);
      if ($("tdb-count-all")) $("tdb-count-all").textContent = String(data.total_count || 0);

      // Populate dynamic Archetype & Regulation filter options once/incrementally
      const archSel = $("tdb-filter-arch");
      if (archSel) {
        const curA = archSel.value;
        const isEs = state.lang === "es";
        archSel.innerHTML =
          `<option value="">${isEs ? "Todos los Arquetipos" : "All Archetypes"}</option>` +
          (data.archetypes || []).map((a) => `<option value="${escapeHtml(a)}">${escapeHtml(a)}</option>`).join("");
        archSel.value = curA;
      }
      const regSel = $("tdb-filter-reg");
      if (regSel) {
        const curR = regSel.value;
        const isEs = state.lang === "es";
        regSel.innerHTML =
          `<option value="">${isEs ? "Todas las Regulaciones" : "All Regulations"}</option>` +
          (data.regulations || []).map((rg) => `<option value="${escapeHtml(rg)}">${escapeHtml(rg)}</option>`).join("");
        regSel.value = curR;
      }
      renderTeamDbCards();
    } catch (_) {}
  }

  function renderTeamDbCards() {
    const grid = $("tdb-cards-grid");
    if (!grid) return;
    const isEs = state.lang === "es";
    const rows = (state.teamDb && state.teamDb.rosters) || [];
    if (!rows.length) {
      grid.innerHTML = `<div class="panel" style="padding:20px;text-align:center;color:#94a3b8;grid-column:1/-1">
        ${isEs ? "No hay equipos que coincidan con estos filtros en DuckDB." : "No teams match the current DuckDB filters."}
      </div>`;
      return;
    }
    grid.innerHTML = rows
      .map((r) => {
        const isRival = r.team_scope === "rival";
        const scopeBadge = isRival
          ? `<span class="cyber-pill gold-pill">${isEs ? "🛡 Rival" : "🛡 Rival"}</span>`
          : `<span class="cyber-pill cyan-pill">${isEs ? "🏠 Propio" : "🏠 Own"}</span>`;
        const eloBadge =
          r.source_type === "showdown_ladder"
            ? `<span class="tdb-elo-chip">${escapeHtml(r.source_legend || "Showdown Opponent")}</span>`
            : "";
        const spritesHtml = (r.species_sprites || [])
          .map(
            (sp) =>
              `<div class="tdb-mon-chip" title="${escapeHtml(sp.species)}">${
                sp.sprite_url ? `<img src="${escapeHtml(sp.sprite_url)}" alt="${escapeHtml(sp.species)}" />` : ""
              }<span>${escapeHtml(sp.species)}</span></div>`
          )
          .join("");
        return `<article class="panel tdb-card ${isRival ? "is-rival" : "is-own"}" data-tdb-rid="${escapeHtml(r.roster_id)}">
          <div class="tdb-card-head">
            <div>
              <div class="tdb-card-title">${escapeHtml(r.display_name || r.roster_id)}</div>
              <div class="tdb-meta-chips">
                ${scopeBadge}
                <span class="tag-neutral">${escapeHtml(r.archetype || "Balance")}</span>
                <span class="tag-neutral">${escapeHtml(r.regulation || "Reg M-C")}</span>
                ${eloBadge}
              </div>
            </div>
            <button class="btn btn-ghost btn-xs tdb-del-btn" type="button" data-tdb-del="${escapeHtml(r.roster_id)}" title="${isEs ? "Eliminar de DuckDB" : "Delete from DuckDB"}">✕</button>
          </div>
          <div class="tdb-sprites-row">${spritesHtml}</div>
          <div class="tdb-card-actions">
            <button class="btn btn-ghost btn-xs" type="button" data-tdb-flip="${escapeHtml(r.roster_id)}" data-tdb-next-scope="${isRival ? "own" : "rival"}">
              ${isRival ? (isEs ? "Mover a Propios" : "Move to Own") : (isEs ? "Mover a Rivales" : "Move to Rivals")}
            </button>
            <button class="btn btn-ghost btn-xs" type="button" data-tdb-copy="${escapeHtml(r.roster_id)}">${isEs ? "📋 Copiar" : "📋 Copy"}</button>
            <button class="btn btn-ghost btn-xs" type="button" data-tdb-prep="${escapeHtml(r.roster_id)}">⚡ Prep</button>
            <button class="btn btn-gold btn-xs" type="button" data-tdb-ll="${escapeHtml(r.roster_id)}" data-tdb-side="${isRival ? "t2" : "t1"}">
              🎯 ${isRival ? "Lead Lab (Rival)" : "Lead Lab (T1)"}
            </button>
          </div>
        </article>`;
      })
      .join("");

    grid.querySelectorAll("[data-tdb-del]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const rid = btn.dataset.tdbDel;
        const res = await fetch("/api/rosters/delete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ roster_id: rid }),
        });
        const d = await res.json();
        if (res.ok && d.rosters) {
          if (state.app) state.app.rosters = d.rosters;
          populateLeadLabRosterSelects();
          populatePrepRosterSelect();
          refreshTeamDb();
        }
      });
    });

    grid.querySelectorAll("[data-tdb-flip]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const rid = btn.dataset.tdbFlip;
        const nextScope = btn.dataset.tdbNextScope;
        const res = await fetch("/api/rosters/update-meta", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ roster_id: rid, team_scope: nextScope }),
        });
        const d = await res.json();
        if (res.ok && d.rosters) {
          if (state.app) state.app.rosters = d.rosters;
          populateLeadLabRosterSelects();
          refreshTeamDb();
        }
      });
    });

    grid.querySelectorAll("[data-tdb-copy]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const row = rows.find((x) => x.roster_id === btn.dataset.tdbCopy);
        if (!row) return;
        try {
          await navigator.clipboard.writeText(row.paste_text || "");
          btn.textContent = isEs ? "✓ Copiado" : "✓ Copied";
          setTimeout(() => { btn.textContent = isEs ? "📋 Copiar" : "📋 Copy"; }, 1200);
        } catch (_) {}
      });
    });

    grid.querySelectorAll("[data-tdb-prep]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const rid = btn.dataset.tdbPrep;
        openPrepToolsView("speed_tiers");
        if ($("prep-roster-select")) {
          $("prep-roster-select").value = rid;
          state.prep.usePaste = false;
          updatePrepControlsUI();
          generatePrepToolPreview();
        }
      });
    });

    grid.querySelectorAll("[data-tdb-ll]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const rid = btn.dataset.tdbLl;
        const side = btn.dataset.tdbSide || "t1";
        openLeadLabView();
        if (side === "t2") {
          state.leadLab.t2Mode = "full";
          state.leadLab.t2UsePaste = false;
          if ($("ll-t2-roster-select")) $("ll-t2-roster-select").value = rid;
        } else {
          state.leadLab.t1UsePaste = false;
          if ($("ll-t1-roster-select")) $("ll-t1-roster-select").value = rid;
        }
        updateLeadLabControlsUI();
        renderLeadLabRosterPreview(side);
        scheduleLeadLabCacheLookup(0);
      });
    });
  }

  if ($("btn-go-home")) $("btn-go-home").onclick = () => setStep("home");
  if ($("nav-hub-speed")) $("nav-hub-speed").onclick = () => openPrepToolsView("speed_tiers");
  if ($("nav-hub-damage")) $("nav-hub-damage").onclick = () => openPrepToolsView("damage_matrix");
  if ($("nav-hub-bo3")) $("nav-hub-bo3").onclick = () => openBo3CoachView();
  if ($("nav-hub-lead-lab")) $("nav-hub-lead-lab").onclick = () => openLeadLabView();
  if ($("nav-hub-analytics")) $("nav-hub-analytics").onclick = () => openAnalyticsView();
  if ($("nav-hub-md-scout")) $("nav-hub-md-scout").onclick = () => openMdScoutView();
  if ($("nav-hub-team-db")) $("nav-hub-team-db").onclick = () => openTeamDbView();

  if ($("cta-card-speed")) $("cta-card-speed").onclick = () => openPrepToolsView("speed_tiers");
  if ($("cta-card-damage")) $("cta-card-damage").onclick = () => openPrepToolsView("damage_matrix");
  if ($("cta-card-bo3")) $("cta-card-bo3").onclick = () => openBo3CoachView();
  if ($("cta-card-lead-lab")) $("cta-card-lead-lab").onclick = () => openLeadLabView();
  if ($("cta-card-analytics")) $("cta-card-analytics").onclick = () => openAnalyticsView();
  if ($("cta-card-md-scout")) $("cta-card-md-scout").onclick = () => openMdScoutView();
  if ($("cta-card-team-db")) $("cta-card-team-db").onclick = () => openTeamDbView();
  if ($("btn-md-scout-back")) $("btn-md-scout-back").onclick = () => setStep("home");
  if ($("btn-tdb-back")) $("btn-tdb-back").onclick = () => setStep("home");

  if ($("btn-tdb-toggle-import")) {
    $("btn-tdb-toggle-import").onclick = () => {
      const dr = $("tdb-import-drawer");
      if (dr) dr.style.display = dr.style.display === "none" ? "block" : "none";
    };
  }
  if ($("btn-tdb-close-import")) {
    $("btn-tdb-close-import").onclick = () => {
      const dr = $("tdb-import-drawer");
      if (dr) dr.style.display = "none";
    };
  }
  if ($("btn-tdb-save-import")) {
    $("btn-tdb-save-import").onclick = async () => {
      const paste = ($("tdb-imp-paste") && $("tdb-imp-paste").value.trim()) || "";
      const scope = ($("tdb-imp-scope") && $("tdb-imp-scope").value) || "own";
      const dname = ($("tdb-imp-name") && $("tdb-imp-name").value.trim()) || "";
      const reg = ($("tdb-imp-reg") && $("tdb-imp-reg").value) || "Reg M-C";
      const arch = ($("tdb-imp-arch") && $("tdb-imp-arch").value) || "";
      const eloRaw = ($("tdb-imp-elo") && $("tdb-imp-elo").value.trim()) || "";
      const stEl = $("tdb-imp-status");
      if (!paste) {
        if (stEl) stEl.textContent = state.lang === "es" ? "Pega un Showdown Paste válido." : "Paste a valid Showdown team first.";
        return;
      }
      const rid = `${scope}_${Date.now().toString(36)}`;
      const res = await fetch("/api/rosters", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          roster_id: rid,
          display_name: dname || (scope === "rival" ? "Showdown Opponent" : "My Team"),
          trainer_hint: scope === "rival" ? "Showdown Opponent" : "trainer_1",
          paste_text: paste,
          team_scope: scope,
          archetype: arch,
          regulation: reg,
          source_type: scope === "rival" ? "showdown_ladder" : "personal",
          opponent_elo: eloRaw ? parseInt(eloRaw, 10) : null,
        }),
      });
      const d = await res.json();
      if (!res.ok || d.error) {
        if (stEl) stEl.textContent = `Error: ${d.error || "Save failed"}`;
        return;
      }
      if (state.app && d.rosters) state.app.rosters = d.rosters;
      if ($("tdb-imp-paste")) $("tdb-imp-paste").value = "";
      if ($("tdb-imp-name")) $("tdb-imp-name").value = "";
      if ($("tdb-import-drawer")) $("tdb-import-drawer").style.display = "none";
      populateLeadLabRosterSelects();
      populatePrepRosterSelect();
      refreshTeamDb();
    };
  }
  document.querySelectorAll("#tdb-scope-tabs [data-tdb-scope]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#tdb-scope-tabs [data-tdb-scope]").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.teamDb.scope = btn.dataset.tdbScope || "own";
      refreshTeamDb();
    });
  });
  if ($("tdb-search-input")) {
    $("tdb-search-input").addEventListener("input", () => {
      state.teamDb.q = $("tdb-search-input").value.trim();
      refreshTeamDb();
    });
  }
  if ($("tdb-filter-arch")) {
    $("tdb-filter-arch").addEventListener("change", () => {
      state.teamDb.archetype = $("tdb-filter-arch").value;
      refreshTeamDb();
    });
  }
  if ($("tdb-filter-reg")) {
    $("tdb-filter-reg").addEventListener("change", () => {
      state.teamDb.regulation = $("tdb-filter-reg").value;
      refreshTeamDb();
    });
  }
  if ($("tdb-filter-elo")) {
    $("tdb-filter-elo").addEventListener("input", () => {
      state.teamDb.minElo = $("tdb-filter-elo").value.trim();
      refreshTeamDb();
    });
  }

  // -------------------------------------------------------------------------
  // Factored 90×90 Turn-1 Lead & Bring Lab Controller
  // -------------------------------------------------------------------------
  function scoreCellBg(score) {
    const v = Math.max(-1.2, Math.min(1.2, Number(score || 0)));
    if (v >= 0.08) {
      const a = Math.min(0.62, 0.14 + (v / 1.2) * 0.48);
      return `rgba(34, 197, 94, ${a.toFixed(2)})`;
    }
    if (v <= -0.08) {
      const a = Math.min(0.62, 0.14 + (-v / 1.2) * 0.48);
      return `rgba(244, 63, 94, ${a.toFixed(2)})`;
    }
    return "rgba(100, 116, 139, 0.18)";
  }

  function scoreTextColor(score) {
    const v = Number(score || 0);
    if (v >= 0.08) return "#bbf7d0";
    if (v <= -0.08) return "#fecdd3";
    return "#cbd5e1";
  }

  function miniSpriteImg(spName, spritesMap) {
    const rec = spritesMap && spritesMap[spName];
    const url = rec && rec.sprite_url;
    if (!url) return "";
    return `<img class="ll-mini-spr" src="${escapeHtml(url)}" alt="${escapeHtml(spName)}" title="${escapeHtml(spName)}" loading="lazy" />`;
  }

  function renderLeadLabRosterPreview(side) {
    const sel = $(`ll-${side}-roster-select`);
    const box = $(`ll-${side}-preview`);
    if (!sel || !box) return;
    const rosters = (state.app && state.app.rosters) || [];
    const found = rosters.find((r) => r.roster_id === sel.value);
    const mons = (found && (found.species_sprites || found.pokemon)) || [];
    if (!mons.length) {
      box.innerHTML = "";
      return;
    }
    box.innerHTML = mons
      .map(
        (m) =>
          `<span class="ll-mon-chip">${spritePairHtml(m.sprite_url, m.item_sprite_url, m.species, m.item)}<span>${escapeHtml(m.species)}</span></span>`
      )
      .join("");
  }

  function populateLeadLabRosterSelects() {
    const rosters = (state.app && state.app.rosters) || [];
    const ownRows = rosters.filter((r) => (r.team_scope || "own") !== "rival");
    const rivalRows = rosters.filter((r) => (r.team_scope || "own") === "rival");
    const isEs = state.lang === "es";

    const buildGroupedOptions = (primaryList, secondaryList, primaryLbl, secondaryLbl) => {
      const mkOpts = (arr) =>
        arr
          .map(
            (r) =>
              `<option value="${escapeHtml(r.roster_id)}">${escapeHtml(r.display_name || r.roster_id)}${
                r.archetype ? ` [${escapeHtml(r.archetype)}]` : ""
              }</option>`
          )
          .join("");
      let htmlOut = "";
      if (primaryList.length) htmlOut += `<optgroup label="${escapeHtml(primaryLbl)}">${mkOpts(primaryList)}</optgroup>`;
      if (secondaryList.length) htmlOut += `<optgroup label="${escapeHtml(secondaryLbl)}">${mkOpts(secondaryList)}</optgroup>`;
      return htmlOut;
    };

    ["t1", "t2"].forEach((side) => {
      const sel = $(`ll-${side}-roster-select`);
      if (!sel) return;
      const prev = sel.value;
      if (!rosters.length) {
        sel.innerHTML = `<option value="">${isEs ? "(Sin equipos DuckDB)" : "(No DuckDB rosters)"}</option>`;
        return;
      }
      const isT1 = side === "t1";
      sel.innerHTML = isT1
        ? buildGroupedOptions(
            ownRows,
            rivalRows,
            isEs ? "🏠 Mis Equipos" : "🏠 Own Teams",
            isEs ? "🛡 Equipos Rivales" : "🛡 Rival Teams"
          )
        : buildGroupedOptions(
            rivalRows,
            ownRows,
            isEs ? "🛡 Equipos Rivales (Showdown / Scout)" : "🛡 Rival Teams (Showdown / Scout)",
            isEs ? "🏠 Mis Equipos" : "🏠 Own Teams"
          );
      if (prev && rosters.some((r) => r.roster_id === prev)) {
        sel.value = prev;
      } else if (isT1 && ownRows.length) {
        sel.value = ownRows[0].roster_id;
      } else if (!isT1 && rivalRows.length) {
        sel.value = rivalRows[0].roster_id;
      } else {
        sel.value = rosters[0].roster_id;
      }
      renderLeadLabRosterPreview(side);
    });
  }

  function updateLeadLabControlsUI() {
    const isEs = state.lang === "es";
    const ll = state.leadLab;
    if ($("ll-t1-paste-drawer")) $("ll-t1-paste-drawer").style.display = ll.t1UsePaste ? "block" : "none";
    if ($("ll-t1-roster-select")) $("ll-t1-roster-select").style.display = ll.t1UsePaste ? "none" : "block";
    if ($("ll-t1-preview")) $("ll-t1-preview").style.display = ll.t1UsePaste ? "none" : "flex";
    if ($("btn-ll-t1-paste")) {
      $("btn-ll-t1-paste").textContent = ll.t1UsePaste
        ? (isEs ? "Usar DuckDB" : "Use Saved Roster")
        : (isEs ? "Pegar 66-SP" : "Paste 66-SP");
    }

    const isScout = ll.t2Mode === "scout";
    if ($("btn-ll-t2-mode-full")) $("btn-ll-t2-mode-full").classList.toggle("active", !isScout);
    if ($("btn-ll-t2-mode-scout")) $("btn-ll-t2-mode-scout").classList.toggle("active", isScout);
    if ($("ll-t2-full-box")) $("ll-t2-full-box").style.display = isScout ? "none" : "block";
    if ($("ll-t2-scout-box")) $("ll-t2-scout-box").style.display = isScout ? "block" : "none";

    if ($("ll-t2-paste-drawer")) $("ll-t2-paste-drawer").style.display = ll.t2UsePaste ? "block" : "none";
    if ($("ll-t2-roster-select")) $("ll-t2-roster-select").style.display = ll.t2UsePaste ? "none" : "block";
    if ($("ll-t2-preview")) $("ll-t2-preview").style.display = ll.t2UsePaste ? "none" : "flex";
    if ($("btn-ll-t2-paste")) {
      $("btn-ll-t2-paste").textContent = ll.t2UsePaste
        ? (isEs ? "Usar DuckDB" : "Use Saved Roster")
        : (isEs ? "Pegar 66-SP" : "Paste 66-SP");
    }

    if ($("btn-ll-t2-solve-sp")) $("btn-ll-t2-solve-sp").disabled = ll.scoutReplays.length === 0;
    if ($("btn-ll-launch")) $("btn-ll-launch").disabled = ll.running;
    if ($("btn-ll-cancel")) {
      $("btn-ll-cancel").disabled = !ll.running;
      $("btn-ll-cancel").style.display = "inline-flex";
    }
    if ($("btn-ll-cancel-bar")) {
      $("btn-ll-cancel-bar").style.display = ll.running ? "inline-flex" : "none";
      $("btn-ll-cancel-bar").disabled = !ll.running;
    }
    if ($("lbl-ll-launch")) {
      $("lbl-ll-launch").textContent = ll.running
        ? (isEs ? "Simulando..." : "Simulating...")
        : (isEs ? "Simular 90×90 Leads →" : "Run 90×90 Lead Nash →");
    }
  }

  function renderLeadLabClampedSpPanel() {
    const panel = $("ll-t2-clamped-panel");
    const list = $("ll-t2-clamped-list");
    const inf = state.leadLab.t2Inference;
    if (!panel || !list) return;
    if (!inf || !inf.pokemon || !inf.pokemon.length) {
      panel.style.display = "none";
      return;
    }
    const isEs = state.lang === "es";
    panel.style.display = "block";
    if ($("ll-t2-solver-badge")) {
      $("ll-t2-solver-badge").textContent = `${inf.games_pooled > 1 ? `Bo3 (${inf.games_pooled}G)` : "Bo1"} · OTS 66-SP`;
    }
    if ($("ll-t2-solver-sub")) {
      $("ll-t2-solver-sub").textContent = `${inf.total_smogon_calcs} calcs · ${inf.elapsed_ms}ms`;
    }
    list.innerHTML = inf.pokemon
      .map((m, mIdx) => {
        const spObj = state.leadLab.t2UserSpreads[m.base_species] || Object.assign({}, m.default_spread);
        state.leadLab.t2UserSpreads[m.base_species] = spObj;
        const totSp = STAT_KEYS.reduce((a, k) => a + Number(spObj[k] || 0), 0);
        const remSp = 66 - totSp;
        const budCls = remSp === 0 ? "ok" : "warn";
        const budTxt = remSp === 0 ? "66 / 66 SP" : `${totSp}/66`;

        const rowsHtml = STAT_KEYS.map((sk) => {
          const b = (m.bounds && m.bounds[sk]) || { min_sp: 0, max_sp: 32, locked: false, status: "unobserved", evidence: [] };
          const curVal = Number(spObj[sk] || 0);
          const l50 = calcChampionsL50Stat(sk, (m.base_stats || {})[sk], curVal, m.nature);
          const pillTxt = b.locked ? `🔒 ${b.min_sp}` : b.status === "bounded" ? `${b.min_sp}..${b.max_sp}` : (isEs ? "Libre" : "Open");
          const leftPct = (b.min_sp / 32.0) * 100.0;
          const widthPct = b.locked ? 4.0 : Math.max(3.0, ((b.max_sp - b.min_sp) / 32.0) * 100.0);
          return `<div class="sp-stat-row">
            <span class="sp-stat-lbl">${STAT_LABELS[sk]}</span>
            <span class="sp-bound-pill ${b.status}">${escapeHtml(pillTxt)}</span>
            <div class="sp-slider-wrap">
              <div class="sp-track-bg">
                <div class="sp-track-feasible ${b.locked ? "pinned" : ""}" style="left:${leftPct.toFixed(1)}%;width:${Math.min(100 - leftPct, widthPct).toFixed(1)}%"></div>
              </div>
              <input type="range" class="sp-range ll-sp-range"
                min="0" max="32" step="1" value="${curVal}"
                data-mon-idx="${mIdx}" data-species="${escapeHtml(m.base_species)}" data-stat="${sk}"
                data-min-sp="${b.min_sp}" data-max-sp="${b.max_sp}"
                ${b.locked ? "disabled" : ""} />
            </div>
            <span class="sp-val-cell" id="ll-sp-val-${mIdx}-${sk}">${curVal} SP</span>
            <span class="sp-l50-cell" id="ll-sp-l50-${mIdx}-${sk}">(${l50})</span>
          </div>`;
        }).join("");

        return `<div class="sp-mon-card">
          <div class="sp-mon-head">
            <div class="sp-mon-head-left">
              ${spritePairHtml(m.sprite_url, m.item_sprite_url, m.base_species, m.item)}
              <div class="ots-row-info">
                <div class="ots-row-name">${escapeHtml(m.base_species)} <span class="muted-xs">· ${escapeHtml(m.nature || "")}</span></div>
                <div class="ots-row-sub">${escapeHtml(m.item || "No Item")} · ${escapeHtml(m.ability || "")}</div>
              </div>
            </div>
            <span class="sp-budget-pill ${budCls}" id="ll-sp-budget-${mIdx}">${budTxt}</span>
          </div>
          <div class="sp-rows">${rowsHtml}</div>
        </div>`;
      })
      .join("");

    list.querySelectorAll(".ll-sp-range").forEach((inp) => {
      inp.addEventListener("input", () => {
        const mIdx = parseInt(inp.dataset.monIdx, 10);
        const spName = inp.dataset.species;
        const sk = inp.dataset.stat;
        const minSp = parseInt(inp.dataset.minSp, 10);
        const maxSp = parseInt(inp.dataset.maxSp, 10);
        const mon = state.leadLab.t2Inference.pokemon[mIdx];
        const curObj = state.leadLab.t2UserSpreads[spName];
        if (!mon || !curObj) return;
        let rawV = parseInt(inp.value, 10);
        let clamped = Math.max(minSp, Math.min(maxSp, rawV));
        const otherSum = STAT_KEYS.reduce((a, k) => a + (k === sk ? 0 : Number(curObj[k] || 0)), 0);
        clamped = Math.min(clamped, Math.max(minSp, Math.min(maxSp, 66 - otherSum)));
        if (clamped !== rawV) inp.value = String(clamped);
        curObj[sk] = clamped;
        const l50 = calcChampionsL50Stat(sk, (mon.base_stats || {})[sk], clamped, mon.nature);
        if ($(`ll-sp-val-${mIdx}-${sk}`)) $(`ll-sp-val-${mIdx}-${sk}`).textContent = `${clamped} SP`;
        if ($(`ll-sp-l50-${mIdx}-${sk}`)) $(`ll-sp-l50-${mIdx}-${sk}`).textContent = `(${l50})`;
        const totSp = STAT_KEYS.reduce((a, k) => a + Number(curObj[k] || 0), 0);
        const bp = $(`ll-sp-budget-${mIdx}`);
        if (bp) {
          bp.className = `sp-budget-pill ${totSp === 66 ? "ok" : "warn"}`;
          bp.textContent = totSp === 66 ? "66 / 66 SP" : `${totSp}/66`;
        }
      });
    });
  }

  function renderLeadLabHeatmapSkeleton(meta) {
    const container = $("ll-heatmap-container");
    if (!container || !meta) return;
    const spr = meta.sprites || {};
    const t1Leads = meta.t1_leads || [];
    const t2Leads = meta.t2_leads || [];

    const hdrCols = t2Leads
      .map(
        (pair, j) =>
          `<th title="T2 Lead #${j + 1}: ${escapeHtml(pair[0])} + ${escapeHtml(pair[1])}">
            <div class="ll-hm-spr-pair">${miniSpriteImg(pair[0], spr)}${miniSpriteImg(pair[1], spr)}</div>
            <div>${escapeHtml(pair[0].slice(0, 6))}/${escapeHtml(pair[1].slice(0, 6))}</div>
          </th>`
      )
      .join("");

    const bodyRows = t1Leads
      .map((pair1, i) => {
        const cells = t2Leads
          .map(
            (_, j) =>
              `<td class="ll-hm-cell" id="ll-cell-${i}-${j}" data-l1="${i}" data-l2="${j}">·</td>`
          )
          .join("");
        return `<tr>
          <th class="ll-hm-row-hdr" title="T1 Lead #${i + 1}: ${escapeHtml(pair1[0])} + ${escapeHtml(pair1[1])}">
            <span class="ll-hm-spr-pair">${miniSpriteImg(pair1[0], spr)}${miniSpriteImg(pair1[1], spr)}</span>
            <span>${escapeHtml(pair1[0])} + ${escapeHtml(pair1[1])}</span>
          </th>
          ${cells}
        </tr>`;
      })
      .join("");

    container.innerHTML = `<table class="ll-hm-table">
      <thead><tr><th class="ll-hm-row-hdr">T1 Leads \\ T2 Leads</th>${hdrCols}</tr></thead>
      <tbody>${bodyRows}</tbody>
    </table>`;

    container.querySelectorAll(".ll-hm-cell").forEach((td) => {
      td.addEventListener("click", () => {
        if (!state.leadLab.result) return;
        const l1 = parseInt(td.dataset.l1, 10);
        const l2 = parseInt(td.dataset.l2, 10);
        selectLeadLabCell(l1, l2);
      });
    });
  }

  function updateLeadLabHeatmapCell(cellEv) {
    const td = $(`ll-cell-${cellEv.lead_1_idx}-${cellEv.lead_2_idx}`);
    if (!td) return;
    const sc = Number(cellEv.score || 0);
    td.textContent = (sc >= 0 ? "+" : "") + sc.toFixed(2);
    td.style.background = scoreCellBg(sc);
    td.style.color = scoreTextColor(sc);
    td.classList.add("ready");
    td.title = `v*=${sc >= 0 ? "+" : ""}${sc.toFixed(3)} | T1 Back: ${(cellEv.best_t1_bench || []).join(" + ")} | ${cellEv.t1_opening || ""}`;
  }

  function renderLeadLabPodium(res) {
    const grid = $("ll-podium-grid");
    const t1List = $("ll-t1-podium-list");
    const t2List = $("ll-t2-counter-list");
    if (!grid || !t1List || !t2List || !res) return;
    const isEs = state.lang === "es";
    const isSci = state.style === "scientific";
    const spr = res.sprites || {};
    grid.style.display = "grid";

    const llBetaHost = $("ll-beta-bar");
    if (llBetaHost) {
      llBetaHost.innerHTML = renderQreBetaControlHtml("lead-lab");
      bindQreBetaControl(llBetaHost, () => {
        renderLeadLabPodium(res);
        if (state.turnResults[state.currentTurn]) renderTurnPanel(state.turnResults[state.currentTurn]);
      });
    }

    const llLiveQre = getLeadLabLiveQre(res);
    const gv = Number(res.global_game_value || 0);
    if ($("ll-global-value-pill")) {
      const valPrefix = isSci ? "Nash v*" : (isEs ? "Ventaja" : "Edge");
      $("ll-global-value-pill").textContent = `${valPrefix} = ${gv >= 0 ? "+" : ""}${gv.toFixed(isSci ? 3 : 2)}`;
    }
    if ($("ll-modes-meta-pill")) {
      $("ll-modes-meta-pill").textContent = `${Number(res.total_modes_evaluated || 0).toLocaleString()} ${isEs ? "modos" : "modes"} · ${res.elapsed_s}s`;
    }

    const mixLbl = isSci ? "Nash" : "Mix";
    const humLbl = isSci ? "QRE" : (isEs ? "Hum." : "Hum.");
    const scoreLbl = isSci ? "EV" : (isEs ? "Vent." : "Score");

    t1List.innerHTML = (res.trainer_1_top_brings || [])
      .slice(0, 8)
      .map((b) => {
        const nashPct = (Number(b.nash_weight || 0) * 100).toFixed(1);
        const liveQ =
          llLiveQre && typeof b.mode_idx === "number" && b.mode_idx < llLiveQre.p.length
            ? llLiveQre.p[b.mode_idx] * 100.0
            : Number(b.qre_weight || 0) * 100.0;
        const ev = Number(b.ev_vs_opp_nash || 0);
        const fl = Number(b.worst_case_floor || 0);
        return `<div class="ll-bring-row ${b.nash_weight > 0.01 ? "top-nash" : ""}" data-jump-l1="${b.lead_idx}" data-jump-b1="${b.bench_idx}">
          <div class="ll-bring-left">
            <span class="ll-rank-num">#${b.rank}</span>
            <div class="ll-squad-pair">
              <div class="ll-lead-line">
                ${miniSpriteImg(b.lead_species[0], spr)}${miniSpriteImg(b.lead_species[1], spr)}
                <span>${escapeHtml(b.lead_species[0])} + ${escapeHtml(b.lead_species[1])}</span>
              </div>
              <div class="ll-bench-line">
                <span>${isEs ? "Banca:" : "Back:"}</span>
                ${miniSpriteImg(b.bench_species[0], spr)}${miniSpriteImg(b.bench_species[1], spr)}
                <span>${escapeHtml(b.bench_species[0])} + ${escapeHtml(b.bench_species[1])}</span>
              </div>
            </div>
          </div>
          <div class="ll-bring-metrics">
            <div class="ll-metric-pill nash"><small>${mixLbl}</small><strong>${nashPct}%</strong></div>
            <div class="ll-metric-pill"><small>${humLbl}</small><strong>${liveQ.toFixed(1)}%</strong></div>
            <div class="ll-metric-pill ${ev >= 0 ? "pos" : "neg"}"><small>${scoreLbl}</small><strong>${ev >= 0 ? "+" : ""}${ev.toFixed(2)}</strong></div>
            <div class="ll-metric-pill ${fl >= 0 ? "pos" : "neg"}"><small>${isEs ? "Piso" : "Floor"}</small><strong>${fl >= 0 ? "+" : ""}${fl.toFixed(2)}</strong></div>
          </div>
        </div>`;
      })
      .join("");

    t1List.querySelectorAll(".ll-bring-row").forEach((row) => {
      row.addEventListener("click", () => {
        const l1 = parseInt(row.dataset.jumpL1, 10);
        const b1 = parseInt(row.dataset.jumpB1, 10);
        const oppTop = (res.trainer_2_top_brings && res.trainer_2_top_brings[0]) || { lead_idx: 0, bench_idx: 0 };
        selectLeadLabCell(l1, oppTop.lead_idx, b1, oppTop.bench_idx);
      });
    });

    t2List.innerHTML = (res.trainer_2_top_brings || [])
      .slice(0, 6)
      .map((o) => {
        const oppPct = (Number(o.opp_nash_weight || 0) * 100).toFixed(1);
        const oppLiveQ =
          llLiveQre && typeof o.mode_idx === "number" && o.mode_idx < llLiveQre.q.length
            ? llLiveQre.q[o.mode_idx] * 100.0
            : Number(o.opp_qre_weight || 0) * 100.0;
        const cScore = Number(o.best_counter_score || 0);
        const counterMode = (res.modes_t1 || [])[o.best_counter_mode_idx];
        const cL1 = counterMode ? counterMode.lead_idx : 0;
        const cB1 = counterMode ? counterMode.bench_idx : 0;
        return `<div class="ll-bring-row" data-jump-l1="${cL1}" data-jump-l2="${o.lead_idx}" data-jump-b1="${cB1}" data-jump-b2="${o.bench_idx}">
          <div class="ll-bring-left">
            <span class="ll-rank-num">#${o.rank}</span>
            <div class="ll-squad-pair">
              <div class="ll-lead-line">
                ${miniSpriteImg(o.lead_species[0], spr)}${miniSpriteImg(o.lead_species[1], spr)}
                <span>${escapeHtml(o.lead_species[0])} + ${escapeHtml(o.lead_species[1])}</span>
                <span class="muted-xs">(${mixLbl} ${oppPct}% · ${humLbl} ${oppLiveQ.toFixed(1)}%)</span>
              </div>
              <div class="ll-bench-line">
                <strong style="color:#67e8f9">${isEs ? "Tu Counter:" : "Counter:"}</strong>
                ${miniSpriteImg(o.best_counter_lead[0], spr)}${miniSpriteImg(o.best_counter_lead[1], spr)}
                <span>${escapeHtml(o.best_counter_lead[0])} + ${escapeHtml(o.best_counter_lead[1])}</span>
                <span class="muted-xs">[${escapeHtml(o.best_counter_bench.join(" / "))}]</span>
              </div>
            </div>
          </div>
          <div class="ll-bring-metrics">
            <div class="ll-metric-pill ${cScore >= 0 ? "pos" : "neg"}"><small>Counter</small><strong>${cScore >= 0 ? "+" : ""}${cScore.toFixed(2)}</strong></div>
          </div>
        </div>`;
      })
      .join("");

    t2List.querySelectorAll(".ll-bring-row").forEach((row) => {
      row.addEventListener("click", () => {
        selectLeadLabCell(
          parseInt(row.dataset.jumpL1, 10),
          parseInt(row.dataset.jumpL2, 10),
          parseInt(row.dataset.jumpB1, 10),
          parseInt(row.dataset.jumpB2, 10)
        );
      });
    });

    renderLeadLabPlaybook();
  }

  function _collectUniqueTopLeads(brings, maxCount) {
    const out = [];
    const seen = new Set();
    for (const b of brings || []) {
      const lIdx = Number(b.lead_idx);
      if (seen.has(lIdx)) continue;
      seen.add(lIdx);
      out.push(b);
      if (out.length >= (maxCount || 5)) break;
    }
    return out;
  }

  function _getActivePlaybookPairs() {
    const res = state.leadLab.result;
    if (!res || !res.heatmap_cells || !res.heatmap_cells.length) return { mode: "by_mine", anchors: [], selectedAnchor: null, pairs: [] };
    const mode = state.leadLab.playbookMode || "by_mine";
    const ownTop = _collectUniqueTopLeads(res.trainer_1_top_brings, 5);
    const oppTop = _collectUniqueTopLeads(res.trainer_2_top_brings, 6);
    if (!ownTop.length || !oppTop.length) return { mode, anchors: [], selectedAnchor: null, pairs: [] };

    const anchors = mode === "by_mine" ? ownTop : oppTop;
    let selIdx = state.leadLab.playbookSelectedIdx;
    if (selIdx === null || !anchors.some((a) => Number(a.lead_idx) === Number(selIdx))) {
      selIdx = Number(anchors[0].lead_idx);
      state.leadLab.playbookSelectedIdx = selIdx;
    }
    const selectedAnchor = anchors.find((a) => Number(a.lead_idx) === Number(selIdx)) || anchors[0];
    const targets = mode === "by_mine" ? oppTop : ownTop;

    const pairs = [];
    for (const tgt of targets) {
      const l1 = mode === "by_mine" ? Number(selectedAnchor.lead_idx) : Number(tgt.lead_idx);
      const l2 = mode === "by_mine" ? Number(tgt.lead_idx) : Number(selectedAnchor.lead_idx);
      const cell = res.heatmap_cells[l1] && res.heatmap_cells[l1][l2];
      if (!cell) continue;
      // Pick the Nash-best bench pairing for this exact (own_lead, opp_lead) pair
      const b1 = Number(cell.best_t1_bench_idx || 0);
      const b2 = Number(cell.best_t2_bench_idx || 0);
      const b1Labels = (cell.t1_bench_labels && cell.t1_bench_labels[b1]) || [];
      const b2Labels = (cell.t2_bench_labels && cell.t2_bench_labels[b2]) || [];
      const nb1 = (cell.t1_bench_labels || []).length || 1;
      const nb2 = (cell.t2_bench_labels || []).length || 1;
      const sc = Number((cell.sub_matrix_6x6 && cell.sub_matrix_6x6[b1] && cell.sub_matrix_6x6[b1][b2]) ?? cell.score ?? 0);
      const fl = Number((cell.sub_cvar_6x6 && cell.sub_cvar_6x6[b1] && cell.sub_cvar_6x6[b1][b2]) ?? sc);
      const t1Top3 = (cell.sub_t1_top_plays && cell.sub_t1_top_plays[b1] && cell.sub_t1_top_plays[b1][b2]) || [];
      const t2Top3 = (cell.sub_t2_top_plays && cell.sub_t2_top_plays[b1] && cell.sub_t2_top_plays[b1][b2]) || [];
      const canonKey = canonicalLeadLabCellKey(cell.lead_1, b1Labels, cell.lead_2, b2Labels);
      pairs.push({
        l1,
        l2,
        b1,
        b2,
        mode_1_idx: l1 * nb1 + b1,
        mode_2_idx: l2 * nb2 + b2,
        lead_1: cell.lead_1,
        bench_1: b1Labels,
        lead_2: cell.lead_2,
        bench_2: b2Labels,
        score: sc,
        floor: fl,
        t1Top3,
        t2Top3,
        anchor: selectedAnchor,
        target: tgt,
        canonKey,
      });
    }
    return { mode, anchors, selectedAnchor, pairs };
  }

  function renderLeadLabPlaybook() {
    const panel = $("ll-playbook-panel");
    const selBox = $("ll-playbook-selector");
    const grid = $("ll-playbook-grid");
    const res = state.leadLab.result;
    if (!panel || !selBox || !grid) return;
    const { mode, anchors, selectedAnchor, pairs } = _getActivePlaybookPairs();
    if (!res || !pairs.length) {
      panel.style.display = "none";
      return;
    }
    panel.style.display = "block";
    const isEs = state.lang === "es";
    const isSci = state.style === "scientific";
    const spr = res.sprites || {};
    const mixLbl = isSci ? "Nash" : "Mix";
    const scoreLbl = isSci ? "v*" : (isEs ? "Vent." : "Edge");

    if ($("btn-ll-pb-by-mine")) {
      $("btn-ll-pb-by-mine").classList.toggle("active", mode === "by_mine");
      $("btn-ll-pb-by-mine").textContent = isEs ? "Mi Lead → vs. Top Rivales" : "My Lead → vs. Top Opp Leads";
    }
    if ($("btn-ll-pb-by-opp")) {
      $("btn-ll-pb-by-opp").classList.toggle("active", mode === "by_opp");
      $("btn-ll-pb-by-opp").textContent = isEs ? "Lead Rival → vs. Mis Top Leads" : "Opp Lead → vs. My Top Leads";
    }
    if ($("lbl-ll-playbook-title")) {
      $("lbl-ll-playbook-title").textContent = isEs
        ? "📋 Playbook Turno 1: Tus Leads vs. Leads del Rival"
        : "📋 Turn-1 Playbook Matrix: Your Leads vs. Opponent Leads";
    }
    if ($("lbl-ll-deep-batch")) {
      $("lbl-ll-deep-batch").textContent = isEs
        ? `Auditar K=128 Todos (${pairs.length} pares)`
        : `Deep Audit K=128 All (${pairs.length} pairs)`;
    }

    const selHint = mode === "by_mine"
      ? (isEs ? "Elige tu Lead:" : "Pick your Lead:")
      : (isEs ? "Elige Lead Rival:" : "Pick Opp Lead:");
    selBox.innerHTML = `<span class="muted-xs" style="align-self:center;margin-right:4px">${selHint}</span>` + anchors
      .map((a) => {
        const activeCls = Number(a.lead_idx) === Number(selectedAnchor.lead_idx) ? "active" : "";
        const wPct = ((Number(mode === "by_mine" ? a.nash_weight : a.opp_nash_weight) || 0) * 100).toFixed(0);
        return `<button class="ll-pb-pill ${activeCls}" type="button" data-pb-anchor="${a.lead_idx}">
          ${miniSpriteImg(a.lead_species[0], spr)}${miniSpriteImg(a.lead_species[1], spr)}
          <span>${escapeHtml(a.lead_species[0])} + ${escapeHtml(a.lead_species[1])}</span>
          <small>${mixLbl} ${wPct}%</small>
        </button>`;
      })
      .join("");
    selBox.querySelectorAll("[data-pb-anchor]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.leadLab.playbookSelectedIdx = parseInt(btn.dataset.pbAnchor, 10);
        renderLeadLabPlaybook();
      });
    });

    grid.innerHTML = pairs
      .map((p, idx) => {
        const isSel = state.leadLab.selectedLead1 === p.l1 && state.leadLab.selectedLead2 === p.l2;
        const cachedAudit = state.leadLab.batchAuditsByKey && state.leadLab.batchAuditsByKey[p.canonKey];
        const hasVaultCache =
          Boolean(cachedAudit) ||
          (state.leadLab.cachedDeepAuditKeys && state.leadLab.cachedDeepAuditKeys.has(p.canonKey));
        const headMons = mode === "by_mine" ? p.lead_2 : p.lead_1;
        const headPrefix = mode === "by_mine" ? (isEs ? "vs. Rival:" : "vs. Opp:") : (isEs ? "Con Tu Lead:" : "With Your Lead:");
        const wPct = ((Number(mode === "by_mine" ? p.target.opp_nash_weight : p.target.nash_weight) || 0) * 100).toFixed(1);

        // Prefer unpruned K=128 Deep Audit top actions when available, otherwise persisted Top-3 Turn-1 plays
        let playsHtml = "";
        if (cachedAudit && cachedAudit.top_actions && cachedAudit.top_actions.length) {
          playsHtml = `<div class="ll-pb-deep-tag">⚡ ${isEs ? "Auditoría K=128 Sin Poda" : "Unpruned K=128 Deep Audit"}</div>` +
            cachedAudit.top_actions
              .slice(0, 3)
              .map(
                (a, ai) => `<div class="ll-pb-play-row ${ai === 0 ? "rank-1" : ""}">
                  <span><strong>#${ai + 1}</strong> ${escapeHtml(a.desc)}</span>
                  <span class="ll-pb-play-meta">${mixLbl} ${a.nash_pct}% · ${a.risk_ev >= 0 ? "+" : ""}${Number(a.risk_ev).toFixed(2)}</span>
                </div>`
              )
              .join("");
        } else if (p.t1Top3 && p.t1Top3.length) {
          playsHtml = p.t1Top3
            .slice(0, 3)
            .map(
              (pl, pi) => `<div class="ll-pb-play-row ${pi === 0 ? "rank-1" : ""}">
                <span><strong>#${pi + 1}</strong> ${escapeHtml(pl[0])}</span>
                <span class="ll-pb-play-meta">${mixLbl} ${Number(pl[1]).toFixed(0)}% · ${Number(pl[2]) >= 0 ? "+" : ""}${Number(pl[2]).toFixed(2)}</span>
              </div>`
            )
            .join("");
        } else {
          playsHtml = `<div class="muted-xs">—</div>`;
        }

        const badgeCache = hasVaultCache
          ? `<span class="cyber-pill cyan-pill" style="font-size:10px;padding:1px 6px">⚡ K=128</span>`
          : "";
        return `<article class="ll-pb-card ${isSel ? "selected" : ""}" data-pb-idx="${idx}">
          <div class="ll-pb-card-head">
            <div class="ll-pb-lead-info">
              <span class="muted-xs">${headPrefix}</span>
              <div class="ll-lead-line">
                ${miniSpriteImg(headMons[0], spr)}${miniSpriteImg(headMons[1], spr)}
                <strong>${escapeHtml(headMons[0])} + ${escapeHtml(headMons[1])}</strong>
              </div>
              <span class="muted-xs">${mixLbl} ${wPct}% · ${isEs ? "Tu Back-2:" : "Your Back:"} ${escapeHtml(p.bench_1.join(" / "))}</span>
            </div>
            <div class="ll-pb-score-col">
              <span class="ll-metric-pill ${p.score >= 0 ? "pos" : "neg"}"><small>${scoreLbl}</small><strong>${p.score >= 0 ? "+" : ""}${p.score.toFixed(2)}</strong></span>
              ${badgeCache}
            </div>
          </div>
          <div class="ll-pb-plays">${playsHtml}</div>
          <div class="ll-pb-actions">
            <button class="btn btn-ghost btn-xs" type="button" data-pb-open="${idx}">${isEs ? "Ver 6×6 + Audit" : "Inspect 6×6"}</button>
          </div>
        </article>`;
      })
      .join("");

    grid.querySelectorAll("[data-pb-open]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const p = pairs[parseInt(btn.dataset.pbOpen, 10)];
        if (!p) return;
        selectLeadLabCell(p.l1, p.l2, p.b1, p.b2);
        const drill = $("ll-drill-panel");
        if (drill) drill.scrollIntoView({ behavior: "smooth", block: "nearest" });
      });
    });
  }

  function canonicalLeadLabModeKey(leadArr, benchArr) {
    const lToks = (leadArr || []).map((s) => normStr(s)).filter(Boolean).sort();
    const bToks = (benchArr || []).map((s) => normStr(s)).filter(Boolean).sort();
    return `${lToks.join("+")}|${bToks.join("+")}`;
  }

  function canonicalLeadLabCellKey(l1Arr, b1Arr, l2Arr, b2Arr) {
    return `${canonicalLeadLabModeKey(l1Arr, b1Arr)}__${canonicalLeadLabModeKey(l2Arr, b2Arr)}`;
  }

  function selectLeadLabCell(l1Idx, l2Idx, optB1, optB2) {
    const res = state.leadLab.result;
    if (!res || !res.heatmap_cells || !res.heatmap_cells[l1Idx] || !res.heatmap_cells[l1Idx][l2Idx]) return;
    const cell = res.heatmap_cells[l1Idx][l2Idx];
    state.leadLab.selectedLead1 = l1Idx;
    state.leadLab.selectedLead2 = l2Idx;
    state.leadLab.selectedBench1 = typeof optB1 === "number" ? optB1 : Number(cell.best_t1_bench_idx || 0);
    state.leadLab.selectedBench2 = typeof optB2 === "number" ? optB2 : Number(cell.best_t2_bench_idx || 0);
    state.leadLab.deepAudit = null;
    state.leadLab.deepAuditReqSeq = (state.leadLab.deepAuditReqSeq || 0) + 1;

    document.querySelectorAll(".ll-hm-cell.selected").forEach((el) => el.classList.remove("selected"));
    const activeTd = $(`ll-cell-${l1Idx}-${l2Idx}`);
    if (activeTd) activeTd.classList.add("selected");

    renderLeadLabDrilldown();
  }

  function renderLeadLabDrilldown() {
    const res = state.leadLab.result;
    const panel = $("ll-drill-panel");
    if (!res || !panel || state.leadLab.selectedLead1 === null) return;
    const l1 = state.leadLab.selectedLead1;
    const l2 = state.leadLab.selectedLead2;
    const b1 = state.leadLab.selectedBench1;
    const b2 = state.leadLab.selectedBench2;
    const cell = res.heatmap_cells[l1][l2];
    const spr = res.sprites || {};
    const isEs = state.lang === "es";

    panel.style.display = "block";
    if ($("ll-drill-title")) {
      $("ll-drill-title").innerHTML = `
        <span>${miniSpriteImg(cell.lead_1[0], spr)}${miniSpriteImg(cell.lead_1[1], spr)} ${escapeHtml(cell.lead_1.join(" + "))}</span>
        <span class="muted-xs">vs.</span>
        <span>${miniSpriteImg(cell.lead_2[0], spr)}${miniSpriteImg(cell.lead_2[1], spr)} ${escapeHtml(cell.lead_2.join(" + "))}</span>
      `;
    }

    // Own-Lead Quick Switcher right in the Drilldown header so coaches can compare different own leads against this exact Opponent Lead!
    const ownSw = $("ll-drill-own-switcher");
    if (ownSw) {
      const ownTop = _collectUniqueTopLeads(res.trainer_1_top_brings, 5);
      ownSw.innerHTML = `<span class="muted-xs" style="margin-right:2px">${isEs ? "Cambiar Mi Lead:" : "Switch My Lead:"}</span>` + ownTop
        .map((ob) => {
          const altL1 = Number(ob.lead_idx);
          const altCell = res.heatmap_cells[altL1] && res.heatmap_cells[altL1][l2];
          const altSc = altCell ? Number(altCell.score || 0) : 0;
          const act = altL1 === l1 ? "active" : "";
          return `<button class="ll-own-sw-pill ${act}" type="button" data-sw-l1="${altL1}" title="${escapeHtml(ob.lead_species.join(" + "))} (${altSc >= 0 ? "+" : ""}${altSc.toFixed(2)})">
            ${miniSpriteImg(ob.lead_species[0], spr)}${miniSpriteImg(ob.lead_species[1], spr)}
            <span>${altSc >= 0 ? "+" : ""}${altSc.toFixed(2)}</span>
          </button>`;
        })
        .join("");
      ownSw.querySelectorAll("[data-sw-l1]").forEach((btn) => {
        btn.addEventListener("click", () => {
          const targetL1 = parseInt(btn.dataset.swL1, 10);
          selectLeadLabCell(targetL1, l2);
        });
      });
    }

    if ($("ll-drill-turn0-strip")) {
      const evs = cell.turn0_events || [];
      $("ll-drill-turn0-strip").innerHTML = evs.length
        ? evs.map((e) => `<span class="ll-t0-chip">${escapeHtml(e)}</span>`).join("")
        : `<span class="muted-xs">${isEs ? "Sin habilidades de entrada Turno 0 en este lead." : "No Turn-0 entry abilities triggered on this lead."}</span>`;
    }

    // Render 6×6 Back-2 sub-matrix
    const subBox = $("ll-submatrix-container");
    if (subBox) {
      const subM = cell.sub_matrix_6x6 || [];
      const b1Lbls = cell.t1_bench_labels || [];
      const b2Lbls = cell.t2_bench_labels || [];
      const hdrs = b2Lbls
        .map(
          (p) =>
            `<th><div class="ll-hm-spr-pair">${miniSpriteImg(p[0], spr)}${miniSpriteImg(p[1], spr)}</div><div>${escapeHtml(p[0].slice(0, 5))}/${escapeHtml(p[1].slice(0, 5))}</div></th>`
        )
        .join("");
      const rows = b1Lbls
        .map((pair1, rIdx) => {
          const nb1 = b1Lbls.length || 1;
          const nb2 = b2Lbls.length || 1;
          const tds = b2Lbls
            .map((_, cIdx) => {
              const val = Number((subM[rIdx] && subM[rIdx][cIdx]) || 0);
              const selCls = rIdx === b1 && cIdx === b2 ? "selected" : "";
              const m1Key = `m${l1 * nb1 + rIdx}`;
              const m2Key = `m${l2 * nb2 + cIdx}`;
              const canonCellKey = canonicalLeadLabCellKey(cell.lead_1, pair1, cell.lead_2, b2Lbls[cIdx] || []);
              const cachedCls =
                state.leadLab.cachedDeepAuditKeys &&
                (state.leadLab.cachedDeepAuditKeys.has(canonCellKey) ||
                  state.leadLab.cachedDeepAuditKeys.has(`${m1Key}__${m2Key}`))
                  ? "has-deep-cache"
                  : "";
              const cacheTip = cachedCls
                ? (isEs ? " · ⚡ Auditoría K=128 en Vault" : " · ⚡ Cached K=128 Deep Audit")
                : "";
              return `<td class="ll-hm-cell ready ${selCls} ${cachedCls}" title="v*=${val >= 0 ? "+" : ""}${val.toFixed(3)}${cacheTip}" style="background:${scoreCellBg(val)};color:${scoreTextColor(val)}" data-sb1="${rIdx}" data-sb2="${cIdx}">${val >= 0 ? "+" : ""}${val.toFixed(2)}</td>`;
            })
            .join("");
          return `<tr><th class="ll-hm-row-hdr">${miniSpriteImg(pair1[0], spr)}${miniSpriteImg(pair1[1], spr)} ${escapeHtml(pair1.join(" + "))}</th>${tds}</tr>`;
        })
        .join("");
      subBox.innerHTML = `<table class="ll-hm-table"><thead><tr><th class="ll-hm-row-hdr">${isEs ? "Tu Back-2 \\ Rival Back-2" : "T1 Back-2 \\ T2 Back-2"}</th>${hdrs}</tr></thead><tbody>${rows}</tbody></table>`;
      subBox.querySelectorAll("[data-sb1]").forEach((td) => {
        td.addEventListener("click", () => {
          state.leadLab.selectedBench1 = parseInt(td.dataset.sb1, 10);
          state.leadLab.selectedBench2 = parseInt(td.dataset.sb2, 10);
          state.leadLab.deepAudit = null;
          state.leadLab.deepAuditReqSeq = (state.leadLab.deepAuditReqSeq || 0) + 1;
          renderLeadLabDrilldown();
        });
      });
    }

    // Render selected (Back-1, Back-2) opening play card with persisted Top-3 Turn-1 plays
    const openCard = $("ll-opening-card");
    if (openCard) {
      const isSci = state.style === "scientific";
      const sc = Number((cell.sub_matrix_6x6[b1] && cell.sub_matrix_6x6[b1][b2]) || 0);
      const cv = Number((cell.sub_cvar_6x6[b1] && cell.sub_cvar_6x6[b1][b2]) || 0);
      const t1Op = (cell.sub_t1_openings[b1] && cell.sub_t1_openings[b1][b2]) || "";
      const t2Op = (cell.sub_t2_openings[b1] && cell.sub_t2_openings[b1][b2]) || "";
      const t1Top3 = (cell.sub_t1_top_plays && cell.sub_t1_top_plays[b1] && cell.sub_t1_top_plays[b1][b2]) || [];
      const t2Top3 = (cell.sub_t2_top_plays && cell.sub_t2_top_plays[b1] && cell.sub_t2_top_plays[b1][b2]) || [];
      const b1Name = (cell.t1_bench_labels[b1] || []).join(" + ");
      const b2Name = (cell.t2_bench_labels[b2] || []).join(" + ");
      const scoreBadge = isSci
        ? `v* = ${sc >= 0 ? "+" : ""}${sc.toFixed(3)} · CVaR₁₀ ${cv >= 0 ? "+" : ""}${cv.toFixed(2)}`
        : isEs
          ? `Ventaja ${sc >= 0 ? "+" : ""}${sc.toFixed(2)} · Piso 10% RNG ${cv >= 0 ? "+" : ""}${cv.toFixed(2)}`
          : `Edge ${sc >= 0 ? "+" : ""}${sc.toFixed(2)} · Bad-Luck Floor ${cv >= 0 ? "+" : ""}${cv.toFixed(2)}`;
      const mixLbl = isSci ? "Nash" : "Mix";

      const renderTopList = (plays, fallbackDesc) => {
        if (plays && plays.length) {
          return `<div class="ll-top-plays-list">${plays
            .map(
              (p, idx) => `<div class="ll-top-play-row ${idx === 0 ? "rank-1" : ""}">
                <span><strong>#${idx + 1}</strong> ${escapeHtml(p[0])}</span>
                <span class="ll-top-play-meta">${mixLbl} ${Number(p[1]).toFixed(1)}% · ${Number(p[2]) >= 0 ? "+" : ""}${Number(p[2]).toFixed(2)}</span>
              </div>`
            )
            .join("")}</div>`;
        }
        return `<div>${escapeHtml(fallbackDesc || "—")}</div>`;
      };

      const t1Head = isSci
        ? (isEs ? "Tus Mejores Jugadas Turno 1 (Nash):" : "Your Top Turn-1 Plays (Nash):")
        : (isEs ? "Tus Mejores Aperturas Turno 1:" : "Your Best Turn-1 Openings:");
      const t2Head = isSci
        ? (isEs ? "Mejores Respuestas del Rival (Nash):" : "Best Opponent Responses (Nash):")
        : (isEs ? "Respuestas Más Peligrosas del Rival:" : "Toughest Opponent Counters:");

      openCard.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap">
          <strong>${isEs ? "Aperturas Óptimas Turno 1" : "Optimal Turn-1 Openings"}</strong>
          <span class="cyber-pill ${sc >= 0 ? "cyan-pill" : "gold-pill"}">${escapeHtml(scoreBadge)}</span>
        </div>
        <div class="muted-xs">${isEs ? "Tu Banca:" : "Your Back-2:"} <strong>${escapeHtml(b1Name)}</strong> · ${isEs ? "Banca Rival:" : "Opp Back-2:"} <strong>${escapeHtml(b2Name)}</strong></div>
        <div class="ll-opening-line"><strong>${t1Head}</strong>${renderTopList(t1Top3, t1Op)}</div>
        <div class="ll-opening-line opp"><strong>${t2Head}</strong>${renderTopList(t2Top3, t2Op)}</div>
      `;
    }

    // Auto-hydrate cached K=128 Deep Audit immediately from DuckDB using canonical species identity + stale-request guard!
    const nb1 = (cell.t1_bench_labels || []).length || 1;
    const nb2 = (cell.t2_bench_labels || []).length || 1;
    const m1Idx = l1 * nb1 + b1;
    const m2Idx = l2 * nb2 + b2;
    const b1PairSel = (cell.t1_bench_labels && cell.t1_bench_labels[b1]) || [];
    const b2PairSel = (cell.t2_bench_labels && cell.t2_bench_labels[b2]) || [];
    const canonKey = canonicalLeadLabCellKey(cell.lead_1, b1PairSel, cell.lead_2, b2PairSel);
    const legacyKey = `m${m1Idx}__m${m2Idx}`;
    const deepBox = $("ll-deep-audit-box");
    if (deepBox) {
      const curAuditKey = state.leadLab.deepAudit && state.leadLab.deepAudit.audit_cell_key;
      if (state.leadLab.deepAudit && (curAuditKey === canonKey || curAuditKey === legacyKey)) {
        renderLeadLabDeepAuditBox(state.leadLab.deepAudit);
      } else if (
        state.leadLab.jobId &&
        state.leadLab.cachedDeepAuditKeys &&
        (state.leadLab.cachedDeepAuditKeys.has(canonKey) || state.leadLab.cachedDeepAuditKeys.has(legacyKey))
      ) {
        const reqSeq = ++state.leadLab.deepAuditReqSeq;
        deepBox.style.display = "flex";
        deepBox.innerHTML = `<span class="muted-xs">⚡ ${isEs ? "Cargando auditoría profunda K=128 guardada en Vault..." : "Loading cached K=128 deep audit from Vault..."}</span>`;
        fetch("/api/lead-lab/deep-turn1", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            job_id: state.leadLab.jobId,
            mode_1_idx: m1Idx,
            mode_2_idx: m2Idx,
            lead_1: cell.lead_1,
            bench_1: b1PairSel,
            lead_2: cell.lead_2,
            bench_2: b2PairSel,
            num_mc: 128,
            force_recompute: false,
          }),
        })
          .then((r) => r.json())
          .then((d) => {
            if (reqSeq !== state.leadLab.deepAuditReqSeq) return;
            if (
              d &&
              !d.error &&
              state.leadLab.selectedLead1 === l1 &&
              state.leadLab.selectedLead2 === l2 &&
              state.leadLab.selectedBench1 === b1 &&
              state.leadLab.selectedBench2 === b2
            ) {
              // Verify returned species match the active box so mismatched moves can NEVER render!
              if (d.mode_1 && d.mode_2) {
                const gotKey = canonicalLeadLabCellKey(
                  d.mode_1.lead_species,
                  d.mode_1.bench_species,
                  d.mode_2.lead_species,
                  d.mode_2.bench_species
                );
                if (gotKey !== canonKey) return;
              }
              state.leadLab.deepAudit = d;
              renderLeadLabDeepAuditBox(d);
            }
          })
          .catch(() => {});
      } else {
        deepBox.style.display = "none";
      }
    }
  }

  function renderLeadLabDeepAuditBox(audit) {
    const deepBox = $("ll-deep-audit-box");
    if (!deepBox || !audit) return;
    const isEs = state.lang === "es";
    const isSci = state.style === "scientific";
    const pk = profileKey();
    const com = (audit.commentary_variants && (audit.commentary_variants[pk] || audit.commentary_variants.es_vgc)) || {};
    deepBox.style.display = "flex";
    const eqBullet = (com.bullets || []).find(
      (b) =>
        b &&
        (b.tag === "Motores de Equity" ||
          b.tag === "Equity Drivers" ||
          b.tag === "Atribucion_Equity_8_Pilares" ||
          b.tag === "8_Pillar_Equity_Attribution")
    );
    const cacheBadge = audit.from_vault_cache
      ? `<span class="cyber-pill cyan-pill">⚡ ${isEs ? "En Vault" : "Vault Cache"}</span>`
      : "";
    const mixLbl = isSci ? "Nash" : "Mix";
    const scoreLbl = isSci ? "EV" : (isEs ? "Vent." : "Score");
    const topRows = (audit.top_actions || [])
      .slice(0, 5)
      .map(
        (a, idx) => `<div class="ll-deep-row">
          <span><strong>#${idx + 1}</strong> ${escapeHtml(a.desc)}</span>
          <span style="white-space:nowrap;font-family:monospace;color:#fde047">${mixLbl} ${a.nash_pct}% · ${scoreLbl} ${a.risk_ev >= 0 ? "+" : ""}${a.risk_ev.toFixed(2)}</span>
        </div>`
      )
      .join("");
    deepBox.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap">
        <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
          <strong style="color:#fde047">⚡ ${isEs ? "Auditoría Profunda Turno 1 (Sin Poda)" : "Deep Unpruned Turn-1 Audit"}</strong>
          ${cacheBadge}
        </div>
        <span class="muted-xs">[${(audit.matrix_shape || []).join("×")}] · K=${audit.num_mc} · ${audit.elapsed_s}s</span>
      </div>
      ${com.headline ? `<div class="muted-sm" style="color:#e2e8f0">${escapeHtml(com.headline)}</div>` : ""}
      ${eqBullet ? `<div class="muted-xs" style="color:#67e8f9"><strong>${escapeHtml(eqBullet.tag)}:</strong> ${escapeHtml(eqBullet.text)}</div>` : ""}
      ${topRows}
    `;
  }

  // -------------------------------------------------------------------------
  // DuckDB Lead Lab Matchup Vault Controller (Searchable Cache & Instant Load)
  // -------------------------------------------------------------------------
  function buildLeadLabCurrentPayload() {
    const ll = state.leadLab;
    const preset = ($("ll-preset-select") && $("ll-preset-select").value) || "balanced";
    const payload = { preset };
    if (ll.t1UsePaste) {
      payload.t1_paste_text = ($("ll-t1-paste-input") && $("ll-t1-paste-input").value.trim()) || "";
    } else {
      payload.t1_roster_id = ($("ll-t1-roster-select") && $("ll-t1-roster-select").value) || "";
    }
    if (ll.t2Mode === "scout") {
      if (ll.t2Inference) payload.t2_user_spreads = ll.t2UserSpreads;
    } else if (ll.t2UsePaste) {
      payload.t2_paste_text = ($("ll-t2-paste-input") && $("ll-t2-paste-input").value.trim()) || "";
    } else {
      payload.t2_roster_id = ($("ll-t2-roster-select") && $("ll-t2-roster-select").value) || "";
    }
    return payload;
  }

  function renderLeadLabCacheHitBar() {
    const bar = $("ll-cache-hit-bar");
    const info = $("ll-cache-hit-info");
    if (!bar || !info) return;
    const hit = state.leadLab.cacheHit;
    if (!hit || !hit.found || state.leadLab.running) {
      bar.style.display = "none";
      return;
    }
    const isEs = state.lang === "es";
    const v = Number(hit.global_nash_value || 0);
    const vStr = `${v >= 0 ? "+" : ""}${v.toFixed(3)}`;
    const outPill = hit.is_outdated
      ? `<span class="cyber-pill gold-pill">⚠ ${isEs ? "Equity anterior" : "Outdated Equity"} (${escapeHtml(hit.engine_version)})</span>`
      : `<span class="cyber-pill cyan-pill">⚡ ${isEs ? "En Vault" : "In Vault"}</span>`;
    const deepTxt =
      hit.cached_deep_audit_count > 0
        ? ` · ⚡ ${hit.cached_deep_audit_count} ${isEs ? "auditorías K=128" : "K=128 audits"}`
        : "";
    bar.classList.toggle("outdated", Boolean(hit.is_outdated));
    bar.style.display = "flex";
    info.innerHTML = `
      ${outPill}
      <strong>${escapeHtml(hit.t1_name)} vs ${escapeHtml(hit.t2_name)}</strong>
      <span class="cyber-pill ${v >= 0 ? "cyan-pill" : "gold-pill"}">v* = ${vStr}</span>
      <span class="muted-xs">${escapeHtml(hit.preset)} · ${hit.elapsed_s}s${deepTxt}</span>
    `;
    if ($("btn-ll-cache-load")) {
      $("btn-ll-cache-load").textContent = isEs ? "⚡ Cargar al Instante" : "⚡ Load Instantly";
    }
    if ($("btn-ll-cache-rerun")) {
      $("btn-ll-cache-rerun").textContent = isEs ? "↻ Recalcular" : "↻ Recompute";
    }
  }

  function scheduleLeadLabCacheLookup(delayMs) {
    const ll = state.leadLab;
    if (ll.lookupTimer) clearTimeout(ll.lookupTimer);
    ll.lookupTimer = setTimeout(async () => {
      try {
        const resp = await fetch("/api/lead-lab/lookup", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(buildLeadLabCurrentPayload()),
        });
        const d = await resp.json();
        ll.cacheHit = resp.ok && d && d.found ? d : null;
      } catch (_) {
        ll.cacheHit = null;
      }
      renderLeadLabCacheHitBar();
    }, Math.max(0, Number(delayMs || 0)));
  }

  function updateLeadLabExportButtons(vaultRunId) {
    const csvBtn = $("btn-ll-export-csv");
    const jsonBtn = $("btn-ll-export-json");
    if (vaultRunId) {
      if (csvBtn) {
        csvBtn.href = `/api/lead-lab/vault/export?run_id=${encodeURIComponent(vaultRunId)}&format=csv`;
        csvBtn.style.display = "inline-flex";
      }
      if (jsonBtn) {
        jsonBtn.href = `/api/lead-lab/vault/export?run_id=${encodeURIComponent(vaultRunId)}&format=json`;
        jsonBtn.style.display = "inline-flex";
      }
    } else {
      if (csvBtn) csvBtn.style.display = "none";
      if (jsonBtn) jsonBtn.style.display = "none";
    }
  }

  function hydrateLeadLabCompletedResult(fullRes, isFromVault) {
    const ll = state.leadLab;
    const isEs = state.lang === "es";
    ll.running = false;
    ll.jobId = fullRes.job_id || ll.jobId;
    ll.result = fullRes;
    ll.currentMatchupHash = fullRes.matchup_hash || "";
    ll.cachedDeepAuditKeys = new Set(fullRes.cached_deep_audit_keys || []);
    ll.selectedLead1 = null;
    ll.selectedLead2 = null;
    ll.deepAudit = null;

    const t1Leads =
      (fullRes.t1_leads && fullRes.t1_leads.length ? fullRes.t1_leads : fullRes.trainer_1_leads) || [];
    const t2Leads =
      (fullRes.t2_leads && fullRes.t2_leads.length ? fullRes.t2_leads : fullRes.trainer_2_leads) || [];
    const meta = {
      job_id: fullRes.job_id,
      t1_label: fullRes.t1_label,
      t2_label: fullRes.t2_label,
      t1_leads: t1Leads,
      t2_leads: t2Leads,
      num_t1_modes: fullRes.num_t1_modes || (fullRes.modes_t1 && fullRes.modes_t1.length) || 90,
      num_t2_modes: fullRes.num_t2_modes || (fullRes.modes_t2 && fullRes.modes_t2.length) || 90,
      total_lead_pairs: t1Leads.length * t2Leads.length,
      sprites: fullRes.sprites || {},
    };
    ll.jobMeta = meta;
    updateLeadLabControlsUI();
    updateLeadLabExportButtons(fullRes.vault_run_id || "");

    if ($("ll-results-shell")) $("ll-results-shell").style.display = "block";
    renderLeadLabHeatmapSkeleton(meta);
    const cellsGrid = fullRes.heatmap_cells || [];
    for (let i = 0; i < cellsGrid.length; i++) {
      const row = cellsGrid[i] || [];
      for (let j = 0; j < row.length; j++) {
        const c = row[j];
        if (!c) continue;
        const cellScore = typeof c.score === "number" ? c.score : Number(c.nash_value || 0);
        updateLeadLabHeatmapCell({
          lead_1_idx: i,
          lead_2_idx: j,
          score: cellScore,
          best_t1_bench: (c.t1_bench_labels && c.t1_bench_labels[c.best_t1_bench_idx || 0]) || [],
          t1_opening:
            c.t1_opening ||
            (c.sub_t1_openings &&
              c.sub_t1_openings[c.best_t1_bench_idx || 0] &&
              c.sub_t1_openings[c.best_t1_bench_idx || 0][c.best_t2_bench_idx || 0]) ||
            "",
        });
      }
    }
    renderLeadLabPodium(fullRes);
    if (fullRes.trainer_1_top_brings && fullRes.trainer_1_top_brings.length && fullRes.trainer_2_top_brings && fullRes.trainer_2_top_brings.length) {
      const top1 = fullRes.trainer_1_top_brings[0];
      const top2 = fullRes.trainer_2_top_brings[0];
      selectLeadLabCell(top1.lead_idx, top2.lead_idx, top1.bench_idx, top2.bench_idx);
    }
    if (isFromVault && $("ll-status-msg")) {
      const gv = Number(fullRes.global_game_value || 0);
      $("ll-status-msg").textContent = isEs
        ? `⚡ Cargado desde Matchup Vault (${fullRes.t1_label} vs ${fullRes.t2_label} · v*=${gv >= 0 ? "+" : ""}${gv.toFixed(3)} · ${fullRes.preset}).`
        : `⚡ Loaded instantly from Matchup Vault (${fullRes.t1_label} vs ${fullRes.t2_label} · v*=${gv >= 0 ? "+" : ""}${gv.toFixed(3)} · ${fullRes.preset}).`;
    }
  }

  async function loadLeadLabFromVault(runId) {
    const isEs = state.lang === "es";
    try {
      const resp = await fetch(`/api/lead-lab/vault/load?run_id=${encodeURIComponent(runId)}`);
      const d = await resp.json();
      if (!resp.ok || !d.ok || !d.result) {
        if ($("ll-status-msg")) $("ll-status-msg").textContent = `Error: ${(d && d.error) || "Failed to load Vault run"}`;
        return;
      }
      state.leadLab.vaultOpen = false;
      if ($("ll-vault-panel")) $("ll-vault-panel").style.display = "none";
      if ($("ll-progress-panel")) $("ll-progress-panel").style.display = "none";
      hydrateLeadLabCompletedResult(d.result, true);
    } catch (err) {
      if ($("ll-status-msg")) {
        $("ll-status-msg").textContent = isEs ? `Error cargando Vault: ${err}` : `Error loading Vault: ${err}`;
      }
    }
  }

  async function rerunLeadLabFromVault(runId) {
    try {
      const resp = await fetch(`/api/lead-lab/vault/load?run_id=${encodeURIComponent(runId)}`);
      const d = await resp.json();
      if (!resp.ok || !d.ok) return;
      state.leadLab.t1UsePaste = true;
      state.leadLab.t2Mode = "full";
      state.leadLab.t2UsePaste = true;
      if ($("ll-t1-paste-input")) $("ll-t1-paste-input").value = d.t1_paste || "";
      if ($("ll-t2-paste-input")) $("ll-t2-paste-input").value = d.t2_paste || "";
      if ($("ll-preset-select") && d.preset) $("ll-preset-select").value = d.preset;
      state.leadLab.vaultOpen = false;
      if ($("ll-vault-panel")) $("ll-vault-panel").style.display = "none";
      updateLeadLabControlsUI();
      launchLeadLabSweep();
    } catch (_) {}
  }

  async function refreshLeadLabVault() {
    const ll = state.leadLab;
    const params = new URLSearchParams();
    if (ll.vaultSearch) params.set("q", ll.vaultSearch);
    if (ll.vaultFilterT1) params.set("t1_name", ll.vaultFilterT1);
    if (ll.vaultFilterAdv) params.set("advantage", ll.vaultFilterAdv);
    params.set("limit", "60");
    try {
      const resp = await fetch(`/api/lead-lab/vault?${params.toString()}`);
      const d = await resp.json();
      if (!resp.ok || !d.ok) return;
      ll.vaultRuns = d.runs || [];
      ll.vaultTotal = Number(d.total_count || 0);
      ll.vaultT1Teams = d.t1_teams || [];
      if ($("ll-vault-count-pill")) $("ll-vault-count-pill").textContent = String(ll.vaultTotal);
      renderLeadLabVaultT1Select();
      renderLeadLabVaultList();
    } catch (_) {}
  }

  function renderLeadLabVaultT1Select() {
    const sel = $("ll-vault-t1-filter");
    if (!sel) return;
    const isEs = state.lang === "es";
    const cur = state.leadLab.vaultFilterT1 || "";
    const opts = [`<option value="">${isEs ? "Todos mis equipos" : "All My Teams"}</option>`].concat(
      (state.leadLab.vaultT1Teams || []).map(
        (name) => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`
      )
    );
    sel.innerHTML = opts.join("");
    sel.value = cur;
  }

  function renderLeadLabVaultList() {
    const box = $("ll-vault-list");
    if (!box) return;
    const isEs = state.lang === "es";
    const runs = state.leadLab.vaultRuns || [];
    if (!runs.length) {
      box.innerHTML = `<div class="muted-sm" style="padding:12px;text-align:center">${
        state.leadLab.vaultTotal === 0
          ? (isEs ? "Aún no hay simulaciones 90×90 guardadas. Ejecuta un sweep para guardarlo automáticamente en DuckDB." : "No saved 90×90 sweeps yet. Run a Lead Lab sweep to auto-save it in DuckDB.")
          : (isEs ? "Ningún matchup coincide con los filtros actuales." : "No saved matchups match the current filters.")
      }</div>`;
      return;
    }

    box.innerHTML = runs
      .map((r) => {
        const v = Number(r.global_nash_value || 0);
        const vCls = v >= 0.08 ? "leg-win" : v <= -0.08 ? "leg-lose" : "leg-even";
        const oppSpr = (r.t2_species_sprites || [])
          .map((s) => (s.sprite_url ? `<img class="ll-mini-spr" src="${escapeHtml(s.sprite_url)}" alt="${escapeHtml(s.species)}" title="${escapeHtml(s.species)}" loading="lazy" />` : ""))
          .join("");
        const top1 = r.top_t1_bring || {};
        const top1Pct = top1.nash_weight != null ? `${(Number(top1.nash_weight) * 100).toFixed(0)}%` : "";
        const top1Names = [].concat(top1.lead_species || [], top1.bench_species || []);
        const top1Label = top1Names.length ? `${top1Names.slice(0, 2).join("+")} [${top1Names.slice(2).join("/")}] ${top1Pct}` : "";
        const outBadge = r.is_outdated
          ? `<span class="cyber-pill gold-pill" title="Computed with an older equity model">⚠ ${isEs ? "Equity anterior" : "Outdated Equity"}</span>`
          : "";
        const deepBadge =
          r.cached_deep_audit_count > 0
            ? `<span class="cyber-pill cyan-pill">⚡ ${r.cached_deep_audit_count}</span>`
            : "";
        const tagHtml = r.tags
          ? `<span class="ll-vault-tag-pill">🏷 ${escapeHtml(r.tags)}</span>`
          : "";
        return `<div class="ll-vault-row" data-run-id="${escapeHtml(r.run_id)}">
          <div class="ll-vault-row-main">
            <div class="ll-vault-row-head">
              <span class="legend-chip ${vCls}">v* ${v >= 0 ? "+" : ""}${v.toFixed(3)}</span>
              <span>${escapeHtml(r.t1_name)} <span class="muted-xs">vs</span> ${escapeHtml(r.t2_name)}</span>
              <span class="cyber-pill slate-pill">${escapeHtml(r.preset)}</span>
              ${outBadge}
              ${deepBadge}
              ${tagHtml}
            </div>
            <div class="ll-vault-row-sprites">
              <span class="ll-vault-spr-strip" title="${escapeHtml((r.t2_species || []).join(", "))}">${oppSpr}</span>
              ${top1Label ? `<span><strong>#1 Bring:</strong> ${escapeHtml(top1Label)}</span>` : ""}
              <span class="muted-xs">${escapeHtml((r.created_at || "").replace("T", " ").slice(0, 16))}</span>
            </div>
          </div>
          <div class="ll-vault-row-actions">
            <button class="btn btn-greatball btn-xs ll-v-load" data-run-id="${escapeHtml(r.run_id)}" type="button">${isEs ? "Cargar" : "Load"}</button>
            <button class="btn btn-ghost btn-xs ll-v-tag" data-run-id="${escapeHtml(r.run_id)}" data-tags="${escapeHtml(r.tags || "")}" type="button">🏷 ${isEs ? "Etiqueta" : "Tag"}</button>
            <button class="btn btn-ghost btn-xs ll-v-rerun" data-run-id="${escapeHtml(r.run_id)}" type="button">↻</button>
            <button class="btn btn-danger btn-xs ll-v-del" data-run-id="${escapeHtml(r.run_id)}" type="button">🗑</button>
          </div>
        </div>`;
      })
      .join("");

    box.querySelectorAll(".ll-v-load").forEach((btn) => {
      btn.addEventListener("click", () => loadLeadLabFromVault(btn.dataset.runId));
    });
    box.querySelectorAll(".ll-v-rerun").forEach((btn) => {
      btn.addEventListener("click", () => rerunLeadLabFromVault(btn.dataset.runId));
    });
    box.querySelectorAll(".ll-v-tag").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const curTags = btn.dataset.tags || "";
        const nextTags = window.prompt(
          isEs ? "Etiquetas o notas para este matchup (ej. Regional, Trick Room):" : "Tags or notes for this matchup (e.g. Regional, Trick Room):",
          curTags
        );
        if (nextTags === null) return;
        await fetch("/api/lead-lab/vault/tag", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ run_id: btn.dataset.runId, tags: nextTags }),
        });
        refreshLeadLabVault();
      });
    });
    box.querySelectorAll(".ll-v-del").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const ok = window.confirm(
          isEs ? "¿Eliminar esta simulación guardada del Vault?" : "Delete this saved matchup from the Vault?"
        );
        if (!ok) return;
        await fetch("/api/lead-lab/vault/delete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ run_id: btn.dataset.runId }),
        });
        refreshLeadLabVault();
        scheduleLeadLabCacheLookup(0);
      });
    });
  }

  function clearLeadLabCli() {
    const box = $("ll-cli-console");
    if (box) box.innerHTML = "";
  }

  function renderLeadLabWorkersStrip(workersMap) {
    const strip = $("ll-workers-strip");
    if (!strip) return;
    const entries = Object.values(workersMap || {});
    if (!entries.length) {
      strip.style.display = "none";
      strip.innerHTML = "";
      return;
    }
    strip.style.display = "flex";
    const isEs = state.lang === "es";
    entries.sort((a, b) => String(a.worker).localeCompare(String(b.worker)));
    strip.innerHTML = entries
      .map((w) => {
        const cls = workerHardwareClass(w.worker);
        const doneCls = w.done ? "hw-done" : "";
        const hwShort = w.hardware_device ? ` · ${w.hardware_device}` : "";
        const cntTxt = `${Number(w.count || 0)} ${isEs ? "celdas" : "cells"}`;
        const cellTxt = w.done
          ? `${cntTxt} ✓`
          : `(${w.l1 + 1},${w.l2 + 1}) · ${cntTxt}`;
        return `<span class="worker-chip ${cls} ${doneCls}"><strong>${escapeHtml(w.worker)}</strong><span>${escapeHtml(hwShort)}</span><span>→ ${escapeHtml(cellTxt)}</span></span>`;
      })
      .join("");
  }

  function appendLeadLabCli(tag, msg, tagClass) {
    const box = $("ll-cli-console");
    if (!box) return;
    const prevLatest = box.querySelector(".ll-cli-line.latest");
    if (prevLatest) prevLatest.classList.remove("latest");

    const now = new Date();
    const ts = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}:${String(now.getSeconds()).padStart(2, "0")}`;
    const line = document.createElement("div");
    line.className = "ll-cli-line latest";
    line.innerHTML = `<span class="ll-cli-ts">${ts}</span><span class="ll-cli-tag ${escapeHtml(tagClass || "")}">[${escapeHtml(tag)}]</span><span class="ll-cli-msg">${escapeHtml(msg)}</span>`;
    box.appendChild(line);
    while (box.childElementCount > 260) {
      box.removeChild(box.firstElementChild);
    }
    box.scrollTop = box.scrollHeight;
  }

  async function launchLeadLabSweep() {
    const isEs = state.lang === "es";
    const ll = state.leadLab;
    if (ll.running) return;
    const statusEl = $("ll-status-msg");
    const preset = ($("ll-preset-select") && $("ll-preset-select").value) || "balanced";
    const computeMode = ($("ll-compute-mode") && $("ll-compute-mode").value) || "auto";

    const payload = { preset, compute_mode: computeMode };
    if (ll.t1UsePaste) {
      payload.t1_paste_text = ($("ll-t1-paste-input") && $("ll-t1-paste-input").value.trim()) || "";
    } else {
      payload.t1_roster_id = ($("ll-t1-roster-select") && $("ll-t1-roster-select").value) || "";
    }

    if (ll.t2Mode === "scout") {
      if (!ll.t2Inference) {
        if (statusEl) {
          statusEl.textContent = isEs
            ? "Primero sube 1–3 logs Bo3 y pulsa 'Resolver 66-SP Rival' antes de simular."
            : "Upload 1–3 Bo3 scouting logs and click 'Solve Opponent 66-SP' first.";
        }
        return;
      }
      payload.t2_user_spreads = ll.t2UserSpreads;
    } else if (ll.t2UsePaste) {
      payload.t2_paste_text = ($("ll-t2-paste-input") && $("ll-t2-paste-input").value.trim()) || "";
    } else {
      payload.t2_roster_id = ($("ll-t2-roster-select") && $("ll-t2-roster-select").value) || "";
    }

    if ($("ll-progress-panel")) $("ll-progress-panel").style.display = "block";
    if ($("ll-status-dot")) $("ll-status-dot").className = "status-dot running";
    renderLeadLabWorkersStrip({});
    clearLeadLabCli();
    appendLeadLabCli(
      "INIT",
      isEs
        ? `Validando 66-SP y precompilando tensores Reg M-C (preset=${preset} · modo=${computeMode.toUpperCase()})...`
        : `Validating 66-SP spreads & pre-compiling Reg M-C tensors (preset=${preset} · mode=${computeMode.toUpperCase()})...`
    );
    if (statusEl) {
      statusEl.textContent = isEs ? "Validando equipos 66-SP y compilando tensores..." : "Validating 66-SP teams & pre-compiling tensors...";
    }

    try {
      const res = await fetch("/api/lead-lab/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const meta = await res.json();
      if (!res.ok || !meta.ok) {
        appendLeadLabCli("ERR", meta.error || "Could not start Lead Lab", "tag-err");
        if ($("ll-status-dot")) $("ll-status-dot").className = "status-dot error";
        if (statusEl) statusEl.textContent = `Error: ${meta.error || "Could not start Lead Lab"}`;
        return;
      }

      ll.running = true;
      ll.jobId = meta.job_id;
      ll.jobMeta = meta;
      ll.result = null;
      ll.selectedLead1 = null;
      ll.selectedLead2 = null;
      ll.deepAudit = null;
      updateLeadLabControlsUI();
      updateLeadLabExportButtons("");

      appendLeadLabCli(
        "READY",
        `${meta.t1_label} vs ${meta.t2_label} · ${meta.t1_leads.length}×${meta.t2_leads.length} leads (${meta.num_t1_modes}×${meta.num_t2_modes} = ${(meta.num_t1_modes * meta.num_t2_modes).toLocaleString()} modes) · ${(meta.compute_mode || computeMode).toUpperCase()} · ${meta.device}`,
        "tag-nash"
      );

      if ($("ll-progress-fill")) $("ll-progress-fill").style.width = "0%";
      if ($("ll-progress-text")) $("ll-progress-text").textContent = `0 / ${meta.total_lead_pairs}`;
      if ($("ll-progress-eta")) $("ll-progress-eta").textContent = "";
      if ($("ll-results-shell")) $("ll-results-shell").style.display = "block";
      if ($("ll-podium-grid")) $("ll-podium-grid").style.display = "none";
      if ($("ll-drill-panel")) $("ll-drill-panel").style.display = "none";
      renderLeadLabHeatmapSkeleton(meta);

      appendLeadLabCli(
        "SCHED",
        isEs
          ? `Scheduler ${(meta.compute_mode || computeMode).toUpperCase()} activo sobre ${meta.total_lead_pairs} pares únicos (GPU desde (1,1)→ y CPU robando desde ←(15,15)) — el log ordenado (001→${meta.total_lead_pairs}) se reconstruirá al finalizar todos los hilos...`
          : `${(meta.compute_mode || computeMode).toUpperCase()} scheduler active across ${meta.total_lead_pairs} unique lead pairs (GPU from (1,1)→ and CPU stealing from ←(15,15)) — the ordered log (001→${meta.total_lead_pairs}) will be reconstructed once all workers join...`,
        "tag-nash"
      );

      if (ll.activeStream) {
        try { ll.activeStream.close(); } catch (_) {}
      }
      const llWorkersLive = {};
      const es = new EventSource(`/api/lead-lab/stream?job_id=${encodeURIComponent(meta.job_id)}`);
      ll.activeStream = es;

      es.addEventListener("cell", (ev) => {
        const d = JSON.parse(ev.data);
        updateLeadLabHeatmapCell(d);
        const wKey = d.compute_worker || "GPU";
        const countsObj = d.worker_cell_counts || {};
        llWorkersLive[wKey] = {
          worker: wKey,
          hardware_device: d.hardware_device || "",
          l1: Number(d.lead_1_idx || 0),
          l2: Number(d.lead_2_idx || 0),
          count: countsObj[wKey] != null ? Number(countsObj[wKey]) : ((llWorkersLive[wKey] && llWorkersLive[wKey].count) || 0) + 1,
          done: false,
        };
        Object.keys(countsObj).forEach((wk) => {
          if (llWorkersLive[wk]) llWorkersLive[wk].count = Number(countsObj[wk]);
        });
        renderLeadLabWorkersStrip(llWorkersLive);

        const pct = Math.min(100, (Number(d.completed || 0) / Math.max(1, Number(d.total || 225))) * 100);
        const modesPerCell =
          meta.total_lead_pairs > 0
            ? Math.round((meta.num_t1_modes * meta.num_t2_modes) / meta.total_lead_pairs)
            : 36;
        const modesDone = Number(d.completed || 0) * modesPerCell;
        const modesTotal = meta.num_t1_modes * meta.num_t2_modes;
        const wTag = d.compute_worker ? `[${d.compute_worker}] ` : "";
        if ($("ll-progress-fill")) $("ll-progress-fill").style.width = `${pct.toFixed(1)}%`;
        if ($("ll-progress-text")) {
          $("ll-progress-text").textContent = isEs
            ? `${wTag}${d.completed} / ${d.total} pares de lead (${modesDone.toLocaleString()} / ${modesTotal.toLocaleString()} modos)`
            : `${wTag}${d.completed} / ${d.total} lead pairs (${modesDone.toLocaleString()} / ${modesTotal.toLocaleString()} modes)`;
        }
        if ($("ll-progress-eta")) {
          const hwInfo = d.hardware_device ? `${d.hardware_device} · ` : "";
          $("ll-progress-eta").textContent = `${hwInfo}${d.elapsed_s}s · ETA ~${d.eta_s}s`;
        }
      });

      es.addEventListener("done", (ev) => {
        const fullRes = JSON.parse(ev.data);
        es.close();
        ll.activeStream = null;
        ll.running = false;
        ll.result = fullRes;
        Object.keys(llWorkersLive).forEach((wk) => {
          llWorkersLive[wk].done = true;
          if (fullRes.worker_cell_counts && fullRes.worker_cell_counts[wk] != null) {
            llWorkersLive[wk].count = Number(fullRes.worker_cell_counts[wk]);
          }
        });
        renderLeadLabWorkersStrip(llWorkersLive);
        ll.currentMatchupHash = fullRes.matchup_hash || "";
        ll.cachedDeepAuditKeys = new Set(fullRes.cached_deep_audit_keys || []);
        updateLeadLabControlsUI();
        updateLeadLabExportButtons(fullRes.vault_run_id || "");
        if ($("ll-progress-fill")) $("ll-progress-fill").style.width = "100%";
        if ($("ll-status-dot")) $("ll-status-dot").className = "status-dot done";

        // Reconstruct complete, strictly ordered (1,1 -> 15,15) hardware-tagged Lead Lab CLI log AFTER all workers join
        clearLeadLabCli();
        const hwCounts = fullRes.worker_cell_counts || {};
        const hwSplitStr = Object.entries(hwCounts)
          .sort((a, b) => a[0].localeCompare(b[0]))
          .map(([wk, cnt]) => `${wk}=${cnt}`)
          .join(" · ");
        const hwDevName = fullRes.hardware_device_name || fullRes.device_used || meta.device;
        appendLeadLabCli(
          "HARDWARE",
          `${hwDevName} · ${hwSplitStr || `${meta.total_lead_pairs} cells`} · ${fullRes.elapsed_s}s`,
          "tag-nash"
        );
        const t1Leads = fullRes.trainer_1_leads || meta.t1_leads || [];
        const t2Leads = fullRes.trainer_2_leads || meta.t2_leads || [];
        const cells2d = fullRes.heatmap_cells || [];
        let seqNum = 0;
        const totPairs = t1Leads.length * t2Leads.length;
        for (let r = 0; r < cells2d.length; r++) {
          const row = cells2d[r] || [];
          for (let c = 0; c < row.length; c++) {
            const cell = row[c];
            if (!cell || typeof cell.score !== "number") continue;
            seqNum += 1;
            const l1Pair = t1Leads[r] || ["?", "?"];
            const l2Pair = t2Leads[c] || ["?", "?"];
            const sc = Number(cell.score || 0);
            const cv = Number(cell.cvar_10 || 0);
            const backStr = (cell.best_t1_bench || []).join("+");
            const wLbl = cell.compute_worker || (String(fullRes.device_used || "").startsWith("cuda") ? "GPU" : "CPU-W1");
            const cTag = `${wLbl} ${String(seqNum).padStart(3, "0")}/${totPairs}`;
            appendLeadLabCli(
              cTag,
              `${l1Pair[0]}+${l1Pair[1]} vs ${l2Pair[0]}+${l2Pair[1]} → v*=${sc >= 0 ? "+" : ""}${sc.toFixed(2)} (CVaR₁₀ ${cv >= 0 ? "+" : ""}${cv.toFixed(2)}) · Back: ${backStr}`,
              sc >= 0.12 ? "tag-win" : sc <= -0.12 ? "tag-err" : ""
            );
          }
        }

        const topBring = (fullRes.trainer_1_top_brings && fullRes.trainer_1_top_brings[0]) || null;
        const gv = Number(fullRes.global_game_value || 0);
        appendLeadLabCli(
          "NASH",
          topBring
            ? `Global ${fullRes.num_t1_modes}×${fullRes.num_t2_modes} LP solved in ${fullRes.elapsed_s}s · v*=${gv >= 0 ? "+" : ""}${gv.toFixed(3)} · #1 Bring: ${topBring.lead_species.join("+")} [${topBring.bench_species.join("/")}] (${(topBring.nash_weight * 100).toFixed(1)}%)`
            : `Global ${fullRes.num_t1_modes}×${fullRes.num_t2_modes} LP solved in ${fullRes.elapsed_s}s · v*=${gv >= 0 ? "+" : ""}${gv.toFixed(3)}`,
          "tag-nash"
        );
        if (fullRes.vault_run_id) {
          appendLeadLabCli(
            "VAULT",
            isEs
              ? `Matchup guardado automáticamente en DuckDB Vault (${fullRes.vault_run_id.slice(0, 10)}).`
              : `Matchup auto-saved to DuckDB Vault (${fullRes.vault_run_id.slice(0, 10)}).`,
            "tag-win"
          );
        }
        if (statusEl) {
          statusEl.textContent = isEs
            ? `Equilibrio de Nash ${fullRes.num_t1_modes}×${fullRes.num_t2_modes} completado en ${fullRes.elapsed_s}s (${fullRes.device_used}) y guardado en Vault.`
            : `${fullRes.num_t1_modes}×${fullRes.num_t2_modes} Nash Equilibrium complete in ${fullRes.elapsed_s}s (${fullRes.device_used}) and saved to Vault.`;
        }
        renderLeadLabPodium(fullRes);
        if (fullRes.trainer_1_top_brings && fullRes.trainer_1_top_brings.length && fullRes.trainer_2_top_brings && fullRes.trainer_2_top_brings.length) {
          const top1 = fullRes.trainer_1_top_brings[0];
          const top2 = fullRes.trainer_2_top_brings[0];
          selectLeadLabCell(top1.lead_idx, top2.lead_idx, top1.bench_idx, top2.bench_idx);
        }
        refreshLeadLabVault();
        scheduleLeadLabCacheLookup(0);
      });

      es.addEventListener("cancelled", () => {
        es.close();
        ll.activeStream = null;
        ll.running = false;
        updateLeadLabControlsUI();
        if ($("ll-status-dot")) $("ll-status-dot").className = "status-dot";
        appendLeadLabCli("STOP", isEs ? "Simulación detenida limpiamente por el usuario." : "Sweep cleanly cancelled by user.", "tag-stop");
        if (statusEl) statusEl.textContent = isEs ? "Simulación detenida por el usuario." : "Simulation cancelled by user.";
      });

      es.addEventListener("error", (ev) => {
        let msg = "Stream error";
        try {
          if (ev && ev.data) msg = JSON.parse(ev.data).error || msg;
        } catch (_) {}
        es.close();
        ll.activeStream = null;
        ll.running = false;
        updateLeadLabControlsUI();
        if ($("ll-status-dot")) $("ll-status-dot").className = "status-dot error";
        appendLeadLabCli("ERR", msg, "tag-err");
        if (statusEl) statusEl.textContent = `Error: ${msg}`;
      });
    } catch (err) {
      ll.running = false;
      updateLeadLabControlsUI();
      appendLeadLabCli("ERR", String(err), "tag-err");
      if (statusEl) statusEl.textContent = `Error: ${String(err)}`;
    }
  }

  // Wire Lead Lab Event Listeners
  if ($("ll-t1-roster-select")) {
    $("ll-t1-roster-select").onchange = () => {
      renderLeadLabRosterPreview("t1");
      scheduleLeadLabCacheLookup(50);
    };
  }
  if ($("ll-t2-roster-select")) {
    $("ll-t2-roster-select").onchange = () => {
      renderLeadLabRosterPreview("t2");
      scheduleLeadLabCacheLookup(50);
    };
  }
  if ($("ll-preset-select")) {
    $("ll-preset-select").onchange = () => scheduleLeadLabCacheLookup(50);
  }
  if ($("ll-t1-paste-input")) {
    $("ll-t1-paste-input").oninput = () => scheduleLeadLabCacheLookup(350);
  }
  if ($("ll-t2-paste-input")) {
    $("ll-t2-paste-input").oninput = () => scheduleLeadLabCacheLookup(350);
  }
  if ($("btn-ll-vault-toggle")) {
    $("btn-ll-vault-toggle").onclick = () => {
      state.leadLab.vaultOpen = !state.leadLab.vaultOpen;
      if ($("ll-vault-panel")) {
        $("ll-vault-panel").style.display = state.leadLab.vaultOpen ? "block" : "none";
      }
      if (state.leadLab.vaultOpen) refreshLeadLabVault();
    };
  }
  if ($("btn-ll-vault-close")) {
    $("btn-ll-vault-close").onclick = () => {
      state.leadLab.vaultOpen = false;
      if ($("ll-vault-panel")) $("ll-vault-panel").style.display = "none";
    };
  }
  if ($("ll-vault-search")) {
    let vaultSearchTimer = null;
    $("ll-vault-search").oninput = (ev) => {
      state.leadLab.vaultSearch = String(ev.target.value || "").trim();
      if (vaultSearchTimer) clearTimeout(vaultSearchTimer);
      vaultSearchTimer = setTimeout(refreshLeadLabVault, 180);
    };
  }
  if ($("ll-vault-t1-filter")) {
    $("ll-vault-t1-filter").onchange = (ev) => {
      state.leadLab.vaultFilterT1 = String(ev.target.value || "");
      refreshLeadLabVault();
    };
  }
  document.querySelectorAll("[data-ll-adv]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.leadLab.vaultFilterAdv = btn.dataset.llAdv || "";
      document.querySelectorAll("[data-ll-adv]").forEach((b) => {
        b.classList.toggle("active", b === btn);
      });
      refreshLeadLabVault();
    });
  });
  if ($("btn-ll-cache-load")) {
    $("btn-ll-cache-load").onclick = () => {
      if (state.leadLab.cacheHit && state.leadLab.cacheHit.run_id) {
        loadLeadLabFromVault(state.leadLab.cacheHit.run_id);
      }
    };
  }
  if ($("btn-ll-cache-rerun")) {
    $("btn-ll-cache-rerun").onclick = () => launchLeadLabSweep();
  }
  if ($("btn-ll-t1-paste")) {
    $("btn-ll-t1-paste").onclick = () => {
      state.leadLab.t1UsePaste = !state.leadLab.t1UsePaste;
      updateLeadLabControlsUI();
      scheduleLeadLabCacheLookup(100);
    };
  }
  if ($("btn-ll-t2-paste")) {
    $("btn-ll-t2-paste").onclick = () => {
      state.leadLab.t2UsePaste = !state.leadLab.t2UsePaste;
      updateLeadLabControlsUI();
      scheduleLeadLabCacheLookup(100);
    };
  }
  if ($("btn-ll-t2-mode-full")) {
    $("btn-ll-t2-mode-full").onclick = () => {
      state.leadLab.t2Mode = "full";
      updateLeadLabControlsUI();
      scheduleLeadLabCacheLookup(100);
    };
  }
  if ($("btn-ll-t2-mode-scout")) {
    $("btn-ll-t2-mode-scout").onclick = () => {
      state.leadLab.t2Mode = "scout";
      updateLeadLabControlsUI();
      scheduleLeadLabCacheLookup(100);
    };
  }
  if ($("ll-scout-file-input")) {
    $("ll-scout-file-input").onchange = async (ev) => {
      const files = Array.from(ev.target.files || []).slice(0, 3);
      const loaded = [];
      for (const f of files) {
        loaded.push({ filename: f.name, raw_input: await f.text() });
      }
      state.leadLab.scoutReplays = loaded;
      if ($("ll-scout-files-label")) {
        $("ll-scout-files-label").textContent = loaded.map((x) => x.filename).join(" · ");
      }
      updateLeadLabControlsUI();
    };
  }
  if ($("btn-ll-t2-solve-sp")) {
    $("btn-ll-t2-solve-sp").onclick = async () => {
      const isEs = state.lang === "es";
      const msgEl = $("ll-scout-status-msg");
      const ll = state.leadLab;
      if (msgEl) msgEl.textContent = isEs ? "Resolviendo 66-SP con Smogon Champions..." : "Solving opponent 66-SP with Smogon Champions...";
      try {
        const body = {
          replays: ll.scoutReplays,
          t2_ots_paste_text: ($("ll-t2-ots-input") && $("ll-t2-ots-input").value.trim()) || "",
        };
        if (ll.t1UsePaste) body.t1_paste_text = ($("ll-t1-paste-input") && $("ll-t1-paste-input").value.trim()) || "";
        else body.t1_roster_id = ($("ll-t1-roster-select") && $("ll-t1-roster-select").value) || "";
        const res = await fetch("/api/lead-lab/infer-opponent", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const d = await res.json();
        if (!res.ok || !d.ok) {
          if (msgEl) msgEl.textContent = `Error: ${d.error || "Inference failed"}`;
          return;
        }
        ll.t2Inference = d;
        ll.t2UserSpreads = {};
        (d.pokemon || []).forEach((m) => {
          ll.t2UserSpreads[m.base_species] = Object.assign({}, m.active_spread || m.default_spread);
        });
        if (msgEl) {
          msgEl.textContent = isEs
            ? `66-SP rival acotado desde ${d.games_pooled} partida(s). Ajusta sliders si deseas y pulsa Simular.`
            : `Opponent 66-SP bounded from ${d.games_pooled} game(s). Adjust sliders if desired and click Run.`;
        }
        renderLeadLabClampedSpPanel();
      } catch (err) {
        if (msgEl) msgEl.textContent = `Error: ${String(err)}`;
      }
    };
  }
  if ($("btn-ll-t2-reset-all")) {
    $("btn-ll-t2-reset-all").onclick = () => {
      const inf = state.leadLab.t2Inference;
      if (!inf) return;
      (inf.pokemon || []).forEach((m) => {
        state.leadLab.t2UserSpreads[m.base_species] = Object.assign({}, m.default_spread);
      });
      renderLeadLabClampedSpPanel();
    };
  }
  async function cancelLeadLabSweep() {
    const isEs = state.lang === "es";
    try {
      await fetch("/api/lead-lab/cancel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
    } catch (_) {}
    if (state.leadLab.activeStream) {
      try { state.leadLab.activeStream.close(); } catch (_) {}
      state.leadLab.activeStream = null;
    }
    state.leadLab.running = false;
    updateLeadLabControlsUI();
    if ($("ll-status-dot")) $("ll-status-dot").className = "status-dot";
    appendLeadLabCli("STOP", isEs ? "Simulación detenida por el usuario." : "Simulation cancelled by user.", "tag-stop");
    if ($("ll-status-msg")) {
      $("ll-status-msg").textContent = isEs
        ? "Simulación detenida por el usuario."
        : "Simulation cancelled by user.";
    }
  }

  if ($("btn-ll-launch")) $("btn-ll-launch").onclick = launchLeadLabSweep;
  if ($("btn-ll-cancel")) $("btn-ll-cancel").onclick = cancelLeadLabSweep;
  if ($("btn-ll-cancel-bar")) $("btn-ll-cancel-bar").onclick = cancelLeadLabSweep;
  if ($("btn-ll-toggle-cli")) {
    $("btn-ll-toggle-cli").onclick = () => {
      const box = $("ll-cli-console");
      if (!box) return;
      box.style.display = box.style.display === "none" ? "block" : "none";
    };
  }
  if ($("btn-ll-deep-audit")) {
    $("btn-ll-deep-audit").onclick = async () => {
      const ll = state.leadLab;
      const res = ll.result;
      if (!res || !ll.jobId || ll.selectedLead1 === null) return;
      const isEs = state.lang === "es";
      const reqL1 = ll.selectedLead1;
      const reqL2 = ll.selectedLead2;
      const reqB1 = ll.selectedBench1;
      const reqB2 = ll.selectedBench2;
      const reqSeq = ++ll.deepAuditReqSeq;
      const cell = res.heatmap_cells[reqL1][reqL2];
      const b1Pair = (cell.t1_bench_labels && cell.t1_bench_labels[reqB1]) || [];
      const b2Pair = (cell.t2_bench_labels && cell.t2_bench_labels[reqB2]) || [];
      const wantCanonKey = canonicalLeadLabCellKey(cell.lead_1, b1Pair, cell.lead_2, b2Pair);
      const nb1 = (cell.t1_bench_labels || []).length || 1;
      const nb2 = (cell.t2_bench_labels || []).length || 1;
      const m1Idx = reqL1 * nb1 + reqB1;
      const m2Idx = reqL2 * nb2 + reqB2;
      const deepBox = $("ll-deep-audit-box");
      appendLeadLabCli(
        "DEEP",
        `Running unpruned Turn-1 Tensor Core audit (${cell.lead_1.join("+")} [${b1Pair.join("/")}] vs ${cell.lead_2.join("+")} [${b2Pair.join("/")}], K=128)...`,
        "tag-deep"
      );
      if (deepBox) {
        deepBox.style.display = "flex";
        deepBox.innerHTML = `<div class="muted-sm">${isEs ? "Ejecutando Tensor Core sin poda (K=128) para este 4v4..." : "Running full unpruned Turn-1 Tensor Core audit (K=128)..."}</div>`;
      }
      try {
        const resp = await fetch("/api/lead-lab/deep-turn1", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            job_id: ll.jobId,
            mode_1_idx: m1Idx,
            mode_2_idx: m2Idx,
            lead_1: cell.lead_1,
            bench_1: b1Pair,
            lead_2: cell.lead_2,
            bench_2: b2Pair,
            num_mc: 128,
          }),
        });
        const d = await resp.json();
        if (!resp.ok || !d.ok) {
          if (reqSeq === ll.deepAuditReqSeq) {
            appendLeadLabCli("ERR", d.error || "Deep audit failed", "tag-err");
            if (deepBox) deepBox.innerHTML = `<div class="muted-sm" style="color:#fda4af">Error: ${escapeHtml(d.error || "Audit failed")}</div>`;
          }
          return;
        }
        if (d.audit_cell_key) {
          if (!ll.cachedDeepAuditKeys) ll.cachedDeepAuditKeys = new Set();
          ll.cachedDeepAuditKeys.add(d.audit_cell_key);
          if (!ll.batchAuditsByKey) ll.batchAuditsByKey = {};
          ll.batchAuditsByKey[d.audit_cell_key] = d;
        }
        appendLeadLabCli(
          "DEEP",
          `${d.from_vault_cache ? "[VAULT CACHE] " : ""}Audit done in ${d.elapsed_s}s [${(d.matrix_shape || []).join("×")}] · v*=${Number(d.nash_value || 0) >= 0 ? "+" : ""}${Number(d.nash_value || 0).toFixed(3)} · #1: ${(d.top_actions && d.top_actions[0] && d.top_actions[0].desc) || ""}`,
          "tag-deep"
        );
        // Guard against stale async race: ONLY paint the box if user is still viewing this exact cell & species match!
        const stillSameCell =
          reqSeq === ll.deepAuditReqSeq &&
          ll.selectedLead1 === reqL1 &&
          ll.selectedLead2 === reqL2 &&
          ll.selectedBench1 === reqB1 &&
          ll.selectedBench2 === reqB2;
        const speciesMatch =
          !d.mode_1 ||
          !d.mode_2 ||
          canonicalLeadLabCellKey(
            d.mode_1.lead_species,
            d.mode_1.bench_species,
            d.mode_2.lead_species,
            d.mode_2.bench_species
          ) === wantCanonKey;
        if (stillSameCell && speciesMatch) {
          ll.deepAudit = d;
          renderLeadLabDrilldown();
          renderLeadLabDeepAuditBox(d);
        }
        renderLeadLabPlaybook();
        refreshLeadLabVault();
      } catch (err) {
        if (reqSeq === ll.deepAuditReqSeq) {
          appendLeadLabCli("ERR", String(err), "tag-err");
          if (deepBox) deepBox.innerHTML = `<div class="muted-sm" style="color:#fda4af">Error: ${escapeHtml(String(err))}</div>`;
        }
      }
    };
  }

  if ($("btn-ll-pb-by-mine")) {
    $("btn-ll-pb-by-mine").onclick = () => {
      state.leadLab.playbookMode = "by_mine";
      state.leadLab.playbookSelectedIdx = null;
      renderLeadLabPlaybook();
    };
  }
  if ($("btn-ll-pb-by-opp")) {
    $("btn-ll-pb-by-opp").onclick = () => {
      state.leadLab.playbookMode = "by_opp";
      state.leadLab.playbookSelectedIdx = null;
      renderLeadLabPlaybook();
    };
  }
  if ($("btn-ll-deep-batch")) {
    $("btn-ll-deep-batch").onclick = async () => {
      const ll = state.leadLab;
      if (!ll.jobId || !ll.result) return;
      const { pairs } = _getActivePlaybookPairs();
      if (!pairs.length) return;
      const isEs = state.lang === "es";
      const btn = $("btn-ll-deep-batch");
      btn.disabled = true;
      const origHtml = btn.innerHTML;
      btn.textContent = isEs ? `⏳ Auditando ${pairs.length} pares (K=128)...` : `⏳ Auditing ${pairs.length} pairs (K=128)...`;
      appendLeadLabCli("DEEP", `Running batch K=128 unpruned Turn-1 audits for ${pairs.length} Playbook pairs...`, "tag-deep");
      try {
        const resp = await fetch("/api/lead-lab/deep-turn1-batch", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            job_id: ll.jobId,
            num_mc: 128,
            pairs: pairs.map((p) => ({
              mode_1_idx: p.mode_1_idx,
              mode_2_idx: p.mode_2_idx,
              lead_1: p.lead_1,
              bench_1: p.bench_1,
              lead_2: p.lead_2,
              bench_2: p.bench_2,
            })),
          }),
        });
        const data = await resp.json();
        if (!resp.ok || !data.ok) {
          appendLeadLabCli("ERR", data.error || "Batch deep audit failed", "tag-err");
          return;
        }
        if (!ll.cachedDeepAuditKeys) ll.cachedDeepAuditKeys = new Set();
        if (!ll.batchAuditsByKey) ll.batchAuditsByKey = {};
        for (const aud of data.audits || []) {
          if (aud && aud.audit_cell_key) {
            ll.cachedDeepAuditKeys.add(aud.audit_cell_key);
            ll.batchAuditsByKey[aud.audit_cell_key] = aud;
          }
        }
        appendLeadLabCli(
          "DEEP",
          `Batch K=128 complete: ${data.count} pairs (${data.cached_count} Vault hits, ${data.computed_count} freshly computed).`,
          "tag-deep"
        );
        renderLeadLabPlaybook();
        renderLeadLabDrilldown();
        refreshLeadLabVault();
      } catch (err) {
        appendLeadLabCli("ERR", String(err), "tag-err");
      } finally {
        btn.disabled = false;
        btn.innerHTML = origHtml;
      }
    };
  }

  // -------------------------------------------------------------------------
  // Legal Disclaimer & Third-Party Vendor Credits Modal (Bilingual ES/EN)
  // -------------------------------------------------------------------------
  function renderLegalModalBody() {
    const box = $("legal-modal-content");
    if (!box) return;
    const isEs = state.lang === "es";
    if ($("lbl-legal-modal-title")) {
      $("lbl-legal-modal-title").textContent = isEs
        ? "⚖ Aviso Legal, Propiedad Intelectual y Créditos de Terceros"
        : "⚖ Legal Notice, Intellectual Property & Third-Party Credits";
    }
    const rows = [
      {
        name: "Pokéos",
        url: "https://www.pokeos.com/",
        role: isEs
          ? "Sprites Pokémon (128×128), íconos de objetos y Megapiedras (24×24), y catálogos Regulation M-C / M-D"
          : "Pokémon sprites (128×128), held item & Mega Stone icons (24×24), and Regulation M-C / M-D catalogs",
        lic: isEs ? "Activos Pokémon © Nintendo / Creatures / GAME FREAK / TPCi" : "Pokémon assets © Nintendo / Creatures / GAME FREAK / TPCi",
      },
      {
        name: "@smogon/calc (v0.12.0)",
        url: "https://github.com/smogon/damage-calc",
        role: isEs ? "Motor oficial de cálculo de daño Champions (bundle offline)" : "Official Champions damage calculation engine (offline bundle)",
        lic: "MIT (© Honko & contributors)",
      },
      {
        name: "Pokémon Showdown",
        url: "https://github.com/smogon/pokemon-showdown",
        role: isEs ? "Reproductor de replays (replay-embed.js) y datos del mod Champions" : "Replay player (replay-embed.js) & Champions mod data",
        lic: "MIT (© Guangcong Luo / Zarel & contributors)",
      },
      {
        name: "MunchStats",
        url: "https://www.munchstats.com/",
        role: isEs ? "Resultados de torneos regionales VGC y estadísticas de uso meta" : "Regional VGC tournament standings & meta usage stats",
        lic: isEs ? "Dataset comunitario" : "Community dataset",
      },
      {
        name: "PyTorch",
        url: "https://pytorch.org/",
        role: isEs ? "Motor GPU/CPU del Tensor Core y evaluación 8-Pillar Victory Equity" : "GPU/CPU Tensor Core state machine & 8-pillar equity engine",
        lic: "BSD-3-Clause",
      },
      {
        name: "DuckDB",
        url: "https://duckdb.org/",
        role: isEs ? "Base de datos en memoria y almacenamiento persistente OTS / Lead Lab Vault" : "In-memory SQL engine & persistent OTS / Lead Lab Matchup Vault",
        lic: "MIT",
      },
      {
        name: "SciPy & HiGHS",
        url: "https://scipy.org/",
        role: isEs ? "Solver exacto de Equilibrio de Nash (LP HiGHS) y calibración L-BFGS-B" : "Exact Zero-Sum Nash LP solver (HiGHS) & L-BFGS-B weight tuner",
        lic: "BSD-3-Clause / MIT (HiGHS)",
      },
      {
        name: "NumPy",
        url: "https://numpy.org/",
        role: isEs ? "Álgebra matricial y puente numérico de tensores" : "Vectorized numerical arrays & tensor bridges",
        lic: "BSD-3-Clause",
      },
      {
        name: "PyMiniRacer & V8",
        url: "https://github.com/bpcreech/PyMiniRacer",
        role: isEs ? "Sandbox JS V8 en proceso sin Node.js para Smogon Champions Calc" : "In-process V8 sandbox (zero Node.js) for Smogon Champions Calc",
        lic: "ISC / BSD-3-Clause (V8)",
      },
    ];

    const tableRowsHtml = rows
      .map(
        (r) => `<tr>
          <td><a href="${escapeHtml(r.url)}" target="_blank" rel="noopener noreferrer"><strong>${escapeHtml(r.name)}</strong></a></td>
          <td>${escapeHtml(r.role)}</td>
          <td>${escapeHtml(r.lic)}</td>
        </tr>`
      )
      .join("");

    box.innerHTML = `
      <div class="legal-callout">
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:4px">
          <span class="community-chip"><img src="/assets/community/pokemmunity.png" alt="Pokémmunity MÉXICO" /><strong>Pokémmunity</strong></span>
          <span class="community-chip"><img src="/assets/community/pokemex.png" alt="PokéMex" /><strong>PokéMex</strong></span>
          <strong>${isEs ? "Agradecimiento Especial a la Comunidad" : "Special Community Thanks"}</strong>
        </div>
        ${
          isEs
            ? "Muchas gracias a los chats grupales de Pokémmunity MÉXICO y PokéMex por todo su apoyo, pruebas y comentarios que ayudaron a mejorar Coach Porygon VGC."
            : "Special thanks to the Pokémmunity MÉXICO and PokéMex group chats for their continuous support, testing, and feedback to improve Coach Porygon VGC."
        }
      </div>
      <div class="legal-callout">
        <strong>${isEs ? "100% Proyecto Fan — Sin Fines de Lucro (Nunca Monetizado)" : "100% Fan-Made Project — Strictly Non-Commercial (Never Monetized)"}</strong><br/>
        ${
          isEs
            ? "Coach Porygon VGC es una herramienta gratuita hecha por fans para fans del VGC competitivo. Nunca tendrá anuncios, suscripciones, muros de pago ni monetización."
            : "Coach Porygon VGC is a free tool built by fans for competitive VGC fans. It will never have ads, paywalls, subscriptions, or monetization."
        }
      </div>
      <div class="legal-callout warn">
        <strong>${isEs ? "Propiedad Intelectual de Pokémon" : "Pokémon Intellectual Property Disclaimer"}</strong><br/>
        ${
          isEs
            ? "Pokémon, Pokémon Champions y todos los nombres de especies, formas, Megaevoluciones, movimientos, objetos, habilidades y sprites son marcas registradas y propiedad intelectual de © 1995–2026 Nintendo, Creatures Inc., GAME FREAK inc. y The Pokémon Company. Este proyecto no está afiliado, respaldado ni patrocinado por ellos. La licencia AGPLv3 del repositorio cubre exclusivamente el código fuente original y excluye todos los activos y marcas de Pokémon."
            : "Pokémon, Pokémon Champions, and all species names, forms, Mega Evolutions, moves, items, abilities, and sprites are registered trademarks and copyrights of © 1995–2026 Nintendo, Creatures Inc., GAME FREAK inc., and The Pokémon Company. This project is not affiliated with, endorsed by, or sponsored by them. The repository's AGPLv3 license applies strictly to original source code and excludes all Pokémon IP and sprites."
        }
      </div>
      <table class="legal-table">
        <thead>
          <tr>
            <th>${isEs ? "Proveedor / Fuente" : "Vendor / Source"}</th>
            <th>${isEs ? "Uso en Coach Porygon VGC" : "Role in Coach Porygon VGC"}</th>
            <th>${isEs ? "Licencia / Derechos" : "License / Rights"}</th>
          </tr>
        </thead>
        <tbody>${tableRowsHtml}</tbody>
      </table>
      <div class="muted-xs">
        ${
          isEs
            ? "Licencia del código fuente: GNU AGPLv3 (ver LICENSE y THIRD_PARTY_NOTICES.md en el repositorio). Contacto para titulares de derechos: esquedevil94@gmail.com."
            : "Source code license: GNU AGPLv3 (see LICENSE and THIRD_PARTY_NOTICES.md in the repository). Rights-holder removal contact: esquedevil94@gmail.com."
        }
      </div>
    `;
  }

  function updateLegalFooterAndModalCopy() {
    const isEs = state.lang === "es";
    if ($("lbl-footer-community")) {
      $("lbl-footer-community").textContent = isEs
        ? "Agradecimiento especial a los grupos Pokémmunity y PokéMex por su apoyo y comentarios para mejorar la app."
        : "Special thanks to the Pokémmunity and PokéMex group chats for their support and feedback to improve the app.";
    }
    if ($("lbl-footer-fan-pill")) {
      $("lbl-footer-fan-pill").textContent = isEs
        ? "FAN-MADE · 100% NO COMERCIAL"
        : "FAN-MADE · 100% NON-COMMERCIAL";
    }
    if ($("lbl-footer-disclaimer")) {
      $("lbl-footer-disclaimer").textContent = isEs
        ? "Proyecto hecho por fans para fans, nunca monetizado. Pokémon, nombres y sprites © Nintendo / Creatures Inc. / GAME FREAK inc. / The Pokémon Company. Sin afiliación ni patrocinio oficial."
        : "Fan-made for fans, never monetized. Pokémon, names & sprites © Nintendo / Creatures Inc. / GAME FREAK inc. / The Pokémon Company. Not affiliated or endorsed.";
    }
    if ($("lbl-footer-credits")) {
      $("lbl-footer-credits").innerHTML =
        `${isEs ? "Créditos:" : "Credits:"} ` +
        `<a href="https://www.pokeos.com/" target="_blank" rel="noopener noreferrer">Pokéos</a> · ` +
        `<a href="https://github.com/smogon/damage-calc" target="_blank" rel="noopener noreferrer">@smogon/calc</a> · ` +
        `<a href="https://github.com/smogon/pokemon-showdown" target="_blank" rel="noopener noreferrer">Pokémon Showdown</a> · ` +
        `<a href="https://www.munchstats.com/" target="_blank" rel="noopener noreferrer">MunchStats</a> · ` +
        `PyTorch · DuckDB · SciPy/HiGHS · NumPy · MiniRacer`;
    }
    if ($("btn-open-legal-modal")) {
      $("btn-open-legal-modal").textContent = isEs ? "⚖ Legal y Créditos" : "⚖ Legal & Credits";
    }
    renderLegalModalBody();
  }

  if ($("btn-open-legal-modal")) {
    $("btn-open-legal-modal").onclick = () => {
      renderLegalModalBody();
      if ($("legal-modal")) $("legal-modal").style.display = "flex";
    };
  }
  if ($("btn-close-legal-modal")) {
    $("btn-close-legal-modal").onclick = () => {
      if ($("legal-modal")) $("legal-modal").style.display = "none";
    };
  }
  if ($("legal-modal")) {
    $("legal-modal").onclick = (ev) => {
      if (ev.target === $("legal-modal")) $("legal-modal").style.display = "none";
    };
  }

  // Boot onto Coach Porygon VGC Cyber-Tactical Command Hub
  (async function init() {
    const res = await fetch("/api/state");
    state.app = await res.json();
    const prefix = state.app.device_type === "cuda" ? "CUDA" : "CPU";
    $("hw-badge").textContent = `${prefix}: ${state.app.device}`;
    if ($("home-hw-pill")) {
      $("home-hw-pill").textContent = `${prefix} · ${state.app.device}`;
    }
    if ($("home-db-pill")) {
      const nRosters = (state.app.rosters || []).length;
      $("home-db-pill").textContent = `DuckDB · ${nRosters} OTS Teams`;
    }
    renderSavedTeamsList("t1");
    renderSavedTeamsList("t2");
    populatePrepRosterSelect();
    populateLeadLabRosterSelects();
    setStep("home");
    applyAllTranslations();
  })();
})();
