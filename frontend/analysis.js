// GridWatch Frontend Controller
// Session token validation check at the top
if (!sessionStorage.getItem('session_token')) {
    window.location.replace('login.html');
}

const API_BASE = window.location.origin.includes('127.0.0.1') || window.location.origin.includes('localhost')
    ? window.location.origin + '/api'
    : 'http://localhost:8000/api';

// Map & Layer State
let map;
let baseTileLayer;
let hotspotsLayerGroup;
let patrolLayerGroup;
let cameraLayerGroup;

// Data cache
let state = {
    hotspots: [],
    cameraRecs: [],
    markersMap: {} // key: cluster_id, value: leaflet circle marker
};

const unitColors = ['#a91d22', '#5a1818', '#d96b27', '#3d3d3d', '#8a3324'];

document.addEventListener('DOMContentLoaded', () => {
    initMap();
    initApp();
});

// Initialize Leaflet Map (Light theme, centered on Bengaluru)
function initMap() {
    const blrCenter = [12.9716, 77.5946];
    
    map = L.map('map', {
        zoomControl: true,
        fadeAnimation: true,
        markerZoomAnimation: true
    }).setView(blrCenter, 12);
    
    // CartoDB Positron (clean light-theme basemap)
    baseTileLayer = L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
        subdomains: 'abcd',
        maxZoom: 20
    }).addTo(map);
    
    // Layer Groups
    hotspotsLayerGroup = L.layerGroup().addTo(map);
    patrolLayerGroup = L.layerGroup().addTo(map);
    cameraLayerGroup = L.layerGroup().addTo(map);
}

function initApp() {
    setupNavigation();
    setupEventListeners();
    loadKPISummary();
    loadHotspots().then(() => {
        // Parse coordinate parameters if present
        const urlParams = new URLSearchParams(window.location.search);
        const lat = urlParams.get('lat');
        const lon = urlParams.get('lon');
        if (lat && lon) {
            const targetLatLng = [parseFloat(lat), parseFloat(lon)];
            map.setView(targetLatLng, 16);
            
            // Drop a temporary marker to highlight the newly reported violation location
            L.marker(targetLatLng, {
                icon: L.divIcon({
                    className: 'custom-div-icon smooth-marker',
                    html: `<div style="background-color: var(--primary-color); width: 16px; height: 16px; border-radius: 50%; border: 3px solid white; box-shadow: 0 0 6px rgba(0,0,0,0.5);"></div>`,
                    iconSize: [16, 16],
                    iconAnchor: [8, 8]
                })
            }).addTo(map).bindPopup("<b>New Manual Report Location</b>").openPopup();
        }
    });
    loadCameraRecommendations();
    loadPredictiveCalendar();
}

// Sidebar Tab switching
function setupNavigation() {
    const tabButtons = document.querySelectorAll('.tab-btn');
    const tabPanels = document.querySelectorAll('.tab-panel');
    
    tabButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetTab = btn.getAttribute('data-tab');
            
            tabButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            
            tabPanels.forEach(p => p.classList.remove('active'));
            document.getElementById(targetTab).classList.add('active');
            
            setTimeout(() => {
                map.invalidateSize();
            }, 100);
        });
    });
}

function setupEventListeners() {
    // Predict tab selectors
    const predictDay = document.getElementById('predict-day');
    const predictHour = document.getElementById('predict-hour');
    const predictHourVal = document.getElementById('predict-hour-val');
    
    if (predictDay && predictHour) {
        predictDay.addEventListener('change', () => loadPredictiveCalendar());
        predictHour.addEventListener('input', (e) => {
            const h = parseInt(e.target.value);
            predictHourVal.textContent = formatHour(h);
            loadPredictiveCalendar();
        });
    }
    
    // Patrol tab selectors & button
    const patrolHour = document.getElementById('patrol-hour');
    const patrolHourVal = document.getElementById('patrol-hour-val');
    const generatePatrolBtn = document.getElementById('btn-generate-routes');
    
    if (patrolHour) {
        patrolHour.addEventListener('input', (e) => {
            patrolHourVal.textContent = formatHour(parseInt(e.target.value));
        });
    }
    
    if (generatePatrolBtn) {
        generatePatrolBtn.addEventListener('click', () => generatePatrolPlan());
    }
    
    // Cameras Toggle Switch
    const toggleCameraLayer = document.getElementById('toggle-camera-layer');
    if (toggleCameraLayer) {
        toggleCameraLayer.addEventListener('change', (e) => {
            if (e.target.checked) {
                map.addLayer(cameraLayerGroup);
            } else {
                map.removeLayer(cameraLayerGroup);
            }
        });
    }

    // Generate Report Button
    const generateReportBtn = document.getElementById('btn-generate-report');
    if (generateReportBtn) {
        generateReportBtn.addEventListener('click', () => generateMonthlyReport());
    }
}

// Formats 24h int to "8 AM" or "12 PM"
function formatHour(h) {
    const ampm = h >= 12 ? 'PM' : 'AM';
    const displayHour = h % 12 === 0 ? 12 : h % 12;
    return `${displayHour} ${ampm}`;
}

// Fetch 4 KPI Cards
async function loadKPISummary() {
    try {
        const response = await fetch(`${API_BASE}/kpi-summary`, {
            headers: {
                'Authorization': `Bearer ${sessionStorage.getItem('session_token')}`
            }
        });
        if (response.status === 401) {
            sessionStorage.clear();
            window.location.replace('login.html');
            return;
        }
        if (!response.ok) throw new Error('KPI network error');
        const kpi = await response.json();
        
        animateCounter('kpi-total', kpi.total_violations_analyzed);
        animateCounter('kpi-hotspots', kpi.hotspots_above_threshold);
        animateCounter('kpi-delay', Math.round(kpi.estimated_daily_delay_saved_min));
        document.getElementById('kpi-backlog').textContent = `${kpi.backlog_reduction_pct.toFixed(1)}%`;
    } catch (err) {
        console.error('Error fetching KPI summary:', err);
    }
}

// Animate counting up for KPI values
function animateCounter(elementId, targetValue) {
    const el = document.getElementById(elementId);
    if (!el) return;
    
    const duration = 800;
    const start = performance.now();
    const startVal = 0;
    
    function step(now) {
        const elapsed = now - start;
        const progress = Math.min(elapsed / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
        const current = Math.round(startVal + (targetValue - startVal) * eased);
        el.textContent = current.toLocaleString();
        if (progress < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
}

// Hotspots Layer
async function loadHotspots() {
    try {
        const response = await fetch(`${API_BASE}/hotspots`, {
            headers: {
                'Authorization': `Bearer ${sessionStorage.getItem('session_token')}`
            }
        });
        if (response.status === 401) {
            sessionStorage.clear();
            window.location.replace('login.html');
            return;
        }
        if (!response.ok) throw new Error('Hotspots network error');
        const hotspots = await response.json();
        state.hotspots = hotspots;
        
        hotspotsLayerGroup.clearLayers();
        state.markersMap = {};
        
        hotspots.forEach(h => {
            if (!h.representative_lat || !h.representative_lon) return;
            
            const lat = h.representative_lat;
            const lon = h.representative_lon;
            const score = h.congestion_cost_score;
            
            // Radius scales with score
            const radius = 5 + (score * 0.22);
            
            // Yellow-to-red gradient based on score (0 to 100)
            const hue = Math.max(0, Math.min(60, (1 - (score / 100)) * 60)); // 60 (yellow) down to 0 (red)
            const color = `hsl(${hue}, 90%, 45%)`;
            
            // Opacity gradient: insignificant spots are highly transparent, significant ones are darker
            const opacity = 0.25 + (score / 100) * 0.65; // Ranges from 0.25 to 0.90
            
            const marker = L.circleMarker([lat, lon], {
                radius: radius,
                stroke: false, // No hard outline border
                fillColor: color,
                fillOpacity: opacity,
                className: 'smooth-marker'
            });
            
            const sparklineHtml = generateSparkline(h.hourly_distribution);
            
            marker.bindPopup(`
                <div class="popup-header">${h.junction_name}</div>
                <div class="popup-row">
                    <span class="popup-label">Police Station</span>
                    <span class="popup-value">${h.police_station || 'Unknown'}</span>
                </div>
                <div class="popup-row">
                    <span class="popup-label">Violations</span>
                    <span class="popup-value">${h.violation_count.toLocaleString()}</span>
                </div>
                <div class="popup-row">
                    <span class="popup-label">Peak Hour</span>
                    <span class="popup-value">${formatHour(h.peak_hour)}</span>
                </div>
                <div class="popup-row">
                    <span class="popup-label">Congestion Score</span>
                    <span class="popup-value" style="color: ${color}; font-weight: 700;">${score.toFixed(2)}</span>
                </div>
                <div class="popup-description">${h.description}</div>
                ${sparklineHtml}
                <div class="popup-simulate-btn-row">
                    <button class="btn btn-primary simulate-impact-btn" data-id="${h.cluster_id}">Simulate Impact</button>
                </div>
            `, {
                maxWidth: 250
            });
            
            marker.addTo(hotspotsLayerGroup);
            state.markersMap[h.cluster_id] = marker;
        });
    } catch (err) {
        console.error('Error fetching hotspots:', err);
    }
}

// Sparkline bar chart
function generateSparkline(distribution) {
    if (!distribution || distribution.length === 0) return '';
    const maxVal = Math.max(...distribution, 1);
    
    let barsHtml = '';
    distribution.forEach((val, hour) => {
        const heightPct = (val / maxVal) * 100;
        const isPeak = (hour >= 8 && hour <= 10) || (hour >= 18 && hour <= 20);
        const barColor = isPeak ? 'var(--primary-color)' : '#c4c4d0';
        
        barsHtml += `
            <div class="spark-bar-container" title="${hour}:00 - ${val} violations">
                <div class="spark-bar" style="height: ${heightPct}%; background-color: ${barColor};"></div>
            </div>
        `;
    });
    
    return `
        <div class="sparkline-container">
            <span class="sparkline-title">24h Distribution</span>
            <div class="sparkline-bars">${barsHtml}</div>
            <div class="sparkline-labels">
                <span>12 AM</span>
                <span>12 PM</span>
                <span>11 PM</span>
            </div>
        </div>
    `;
}

// Predictive Calendar
async function loadPredictiveCalendar() {
    const day = document.getElementById('predict-day').value;
    const hour = document.getElementById('predict-hour').value;
    const listContainer = document.getElementById('calendar-list');
    
    listContainer.innerHTML = `
        <div class="text-center py-4">
            <div class="loading-spinner"></div>
            <span class="text-muted-editorial text-sm">Querying predictive calendar...</span>
        </div>
    `;
    
    try {
        const response = await fetch(`${API_BASE}/predictive-calendar?day_of_week=${day}&hour=${hour}`, {
            headers: {
                'Authorization': `Bearer ${sessionStorage.getItem('session_token')}`
            }
        });
        if (response.status === 401) {
            sessionStorage.clear();
            window.location.replace('login.html');
            return;
        }
        if (!response.ok) throw new Error('Calendar fetch error');
        const data = await response.json();
        
        listContainer.innerHTML = '';
        if (data.length === 0) {
            listContainer.innerHTML = `
                <div class="ledger-placeholder">
                    No predictive targets active for ${day} at ${formatHour(parseInt(hour))}.
                </div>
            `;
            return;
        }
        
        const sorted = data.sort((a, b) => b.congestion_cost_score - a.congestion_cost_score);
        
        sorted.forEach(c => {
            const card = document.createElement('div');
            card.className = 'target-card';
            
            const hitRatePct = Math.round(c.recurrence_probability * 100);
            let badgeClass = 'low';
            if (hitRatePct >= 75) badgeClass = 'high';
            else if (hitRatePct >= 60) badgeClass = 'med';
            
            card.innerHTML = `
                <div class="card-title-row">
                    <span class="card-title">${c.junction_name}</span>
                    <span class="card-badge ${badgeClass}">${hitRatePct}% Hit</span>
                </div>
                <div class="card-desc">${c.recommended_action}</div>
                <div class="card-footer">
                    <span class="card-footer-item">Score: <strong>${c.congestion_cost_score.toFixed(1)}</strong></span>
                    <button class="btn-text show-marker-btn" data-id="${c.cluster_id}">Show on Map</button>
                </div>
            `;
            
            card.querySelector('.show-marker-btn').addEventListener('click', (e) => {
                const clusterId = e.target.getAttribute('data-id');
                showHotspotOnMap(clusterId);
            });
            
            listContainer.appendChild(card);
        });
    } catch (err) {
        console.error('Error loading calendar:', err);
        listContainer.innerHTML = `<div class="ledger-placeholder text-danger">Error loading calendar: ${err.message}</div>`;
    }
}

// Focus map on a hotspot
function showHotspotOnMap(clusterId) {
    const marker = state.markersMap[clusterId];
    if (marker) {
        map.setView(marker.getLatLng(), 15);
        marker.openPopup();
    } else {
        const h = state.hotspots.find(x => x.cluster_id === clusterId);
        if (h && h.representative_lat && h.representative_lon) {
            map.setView([h.representative_lat, h.representative_lon], 15);
        }
    }
}

// Patrol Route Generator
async function generatePatrolPlan() {
    const day = document.getElementById('patrol-day').value;
    const hour = document.getElementById('patrol-hour').value;
    const units = document.getElementById('patrol-units').value || '3';
    
    const listContainer = document.getElementById('routes-list');
    listContainer.innerHTML = `
        <div class="text-center py-4">
            <div class="loading-spinner"></div>
            <span class="text-muted-editorial text-sm">Solving route optimization...</span>
        </div>
    `;
    
    patrolLayerGroup.clearLayers();
    
    try {
        const response = await fetch(`${API_BASE}/patrol-plan?day_of_week=${day}&hour=${hour}&num_units=${units}`, {
            headers: {
                'Authorization': `Bearer ${sessionStorage.getItem('session_token')}`
            }
        });
        if (response.status === 401) {
            sessionStorage.clear();
            window.location.replace('login.html');
            return;
        }
        if (!response.ok) throw new Error('Patrol plan fetch error');
        const plan = await response.json();
        
        listContainer.innerHTML = '';
        const unitKeys = Object.keys(plan);
        
        if (unitKeys.length === 0) {
            listContainer.innerHTML = `
                <div class="ledger-placeholder">
                    No active targets for this hour. Route planner requires targets with &ge; 50% hit rate.
                </div>
            `;
            return;
        }
        
        let allCoordinates = [];
        
        unitKeys.forEach((unitKey, idx) => {
            const stops = plan[unitKey];
            if (stops.length === 0) return;
            
            const color = unitColors[idx % unitColors.length];
            const card = document.createElement('div');
            card.className = 'route-unit-card';
            
            let stopsHtml = '';
            let latlngs = [];
            
            stops.forEach((stop, sidx) => {
                const lat = stop.representative_lat;
                const lon = stop.representative_lon;
                
                if (lat == null || lon == null || isNaN(lat) || isNaN(lon)) {
                    console.warn(`Skipping stop with invalid coords: unit=${unitKey}, stop=${sidx}`);
                    return;
                }
                
                const markerLatLng = [lat, lon];
                latlngs.push(markerLatLng);
                allCoordinates.push(markerLatLng);
                
                const distMeters = (stop.distance_from_prev_km || 0) * 1000;
                const travelMins = stop.travel_time_mins || 0;
                
                stopsHtml += `
                    <li class="timeline-item">
                        <span class="timeline-bullet" style="border-color: ${color};"></span>
                        <div class="timeline-item-meta">
                            <span>Stop #${sidx + 1} &middot; ETA: ${stop.eta}</span>
                            <span>Score: ${stop.congestion_cost_score.toFixed(1)}</span>
                        </div>
                        <div class="timeline-item-title">${stop.junction_name}</div>
                        <div class="timeline-item-desc">
                            ${sidx > 0 ? `Travel: ${distMeters.toFixed(0)}m (${Math.round(travelMins)} min)` : 'Dispatch origin'}
                        </div>
                    </li>
                `;
                
                // Numbered marker on map
                L.marker(markerLatLng, {
                    icon: L.divIcon({
                        className: 'custom-div-icon',
                        html: `<div class="patrol-marker-pin" style="background-color: ${color};">${sidx + 1}</div>`,
                        iconSize: [24, 24],
                        iconAnchor: [12, 12]
                    })
                }).bindPopup(`
                    <div class="popup-header">Unit #${parseInt(unitKey) + 1} — Stop #${sidx + 1}</div>
                    <div class="popup-row"><span class="popup-label">Junction</span><span class="popup-value">${stop.junction_name}</span></div>
                    <div class="popup-row"><span class="popup-label">ETA</span><span class="popup-value">${stop.eta}</span></div>
                    <div class="popup-row"><span class="popup-label">Distance</span><span class="popup-value">${distMeters.toFixed(0)}m</span></div>
                    <div class="popup-row"><span class="popup-label">Priority</span><span class="popup-value">${stop.congestion_cost_score.toFixed(2)}</span></div>
                `).addTo(patrolLayerGroup);
            });
            
            // Polyline connecting stops
            if (latlngs.length > 1) {
                L.polyline(latlngs, {
                    color: color,
                    weight: 3,
                    opacity: 0.75,
                    dashArray: '6, 8'
                }).addTo(patrolLayerGroup);
            }
            
            card.innerHTML = `
                <div class="route-unit-header" style="background-color: rgba(${hexToRgb(color)}, 0.06); color: ${color};">
                    <span>Unit #${parseInt(unitKey) + 1}</span>
                    <span>${stops.length} checkpoints</span>
                </div>
                <div class="route-unit-body">
                    <ul class="timeline-list">${stopsHtml}</ul>
                </div>
            `;
            listContainer.appendChild(card);
        });
        
        if (allCoordinates.length > 0) {
            map.fitBounds(L.latLngBounds(allCoordinates), { padding: [50, 50] });
        }
        
    } catch (err) {
        console.error('Error generating patrol plan:', err);
        listContainer.innerHTML = `<div class="ledger-placeholder text-danger">Error: ${err.message}</div>`;
    }
}

// Convert Hex color to RGB
function hexToRgb(hex) {
    const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    if (!result) return '212, 43, 43';
    return `${parseInt(result[1], 16)}, ${parseInt(result[2], 16)}, ${parseInt(result[3], 16)}`;
}

// Camera Recommendations
async function loadCameraRecommendations() {
    const listContainer = document.getElementById('camera-recs-list');
    
    try {
        const response = await fetch(`${API_BASE}/camera-recommendations`, {
            headers: {
                'Authorization': `Bearer ${sessionStorage.getItem('session_token')}`
            }
        });
        if (response.status === 401) {
            sessionStorage.clear();
            window.location.replace('login.html');
            return;
        }
        if (!response.ok) throw new Error('Camera Recommendations network error');
        const data = await response.json();
        
        state.cameraRecs = data;
        cameraLayerGroup.clearLayers();
        listContainer.innerHTML = '';
        
        if (data.length === 0) {
            listContainer.innerHTML = '<div class="ledger-placeholder">No coverage gaps detected.</div>';
            return;
        }
        
        data.forEach((r, idx) => {
            const card = document.createElement('div');
            card.className = 'target-card';
            card.innerHTML = `
                <div class="card-title-row">
                    <span class="card-title">Gap #${idx + 1}</span>
                    <span class="card-badge high">Dist: ${Math.round(r.distance_to_nearest_existing_device_m)}m</span>
                </div>
                <div class="card-desc"><strong>${r.junction_name}</strong>: ${r.justification}</div>
                <div class="card-footer">
                    <span class="card-footer-item">Score: <strong>${r.congestion_cost_score.toFixed(1)}</strong></span>
                    <button class="btn-text focus-camera-btn" data-lat="${r.lat}" data-lon="${r.lon}">Focus Site</button>
                </div>
            `;
            
            card.querySelector('.focus-camera-btn').addEventListener('click', (e) => {
                const lat = parseFloat(e.target.getAttribute('data-lat'));
                const lon = parseFloat(e.target.getAttribute('data-lon'));
                map.setView([lat, lon], 16);
            });
            
            listContainer.appendChild(card);
            
            // Camera marker on map
            const camMarker = L.marker([r.lat, r.lon], {
                icon: L.divIcon({
                    className: 'custom-div-icon',
                    html: `<div class="camera-marker-pin">C</div>`,
                    iconSize: [26, 26],
                    iconAnchor: [13, 13]
                })
            }).bindPopup(`
                <div class="popup-header">Suggested Camera #${idx + 1}</div>
                <div class="popup-row"><span class="popup-label">Junction</span><span class="popup-value">${r.junction_name}</span></div>
                <div class="popup-row"><span class="popup-label">Impact Score</span><span class="popup-value">${r.congestion_cost_score.toFixed(2)}</span></div>
                <div class="popup-row"><span class="popup-label">Nearest Device</span><span class="popup-value">${Math.round(r.distance_to_nearest_existing_device_m)}m</span></div>
                <div class="popup-description">${r.justification}</div>
            `);
            camMarker.addTo(cameraLayerGroup);
        });
    } catch (err) {
        console.error('Error loading camera recs:', err);
        listContainer.innerHTML = `<div class="ledger-placeholder text-danger">Error: ${err.message}</div>`;
    }
}

// Delegate popup simulate click
document.addEventListener('click', (e) => {
    if (e.target && e.target.classList.contains('simulate-impact-btn')) {
        const clusterId = e.target.getAttribute('data-id');
        triggerSimulation(clusterId);
    }
});

function triggerSimulation(clusterId) {
    const h = state.hotspots.find(x => x.cluster_id === clusterId);
    if (!h) return;
    
    const simTabBtn = document.querySelector('.tab-btn[data-tab="tab-simulate"]');
    if (simTabBtn) {
        simTabBtn.click();
    }
    
    if (window.startSimulation) {
        window.startSimulation(h);
    }
}

// Open printable monthly-report.html in a new tab
function generateMonthlyReport() {
    const monthSelect = document.getElementById('report-month');
    const yearSelect = document.getElementById('report-year');
    
    if (!monthSelect || !yearSelect) return;
    
    const month = monthSelect.value;
    const year = yearSelect.value;
    
    // Open printable page in a new tab
    const url = `monthly-report.html?year=${year}&month=${month}`;
    window.open(url, '_blank');
}

// Show toast message
function showToast(text, title = 'Notification', type = 'info') {
    let toast = document.getElementById('app-toast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'app-toast';
        toast.className = 'toast';
        toast.innerHTML = `
            <div style="font-weight: bold; margin-bottom: 4px;" class="toast-title">Notification</div>
            <span class="toast-text"></span>
        `;
        document.body.appendChild(toast);
    }
    
    const titleEl = toast.querySelector('.toast-title');
    const textEl = toast.querySelector('.toast-text');
    
    if (titleEl) titleEl.textContent = title;
    if (textEl) textEl.textContent = text;
    
    // Style based on type
    if (type === 'error') {
        toast.style.borderLeftColor = 'var(--primary-color, #a91d22)';
    } else if (type === 'success') {
        toast.style.borderLeftColor = '#2e7d32';
    } else {
        toast.style.borderLeftColor = '#3b82f6';
    }
    
    toast.style.display = 'block';
    
    // Hide after 4 seconds
    if (window.toastTimeout) {
        clearTimeout(window.toastTimeout);
    }
    window.toastTimeout = setTimeout(() => {
        toast.style.display = 'none';
    }, 4000);
}
