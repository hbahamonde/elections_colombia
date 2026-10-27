"""Exercise navigation evidence in memory only, with no oTree database or network.

Run ``.venv/bin/python test_navigation_frontend.py``. Real Chrome/oTree tests
complement these deterministic JavaScript event, acknowledgement, and clock tests.
"""

from pathlib import Path
import shutil
import subprocess
import unittest


CHECK_JAVASCRIPT = r'''
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync(process.argv[1], 'utf8');
let id = 0;
let now = 10000;

function browser(options = {}) {
    const saved = options.storage || new Map();
    const listeners = {};
    const navListeners = {};
    const sent = [];
    const intervals = [];
    const replacements = [];
    const config = Object.assign({ participant_code: 'testsubject', page_index: 7,
        page_name: 'Task', round_number: 1, enabled: true, final_screen: false,
        violation: false }, options.config || {});
    const form = { children: [], handlers: [], addEventListener: function(type, callback) {
        if (type === 'submit') this.handlers.push(callback);
    },
        appendChild: function(input) { this.children.push(input); } };
    const control = { disabled: false };
    const summary = { hidden: false };
    const document = { getElementById: id => ({ form: form, 'study-final-content': summary })[id] || null,
        createElement: () => ({ style: {}, setAttribute: () => {} }),
        querySelectorAll: selector => selector.includes('button') ? [control] : [],
        body: { children: [], appendChild: function(element) { this.children.push(element); } } };
    const context = { document, Set, Math, Number, JSON, Infinity,
        Date: { now: () => now },
        performance: { now: () => now, getEntriesByType: () => [
            { type: options.navigationType || 'navigate' }] },
        sessionStorage: { getItem: key => {
            if (options.storageBlocked) throw new Error('Disabled storage');
            return saved.get(key) || null;
        }, setItem: (key, value) => {
            if (options.storageBlocked) throw new Error('Disabled storage');
            saved.set(key, value);
        } },
        Event: function(type) { this.type = type; },
        CustomEvent: function(type, init) { this.type = type; this.detail = init.detail; },
        setInterval: callback => intervals.push(callback),
        crypto: { randomUUID: () => 'event-' + (++id) },
        URLSearchParams,
        location: { href: 'https://local.test/p/testsubject/Task/7',
            replace: url => replacements.push(url) },
        js_vars: { study_navigation: config },
        addEventListener: (type, callback) => (listeners[type] ||= []).push(callback),
        dispatchEvent: event => (listeners[event.type] || []).forEach(callback => callback(event)),
        navigation: { addEventListener: (type, callback) => {
            (navListeners[type] ||= []).push(callback);
        } },
        liveSend: message => {
            if (options.offline) throw new Error('Disconnected socket');
            sent.push(message);
        }
    };
    if (options.fetch) context.fetch = options.fetch;
    context.window = context;
    vm.createContext(context);
    vm.runInContext(source, context);
    return { context, sent, saved, form, control, summary, replacements,
        fire: (type, event = {}) => context.dispatchEvent(Object.assign({ type }, event)),
        navigate: event => (navListeners.navigate || []).forEach(callback => callback(event)),
        pending: () => JSON.parse(saved.get('colombia-navigation:testsubject')).pending,
        tick: () => intervals.forEach(callback => callback()) };
}

const passed = [];
function check(name, run) { run(); passed.push(name); }

check('normal navigation, submit, hide, online, and socket retry do not create events', () => {
    const tab = browser();
    tab.fire('pagehide'); tab.fire('online'); tab.tick();
    tab.context.studyNavigation.allowSubmit();
    assert.equal(tab.sent.length, 0);
});
check('initial instructions can be reloaded before acknowledgement', () => {
    const tab = browser({ navigationType: 'reload', config: { enabled: false } });
    assert.equal(tab.sent.length, 0);
});
check('protected reload creates one persistent event and retry uses the same id', () => {
    const tab = browser({ navigationType: 'reload' });
    assert.equal(tab.pending().length, 1);
    const first = tab.pending()[0];
    assert.equal(first.type, 'reload');
    tab.tick(); tab.fire('pageshow');
    assert.equal(tab.pending().length, 1);
    assert.equal(tab.sent.at(-1).navigation_events[0].id, first.id);
    tab.context.liveRecv({ navigation_ack: [first.id], navigation_violation: true });
    assert.equal(tab.pending().length, 0);
});
check('back_forward, persisted pageshow and popstate deduplicate the same traversal', () => {
    const tab = browser({ navigationType: 'back_forward' });
    tab.fire('pageshow', { persisted: true }); tab.fire('popstate');
    assert.equal(tab.pending().length, 1);
    assert.equal(tab.pending()[0].type, 'history');
});
check('actual traversal is recorded on origin even if oTree redirects the destination', () => {
    const tab = browser();
    tab.navigate({ navigationType: 'traverse', signal: { aborted: false } });
    assert.equal(tab.sent.length, 0);
    tab.fire('pagehide');
    assert.equal(tab.pending()[0].type, 'history');
});
check('cancelled or aborted browser navigation is not a violation', () => {
    const tab = browser();
    tab.navigate({ navigationType: 'traverse', signal: { aborted: true } });
    tab.fire('pagehide');
    assert.equal(tab.sent.length, 0);
    tab.navigate({ navigationType: 'traverse', signal: { aborted: false } });
    assert.equal(tab.sent.length, 0); // Cancelled dialog did not leave the document.
});
check('pending event survives a lost socket and a subsequent normal page', () => {
    const first = browser({ navigationType: 'reload', offline: true });
    assert.equal(first.pending().length, 1);
    const second = browser({ storage: first.saved, config: { page_index: 8, page_name: 'FollowUp' } });
    assert.equal(second.sent[0].navigation_events[0].page_index, 7);
    assert.equal(second.pending().length, 1);
});
check('unacknowledged events accompany normal POST even if live socket is disconnected', () => {
    const tab = browser({ navigationType: 'reload', offline: true });
    const evidence = tab.form.children.find(input => input.name === '_study_navigation_events');
    assert.equal(evidence.type, 'hidden');
    assert.equal(JSON.parse(evidence.value)[0].type, 'reload');
    tab.context.studyNavigation.allowSubmit();
    assert.equal(tab.form.children.length, 1);
    const eventId = JSON.parse(evidence.value)[0].id;
    tab.context.liveRecv({ navigation_ack: [eventId] });
    assert.equal(evidence.value, '[]');
});
check('Summary flushes old evidence but adds none, including Back from raffle/end', () => {
    const first = browser({ navigationType: 'reload' });
    const end = browser({ storage: first.saved, navigationType: 'reload',
        config: { final_screen: true, page_name: 'Summary', page_index: 100 } });
    assert.equal(end.pending().length, 1);
    assert.equal(end.sent.length, 1);
    first.fire('popstate'); // Cached old task sees the terminal marker.
    assert.equal(first.pending().length, 1);
    end.fire('pageshow', { persisted: true });
    assert.equal(end.pending().length, 1);
});
check('timed first-visible deadline survives reload, keeps evidence, and isolates rounds', () => {
    const first = browser();
    const clock = first.context.studyNavigation.decisionClock(9);
    const progress = first.context.studyNavigation.readTask();
    progress.fields = { decision_side: 'left', learn_more_clicks: '2' };
    first.context.studyNavigation.saveTask(progress);
    now += 4000;
    const second = browser({ storage: first.saved, navigationType: 'reload' });
    assert.equal(second.context.studyNavigation.decisionClock(9).startedAt, clock.startedAt);
    assert.equal(second.context.studyNavigation.readTask().fields.decision_side, 'left');
    const next = browser({ storage: first.saved, config: { round_number: 2, page_index: 17 } });
    assert.equal(next.context.studyNavigation.decisionClock(9).startedAt, now);
});
check('blocked storage alone does not crash or fabricate a navigation violation', () => {
    const tab = browser({ storageBlocked: true });
    assert.equal(tab.sent.length, 0);
    assert.equal(tab.context.studyNavigation.decisionClock(9).startedAt, now);
    tab.fire('online'); tab.fire('pagehide');
    assert.equal(tab.sent.length, 0);
});
check('server acknowledgement is dispatched without replacing another page receiver', () => {
    const tab = browser({ navigationType: 'reload' });
    let received = false;
    tab.context.addEventListener('study-navigation-message', () => { received = true; });
    tab.context.liveRecv({ navigation_ack: [tab.pending()[0].id] });
    assert.equal(received, true);
});
check('detected navigation immediately freezes controls and blocks ordinary form submission', () => {
    const tab = browser({ navigationType: 'reload' });
    assert.equal(tab.context.studyNavigation.isStopped(), true);
    assert.equal(tab.context.studyNavigation.allowSubmit(), false);
    assert.equal(tab.control.disabled, true);
    let prevented = false;
    tab.form.handlers.forEach(callback => callback({ preventDefault: () => { prevented = true; } }));
    assert.equal(prevented, true);
    assert.equal(tab.replacements.length, 0); // Wait for actual server confirmation.
});
check('termination acknowledgement persists closure and redirects only once', () => {
    const tab = browser({ navigationType: 'reload' });
    const message = { navigation_ack: [tab.pending()[0].id], study_terminated: true,
        termination_url: tab.context.location.href };
    tab.context.liveRecv(message); tab.context.liveRecv(message);
    assert.equal(tab.replacements.length, 1);
    assert.equal(tab.replacements[0], tab.context.location.href);
    assert.equal(JSON.parse(tab.saved.get('colombia-navigation:testsubject')).terminated, true);
    const restored = browser({ storage: tab.saved });
    assert.equal(restored.context.studyNavigation.isStopped(), true);
    assert.equal(restored.control.disabled, true);
    assert.equal(restored.replacements.length, 1);
    restored.fire('pageshow', { persisted: true });
    assert.equal(restored.replacements.length, 1);
});
check('backend study_terminated flag is recognized directly', () => {
    const tab = browser({ config: { study_terminated: true } });
    assert.equal(tab.context.studyNavigation.isStopped(), true);
    assert.equal(tab.control.disabled, true);
    assert.equal(tab.replacements.length, 1);
});
check('pending evidence suppresses final content, whereas a clean Summary remains complete', () => {
    const prior = browser({ navigationType: 'reload' });
    const blocked = browser({ storage: prior.saved, config: { final_screen: true, page_name: 'Summary' } });
    assert.equal(blocked.summary.hidden, true);
    assert.equal(blocked.context.studyNavigation.isStopped(), true);
    const clean = browser({ config: { final_screen: true, page_name: 'Summary' } });
    assert.equal(clean.summary.hidden, false);
    assert.equal(JSON.parse(clean.saved.get('colombia-navigation:testsubject')).complete, true);
    clean.fire('popstate');
    assert.equal(clean.sent.length, 0);
});
check('a disconnected socket stays frozen and fallback POST carries only evidence and actual partial telemetry', () => {
    const requests = [];
    const tab = browser({ navigationType: 'reload', offline: true,
        fetch: (url, settings) => {
            requests.push({ url, settings });
            return Promise.resolve({ ok: false });
        } });
    tab.context.studyNavigation.savePartialTask({ page_index: 7,
        fields: { learn_more_clicks: '2', decision_side: 'left' } });
    now += 2000;
    tab.tick();
    assert.equal(tab.control.disabled, true);
    assert.equal(requests.length, 1);
    const body = new URLSearchParams(requests[0].settings.body);
    assert.equal(JSON.parse(body.get('_study_navigation_events'))[0].type, 'reload');
    assert.equal(JSON.parse(body.get('_study_navigation_task')).fields.learn_more_clicks, '2');
    assert.equal(body.has('decision_side'), false); // Never submit a normal task outcome.
    assert.equal(tab.replacements.length, 0);
});
console.log(JSON.stringify({ passed }));
'''


class NavigationFrontendTests(unittest.TestCase):
    def test_browser_events_and_persistent_deadline(self):
        node = shutil.which('node') or str(Path.home() / '.cache/codex-runtimes/'
            'codex-primary-runtime/dependencies/node/bin/node')
        source = Path(__file__).parent / '_static/conjoint/navigation_integrity.js'
        result = subprocess.run([node, '-e', CHECK_JAVASCRIPT, str(source)],
                                text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        print(result.stdout.strip())


if __name__ == '__main__':
    unittest.main()
