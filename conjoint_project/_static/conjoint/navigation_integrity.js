/* Navigation evidence only: never disable, replace, or trap browser controls. */
(function () {
    'use strict';

    const config = window.js_vars && window.js_vars.study_navigation;
    if (!config || !config.participant_code) return;

    const stateKey = 'colombia-navigation:' + config.participant_code;
    let memoryState = { pending: [], complete: false };
    let lastHistoryAt = -Infinity;
    let postEvidenceInput = null;
    let frozen = false;
    let redirectedToTermination = false;
    let fallbackInFlight = false;
    let firstPendingAt = null;

    function readState() {
        try {
            const saved = sessionStorage.getItem(stateKey);
            if (saved) {
                const parsed = JSON.parse(saved);
                if (parsed && Array.isArray(parsed.pending)) memoryState = parsed;
            }
        } catch (error) {
            // Private-browser/storage restrictions are not a navigation violation.
        }
        return memoryState;
    }

    function writeState(state) {
        memoryState = state;
        try { sessionStorage.setItem(stateKey, JSON.stringify(state)); }
        catch (error) { /* Keep evidence in memory and retry the live connection. */ }
    }

    function mirrorPostEvidence(pending) {
        const form = document.getElementById('form');
        if (!form || typeof form.appendChild !== 'function' || typeof document.createElement !== 'function') return;
        if (!postEvidenceInput) {
            postEvidenceInput = document.createElement('input');
            postEvidenceInput.type = 'hidden';
            postEvidenceInput.name = '_study_navigation_events';
            form.appendChild(postEvidenceInput);
        }
        postEvidenceInput.value = JSON.stringify(pending.slice(0, 20));
    }

    function freezeStudy() {
        if (frozen) return;
        frozen = true;
        // The Task listener first snapshots actual telemetry and stops its clock.
        // Nothing here submits a candidate choice or fabricates a timed response.
        window.dispatchEvent(new Event('study-navigation-freeze'));
        if (typeof document.querySelectorAll === 'function') {
            document.querySelectorAll('input:not([type="hidden"]), select, textarea, button').forEach(function(control) {
                control.disabled = true;
            });
            document.querySelectorAll('a[href]').forEach(function(link) {
                link.removeAttribute('href');
                link.setAttribute('aria-disabled', 'true');
            });
        }
        const summary = document.getElementById('study-final-content');
        if (summary && summary !== document.getElementById('form')) summary.hidden = true;
        if (document.body && typeof document.createElement === 'function') {
            const notice = document.createElement('div');
            notice.id = 'study-navigation-stop';
            notice.setAttribute('role', 'status');
            notice.style.cssText = 'max-width:850px;margin:24px auto;padding:20px;border:1px solid #ddd;border-radius:10px;background:#f8f9fa;';
            notice.textContent = 'Su participación ha finalizado. Estamos registrando el cierre del estudio. Espere mientras se confirma el registro.';
            document.body.appendChild(notice);
        }
    }

    function replaceWithTermination(url) {
        if (redirectedToTermination || !url) return;
        redirectedToTermination = true;
        window.location.replace(url);
    }

    function fallbackTerminationPost(pending) {
        // A disconnected live socket must not permit continued participation.
        // This POST contains evidence only, never the unsubmitted task response.
        if (!frozen || !pending.length || fallbackInFlight || typeof window.fetch !== 'function') return;
        if (firstPendingAt === null || Date.now() - firstPendingAt < 1500) return;
        fallbackInFlight = true;
        const postData = { _study_navigation_events: JSON.stringify(pending.slice(0, 20)) };
        const partial = readState().partial_task;
        if (partial) postData._study_navigation_task = JSON.stringify(partial);
        window.fetch(window.location.href, {
            method: 'POST', credentials: 'same-origin', cache: 'no-store', keepalive: true,
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: new URLSearchParams(postData).toString()
        }).then(function(response) {
            if (!response.ok) return '';
            return response.text();
        }).then(function(html) {
            if (html && html.includes('id="study-terminated-screen"')) replaceWithTermination(window.location.href);
        }).catch(function() {
            // Stay frozen and retry after reconnection, without losing evidence.
        }).finally(function() { fallbackInFlight = false; });
    }

    function flush() {
        const state = readState();
        const pending = state.pending;
        // A previously acknowledged closure also applies to a cached document
        // restored with Back/Forward after the terminal page has been shown.
        if (state.terminated || config.study_terminated || config.terminated) {
            freezeStudy();
            replaceWithTermination(window.location.href);
            return;
        }
        // The normal form POST carries unacknowledged evidence as well. This
        // protects a final submission even if its live socket has not recovered.
        mirrorPostEvidence(pending);
        if (!pending.length) return;
        if (firstPendingAt === null) firstPendingAt = Date.now();
        freezeStudy();
        if (typeof window.liveSend === 'function') {
            try { window.liveSend({ navigation_events: pending.slice(0, 20), navigation_task: readState().partial_task || null }); }
            catch (error) { /* Retry after reconnection, without inventing a violation. */ }
        }
        fallbackTerminationPost(pending);
    }

    function recordNavigation(type) {
        const state = readState();
        if (frozen || !config.enabled || config.final_screen || state.complete || state.terminated) return;
        if (type === 'history') {
            // The same back/forward action can fire both pageshow and popstate.
            if (performance.now() - lastHistoryAt < 1000) return;
            lastHistoryAt = performance.now();
        }
        const id = (window.crypto && typeof window.crypto.randomUUID === 'function')
            ? window.crypto.randomUUID()
            : Date.now().toString(36) + '-' + Math.random().toString(36).slice(2);
        state.pending.push({ id: id, type: type, page_index: config.page_index });
        writeState(state);
        freezeStudy();
        flush();
    }

    const previousLiveRecv = window.liveRecv;
    window.liveRecv = function (message) {
        if (message && Array.isArray(message.navigation_ack)) {
            const state = readState();
            const acknowledged = new Set(message.navigation_ack);
            state.pending = state.pending.filter(function (event) {
                return !acknowledged.has(event.id);
            });
            writeState(state);
            mirrorPostEvidence(state.pending);
        }
        if (message && message.study_terminated) {
            const state = readState();
            state.terminated = true;
            state.complete = false;
            writeState(state);
            freezeStudy();
            replaceWithTermination(message.termination_url);
        }
        if (typeof previousLiveRecv === 'function') previousLiveRecv(message);
        window.dispatchEvent(new CustomEvent('study-navigation-message', { detail: message }));
    };

    // A clean Summary is terminal. Earlier queued evidence must be confirmed
    // before any normal final content or external registration is displayed.
    if (config.final_screen) {
        const state = readState();
        state.complete = !config.study_terminated && !config.terminated && !state.pending.length && !state.terminated;
        writeState(state);
        if (state.pending.length && !config.terminated) freezeStudy();
    }

    let navigationType = '';
    try {
        const entry = performance.getEntriesByType('navigation')[0];
        if (entry) navigationType = entry.type;
        else if (performance.navigation) {
            navigationType = ({ 1: 'reload', 2: 'back_forward' })[performance.navigation.type] || '';
        }
    } catch (error) { /* Missing timing APIs alone are not evidence. */ }
    if (navigationType === 'reload') recordNavigation('reload');
    if (navigationType === 'back_forward') recordNavigation('history');
    window.addEventListener('pageshow', function (event) {
        if (event.persisted) recordNavigation('history');
        flush();
    });
    window.addEventListener('popstate', function () { recordNavigation('history'); });
    window.addEventListener('online', flush);

    // Chrome can redirect an obsolete oTree history URL to the current page.
    // Observe the actual traversal on the origin document, rather than guessing
    // from a repeated GET. Commit only when it really leaves, not on cancellation.
    let pendingTraversal = null;
    if (window.navigation && typeof window.navigation.addEventListener === 'function') {
        window.navigation.addEventListener('navigate', function(event) {
            pendingTraversal = event.navigationType === 'traverse' ? event : null;
        });
        window.addEventListener('pagehide', function() {
            if (pendingTraversal && (!pendingTraversal.signal || !pendingTraversal.signal.aborted)) {
                recordNavigation('history');
            }
            pendingTraversal = null;
        });
    }

    // Existing normal form submission remains untouched. No beforeunload event
    // is counted: cancelled navigation and ordinary Continue are not evidence.
    window.studyNavigation = {
        allowSubmit: function () { flush(); return !frozen; },
        isStopped: function () { return frozen || Boolean(config.study_terminated || config.terminated) || Boolean(readState().terminated); },
        savePartialTask: function (snapshot) {
            const state = readState();
            state.partial_task = snapshot;
            writeState(state);
        },
        flush: flush,
        taskKey: 'colombia-task:' + config.participant_code + ':' + config.page_index + ':' + config.round_number,
        readTask: function () {
            try {
                const saved = sessionStorage.getItem(this.taskKey);
                return saved ? JSON.parse(saved) : null;
            } catch (error) { return null; }
        },
        saveTask: function (state) {
            try { sessionStorage.setItem(this.taskKey, JSON.stringify(state)); }
            catch (error) { /* A storage failure is not respondent misconduct. */ }
        },
        decisionClock: function (durationSeconds) {
            const state = this.readTask() || {};
            // The deadline starts only when both photographs first become visible.
            if (!Number.isFinite(state.startedAt) || state.durationSeconds !== durationSeconds) {
                state.startedAt = Date.now();
                state.durationSeconds = durationSeconds;
                this.saveTask(state);
            }
            return { startedAt: state.startedAt };
        }
    };

    // A reload can be detected before Task initializes. Keep any actual snapshot
    // saved by the previous document rather than replacing it with empty fields.
    if (window.studyNavigationPartialTask) {
        window.studyNavigation.savePartialTask(window.studyNavigationPartialTask);
    }

    const form = document.getElementById('form');
    if (form) form.addEventListener('submit', function (event) {
        flush();
        if (frozen) event.preventDefault();
    }, true);
    setInterval(flush, 1000);
    flush();
    window.dispatchEvent(new Event('study-navigation-ready'));
}());
