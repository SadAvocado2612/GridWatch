// GridWatch Monthly Report Controller

// 1. Session verification
const sessionToken = sessionStorage.getItem('session_token');
if (!sessionToken) {
    window.location.replace('login.html');
}

const API_BASE = window.location.origin.includes('127.0.0.1') || window.location.origin.includes('localhost')
    ? window.location.origin + '/api'
    : 'http://localhost:8000/api';

document.addEventListener('DOMContentLoaded', () => {
    loadReportData();
});

async function loadReportData() {
    // 2. Extract year and month parameters
    const urlParams = new URLSearchParams(window.location.search);
    const year = parseInt(urlParams.get('year')) || 2024;
    const month = parseInt(urlParams.get('month')) || 3;
    
    try {
        // 3. Fetch monthly statistics
        const response = await fetch(`${API_BASE}/reports/monthly-data?year=${year}&month=${month}`, {
            headers: {
                'Authorization': `Bearer ${sessionToken}`
            }
        });
        
        if (response.status === 401) {
            sessionStorage.clear();
            window.location.replace('login.html');
            return;
        }
        
        if (!response.ok) {
            throw new Error(`API returned status ${response.status}`);
        }
        
        const data = await response.json();
        renderReport(data);
        
    } catch (err) {
        console.error('Error loading report data:', err);
        document.body.innerHTML = `
            <div style="padding: 40px; text-align: center; font-family: sans-serif; color: #a91d22;">
                <h2>Failed to Load Report Data</h2>
                <p>${err.message}</p>
                <button onclick="window.close()" style="margin-top:20px; padding:10px 20px; cursor:pointer; background:#1e293b; color:#fff; border:none;">Close Window</button>
            </div>
        `;
    }
}

function renderReport(data) {
    // Cover details
    document.getElementById('report-cover-period').textContent = `${data.month_name} ${data.year}`;
    document.getElementById('report-generation-time').innerHTML = `
        Generated: ${new Date().toLocaleDateString('en-IN', { year: 'numeric', month: 'long', day: 'numeric' })}<br>
        Auditor Badge: ${sessionStorage.getItem('badge_id') || 'BTP-SYSTEM'}
    `;
    
    // 1. Render KPIs
    // Violations Analyzed
    document.getElementById('val-total-violations').textContent = data.total_violations.toLocaleString('en-IN');
    const chgV = data.pct_change_violations;
    const vChangeEl = document.getElementById('change-violations');
    if (chgV > 0) {
        vChangeEl.innerHTML = `<span style="color:#c62828;">▲ ${chgV.toFixed(1)}%</span> vs prev. month`;
    } else if (chgV < 0) {
        vChangeEl.innerHTML = `<span style="color:#2e7d32;">▼ ${Math.abs(chgV).toFixed(1)}%</span> vs prev. month`;
    } else {
        vChangeEl.innerHTML = `<span>0.0%</span> vs prev. month`;
    }

    // Validation Approval Rate
    const appRate = data.validation_approval_rate * 100;
    document.getElementById('val-approval-rate').textContent = `${appRate.toFixed(1)}%`;
    const chgA = data.pct_change_approval_rate || data.pct_change_approval || 0;
    const aChangeEl = document.getElementById('change-approval');
    if (chgA > 0) {
        aChangeEl.innerHTML = `<span style="color:#2e7d32;">▲ ${chgA.toFixed(1)}%</span> vs prev. month`;
    } else if (chgA < 0) {
        aChangeEl.innerHTML = `<span style="color:#c62828;">▼ ${Math.abs(chgA).toFixed(1)}%</span> vs prev. month`;
    } else {
        aChangeEl.innerHTML = `<span>0.0%</span> vs prev. month`;
    }

    // Outstanding and Collected Fines
    const fSum = data.fines_summary;
    document.getElementById('val-outstanding-fines').textContent = `₹${fSum.total_outstanding.toLocaleString('en-IN')}`;
    document.getElementById('val-collected-fines').textContent = `₹${fSum.total_collected.toLocaleString('en-IN')}`;

    // 2. Generate and Render dynamic takeaways
    // KPI Takeaway
    const kpiTakeawayText = `Violations analyzed for ${data.month_name} ${data.year} totaled ${data.total_violations.toLocaleString('en-IN')} cases, presenting a ${chgV >= 0 ? 'growth' : 'reduction'} of ${Math.abs(chgV).toFixed(1)}% against the prior baseline. The ticketing validation approval rate ended at ${appRate.toFixed(1)}%, signaling ${chgA >= 0 ? 'an improvement' : 'a correction'} in automated and manual enforcer accuracy. Total fines issued was ₹${fSum.total_fine_amount.toLocaleString('en-IN')}.`;
    document.getElementById('kpi-takeaway').innerHTML = `<div class="takeaway-label">Enforcement Summary Outlook</div>${kpiTakeawayText}`;

    // Daily Trend Takeaway
    const dailyCounts = Object.values(data.daily_violation_counts);
    const maxDaily = dailyCounts.length > 0 ? Math.max(...dailyCounts) : 0;
    const minDaily = dailyCounts.length > 0 ? Math.min(...dailyCounts) : 0;
    const avgDaily = dailyCounts.length > 0 ? Math.round(dailyCounts.reduce((a,b)=>a+b, 0) / dailyCounts.length) : 0;
    const dailyTakeawayText = `Activity monitoring recorded an average of ${avgDaily} violations per day, peaking at ${maxDaily} incidents. The minimum daily volume was ${minDaily} incidents, corresponding with lower enforcement hours or weekends. Scheduled patrol routes align with these active cycles.`;
    document.getElementById('daily-takeaway').innerHTML = `<div class="takeaway-label">Daily Takeaway Outlook</div>${dailyTakeawayText}`;

    // Vehicle Breakdown Takeaway
    const vehTypes = Object.keys(data.violations_by_vehicle_type);
    let topVehicle = 'N/A';
    let topVehicleCount = 0;
    let topVehiclePct = 0;
    if (vehTypes.length > 0) {
        // find top vehicle
        const sortedVehs = Object.entries(data.violations_by_vehicle_type).sort((a,b) => b[1] - a[1]);
        topVehicle = sortedVehs[0][0];
        topVehicleCount = sortedVehs[0][1];
        topVehiclePct = ((topVehicleCount / data.total_violations) * 100).toFixed(1);
    }
    const vehicleTakeawayText = `Vehicle classification isolations reveal that ${topVehicle} counts constituted the largest single share of offenses with ${topVehicleCount.toLocaleString('en-IN')} violations (${topVehiclePct}% of the month's total). Targeted enforcement of this segment remains a priority.`;
    document.getElementById('vehicle-takeaway').innerHTML = `<div class="takeaway-label">Vehicle Analysis Outlook</div>${vehicleTakeawayText}`;

    // Hourly Distribution Takeaway
    const hourCounts = Object.values(data.violations_by_hour_of_day);
    let peakHour = 0;
    let peakHourCount = 0;
    if (hourCounts.length > 0) {
        peakHour = Object.entries(data.violations_by_hour_of_day).sort((a,b) => b[1] - a[1])[0][0];
        peakHourCount = Math.max(...hourCounts);
    }
    const peakHour12h = formatHour(parseInt(peakHour));
    const hourlyTakeawayText = `Diurnal variations confirm high activity starting at ${peakHour12h} with ${peakHourCount.toLocaleString('en-IN')} offenses. Traffic congestion surges during early morning business operations and mid-afternoon drop-off intervals.`;
    document.getElementById('hourly-takeaway').innerHTML = `<div class="takeaway-label">Hourly Takeaway Outlook</div>${hourlyTakeawayText}`;

    // Hotspot Takeaway
    let topJunctionName = 'N/A';
    let topJunctionCount = 0;
    if (data.top_10_hotspots.length > 0) {
        topJunctionName = data.top_10_hotspots[0].junction_name;
        topJunctionCount = data.top_10_hotspots[0].violation_count;
    }
    const hotspotTakeawayText = `Geospatial clustering indicates that ${topJunctionName} was the highest congestion hotspot, logging ${topJunctionCount.toLocaleString('en-IN')} violations. Restructuring roadway access or adding camera surveillance at this junction is recommended.`;
    document.getElementById('hotspots-takeaway').innerHTML = `<div class="takeaway-label">Hotspot Density Outlook</div>${hotspotTakeawayText}`;

    // 3. Render Chart.js charts
    // Chart 1: Daily Trend
    const dailyDays = Object.keys(data.daily_violation_counts).map(d => d.split('-')[2]); // just day number
    const dailyValues = Object.values(data.daily_violation_counts);
    new Chart(document.getElementById('chart-daily-violations').getContext('2d'), {
        type: 'line',
        data: {
            labels: dailyDays,
            datasets: [{
                label: 'Violations',
                data: dailyValues,
                borderColor: '#a91d22',
                backgroundColor: 'rgba(169, 29, 34, 0.05)',
                borderWidth: 2,
                fill: true,
                tension: 0.1,
                pointRadius: 2
            }]
        },
        options: {
            animation: false,
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                y: { grid: { color: '#f3f4f6' }, ticks: { font: { size: 9 } } },
                x: { grid: { display: false }, ticks: { font: { size: 9 } } }
            }
        }
    });

    // Chart 2: Vehicle Breakdown
    const sortedVehicles = Object.entries(data.violations_by_vehicle_type)
        .sort((a,b) => b[1] - a[1])
        .slice(0, 7);
    const vehicleLabels = sortedVehicles.map(v => v[0]);
    const vehicleValues = sortedVehicles.map(v => v[1]);
    new Chart(document.getElementById('chart-vehicle-breakdown').getContext('2d'), {
        type: 'bar',
        data: {
            labels: vehicleLabels,
            datasets: [{
                data: vehicleValues,
                backgroundColor: '#a91d22',
                barThickness: 20
            }]
        },
        options: {
            animation: false,
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                y: { grid: { color: '#f3f4f6' }, ticks: { font: { size: 9 } } },
                x: { grid: { display: false }, ticks: { font: { size: 9 } } }
            }
        }
    });

    // Chart 3: Hourly distribution
    const hours = Object.keys(data.violations_by_hour_of_day).map(h => formatHour(parseInt(h)));
    const hourValues = Object.values(data.violations_by_hour_of_day);
    new Chart(document.getElementById('chart-hourly-distribution').getContext('2d'), {
        type: 'bar',
        data: {
            labels: hours,
            datasets: [{
                data: hourValues,
                backgroundColor: '#a91d22',
                barThickness: 10
            }]
        },
        options: {
            animation: false,
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                y: { grid: { color: '#f3f4f6' }, ticks: { font: { size: 9 } } },
                x: { grid: { display: false }, ticks: { font: { size: 8 } } }
            }
        }
    });

    // Chart 4: Hotspots horizontal bar chart
    const top10 = data.top_10_hotspots.slice(0, 10);
    const hotspotLabels = top10.map(h => h.junction_name.length > 20 ? h.junction_name.substring(0, 20) + '...' : h.junction_name);
    const hotspotValues = top10.map(h => h.violation_count);
    new Chart(document.getElementById('chart-hotspots-density').getContext('2d'), {
        type: 'bar',
        data: {
            labels: hotspotLabels,
            datasets: [{
                data: hotspotValues,
                backgroundColor: '#a91d22',
                barThickness: 12
            }]
        },
        options: {
            indexAxis: 'y',
            animation: false,
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { grid: { color: '#f3f4f6' }, ticks: { font: { size: 9 } } },
                y: { grid: { display: false }, ticks: { font: { size: 9 } } }
            }
        }
    });

    // 4. Populate Tables
    // Hotspots table
    const hotspotsBody = document.getElementById('table-hotspots-body');
    hotspotsBody.innerHTML = '';
    if (data.top_10_hotspots.length === 0) {
        hotspotsBody.innerHTML = '<tr><td colspan="4" style="text-align:center;">No hotspot violations logged this month.</td></tr>';
    } else {
        data.top_10_hotspots.forEach(item => {
            const costStr = item.daily_cost_inr !== null ? `₹${item.daily_cost_inr.toLocaleString('en-IN')}` : 'N/A';
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><strong>${item.junction_name}</strong></td>
                <td class="num-cell">${item.violation_count.toLocaleString('en-IN')}</td>
                <td class="num-cell">${item.congestion_cost_score.toFixed(1)}</td>
                <td class="num-cell">${costStr}</td>
            `;
            hotspotsBody.appendChild(tr);
        });
    }

    // Fines summary table
    const finesBody = document.getElementById('table-fines-body');
    finesBody.innerHTML = `
        <tr>
            <td>Total Repeat Offenders Flagged (>5 violations)</td>
            <td class="num-cell"><strong>${fSum.new_repeat_offenders.toLocaleString('en-IN')}</strong></td>
        </tr>
        <tr>
            <td>Total Fine Amounts Issued</td>
            <td class="num-cell"><strong>₹${fSum.total_fine_amount.toLocaleString('en-IN')}</strong></td>
        </tr>
        <tr>
            <td>Collected Balance (Fines Paid)</td>
            <td class="num-cell" style="color: #2e7d32;"><strong>₹${fSum.total_collected.toLocaleString('en-IN')}</strong></td>
        </tr>
        <tr>
            <td>Outstanding Balance (Fines Unpaid)</td>
            <td class="num-cell" style="color: #c62828;"><strong>₹${fSum.total_outstanding.toLocaleString('en-IN')}</strong></td>
        </tr>
    `;

    // 5. Recommended Focus Next Month list
    const recsList = document.getElementById('recommendations-list');
    recsList.innerHTML = '';
    if (data.recommended_focus_next_month.length === 0) {
        recsList.innerHTML = '<li class="rec-item">No predictive focus targets available.</li>';
    } else {
        data.recommended_focus_next_month.forEach((item, index) => {
            const li = document.createElement('li');
            li.className = 'rec-item';
            li.innerHTML = `
                <div class="rec-header">
                    <span class="rec-target">${index + 1}. ${item.junction_name} (${item.police_station} Station)</span>
                    <span class="rec-metrics">Recurrence score: ${(item.recurrence_probability * 100).toFixed(0)}%</span>
                </div>
                <div class="rec-action">
                    Target Time Slot: <strong>${item.day_of_week} at ${item.start_hour}:00 - ${item.end_hour}:00</strong>. Action: ${item.recommended_action}
                </div>
            `;
            recsList.appendChild(li);
        });
    }
}

// Format 24h hour int to 12h label
function formatHour(h) {
    const ampm = h >= 12 ? 'PM' : 'AM';
    const displayHour = h % 12 === 0 ? 12 : h % 12;
    return `${displayHour} ${ampm}`;
}
