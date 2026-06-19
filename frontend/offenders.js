// offenders.js - D3 Force-Directed Offender Network Graph & Table
// Depends on d3.v7

(function () {
    'use strict';

    // Session token validation check
    const sessionToken = sessionStorage.getItem('session_token');
    if (!sessionToken) {
        window.location.replace('login.html');
        return;
    }

    const API_BASE = window.location.origin.includes('127.0.0.1') || window.location.origin.includes('localhost')
        ? (window.location.port === '8000' ? '/api' : 'http://localhost:8000/api')
        : '/api';

    const COLORS = {
        habitual: '#a91d22',
        roaming:  '#d96b27',
        mixed:    '#6b7280',
        cluster:  '#1e293b',
        link:     '#d1d5db',
        linkHover:'#a91d22',
        bg:       '#fafaf9',
    };

    let graphData = null;
    let simulation = null;
    let svgEl = null;
    let graphInitialized = false;

    // ── Bootstrap ────────────────────────────────────────────────────────────
    // Wait for the Offenders tab to become visible before initializing.
    // We observe the tab-btn click via MutationObserver on the panel class.
    function waitForTabAndInit() {
        const panel = document.getElementById('tab-offenders');
        if (!panel) return;

        const mapFrame = document.getElementById('map-frame-container');
        const graphFrame = document.getElementById('graph-frame-container');
        const caption1 = document.getElementById('caption-figure-1');
        const caption2 = document.getElementById('caption-figure-2');

        function syncVisibility() {
            const isActive = panel.classList.contains('active');
            if (isActive) {
                if (mapFrame) mapFrame.style.display = 'none';
                if (caption1) caption1.style.display = 'none';
                if (graphFrame) graphFrame.style.display = 'block';
                if (caption2) caption2.style.display = 'block';
            } else {
                if (mapFrame) mapFrame.style.display = 'block';
                if (caption1) caption1.style.display = 'block';
                if (graphFrame) graphFrame.style.display = 'none';
                if (caption2) caption2.style.display = 'none';
            }
        }

        // Use MutationObserver to watch for 'active' class being added
        const observer = new MutationObserver(() => {
            syncVisibility();
            if (panel.classList.contains('active') && !graphInitialized) {
                graphInitialized = true;
                // Wait briefly for display block layout to settle so dimensions are correct
                setTimeout(() => {
                    loadOffenderData();
                }, 50);
            }
        });
        observer.observe(panel, { attributes: true, attributeFilter: ['class'] });

        // Run sync initially
        syncVisibility();

        // Also load the table immediately (it's just data, not layout-dependent)
        loadTopOffendersTable();
    }

    document.addEventListener('DOMContentLoaded', waitForTabAndInit);

    // ── Data Loading ─────────────────────────────────────────────────────────
    async function loadOffenderData() {
        const placeholder = document.getElementById('graph-placeholder');
        try {
            const res = await fetch(`${API_BASE}/offender-network`, {
                headers: {
                    'Authorization': `Bearer ${sessionStorage.getItem('session_token')}`
                }
            });
            if (res.status === 401) {
                sessionStorage.clear();
                window.location.replace('login.html');
                return;
            }
            if (!res.ok) throw new Error('Network error');
            graphData = await res.json();
            if (placeholder) placeholder.style.display = 'none';
            renderForceGraph(graphData);
        } catch (err) {
            console.error('[offenders] Failed to load network data:', err);
            if (placeholder) placeholder.textContent = 'Failed to load offender network data.';
        }
    }

    async function loadTopOffendersTable() {
        const tbody = document.getElementById('offender-table-body');
        if (!tbody) return;
        try {
            const res = await fetch(`${API_BASE}/top-offenders`, {
                headers: {
                    'Authorization': `Bearer ${sessionStorage.getItem('session_token')}`
                }
            });
            if (res.status === 401) {
                sessionStorage.clear();
                window.location.replace('login.html');
                return;
            }
            if (!res.ok) throw new Error('Network error');
            const data = await res.json();
            renderOffendersTable(data, tbody);
        } catch (err) {
            console.error('[offenders] Failed to load table:', err);
            tbody.innerHTML = `<tr><td colspan="6" class="ledger-placeholder text-danger">Error: ${err.message}</td></tr>`;
        }
    }

    // ── Force Graph Rendering ────────────────────────────────────────────────
    function renderForceGraph(data) {
        const container = document.getElementById('offender-graph-container');
        svgEl = document.getElementById('offender-graph-svg');
        if (!container || !svgEl) return;

        let width = container.clientWidth || 600;
        let height = container.clientHeight || 420;

        const svg = d3.select(svgEl)
            .attr('width', width)
            .attr('height', height)
            .attr('viewBox', [0, 0, width, height]);

        svg.selectAll('*').remove();

        // Defs for glow filter
        const defs = svg.append('defs');
        const filter = defs.append('filter').attr('id', 'glow');
        filter.append('feGaussianBlur').attr('stdDeviation', '2').attr('result', 'coloredBlur');
        const feMerge = filter.append('feMerge');
        feMerge.append('feMergeNode').attr('in', 'coloredBlur');
        feMerge.append('feMergeNode').attr('in', 'SourceGraphic');

        // Scale nodes by their size property
        const vehicleSizes = data.nodes.filter(n => n.type === 'vehicle').map(n => n.size);
        const clusterSizes = data.nodes.filter(n => n.type === 'cluster').map(n => n.size);
        
        const vehicleScale = d3.scaleSqrt()
            .domain([d3.min(vehicleSizes) || 3, d3.max(vehicleSizes) || 55])
            .range([3, 12]);
        
        const clusterScale = d3.scaleSqrt()
            .domain([d3.min(clusterSizes) || 0, d3.max(clusterSizes) || 100])
            .range([6, 18]);

        function nodeRadius(d) {
            if (d.type === 'cluster') return clusterScale(d.size || 10);
            return vehicleScale(d.size || 3);
        }

        function nodeColor(d) {
            if (d.type === 'cluster') return COLORS.cluster;
            return COLORS[d.classification] || COLORS.mixed;
        }

        // Weight-based link opacity
        const linkWeights = data.links.map(l => l.weight);
        const linkOpacityScale = d3.scaleLinear()
            .domain([d3.min(linkWeights) || 1, d3.max(linkWeights) || 50])
            .range([0.08, 0.45]);

        // Create zoom container
        const g = svg.append('g');

        const zoom = d3.zoom()
            .scaleExtent([0.3, 5])
            .on('zoom', (event) => {
                g.attr('transform', event.transform);
            });
        svg.call(zoom);

        // Links
        const link = g.append('g')
            .attr('class', 'links')
            .selectAll('line')
            .data(data.links)
            .join('line')
            .attr('stroke', COLORS.link)
            .attr('stroke-width', d => Math.max(0.5, Math.sqrt(d.weight) * 0.5))
            .attr('stroke-opacity', d => linkOpacityScale(d.weight));

        // Nodes
        const node = g.append('g')
            .attr('class', 'nodes')
            .selectAll('circle')
            .data(data.nodes)
            .join('circle')
            .attr('r', d => nodeRadius(d))
            .attr('fill', d => nodeColor(d))
            .attr('stroke', '#fff')
            .attr('stroke-width', d => d.type === 'cluster' ? 1.5 : 0.5)
            .attr('cursor', 'pointer')
            .style('filter', d => d.type === 'cluster' ? 'url(#glow)' : 'none')
            .on('mouseover', function (event, d) {
                d3.select(this)
                    .transition().duration(150)
                    .attr('r', nodeRadius(d) * 1.5)
                    .attr('stroke-width', 2);
                // Highlight connected links
                link.attr('stroke', l =>
                    (l.source.id === d.id || l.target.id === d.id) ? COLORS.linkHover : COLORS.link
                ).attr('stroke-opacity', l =>
                    (l.source.id === d.id || l.target.id === d.id) ? 0.7 : linkOpacityScale(l.weight)
                );
                showTooltip(event, d);
            })
            .on('mouseout', function (event, d) {
                d3.select(this)
                    .transition().duration(150)
                    .attr('r', nodeRadius(d))
                    .attr('stroke-width', d.type === 'cluster' ? 1.5 : 0.5);
                link.attr('stroke', COLORS.link)
                    .attr('stroke-opacity', l => linkOpacityScale(l.weight));
                hideTooltip();
            })
            .on('click', (event, d) => {
                event.stopPropagation();
                showDetailPanel(d, data);
            })
            .call(d3.drag()
                .on('start', dragstarted)
                .on('drag', dragged)
                .on('end', dragended));

        // Labels for cluster nodes only
        const label = g.append('g')
            .attr('class', 'labels')
            .selectAll('text')
            .data(data.nodes.filter(n => n.type === 'cluster'))
            .join('text')
            .text(d => {
                // Short label: extract junction name
                const parts = d.label.split(' - ');
                return parts.length > 1 ? parts[1].substring(0, 18) : d.label.substring(0, 18);
            })
            .attr('font-size', '7px')
            .attr('font-family', 'Inter, sans-serif')
            .attr('fill', '#374151')
            .attr('text-anchor', 'middle')
            .attr('dy', d => -clusterScale(d.size || 10) - 4)
            .attr('pointer-events', 'none');

        // Simulation
        simulation = d3.forceSimulation(data.nodes)
            .force('link', d3.forceLink(data.links).id(d => d.id).distance(60).strength(0.3))
            .force('charge', d3.forceManyBody().strength(-80))
            .force('center', d3.forceCenter(width / 2, height / 2))
            .force('collision', d3.forceCollide().radius(d => nodeRadius(d) + 2))
            .force('x', d3.forceX(width / 2).strength(0.05))
            .force('y', d3.forceY(height / 2).strength(0.05))
            .on('tick', () => {
                link
                    .attr('x1', d => d.source.x)
                    .attr('y1', d => d.source.y)
                    .attr('x2', d => d.target.x)
                    .attr('y2', d => d.target.y);
                node
                    .attr('cx', d => d.x)
                    .attr('cy', d => d.y);
                label
                    .attr('x', d => d.x)
                    .attr('y', d => d.y);
            });

        // Click on background to deselect
        svg.on('click', () => {
            const panel = document.getElementById('offender-detail-panel');
            if (panel) panel.style.display = 'none';
        });

        // Resize observer to ensure the graph adjusts dynamically to fit the container
        const resizeObserver = new ResizeObserver(entries => {
            for (let entry of entries) {
                const newWidth = entry.contentRect.width;
                const newHeight = entry.contentRect.height;
                if (newWidth > 0 && newHeight > 0) {
                    width = newWidth;
                    height = newHeight;
                    svg.attr('width', width)
                       .attr('height', height)
                       .attr('viewBox', [0, 0, width, height]);
                    simulation.force('center', d3.forceCenter(width / 2, height / 2));
                    simulation.force('x', d3.forceX(width / 2).strength(0.05));
                    simulation.force('y', d3.forceY(height / 2).strength(0.05));
                    simulation.alpha(0.15).restart();
                }
            }
        });
        resizeObserver.observe(container);
    }

    // ── Drag handlers ────────────────────────────────────────────────────────
    function dragstarted(event, d) {
        if (!event.active) simulation.alphaTarget(0.3).restart();
        d.fx = d.x;
        d.fy = d.y;
    }
    function dragged(event, d) {
        d.fx = event.x;
        d.fy = event.y;
    }
    function dragended(event, d) {
        if (!event.active) simulation.alphaTarget(0);
        d.fx = null;
        d.fy = null;
    }

    // ── Tooltip ──────────────────────────────────────────────────────────────
    let tooltipEl = null;

    function ensureTooltip() {
        if (!tooltipEl) {
            tooltipEl = document.createElement('div');
            tooltipEl.className = 'graph-tooltip';
            document.body.appendChild(tooltipEl);
        }
        return tooltipEl;
    }

    function showTooltip(event, d) {
        const tip = ensureTooltip();
        if (d.type === 'vehicle') {
            tip.innerHTML = `
                <div class="tip-title">${d.label}</div>
                <div class="tip-row">${d.size} violations &middot; ${d.classification}</div>
            `;
        } else {
            tip.innerHTML = `
                <div class="tip-title">${d.label}</div>
                <div class="tip-row">Cluster &middot; Score: ${typeof d.size === 'number' ? d.size.toFixed(1) : d.size}</div>
            `;
        }
        tip.style.display = 'block';
        tip.style.left = (event.pageX + 12) + 'px';
        tip.style.top = (event.pageY - 10) + 'px';
    }

    function hideTooltip() {
        if (tooltipEl) tooltipEl.style.display = 'none';
    }

    // ── Detail Panel ─────────────────────────────────────────────────────────
    function showDetailPanel(d, data) {
        const panel = document.getElementById('offender-detail-panel');
        const title = document.getElementById('detail-panel-title');
        const body = document.getElementById('detail-panel-body');
        if (!panel || !title || !body) return;

        panel.style.display = 'block';
        title.textContent = d.label;

        if (d.type === 'vehicle') {
            // Find connected clusters
            const connected = data.links
                .filter(l => (l.source.id || l.source) === d.id || (l.target.id || l.target) === d.id)
                .map(l => {
                    const otherId = (l.source.id || l.source) === d.id ? (l.target.id || l.target) : (l.source.id || l.source);
                    const otherNode = data.nodes.find(n => n.id === otherId);
                    return { cluster: otherNode ? otherNode.label : otherId, weight: l.weight };
                })
                .sort((a, b) => b.weight - a.weight);

            body.innerHTML = `
                <div class="detail-stat-row"><span class="detail-label">Classification</span><span class="detail-value classification-${d.classification}">${d.classification.toUpperCase()}</span></div>
                <div class="detail-stat-row"><span class="detail-label">Total Violations</span><span class="detail-value">${d.size}</span></div>
                <div class="detail-stat-row"><span class="detail-label">Linked Clusters</span><span class="detail-value">${connected.length}</span></div>
                <hr class="detail-divider">
                <div class="detail-section-title">Cluster Activity</div>
                ${connected.map(c => `
                    <div class="detail-cluster-row">
                        <span class="detail-cluster-name">${c.cluster}</span>
                        <span class="detail-cluster-count">${c.weight}</span>
                    </div>
                `).join('')}
            `;
        } else {
            // Cluster node: show connected vehicles
            const connected = data.links
                .filter(l => (l.source.id || l.source) === d.id || (l.target.id || l.target) === d.id)
                .map(l => {
                    const otherId = (l.source.id || l.source) === d.id ? (l.target.id || l.target) : (l.source.id || l.source);
                    const otherNode = data.nodes.find(n => n.id === otherId);
                    return { vehicle: otherNode ? otherNode.label : otherId, weight: l.weight, classification: otherNode?.classification || 'mixed' };
                })
                .sort((a, b) => b.weight - a.weight);

            body.innerHTML = `
                <div class="detail-stat-row"><span class="detail-label">Type</span><span class="detail-value">Hotspot Cluster</span></div>
                <div class="detail-stat-row"><span class="detail-label">Congestion Score</span><span class="detail-value">${typeof d.size === 'number' ? d.size.toFixed(1) : d.size}</span></div>
                <div class="detail-stat-row"><span class="detail-label">Linked Vehicles</span><span class="detail-value">${connected.length}</span></div>
                <hr class="detail-divider">
                <div class="detail-section-title">Repeat Offenders at this Cluster</div>
                ${connected.slice(0, 20).map(c => `
                    <div class="detail-cluster-row">
                        <span class="detail-cluster-name classification-${c.classification}">${c.vehicle}</span>
                        <span class="detail-cluster-count">${c.weight} hits</span>
                    </div>
                `).join('')}
                ${connected.length > 20 ? `<div class="detail-more">+${connected.length - 20} more...</div>` : ''}
            `;
        }

        // Close button
        document.getElementById('detail-panel-close').onclick = () => {
            panel.style.display = 'none';
        };
    }

    // ── Table Rendering ──────────────────────────────────────────────────────
    function renderOffendersTable(data, tbody) {
        if (!data || data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="ledger-placeholder">No offender data available.</td></tr>';
            return;
        }

        // Show top 50 in the table
        const topRows = data.slice(0, 50);
        tbody.innerHTML = topRows.map((row, idx) => `
            <tr class="offender-row" data-classification="${row.classification}">
                <td class="rank-cell">${idx + 1}</td>
                <td class="vid-cell">${row.vehicle_id}</td>
                <td class="violations-cell">${row.total_violations}</td>
                <td class="num-cell-secondary">${row.distinct_clusters}</td>
                <td class="num-cell-secondary">${row.distinct_days}</td>
                <td class="badge-cell"><span class="classification-badge ${row.classification}">${row.classification}</span></td>
            </tr>
        `).join('');
    }
})();
