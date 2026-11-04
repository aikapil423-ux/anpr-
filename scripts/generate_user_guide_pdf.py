#!/usr/bin/env python3
"""
Haryana Police Smart Surveillance System - User Guide PDF Generator (Hinglish Edition)
Generates an exhaustive, operator-friendly User Manual in clean Hinglish covering strictly
the active AI models (YOLO11n, YOLO11_Plate, Awiros PP-OCRv5, SCRFD, ArcFace ResNet-34)
and every frontend button, toggle, modal, and drawer.
"""

import os
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT_DIR / "static"
OUTPUT_PDF_STATIC = STATIC_DIR / "haryana_police_user_guide.pdf"
OUTPUT_PDF_ROOT = ROOT_DIR / "Haryana_Police_Surveillance_User_Guide.pdf"
TEMP_HTML = ROOT_DIR / "scratch" / "user_guide_hinglish_print.html"

HTML_CONTENT = """<!DOCTYPE html>
<html lang="hi">
<head>
<meta charset="UTF-8">
<title>Haryana Police Smart Surveillance System - Complete User Guide (Hinglish)</title>
<style>
  @page {
    size: A4;
    margin: 18mm 16mm 18mm 16mm;
    @top-left {
      content: "HARYANA POLICE &bull; SMART SURVEILLANCE PLATFORM";
      font-family: 'Segoe UI', Arial, sans-serif;
      font-size: 8pt;
      font-weight: 700;
      color: #475569;
      letter-spacing: 0.05em;
    }
    @top-right {
      content: "OFFICIAL LAW ENFORCEMENT MANUAL (HINGLISH)";
      font-family: 'Segoe UI', Arial, sans-serif;
      font-size: 8pt;
      font-weight: 700;
      color: #dc2626;
      letter-spacing: 0.05em;
    }
    @bottom-left {
      content: "ANPR & FRS Unified Frontend Guide v2.4";
      font-family: 'Segoe UI', Arial, sans-serif;
      font-size: 8pt;
      color: #64748b;
    }
    @bottom-right {
      content: "Page " counter(page) " of " counter(pages);
      font-family: 'Segoe UI', Arial, sans-serif;
      font-size: 8pt;
      font-weight: 600;
      color: #1e293b;
    }
  }

  body {
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, Helvetica, Arial, sans-serif;
    color: #1e293b;
    background-color: #ffffff;
    line-height: 1.6;
    font-size: 9.8pt;
    margin: 0;
    padding: 0;
  }

  .page-break {
    page-break-after: always;
    break-after: page;
  }
  .avoid-break {
    page-break-inside: avoid;
    break-inside: avoid;
  }

  /* Cover Page */
  .cover-page {
    min-height: 250mm;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    padding: 20mm 10mm 15mm 10mm;
    box-sizing: border-box;
    text-align: center;
  }
  .emblem-badge {
    display: inline-block;
    background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 100%);
    color: #f8fafc;
    padding: 12px 28px;
    border-radius: 50px;
    font-weight: 800;
    letter-spacing: 2px;
    font-size: 11pt;
    border: 2px solid #38bdf8;
    box-shadow: 0 4px 15px rgba(30, 58, 138, 0.2);
    margin-bottom: 25px;
  }
  .cover-title {
    font-size: 25pt;
    font-weight: 900;
    color: #0f172a;
    line-height: 1.25;
    margin: 15px 0 10px 0;
    text-transform: uppercase;
  }
  .cover-subtitle {
    font-size: 13.5pt;
    color: #2563eb;
    font-weight: 700;
    margin-bottom: 25px;
  }
  .cover-divider {
    width: 140px;
    height: 4px;
    background: linear-gradient(90deg, #2563eb, #38bdf8);
    margin: 0 auto 25px auto;
    border-radius: 2px;
  }
  .cover-desc {
    font-size: 10.5pt;
    color: #475569;
    max-width: 600px;
    margin: 0 auto 35px auto;
    line-height: 1.7;
  }
  .cover-metadata-box {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 18px 26px;
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 14px;
    text-align: left;
    max-width: 600px;
    margin: 0 auto 35px auto;
  }
  .meta-item strong {
    display: block;
    font-size: 8pt;
    text-transform: uppercase;
    color: #64748b;
    letter-spacing: 0.5px;
  }
  .meta-item span {
    font-size: 9.5pt;
    color: #0f172a;
    font-weight: 600;
  }
  .cover-footer {
    font-size: 8.5pt;
    color: #94a3b8;
    border-top: 1px solid #e2e8f0;
    padding-top: 15px;
  }

  /* Headings */
  h1 {
    font-size: 16pt;
    font-weight: 800;
    color: #0f172a;
    border-bottom: 2px solid #e2e8f0;
    padding-bottom: 8px;
    margin-top: 22px;
    margin-bottom: 12px;
    display: flex;
    align-items: center;
    gap: 10px;
  }
  h1 .chapter-num {
    background: #2563eb;
    color: #ffffff;
    font-size: 10pt;
    padding: 3px 9px;
    border-radius: 6px;
    font-weight: 700;
  }
  h2 {
    font-size: 12pt;
    font-weight: 700;
    color: #1e293b;
    margin-top: 18px;
    margin-bottom: 8px;
    padding-left: 9px;
    border-left: 4px solid #38bdf8;
  }
  h3 {
    font-size: 10.5pt;
    font-weight: 700;
    color: #334155;
    margin-top: 14px;
    margin-bottom: 6px;
  }
  p {
    margin: 0 0 9px 0;
    color: #334155;
  }

  /* Tables */
  table {
    width: 100%;
    border-collapse: collapse;
    margin: 10px 0 16px 0;
    font-size: 8.8pt;
  }
  th {
    background: #0f172a;
    color: #ffffff;
    text-align: left;
    padding: 7px 9px;
    font-weight: 600;
    border: 1px solid #0f172a;
  }
  td {
    padding: 7px 9px;
    border: 1px solid #cbd5e1;
    vertical-align: top;
  }
  tr:nth-child(even) td {
    background-color: #f8fafc;
  }

  /* Badges & Buttons */
  .badge {
    display: inline-block;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 7.5pt;
    font-weight: 700;
    text-transform: uppercase;
    white-space: nowrap;
  }
  .badge-primary { background: #dbeafe; color: #1e40af; border: 1px solid #bfdbfe; }
  .badge-danger { background: #fee2e2; color: #991b1b; border: 1px solid #fecaca; }
  .badge-warning { background: #fef3c7; color: #92400e; border: 1px solid #fde68a; }
  .badge-success { background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; }
  .badge-secondary { background: #f1f5f9; color: #475569; border: 1px solid #e2e8f0; }

  code {
    font-family: Consolas, Monaco, monospace;
    font-size: 8.5pt;
    background: #f1f5f9;
    color: #0f172a;
    padding: 1px 4px;
    border-radius: 4px;
    border: 1px solid #e2e8f0;
  }
  .btn-id {
    font-family: Consolas, Monaco, monospace;
    font-size: 8.2pt;
    font-weight: 700;
    color: #1e3a8a;
    background: #eff6ff;
    padding: 2px 5px;
    border-radius: 4px;
    border: 1px solid #bfdbfe;
    display: inline-block;
  }

  /* Callouts */
  .callout {
    border-radius: 8px;
    padding: 11px 14px;
    margin: 12px 0;
    font-size: 9.2pt;
    border-left: 4px solid #1e3a8a;
    background: #f8fafc;
    border-top: 1px solid #e2e8f0;
    border-right: 1px solid #e2e8f0;
    border-bottom: 1px solid #e2e8f0;
  }

  .grid-2 {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 10px;
    margin: 10px 0;
  }
  .feature-card {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 11px 13px;
  }
  .feature-card h4 {
    margin: 0 0 5px 0;
    font-size: 9.5pt;
    color: #0f172a;
  }

  .step-box {
    margin: 8px 0;
    padding: 9px 12px;
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    display: flex;
    gap: 10px;
  }
  .step-number {
    background: #2563eb;
    color: #ffffff;
    width: 22px;
    height: 22px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: 8.5pt;
    flex-shrink: 0;
  }
  .step-content {
    flex: 1;
    font-size: 9pt;
  }
</style>
</head>
<body>

<!-- COVER PAGE -->
<div class="cover-page page-break">
  <div>
    <div class="emblem-badge">HARYANA POLICE &bull; STATE CRIME RECORDS BUREAU</div>
    <div class="cover-title">SMART SURVEILLANCE USER GUIDE</div>
    <div class="cover-subtitle">Complete Operational Manual in Hinglish (ANPR + FRS)</div>
    <div class="cover-divider"></div>
    <div class="cover-desc">
      Ye Haryana Police Surveillance System ka official operator manual hai. Isme frontend ke har ek button, switch, input field, modal, sliding drawer aur live AI detection pipeline ki step-by-step working saral <strong>Hinglish</strong> me explain ki gayi hai.
    </div>
  </div>

  <div class="cover-metadata-box">
    <div class="meta-item">
      <strong>Document ID:</strong>
      <span>HP-SURV-GUIDE-HINGLISH-V2.4</span>
    </div>
    <div class="meta-item">
      <strong>Active Release:</strong>
      <span>Production v2.4 (Ready for Deployment)</span>
    </div>
    <div class="meta-item">
      <strong>Currently Active Models:</strong>
      <span>YOLO11n + Awiros PP-OCRv5 + SCRFD + ArcFace R34</span>
    </div>
    <div class="meta-item">
      <strong>Fallback Engine:</strong>
      <span>EasyOCR (Auto-Fallback Enabled)</span>
    </div>
    <div class="meta-item">
      <strong>Web Dashboard Port:</strong>
      <span>http://localhost:8000 &bull; http://0.0.0.0:8000</span>
    </div>
    <div class="meta-item">
      <strong>Language Format:</strong>
      <span>Natural Hinglish (Roman Hindi + English Tech Terms)</span>
    </div>
  </div>

  <div class="cover-footer">
    &copy; 2026 Haryana Police Department. Confidential &bull; For Law Enforcement & Control Room Personnel Only.
  </div>
</div>

<!-- CHAPTER 1: SYSTEM & ACTIVE MODELS OVERVIEW -->
<div>
  <h1><span class="chapter-num">CH 01</span> System Overview & Active AI Models</h1>
  
  <p>Hamara system Haryana ke highways, toll plazas, city entry gates aur sensitive locations par lagaane ke liye banaya gaya hai. Ye ek <strong>Unified System</strong> hai jo ek sath do kaam karta hai:</p>
  <ul>
    <li><strong>ANPR (Automatic Number Plate Recognition):</strong> Gaadiyon (Car, Truck, Bus, Bike) ko detect karta hai, unki plate dhundhta hai aur plate number read karta hai.</li>
    <li><strong>FRS (Facial Recognition System):</strong> Frame me maujood logo ke chehre detect karta hai aur police watchlists (Suspects/Wanted) ke sath match karta hai.</li>
  </ul>

  <h2>System me Currently Kon-Konse AI Models Use Ho Rahe Hain?</h2>
  <p>Project me strictly wahi models active hain jo humne configure aur verify kiye hain (koi fake ya extra model nahi hai):</p>

  <table>
    <thead>
      <tr>
        <th style="width: 22%;">AI Model Name</th>
        <th style="width: 20%;">Model File Path</th>
        <th style="width: 18%;">Framework / Size</th>
        <th style="width: 40%;">Kaam (Exact Role in Pipeline)</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><strong>YOLO11n (Vehicle)</strong></td>
        <td><code>models/yolo/yolo11n.pt</code></td>
        <td>PyTorch / ~5.4 MB</td>
        <td>Frame me cars, trucks, motorcycles aur buses ko detect karta hai aur <strong>ByteTrack</strong> se unhe track ID assign karta hai.</td>
      </tr>
      <tr>
        <td><strong>YOLO11_Plate</strong></td>
        <td><code>models/yolo/yolo11_plate.pt</code></td>
        <td>PyTorch / ~5.5 MB</td>
        <td>Gaadi ke andar number plate ke exact coordinates (tight bounding box) ko locate karta hai.</td>
      </tr>
      <tr>
        <td><strong>Awiros PP-OCRv5</strong></td>
        <td><code>models/awiros_anpr/model.safetensors</code></td>
        <td>PaddlePaddle / 142.5 MB</td>
        <td><strong>Hamara main Indian ANPR OCR engine.</strong> Ye 37.3M parameter SVTR_HGNet CTC model hai jo Indian number plates ko high accuracy ke sath read karta hai.</td>
      </tr>
      <tr>
        <td><strong>EasyOCR Fallback</strong></td>
        <td><code>src/ocr/ocr_engine.py</code></td>
        <td>PyTorch / Built-in</td>
        <td>Agar kisi karan se Awiros model na mile ya load na ho, to ye system ko crash hone se bachata hai aur plate automatically read kar leta hai ("UNREADABLE" error nahi aane deta).</td>
      </tr>
      <tr>
        <td><strong>SCRFD 10G</strong></td>
        <td><code>models/frs/scrfd_10g_bnkps.onnx</code></td>
        <td>ONNX Runtime / ~16.9 MB</td>
        <td>Frame me se human faces ko detect karta hai aur 5 facial landmarks (dono aankhein, naak aur lips) nikaalta hai.</td>
      </tr>
      <tr>
        <td><strong>ArcFace ResNet-34</strong></td>
        <td><code>models/frs/arcface_r34.onnx</code></td>
        <td>ONNX Runtime / 130.3 MB</td>
        <td>Chehre ka 512-dimensional vector embedding nikaalta hai jise hum database me match karne ke liye use karte hain.</td>
      </tr>
    </tbody>
  </table>

  <div class="callout">
    <strong>💡 Dhyan Dein:</strong> Heavy models (<code>model.safetensors</code> aur <code>arcface_r34.onnx</code>) private GitHub Releases (<code>v1.0-weights</code>) par securely host hain aur <code>python scripts/download_models.py</code> chala kar kisi bhi fresh machine par automatically download ho jaate hain.
  </div>
</div>

<div class="page-break"></div>

<!-- CHAPTER 2: NAVIGATION SIDEBAR -->
<div>
  <h1><span class="chapter-num">CH 02</span> Navigation Sidebar & Main Menu</h1>
  
  <p>Dashboard ke left-hand side me persistent dark navigation bar diya gaya hai jisse operator bina page refresh kiye alag-alag modules me switch kar sakta hai:</p>

  <table>
    <thead>
      <tr>
        <th style="width: 25%;">Sidebar Button & ID</th>
        <th style="width: 15%;">Button Type</th>
        <th style="width: 60%;">Working (Button dabane se kya hota hai?)</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><span class="btn-id">navDashboardBtn</span><br><strong>Live Surveillance Hub</strong></td>
        <td><span class="badge badge-primary">Main Tab</span></td>
        <td>Is button ko dabane se aap <strong>Live Monitoring Screen</strong> par aa jaate hain jahan live camera feeds, 2x2 grid, aur video overlays dikhte hain.</td>
      </tr>
      <tr>
        <td><span class="btn-id">navMasterDbBtn</span><br><strong>Master DB Registry</strong></td>
        <td><span class="badge badge-primary">Main Tab</span></td>
        <td>Is par click karne se <strong>Criminal & Stolen Watchlists</strong> khulti hain jahan chori ki gaadiyan aur wanted suspects ki entry ki jaati hai.</td>
      </tr>
      <tr>
        <td><span class="btn-id">navMasterTrailBtn</span><br><strong>Master Trail</strong></td>
        <td><span class="badge badge-primary">Main Tab</span></td>
        <td>Is par click karne se <strong>Master Trail</strong> view khulta hai, jahan kisi gaadi ya shaqsiat ki timeline aur camera corridor tracking dikhti hai.</td>
      </tr>
      <tr>
        <td><span class="btn-id">navOpenVehiclesDrawerBtn</span><br><strong>Captured Vehicles</strong></td>
        <td><span class="badge badge-warning">Slide Drawer</span></td>
        <td>Screen ke right side se ek sliding drawer khul jaata hai jisme live cameras dwara capture ki gayi saari gaadiyan unke plate crop ke sath dikhti hain.</td>
      </tr>
      <tr>
        <td><span class="btn-id">navOpenFacesDrawerBtn</span><br><strong>Captured Faces</strong></td>
        <td><span class="badge badge-danger">Slide Drawer</span></td>
        <td>Screen ke right side se sliding drawer khulta hai jisme camera me aane wale har insaan ka face crop aur match score dikhta hai.</td>
      </tr>
    </tbody>
  </table>

  <h2>Global Status Badges (Header Bar)</h2>
  <div class="grid-2">
    <div class="feature-card">
      <h4>🟢 Live Stream Beacon</h4>
      <p style="font-size: 8.5pt; color: #475569;">
        Agar beacon green hai aur blink kar raha hai to iska matlab backend WebSocket aur camera feed live hai aur sub-50ms latency ke sath chal raha hai.
      </p>
    </div>
    <div class="feature-card">
      <h4>🚨 Live Hit Alarm</h4>
      <p style="font-size: 8.5pt; color: #475569;">
        Jaise hi koi chori ki gaadi (Hotlist) ya wanted suspect camera ke samne aayega, header me red alarm bar flashing alert dikhane lagta hai.
      </p>
    </div>
  </div>
</div>

<div class="page-break"></div>

<!-- CHAPTER 3: LIVE SURVEILLANCE HUB & HUD BUTTONS -->
<div>
  <h1><span class="chapter-num">CH 03</span> Live Surveillance Hub & HUD Overlays</h1>
  
  <p>Live Surveillance Hub par operator camera feed dekhta hai aur screen par dikhne wale boxes/text ko control karta hai.</p>

  <h2>1. View Mode Switcher (Screen Layout Buttons)</h2>
  <table>
    <thead>
      <tr>
        <th style="width: 22%;">Button Name</th>
        <th style="width: 20%;">HTML ID</th>
        <th style="width: 58%;">Working & Output</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><strong>1x1 Focus</strong></td>
        <td><span class="btn-id">btnView1x1</span></td>
        <td>Is button ko dabane se grid band ho jaati hai aur <strong>single selected camera</strong> poori screen par maximize ho jaata hai taaki plate aur face saaf dikhein.</td>
      </tr>
      <tr>
        <td><strong>2x2 Grid</strong></td>
        <td><span class="btn-id">btnView2x2</span></td>
        <td>Is button se screen <strong>4 barabar hisson (CAM-01, CAM-02, CAM-03, CAM-04)</strong> me divide ho jaati hai jisse ek sath 4 cameras monitor hote hain.</td>
      </tr>
      <tr>
        <td><strong>Fullscreen</strong></td>
        <td><span class="btn-id">btnStreamFullscreen</span></td>
        <td>Video feed ko computer ki poori physical monitor screen par fullscreen mode me open karta hai.</td>
      </tr>
    </tbody>
  </table>

  <h2>2. Live HUD Preset Buttons (One-Click Layer Modes)</h2>
  <p>Agar operator ko baar-baar checkboxes on/off na karni ho to ye 4 preset buttons hain:</p>
  <table>
    <thead>
      <tr>
        <th style="width: 20%;">Preset Button</th>
        <th style="width: 20%;">HTML ID</th>
        <th style="width: 60%;">Working (Button dabate hi kya hota hai?)</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><strong>Raw Feed</strong></td>
        <td><span class="btn-id">btnPresetRaw</span></td>
        <td>Saare bounding boxes, boxes aur text band ho jaate hain. Screen par <strong>100% clean video feed</strong> dikhai deti hai bina kisi AI graphics ke.</td>
      </tr>
      <tr>
        <td><strong>ANPR Only</strong></td>
        <td><span class="btn-id">btnPresetPlate</span></td>
        <td>Chehre aur insaan ke boxes band ho jaate hain; sirf <strong>number plate ka box aur read kiya gaya plate number text</strong> dikhta hai.</td>
      </tr>
      <tr>
        <td><strong>FRS Only</strong></td>
        <td><span class="btn-id">btnPresetFrs</span></td>
        <td>Gaadiyon aur number plate ke boxes band ho jaate hain; sirf <strong>human faces, 5 landmarks aur head count</strong> dikhta hai.</td>
      </tr>
      <tr>
        <td><strong>All Layers</strong></td>
        <td><span class="btn-id">btnPresetAll</span></td>
        <td><strong>Sabhi AI overlays ek sath chalu ho jaate hain:</strong> Vehicle, ByteTrack ID, Plate box, Plate text, Person, Face, Landmarks aur Counter.</td>
      </tr>
    </tbody>
  </table>

  <h2>3. Individual Layer Checkboxes (Custom Filters)</h2>
  <p>Operator apni marzi ke hisab se kisi bhi visual element ko tick ya untick kar sakta hai:</p>
  <table>
    <thead>
      <tr>
        <th style="width: 28%;">Checkbox ID</th>
        <th style="width: 24%;">Overlay Element</th>
        <th style="width: 48%;">Working (Checkbox On/Off karne se kya badalega?)</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><span class="btn-id">layerToggleVehicle</span></td>
        <td>Vehicle Box</td>
        <td>Gaadi ke charon taraf green rectangular box dikhana ya chupana.</td>
      </tr>
      <tr>
        <td><span class="btn-id">layerToggleBytetrack</span></td>
        <td>ByteTrack ID</td>
        <td>Gaadi ka unique continuous tracking number (e.g. <code>TRK-14</code>) dikhana.</td>
      </tr>
      <tr>
        <td><span class="btn-id">layerTogglePlate</span></td>
        <td>Plate Box</td>
        <td>License plate ke charon taraf ka tight box toggle karna.</td>
      </tr>
      <tr>
        <td><span class="btn-id">layerToggleOcr</span></td>
        <td>OCR Text & Conf</td>
        <td>Plate ke upar read kiya gaya text (e.g. <code>HR26AB1234</code>) aur confidence % dikhana.</td>
      </tr>
      <tr>
        <td><span class="btn-id">layerTogglePerson</span></td>
        <td>Person Box</td>
        <td>Pedestrians (chalte huye logo) ke charon taraf cyan box toggle karna.</td>
      </tr>
      <tr>
        <td><span class="btn-id">layerToggleFace</span></td>
        <td>Face Box</td>
        <td>Human face ke upar ka box. Normal face par amber, suspect par red dikhta hai.</td>
      </tr>
      <tr>
        <td><span class="btn-id">layerToggleLandmarks</span></td>
        <td>5 Landmarks</td>
        <td>Chehre ke 5 alignment points (eyes, nose, mouth corners) draw karna.</td>
      </tr>
      <tr>
        <td><span class="btn-id">layerToggleCounter</span></td>
        <td>Live Tally Counter</td>
        <td>Screen ke corner me live total vehicles aur active people count card dikhana.</td>
      </tr>
    </tbody>
  </table>
</div>

<div class="page-break"></div>

<!-- CHAPTER 4: CONNECT FEED MODAL -->
<div>
  <h1><span class="chapter-num">CH 04</span> Connect Feed Modal & Tile Controls</h1>
  
  <p>Camera feed connect karne ke liye header me <span class="btn-id">btnOpenConnectModal</span> (<strong>Connect Feed</strong>) ya kisi tile par <span class="btn-id">+ Connect</span> par click karein.</p>

  <h2>1. Feed Types (Input Source Tabs)</h2>
  <div class="step-box">
    <div class="step-number">1</div>
    <div class="step-content">
      <strong>📹 USB Webcam:</strong> Local computer se jude webcam ko chalata hai (Index <code>0</code> laptop webcam, <code>1</code> external USB camera).
    </div>
  </div>
  <div class="step-box">
    <div class="step-number">2</div>
    <div class="step-content">
      <strong>🌐 RTSP Stream:</strong> Highway ya checkpost ke network IP camera ka RTSP link dalne ke liye (e.g., <code>rtsp://admin:pass@192.168.1.100:554/ch01</code>).
    </div>
  </div>
  <div class="step-box">
    <div class="step-number">3</div>
    <div class="step-content">
      <strong>🔗 HTTP / HTTPS:</strong> Web M-JPEG camera feeds ya live stream IP links ke liye.
    </div>
  </div>
  <div class="step-box">
    <div class="step-number">4</div>
    <div class="step-content">
      <strong>🎬 Loop Demo:</strong> Testing ya demo ke liye sample video files ko continuous loop me chalata hai.
    </div>
  </div>

  <h2>2. Camera Configuration Fields & Buttons</h2>
  <table>
    <thead>
      <tr>
        <th style="width: 25%;">Field / Button ID</th>
        <th style="width: 20%;">Type</th>
        <th style="width: 55%;">Working (Iska use kaise karein?)</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><strong>Camera ID</strong></td>
        <td>Dropdown</td>
        <td>Select karein ki ye camera grid ke kis tile me chalana hai: <code>CAM-01</code>, <code>CAM-02</code>, <code>CAM-03</code> ya <code>CAM-04</code>.</td>
      </tr>
      <tr>
        <td><strong>Camera Name / Location</strong></td>
        <td>Text Input</td>
        <td>Camera ka naam likhein (e.g. <em>"Kundli Border Toll Lane 2"</em> ya <em>"Karnal Highway Checkpost"</em>).</td>
      </tr>
      <tr>
        <td><span class="btn-id">btnDetectGps</span><br><strong>📍 Auto-Detect GPS</strong></td>
        <td><span class="badge badge-primary">GPS Button</span></td>
        <td><strong>Auto-GPS Button:</strong> Is button ko dabate hi browser location mangta hai aur system automatic Latitude aur Longitude fill kar deta hai.</td>
      </tr>
      <tr>
        <td><span class="btn-id">btnSubmitConnect</span><br><strong>Connect & Start Feed</strong></td>
        <td><span class="badge badge-success">Submit</span></td>
        <td>Capture background thread launch karta hai aur live AI video stream start ho jaati hai.</td>
      </tr>
      <tr>
        <td><span class="btn-id">btnCancelConnectModal</span><br><strong>Cancel</strong></td>
        <td><span class="badge badge-secondary">Cancel</span></td>
        <td>Modal ko band kar deta hai bina koi stream change kiye.</td>
      </tr>
      <tr>
        <td><span class="btn-id">btnDisconnectStream</span><br><strong>Disconnect</strong></td>
        <td><span class="badge badge-danger">Disconnect</span></td>
        <td>Header bar me maujood ye button active running video stream ko stop karke release kar deta hai.</td>
      </tr>
    </tbody>
  </table>

  <h2>3. Per-Camera Tile Buttons (Hover Controls)</h2>
  <ul>
    <li><strong>Focus Button (Maximize Icon):</strong> Us specific camera ko turant 1x1 full view me le aata hai.</li>
    <li><strong>Disconnect Button (Cross Icon):</strong> Sirf us specific channel ki streaming band karta hai.</li>
    <li><strong>Tile ANPR Checkbox (<code>tileToggleAnpr-CAM-XX</code>):</strong> Agar system par CPU/GPU load kam karna ho to kisi camera par ANPR AI processing band karke sirf video chalu rakh sakte hain.</li>
  </ul>
</div>

<div class="page-break"></div>

<!-- CHAPTER 5: CAPTURED DRAWERS & SIGHTINGS -->
<div>
  <h1><span class="chapter-num">CH 05</span> Real-Time Sighting Drawers & Alarms</h1>
  
  <p>Camera ke samne se jaise hi koi gaadi ya vyakti nikalta hai, system automatic snapshot lekar sliding inspection drawer me entry add kar deta hai.</p>

  <h2>1. Captured Vehicles Drawer (`#vehiclesDrawer`)</h2>
  <p>Sidebar me <span class="btn-id">navOpenVehiclesDrawerBtn</span> dabane par right side se khulta hai:</p>

  <table>
    <thead>
      <tr>
        <th style="width: 25%;">Control / Button ID</th>
        <th style="width: 20%;">Element Type</th>
        <th style="width: 55%;">Working & Operation</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><span class="btn-id">drawerVehFilterAll</span></td>
        <td>Filter Button</td>
        <td>Live stream me detect huyi <strong>sabhyi gaadiyon</strong> ki list dikhata hai.</td>
      </tr>
      <tr>
        <td><span class="btn-id">drawerVehFilterHotlist</span></td>
        <td>Filter Button</td>
        <td>Sirf wahi gaadiyan filter karta hai jo <strong>Police FIR ya Chori (Stolen)</strong> me wanted hain (Hotlist Hits).</td>
      </tr>
      <tr>
        <td><span class="btn-id">window.refreshDrawerVehicles</span></td>
        <td>Refresh Icon</td>
        <td>SQLite database (<code>captured_db.sqlite</code>) se latest sightings fetch karke card list update karta hai.</td>
      </tr>
      <tr>
        <td><span class="btn-id">window.clearAllCapturedVehicles</span></td>
        <td>Clear Button</td>
        <td>Confirmation mangne ke baad temporary live captured vehicles ki list ko clear kar deta hai.</td>
      </tr>
      <tr>
        <td><span class="btn-id">.side-drawer-close</span></td>
        <td>Close (×)</td>
        <td>Sliding drawer ko wapas band karke live video screen ka poora view dikhata hai.</td>
      </tr>
    </tbody>
  </table>

  <h3>Sighting Detail Modal (`#captureDetailModal`):</h3>
  <p>Kisi bhi gaadi ke card par click karne par ye modal khulta hai jisme:</p>
  <ul>
    <li><strong>Full Scene Photo:</strong> Camera ka poora frame jisme gaadi apni lane me dikhti hai.</li>
    <li><strong>Tight Plate Crop:</strong> Number plate ka 4x magnified enhanced photo.</li>
    <li><strong>Plate Diagnostics:</strong> Read kiya gaya number (e.g. <code>DL3CCY7011</code>), OCR confidence %, aur skew angle.</li>
    <li><strong>Hotlist Case Alert:</strong> Agar gaadi stolen hai to FIR No, Police Station aur IO Contact details crimson red me flashing aati hain.</li>
  </ul>

  <h2>2. Captured Faces Drawer (`#facesDrawer`)</h2>
  <p>Sidebar me <span class="btn-id">navOpenFacesDrawerBtn</span> dabane par right side se khulta hai:</p>
  <ul>
    <li><code>drawerFaceFilterAll</code>: Saare detect huye chehre dikhata hai.</li>
    <li><code>drawerFaceFilterMatch</code>: Sirf wahi chehre dikhata hai jo police database ke suspects se <strong>match</strong> huye hain.</li>
    <li><code>drawerFaceFilterSuspect</code>: Sirf <strong>Wanted Criminals / FIR Accused</strong> ko filter karta hai.</li>
    <li><code>drawerFaceFilterVip</code> / <code>drawerFaceFilterStaff</code>: VIP ya Staff categorised chehre filter karta hai.</li>
    <li><strong>Face Sighting Modal (`#frsCaptureDetailModal`):</strong> Chehre ka 112x112 aligned crop aur enrolled gallery photo ko side-by-side match percentage ke sath dikhata hai.</li>
  </ul>
</div>

<div class="page-break"></div>

<!-- CHAPTER 6: MASTER DB REGISTRY -->
<div>
  <h1><span class="chapter-num">CH 06</span> Master DB Registry (Watchlists Management)</h1>
  
  <p>Master DB me police watchlists maintain ki jaati hain. Sidebar me <span class="btn-id">navMasterDbBtn</span> dabakar isme jate hain.</p>

  <h2>1. Vehicle DB Registry (`subtabVehicleDbBtn`)</h2>
  <p>Yahan stolen ya crime me involved gaadiyon ka record manage hota hai:</p>

  <table>
    <thead>
      <tr>
        <th style="width: 25%;">Control / Button ID</th>
        <th style="width: 20%;">Type</th>
        <th style="width: 55%;">Working & Police Use</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><span class="btn-id">dbSearchInput</span></td>
        <td>Search Box</td>
        <td>Plate number, FIR number, police station ya car color daal kar instant search karein.</td>
      </tr>
      <tr>
        <td><strong>All Records / FIR / Stolen</strong></td>
        <td>Filter Pills</td>
        <td>Category wise gaadiyon ki table ko filter karne ke liye.</td>
      </tr>
      <tr>
        <td><span class="btn-id">btnOpenRegisterModal</span><br><strong>Register New Vehicle</strong></td>
        <td><span class="badge badge-primary">Modal Trigger</span></td>
        <td>Nayi wanted/stolen gaadi add karne ke liye registration form open karta hai.</td>
      </tr>
    </tbody>
  </table>

  <h3>Vehicle Registration Form Inputs (`#registerModal`):</h3>
  <ul>
    <li><code>regPlate</code>: Gaadi ka registration number (e.g. <code>HR26DA1234</code>).</li>
    <li><code>regType</code>: Gaadi ki category select karein (Car, Motorcycle, Truck, Bus).</li>
    <li><code>regColor</code>: Gaadi ka rang (White, Black, Silver, etc.).</li>
    <li><code>regLocation</code>: Last known location ya owner ka address.</li>
    <li><code>involvedInCase</code>: Radio button (Yes / No).</li>
    <li><code>regOffenceType</code>: Apradh ki category (Theft, Robbery, Hit & Run, Kidnapping, Narcotics).</li>
    <li><code>regFirNumber</code>: FIR Number (e.g. <code>FIR-142/2026</code>).</li>
    <li><code>regPoliceStation</code>: Thana ka naam (e.g. <em>PS City Panipat</em>).</li>
    <li><span class="btn-id">saveVehicleBtn</span> (<strong>Save to Vehicle DB</strong>): Record ko SQLite database (<code>data/vehicle_db.sqlite</code>) me permanently save karta hai.</li>
  </ul>

  <h2>2. Face DB Registry (`subtabFaceDbBtn`)</h2>
  <p>Yahan wanted suspects aur VIPs ke chehre enroll kiye jaate hain:</p>
  <ul>
    <li><span class="btn-id">faceDbSearchInput</span>: Naam ya case ID se enrolled suspect ko search karein.</li>
    <li><span class="btn-id">btnOpenEnrollModal</span> (<strong>Enroll New Face</strong>): Face enrollment form open karta hai.</li>
  </ul>

  <h3>Face Enrollment Form Inputs (`#enrollModal`):</h3>
  <ul>
    <li><code>enrollPersonName</code>: Suspect ka poora naam ya criminal alias.</li>
    <li><code>enrollCategory</code>: Dropdown se category chunein (<code>SUSPECT</code>, <code>VIP</code>, <code>STAFF</code>, <code>SECURITY</code>).</li>
    <li><code>enrollMetadata</code>: Case reference number ya criminal dossier ID.</li>
    <li><code>enrollPhotoFile</code>: Suspect ki passport-size ya frontal photo upload karein. <strong>System usi waqt ArcFace ResNet-34 model se 512-D vector feature embedding nikaal leta hai.</strong></li>
    <li><span class="btn-id">submitEnrollBtn</span> (<strong>Save to Face DB</strong>): Record aur vector embedding ko <code>data/frs/face_db.sqlite</code> me save karta hai.</li>
  </ul>
</div>

<div class="page-break"></div>

<!-- CHAPTER 7: MASTER TRAIL & CORRIDOR TRACKING -->
<div>
  <h1><span class="chapter-num">CH 07</span> Master Trail & Journey Corridor Tracking</h1>
  
  <p>Master Trail police investigation ka sabse zaroori tool hai. Ye kisi suspect gaadi ya vyakti ki <strong>timeline</strong> banata hai ki wo kis time par kis camera ke samne se guzra aur kis taraf ja raha hai.</p>

  <h2>Master Trail Controls</h2>
  <table>
    <thead>
      <tr>
        <th style="width: 25%;">Control / Button ID</th>
        <th style="width: 20%;">Type</th>
        <th style="width: 55%;">Working (Investigation me kaise use karein?)</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><span class="btn-id">subtabVehicleTrailBtn</span></td>
        <td>Subtab</td>
        <td>Gaadiyon ke camera passage corridors dekhne ke liye.</td>
      </tr>
      <tr>
        <td><span class="btn-id">subtabFaceTrailBtn</span></td>
        <td>Subtab</td>
        <td>Enrolled suspects ke camera passage corridors dekhne ke liye.</td>
      </tr>
      <tr>
        <td><span class="btn-id">trailSearchInput</span></td>
        <td>Search Box</td>
        <td>Target plate number (e.g. <code>HR08AH3647</code>) daal kar corridor filter karein.</td>
      </tr>
      <tr>
        <td><span class="btn-id">btnApplyTrailFilters</span></td>
        <td>Filter Button</td>
        <td>Date aur time range apply karta hai (e.g. pichle 24 ghante ka record).</td>
      </tr>
      <tr>
        <td><span class="btn-id">btnResetTrailFilters</span></td>
        <td>Reset Button</td>
        <td>Filters hata kar complete history wapas load karta hai.</td>
      </tr>
      <tr>
        <td><span class="btn-id">btnToggleFaceTrailAuditTable</span></td>
        <td>Table Toggle</td>
        <td>Visual timeline cards aur detailed spreadsheet (tabular audit log) ke beech switch karta hai.</td>
      </tr>
      <tr>
        <td><span class="btn-id">btnOpenTrailNarrativeModal</span></td>
        <td>AI Summary</td>
        <td><strong>AI Route Summary:</strong> Ek paragraph me police narrative banata hai ki gaadi kahan se ghusi, kis speed se gayi aur aakhiri baar kahan dekhi gayi.</td>
      </tr>
      <tr>
        <td><span class="btn-id">btnHeaderExportPdf</span></td>
        <td>Export PDF</td>
        <td><strong>Download PDF Dossier:</strong> Pure movement corridor ka print-ready official PDF report download kar deta hai jise case diary me lagaya ja sake.</td>
      </tr>
    </tbody>
  </table>

  <div class="callout">
    <strong>Sample AI Route Summary Output:</strong><br>
    <em>"Target Vehicle <strong>HR-26-DA-1234</strong> (Case FIR #204/24 PS Sadar) sabse pehle <strong>09:14 AM</strong> par Camera CAM-01 (Kundli Toll) par capture hua. Dakshin disha me lagbhag 60 km/h ki gati se chalte huye ye gaadi <strong>09:38 AM</strong> par Camera CAM-03 (Sector 14) par dekhi gayi, aur aakhiri baar <strong>09:55 AM</strong> par Camera CAM-02 (IFFCO Chowk Exit) par record huyi. Total recorded transit time: 41 minutes."</em>
  </div>
</div>

<div class="page-break"></div>

<!-- CHAPTER 8: UNIFIED MEDIA UPLOAD & MASTER INDEX -->
<div>
  <h1><span class="chapter-num">CH 08</span> Unified Media Upload & Button Reference Table</h1>
  
  <p>Live camera ke alawa agar investigation officer ke paas mobile se khichi photo ya CCTV DVR ki video pen drive me ho, to use yahan test kiya ja sakta hai:</p>

  <h2>Unified Media Upload Hub Inputs</h2>
  <table>
    <thead>
      <tr>
        <th style="width: 25%;">Input Control</th>
        <th style="width: 22%;">HTML ID</th>
        <th style="width: 53%;">Working & Supported Media</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><strong>Unified Media Input</strong></td>
        <td><span class="btn-id">unifiedMediaInput</span></td>
        <td>Photo ya Video dono accept karta hai aur dono engines (ANPR + FRS) ek sath run karta hai.</td>
      </tr>
      <tr>
        <td><strong>Video File Upload</strong></td>
        <td><span class="btn-id">videoFileInput</span></td>
        <td>CCTV footage (MP4, AVI) frame-by-frame process hoti hai aur progress bar dikhta hai.</td>
      </tr>
      <tr>
        <td><strong>Image File Upload</strong></td>
        <td><span class="btn-id">imageFileInput</span></td>
        <td>Single photo (JPG, PNG) dalne par instant dual-column analysis (Vehicle + Face) deta hai.</td>
      </tr>
      <tr>
        <td><strong>Close Inspection</strong></td>
        <td><span class="btn-id">btnCloseInspection</span></td>
        <td>Forensic results band karke wapas live surveillance viewport par le aata hai.</td>
      </tr>
    </tbody>
  </table>

  <h2>Master Button Quick Reference (Sabhi Buttons Ka Index)</h2>
  <table>
    <thead>
      <tr>
        <th style="width: 24%;">Button ID</th>
        <th style="width: 18%;">Button Text</th>
        <th style="width: 58%;">Kaam (Exact Single-Line Function)</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><span class="btn-id">navDashboardBtn</span></td>
        <td>Live Hub</td>
        <td>Live camera feeds aur live alerts screen open karta hai.</td>
      </tr>
      <tr>
        <td><span class="btn-id">navMasterDbBtn</span></td>
        <td>Master DB</td>
        <td>Stolen gaadiyon aur wanted suspects ki registry open karta hai.</td>
      </tr>
      <tr>
        <td><span class="btn-id">navMasterTrailBtn</span></td>
        <td>Master Trail</td>
        <td>Movement corridor aur timeline tracking screen open karta hai.</td>
      </tr>
      <tr>
        <td><span class="btn-id">btnView1x1</span></td>
        <td>1x1 Focus</td>
        <td>Single camera ko screen par maximize karta hai.</td>
      </tr>
      <tr>
        <td><span class="btn-id">btnView2x2</span></td>
        <td>2x2 Grid</td>
        <td>4 cameras ko ek sath 2x2 grid me arrange karta hai.</td>
      </tr>
      <tr>
        <td><span class="btn-id">btnOpenConnectModal</span></td>
        <td>Connect Feed</td>
        <td>Naya RTSP/Webcam camera link karne ka dialog kholta hai.</td>
      </tr>
      <tr>
        <td><span class="btn-id">btnDisconnectStream</span></td>
        <td>Disconnect</td>
        <td>Active video streams ko stop aur disconnect karta hai.</td>
      </tr>
      <tr>
        <td><span class="btn-id">btnPresetRaw</span></td>
        <td>Raw Feed</td>
        <td>Saare AI boxes band karke 100% clean video dikhata hai.</td>
      </tr>
      <tr>
        <td><span class="btn-id">btnPresetPlate</span></td>
        <td>ANPR Only</td>
        <td>Sirf plate box aur OCR plate number text dikhata hai.</td>
      </tr>
      <tr>
        <td><span class="btn-id">btnPresetFrs</span></td>
        <td>FRS Only</td>
        <td>Sirf human face boxes aur facial landmarks dikhata hai.</td>
      </tr>
      <tr>
        <td><span class="btn-id">btnPresetAll</span></td>
        <td>All Layers</td>
        <td>Sabhi AI visual overlays ko ek sath enable karta hai.</td>
      </tr>
      <tr>
        <td><span class="btn-id">btnDetectGps</span></td>
        <td>📍 Auto-Detect</td>
        <td>Browser geolocation se station ke Latitude/Longitude auto-fill karta hai.</td>
      </tr>
      <tr>
        <td><span class="btn-id">btnSubmitConnect</span></td>
        <td>Connect & Start</td>
        <td>Camera stream background thread me start karta hai.</td>
      </tr>
      <tr>
        <td><span class="btn-id">btnOpenRegisterModal</span></td>
        <td>Register Vehicle</td>
        <td>Chori ki gaadi ka FIR case record database me daalne ka modal kholta hai.</td>
      </tr>
      <tr>
        <td><span class="btn-id">saveVehicleBtn</span></td>
        <td>Save to Vehicle DB</td>
        <td>Gaadi record ko `vehicle_db.sqlite` me commit karta hai.</td>
      </tr>
      <tr>
        <td><span class="btn-id">btnOpenEnrollModal</span></td>
        <td>Enroll New Face</td>
        <td>Suspect ki photo aur dossier detail daalne ka modal kholta hai.</td>
      </tr>
      <tr>
        <td><span class="btn-id">submitEnrollBtn</span></td>
        <td>Save to Face DB</td>
        <td>ArcFace se 512-D vector nikaal kar `face_db.sqlite` me save karta hai.</td>
      </tr>
      <tr>
        <td><span class="btn-id">btnHeaderExportPdf</span></td>
        <td>Export PDF</td>
        <td>Investigative Movement Corridor report ka official PDF download karta hai.</td>
      </tr>
    </tbody>
  </table>

  <div style="margin-top: 25px; text-align: center; border-top: 1px solid #cbd5e1; padding-top: 12px; color: #64748b; font-size: 8.5pt;">
    <strong>END OF OPERATIONAL MANUAL (HINGLISH)</strong> &bull; Haryana Police Surveillance Infrastructure Group
  </div>
</div>

</body>
</html>
"""

def main():
    print("=" * 60)
    print(" Haryana Police Surveillance System - Hinglish User Guide Generator")
    print("=" * 60)

    TEMP_HTML.parent.mkdir(parents=True, exist_ok=True)
    TEMP_HTML.write_text(HTML_CONTENT, encoding="utf-8")
    print(f"[OK] Print-ready Hinglish HTML generated at: {TEMP_HTML}")

    print("[INFO] Launching Playwright Chromium...")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        print("[INFO] Loading document...")
        page.set_content(HTML_CONTENT, wait_until="networkidle")

        print("[INFO] Rendering vector PDF...")
        # 1. Output to static folder for web browser downloads
        STATIC_DIR.mkdir(parents=True, exist_ok=True)
        page.pdf(
            path=str(OUTPUT_PDF_STATIC),
            format="A4",
            print_background=True,
            margin={"top": "18mm", "bottom": "18mm", "left": "16mm", "right": "16mm"},
        )
        print(f"[SUCCESS] PDF saved to static folder: {OUTPUT_PDF_STATIC}")

        # 2. Output to project root folder for direct file access
        page.pdf(
            path=str(OUTPUT_PDF_ROOT),
            format="A4",
            print_background=True,
            margin={"top": "18mm", "bottom": "18mm", "left": "16mm", "right": "16mm"},
        )
        print(f"[SUCCESS] PDF saved to root folder: {OUTPUT_PDF_ROOT}")

        browser.close()

    print("=" * 60)
    print(f" PDF Size: {OUTPUT_PDF_ROOT.stat().st_size / 1024:.1f} KB")
    print(" Hinglish User Guide PDF generated successfully!")
    print("=" * 60)

if __name__ == "__main__":
    main()
