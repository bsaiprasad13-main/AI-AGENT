// API Base URL (assuming serving from same domain)
const API_BASE = '/api/v1';

// State
let recipients = [];
let pollInterval = null;

// DOM Elements
const elements = {
    btnRun: document.getElementById('btn-run'),
    btnPublish: document.getElementById('btn-publish'),
    statusBadge: document.getElementById('backend-status'),
    runStatusContainer: document.getElementById('run-status-container'),
    runStepText: document.getElementById('run-step'),
    runError: document.getElementById('run-error'),
    spinner: document.querySelector('.spinner'),
    
    emptyState: document.getElementById('empty-state'),
    dashboardContent: document.getElementById('dashboard-content'),
    insightsSkeleton: document.getElementById('insights-skeleton'),
    
    statExtracted: document.getElementById('stat-extracted'),
    statTotal: document.getElementById('stat-total'),
    statRating: document.getElementById('stat-rating'),
    statNegative: document.getElementById('stat-negative'),
    reportDate: document.getElementById('report-date'),
    clusterList: document.getElementById('cluster-list'),
    
    docPreview: document.getElementById('doc-preview'),
    emailSubject: document.getElementById('email-subject'),
    emailBody: document.getElementById('email-body'),
    
    chipContainer: document.getElementById('chip-container'),
    recipientInput: document.getElementById('recipient-input'),
    btnAddRecipient: document.getElementById('btn-add-recipient'),
    emailError: document.getElementById('email-error'),
    approveToggle: document.getElementById('approve-toggle'),
    
    historyTableBody: document.querySelector('#history-table tbody')
};

// --- Initialization ---
async function init() {
    await checkStatus();
    await fetchHistory();
    await fetchLatestReport();
    setupEventListeners();
}

function setupEventListeners() {
    elements.btnRun.addEventListener('click', triggerAnalysis);
    elements.btnPublish.addEventListener('click', publishReport);
    elements.approveToggle.addEventListener('change', validatePublishState);
    
    // Chips logic - Enter / Tab / comma key
    elements.recipientInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === 'Tab' || e.key === ',') {
            e.preventDefault();
            addRecipient(e.target.value.trim().replace(/,$/, ''));
        }
    });

    // Chips logic - blur (click away auto-adds if valid)
    elements.recipientInput.addEventListener('blur', (e) => {
        const val = e.target.value.trim();
        if (val) addRecipient(val);
    });

    // Chips logic - + button
    elements.btnAddRecipient.addEventListener('click', () => {
        addRecipient(elements.recipientInput.value.trim());
        elements.recipientInput.focus();
    });
}

// --- API Calls ---

async function checkStatus() {
    try {
        const res = await fetch(`${API_BASE}/status`);
        const data = await res.json();
        if (data.status === 'online') {
            elements.statusBadge.textContent = 'MCP Online';
            elements.statusBadge.className = 'status-badge online';
        } else {
            elements.statusBadge.textContent = 'MCP Offline';
            elements.statusBadge.className = 'status-badge offline';
        }
    } catch (e) {
        elements.statusBadge.textContent = 'Backend Offline';
        elements.statusBadge.className = 'status-badge offline';
    }
}

async function triggerAnalysis() {
    elements.btnRun.disabled = true;
    elements.spinner.classList.remove('hidden');
    elements.runError.classList.add('hidden');
    elements.runStatusContainer.classList.remove('hidden');
    elements.runStepText.textContent = 'Starting...';

    try {
        const res = await fetch(`${API_BASE}/trigger`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ product: 'groww', force: true }) // MVP hardcoded
        });
        
        if (!res.ok) throw new Error(await res.text());
        
        // Start polling
        pollInterval = setInterval(pollRunStatus, 3000);
    } catch (e) {
        showRunError(e.message);
    }
}

async function pollRunStatus() {
    try {
        const res = await fetch(`${API_BASE}/run-status`);
        const data = await res.json();
        
        if (data.status === 'loading') {
            elements.runStepText.textContent = data.step;
        } else if (data.status === 'success') {
            clearInterval(pollInterval);
            resetRunButton();
            await fetchLatestReport(); // Refresh UI
            await fetchHistory();
        } else if (data.status === 'error') {
            clearInterval(pollInterval);
            showRunError(data.error);
        }
    } catch (e) {
        console.error('Polling error', e);
    }
}

function resetRunButton() {
    elements.btnRun.disabled = false;
    elements.spinner.classList.add('hidden');
    elements.runStatusContainer.classList.add('hidden');
}

function showRunError(msg) {
    resetRunButton();
    elements.runError.textContent = msg;
    elements.runError.classList.remove('hidden');
}

async function fetchLatestReport() {
    elements.emptyState.classList.add('hidden');
    elements.dashboardContent.classList.add('hidden');
    elements.insightsSkeleton.classList.remove('hidden');

    try {
        const res = await fetch(`${API_BASE}/latest-report`);
        const data = await res.json();
        
        elements.insightsSkeleton.classList.add('hidden');
        
        if (data.status === 'not_found') {
            elements.emptyState.classList.remove('hidden');
            return;
        }

        renderDashboard(data);
    } catch (e) {
        elements.insightsSkeleton.classList.add('hidden');
        elements.emptyState.classList.remove('hidden');
        elements.emptyState.textContent = 'Error loading report data.';
    }
}

function renderDashboard(data) {
    const report = data.report;
    elements.dashboardContent.classList.remove('hidden');
    
    // Stats
    elements.statExtracted.textContent = report.total_reviews_extracted || '0';
    elements.statTotal.textContent = report.total_reviews_analyzed;
    elements.statRating.textContent = report.average_rating;
    elements.statNegative.textContent = report.negative_review_percentage + '%';
    elements.reportDate.textContent = `Week: ${report.iso_week}`;

    // Clusters
    elements.clusterList.innerHTML = '';
    report.themes.forEach(theme => {
        const el = document.createElement('div');
        el.className = 'cluster-item';
        
        let quotes = theme.verified_quotes || [];
        let quotesHtml = quotes.slice(0,3).map(q => `<div class="quote-block">"${q.quote_text}"</div>`).join('');
        
        el.innerHTML = `
            <div class="cluster-header">
                <span class="cluster-title">${theme.title}</span>
                <span class="cluster-impact">Impact: ${theme.impact_score.toFixed(1)}</span>
            </div>
            <div class="cluster-desc">${theme.root_cause}</div>
            <div class="cluster-quotes">${quotesHtml}</div>
        `;
        
        el.addEventListener('click', () => el.classList.toggle('expanded'));
        elements.clusterList.appendChild(el);
    });

    // Preview - Rendered Markdown from Backend
    if (data.doc_text && window.marked) {
        elements.docPreview.innerHTML = marked.parse(data.doc_text);
    } else {
        elements.docPreview.textContent = data.doc_text || JSON.stringify(report, null, 2);
    }
    
    // Email defaults - From Backend
    elements.emailSubject.value = data.email_subject || `[Review Pulse] ${report.product_display_name} - ${report.iso_week}`;
    elements.emailBody.value = data.email_body || '';
    
    // reset publish state
    elements.approveToggle.checked = false;
    validatePublishState();
}

async function fetchHistory() {
    try {
        const res = await fetch(`${API_BASE}/history?limit=5`);
        const data = await res.json();
        
        elements.historyTableBody.innerHTML = '';
        data.records.forEach(r => {
            elements.historyTableBody.innerHTML += `
                <tr>
                    <td>${new Date(r.created_at).toLocaleString()}</td>
                    <td>${r.iso_week}</td>
                    <td>${r.reviews_count}</td>
                    <td>${r.doc_status}</td>
                    <td>${r.draft_status}</td>
                </tr>
            `;
        });
    } catch (e) {
        console.error(e);
    }
}

// --- Recipients & Publish ---

function addRecipient(email) {
    const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!regex.test(email)) {
        elements.emailError.style.display = 'block';
        return;
    }
    if (recipients.includes(email)) return;
    
    elements.emailError.style.display = 'none';
    recipients.push(email);
    renderChips();
    elements.recipientInput.value = '';
    validatePublishState();
}

function removeRecipient(email) {
    recipients = recipients.filter(e => e !== email);
    renderChips();
    validatePublishState();
}

function renderChips() {
    // Remove existing chips
    document.querySelectorAll('.chip').forEach(c => c.remove());
    
    // Add chips before input
    recipients.forEach(email => {
        const chip = document.createElement('div');
        chip.className = 'chip';
        chip.innerHTML = `
            ${email}
            <span class="chip-remove" onclick="removeRecipient('${email}')">✕</span>
        `;
        elements.chipContainer.insertBefore(chip, elements.recipientInput);
    });
}

function validatePublishState() {
    const hasRecipients = recipients.length > 0;
    const isApproved = elements.approveToggle.checked;
    
    elements.btnPublish.disabled = !(hasRecipients && isApproved);
    
    if (elements.btnPublish.textContent === '✅ Published!') {
        elements.btnPublish.textContent = 'Publish & Send Email';
        elements.btnPublish.style.background = '';
    }
}

async function publishReport() {
    elements.btnPublish.disabled = true;
    elements.btnPublish.textContent = '⏳ Publishing...';
    elements.btnPublish.style.background = '#f59e0b';

    // Hide any previous banners
    const existing = document.getElementById('publish-result-banner');
    if (existing) existing.remove();

    try {
        const payload = {
            product: 'groww',
            send_email: true,
            recipients: recipients,
            subject: elements.emailSubject.value,
            body: elements.emailBody.value
        };

        const res = await fetch(`${API_BASE}/publish`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await res.json();

        if (!res.ok) throw new Error(data.detail || JSON.stringify(data));

        showPublishBanner('success', '✅ Published! Document updated & Gmail draft created successfully.');
        elements.btnPublish.textContent = '✅ Published!';
        elements.btnPublish.style.background = 'var(--success)';
        await fetchHistory();
    } catch (e) {
        showPublishBanner('error', '❌ Publish failed: ' + e.message);
        elements.btnPublish.textContent = 'Publish & Send Email';
        elements.btnPublish.style.background = 'var(--success)';
        elements.btnPublish.disabled = false;
    }
}

function showPublishBanner(type, message) {
    const banner = document.createElement('div');
    banner.id = 'publish-result-banner';
    banner.style.cssText = `
        margin-top: 1rem;
        padding: 1rem 1.25rem;
        border-radius: 8px;
        font-size: 0.9rem;
        font-weight: 500;
        background: ${type === 'success' ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)'};
        border: 1px solid ${type === 'success' ? 'rgba(16,185,129,0.4)' : 'rgba(239,68,68,0.4)'};
        color: ${type === 'success' ? '#10b981' : '#ef4444'};
    `;
    banner.textContent = message;
    elements.btnPublish.insertAdjacentElement('afterend', banner);
}

// Start
init();
