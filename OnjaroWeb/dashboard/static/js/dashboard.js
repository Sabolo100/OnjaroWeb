/**
 * Onjaro Evolution Dashboard - Real-time monitoring client
 */

const socket = io();
let currentRunId = null;
let nextRunAt = null;
let countdownInterval = null;

// ── Clock ────────────────────────────────────────────────────────────────────
function updateClock() {
    const now = new Date();
    document.getElementById('clock').textContent =
        now.toLocaleTimeString('hu-HU', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    document.getElementById('clock-date').textContent =
        now.toLocaleDateString('hu-HU', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'short' });
}
setInterval(updateClock, 1000);
updateClock();

// ── Countdown ────────────────────────────────────────────────────────────────
function updateCountdown() {
    const el = document.getElementById('countdown');
    const info = document.getElementById('countdown-info');

    if (!nextRunAt) {
        el.textContent = '--:--:--';
        info.textContent = 'Várakozás...';
        return;
    }

    const now = new Date();
    const diff = nextRunAt - now;

    if (diff <= 0) {
        el.textContent = '00:00:00';
        el.className = 'countdown-timer imminent';
        info.textContent = 'Futás indul...';
        return;
    }

    const h = Math.floor(diff / 3600000);
    const m = Math.floor((diff % 3600000) / 60000);
    const s = Math.floor((diff % 60000) / 1000);
    el.textContent = `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;

    if (diff < 60000) {
        el.className = 'countdown-timer imminent';
    } else if (diff < 300000) {
        el.className = 'countdown-timer urgent';
    } else {
        el.className = 'countdown-timer';
    }

    info.textContent = `${nextRunAt.toLocaleTimeString('hu-HU', { hour: '2-digit', minute: '2-digit' })}-kor`;
}
setInterval(updateCountdown, 1000);

// ── Socket events ─────────────────────────────────────────────────────────────
socket.on('connect', () => {
    loadInitialData();
    // Fetch next run time from server
    fetch('/api/status').then(r => r.json()).then(d => {
        if (d.next_run_at) nextRunAt = new Date(d.next_run_at);
        updateCountdown();
    });
});

socket.on('next_run_scheduled', (data) => {
    if (data.next_run_at) nextRunAt = new Date(data.next_run_at);
    updateCountdown();
});

socket.on('active_run', (data) => {
    currentRunId = data.run_id;
    updateCurrentRun(data);
});

socket.on('run_start', (event) => {
    currentRunId = event.run_id;
    setSystemStatus('active', 'Running');
    addTimelineEvent(event);
    updateCurrentRun({ run_id: event.run_id, status: 'RUNNING', phase: 'INIT', started_at: event.timestamp });
});

socket.on('phase_change', (event) => {
    addTimelineEvent(event);
    updatePhase(event.phase, event.agent_name || 'orchestrator', event.message);
});

socket.on('agent_start', (event) => {
    addTimelineEvent(event);
    updatePhase(event.phase, event.agent_name, event.message);
});

socket.on('agent_complete', (event) => { addTimelineEvent(event); });
socket.on('agent_failed',   (event) => { addTimelineEvent(event); });

socket.on('feature_chosen', (event) => {
    addTimelineEvent(event);
    updateDecision(event);
    // Reload ideas for this run
    if (event.run_id) loadRunIdeas(event.run_id);
});

socket.on('test_result', (event) => {
    addTimelineEvent(event);
    updateTestResult(event);
});

socket.on('run_complete', (event) => {
    currentRunId = null;
    setSystemStatus('idle', 'Idle');
    addTimelineEvent(event);
    updatePhase('COMPLETE', 'orchestrator', event.message);
    loadRuns();
    loadFeatures();
    if (event.data && event.data.run_id) loadRunIdeas(event.data.run_id);
});

socket.on('run_failed', (event) => {
    currentRunId = null;
    setSystemStatus('error', 'Failed');
    addTimelineEvent(event);
    updatePhase('FAILED', 'orchestrator', event.message);
    loadRuns();
    loadFailures();
});

// ── UI updates ────────────────────────────────────────────────────────────────
function setSystemStatus(state, text) {
    const indicator = document.getElementById('system-status');
    const dot = indicator.querySelector('.dot');
    dot.className = 'dot' + (state === 'active' ? ' active' : state === 'error' ? ' error' : '');
    indicator.querySelector('.status-text').textContent = text;
}

function updateCurrentRun(run) {
    document.getElementById('current-run-content').innerHTML = `
        <div class="run-info">
            <div class="run-info-row"><span class="run-info-label">Run ID</span><span class="run-info-value">${run.run_id || '-'}</span></div>
            <div class="run-info-row"><span class="run-info-label">Status</span><span class="run-status ${(run.status||'').toLowerCase()}">${run.status||'-'}</span></div>
            <div class="run-info-row"><span class="run-info-label">Phase</span><span class="phase-badge ${(run.phase||'').toLowerCase()}">${run.phase||'-'}</span></div>
            <div class="run-info-row"><span class="run-info-label">Feature</span><span class="run-info-value">${run.feature_title||'-'}</span></div>
            <div class="run-info-row"><span class="run-info-label">Started</span><span class="run-info-value">${formatTime(run.started_at)}</span></div>
        </div>`;
}

function updatePhase(phase, agent, message) {
    const badge = document.querySelector('#current-stage .phase-badge');
    badge.className = `phase-badge ${phase.toLowerCase()}`;
    badge.textContent = phase;
    document.getElementById('active-agent').textContent = agent || '-';
    document.getElementById('stage-message').textContent = message || '';
}

function addTimelineEvent(event) {
    const container = document.getElementById('timeline');
    const cssClass = event.severity === 'ERROR' ? 'error' :
                     event.severity === 'DECISION' ? 'decision' :
                     event.event_type === 'run_complete' ? 'success' : '';

    const el = document.createElement('div');
    el.className = `timeline-event ${cssClass}`;
    el.innerHTML = `
        <div class="timeline-time">${formatTime(event.timestamp)}</div>
        <div class="timeline-agent">${event.agent_name||'-'}</div>
        <div class="timeline-message">${event.message||''}</div>`;

    container.querySelector('.empty-state')?.remove();
    container.prepend(el);
    while (container.children.length > 50) container.removeChild(container.lastChild);
}

function updateDecision(event) {
    const chosen = (event.data||{}).chosen || {};
    document.getElementById('decision-card').innerHTML = `
        <div class="decision-content">
            <div class="decision-title">${event.message||'Feature Selected'}</div>
            <div class="decision-rationale">${chosen.rationale||''}</div>
            <div class="decision-score">Score: ${chosen.score||'-'}/100</div>
        </div>`;
}

function updateTestResult(event) {
    const container = document.getElementById('tests-content');
    container.querySelector('.empty-state')?.remove();
    const data = event.data || {};
    const el = document.createElement('div');
    el.className = 'test-item';
    el.innerHTML = `
        <span class="test-name">${data.test_type || event.message || '-'}</span>
        <span class="test-badge ${data.passed ? 'pass' : 'fail'}">${data.passed ? 'PASS' : 'FAIL'}</span>`;
    container.appendChild(el);
}

function renderIdeas(ideas) {
    const el = document.getElementById('ideas-content');
    if (!ideas || !ideas.length) {
        el.innerHTML = '<div class="empty-state">No ideas yet</div>';
        return;
    }
    el.innerHTML = ideas.map(idea => {
        const isChosen = !idea.rejected_reason;
        return `
        <div class="idea-item ${isChosen ? 'chosen' : 'rejected'}">
            <div class="idea-title">
                ${idea.title}
                <span class="idea-badge ${isChosen ? 'chosen' : 'rejected'}">${isChosen ? '✓ Választott' : '✗ Elutasított'}</span>
            </div>
            <div class="idea-desc">${idea.description || ''}</div>
            ${idea.rejected_reason ? `<div class="idea-reject-reason">Miért nem: ${idea.rejected_reason}</div>` : ''}
        </div>`;
    }).join('');
}

// ── Data loading ──────────────────────────────────────────────────────────────
async function loadInitialData() {
    await Promise.all([loadRuns(), loadFeatures(), loadFailures()]);
    // Load ideas from most recent run
    const runs = await fetch('/api/runs').then(r => r.json());
    if (runs.length) loadRunIdeas(runs[0].run_id);
}

async function loadRuns() {
    const runs = await fetch('/api/runs').then(r => r.json()).catch(() => []);
    const el = document.getElementById('runs-list-content');
    if (!runs.length) { el.innerHTML = '<div class="empty-state">No runs yet</div>'; return; }
    el.innerHTML = runs.slice(0, 15).map(run => `
        <div class="run-item" onclick="loadRunDetail('${run.run_id}')">
            <span class="run-id">${run.run_id.slice(0,8)}</span>
            <span class="run-feature">${run.feature_title||'-'}</span>
            <span class="run-status ${(run.status||'').toLowerCase()}">${run.status}</span>
        </div>`).join('');
}

async function loadFeatures() {
    const features = await fetch('/api/features').then(r => r.json()).catch(() => []);
    const el = document.getElementById('features-content');
    if (!features.length) { el.innerHTML = '<div class="empty-state">No live features yet</div>'; return; }
    el.innerHTML = features.slice(0, 15).map(f => `
        <div class="feature-item">
            <div class="feature-title">${f.title}</div>
            <div class="feature-meta">${f.screen||''} | ${formatTime(f.committed_at)}</div>
        </div>`).join('');
}

async function loadFailures() {
    const failures = await fetch('/api/failures').then(r => r.json()).catch(() => []);
    const el = document.getElementById('failures-content');
    if (!failures.length) { el.innerHTML = '<div class="empty-state">No failures</div>'; return; }
    el.innerHTML = failures.slice(0, 10).map(f => `
        <div class="failure-item">
            <div class="failure-phase">${f.phase} - ${f.error_type}</div>
            <div class="failure-message">${(f.error_message||'').substring(0,200)}</div>
            <div class="failure-time">${formatTime(f.created_at)}</div>
        </div>`).join('');
}

async function loadRunIdeas(runId) {
    const ideas = await fetch(`/api/runs/${runId}/ideas`).then(r => r.json()).catch(() => []);
    renderIdeas(ideas);
}

async function loadRunDetail(runId) {
    const data = await fetch(`/api/runs/${runId}`).then(r => r.json()).catch(() => null);
    if (!data) return;
    if (data.run) updateCurrentRun(data.run);

    // Timeline
    const container = document.getElementById('timeline');
    container.innerHTML = '';
    (data.events||[]).reverse().forEach(e => addTimelineEvent(e));

    // Tests
    const testsEl = document.getElementById('tests-content');
    testsEl.innerHTML = '';
    (data.tests||[]).forEach(t => {
        const el = document.createElement('div');
        el.className = 'test-item';
        el.innerHTML = `<span class="test-name">${t.test_type}</span>
            <span class="test-badge ${t.passed ? 'pass' : 'fail'}">${t.passed ? 'PASS' : 'FAIL'}</span>`;
        testsEl.appendChild(el);
    });
    if (!data.tests?.length) testsEl.innerHTML = '<div class="empty-state">No test results</div>';

    // Ideas
    renderIdeas(data.ideas);
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function formatTime(ts) {
    if (!ts) return '-';
    const d = new Date(ts);
    if (isNaN(d.getTime())) return ts;
    return d.toLocaleTimeString('hu-HU', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}
