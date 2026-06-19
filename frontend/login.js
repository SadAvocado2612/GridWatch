// login.js - Enforcer Login Controller
(function () {
    'use strict';

    const API_BASE = window.location.origin.includes('127.0.0.1') || window.location.origin.includes('localhost')
        ? (window.location.port === '8000' ? '/api' : 'http://localhost:8000/api')
        : '/api';

    document.addEventListener('DOMContentLoaded', () => {
        // If already logged in, redirect directly to analysis.html
        if (sessionStorage.getItem('session_token')) {
            window.location.replace('analysis.html');
            return;
        }

        const loginForm = document.getElementById('login-form');
        const loginBtn = document.getElementById('btn-login');
        const errorContainer = document.getElementById('error-container');

        if (loginForm && loginBtn) {
            loginBtn.addEventListener('click', async (e) => {
                e.preventDefault();
                
                const badgeId = document.getElementById('badge-id').value.trim();
                const password = document.getElementById('password').value;

                if (!badgeId || !password) {
                    showError('Please enter both Badge ID and Password.');
                    return;
                }

                loginBtn.textContent = 'Authenticating...';
                loginBtn.disabled = true;
                if (errorContainer) errorContainer.style.display = 'none';

                try {
                    const res = await fetch(`${API_BASE}/login`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({ badge_id: badgeId, password: password })
                    });

                    if (!res.ok) {
                        let errMsg = 'Authentication failed';
                        const contentType = res.headers.get('content-type');
                        if (contentType && contentType.includes('application/json')) {
                            try {
                                const errData = await res.json();
                                errMsg = errData.detail || errMsg;
                            } catch (e) {}
                        } else {
                            errMsg = `Connection Error (${res.status}): The backend API server could not be reached. Make sure your backend API is deployed and the API_URL environment variable is set in Netlify.`;
                        }
                        throw new Error(errMsg);
                    }

                    let data;
                    try {
                        data = await res.json();
                    } catch (e) {
                        throw new Error('The server returned an invalid response format.');
                    }
                    
                    // Store token & enforcer details in sessionStorage
                    sessionStorage.setItem('session_token', data.session_token);
                    sessionStorage.setItem('enforcer_name', data.name);
                    sessionStorage.setItem('enforcer_station', data.station);

                    // Redirect to analysis page
                    window.location.replace('analysis.html');
                } catch (err) {
                    showError(err.message);
                    loginBtn.textContent = 'Sign In';
                    loginBtn.disabled = false;
                }
            });
        }

        function showError(msg) {
            if (errorContainer) {
                errorContainer.textContent = msg;
                errorContainer.style.display = 'block';
            }
        }
    });
})();
