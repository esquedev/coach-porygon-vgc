(function () {
  "use strict";

  const state = {
    app: null,
    activeStep: "setup",
    activeCoachTab: "advice",
    lang: localStorage.getItem("porygon_lang") || "es",
    style: localStorage.getItem("porygon_style") || "vgc",
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
    prevStepBeforePrep: "setup",
    prep: {
      kind: "speed_tiers",
      topN: 50,
      usePaste: false,
      token: null,
      filename: "",
      generating: false,
      meta: null,
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
      state.prevStepBeforePrep = state.activeStep || "setup";
    }
    state.activeStep = stepName;
    ["setup", "pipeline", "review", "prep"].forEach((s) => {
      const view = $(`view-${s}`);
      const btn = $(`nav-step-${s}`);
      if (view) view.classList.toggle("active", s === stepName);
      if (btn) btn.classList.toggle("active", s === stepName);
    });
    const prepTopBtn = $("btn-open-prep-view");
    if (prepTopBtn) prepTopBtn.classList.toggle("active", stepName === "prep");
  }

  function setCoachTab(tabName) {
    state.activeCoachTab = tabName;
    ["advice", "matrix", "board"].forEach((t) => {
      const btn = $(`tab-btn-${t}`);
      if (btn) btn.classList.toggle("active", t === tabName);
    });
    if (state.turnResults[state.currentTurn]) {
      renderTurnPanel(state.turnResults[state.currentTurn]);
    }
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

    $("tab-btn-advice").textContent = isEs ? "Consejos" : "Advice";
    $("tab-btn-matrix").textContent = isSci
      ? (isEs ? "Matriz Nash / IEDS" : "Nash / IEDS Matrix")
      : (isEs ? "Todas las Jugadas" : "All Plays");
    $("tab-btn-board").textContent = isEs ? "Tablero y Curva" : "Board & Graph";

    if ($("lbl-prep-btn")) {
      $("lbl-prep-btn").textContent = isEs ? "Herramientas Prep" : "Prep Tools";
    }
    if ($("btn-prep-back")) {
      $("btn-prep-back").textContent = isEs ? "← Volver al Studio" : "← Back to Studio";
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
    if ($("lbl-analytics-btn")) {
      $("lbl-analytics-btn").textContent = isEs ? "Analítica" : "Analytics";
    }
    if ($("lbl-analytics-modal-title")) {
      $("lbl-analytics-modal-title").textContent = isEs
        ? "Analítica de Sesiones y Torneos Bo3"
        : "Bo3 & Tournament Session Analytics";
    }
    if ($("btn-refresh-analytics")) {
      $("btn-refresh-analytics").textContent = isEs ? "Actualizar" : "Refresh";
    }
    $("lbl-bug-btn").textContent = isEs ? "Reportar Bug" : "Report Bug";
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
    const games =
      (state.app && state.app.bo3_games && state.app.bo3_games.length
        ? state.app.bo3_games
        : state.bo3GamesMeta) || [];
    const isEs = state.lang === "es";
    const containers = [$("setup-bo3-tabs"), $("pipeline-bo3-tabs"), $("review-bo3-tabs")];
    if (games.length <= 1) {
      containers.forEach((el) => {
        if (el) {
          el.style.display = "none";
          el.innerHTML = "";
        }
      });
      return;
    }

    const html = games
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

    containers.forEach((el) => {
      if (!el) return;
      el.style.display = el.classList.contains("bo3-tabs-inline") ? "inline-flex" : "flex";
      el.innerHTML = html;
      el.querySelectorAll("[data-bo3-idx]").forEach((btn) => {
        btn.addEventListener("click", () => switchBo3Game(parseInt(btn.dataset.bo3Idx, 10)));
      });
    });
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
  function renderPipelineLogs() {
    const feed = $("pipeline-log-feed");
    if (!feed) return;
    const pk = profileKey();
    let html = "";
    let lastTurn = -1;

    state.pipelineLogs.forEach((entry) => {
      if (entry.turn && entry.turn !== lastTurn) {
        lastTurn = entry.turn;
        html += `<div class="log-turn-header">${state.lang === "es" ? `Turno ${entry.turn}` : `Turn ${entry.turn}`}</div>`;
      }
      const msg = (entry.messages && (entry.messages[pk] || entry.messages.es_vgc)) || entry.error || "";
      html += `<div class="log-line">
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
    const numMc = parseInt($("setup-k-select").value || "128", 10);
    const twoPly = $("chk-two-ply") && $("chk-two-ply").checked ? 1 : 0;
    const isResume = startTurn > 1;

    if (!isResume) {
      state.turnResults = {};
      state.pipelineLogs = [];
      state.matchSummary = null;
      state.autoPausedTurns = {};
      $("pipeline-progress-fill").style.width = "0%";
      $("pipeline-progress-pill").textContent = `0 / ${state.app.replay.num_turns}`;
      renderPipelineLogs();
    }

    $("pipeline-done-banner").style.display = "none";
    $("pipeline-sub-meta").textContent = `${state.app.replay.trainer_1_name} vs. ${state.app.replay.trainer_2_name} · K=${numMc}${twoPly ? " · 2-Ply" : ""} · ${state.app.device}`;
    $("live-status-dot").className = "status-dot running";
    $("live-tile-badge").textContent = isResume ? `T${startTurn}` : "RUNNING";
    $("live-tile-text").textContent =
      state.lang === "es"
        ? (isResume ? `Reanudando desde Turno ${startTurn}...` : "Iniciando simulación...")
        : (isResume ? `Resuming from Turn ${startTurn}...` : "Starting simulation...");

    const es = new EventSource(`/api/analyze/stream?num_mc=${numMc}&start_turn=${startTurn}&two_ply=${twoPly}`);
    state.activeStream = es;
    updatePipelineActionButtons();

    es.addEventListener("log", (ev) => {
      const entry = JSON.parse(ev.data);
      const pk = profileKey();
      const msg = (entry.messages && (entry.messages[pk] || entry.messages.es_vgc)) || "";
      if (entry.in_place) {
        $("live-status-dot").className = "status-dot running";
        $("live-tile-badge").textContent = `T${entry.turn}`;
        $("live-tile-text").textContent = msg;
      } else {
        state.pipelineLogs.push(entry);
        renderPipelineLogs();
      }
    });

    es.addEventListener("turn", (ev) => {
      const data = JSON.parse(ev.data);
      state.turnResults[data.turn] = data;
      const doneCnt = Object.keys(state.turnResults).length;
      const totCnt = state.app.replay.num_turns;
      const pct = Math.min(100, Math.round((doneCnt / Math.max(1, totCnt)) * 100));
      $("pipeline-progress-fill").style.width = `${pct}%`;
      $("pipeline-progress-pill").textContent = `${doneCnt} / ${totCnt}`;
      renderTimeline();
    });

    es.addEventListener("error", (ev) => {
      if (ev.data) {
        try {
          const payload = JSON.parse(ev.data);
          state.pipelineLogs.push({
            turn: payload.turn || 0,
            phase: "ERROR",
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

    es.addEventListener("cancelled", () => {
      es.close();
      state.activeStream = null;
      $("live-status-dot").className = "status-dot error";
      $("live-tile-badge").textContent = state.lang === "es" ? "DETENIDO" : "STOPPED";
      updatePipelineActionButtons();
    });

    es.addEventListener("done", (ev) => {
      const payload = JSON.parse(ev.data || "{}");
      es.close();
      state.activeStream = null;
      $("live-status-dot").className = "status-dot done";
      $("live-tile-badge").textContent = "DONE";
      $("live-tile-text").textContent =
        state.lang === "es" ? "Todos los turnos analizados." : "All turns analyzed.";
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
    (state.app.telemetry_teams || ["char_y_v4", "char_y_v3"]).forEach((tf) => {
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
    $("turn-compute-meta").textContent = isSci
      ? `[${data.matrix_shape[0]}×${data.matrix_shape[1]}] · ${(data.total_timelines / 1000).toFixed(0)}k · ${data.elapsed_s}s`
      : `${data.elapsed_s}s`;

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

    const heroHtml = `
      <div class="verdict-hero ${com.badge_class}">
        <div class="verdict-row">
          <span class="verdict-pill ${com.badge_class}">${escapeHtml(com.symbol)} ${escapeHtml(com.badge)}</span>
          <span class="muted-xs">${escapeHtml(fieldStr)}</span>
        </div>
        <div class="verdict-headline">${escapeHtml(com.headline)}</div>

        <div class="compare-box">
          <div class="compare-line">
            <span class="compare-label">${isEs ? "Tu jugada" : "Your play"}</span>
            <span class="compare-play">${escapeHtml(act.desc)}</span>
            <span class="compare-delta">${fmtScore(act.risk_ev)}</span>
          </div>
          ${
            !sameAsBest
              ? `<div class="compare-line">
                  <span class="compare-label">${isEs ? "Recomendada #1" : "#1 Best line"}</span>
                  <span class="compare-play">${escapeHtml(best.desc)}</span>
                  <span class="compare-delta">${fmtScore(best.risk_ev)} (${lossVal > 0 ? "-" : ""}${lossVal.toFixed(isSci ? 3 : 2)})</span>
                </div>`
              : ""
          }
          <div class="compare-line">
            <span class="compare-label">${isEs ? "Rival jugó" : "Opponent"}</span>
            <span class="compare-play muted-sm">${escapeHtml(act.opp_actual_desc)}</span>
            <span class="compare-delta">#${act.rank}/${act.total_actions}</span>
          </div>
        </div>
      </div>
    `;

    let tabHtml = "";

    if (state.activeCoachTab === "advice") {
      const bulletsHtml = (com.bullets || [])
        .map(
          (b) => `<li class="advice-item ${b.tone}">
            <div class="advice-tag">${escapeHtml(b.tag)}</div>
            <div class="advice-text">${escapeHtml(b.text)}</div>
          </li>`
        )
        .join("");

      const tMix = getTermInfo("nash_mix", "Mix %", true);
      const top3 = (data.top_actions || []).slice(0, 3);
      const top3Html = top3
        .map(
          (r, i) => `<div class="top3-row ${r.is_played ? "is-played" : ""}">
            <span class="top3-rank">#${i + 1}</span>
            <span class="top3-desc">${escapeHtml(r.desc)}</span>
            <span class="top3-meta">${fmtScore(r.risk_ev)} · ${r.nash_pct.toFixed(0)}%</span>
          </div>`
        )
        .join("");

      tabHtml = `
        <div class="subhead">${isEs ? "Claves del turno" : "Key takeaways"}</div>
        <ul class="advice-list">${bulletsHtml}</ul>

        <div class="subhead">${isEs ? `Top 3 líneas (${tMix.label})` : `Top 3 lines (${tMix.label})`}</div>
        <div class="top3-list">${top3Html}</div>
      `;
    } else if (state.activeCoachTab === "matrix") {
      const tVal = getTermInfo("nash_value", "Turn Advantage", false);
      const tLoss = getTermInfo("nash_regret", "Play Cost", false);
      const tCvar = getTermInfo("cvar_10", "Bad-Luck Floor", false);
      const tSurv = getTermInfo("ieds_survivors", "Viable Plays", false);
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
          return `<tr class="${r.is_played ? "played-row" : ""}">
            <td>${rk}</td>
            <td>${escapeHtml(r.desc)}</td>
            <td>${stPill}</td>
            <td class="num">${fmtScore(r.risk_ev)}</td>
            <td class="num">${fmtScore(r.cvar10)}</td>
            <td class="num">${r.nash_pct.toFixed(1)}%</td>
            <td class="num">${r.qre_pct.toFixed(1)}%</td>
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
        <div class="kpi-strip">
          <div class="kpi-card" title="${escapeHtml(tVal.tooltip)}">
            <div class="kpi-name">${escapeHtml(tVal.label)}</div>
            <div class="kpi-value">${fmtScore(data.nash_value)}</div>
          </div>
          <div class="kpi-card" title="${escapeHtml(tLoss.tooltip)}">
            <div class="kpi-name">${escapeHtml(tLoss.label)}</div>
            <div class="kpi-value">${act.nash_regret.toFixed(isSci ? 4 : 2)}</div>
          </div>
          <div class="kpi-card" title="${escapeHtml(tCvar.tooltip)}">
            <div class="kpi-name">${escapeHtml(tCvar.label)}</div>
            <div class="kpi-value">${fmtScore(act.cvar10)}</div>
          </div>
          <div class="kpi-card" title="${escapeHtml(tSurv.tooltip)}">
            <div class="kpi-name">${escapeHtml(tSurv.label)}</div>
            <div class="kpi-value">${data.ieds.t1_strict} / ${data.ieds.t1_total}</div>
          </div>
        </div>

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
          <div style="margin-top:8px">
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
    } else {
      const renderSide = (title, mons) => {
        const rows = (mons || [])
          .map((m) => {
            const boosts = [];
            if (m.atk_boost) boosts.push(`Atk${m.atk_boost > 0 ? "+" : ""}${m.atk_boost}`);
            if (m.spa_boost) boosts.push(`SpA${m.spa_boost > 0 ? "+" : ""}${m.spa_boost}`);
            if (m.spd_boost) boosts.push(`SpD${m.spd_boost > 0 ? "+" : ""}${m.spd_boost}`);
            const bStr = boosts.length ? ` [${boosts.join(",")}]` : "";
            return `<div class="board-mon ${m.hp_cur <= 0 ? "fainted" : ""}">
              <span class="board-mon-left">
                ${spritePairHtml(m.sprite_url, m.item_sprite_url, m.species, m.item)}
                <span><strong>${m.role === "Active" ? "ACT" : "BNC"}</strong> ${escapeHtml(m.species)}${escapeHtml(bStr)}</span>
              </span>
              <span class="muted-xs">${m.hp_pct}% · ${m.spe} Spe</span>
            </div>`;
          })
          .join("");
        return `<div class="side-card"><div class="side-head">${escapeHtml(title)}</div>${rows}</div>`;
      };

      const valLabel = getTermInfo("nash_value", "Turn Advantage", false).label;
      tabHtml = `
        <div class="subhead">${isEs ? `Estado al inicio del Turno ${data.turn}` : `Board at start of Turn ${data.turn}`}</div>
        <div class="board-columns">
          ${renderSide(rep.trainer_1_name, data.board.trainer_1)}
          ${renderSide(rep.trainer_2_name, data.board.trainer_2)}
        </div>

        <div class="subhead">${escapeHtml(valLabel)} — ${isEs ? "Evolución de la partida" : "Match progression"}</div>
        ${buildEvalChartSvg()}
      `;
    }

    const body = $("coach-panel-body");
    body.innerHTML = heroHtml + tabHtml;
    body.querySelectorAll("circle[data-chart-turn]").forEach((el) => {
      el.addEventListener("click", () => selectTurn(parseInt(el.dataset.chartTurn, 10), true, false));
    });
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

  ["advice", "matrix", "board"].forEach((t) => {
    $(`tab-btn-${t}`).onclick = () => setCoachTab(t);
  });

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

  // Multi-File Drag & Drop + File Input (1 to 3 Showdown Replays: Bo1 or Bo3)
  async function readUploadedFiles(fileList) {
    const arr = Array.from(fileList || []).slice(0, 3);
    arr.sort((a, b) => (a.name || "").localeCompare(b.name || "", undefined, { numeric: true }));
    const items = [];
    for (const f of arr) {
      items.push({ filename: f.name, raw_input: await f.text() });
    }
    if (items.length) {
      await handleBo3ReplayFiles(items, false, null);
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
      await readUploadedFiles(e.dataTransfer.files);
    }
  });

  $("replay-file-input").onchange = async (e) => {
    if (e.target.files && e.target.files.length) {
      await readUploadedFiles(e.target.files);
      e.target.value = "";
    }
  };

  $("btn-change-replay").onclick = () => {
    $("replay-dropzone").style.display = "block";
  };

  $("btn-toggle-raw-replay").onclick = () => {
    const box = $("raw-replay-box");
    box.style.display = box.style.display === "none" ? "block" : "none";
  };

  $("btn-parse-raw-replay").onclick = () => {
    handleReplayInput($("raw-replay-textarea").value, false, null);
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

  async function loadAndRenderAnalytics(teamOverride) {
    const isEs = state.lang === "es";
    const sel = $("analytics-team-select");
    const body = $("analytics-dashboard-body");
    if (!body) return;
    body.innerHTML = `<div class="muted-sm">${isEs ? "Cargando sesiones..." : "Loading session analytics..."}</div>`;

    const reqTeam = teamOverride || (sel && sel.value) || "all";
    const res = await fetch(`/api/telemetry/summary?team=${encodeURIComponent(reqTeam)}`);
    const d = await res.json();
    if (!d.ok) {
      body.innerHTML = `<div class="muted-sm">Error: ${escapeHtml(d.error || "Unknown")}</div>`;
      return;
    }

    if (sel) {
      const teams = d.teams || [];
      sel.innerHTML =
        `<option value="all">${isEs ? "Todos los equipos" : "All teams"}</option>` +
        teams.map((tf) => `<option value="${escapeHtml(tf)}">${escapeHtml(tf)}</option>`).join("");
      sel.value = d.team_folder || "all";
    }

    if (!d.total_matches) {
      body.innerHTML = `<div class="muted-sm" style="padding:14px 0">${
        isEs
          ? "Aún no hay partidas exportadas en esta carpeta. Analiza una partida y pulsa 'Exportar CSV' en el Paso 3."
          : "No exported matches found in this folder yet. Analyze a replay and click 'Export CSV' in Step 3."
      }</div>`;
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

  function openAnalyticsModal() {
    $("analytics-modal").style.display = "flex";
    loadAndRenderAnalytics();
  }

  function closeAnalyticsModal() {
    $("analytics-modal").style.display = "none";
  }

  if ($("btn-open-analytics-modal")) $("btn-open-analytics-modal").onclick = openAnalyticsModal;
  if ($("btn-close-analytics-modal")) $("btn-close-analytics-modal").onclick = closeAnalyticsModal;
  if ($("btn-refresh-analytics")) $("btn-refresh-analytics").onclick = () => loadAndRenderAnalytics();
  if ($("analytics-team-select")) {
    $("analytics-team-select").onchange = (e) => loadAndRenderAnalytics(e.target.value);
  }
  if ($("analytics-modal")) {
    $("analytics-modal").addEventListener("click", (ev) => {
      if (ev.target === $("analytics-modal")) closeAnalyticsModal();
    });
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

  function openPrepToolsView() {
    if (state.activeStep === "prep") {
      setStep(state.prevStepBeforePrep || "setup");
      return;
    }
    populatePrepRosterSelect();
    setStep("prep");
    updatePrepControlsUI();
    if (!state.prep.token && !state.prep.usePaste && $("prep-roster-select") && $("prep-roster-select").value) {
      generatePrepToolPreview();
    }
  }

  if ($("btn-open-prep-view")) $("btn-open-prep-view").onclick = openPrepToolsView;
  if ($("btn-prep-back")) {
    $("btn-prep-back").onclick = () => setStep(state.prevStepBeforePrep || "setup");
  }
  if ($("btn-prep-kind-speed")) {
    $("btn-prep-kind-speed").onclick = () => {
      state.prep.kind = "speed_tiers";
      updatePrepControlsUI();
      if (!state.prep.usePaste || ($("prep-paste-input") && $("prep-paste-input").value.trim())) {
        generatePrepToolPreview();
      }
    };
  }
  if ($("btn-prep-kind-damage")) {
    $("btn-prep-kind-damage").onclick = () => {
      state.prep.kind = "damage_matrix";
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

  // Boot on Step 1
  (async function init() {
    const res = await fetch("/api/state");
    state.app = await res.json();
    const prefix = state.app.device_type === "cuda" ? "CUDA" : "CPU";
    $("hw-badge").textContent = `${prefix}: ${state.app.device}`;
    renderSavedTeamsList("t1");
    renderSavedTeamsList("t2");
    populatePrepRosterSelect();
    applyAllTranslations();
  })();
})();
