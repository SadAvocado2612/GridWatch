// fines.js - Fines Management System Controller
(function () {
    'use strict';

    // Session validation guard
    const sessionToken = sessionStorage.getItem('session_token');
    if (!sessionToken) {
        window.location.replace('login.html');
        return;
    }

    const API_BASE = window.location.origin.includes('127.0.0.1') || window.location.origin.includes('localhost')
        ? window.location.origin + '/api'
        : 'http://localhost:8000/api';

    let finesList = [];
    let loadedHistories = {}; // cache for loaded violation histories by vehicle number

    document.addEventListener('DOMContentLoaded', () => {
        setupEventListeners();
        loadFines();
    });

    function setupEventListeners() {
        const filterStatus = document.getElementById('filter-status');
        const sortBy = document.getElementById('sort-by');
        const scanBtn = document.getElementById('btn-scan-offenders');
        const bulkBtn = document.getElementById('btn-bulk-reminders');

        if (filterStatus) {
            filterStatus.addEventListener('change', () => renderTable());
        }
        if (sortBy) {
            sortBy.addEventListener('change', () => renderTable());
        }
        if (scanBtn) {
            scanBtn.addEventListener('click', () => triggerScan());
        }
        if (bulkBtn) {
            bulkBtn.addEventListener('click', () => triggerBulkReminders());
        }
    }

    // Fetch all fines from database
    async function loadFines() {
        const tbody = document.getElementById('fines-table-body');
        try {
            const res = await fetch(`${API_BASE}/fines`, {
                headers: {
                    'Authorization': `Bearer ${sessionToken}`
                }
            });

            if (res.status === 401) {
                sessionStorage.clear();
                window.location.replace('login.html');
                return;
            }

            if (!res.ok) throw new Error('Failed to fetch fines list');
            finesList = await res.json();

            computeSummaryMetrics(finesList);
            renderTable();
        } catch (err) {
            console.error('Error loading fines:', err);
            tbody.innerHTML = `<tr><td colspan="9" class="ledger-placeholder text-danger">Error: ${err.message}</td></tr>`;
        }
    }

    // Compute metric strip values
    function computeSummaryMetrics(list) {
        const totalFines = list.length;
        let outstanding = 0;
        let collected = 0;
        
        list.forEach(item => {
            if (item.status === 'paid') {
                collected += item.fine_amount;
            } else {
                outstanding += item.fine_amount;
            }
        });

        document.getElementById('summary-total-fines').textContent = totalFines;
        document.getElementById('summary-outstanding-amount').textContent = `₹${outstanding.toLocaleString()}`;
        document.getElementById('summary-collected-amount').textContent = `₹${collected.toLocaleString()}`;
        document.getElementById('summary-repeat-offenders').textContent = totalFines; // unique vehicle count matches fines rows
    }

    // Sort and filter grid rows
    function renderTable() {
        const tbody = document.getElementById('fines-table-body');
        const statusFilter = document.getElementById('filter-status').value;
        const sortCriteria = document.getElementById('sort-by').value;

        // 1. Filter
        let filtered = finesList.filter(item => {
            if (statusFilter === 'all') return true;
            return item.status === statusFilter;
        });

        // 2. Sort
        filtered.sort((a, b) => {
            if (sortCriteria === 'amount-desc') {
                return b.fine_amount - a.fine_amount;
            } else if (sortCriteria === 'amount-asc') {
                return a.fine_amount - b.fine_amount;
            } else if (sortCriteria === 'count-desc') {
                return b.violation_count - a.violation_count;
            }
            return 0;
        });

        // 3. Render
        if (filtered.length === 0) {
            tbody.innerHTML = `<tr><td colspan="9" class="ledger-placeholder" style="text-align: center; padding: 30px;">No matching fine records found.</td></tr>`;
            return;
        }

        tbody.innerHTML = '';
        filtered.forEach(row => {
            // Main row
            const tr = document.createElement('tr');
            tr.className = `fine-row row-main-${row.fine_id}`;
            tr.setAttribute('data-id', row.fine_id);
            tr.setAttribute('data-vehicle', row.vehicle_number);

            const lastReminderStr = row.last_reminder_at 
                ? formatDate(row.last_reminder_at) 
                : 'Never';
                
            const statusHtml = row.status === 'paid'
                ? `<span class="status-pill paid pill-status-${row.fine_id}">Paid</span>`
                : `<span class="status-pill unpaid pill-status-${row.fine_id}">Unpaid</span>`;

            const actionHtml = row.status === 'paid'
                ? `<span class="text-muted text-sm" style="font-size: 12px; font-weight: 500;">Closed</span>`
                : `<div class="actions-cell-${row.fine_id}" style="display: flex; align-items: center;">
                       <span class="link-mark-paid link-paid-${row.fine_id}" data-id="${row.fine_id}">Mark Paid</span>
                   </div>`;

            tr.innerHTML = `
                <td class="vehicle-cell">${row.vehicle_number}</td>
                <td>${row.vehicle_type}</td>
                <td style="font-weight: 600; text-align: center;">${row.violation_count}</td>
                <td style="font-weight: 700; color: var(--primary-color);">₹${row.fine_amount.toLocaleString()}</td>
                <td>${row.phone_number_simulated}</td>
                <td>${statusHtml}</td>
                <td class="last-reminder-col-${row.fine_id}">${lastReminderStr}</td>
                <td class="reminder-count-col-${row.fine_id}" style="text-align: center; font-weight: 600;">${row.reminder_count}</td>
                <td>${actionHtml}</td>
            `;

            // Expandable detail row
            const detailTr = document.createElement('tr');
            detailTr.className = `detail-row row-detail-${row.fine_id}`;
            detailTr.id = `detail-${row.fine_id}`;
            detailTr.innerHTML = `
                <td colspan="9">
                    <div class="detail-container">
                        <div class="detail-sections">
                            <!-- SMS text -->
                            <div class="detail-sms-box">
                                <div class="detail-sms-header">
                                    <span>Notification SMS</span>
                                    <span>To: ${row.phone_number_simulated}</span>
                                </div>
                                <div class="detail-sms-body">
                                    ${row.message_text}
                                </div>
                            </div>
                            <!-- Violations history -->
                            <div class="detail-history-box">
                                <div class="detail-history-title">Violation History Context</div>
                                <div style="max-height: 150px; overflow-y: auto; border: 1px solid var(--border-color);">
                                    <table class="history-table">
                                        <thead>
                                            <tr>
                                                <th>Violation ID</th>
                                                <th>Timestamp</th>
                                                <th>Junction</th>
                                                <th>Address Location</th>
                                                <th>Types</th>
                                            </tr>
                                        </thead>
                                        <tbody class="history-table-body-${row.fine_id}">
                                            <tr>
                                                <td colspan="5" class="ledger-placeholder" style="text-align: center; padding: 12px; font-size: 11px;">Loading vehicle history...</td>
                                            </tr>
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        </div>
                    </div>
                </td>
            `;

            // Row click event to expand accordion (avoid clicking on inputs/buttons/links)
            tr.addEventListener('click', (e) => {
                if (e.target.tagName === 'BUTTON' || e.target.classList.contains('link-mark-paid')) {
                    return;
                }
                const isExpanded = tr.classList.contains('expanded');
                // Close other expanded rows
                document.querySelectorAll('.fine-row.expanded').forEach(el => {
                    if (el !== tr) {
                        el.classList.remove('expanded');
                        const oid = el.getAttribute('data-id');
                        document.querySelector(`.row-detail-${oid}`).classList.remove('active');
                    }
                });

                if (isExpanded) {
                    tr.classList.remove('expanded');
                    detailTr.classList.remove('active');
                } else {
                    tr.classList.add('expanded');
                    detailTr.classList.add('active');
                    loadHistoryDetails(row.vehicle_number, row.fine_id);
                }
            });

            tbody.appendChild(tr);
            tbody.appendChild(detailTr);
        });

        // Add action button handlers
        attachActionListeners();
    }

    function attachActionListeners() {
        // Mark Paid
        document.querySelectorAll('.link-mark-paid').forEach(link => {
            link.addEventListener('click', async (e) => {
                e.stopPropagation();
                const fid = link.getAttribute('data-id');
                
                try {
                    const res = await fetch(`${API_BASE}/fines/${fid}/mark-paid`, {
                        method: 'POST',
                        headers: {
                            'Authorization': `Bearer ${sessionToken}`
                        }
                    });

                    if (res.status === 401) {
                        sessionStorage.clear();
                        window.location.replace('login.html');
                        return;
                    }

                    const data = await res.json();
                    if (!res.ok) throw new Error(data.detail || 'Payment update failed');

                    // Update local list state
                    const index = finesList.findIndex(x => x.fine_id == fid);
                    if (index !== -1) {
                        finesList[index].status = 'paid';
                        computeSummaryMetrics(finesList);
                    }

                    // Update UI elements in place
                    const statusPill = document.querySelector(`.pill-status-${fid}`);
                    if (statusPill) {
                        statusPill.textContent = 'Paid';
                        statusPill.className = 'status-pill paid';
                    }

                    const actionsDiv = document.querySelector(`.actions-cell-${fid}`);
                    if (actionsDiv) {
                        actionsDiv.parentElement.innerHTML = `<span class="text-muted text-sm" style="font-size: 12px; font-weight: 500;">Closed</span>`;
                    }
                    showToast('Fine marked as paid successfully.', 'Payment Received', 'success');
                } catch (err) {
                    showToast(err.message, 'Error', 'error');
                }
            });
        });
    }

    // Load vehicle details history dynamically
    async function loadHistoryDetails(vehicleNumber, fineId) {
        const historyTbody = document.querySelector(`.history-table-body-${fineId}`);
        if (!historyTbody) return;

        // Cache hit
        if (loadedHistories[vehicleNumber]) {
            renderHistoryRows(loadedHistories[vehicleNumber], historyTbody);
            return;
        }

        try {
            const res = await fetch(`${API_BASE}/fines/${vehicleNumber}/history`, {
                headers: {
                    'Authorization': `Bearer ${sessionToken}`
                }
            });

            if (!res.ok) throw new Error('History load failed');
            const data = await res.json();

            loadedHistories[vehicleNumber] = data;
            renderHistoryRows(data, historyTbody);
        } catch (err) {
            console.error('History load failed:', err);
            historyTbody.innerHTML = `<tr><td colspan="5" class="ledger-placeholder text-danger" style="font-size: 11px;">Failed to load history: ${err.message}</td></tr>`;
        }
    }

    function renderHistoryRows(history, tbody) {
        if (!history || history.length === 0) {
            tbody.innerHTML = `<tr><td colspan="5" class="ledger-placeholder" style="font-size: 11px; text-align: center;">No history logs found.</td></tr>`;
            return;
        }

        tbody.innerHTML = history.map(row => `
            <tr>
                <td style="font-family: monospace;">${row.id}</td>
                <td>${formatDate(row.created_datetime)}</td>
                <td>${row.junction_name}</td>
                <td style="font-size: 11px; max-width: 250px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${row.location}">${row.location}</td>
                <td style="font-size: 11px; font-weight: 600; color: var(--primary-color);">${row.violation_type.join(', ')}</td>
            </tr>
        `).join('');
    }

    // Trigger SQLite scanning
    async function triggerScan() {
        const scanBtn = document.getElementById('btn-scan-offenders');
        scanBtn.disabled = true;
        scanBtn.textContent = 'Scanning Database...';

        try {
            const res = await fetch(`${API_BASE}/fines/generate`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${sessionToken}`
                }
            });

            if (res.status === 401) {
                sessionStorage.clear();
                window.location.replace('login.html');
                return;
            }

            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Scan failed');

            showToast(`Scan complete. New fines: ${data.new_records}, Updated: ${data.updated_records}.`, 'Scan Success', 'success');
            loadFines();
        } catch (err) {
            showToast(err.message, 'Scan Error', 'error');
        } finally {
            scanBtn.disabled = false;
            scanBtn.textContent = 'Scan for Repeat Offenders';
        }
    }

    // Trigger bulk SMS warnings
    async function triggerBulkReminders() {
        const statusFilter = document.getElementById('filter-status').value;
        
        // Filter the dataset to get all unpaid entries in the current visible list
        let targetFines = finesList.filter(item => {
            if (statusFilter === 'all') return item.status === 'unpaid';
            return item.status === statusFilter && item.status === 'unpaid';
        });

        if (targetFines.length === 0) {
            showToast('No eligible unpaid offenders found to send reminders to.', 'Bulk Reminders', 'info');
            return;
        }

        const bulkBtn = document.getElementById('btn-bulk-reminders');
        bulkBtn.disabled = true;
        bulkBtn.textContent = 'Sending Reminders...';

        const targetIds = targetFines.map(x => x.fine_id);

        try {
            const res = await fetch(`${API_BASE}/fines/send-reminders`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${sessionToken}`
                },
                body: JSON.stringify({ fine_ids: targetIds })
            });

            if (res.status === 401) {
                sessionStorage.clear();
                window.location.replace('login.html');
                return;
            }

            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Bulk reminder request failed');

            showToast(data.message, 'Bulk Reminders Sent', 'success');

            // Update local state list so filters/updates render properly in place
            targetIds.forEach(fid => {
                const idx = finesList.findIndex(x => x.fine_id == fid);
                if (idx !== -1) {
                    finesList[idx].reminder_count += 1;
                    finesList[idx].last_reminder_at = data.last_reminder_at;
                }
            });

            // Re-render table in place
            renderTable();
        } catch (err) {
            showToast(err.message, 'Bulk Reminders Error', 'error');
        } finally {
            bulkBtn.disabled = false;
            bulkBtn.textContent = 'Bulk Send Reminders';
        }
    }


    // Formats datetime string
    function formatDate(isoStr) {
        if (!isoStr) return '';
        try {
            const d = new Date(isoStr);
            return d.toLocaleString([], { year: 'numeric', month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' });
        } catch (e) {
            return isoStr;
        }
    }

    // Show simulated toast message with dynamic title and type
    function showToast(text, title = 'Notification', type = 'info') {
        const toast = document.getElementById('sms-toast');
        const toastText = document.getElementById('sms-toast-text');
        if (!toast || !toastText) return;

        // Update title if exists
        const titleEl = toast.querySelector('strong');
        if (titleEl) {
            titleEl.textContent = title;
        }

        // Style based on type
        if (type === 'error') {
            toast.style.borderLeftColor = 'var(--primary-color)';
        } else if (type === 'success') {
            toast.style.borderLeftColor = '#2e7d32';
        } else {
            toast.style.borderLeftColor = '#3b82f6';
        }

        toastText.textContent = text;
        toast.style.display = 'block';

        if (toast.timeoutId) {
            clearTimeout(toast.timeoutId);
        }

        toast.timeoutId = setTimeout(() => {
            toast.style.display = 'none';
        }, 5000);
    }
})();
