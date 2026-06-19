// nav.js - Shared Navigation Component for GridWatch
(function () {
    'use strict';

    const API_BASE = window.location.origin.includes('127.0.0.1') || window.location.origin.includes('localhost')
        ? (window.location.port === '8000' ? '/api' : 'http://localhost:8000/api')
        : '/api';

    function injectNavbar() {
        const container = document.getElementById('app-nav');
        if (!container) return;

        const name = sessionStorage.getItem('enforcer_name');
        const station = sessionStorage.getItem('enforcer_station');
        const token = sessionStorage.getItem('session_token');

        const userInfoHtml = name && station
            ? `<span class="nav-user-info" style="font-size: 12px; font-weight: 500; color: var(--text-secondary); margin-right: 16px;">Logged in as ${name}, ${station}</span>`
            : '';

        container.innerHTML = `
            <nav class="app-navbar">
                <div class="nav-brand">
                    <div class="logo-accent"></div>
                    <div class="brand-text">
                        <span class="brand-title">GridWatch</span>
                        <span class="brand-subtitle">Municipal Audit</span>
                    </div>
                </div>
                <div class="nav-menu">
                    <a href="analysis.html" class="nav-link" id="nav-link-analysis">Analysis</a>
                    <a href="report.html" class="nav-link" id="nav-link-report">Report Violation</a>
                    <a href="fines.html" class="nav-link" id="nav-link-fines">Fines</a>
                </div>
                <div class="nav-actions">
                    ${token ? userInfoHtml : ''}
                    <button class="btn-logout" id="btn-logout">Log out</button>
                </div>
            </nav>
        `;

        // Highlight active page using current path
        const path = window.location.pathname;
        const page = path.substring(path.lastIndexOf('/') + 1) || 'analysis.html';

        if (page.includes('analysis')) {
            const link = document.getElementById('nav-link-analysis');
            if (link) link.classList.add('active');
        } else if (page.includes('report')) {
            const link = document.getElementById('nav-link-report');
            if (link) link.classList.add('active');
        } else if (page.includes('fines')) {
            const link = document.getElementById('nav-link-fines');
            if (link) link.classList.add('active');
        } else {
            // Default fallback if path resolves to root index.html or analysis page
            const link = document.getElementById('nav-link-analysis');
            if (link) link.classList.add('active');
        }

        // Add event listener for logout button
        const logoutBtn = document.getElementById('btn-logout');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', async () => {
                const sessionToken = sessionStorage.getItem('session_token');
                if (sessionToken) {
                    try {
                        await fetch(`${API_BASE}/logout`, {
                            method: 'POST',
                            headers: {
                                'Authorization': `Bearer ${sessionToken}`
                            }
                        });
                    } catch (e) {
                        console.error('Server logout failed:', e);
                    }
                }
                // Clear enforcer details and redirect to login page
                sessionStorage.removeItem('session_token');
                sessionStorage.removeItem('enforcer_name');
                sessionStorage.removeItem('enforcer_station');
                window.location.replace('login.html');
            });
        }
    }

    // Run injection on DOM load or immediately if already loaded
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', injectNavbar);
    } else {
        injectNavbar();
    }
})();
