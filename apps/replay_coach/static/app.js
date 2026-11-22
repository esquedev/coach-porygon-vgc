(function () {
  "use strict";

  const state = {
    app: null,
    currentTurn: 1,
    turnResults: {},
    activeStream: null,
    selectedRosterId: null,
  };

  const $ = (id) => document.getElementById(id);

  function getSolverConfig() {
    const [mp, k] = $("mode-select").value.split("|");
    return { minPrior: parseFloat(mp), numMc: parseInt(k, 10) };
  }

  function postToShowdown(payload) {
    const frame = $("showdown-iframe");
    if (frame && frame.contentWindow) {
      frame.contentWindow.postMessage(payload, "*");
    }
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function refreshAppState(reloadIframe) {
    const res = await fetch("/api/state");
    state.app = await res.json();
    $("gpu-badge").textContent = `GPU: ${state.app.device}`;

    const rep = state.app.replay;
    if (rep) {
      $("match-title").textContent = `${rep.trainer_1_name} (trainer_1) vs. ${rep.trainer_2_name} (trainer_2) — ${rep.format_name}`;
      const r1 = state.app.active_t1_roster_id || "Sin DB";
      const r2 = state.app.active_t2_roster_id || "Sin DB";
      $("ots-match-indicator").textContent = `OTS DB: ${r1} vs. ${r2}`;

      const povSel = $("pov-select");
      povSel.innerHTML = "";
      [rep.trainer_1_name, rep.trainer_2_name].forEach((name, idx) => {
        const opt = document.createElement("option");
        opt.value = name;
        opt.textContent = `Coachear: ${name}`;
        if (idx === 0) opt.selected = true;
        povSel.appendChild(opt);
      });

      if (reloadIframe) {
        $("showdown-iframe").src = `/api/replay-player?ts=${Date.now()}`;
      }
      renderTimeline();
      renderEvalChart();
      populateRosterModal();
    }
  }

  function renderTimeline() {
    const container = $("turn-pills");
    container.innerHTML = "";
    const rep = state.app && state.app.replay;
    if (!rep) return;

    rep.turn_numbers.forEach((t) => {
      const btn = document.createElement("button");
      btn.className = "turn-pill" + (t === state.currentTurn ? " active" : "");
      const tr = state.turnResults[t];
      let badgeHtml = `<span style="color:#64748b">·</span>`;
      if (tr && tr.commentary) {
        badgeHtml = `<span class="sym ${tr.commentary.badge_class}">${escapeHtml(tr.commentary.symbol)}</span>`;
      }
      btn.innerHTML = `<span>T${t}</span>${badgeHtml}`;
      btn.onclick = () => selectTurn(t, true);
      container.appendChild(btn);
    });
  }

  function renderEvalChart() {
    const svg = $("eval-chart");
    const rep = state.app && state.app.replay;
    if (!rep || !rep.turn_numbers.length) {
      svg.innerHTML = "";
      return;
    }
    const turns = rep.turn_numbers;
    const w = 1000, h = 76, padX = 28, padY = 12;
    const midY = h / 2;

    let html = `<line x1="${padX}" y1="${midY}" x2="${w - padX}" y2="${midY}" stroke="#334155" stroke-dasharray="4 4" stroke-width="1"/>`;
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
      html += `<path d="${d}" fill="none" stroke="#38bdf8" stroke-width="2.2"/>`;
    }

    const colorMap = {
      optimal: "#22c55e",
      good: "#38bdf8",
      inaccuracy: "#f59e0b",
      warn: "#f59e0b",
      mistake: "#ef4444",
      blunder: "#ef4444",
    };

    pts.forEach((p) => {
      const c = colorMap[p.tr.commentary.badge_class] || "#38bdf8";
      const r = p.t === state.currentTurn ? 6 : 4;
      html += `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="${r}" fill="${c}" stroke="#0b1120" stroke-width="1.5" style="cursor:pointer" data-turn="${p.t}"><title>T${p.t}: v*=${p.tr.nash_value.toFixed(3)} (${p.tr.commentary.badge})</title></circle>`;
    });

    svg.innerHTML = html;
    svg.querySelectorAll("circle[data-turn]").forEach((el) => {
      el.addEventListener("click", () => selectTurn(parseInt(el.dataset.turn, 10), true));
    });
  }

  function renderTurnPanel(data) {
    $("coach-panel-title").textContent = `Análisis GPU Tensor Core — Turno ${data.turn}`;
    $("turn-compute-meta").textContent =
      `[${data.matrix_shape[0]}×${data.matrix_shape[1]}] · ${(data.total_timelines / 1000).toFixed(0)}k líneas · ${data.elapsed_s}s${data.from_cache ? " (caché)" : ""}`;

    const act = data.actual_action;
    const com = data.commentary;
    const f = data.field;
    const fieldTags = [];
    if (f.weather) fieldTags.push(`Clima: ${f.weather} (${f.weather_turns}t)`);
    if (f.terrain) fieldTags.push(`Terreno: ${f.terrain} (${f.terrain_turns}t)`);
    if (f.trick_room_turns > 0) fieldTags.push(`Trick Room: ${f.trick_room_turns}t`);
    if (f.t1_tailwind > 0) fieldTags.push(`Tailwind T1: ${f.t1_tailwind}t`);
    if (f.t2_tailwind > 0) fieldTags.push(`Tailwind T2: ${f.t2_tailwind}t`);
    const fieldStr = fieldTags.length ? fieldTags.join(" · ") : "Campo Limpio";

    const renderSide = (title, mons) => {
      const rows = mons
        .map((m) => {
          const boosts = [];
          if (m.atk_boost) boosts.push(`Atk${m.atk_boost > 0 ? "+" : ""}${m.atk_boost}`);
          if (m.spa_boost) boosts.push(`SpA${m.spa_boost > 0 ? "+" : ""}${m.spa_boost}`);
          if (m.spd_boost) boosts.push(`SpD${m.spd_boost > 0 ? "+" : ""}${m.spd_boost}`);
          if (m.protect_prev) boosts.push("ProtPrev");
          const bStr = boosts.length ? ` [${boosts.join(",")}]` : "";
          const roleTag = m.role === "Active" ? "ACT" : "BNC";
          return `<div class="mon-row ${m.hp_cur <= 0 ? "fainted" : ""}">
            <span><strong>${roleTag}</strong> ${escapeHtml(m.species)}${escapeHtml(bStr)}</span>
            <span>${m.hp_cur}/${m.hp_max} (${m.hp_pct}%) · ${m.spe} Spe</span>
          </div>`;
        })
        .join("");
      return `<div class="side-box"><div class="side-title">${escapeHtml(title)}</div>${rows}</div>`;
    };

    const bulletsHtml = com.bullets
      .map(
        (b) => `<li class="bullet-item ${b.tone}">
          <span class="bullet-tag">[${escapeHtml(b.tag)}]</span>${escapeHtml(b.text)}
        </li>`
      )
      .join("");

    // Ensure played action appears in the comparison table
    const tableRows = [...data.top_actions];
    if (!tableRows.some((r) => r.is_played)) {
      tableRows.push(act);
    }

    const actionsHtml = tableRows
      .map((r, idx) => {
        const iedsBadge = r.survived_strict_ieds
          ? `<span class="badge surv">SURV</span>`
          : `<span class="badge dom">DOM R${r.strict_dominated_by ? r.strict_dominated_by.round : "?"}</span>`;
        const rkLabel = r.is_played && idx >= data.top_actions.length ? `#${act.rank}` : `#${idx + 1}`;
        const playedTag = r.is_played ? ` <span class="badge good">JUGADA</span>` : "";
        return `<tr class="${r.is_played ? "played-row" : ""}">
          <td>${rkLabel}</td>
          <td>${escapeHtml(r.desc)}${playedTag}</td>
          <td>${iedsBadge}</td>
          <td class="num">${r.risk_ev >= 0 ? "+" : ""}${r.risk_ev.toFixed(3)}</td>
          <td class="num">${r.cvar10 >= 0 ? "+" : ""}${r.cvar10.toFixed(3)}</td>
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
          <td class="num">+${e.worst_margin.toFixed(3)} / +${e.mean_margin.toFixed(3)}</td>
        </tr>`
      )
      .join("");

    const rep = state.app.replay;
    $("coach-panel-body").innerHTML = `
      <div class="verdict-box ${com.badge_class}">
        <div class="verdict-top">
          <span class="badge ${com.badge_class}">${escapeHtml(com.symbol)} ${escapeHtml(com.badge)}</span>
          <span class="status-msg">${escapeHtml(fieldStr)}</span>
        </div>
        <div style="font-weight:600;line-height:1.4">${escapeHtml(com.headline)}</div>
      </div>

      <div class="kpi-grid">
        <div class="kpi">
          <div class="kpi-label">Equilibrio Nash v*</div>
          <div class="kpi-val">${data.nash_value >= 0 ? "+" : ""}${data.nash_value.toFixed(3)}</div>
        </div>
        <div class="kpi">
          <div class="kpi-label">Nash Regret</div>
          <div class="kpi-val" style="color:${act.nash_regret > 0.2 ? "#f87171" : "#4ade80"}">${act.nash_regret.toFixed(3)}</div>
        </div>
        <div class="kpi">
          <div class="kpi-label">Piso CVaR_10</div>
          <div class="kpi-val">${act.cvar10 >= 0 ? "+" : ""}${act.cvar10.toFixed(3)}</div>
        </div>
        <div class="kpi">
          <div class="kpi-label">IEDS (Estricto)</div>
          <div class="kpi-val">${data.ieds.t1_total} &rarr; ${data.ieds.t1_strict}</div>
        </div>
      </div>

      <div class="played-card">
        <div class="played-line">Jugada de ${escapeHtml(rep.trainer_1_name)}: ${escapeHtml(act.desc)}</div>
        <div class="opp-line">Respuesta de ${escapeHtml(rep.trainer_2_name)}: ${escapeHtml(act.opp_actual_desc)} · Rank #${act.rank}/${act.total_actions} · Nash ${act.nash_pct.toFixed(1)}% · QRE ${act.qre_pct.toFixed(1)}%</div>
      </div>

      <div class="section-title">Comentario Determinista (0% IA — Testigos GPU)</div>
      <ul class="bullet-list">${bulletsHtml}</ul>

      <div class="section-title">Estado del Tablero al Inicio del Turno ${data.turn}</div>
      <div class="board-strip">
        ${renderSide(`${rep.trainer_1_name} (trainer_1)`, data.board.trainer_1)}
        ${renderSide(`${rep.trainer_2_name} (trainer_2)`, data.board.trainer_2)}
      </div>

      <div class="section-title">Ranking Post-IEDS (Equilibrio de Nash &amp; QRE Logit)</div>
      <table class="data-table">
        <thead>
          <tr>
            <th>Rk</th><th>Acción Conjunta (trainer_1)</th><th>IEDS</th>
            <th class="num">RiskEV</th><th class="num">CVaR10</th>
            <th class="num">Nash%</th><th class="num">QRE%</th>
          </tr>
        </thead>
        <tbody>${actionsHtml}</tbody>
      </table>

      <details class="ieds-box">
        <summary>Inspector de Eliminación IEDS (${data.ieds.t1_strict_elim} estrategias estrictamente dominadas en ${data.ieds.strict_rounds} ronda(s))</summary>
        <div style="margin-top:8px">
          ${
            elimRows
              ? `<table class="data-table">
                  <thead><tr><th>Ronda</th><th>Estrategia Eliminada</th><th>Dominada Por</th><th class="num">Min / Media</th></tr></thead>
                  <tbody>${elimRows}</tbody>
                </table>`
              : `<div class="status-msg">Ninguna estrategia fue estrictamente dominada en este turno.</div>`
          }
        </div>
      </details>
    `;
  }

  async function selectTurn(turnNum, syncShowdown, forceRecompute) {
    const rep = state.app && state.app.replay;
    if (!rep) return;
    const clamped = Math.max(1, Math.min(rep.num_turns, turnNum));
    state.currentTurn = clamped;
    $("current-turn-label").textContent = `Turno ${clamped} / ${rep.num_turns}`;
    if (syncShowdown) {
      postToShowdown({ type: "SEEK_TURN", turn: clamped });
    }
    renderTimeline();
    renderEvalChart();

    if (!forceRecompute && state.turnResults[clamped]) {
      renderTurnPanel(state.turnResults[clamped]);
      return;
    }

    $("coach-panel-title").textContent = `Calculando Turno ${clamped} en GPU...`;
    $("coach-panel-body").innerHTML = `<div class="status-msg">Ejecutando VgcTensorStateMachine + IEDS + HiGHS LP Nash en ${escapeHtml(state.app.device)}...</div>`;

    const { minPrior, numMc } = getSolverConfig();
    const url = `/api/analyze/turn?turn=${clamped}&min_prior=${minPrior}&num_mc=${numMc}&force=${forceRecompute ? 1 : 0}`;
    const res = await fetch(url);
    const data = await res.json();
    if (data.error) {
      $("coach-panel-body").innerHTML = `<div style="color:#f87171">Error: ${escapeHtml(data.error)}</div>`;
      return;
    }
    state.turnResults[clamped] = data;
    if (state.currentTurn === clamped) {
      renderTurnPanel(data);
    }
    renderTimeline();
    renderEvalChart();
  }

  function analyzeAllTurnsStream(forceRecompute) {
    if (state.activeStream) {
      state.activeStream.close();
      state.activeStream = null;
    }
    const { minPrior, numMc } = getSolverConfig();
    $("stream-status").textContent = "Analizando turnos en GPU (streaming en vivo)...";
    $("btn-analyze-all").disabled = true;

    const es = new EventSource(
      `/api/analyze/stream?min_prior=${minPrior}&num_mc=${numMc}&force=${forceRecompute ? 1 : 0}`
    );
    state.activeStream = es;

    es.addEventListener("turn", (ev) => {
      const data = JSON.parse(ev.data);
      state.turnResults[data.turn] = data;
      $("stream-status").textContent = `Turno ${data.turn}/${state.app.replay.num_turns} completado (${data.elapsed_s}s)`;
      renderTimeline();
      renderEvalChart();
      if (data.turn === state.currentTurn) {
        renderTurnPanel(data);
      }
    });

    es.addEventListener("done", () => {
      $("stream-status").textContent = `Partida completa analizada (${state.app.replay.num_turns} turnos)`;
      $("btn-analyze-all").disabled = false;
      es.close();
      state.activeStream = null;
    });

    es.onerror = () => {
      $("stream-status").textContent = "Stream finalizado.";
      $("btn-analyze-all").disabled = false;
      es.close();
      state.activeStream = null;
    };
  }

  // OTS Roster DB Modal Logic
  function populateRosterModal() {
    const rosters = (state.app && state.app.rosters) || [];
    const listEl = $("roster-list");
    listEl.innerHTML = "";

    const fillSel = (selId, activeId) => {
      const sel = $(selId);
      sel.innerHTML = `<option value="">(Auto-match / Replay OTS)</option>`;
      rosters.forEach((r) => {
        const opt = document.createElement("option");
        opt.value = r.roster_id;
        opt.textContent = r.display_name;
        if (r.roster_id === activeId) opt.selected = true;
        sel.appendChild(opt);
      });
    };
    fillSel("assign-t1", state.app.active_t1_roster_id);
    fillSel("assign-t2", state.app.active_t2_roster_id);

    rosters.forEach((r) => {
      const div = document.createElement("div");
      div.className = "roster-item" + (r.roster_id === state.selectedRosterId ? " selected" : "");
      div.innerHTML = `<div style="font-weight:600">${escapeHtml(r.display_name)}</div>
        <div class="status-msg">${escapeHtml(r.species.join(" / "))}</div>`;
      div.onclick = () => {
        state.selectedRosterId = r.roster_id;
        $("ed-roster-id").value = r.roster_id;
        $("ed-display-name").value = r.display_name;
        $("ed-trainer-hint").value = r.trainer_hint;
        $("ed-paste").value = r.paste_text;
        $("ots-editor-status").textContent = "";
        populateRosterModal();
      };
      listEl.appendChild(div);
    });
  }

  // Event Listeners
  window.addEventListener("message", (ev) => {
    const msg = ev.data || {};
    if (msg.type === "TURN_CHANGED" && typeof msg.turn === "number" && msg.turn >= 1) {
      if (msg.turn !== state.currentTurn) {
        selectTurn(msg.turn, false, false);
      }
    }
  });

  $("btn-prev-turn").onclick = () => selectTurn(state.currentTurn - 1, true, false);
  $("btn-next-turn").onclick = () => selectTurn(state.currentTurn + 1, true, false);
  $("btn-play-pause").onclick = () => postToShowdown({ type: "TOGGLE_PLAY" });
  $("btn-flip-pov").onclick = () => postToShowdown({ type: "SWITCH_VIEWPOINT" });
  $("btn-recompute-turn").onclick = () => selectTurn(state.currentTurn, false, true);
  $("btn-analyze-all").onclick = () => analyzeAllTurnsStream(false);

  $("pov-select").onchange = async (e) => {
    state.turnResults = {};
    await fetch("/api/replay/load", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pov_trainer: e.target.value }),
    });
    await refreshAppState(true);
    selectTurn(1, false, false);
  };

  $("replay-file-input").onchange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const text = await file.text();
    state.turnResults = {};
    await fetch("/api/replay/load", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ raw_input: text, pov_trainer: "treces_gc" }),
    });
    await refreshAppState(true);
    selectTurn(1, false, false);
  };

  $("btn-open-ots").onclick = () => {
    populateRosterModal();
    $("ots-modal").classList.add("open");
  };
  $("btn-close-ots").onclick = () => $("ots-modal").classList.remove("open");

  $("btn-new-roster").onclick = () => {
    state.selectedRosterId = null;
    $("ed-roster-id").value = "";
    $("ed-display-name").value = "";
    $("ed-trainer-hint").value = "";
    $("ed-paste").value = "";
    $("ots-editor-status").textContent = "Listo para pegar nuevo OTS + EVs/SPs.";
    populateRosterModal();
  };

  $("btn-validate-paste").onclick = async () => {
    const res = await fetch("/api/rosters/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ paste_text: $("ed-paste").value }),
    });
    const d = await res.json();
    if (d.error) {
      $("ots-editor-status").textContent = `Error: ${d.error}`;
    } else if (d.valid) {
      $("ots-editor-status").textContent = `OK: ${d.count} Pokémon válidos bajo Reg M-C 66-SP.`;
    } else {
      $("ots-editor-status").textContent = `Avisos: ${(d.warnings || []).join("; ")}`;
    }
  };

  $("btn-save-roster").onclick = async () => {
    const res = await fetch("/api/rosters", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        roster_id: $("ed-roster-id").value,
        display_name: $("ed-display-name").value,
        trainer_hint: $("ed-trainer-hint").value,
        paste_text: $("ed-paste").value,
      }),
    });
    const d = await res.json();
    if (d.error) {
      $("ots-editor-status").textContent = `Error: ${d.error}`;
    } else {
      $("ots-editor-status").textContent = "Guardado en DuckDB (caché refrescada).";
      state.turnResults = {};
      await refreshAppState(false);
    }
  };

  $("btn-apply-rosters").onclick = async () => {
    state.turnResults = {};
    await fetch("/api/replay/load", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        t1_roster_id: $("assign-t1").value || null,
        t2_roster_id: $("assign-t2").value || null,
      }),
    });
    $("ots-modal").classList.remove("open");
    await refreshAppState(false);
    selectTurn(state.currentTurn, false, true);
  };

  // Boot
  (async function init() {
    await refreshAppState(false);
    if (state.app && state.app.replay) {
      selectTurn(1, false, false);
    }
  })();
})();
