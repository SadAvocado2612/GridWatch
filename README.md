# GridWatch: Spatial-Temporal Parking Enforcement & Congestion Analytics

## 1. Problem Statement
Urban centers globally suffer from severe traffic bottlenecking, driven heavily by illegal and unorganized curbside parking. Traditional municipal enforcement remains highly reactive, relying on random physical patrols that lack data-driven visibility into when and where violations cluster. Because enforcement agencies cannot accurately measure the economic and environmental cost of illegal parking, they struggle to allocate limited officer forces efficiently. This leads to persistent peak-hour capacity losses, increased commute delays, and a cycle of unresolved repeat offences that degrade city roadway efficiency.

---

## 2. Platform Capabilities & Approach

*   **Congestion Cost Scoring**: GridWatch quantifies the physical footprint of parking violations by calculating BPR-style capacity loss coefficients and converting them directly into delay metrics. This allows municipal planners to see the delay impact of blockages on specific roadways.
*   **Predictive Enforcement Windows**: By analyzing historical spatial-temporal patterns, the platform calculates weekly recurrence probabilities. Planners can anticipate peak violation windows ($\ge 50\%$ recurrence) to shift patrol scheduling from reactive to proactive dispatch.
*   **Patrol Route Optimization**: A greedy nearest-neighbor algorithm dynamically generates sequential patrol itineraries for $N$ enforcement units. By optimizing routes using Haversine distances between current hotspot coordinates, officers cover more high-priority violations in less time.
*   **Camera Placement Gap Analysis**: To maximize camera coverage, the platform conducts spatial gap analysis, flagging spots further than 300 meters from current surveillance devices. It recommends optimal placement coordinates separated by a minimum buffer zone.
*   **Validation Triage Classifier**: An integrated Machine Learning classifier predicts ticket approval rates. This categorizes low-risk tickets for automated batch processing, reducing manual auditing backlog.
*   **Repeat-Offender Network**: A visual relation network map links habitual vehicle license plates to specific violation hotspots. Planners can identify "habitual" localized offenders versus "roaming" violators across the city.
*   **Displacement Detection**: By observing adjacent cluster density shifts post-patrol, the platform tracks spatial displacement. This verifies if violations are deterred or simply pushed to neighboring streets.
*   **Automatic Scaling Fines with Simulated Notifications**: The platform implements an escalating penalty schema for repeat offenders, increasing fines by ₹100 for each offense beyond a repeat threshold. It features bulk simulation of SMS warnings sent to registered vehicle owners.
*   **Monthly Reports**: Users can generate print-ready Monthly Audit summaries. The browser compiles clean multi-page document layouts containing activity trends, top hotspots tables, and automated fine tallies using standard CSS print rules.
---

## 3. Pages Overview

| Page Name | Target Audience | Primary Function & Description |
| :--- | :--- | :--- |
| **Login** (`login.html`) | Enforcers / Officers | Secured authentication gate verifying officer badges (e.g. `BTP001`) and establishing session storage tokens for protected API communication. |
| **Analysis** (`analysis.html`) | Planners / Admins | The command center. Displays predictive calendars, patrol dispatch planners, camera placement suggestions, the offender relation network graph, and the monthly report generator. |
| **Report Violation** (`report.html` or in-app form) | Citizens & Enforcers | Form for reporting vehicle parking violations. Reuses Leaflet pin drops to automatically grab precise coordinates and vehicle numbers. |
| **Fines** (`fines.html`) | Admins / Officers | Repeat offender registry. Scans the database, calculates escalating fine amounts, triggers bulk SMS reminders, and manages paid/unpaid status. |
| **Monthly Report** (`monthly-report.html`) | Commissioners / Admins | Print-ready layout containing monthly KPIs, Chart.js trends, hotspot tables, and predictive focus recommendations. |

---

## 4. Technical Architecture

### Backend Stack
*   **FastAPI Framework**: Serves all analytical, authentication, and database endpoints.
*   **Analysis Engines**: Python modules leveraging `pandas` and `numpy` for data extraction and machine learning predictions.
*   **Parquet Storage**: Analytical outputs and violation logs are saved in wide Parquet formats (`violations_clean.parquet`, `hotspots_scored.parquet`) for fast processing.
*   **SQLite Database**: Managed by Python's `sqlite3` driver, storing persistent transaction logs for repeat-offender fines, sms reminders, and payments.

### Frontend Stack
*   **Vanilla JS, HTML5, & CSS3**: Core layout and responsive interactions.
*   **Leaflet.js**: Renders interactive map interfaces and overlays path routes.
*   **Three.js**: Powers the interactive 3D Congestion Skyline.
*   **Chart.js**: Paints canvas-based charts for monthly trends and distributions.
*   **External CDN dependencies**: No heavy binaries or node packages are installed locally; all UI libraries load from secure CDNs.

---

## 5. Setup & Installation

### Prerequisite
*   Python 3.8 or higher installed on your system.

### Running the Application

1.  **Clone the workspace** and navigate to the project root directory:
    ```powershell
    cd "d:\RandomHackathons\Flipkart Hackathon Round 2"
    ```

2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Start the FastAPI backend server**:
    ```bash
    python -m uvicorn backend.app:app --reload --port 8000
    ```

4.  **Launch the frontend**:
    - Open `http://127.0.0.1:8000/frontend/index.html` in your browser.
    - To log in as an enforcer on the Analysis dashboard, use:
      - **Badge ID**: `BTP001`
      - **Password**: `password123`

---

## 6. Known Limitations & Simulations

*   **Simulated Phone & SMS Logs**: No actual SMS messages are dispatched. Phone numbers and warning notifications generated under the Fines page are simulated for demonstration purposes.
*   **Default Road Width**: Where OpenStreetMap (OSM) roadway data is not dynamically loaded, the congestion model assumes a standard two-lane width of 7.0 meters.

---

## 7. Production Roadmap

*   **Real OSM Integration**: Fetch roadway dimensions and number of lanes directly via Overpass API queries based on GPS coordinates.
*   **Live Transit Integration**: Consume real-time GPS feeds from city public buses to measure true speed deviations against scheduled speeds.
*   **Production SMS Gateways**: IntegrateTwilio or localized SMS providers to dispatch actual citation alerts to vehicle owners.
*   **Existing Camera Infrastructure**: Sync with public surveillance networks using computer vision classification to automatically log parking violations.
