// report.js - Manual Violation Logging Controller
(function () {
    'use strict';

    // Session token guard
    const sessionToken = sessionStorage.getItem('session_token');
    if (!sessionToken) {
        window.location.replace('login.html');
        return;
    }

    const API_BASE = window.location.origin.includes('127.0.0.1') || window.location.origin.includes('localhost')
        ? (window.location.port === '8000' ? '/api' : 'http://localhost:8000/api')
        : '/api';

    let map;
    let marker;

    document.addEventListener('DOMContentLoaded', () => {
        initFormMap();
        loadViolationTypes();
        setupFormHandlers();
    });

    // Initialize the mini locator map
    function initFormMap() {
        const blrCenter = [12.9716, 77.5946];
        map = L.map('report-map', {
            zoomControl: true,
            attributionControl: false
        }).setView(blrCenter, 13);

        L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
            maxZoom: 20
        }).addTo(map);

        // Click event listener to drop pin
        map.on('click', (e) => {
            const lat = e.latlng.lat;
            const lon = e.latlng.lng;

            document.getElementById('latitude').value = lat.toFixed(7);
            document.getElementById('longitude').value = lon.toFixed(7);

            if (marker) {
                marker.setLatLng(e.latlng);
            } else {
                marker = L.marker(e.latlng, {
                    icon: L.divIcon({
                        className: 'custom-div-icon smooth-marker',
                        html: `<div style="background-color: var(--primary-color); width: 14px; height: 14px; border-radius: 50%; border: 2px solid white; box-shadow: 0 0 4px rgba(0,0,0,0.4);"></div>`,
                        iconSize: [14, 14],
                        iconAnchor: [7, 7]
                    })
                }).addTo(map);
            }
        });
    }

    // Dynamic categories fetching
    async function loadViolationTypes() {
        const container = document.getElementById('violation-types-container');
        try {
            const res = await fetch(`${API_BASE}/violation-types`, {
                headers: {
                    'Authorization': `Bearer ${sessionToken}`
                }
            });

            if (res.status === 401) {
                sessionStorage.clear();
                window.location.replace('login.html');
                return;
            }

            if (!res.ok) throw new Error('Failed to load categories');
            const data = await res.json();

            container.innerHTML = '';
            if (data.length === 0) {
                container.innerHTML = '<span style="font-size: 12px; color: var(--text-muted); padding: 8px;">No violation types available.</span>';
                return;
            }

            data.forEach((tag, idx) => {
                const label = document.createElement('label');
                label.className = 'checkbox-item';
                label.innerHTML = `
                    <input type="checkbox" name="violation-type" value="${tag}">
                    <span>${tag}</span>
                `;
                container.appendChild(label);
            });
        } catch (err) {
            console.error('Error loading violation types:', err);
            container.innerHTML = `<span style="font-size: 12px; color: var(--primary-color); padding: 8px;">Error: ${err.message}</span>`;
        }
    }

    // Handlers setup
    function setupFormHandlers() {
        const fileInput = document.getElementById('photo-upload');
        const fileLabel = document.getElementById('file-label');
        const form = document.getElementById('violation-form');
        const submitBtn = document.getElementById('btn-submit-violation');
        const successBanner = document.getElementById('success-banner');
        const errorBanner = document.getElementById('error-banner');
        const viewLink = document.getElementById('view-analysis-link');

        // File label changes on select
        if (fileInput && fileLabel) {
            fileInput.addEventListener('change', (e) => {
                if (fileInput.files.length > 0) {
                    fileLabel.textContent = fileInput.files[0].name;
                } else {
                    fileLabel.textContent = 'Choose image file...';
                }
            });
        }

        // Form submission
        if (form && submitBtn) {
            submitBtn.addEventListener('click', async (e) => {
                e.preventDefault();

                // Clear previous states
                successBanner.style.display = 'none';
                errorBanner.style.display = 'none';

                const latStr = document.getElementById('latitude').value;
                const lonStr = document.getElementById('longitude').value;
                const vehicleNo = document.getElementById('vehicle-number').value.trim();
                const vehicleType = document.getElementById('vehicle-type').value;
                const location = document.getElementById('location').value.trim();
                const junction = document.getElementById('junction-name').value.trim();
                const desc = document.getElementById('description').value.trim();
                const photoFile = fileInput && fileInput.files.length > 0 ? fileInput.files[0].name : null;

                // Violation checkboxes checked state
                const checkedBoxes = Array.from(document.querySelectorAll('input[name="violation-type"]:checked'))
                    .map(el => el.value);

                // Client-side validations
                if (!latStr || !lonStr) {
                    showError('Please tap on the map to pinpoint coordinates.');
                    return;
                }
                if (!vehicleNo) {
                    showError('Please enter a vehicle registration number.');
                    return;
                }
                if (!vehicleType) {
                    showError('Please select a vehicle type.');
                    return;
                }
                if (checkedBoxes.length === 0) {
                    showError('Please select at least one violation category.');
                    return;
                }

                // Loading state
                submitBtn.disabled = true;
                submitBtn.textContent = 'Filing Report & Recomputing Analysis...';

                const payload = {
                    latitude: parseFloat(latStr),
                    longitude: parseFloat(lonStr),
                    location: location || "Unknown",
                    vehicle_number: vehicleNo,
                    vehicle_type: vehicleType,
                    violation_types: checkedBoxes,
                    description: desc || "",
                    junction_name: junction || "No Junction",
                    photo_filename: photoFile
                };

                try {
                    const response = await fetch(`${API_BASE}/report-violation`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': `Bearer ${sessionToken}`
                        },
                        body: JSON.stringify(payload)
                    });

                    if (response.status === 401) {
                        sessionStorage.clear();
                        window.location.replace('login.html');
                        return;
                    }

                    const result = await response.json();
                    if (!response.ok) {
                        throw new Error(result.detail || 'Failed to file report');
                    }

                    // Show success
                    successBanner.style.display = 'block';
                    viewLink.setAttribute('href', `analysis.html?lat=${payload.latitude}&lon=${payload.longitude}`);
                    
                    // Reset form fields
                    form.reset();
                    if (marker) {
                        map.removeLayer(marker);
                        marker = null;
                    }
                    if (fileLabel) {
                        fileLabel.textContent = 'Choose image file...';
                    }

                    // Reset map view
                    map.setView([12.9716, 77.5946], 13);
                    window.scrollTo({ top: 0, behavior: 'smooth' });

                } catch (err) {
                    showError(err.message);
                } finally {
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Submit Infraction Report';
                }
            });
        }

        function showError(msg) {
            errorBanner.textContent = msg;
            errorBanner.style.display = 'block';
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }
    }
})();
