# GridWatch: Closed-Loop Spatial-Temporal Parking Enforcement

## The Pitch
Illegal curbside parking is not just a ticketing nuisance; it is a major catalyst for urban mobility collapse. Traditional enforcement is reactive, manual, and blind to economic impact. **GridWatch** solves this by introducing a data-driven, closed-loop spatial-temporal audit system that optimizes officer dispatch, models congestion costs, and deters repeat offenders. 

---

## The Demo Narrative Arc: A Four-Stage Solution

### 1. DETECT
Instead of random patrols, GridWatch monitors municipal traffic flows using historical datasets to cluster offenses geospatially.
*   **The Technology**: Spatial density clustering models locate hotspots across Bengaluru. The **Predictive Calendar** analyzes hourly and weekly frequencies, isolating target enforcement windows with $\ge 50\%$ recurrence probability.
*   **The Demo Point**: Enforcers log onto the dashboard and see exactly where and when the city will experience parking bottlenecks next Tuesday at 9 AM before they even manifest.

### 2. QUANTIFY
Every vehicle blocking a lane causes a cascade of delay. GridWatch models this capacity reduction to show the cost of illegal parking.
*   **The Technology**: We compute a BPR-style congestion cost score, translating delay into physical capacity loss. Commuters and planners visualize this in real-time via the **3D Congestion Skyline**, where vertical columns grow and shrink based on congestion intensity.
*   **The Demo Point**: Planners click on *Safina Plaza Junction* and see that curbside blockages are costing commuters delay, which translates to a clear daily loss in productivity.

### 3. ENFORCE
Once congestion is quantified, the platform moves resources to key areas.
*   **The Technology**: The **Patrol Router** calculates greedy nearest-neighbor itineraries for $N$ enforcement units based on distance. Simultaneously, **Camera Gap Analysis** highlights unmonitored zones to suggest optimal camera placements. For repeat offenders, the database calculates escalating fines (increasing by ₹100 per infraction) and triggers simulated SMS alerts to vehicle owners.
*   **The Demo Point**: With one click, the system dispatches optimized patrol paths to 3 units, flags a vehicle with 8 violations for an escalated ₹800 fine, and prepares simulated bulk reminders.

### 4. CLOSE THE LOOP
Enforcement must adapt dynamically as traffic patterns shift.
*   **The Technology**: The **Report Violation** portal allows citizens to drop Leaflet pins and submit curbside violations. These reports feed straight back into the analytical pipeline. The print-ready **Monthly Report** compiles KPIs, Chart.js trends, and hotspots into an actionable summary. Additionally, the **Public Commuter View** alerts drivers of active blocks so they can reroute.
*   **The Demo Point**: A citizen files a report, the hotspot index updates, the monthly report updates, and drivers route around the blockage, closing the enforcement loop.

---

## The "So What?" — Headline Impact Metrics

Based on the audit of **298,446** historical traffic records in Bengaluru, enforcing the top 10 hotspots yields:
*   **30,052.8 delay-minutes saved per day** (~500 hours of commuter time recovered daily).
*   **₹300,528 saved daily in productivity and fuel wastage** (assuming a conservative cost of ₹10 per delay-minute).
*   **601 kg of CO2 emissions prevented daily** (averaging 20g of carbon output saved per minute of avoided idling).
*   **11 critical hotspots** identified with high congestion indexes ($\ge 20.0$).
*   **73.6% ML ticket triage accuracy**, reducing manual auditing backlogs by up to 50%.

---

## Prototype Simulation Boundaries
*   **Simulated Actions**: Warning SMS notification dispatches, cell numbers, and delivery confirmation flags shown on the Fines dashboard are simulated. No actual carrier integration is active in this prototype.
*   **Default Metrics**: Road widths default to 7.0 meters where OpenStreetMap (OSM) APIs are not queried, and the 3D skyline renders columns on an abstract coordinate plane.
