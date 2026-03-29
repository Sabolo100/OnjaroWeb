/**
 * Onjaro Evolution Dashboard - Real-time monitoring client
 */

const socket = io();
let currentRunId = null;
let nextRunAt = null;
let countdownInterval = null;
let sessionStartTime = Date.now();

// ── CET Formatter ─────────────────────────────────────────────────────────────
// All timestamps displayed in CET (Central European Time)
function formatTime(ts) {
    if (!ts) return '-';
    const d = new Date(ts);
    if (isNaN(d.getTime())) return ts;
    return d.toLocaleString('hu-HU', {
        timeZone: 'Europe/Budapest',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
    });
}

function formatTimeShort(ts) {
    if (!ts) return '-';
    const d = new Date(ts);
    if (isNaN(d.getTime())) return ts;
    return d.toLocaleString('hu-HU', {
        timeZone: 'Europe/Budapest',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
    });
}

// ── Clock ────────────────────────────────────────────────────────────────────
function updateClock() {
    const now = new Date();
    document.getElementById('clock').textContent =
        now.toLocaleTimeString('hu-HU', { timeZone: 'Europe/Budapest', hour: '2-digit', minute: '2-digit', second: '2-digit' });
    document.getElementById('clock-date').textContent =
        now.toLocaleDateString('hu-HU', { timeZone: 'Europe/Budapest', year: 'numeric', month: 'long', day: 'numeric', weekday: 'short' }) + ' CET';
}
setInterval(updateClock, 1000);
updateClock();

// ── Session Timer / Stopwatch ─────────────────────────────────────────────────
function updateSessionTimer() {
    const el = document.getElementById('session-timer');
    if (!el) return;
    const elapsed = Date.now() - sessionStartTime;
    const h = Math.floor(elapsed / 3600000);
    const m = Math.floor((elapsed % 3600000) / 60000);
    const s = Math.floor((elapsed % 60000) / 1000);
    el.textContent = `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
}
setInterval(updateSessionTimer, 1000);

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

    info.textContent = `${nextRunAt.toLocaleTimeString('hu-HU', { timeZone: 'Europe/Budapest', hour: '2-digit', minute: '2-digit' })} CET`;
}
setInterval(updateCountdown, 1000);

// ── Socket events ─────────────────────────────────────────────────────────────
socket.on('connect', () => {
    loadInitialData();
    // Fetch status from server
    fetch('/api/status').then(r => r.json()).then(d => {
        // Store server-reported session start for the stopwatch
        if (d.session_started_at) {
            sessionStartTime = new Date(d.session_started_at).getTime();
        }
        if (!d.evolution_enabled) {
            setSystemStatus('idle', 'Evolution KI');
            document.getElementById('current-run-content').innerHTML =
                '<div class="empty-state">Evolution modul kikapcsolva (EVOLUTION_ENABLED=0)</div>';
            document.getElementById('countdown-banner').style.display = 'none';
        } else {
            if (d.next_run_at) nextRunAt = new Date(d.next_run_at);
            updateCountdown();
        }
        if (!d.research_enabled) {
            document.getElementById('research-run-content').innerHTML =
                '<div class="empty-state">Research modul kikapcsolva (RESEARCH_ENABLED=0)</div>';
        }
        // Update combined system status
        updateCombinedStatus(d);
    });
});

function updateCombinedStatus(statusData) {
    // Determine the real combined status
    const evoEnabled = statusData.evolution_enabled;
    const resEnabled = statusData.research_enabled;

    if (!evoEnabled && !resEnabled) {
        setSystemStatus('idle', 'Minden KI');
    } else {
        // Will be updated dynamically by socket events
    }
}

socket.on('next_run_scheduled', (data) => {
    if (data.next_run_at) nextRunAt = new Date(data.next_run_at);
    updateCountdown();
});

socket.on('active_run', (data) => {
    currentRunId = data.run_id;
    updateCurrentRun(data);
    setSystemStatus('active', 'Evolution fut');
});

socket.on('run_start', (event) => {
    currentRunId = event.run_id;
    setSystemStatus('active', 'Evolution fut');
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
    setSystemStatus('error', 'Hiba');
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

    // Update the session status banner
    const banner = document.getElementById('session-status-banner');
    if (banner) {
        if (state === 'active') {
            banner.className = 'session-status-banner active';
            banner.querySelector('.session-status-text').textContent = text;
        } else if (state === 'error') {
            banner.className = 'session-status-banner error';
            banner.querySelector('.session-status-text').textContent = text;
        } else {
            banner.className = 'session-status-banner idle';
            banner.querySelector('.session-status-text').textContent = text;
        }
    }
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
            <div class="feature-meta">${f.screen||''} | ${formatTimeShort(f.committed_at)}</div>
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

// ══════════════════════════════════════════════════════════════════════════════
// TAB NAVIGATION
// ══════════════════════════════════════════════════════════════════════════════

function switchTab(tabName) {
    // Update buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tabName);
    });
    // Update content
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.toggle('active', content.id === 'tab-' + tabName);
    });
    // Load research data when switching to research tab
    if (tabName === 'research') {
        loadResearchData();
    }
}

// ══════════════════════════════════════════════════════════════════════════════
// RESEARCH TAB - Socket events
// ══════════════════════════════════════════════════════════════════════════════

let researchRunActive = false;

socket.on('active_research_run', (data) => {
    researchRunActive = true;
    updateResearchRun(data);
    setSystemStatus('active', `Research fut — ${data.phase || 'INIT'}`);
});

socket.on('research_run_start', (event) => {
    researchRunActive = true;
    addResearchTimelineEvent(event);
    updateResearchRun({ run_id: event.run_id, status: 'RUNNING', phase: 'QUEUED', started_at: event.timestamp });
    setSystemStatus('active', 'Research fut — QUEUED');
});

socket.on('research_phase_change', (event) => {
    addResearchTimelineEvent(event);
    const phase = event.phase || '';
    updateResearchPhase(phase, event.agent_name || 'research_manager', event.message);
    // Update header status to show combined state
    if (researchRunActive) {
        setSystemStatus('active', `Research fut — ${phase.toUpperCase()}`);
    }
});

socket.on('research_agent_start', (event) => { addResearchTimelineEvent(event); });
socket.on('research_agent_complete', (event) => { addResearchTimelineEvent(event); });
socket.on('research_agent_failed', (event) => { addResearchTimelineEvent(event); });

socket.on('research_item_complete', (event) => {
    addResearchTimelineEvent(event);
    updateResearchStats(event.data);
});

socket.on('research_run_complete', (event) => {
    researchRunActive = false;
    addResearchTimelineEvent(event);
    updateResearchPhase('COMPLETED', 'research_manager', event.message);
    setSystemStatus('idle', 'Idle — Research kész');
    loadResearchRuns();
    loadResearchReviews();
});

socket.on('research_run_failed', (event) => {
    researchRunActive = false;
    addResearchTimelineEvent(event);
    updateResearchPhase('FAILED', 'research_manager', event.message);
    setSystemStatus('error', 'Hiba — Research');
    loadResearchRuns();
});

// ── Receive initial research timeline events on connect ──
socket.on('research_timeline_history', (events) => {
    if (!events || !events.length) return;
    const container = document.getElementById('research-timeline');
    if (!container) return;
    container.innerHTML = '';
    // events arrive oldest-first, we display newest-first
    events.reverse().forEach(e => {
        const cssClass = e.severity === 'ERROR' ? 'error' :
                         e.event_type === 'research_run_complete' ? 'success' : '';
        const el = document.createElement('div');
        el.className = `timeline-event ${cssClass}`;
        el.innerHTML = `
            <div class="timeline-time">${formatTime(e.timestamp)}</div>
            <div class="timeline-agent">${e.agent_name||'-'}</div>
            <div class="timeline-message">${e.message||''}</div>`;
        container.appendChild(el);
    });
});

// ── Research UI updates ──────────────────────────────────────────────────────

function updateResearchRun(run) {
    const statusPhase = run.phase ? `${run.status || 'RUNNING'} — ${run.phase}` : (run.status || '-');
    document.getElementById('research-run-content').innerHTML = `
        <div class="run-info">
            <div class="run-info-row"><span class="run-info-label">Run ID</span><span class="run-info-value">${run.run_id || '-'}</span></div>
            <div class="run-info-row"><span class="run-info-label">Status</span><span class="run-status ${(run.status||'').toLowerCase()}">${statusPhase}</span></div>
            <div class="run-info-row"><span class="run-info-label">Items</span><span class="run-info-value">${run.items_completed||0}/${run.items_total||0} (${run.items_failed||0} failed)</span></div>
            <div class="run-info-row"><span class="run-info-label">Started</span><span class="run-info-value">${formatTime(run.started_at)}</span></div>
        </div>`;
}

function updateResearchPhase(phase, agent, message) {
    const badge = document.querySelector('#research-stage .phase-badge');
    if (badge) {
        badge.className = `phase-badge ${phase.toLowerCase()}`;
        badge.textContent = phase;
    }
    const agentEl = document.getElementById('research-active-agent');
    if (agentEl) agentEl.textContent = agent || '-';
    const msgEl = document.getElementById('research-stage-message');
    if (msgEl) msgEl.textContent = message || '';
}

function addResearchTimelineEvent(event) {
    const container = document.getElementById('research-timeline');
    if (!container) return;
    const cssClass = event.severity === 'ERROR' ? 'error' :
                     event.event_type === 'research_run_complete' ? 'success' : '';

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

function updateResearchStats(data) {
    if (!data) return;
    document.getElementById('research-stats').innerHTML = `
        <div class="decision-content">
            <div class="decision-title">Item: ${data.item_id || '-'}</div>
            <div class="decision-rationale">
                Raw findings: ${data.raw || 0} |
                Extracted: ${data.extracted || 0} |
                Persisted: ${data.persisted || 0} |
                Skipped: ${data.skipped || 0}
            </div>
        </div>`;
}

// ── Research data loading ────────────────────────────────────────────────────

async function loadResearchData() {
    await Promise.all([
        loadResearchRuns(),
        loadResearchReviews(),
        loadResearchSources(),
        loadResearchTimeline(),
    ]);
}

async function loadResearchTimeline() {
    // Fetch timeline from the most recent research run
    const runs = await fetch('/api/research/runs').then(r => r.json()).catch(() => []);
    if (!runs.length) return;
    const latestRunId = runs[0].run_id;
    const detail = await fetch(`/api/research/runs/${latestRunId}`).then(r => r.json()).catch(() => null);
    if (!detail || !detail.events || !detail.events.length) return;

    const container = document.getElementById('research-timeline');
    if (!container) return;
    container.innerHTML = '';
    detail.events.reverse().forEach(e => {
        const cssClass = e.severity === 'ERROR' ? 'error' :
                         e.event_type === 'research_run_complete' ? 'success' : '';
        const el = document.createElement('div');
        el.className = `timeline-event ${cssClass}`;
        el.innerHTML = `
            <div class="timeline-time">${formatTime(e.timestamp)}</div>
            <div class="timeline-agent">${e.agent_name||'-'}</div>
            <div class="timeline-message">${e.message||''}</div>`;
        container.appendChild(el);
    });

    // Also update run info panel
    if (detail.run) updateResearchRun(detail.run);
}

async function loadResearchRuns() {
    const runs = await fetch('/api/research/runs').then(r => r.json()).catch(() => []);
    const el = document.getElementById('research-runs-list');
    if (!el) return;
    if (!runs.length) { el.innerHTML = '<div class="empty-state">No research runs yet</div>'; return; }
    el.innerHTML = runs.slice(0, 15).map(run => `
        <div class="run-item" onclick="loadResearchRunDetail('${run.run_id}')">
            <span class="run-id">${run.run_id.slice(0,12)}</span>
            <span class="run-feature">${run.items_completed||0}/${run.items_total||0} items</span>
            <span class="run-status ${(run.status||'').toLowerCase()}">${run.status}</span>
            <span class="run-time">${formatTimeShort(run.started_at)}</span>
        </div>`).join('');
}

async function loadResearchRunDetail(runId) {
    const data = await fetch(`/api/research/runs/${runId}`).then(r => r.json()).catch(() => null);
    if (!data) return;
    if (data.run) updateResearchRun(data.run);

    // Timeline
    const container = document.getElementById('research-timeline');
    if (container) {
        container.innerHTML = '';
        (data.events||[]).reverse().forEach(e => addResearchTimelineEvent(e));
    }

    // Findings
    const findingsEl = document.getElementById('research-findings-content');
    if (findingsEl) {
        const findings = data.raw_findings || [];
        if (!findings.length) {
            findingsEl.innerHTML = '<div class="empty-state">No findings</div>';
        } else {
            findingsEl.innerHTML = findings.slice(0, 20).map(f => `
                <div class="feature-item">
                    <div class="feature-title">${f.title || f.url}</div>
                    <div class="feature-meta">${f.source_domain || ''} | ${formatTimeShort(f.fetched_at)}</div>
                </div>`).join('');
        }
    }
}

async function loadResearchReviews() {
    const reviews = await fetch('/api/research/reviews').then(r => r.json()).catch(() => []);
    const el = document.getElementById('review-queue-content');
    if (!el) return;

    // Update badge
    const badge = document.getElementById('review-badge');
    if (badge) {
        if (reviews.length > 0) {
            badge.textContent = reviews.length;
            badge.style.display = 'inline-block';
        } else {
            badge.style.display = 'none';
        }
    }

    if (!reviews.length) { el.innerHTML = '<div class="empty-state">Nincs elbiralasra varo elem</div>'; return; }
    el.innerHTML = reviews.map(r => {
        // Parse extracted_data for richer display
        let extracted = {};
        try {
            if (typeof r.extracted_data === 'string') {
                extracted = JSON.parse(r.extracted_data);
            } else if (r.extracted_data) {
                extracted = r.extracted_data;
            }
        } catch(e) {}

        const entityName = extracted.title || extracted.name || '-';
        const entityType = r.item_id ? r.item_id.replace(/_hu$/, '').replace(/_/g, ' ') : '-';
        const confidence = (r.confidence || 0);
        const confPct = Math.round(confidence * 100);
        const confColor = confPct >= 70 ? 'var(--accent-green)' : confPct >= 50 ? 'var(--accent-yellow)' : 'var(--accent-red)';

        // Build detail fields
        let details = [];
        if (extracted.service_types && extracted.service_types.length) details.push(`Szolg: ${extracted.service_types.join(', ')}`);
        if (extracted.building_type) details.push(`Típus: ${extracted.building_type}`);
        if (extracted.building_class) details.push(`Kat: ${extracted.building_class}`);
        if (extracted.city || extracted.headquarters_city) details.push(`Város: ${extracted.city || extracted.headquarters_city}`);
        if (extracted.address) details.push(`Cím: ${extracted.address}`);
        if (extracted.website) details.push(`Web: ${extracted.website}`);
        if (extracted.position_title || extracted.title) details.push(`Pozíció: ${extracted.position_title || extracted.title}`);
        if (extracted.current_company_name) details.push(`Cég: ${extracted.current_company_name}`);
        if (extracted.total_area_sqm) details.push(`Terület: ${extracted.total_area_sqm} m²`);
        if (extracted.source_url) details.push(`Forrás: ${String(extracted.source_url).substring(0, 60)}`);
        const detailsHtml = details.length ? `<div class="review-details">${details.map(d => `<span class="review-detail-chip">${d}</span>`).join('')}</div>` : '';

        return `
        <div class="review-card">
            <div class="review-header">
                <div class="review-entity-name">${entityName}</div>
                <div class="review-entity-type">${entityType}</div>
            </div>
            <div class="review-confidence-row">
                <div class="review-conf-bar-bg">
                    <div class="review-conf-bar" style="width:${confPct}%; background:${confColor}"></div>
                </div>
                <span class="review-conf-label" style="color:${confColor}">${confPct}%</span>
            </div>
            <div class="review-reason-text">${r.review_reason || ''}</div>
            ${detailsHtml}
            <div class="review-actions">
                <button class="btn-approve" onclick="approveReview(${r.review_id})">&#10003; Jóváhagy</button>
                <button class="btn-reject" onclick="rejectReview(${r.review_id})">&#10007; Elutasít</button>
            </div>
        </div>`;
    }).join('');
}

async function loadResearchSources() {
    const sources = await fetch('/api/research/sources').then(r => r.json()).catch(() => []);
    const el = document.getElementById('source-health-content');
    if (!el) return;
    if (!sources.length) { el.innerHTML = '<div class="empty-state">No sources registered</div>'; return; }
    el.innerHTML = sources.map(s => `
        <div class="feature-item">
            <div class="feature-title">${s.domain} <span class="test-badge ${s.trust_score >= 0.7 ? 'pass' : s.trust_score >= 0.4 ? '' : 'fail'}">${(s.trust_score||0).toFixed(2)}</span></div>
            <div class="feature-meta">Fetches: ${s.total_fetches||0} | Success: ${s.successful_extractions||0} | ${s.language||'?'}</div>
        </div>`).join('');
}

async function approveReview(reviewId) {
    await fetch(`/api/research/reviews/${reviewId}/approve`, {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'
    });
    loadResearchReviews();
}

async function rejectReview(reviewId) {
    await fetch(`/api/research/reviews/${reviewId}/reject`, {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'
    });
    loadResearchReviews();
}
