
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>AI EQMS Hub Pro — Data Table</title>
    <!-- Font Awesome (icons) -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css" />
    <style>
        /* ----- RESET & BASE ----- */
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: 'Segoe UI', Roboto, system-ui, sans-serif;
            background: #f8fafc;
            color: #1e293b;
            padding: 16px;
            min-height: 100vh;
            transition: background 0.2s, color 0.2s;
        }
        .app-container {
            max-width: 1440px;
            margin: 0 auto;
        }

        /* ----- THEME TOGGLE (light/dark) ----- */
        .theme-toggle {
            position: fixed;
            top: 16px;
            right: 16px;
            z-index: 999;
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 40px;
            padding: 8px 16px;
            font-size: 0.9rem;
            font-weight: 600;
            cursor: pointer;
            box-shadow: 0 4px 12px rgba(0,0,0,0.06);
            display: flex;
            align-items: center;
            gap: 8px;
            transition: 0.2s;
        }
        .theme-toggle:hover {
            box-shadow: 0 6px 20px rgba(0,0,0,0.1);
        }
        .theme-toggle i {
            font-size: 1.1rem;
        }

        /* ----- HEADER / MARQUEE ----- */
        .marquee-box {
            background: linear-gradient(90deg, #FF9933, #FFFFFF, #138808);
            padding: 10px 0;
            border-radius: 12px;
            margin-bottom: 20px;
            overflow: hidden;
            box-shadow: 0 2px 12px rgba(0,0,0,0.08);
            white-space: nowrap;
        }
        .marquee-box .scroll-text {
            display: inline-block;
            padding-left: 100%;
            animation: marquee-scroll 28s linear infinite;
            color: #000000;
            font-weight: 700;
            font-size: 15px;
            letter-spacing: 0.3px;
        }
        @keyframes marquee-scroll {
            0% { transform: translateX(0); }
            100% { transform: translateX(-100%); }
        }

        /* ----- TOP BAR (title + nav + status) ----- */
        .top-bar {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            margin-bottom: 8px;
        }
        .top-bar h1 {
            font-size: 22px;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 8px;
            margin: 0;
        }
        .top-bar h1 i {
            color: #2563eb;
        }
        .nav-buttons {
            display: flex;
            gap: 6px;
            flex-wrap: wrap;
        }
        .nav-btn {
            background: #f1f5f9;
            border: 1px solid #cbd5e1;
            border-radius: 30px;
            padding: 6px 16px;
            font-size: 0.9rem;
            font-weight: 600;
            color: #1e293b;
            cursor: pointer;
            transition: 0.15s;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }
        .nav-btn.active {
            background: #2563eb;
            color: white;
            border-color: #2563eb;
        }
        .nav-btn:hover {
            background: #dbeafe;
        }
        .nav-btn.active:hover {
            background: #1d4ed8;
        }
        .status-pill {
            font-size: 13px;
            background: rgba(63, 185, 80, 0.15);
            color: #16a34a;
            border: 1px solid #16a34a;
            border-radius: 40px;
            padding: 4px 14px;
            font-weight: 600;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            animation: live-pulse 2s infinite;
        }
        @keyframes live-pulse {
            0%, 100% { box-shadow: 0 0 0 0 rgba(63,185,80,0.3); }
            50% { box-shadow: 0 0 0 8px rgba(63,185,80,0); }
        }

        /* ----- SHEET HEADER ----- */
        .sheet-header {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            justify-content: space-between;
            margin: 18px 0 12px;
        }
        .sheet-header h2 {
            font-size: 1.5rem;
            font-weight: 600;
        }
        .sheet-header .badge {
            background: #e2e8f0;
            border-radius: 40px;
            padding: 2px 14px;
            font-weight: 600;
            font-size: 0.9rem;
        }

        /* ----- SEARCH & FILTERS ----- */
        .search-row {
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            margin-bottom: 16px;
            align-items: center;
        }
        .search-row input,
        .search-row select {
            padding: 8px 14px;
            border: 1px solid #cbd5e1;
            border-radius: 30px;
            font-size: 0.95rem;
            background: white;
            transition: 0.2s;
            flex: 1 1 200px;
        }
        .search-row input:focus,
        .search-row select:focus {
            outline: none;
            border-color: #2563eb;
            box-shadow: 0 0 0 3px rgba(37,99,235,0.2);
        }
        .search-row .btn {
            background: #f1f5f9;
            border: 1px solid #cbd5e1;
            border-radius: 30px;
            padding: 8px 20px;
            font-weight: 600;
            cursor: pointer;
            transition: 0.15s;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            color: #1e293b;
        }
        .search-row .btn-primary {
            background: #2563eb;
            border-color: #2563eb;
            color: white;
        }
        .search-row .btn-primary:hover {
            background: #1d4ed8;
        }
        .search-row .btn:hover {
            background: #dbeafe;
        }
        .search-row .btn-primary:hover {
            background: #1d4ed8;
        }

        /* ----- TRAIN COUNT CARDS ----- */
        .train-cards {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin: 12px 0 16px;
        }
        .train-card {
            background: white;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 6px 18px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.04);
            text-align: center;
            transition: 0.15s;
            min-width: 70px;
        }
        .train-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.08);
            border-color: #2563eb;
        }
        .train-card .number {
            font-weight: 800;
            font-size: 1.6rem;
            color: #2563eb;
            line-height: 1.2;
        }
        .train-card .label {
            font-size: 0.8rem;
            font-weight: 600;
            color: #64748b;
        }
        .train-card.total {
            border-color: #16a34a;
            background: #f0fdf4;
        }
        .train-card.total .number {
            color: #16a34a;
        }

        /* ----- TABLE WRAPPER ----- */
        .table-wrapper {
            background: white;
            border-radius: 16px;
            border: 1px solid #e2e8f0;
            overflow: auto;
            box-shadow: 0 2px 12px rgba(0,0,0,0.04);
            margin: 12px 0;
        }
        .table-wrapper table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.85rem;
            min-width: 600px;
        }
        .table-wrapper th {
            background: #1e293b;
            color: white;
            font-weight: 600;
            padding: 10px 12px;
            text-align: center;
            border-bottom: 2px solid #334155;
            position: sticky;
            top: 0;
            z-index: 10;
            white-space: nowrap;
        }
        .table-wrapper td {
            padding: 8px 10px;
            text-align: center;
            border-bottom: 1px solid #e2e8f0;
            vertical-align: middle;
        }
        .table-wrapper tr:nth-child(even) td {
            background: #f8fafc;
        }
        .table-wrapper tr:hover td {
            background: #eff6ff;
        }
        .table-wrapper .checkbox-cell {
            width: 40px;
            text-align: center;
        }
        .table-wrapper input[type="checkbox"] {
            width: 18px;
            height: 18px;
            cursor: pointer;
            accent-color: #2563eb;
        }

        /* ----- PAGINATION ----- */
        .pagination {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            margin: 14px 0 10px;
        }
        .pagination .page-info {
            font-weight: 500;
        }
        .pagination .btn-group {
            display: flex;
            gap: 6px;
        }
        .pagination .btn-group button {
            background: #f1f5f9;
            border: 1px solid #cbd5e1;
            border-radius: 30px;
            padding: 6px 18px;
            font-weight: 600;
            cursor: pointer;
            transition: 0.15s;
            color: #1e293b;
        }
        .pagination .btn-group button:hover:not(:disabled) {
            background: #dbeafe;
        }
        .pagination .btn-group button:disabled {
            opacity: 0.4;
            cursor: not-allowed;
        }

        /* ----- ACTION BUTTONS ----- */
        .action-bar {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin: 14px 0 8px;
            align-items: center;
        }
        .action-bar .btn {
            background: #f1f5f9;
            border: 1px solid #cbd5e1;
            border-radius: 30px;
            padding: 8px 18px;
            font-weight: 600;
            cursor: pointer;
            transition: 0.15s;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            color: #1e293b;
            font-size: 0.9rem;
        }
        .action-bar .btn:hover {
            background: #dbeafe;
        }
        .action-bar .btn-danger {
            color: #dc2626;
            border-color: #fca5a5;
        }
        .action-bar .btn-danger:hover {
            background: #fee2e2;
        }
        .action-bar .btn-success {
            background: #16a34a;
            border-color: #16a34a;
            color: white;
        }
        .action-bar .btn-success:hover {
            background: #15803d;
        }
        .action-bar .btn-primary {
            background: #2563eb;
            border-color: #2563eb;
            color: white;
        }
        .action-bar .btn-primary:hover {
            background: #1d4ed8;
        }

        /* ----- EXPORT / EXTRA ----- */
        .extra-section {
            margin-top: 20px;
            border-top: 1px solid #e2e8f0;
            padding-top: 18px;
        }
        .extra-section .row {
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            margin-top: 8px;
        }
        .extra-section .btn {
            background: #f1f5f9;
            border: 1px solid #cbd5e1;
            border-radius: 30px;
            padding: 6px 16px;
            font-weight: 600;
            cursor: pointer;
            transition: 0.15s;
            font-size: 0.85rem;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }
        .extra-section .btn:hover {
            background: #dbeafe;
        }

        /* ----- FOOTER ----- */
        .footer {
            margin-top: 36px;
            padding-top: 18px;
            border-top: 1px solid #e2e8f0;
            text-align: center;
            color: #64748b;
            font-size: 0.85rem;
        }

        /* ----- DARK THEME ----- */
        body.dark {
            background: #0f172a;
            color: #f1f5f9;
        }
        body.dark .theme-toggle {
            background: #1e293b;
            border-color: #334155;
            color: #f1f5f9;
        }
        body.dark .marquee-box {
            background: linear-gradient(90deg, #1e293b, #334155, #1e293b);
        }
        body.dark .marquee-box .scroll-text {
            color: #f1f5f9;
        }
        body.dark .nav-btn {
            background: #1e293b;
            border-color: #334155;
            color: #f1f5f9;
        }
        body.dark .nav-btn.active {
            background: #2563eb;
            border-color: #2563eb;
            color: white;
        }
        body.dark .nav-btn:hover {
            background: #334155;
        }
        body.dark .status-pill {
            background: rgba(63,185,80,0.2);
            color: #4ade80;
            border-color: #4ade80;
        }
        body.dark .search-row input,
        body.dark .search-row select {
            background: #1e293b;
            border-color: #334155;
            color: #f1f5f9;
        }
        body.dark .search-row input:focus,
        body.dark .search-row select:focus {
            border-color: #60a5fa;
            box-shadow: 0 0 0 3px rgba(96,165,250,0.25);
        }
        body.dark .search-row .btn {
            background: #1e293b;
            border-color: #334155;
            color: #f1f5f9;
        }
        body.dark .search-row .btn-primary {
            background: #2563eb;
            border-color: #2563eb;
            color: white;
        }
        body.dark .search-row .btn-primary:hover {
            background: #1d4ed8;
        }
        body.dark .table-wrapper {
            background: #1e293b;
            border-color: #334155;
        }
        body.dark .table-wrapper th {
            background: #0f172a;
            border-bottom-color: #334155;
        }
        body.dark .table-wrapper td {
            border-bottom-color: #334155;
        }
        body.dark .table-wrapper tr:nth-child(even) td {
            background: #1a2332;
        }
        body.dark .table-wrapper tr:hover td {
            background: #25344a;
        }
        body.dark .train-card {
            background: #1e293b;
            border-color: #334155;
        }
        body.dark .train-card .number {
            color: #60a5fa;
        }
        body.dark .train-card.total {
            background: #052e16;
            border-color: #16a34a;
        }
        body.dark .train-card.total .number {
            color: #4ade80;
        }
        body.dark .action-bar .btn,
        body.dark .extra-section .btn,
        body.dark .pagination .btn-group button {
            background: #1e293b;
            border-color: #334155;
            color: #f1f5f9;
        }
        body.dark .action-bar .btn:hover,
        body.dark .extra-section .btn:hover,
        body.dark .pagination .btn-group button:hover:not(:disabled) {
            background: #334155;
        }
        body.dark .action-bar .btn-danger {
            color: #f87171;
            border-color: #7f1d1d;
        }
        body.dark .action-bar .btn-danger:hover {
            background: #3f1a1a;
        }
        body.dark .action-bar .btn-success {
            background: #16a34a;
            border-color: #16a34a;
            color: white;
        }
        body.dark .action-bar .btn-success:hover {
            background: #15803d;
        }
        body.dark .action-bar .btn-primary {
            background: #2563eb;
            border-color: #2563eb;
            color: white;
        }
        body.dark .action-bar .btn-primary:hover {
            background: #1d4ed8;
        }
        body.dark .extra-section {
            border-top-color: #334155;
        }
        body.dark .footer {
            border-top-color: #334155;
            color: #94a3b8;
        }
        body.dark .sheet-header .badge {
            background: #334155;
            color: #f1f5f9;
        }

        /* ----- RESPONSIVE ----- */
        @media (max-width: 768px) {
            .top-bar { flex-direction: column; align-items: stretch; }
            .nav-buttons { justify-content: center; }
            .search-row { flex-direction: column; }
            .search-row input { flex: 1 1 auto; }
            .action-bar { justify-content: center; }
            .pagination { flex-direction: column; align-items: center; }
            .train-cards { justify-content: center; }
            .table-wrapper table { font-size: 0.75rem; min-width: 400px; }
        }
        @media print {
            .no-print { display: none !important; }
            body { background: white !important; color: black !important; }
            .table-wrapper { border: 1px solid #999; }
            .table-wrapper th { background: #333 !important; color: white !important; }
            .table-wrapper td { border: 1px solid #999; }
            .table-wrapper tr:nth-child(even) td { background: #f5f5f5 !important; }
        }
    </style>
</head>
<body>
    <div class="app-container">

        <!-- Theme Toggle -->
        <button class="theme-toggle no-print" id="themeToggle">
            <i class="fas fa-moon"></i> <span id="themeLabel">Dark</span>
        </button>

        <!-- Marquee -->
        <div class="marquee-box">
            <span class="scroll-text">🚂 Welcome to AI EQMS Hub Pro • Created by Sharique • Indian Railways • Emergency Quota Management System • Real-time Data • PNR Status • Live Train • Weather • Gemini AI • Google Sheets Integration • Drive Auto-Save</span>
        </div>

        <!-- Top Bar -->
        <div class="top-bar">
            <h1><i class="fas fa-train"></i> AI EQMS Hub Pro — EQ</h1>
            <div class="nav-buttons">
                <button class="nav-btn active"><i class="fas fa-table"></i> Data Table</button>
                <button class="nav-btn"><i class="fas fa-chart-bar"></i> Dashboard</button>
                <button class="nav-btn"><i class="fas fa-comment"></i> Chat</button>
                <button class="nav-btn"><i class="fas fa-railway"></i> Railway</button>
                <button class="nav-btn"><i class="fas fa-cloud-sun"></i> Weather</button>
            </div>
            <div>
                <span class="status-pill"><i class="fas fa-circle" style="font-size: 0.5rem;"></i> Live</span>
                <span style="font-size:13px; margin-left:8px;">Sync 15:30 IST</span>
            </div>
        </div>

        <!-- Sheet Header -->
        <div class="sheet-header">
            <h2><i class="fas fa-file-alt" style="color:#2563eb;"></i> EQ  <span class="badge">142 rows</span></h2>
            <button class="btn no-print" style="background:#f1f5f9; border:1px solid #cbd5e1; border-radius:30px; padding:6px 18px; font-weight:600; cursor:pointer;"><i class="fas fa-sync-alt"></i> Refresh</button>
        </div>

        <!-- Search & Filters -->
        <div class="search-row no-print">
            <input type="text" placeholder="🔍 Global Search (all columns)" style="flex:3;" />
            <input type="text" placeholder="PNR" style="flex:1;" />
            <input type="text" placeholder="Train" style="flex:1;" />
            <input type="date" style="flex:1;" />
            <input type="date" style="flex:1;" />
            <button class="btn"><i class="fas fa-undo-alt"></i> Clear</button>
        </div>

        <!-- Train Count Cards -->
        <div class="train-cards no-print">
            <div class="train-card total">
                <div class="number">142</div>
                <div class="label">Total EQ</div>
            </div>
            <div class="train-card">
                <div class="number">15909</div>
                <div class="label">12</div>
            </div>
            <div class="train-card">
                <div class="number">12423</div>
                <div class="label">8</div>
            </div>
            <div class="train-card">
                <div class="number">20505</div>
                <div class="label">6</div>
            </div>
            <div class="train-card">
                <div class="number">15645</div>
                <div class="label">5</div>
            </div>
            <div class="train-card">
                <div class="number">15946</div>
                <div class="label">4</div>
            </div>
            <div class="train-card">
                <div class="number">+ 8</div>
                <div class="label">more</div>
            </div>
        </div>

        <!-- Table -->
        <div class="table-wrapper">
            <table>
                <thead>
                    <tr>
                        <th class="checkbox-cell"><input type="checkbox" id="selectAll" /></th>
                        <th>S/N</th>
                        <th>PNR</th>
                        <th>FROM</th>
                        <th>TO</th>
                        <th>BOARDING</th>
                        <th>T/N</th>
                        <th>CLASS</th>
                        <th>DOJ</th>
                        <th>PASS NAME</th>
                        <th>PASS PH</th>
                        <th>T/BERTHS</th>
                        <th>PURPOSE</th>
                        <th>ADDRESS</th>
                        <th>DIARY NO</th>
                        <th>RECOMMENDATION</th>
                        <th>DESIGNATION</th>
                        <th>PHONE NUBER</th>
                        <th>VIP</th>
                        <th>WARRANT</th>
                    </tr>
                </thead>
                <tbody>
                    <!-- Row 1 -->
                    <tr>
                        <td class="checkbox-cell"><input type="checkbox" class="row-check" /></td>
                        <td>1</td>
                        <td>9085176759</td>
                        <td>NTSK</td>
                        <td>DLI</td>
                        <td>NTSK</td>
                        <td>15909</td>
                        <td>SL</td>
                        <td>28-06-2026</td>
                        <td>SHARIQUE</td>
                        <td>9876543210</td>
                        <td>1</td>
                        <td>Official</td>
                        <td>New Tinsukia</td>
                        <td>D/123</td>
                        <td>Mr. Sharma</td>
                        <td>DM</td>
                        <td>9876543211</td>
                        <td>—</td>
                        <td>IC-240</td>
                    </tr>
                    <!-- Row 2 -->
                    <tr>
                        <td class="checkbox-cell"><input type="checkbox" class="row-check" /></td>
                        <td>2</td>
                        <td>9085176760</td>
                        <td>GHY</td>
                        <td>NDLS</td>
                        <td>GHY</td>
                        <td>12423</td>
                        <td>3A</td>
                        <td>29-06-2026</td>
                        <td>RAHUL</td>
                        <td>9123456789</td>
                        <td>2</td>
                        <td>Family</td>
                        <td>Guwahati</td>
                        <td>D/456</td>
                        <td>Mrs. Verma</td>
                        <td>SP</td>
                        <td>9123456780</td>
                        <td>MP</td>
                        <td>MP-123</td>
                    </tr>
                    <!-- Row 3 -->
                    <tr>
                        <td class="checkbox-cell"><input type="checkbox" class="row-check" /></td>
                        <td>3</td>
                        <td>9085176761</td>
                        <td>NJP</td>
                        <td>HWH</td>
                        <td>NJP</td>
                        <td>20505</td>
                        <td>2A</td>
                        <td>30-06-2026</td>
                        <td>ANJALI</td>
                        <td>9988776655</td>
                        <td>1</td>
                        <td>Medical</td>
                        <td>New Jalpaiguri</td>
                        <td>D/789</td>
                        <td>Dr. Sen</td>
                        <td>CMO</td>
                        <td>9988776654</td>
                        <td>MINISTER</td>
                        <td>W/567</td>
                    </tr>
                    <!-- Row 4 -->
                    <tr>
                        <td class="checkbox-cell"><input type="checkbox" class="row-check" /></td>
                        <td>4</td>
                        <td>9085176762</td>
                        <td>DBRG</td>
                        <td>KYQ</td>
                        <td>DBRG</td>
                        <td>15645</td>
                        <td>SL</td>
                        <td>01-07-2026</td>
                        <td>VIKRAM</td>
                        <td>9871234567</td>
                        <td>3</td>
                        <td>Tourist</td>
                        <td>Dibrugarh</td>
                        <td>D/321</td>
                        <td>Mr. Singh</td>
                        <td>SDM</td>
                        <td>9871234568</td>
                        <td>—</td>
                        <td>—</td>
                    </tr>
                    <!-- Row 5 -->
                    <tr>
                        <td class="checkbox-cell"><input type="checkbox" class="row-check" /></td>
                        <td>5</td>
                        <td>9085176763</td>
                        <td>MXN</td>
                        <td>GKP</td>
                        <td>MXN</td>
                        <td>15946</td>
                        <td>3E</td>
                        <td>02-07-2026</td>
                        <td>PRIYA</td>
                        <td>9876541230</td>
                        <td>2</td>
                        <td>Official</td>
                        <td>Mariani</td>
                        <td>D/654</td>
                        <td>Mr. Gupta</td>
                        <td>SP</td>
                        <td>9876541231</td>
                        <td>ML</td>
                        <td>ML-456</td>
                    </tr>
                    <!-- Row 6 -->
                    <tr>
                        <td class="checkbox-cell"><input type="checkbox" class="row-check" /></td>
                        <td>6</td>
                        <td>9085176764</td>
                        <td>KYQ</td>
                        <td>PNBE</td>
                        <td>KYQ</td>
                        <td>12423</td>
                        <td>2S</td>
                        <td>03-07-2026</td>
                        <td>AMIT</td>
                        <td>9988112233</td>
                        <td>1</td>
                        <td>Business</td>
                        <td>Kamakhya</td>
                        <td>D/987</td>
                        <td>Mrs. Kaur</td>
                        <td>PS</td>
                        <td>9988112234</td>
                        <td>VIP</td>
                        <td>VIP-789</td>
                    </tr>
                    <!-- Row 7 -->
                    <tr>
                        <td class="checkbox-cell"><input type="checkbox" class="row-check" /></td>
                        <td>7</td>
                        <td>9085176765</td>
                        <td>NBQ</td>
                        <td>SC</td>
                        <td>NBQ</td>
                        <td>20505</td>
                        <td>1A</td>
                        <td>04-07-2026</td>
                        <td>NEHA</td>
                        <td>9871239876</td>
                        <td>2</td>
                        <td>Official</td>
                        <td>New Bongaigaon</td>
                        <td>D/147</td>
                        <td>Mr. Reddy</td>
                        <td>GM</td>
                        <td>9871239875</td>
                        <td>—</td>
                        <td>—</td>
                    </tr>
                    <!-- Row 8 -->
                    <tr>
                        <td class="checkbox-cell"><input type="checkbox" class="row-check" /></td>
                        <td>8</td>
                        <td>9085176766</td>
                        <td>FKG</td>
                        <td>BJU</td>
                        <td>FKG</td>
                        <td>15645</td>
                        <td>SL</td>
                        <td>05-07-2026</td>
                        <td>RAJESH</td>
                        <td>9988771122</td>
                        <td>3</td>
                        <td>Family</td>
                        <td>Furkating</td>
                        <td>D/258</td>
                        <td>Mr. Das</td>
                        <td>SP</td>
                        <td>9988771123</td>
                        <td>MP</td>
                        <td>MP-789</td>
                    </tr>
                    <!-- Row 9 -->
                    <tr>
                        <td class="checkbox-cell"><input type="checkbox" class="row-check" /></td>
                        <td>9</td>
                        <td>9085176767</td>
                        <td>NNA</td>
                        <td>JP</td>
                        <td>NNA</td>
                        <td>15909</td>
                        <td>3A</td>
                        <td>06-07-2026</td>
                        <td>SUNITA</td>
                        <td>9876543212</td>
                        <td>1</td>
                        <td>Tourist</td>
                        <td>Naugachia</td>
                        <td>D/369</td>
                        <td>Mr. Khan</td>
                        <td>SDM</td>
                        <td>9876543213</td>
                        <td>—</td>
                        <td>IC-567</td>
                    </tr>
                    <!-- Row 10 -->
                    <tr>
                        <td class="checkbox-cell"><input type="checkbox" class="row-check" /></td>
                        <td>10</td>
                        <td>9085176768</td>
                        <td>BGP</td>
                        <td>DDU</td>
                        <td>BGP</td>
                        <td>12423</td>
                        <td>2A</td>
                        <td>07-07-2026</td>
                        <td>DEEPAK</td>
                        <td>9871234560</td>
                        <td>2</td>
                        <td>Medical</td>
                        <td>Bhagalpur</td>
                        <td>D/741</td>
                        <td>Dr. Mehta</td>
                        <td>CMO</td>
                        <td>9871234561</td>
                        <td>MINISTER</td>
                        <td>W/890</td>
                    </tr>
                </tbody>
            </table>
        </div>

        <!-- Pagination -->
        <div class="pagination no-print">
            <div class="page-info">Page 1 of 15 &nbsp;|&nbsp; <strong>142 total rows</strong></div>
            <div class="btn-group">
                <button disabled><i class="fas fa-chevron-left"></i> Previous</button>
                <button>Next <i class="fas fa-chevron-right"></i></button>
            </div>
        </div>

        <!-- Action Bar -->
        <div class="action-bar no-print">
            <button class="btn btn-success"><i class="fas fa-save"></i> Save Edits</button>
            <button class="btn"><i class="fas fa-plus"></i> Add Row</button>
            <button class="btn btn-danger"><i class="fas fa-trash-alt"></i> Delete</button>
            <button class="btn btn-primary"><i class="fab fa-whatsapp"></i> WhatsApp Text</button>
            <button class="btn"><i class="fas fa-print"></i> PRINT</button>
        </div>

        <!-- Extra / Export -->
        <div class="extra-section no-print">
            <div style="font-weight:600; margin-bottom:6px;"><i class="fas fa-download"></i> Export</div>
            <div class="row">
                <button class="btn"><i class="fas fa-file-pdf"></i> PDF (All)</button>
                <button class="btn"><i class="fas fa-file-csv"></i> CSV (Selected)</button>
                <button class="btn"><i class="fas fa-file-excel"></i> Excel</button>
                <button class="btn"><i class="fas fa-copy"></i> Copy CSV</button>
                <button class="btn"><i class="fas fa-image"></i> Table Image</button>
                <button class="btn"><i class="fas fa-image"></i> Selected Image</button>
            </div>
        </div>

        <!-- Footer -->
        <div class="footer no-print">
            🚂 AI EQMS Hub Pro • Created by Sharique<br />
            © 2026 All Rights Reserved
        </div>

    </div>

    <script>
        (function() {
            // ----- THEME TOGGLE -----
            const toggleBtn = document.getElementById('themeToggle');
            const themeLabel = document.getElementById('themeLabel');
            let dark = false;

            toggleBtn.addEventListener('click', function() {
                dark = !dark;
                document.body.classList.toggle('dark', dark);
                themeLabel.textContent = dark ? 'Day' : 'Dark';
                toggleBtn.innerHTML = dark ?
                    '<i class="fas fa-sun"></i> <span id="themeLabel">Day</span>' :
                    '<i class="fas fa-moon"></i> <span id="themeLabel">Dark</span>';
            });

            // ----- SELECT ALL -----
            const selectAll = document.getElementById('selectAll');
            const rowChecks = document.querySelectorAll('.row-check');
            if (selectAll) {
                selectAll.addEventListener('change', function() {
                    rowChecks.forEach(cb => cb.checked = selectAll.checked);
                });
                rowChecks.forEach(cb => {
                    cb.addEventListener('change', function() {
                        const allChecked = Array.from(rowChecks).every(c => c.checked);
                        selectAll.checked = allChecked;
                    });
                });
            }

            // ----- NAV BUTTONS (demo) -----
            document.querySelectorAll('.nav-btn').forEach(btn => {
                btn.addEventListener('click', function() {
                    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
                    this.classList.add('active');
                });
            });

            // ----- PRINT (demo) -----
            document.querySelector('.action-bar .btn:last-child')?.addEventListener('click', function() {
                window.print();
            });

        })();
    </script>
</body>
</html>
