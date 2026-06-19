// simulation.js - Traffic Flow Micro-Simulation (Light Theme)
(function() {
    let canvas, ctx;
    let animationFrameId = null;
    let isRunning = false;
    let activeHotspot = null;
    let isObstructed = true;

    // Dual Sim State
    let normalSim = {
        vehicles: [],
        spawnTimer: 0,
        passedTimestamps: []
    };
    
    let obstructedSim = {
        vehicles: [],
        spawnTimer: 0,
        passedTimestamps: []
    };

    const LANE_HEIGHT = 40;
    const VEHICLE_WIDTH = 26;
    const VEHICLE_HEIGHT = 14;
    const BASE_SPEED = 2.5;
    const MIN_GAP = 30;

    // Editorial palette friendly vehicle colors (charcoals, slate, terracotta, brick red)
    const VEHICLE_COLORS = ['#1a1a1a', '#333333', '#4a4a4a', '#5c5c5c', '#7c7c7c', '#a91d22', '#8c2424'];

    window.startSimulation = function(hotspot) {
        activeHotspot = hotspot;
        
        document.getElementById('simulation-instructions').style.display = 'none';
        document.getElementById('simulation-controls').style.display = 'block';
        document.getElementById('sim-canvas-container').style.display = 'block';
        document.getElementById('sim-analysis-container').style.display = 'block';

        document.getElementById('sim-hotspot-name').textContent = hotspot.junction_name;
        
        const lossPct = Math.round((hotspot.peak_capacity_loss_pct || 0) * 100);
        const badge = document.getElementById('sim-cap-loss-badge');
        badge.textContent = `${lossPct}% Capacity Loss`;
        badge.className = `card-badge ${lossPct >= 70 ? 'high' : lossPct >= 40 ? 'med' : 'low'}`;
        
        document.getElementById('sim-analysis-text').innerHTML = `
            <strong>Peak Hour:</strong> ${formatHour(hotspot.peak_hour)}<br>
            <strong>Delay Factor:</strong> ${hotspot.peak_delay_factor.toFixed(1)}x normal<br>
            <strong>Impact:</strong> ${hotspot.description}<br>
            <strong>Avg Footprint:</strong> ${hotspot.avg_footprint_width ? hotspot.avg_footprint_width.toFixed(2) : '1.8'}m width
        `;

        canvas = document.getElementById('sim-canvas');
        ctx = canvas.getContext('2d');
        
        canvas.width = canvas.parentElement.clientWidth * 2;
        canvas.height = canvas.parentElement.clientHeight * 2;
        
        resetSim(normalSim);
        resetSim(obstructedSim);
        
        const toggleParking = document.getElementById('toggle-sim-parking');
        isObstructed = toggleParking ? toggleParking.checked : true;

        if (animationFrameId) {
            cancelAnimationFrame(animationFrameId);
            animationFrameId = null;
        }
        
        startLoop();
    };

    function formatHour(h) {
        const ampm = h >= 12 ? 'PM' : 'AM';
        const displayHour = h % 12 === 0 ? 12 : h % 12;
        return `${displayHour} ${ampm}`;
    }

    function resetSim(sim) {
        sim.vehicles = [];
        sim.spawnTimer = 0;
        sim.passedTimestamps = [];
    }

    function spawnVehicle(sim, numLanes) {
        const lane = Math.floor(Math.random() * numLanes);
        const spaceBlocked = sim.vehicles.some(v => v.lane === lane && v.x < 40);
        if (spaceBlocked) return;

        sim.vehicles.push({
            id: Math.random(),
            x: -VEHICLE_WIDTH,
            y: lane * LANE_HEIGHT + LANE_HEIGHT / 2,
            lane: lane,
            targetLane: lane,
            speed: BASE_SPEED,
            color: VEHICLE_COLORS[Math.floor(Math.random() * VEHICLE_COLORS.length)],
            width: VEHICLE_WIDTH,
            height: VEHICLE_HEIGHT,
            isSlowing: false
        });
    }

    function updateSimulation(sim, hasObstruction) {
        if (!activeHotspot) return;
        const roadWidth = activeHotspot.road_width || 7.0;
        const numLanes = Math.max(1, Math.round(roadWidth / 3.5));
        const delayFactor = activeHotspot.peak_delay_factor || 1.0;
        const capLossPct = activeHotspot.peak_capacity_loss_pct || 0.0;
        
        const obstacleX = canvas.width / 2;
        const numObstacles = capLossPct > 0.6 ? 3 : capLossPct > 0.3 ? 2 : 1;

        // Spawn logic
        sim.spawnTimer++;
        if (sim.spawnTimer > 35) {
            spawnVehicle(sim, numLanes);
            sim.spawnTimer = 0;
        }

        for (let i = 0; i < sim.vehicles.length; i++) {
            const v = sim.vehicles[i];
            let targetSpeed = BASE_SPEED;
            v.isSlowing = false;
            
            if (hasObstruction) {
                const inBottleneck = v.x > obstacleX - 150 && v.x < obstacleX + 100;
                if (inBottleneck) {
                    targetSpeed = BASE_SPEED / delayFactor;
                    v.isSlowing = true;
                }
                
                if (v.lane === 0 && v.x > obstacleX - 180 && v.x < obstacleX) {
                    if (v.targetLane === 0 && numLanes > 1) {
                        const spaceAvailable = !sim.vehicles.some(other => {
                            if (other.id === v.id || (other.lane !== 1 && other.targetLane !== 1)) return false;
                            return Math.abs(other.x - v.x) < 45;
                        });
                        
                        if (spaceAvailable) {
                            v.targetLane = 1;
                        } else {
                            targetSpeed = Math.min(targetSpeed, 0.4);
                            v.isSlowing = true;
                        }
                    }
                }
            }

            // Car-following model
            let minDistance = Infinity;
            let frontVehicle = null;
            
            sim.vehicles.forEach(other => {
                if (other.id === v.id) return;
                const sameCurrent = other.lane === v.lane && v.lane === v.targetLane;
                const sameTarget = other.targetLane === v.targetLane;
                const transitionConflict = Math.abs(other.y - v.y) < LANE_HEIGHT && v.lane !== v.targetLane;
                
                if ((sameCurrent || sameTarget || transitionConflict) && other.x > v.x) {
                    const dist = other.x - v.x - v.width;
                    if (dist < minDistance) {
                        minDistance = dist;
                        frontVehicle = other;
                    }
                }
            });

            if (frontVehicle && minDistance < MIN_GAP) {
                const gapRatio = Math.max(0.1, minDistance / MIN_GAP);
                targetSpeed = Math.min(targetSpeed, frontVehicle.speed * gapRatio);
                v.isSlowing = true;
            }

            v.speed += (targetSpeed - v.speed) * 0.1;
            v.x += v.speed;

            const targetY = v.targetLane * LANE_HEIGHT + LANE_HEIGHT / 2;
            v.y += (targetY - v.y) * 0.1;
            
            if (Math.abs(v.y - targetY) < 1) {
                v.lane = v.targetLane;
            }
        }

        const now = Date.now();
        sim.vehicles = sim.vehicles.filter(v => {
            if (v.x > canvas.width) {
                sim.passedTimestamps.push(now);
                return false;
            }
            return true;
        });

        sim.passedTimestamps = sim.passedTimestamps.filter(t => now - t < 30000);
    }

    function drawSimulation(sim, hasObstruction) {
        // Light theme background (pure white/subtle gray)
        ctx.fillStyle = '#f9f9f9';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        if (!activeHotspot) return;
        const roadWidth = activeHotspot.road_width || 7.0;
        const numLanes = Math.max(1, Math.round(roadWidth / 3.5));
        const avgFootprint = activeHotspot.avg_footprint_width || 1.8;
        const capLossPct = activeHotspot.peak_capacity_loss_pct || 0.0;
        
        const roadHeight = numLanes * LANE_HEIGHT;
        const roadY = (canvas.height - roadHeight) / 2;
        
        // Draw road surface (clean gray tone)
        ctx.fillStyle = '#eaeaea';
        ctx.fillRect(0, roadY, canvas.width, roadHeight);
        
        // Road shoulder borders (hairline slate grey)
        ctx.strokeStyle = '#cccccc';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(0, roadY);
        ctx.lineTo(canvas.width, roadY);
        ctx.moveTo(0, roadY + roadHeight);
        ctx.lineTo(canvas.width, roadY + roadHeight);
        ctx.stroke();

        // Lane dividers (clean white dashes)
        if (numLanes > 1) {
            ctx.strokeStyle = '#ffffff';
            ctx.lineWidth = 1.5;
            ctx.setLineDash([12, 12]);
            ctx.beginPath();
            for (let i = 1; i < numLanes; i++) {
                ctx.moveTo(0, roadY + i * LANE_HEIGHT);
                ctx.lineTo(canvas.width, roadY + i * LANE_HEIGHT);
            }
            ctx.stroke();
            ctx.setLineDash([]);
        }

        // Draw Obstacles (Crimson blocks representing parked cars)
        const obstacleX = canvas.width / 2;
        if (hasObstruction) {
            const numObstacles = capLossPct > 0.6 ? 3 : capLossPct > 0.3 ? 2 : 1;
            const obsW = 35;
            const obsH = Math.max(12, Math.min(LANE_HEIGHT - 6, avgFootprint * (LANE_HEIGHT / 3.5)));
            
            for (let i = 0; i < numObstacles; i++) {
                const ox = obstacleX - (obsW / 2) + i * 40;
                const oy = roadY + (LANE_HEIGHT - obsH) / 2;
                
                ctx.fillStyle = '#a91d22'; // Deep crimson
                ctx.fillRect(ox, oy, obsW, obsH);
                
                ctx.strokeStyle = 'rgba(169, 29, 34, 0.3)';
                ctx.lineWidth = 1.5;
                ctx.strokeRect(ox - 2, oy - 2, obsW + 4, obsH + 4);
                
                // Hazard indicators (Amber warning flashers)
                const isFlash = Math.floor(Date.now() / 300) % 2 === 0;
                if (isFlash) {
                    ctx.fillStyle = '#d97706';
                    ctx.beginPath();
                    ctx.arc(ox + 2, oy + obsH / 2, 2, 0, Math.PI * 2);
                    ctx.arc(ox + obsW - 2, oy + obsH / 2, 2, 0, Math.PI * 2);
                    ctx.fill();
                }
            }

            ctx.fillStyle = '#a91d22'; // Deep crimson
            ctx.font = 'bold 12px Inter, sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText('VIOLATION OBSTRUCTION', canvas.width / 2, roadY - 12);
        } else {
            ctx.fillStyle = '#2e7d32'; // Forest green
            ctx.font = 'bold 12px Inter, sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText('NORMAL FLOW', canvas.width / 2, roadY - 12);
        }

        // Draw vehicles on the road (offset by roadY)
        sim.vehicles.forEach(v => {
            // Vehicle body with rounded corners effect
            ctx.fillStyle = v.color;
            ctx.beginPath();
            const r = 3;
            const vx = v.x;
            const vy = roadY + v.y - v.height / 2;
            const vw = v.width;
            const vh = v.height;
            
            ctx.moveTo(vx + r, vy);
            ctx.lineTo(vx + vw - r, vy);
            ctx.quadraticCurveTo(vx + vw, vy, vx + vw, vy + r);
            ctx.lineTo(vx + vw, vy + vh - r);
            ctx.quadraticCurveTo(vx + vw, vy + vh, vx + vw - r, vy + vh);
            ctx.lineTo(vx + r, vy + vh);
            ctx.quadraticCurveTo(vx, vy + vh, vx, vy + vh - r);
            ctx.lineTo(vx, vy + r);
            ctx.quadraticCurveTo(vx, vy, vx + r, vy);
            ctx.closePath();
            ctx.fill();
            
            // Headlights
            ctx.fillStyle = '#fef3c7';
            ctx.beginPath();
            ctx.arc(v.x + v.width, roadY + v.y - v.height / 4, 1.5, 0, Math.PI * 2);
            ctx.arc(v.x + v.width, roadY + v.y + v.height / 4, 1.5, 0, Math.PI * 2);
            ctx.fill();

            // Brake glow when slowing
            if (v.isSlowing) {
                ctx.fillStyle = 'rgba(220, 38, 38, 0.2)';
                ctx.fillRect(v.x - 2, roadY + v.y - v.height / 2 - 1, v.width + 4, v.height + 2);
            }
        });
    }

    function startLoop() {
        if (animationFrameId) {
            cancelAnimationFrame(animationFrameId);
            animationFrameId = null;
        }
        isRunning = true;
        animationFrameId = requestAnimationFrame(tick);
    }

    function tick() {
        if (!isRunning) {
            animationFrameId = null;
            return;
        }

        updateSimulation(normalSim, false);
        updateSimulation(obstructedSim, true);

        drawSimulation(isObstructed ? obstructedSim : normalSim, isObstructed);

        const withoutVal = document.getElementById('metric-without');
        const withVal = document.getElementById('metric-with');
        if (withoutVal) withoutVal.textContent = normalSim.passedTimestamps.length;
        if (withVal) withVal.textContent = obstructedSim.passedTimestamps.length;

        animationFrameId = requestAnimationFrame(tick);
    }

    document.addEventListener('DOMContentLoaded', () => {
        const toggleParking = document.getElementById('toggle-sim-parking');
        if (toggleParking) {
            toggleParking.addEventListener('change', (e) => {
                isObstructed = e.target.checked;
            });
        }

        const tabButtons = document.querySelectorAll('.tab-btn');
        tabButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                const targetTab = btn.getAttribute('data-tab');
                if (targetTab !== 'tab-simulate') {
                    isRunning = false;
                    if (animationFrameId) {
                        cancelAnimationFrame(animationFrameId);
                        animationFrameId = null;
                    }
                } else if (activeHotspot) {
                    startLoop();
                }
            });
        });
    });
})();
