"use strict";

(() => {
    const REFRESH_INTERVAL = 10000;
    const numberFormat = new Intl.NumberFormat("es-CL");
    const timeFormat = new Intl.DateTimeFormat("es-CL", {
        day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit"
    });
    let loading = false;
    let hasData = false;
    let lastSuccessfulUpdate = null;
    let refreshTimer = null;

    const byId = (id) => document.getElementById(id);
    const count = (value) => Number.isFinite(Number(value)) ? Math.max(0, Math.trunc(Number(value))) : 0;
    const formatCount = (value) => numberFormat.format(count(value));
    const array = (value) => Array.isArray(value) ? value : [];

    function requireCounts(object, keys) {
        if (!object || keys.some((key) => typeof object[key] !== "number" || !Number.isInteger(object[key]) || object[key] < 0)) {
            throw new Error("invalid_counts");
        }
    }

    function validateReadyData(data) {
        requireCounts(data.summary, [
            "assigned", "not_started", "started", "screening_pending", "screened_out",
            "screening_passed", "baseline_pending", "eligible_baseline_complete",
            "eligible_in_progress", "eligible_completed", "eligible_final_screen_completion",
            "eligible_finished_incomplete", "eligible_navigation_incomplete", "eligible_terminated_incomplete", "all_main_tasks_submitted",
            "main_tasks_submitted", "main_tasks_with_selection", "main_tasks_no_selection",
            "deadline_expiries", "participants_with_timeouts"
        ]);
        requireCounts(data, ["main_task_count"]);
        requireCounts(data.completion_rule, ["minimum_valid_main_choices", "main_task_count", "maximum_missing_main_choices"]);
        if (data.completion_rule.main_task_count !== data.main_task_count ||
            data.completion_rule.minimum_valid_main_choices + data.completion_rule.maximum_missing_main_choices !== data.main_task_count) throw new Error("invalid_completion_rule");
        if (!Array.isArray(data.quota_dimensions) || !Array.isArray(data.treatments) || !Array.isArray(data.exclusions)) throw new Error("invalid_data");
        data.quota_dimensions.forEach((dimension) => {
            requireCounts(dimension, ["completed_total", "in_progress_total", "missing_completed", "missing_in_progress"]);
            if (!Array.isArray(dimension.rows)) throw new Error("invalid_data");
            dimension.rows.forEach((row) => requireCounts(row, ["completed", "in_progress"]));
        });
        data.treatments.forEach((row) => requireCounts(row, ["eligible_baseline_complete", "in_progress", "completed", "finished_incomplete", "navigation_incomplete", "terminated_incomplete"]));
        data.exclusions.forEach((row) => requireCounts(row, ["count"]));
        if (!data.age_gender || !Array.isArray(data.age_gender.columns) || !Array.isArray(data.age_gender.rows)) throw new Error("invalid_data");
        data.age_gender.rows.forEach((row) => {
            if (!Array.isArray(row.cells)) throw new Error("invalid_data");
            row.cells.forEach((cell) => requireCounts(cell, ["completed", "in_progress"]));
        });
        if (Number.isNaN(new Date(data.updated_at).getTime())) throw new Error("invalid_date");
    }

    function element(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined) node.textContent = String(text);
        return node;
    }

    function setSync(state, text) {
        byId("sync-status").dataset.state = state;
        byId("sync-label").textContent = text;
    }

    function setMode(mode) {
        const badge = byId("mode-badge");
        badge.className = "mode-badge";
        if (mode === "official") {
            badge.classList.add("mode-official");
            badge.textContent = "Recolección oficial";
        } else if (mode === "testing") {
            badge.classList.add("mode-testing");
            badge.textContent = "Pruebas · datos de ensayo";
        } else {
            badge.classList.add("mode-pending");
            badge.textContent = "Estado sin confirmar";
        }
    }

    function makeProgress(value, maximum, label) {
        const progress = element("progress");
        progress.max = Math.max(1, count(maximum));
        progress.value = Math.min(count(value), progress.max);
        progress.setAttribute("aria-label", label);
        progress.textContent = `${formatCount(value)} de ${formatCount(maximum)}`;
        return progress;
    }

    function tableShell(headers, className, label) {
        const wrapper = element("div", "table-scroll");
        wrapper.tabIndex = 0;
        wrapper.setAttribute("role", "region");
        wrapper.setAttribute("aria-label", label);
        const table = element("table", className);
        const thead = element("thead");
        const tr = element("tr");
        headers.forEach((header, index) => {
            const th = element("th", index ? "numeric" : "", header);
            th.scope = "col";
            tr.append(th);
        });
        thead.append(tr);
        const tbody = element("tbody");
        table.append(thead, tbody);
        wrapper.append(table);
        return { wrapper, tbody };
    }

    function renderDimensions(dimensions) {
        const container = byId("dimensions-grid");
        container.replaceChildren();
        array(dimensions).forEach((dimension) => {
            const card = element("section", "panel dimension-panel");
            const heading = element("div", "panel-heading");
            const title = element("h3", "dimension-title", dimension.label || "Composición");
            const totals = element("p", "panel-total");
            totals.append(element("strong", "", formatCount(dimension.completed_total)), document.createTextNode(count(dimension.completed_total) === 1 ? " encuesta completa" : " encuestas completas"));
            heading.append(title, totals);
            card.append(heading);
            const rows = array(dimension.rows);
            if (!rows.length) {
                card.append(element("p", "panel-empty", "Todavía no hay categorías disponibles."));
            } else {
                const { wrapper, tbody } = tableShell(["Categoría", "Completas", "En curso"], "dimension-table", dimension.label || "Composición");
                rows.forEach((row) => {
                    const tr = element("tr");
                    const label = element("th", "", row.label || "Sin dato");
                    label.scope = "row";
                    const completed = element("td", "numeric count-cell completed-number");
                    completed.append(element("strong", "", formatCount(row.completed)));
                    const hasTarget = row.target !== null && row.target !== undefined;
                    const maximum = hasTarget ? row.target : dimension.completed_total;
                    completed.append(makeProgress(row.completed, maximum, hasTarget ? `${row.label}: ${formatCount(row.completed)} de una meta de ${formatCount(row.target)}` : `${row.label}: ${formatCount(row.completed)} encuestas completas`));
                    if (hasTarget) {
                        const percentage = Math.round(Math.min(100, Math.max(0, Number(row.progress_percent) || 0)));
                        completed.append(element("span", row.is_full ? "target-note target-full" : "target-note", row.is_full ? `Meta ${formatCount(row.target)} · cubierta` : `Meta ${formatCount(row.target)} · ${percentage}%`));
                    }
                    const inProgress = element("td", "numeric in-progress-number", formatCount(row.in_progress));
                    tr.append(label, completed, inProgress);
                    tbody.append(tr);
                });
                card.append(wrapper);
            }
            const footnotes = [];
            if (count(dimension.missing_completed) || count(dimension.missing_in_progress)) {
                footnotes.push(`Sin dato: ${formatCount(dimension.missing_completed)} encuestas completas y ${formatCount(dimension.missing_in_progress)} en curso.`);
            }
            if (!rows.some((row) => row.target !== null && row.target !== undefined)) {
                footnotes.push("Las barras muestran la distribución de las encuestas completas, no metas de reclutamiento.");
            }
            if (footnotes.length) card.append(element("p", "panel-footnote", footnotes.join(" ")));
            container.append(card);
        });
        if (!container.children.length) container.append(element("p", "section-description", "La composición se mostrará cuando haya datos de caracterización disponibles."));
    }

    function renderAgeGender(data) {
        const container = byId("age-gender-content");
        const columns = array(data && data.columns);
        const rows = array(data && data.rows);
        container.replaceChildren();
        if (!rows.length || !columns.length) {
            container.append(element("p", "panel-empty", "Todavía no hay datos disponibles para este cruce."));
            return;
        }
        const { wrapper, tbody } = tableShell(["Edad", ...columns.map((column) => column.label)], "matrix-table", "Cruce de edad y género: encuestas completas y participación en curso");
        rows.forEach((row) => {
            const tr = element("tr");
            const label = element("th", "", row.label || "Sin dato");
            label.scope = "row";
            tr.append(label);
            columns.forEach((column) => {
                const cell = array(row.cells).find((item) => item.gender_key === column.key);
                const td = element("td");
                if (!cell) {
                    td.append(element("span", "", "—"));
                } else {
                    const completed = element("strong", "completed-number", formatCount(cell.completed));
                    completed.setAttribute("aria-label", `${formatCount(cell.completed)} encuestas completas`);
                    td.append(completed, element("span", "matrix-in-progress", `${formatCount(cell.in_progress)} en curso`));
                    if (cell.target !== null && cell.target !== undefined) {
                        td.append(makeProgress(cell.completed, cell.target, `${row.label}, ${column.label}: ${formatCount(cell.completed)} de una meta de ${formatCount(cell.target)}`));
                        td.append(element("span", cell.is_full ? "target-note target-full" : "target-note", cell.is_full ? `Meta ${formatCount(cell.target)} · cubierta` : `Meta ${formatCount(cell.target)} · faltan ${formatCount(cell.remaining)}`));
                    }
                }
                tr.append(td);
            });
            tbody.append(tr);
        });
        container.append(wrapper);
    }

    function renderTreatments(treatments) {
        const container = byId("treatment-content");
        container.replaceChildren();
        const rows = array(treatments);
        if (!rows.length) {
            container.append(element("p", "panel-empty", "Todavía no hay asignaciones de participantes elegibles."));
            return;
        }
        const { wrapper, tbody } = tableShell(["Grupo", "Caracterización completa", "En curso", "Completas", "Finalizadas insuficientes", "Incompletas por navegación", "Terminadas antes de finalizar"], "treatment-table", "Avance de participantes elegibles por grupo experimental");
        rows.forEach((row) => {
            const tr = element("tr");
            const label = element("th", "", row.label || "Grupo");
            label.scope = "row";
            tr.append(label, element("td", "numeric", formatCount(row.eligible_baseline_complete)), element("td", "numeric in-progress-number", formatCount(row.in_progress)), element("td", "numeric completed-number", formatCount(row.completed)), element("td", "numeric", formatCount(row.finished_incomplete)), element("td", "numeric", formatCount(row.navigation_incomplete)), element("td", "numeric", formatCount(row.terminated_incomplete)));
            tbody.append(tr);
        });
        container.append(wrapper);
    }

    function renderTaskSummary(summary, taskCount) {
        byId("task-count-note").textContent = `Cada participante realiza ${formatCount(taskCount)} tareas principales. Los vencimientos de plazo se registran por separado.`;
        const container = byId("task-summary");
        container.replaceChildren();
        [
            ["Tareas enviadas", "main_tasks_submitted"],
            ["Tareas con selección registrada", "main_tasks_with_selection"],
            ["Tareas sin selección registrada", "main_tasks_no_selection"],
            ["Vencimientos del plazo", "deadline_expiries"],
            ["Participantes con un vencimiento sin selección", "participants_with_timeouts"],
            ["Participantes con todas las tareas enviadas", "all_main_tasks_submitted"]
        ].forEach(([label, key]) => {
            const row = element("div");
            row.append(element("dt", "", label), element("dd", "", formatCount(summary[key])));
            container.append(row);
        });
    }

    function renderScreening(summary, exclusions) {
        const status = byId("screening-status");
        status.replaceChildren();
        [
            ["Revisión inicial pendiente", "screening_pending"],
            ["Cumplen los requisitos iniciales", "screening_passed"],
            ["Caracterización pendiente", "baseline_pending"]
        ].forEach(([label, key]) => {
            const item = element("p", "", label);
            item.append(element("strong", "", formatCount(summary[key])));
            status.append(item);
        });
        const container = byId("exclusion-content");
        container.replaceChildren();
        const rows = array(exclusions);
        if (!rows.length) {
            container.append(element("p", "panel-empty", "No hay motivos de exclusión registrados."));
            return;
        }
        const list = element("ul", "exclusion-list");
        rows.forEach((row) => {
            const item = element("li");
            item.append(element("span", "", row.label || "Otro motivo"), element("strong", "", formatCount(row.count)));
            list.append(item);
        });
        container.append(list);
    }

    function renderReady(data) {
        validateReadyData(data);
        const summary = data.summary;
        [
            ["count-started", "started"], ["count-screened-out", "screened_out"],
            ["count-in-progress", "eligible_in_progress"], ["count-completed", "eligible_completed"],
            ["count-finished-incomplete", "eligible_finished_incomplete"],
            ["count-navigation-incomplete", "eligible_navigation_incomplete"],
            ["count-terminated-incomplete", "eligible_terminated_incomplete"],
            ["count-final-screen", "eligible_final_screen_completion"],
            ["count-assigned", "assigned"], ["count-not-started", "not_started"],
            ["count-baseline", "eligible_baseline_complete"]
        ].forEach(([id, key]) => { byId(id).textContent = formatCount(summary[key]); });
        renderDimensions(data.quota_dimensions);
        renderAgeGender(data.age_gender);
        renderTreatments(data.treatments);
        renderTaskSummary(summary, data.main_task_count);
        renderScreening(summary, data.exclusions);
        const rule = data.completion_rule;
        byId("completion-rule-note").textContent = `Completa significa haber llegado a la página final, enviado las ${formatCount(rule.main_task_count)} tareas principales, registrado al menos ${formatCount(rule.minimum_valid_main_choices)} decisiones válidas y no tener recargas o regresos registrados desde el inicio de la práctica. Se permiten hasta ${formatCount(rule.maximum_missing_main_choices)} tareas sin selección. Las preguntas que no correspondía responder no se consideran faltantes.`;
        byId("quota-message").textContent = data.targets_configured
            ? "Las metas configuradas se comparan solo con las encuestas completas elegibles. El panel informa el avance y no cierra cuotas automáticamente."
            : "Metas no configuradas; el panel no cierra cuotas automáticamente.";
        const date = new Date(data.updated_at);
        lastSuccessfulUpdate = date;
        byId("last-updated").dateTime = date.toISOString();
        byId("last-updated").textContent = timeFormat.format(date);
        byId("dashboard-data").hidden = false;
        byId("dashboard-data").dataset.state = "fresh";
        byId("dashboard-data").setAttribute("aria-busy", "false");
        byId("stale-notice").hidden = true;
        byId("empty-state").hidden = true;
        hasData = true;
        setSync("fresh", `Datos actualizados a las ${date.toLocaleTimeString("es-CL")}`);
    }

    function renderNotReady(data) {
        const states = {
            no_active_session: ["Aún no hay una sesión activa", data.mode === "official" ? "Todavía no hay una sesión de recolección oficial disponible para monitorear." : "Todavía no hay una sesión de pruebas disponible para monitorear."],
            mode_mismatch: ["La sesión activa corresponde a otro modo", "La sesión disponible no corresponde al modo de seguimiento configurado. Las cifras se mostrarán cuando ambos coincidan."],
            configuration_error: ["El panel necesita una configuración", "La persona responsable del estudio debe revisar la configuración de la sesión antes de mostrar sus cifras."]
        };
        const [title, description] = states[data.status] || ["Datos no disponibles", "El panel no pudo confirmar el estado del estudio."];
        byId("empty-title").textContent = title;
        byId("empty-message").textContent = description;
        byId("empty-state").hidden = false;
        byId("dashboard-data").hidden = true;
        byId("dashboard-data").setAttribute("aria-busy", "false");
        byId("last-updated").textContent = "sin datos de la sesión actual";
        byId("last-updated").removeAttribute("datetime");
        hasData = false;
        lastSuccessfulUpdate = null;
        setSync("pending", "Esperando una sesión compatible");
    }

    function renderError() {
        byId("error-banner").hidden = false;
        byId("error-message").textContent = hasData
            ? "Las cifras anteriores quedan deshabilitadas hasta recuperar la conexión. El panel volverá a intentarlo automáticamente."
            : "No se muestran cifras hasta obtener datos del servidor. Compruebe su conexión o vuelva a actualizar.";
        if (hasData) {
            byId("dashboard-data").dataset.state = "stale";
            byId("stale-notice").hidden = false;
            byId("dashboard-data").setAttribute("aria-busy", "false");
        } else {
            byId("dashboard-data").hidden = true;
            byId("empty-state").hidden = false;
            byId("empty-title").textContent = "Esperando datos del servidor";
            byId("empty-message").textContent = "El panel no puede confirmar las cifras actuales. No se han sustituido por ceros.";
        }
        const previous = lastSuccessfulUpdate ? ` Última lectura: ${timeFormat.format(lastSuccessfulUpdate)}.` : "";
        setSync("error", `Sin datos actuales.${previous}`);
    }

    async function refresh() {
        if (loading) return;
        loading = true;
        byId("refresh-button").disabled = true;
        byId("refresh-button").textContent = "Actualizando…";
        byId("dashboard-data").setAttribute("aria-busy", "true");
        setSync("loading", hasData ? "Actualizando las cifras…" : "Consultando el estado del estudio…");
        const controller = new AbortController();
        const timeout = window.setTimeout(() => controller.abort(), 15000);
        try {
            const response = await fetch("/monitor/data", {
                method: "GET", credentials: "same-origin", cache: "no-store",
                headers: { "Accept": "application/json" }, signal: controller.signal
            });
            if (!response.ok) throw new Error("request_failed");
            const data = await response.json();
            if (!data || typeof data !== "object") throw new Error("invalid_data");
            setMode(data.mode);
            if (data.status === "ready") renderReady(data);
            else if (["no_active_session", "mode_mismatch", "configuration_error"].includes(data.status)) renderNotReady(data);
            else throw new Error("invalid_status");
            byId("error-banner").hidden = true;
        } catch (_error) {
            renderError();
        } finally {
            window.clearTimeout(timeout);
            loading = false;
            byId("refresh-button").disabled = false;
            byId("refresh-button").textContent = "Actualizar ahora";
        }
    }

    function scheduleRefresh() {
        window.clearInterval(refreshTimer);
        refreshTimer = null;
        if (!document.hidden) refreshTimer = window.setInterval(refresh, REFRESH_INTERVAL);
    }

    byId("refresh-button").addEventListener("click", refresh);
    document.addEventListener("visibilitychange", () => {
        scheduleRefresh();
        if (!document.hidden) refresh();
    });
    scheduleRefresh();
    refresh();
})();
