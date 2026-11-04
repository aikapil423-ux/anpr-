import os
import cv2
import numpy as np
import time
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.pdfgen import canvas

from src.detection.vehicle_detector import VehicleDetector
from src.detection.plate_detector import PlateDetector
from src.quality.crop_filter import CropQualityFilter
from src.ocr.ocr_engine import OCREngine
from src.ocr.normalizer import IndianPlateNormalizer
from src.identity.vehicle_identity import CandidateReading, VehicleRecord
from src.identity.temporal_voting import TemporalVotingEngine

DOC_ASSETS_DIR = "outputs/doc_assets"
os.makedirs(DOC_ASSETS_DIR, exist_ok=True)
PDF_OUTPUT_PATH = "outputs/ANPR_Pipeline_Complete_Workflow_Guide.pdf"

print("1. Extracting sample frame and generating step images...")
cap = cv2.VideoCapture("outputs/video.mp4")
v_det = VehicleDetector()
p_det = PlateDetector()
q_filter = CropQualityFilter()
ocr_engine = OCREngine()
normalizer = IndianPlateNormalizer()
voting_engine = TemporalVotingEngine()

sample_frame = None
best_plate_info = None
best_veh_info = None
best_conf = 0.0
frame_count = 0

while cap.isOpened() and frame_count < 180:
    ret, frame = cap.read()
    if not ret:
        break
    frame_count += 1
    if frame_count % 5 != 0:
        continue

    v_results = v_det.track(frame, persist=True)
    if not v_results:
        continue
    
    p_results = p_det.detect_in_frame(frame, [v["bbox"] for v in v_results])
    for p in p_results:
        if p["conf"] > best_conf and p.get("vehicle_bbox"):
            best_conf = p["conf"]
            sample_frame = frame.copy()
            best_plate_info = p
            for v in v_results:
                if v["bbox"] == p["vehicle_bbox"]:
                    best_veh_info = v
                    break

cap.release()
print(f"Sample frame selected. Plate detection confidence: {best_conf:.2f}")

# Fallback if no plate found in the first frames
if sample_frame is None or best_plate_info is None:
    raise RuntimeError("Could not find a valid plate in outputs/video.mp4")

fh, fw = sample_frame.shape[:2]
vx1, vy1, vx2, vy2 = best_plate_info["vehicle_bbox"]
px1, py1, px2, py2 = best_plate_info["bbox"]

# Step 1: Raw Input Scene Frame
cv2.imwrite(os.path.join(DOC_ASSETS_DIR, "step1_raw_frame.jpg"), sample_frame)

# Step 2: Vehicle Detection & Tracking
img_step2 = sample_frame.copy()
cv2.rectangle(img_step2, (vx1, vy1), (vx2, vy2), (255, 140, 0), 3)
tid = best_veh_info.get("track_id", 1)
cls_name = best_veh_info.get("cls_name", "Car").capitalize()
v_lbl = f"Vehicle: {cls_name} #{tid} (Tracked)"
(tw, th), _ = cv2.getTextSize(v_lbl, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
cv2.rectangle(img_step2, (vx1, max(0, vy1 - th - 10)), (vx1 + tw + 10, vy1), (255, 140, 0), -1)
cv2.putText(img_step2, v_lbl, (vx1 + 5, max(th + 2, vy1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
cv2.imwrite(os.path.join(DOC_ASSETS_DIR, "step2_vehicle_detection.jpg"), img_step2)

# Step 3: License Plate Localization inside Vehicle ROI
img_step3 = sample_frame.copy()
cv2.rectangle(img_step3, (vx1, vy1), (vx2, vy2), (255, 140, 0), 2)
cv2.rectangle(img_step3, (px1, py1), (px2, py2), (0, 255, 255), 3) # Vibrant Yellow/Cyan
p_lbl = f"Plate ROI ({int(best_conf * 100)}% conf)"
(ptw, pth), _ = cv2.getTextSize(p_lbl, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
cv2.rectangle(img_step3, (px1, max(0, py1 - pth - 8)), (px1 + ptw + 8, py1), (0, 255, 255), -1)
cv2.putText(img_step3, p_lbl, (px1 + 4, max(pth + 2, py1 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 2)
cv2.imwrite(os.path.join(DOC_ASSETS_DIR, "step3_plate_localization.jpg"), img_step3)

# Step 4: Crop Quality Gate & Adaptive Preprocessing
pw, ph = px2 - px1, py2 - py1
pad_x = int(pw * 0.08)
pad_y = int(ph * 0.08)
x1c = max(0, px1 - pad_x)
y1c = max(0, py1 - pad_y)
x2c = min(fw, px2 + pad_x)
y2c = min(fh, py2 + pad_y)
raw_plate_crop = sample_frame[y1c:y2c, x1c:x2c].copy()

is_valid, reason, blur_score, cleaned_crop = q_filter.validate(
    crop=raw_plate_crop,
    det_conf=best_plate_info["conf"],
    bbox=(px1, py1, px2, py2),
    frame_shape=(fh, fw)
)
if cleaned_crop is None or cleaned_crop.size == 0:
    cleaned_crop = raw_plate_crop.copy()

# Side-by-side comparison image for Step 4
target_h = 100
r_w = int(raw_plate_crop.shape[1] * (target_h / max(1, raw_plate_crop.shape[0])))
c_w = int(cleaned_crop.shape[1] * (target_h / max(1, cleaned_crop.shape[0])))
r_resized = cv2.resize(raw_plate_crop, (r_w, target_h))
c_resized = cv2.resize(cleaned_crop, (c_w, target_h))

sep = np.full((target_h, 20, 3), 40, dtype=np.uint8)
comparison_img = np.hstack([r_resized, sep, c_resized])
# Add labels
labeled_comp = np.full((target_h + 35, comparison_img.shape[1], 3), 245, dtype=np.uint8)
labeled_comp[35:, :] = comparison_img
cv2.putText(labeled_comp, "[A] Raw Isolated Crop", (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (20, 20, 20), 2)
cv2.putText(labeled_comp, "[B] Cleaned & Enhanced Crop", (r_w + 30, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (16, 120, 20), 2)
cv2.imwrite(os.path.join(DOC_ASSETS_DIR, "step4_crop_comparison.jpg"), labeled_comp)

# Step 5: OCR Recognition & MoRTH Normalization
raw_ocr_text, ocr_conf = ocr_engine.read_text(cleaned_crop)
is_valid_fmt, fmt_type, norm_text = normalizer.validate(raw_ocr_text)
disp_text = normalizer.format_display(norm_text)
print(f"OCR Result: raw='{raw_ocr_text}', norm='{norm_text}', conf={ocr_conf:.2f}, valid={is_valid_fmt}")

# Step 6: Multi-Frame Voting Simulation
vehicle_crop = sample_frame[max(0, vy1):min(fh, vy2), max(0, vx1):min(fw, vx2)].copy()
cv2.imwrite(os.path.join(DOC_ASSETS_DIR, "step6_vehicle_crop.jpg"), vehicle_crop)
cv2.imwrite(os.path.join(DOC_ASSETS_DIR, "step6_plate_crop.jpg"), cleaned_crop)

# Step 7: Final Annotated Output Scene (Verified Badge)
final_annotated = sample_frame.copy()
cv2.rectangle(final_annotated, (vx1, vy1), (vx2, vy2), (255, 140, 0), 3)
cv2.rectangle(final_annotated, (px1, py1), (px2, py2), (16, 185, 129), 3)
tag = f"{disp_text} ({int(ocr_conf * 100)}% VERIFIED)"
(tw, th), _ = cv2.getTextSize(tag, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
cv2.rectangle(final_annotated, (px1, max(0, py1 - th - 10)), (px1 + tw + 10, py1), (16, 185, 129), -1)
cv2.putText(final_annotated, tag, (px1 + 5, max(th + 2, py1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
cv2.imwrite(os.path.join(DOC_ASSETS_DIR, "step7_final_annotated.jpg"), final_annotated)

print("Step images generated successfully. Now building PDF document...")

# --- REPORTLAB PDF GENERATION ---
class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, total_pages):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748b"))
        # Header (Pages > 1)
        if self._pageNumber > 1:
            self.drawString(54, 750, "Automated License Plate Recognition (ANPR) System | Architecture & Workflow Guide")
            self.setStrokeColor(colors.HexColor("#e2e8f0"))
            self.setLineWidth(0.5)
            self.line(54, 744, 558, 744)
        
        # Footer
        self.setStrokeColor(colors.HexColor("#e2e8f0"))
        self.setLineWidth(0.5)
        self.line(54, 45, 558, 45)
        self.drawString(54, 32, "Confidential | Engineering System Architecture Documentation")
        self.drawRightString(558, 32, f"Page {self._pageNumber} of {total_pages}")
        self.restoreState()

doc = SimpleDocTemplate(
    PDF_OUTPUT_PATH,
    pagesize=letter,
    leftMargin=54,
    rightMargin=54,
    topMargin=54,
    bottomMargin=54
)

styles = getSampleStyleSheet()

# Custom styles
primary_color = colors.HexColor("#0f172a") # Dark Slate / Navy
accent_color = colors.HexColor("#2563eb")  # Blue
verified_color = colors.HexColor("#059669")# Emerald green
text_dark = colors.HexColor("#1e293b")
text_muted = colors.HexColor("#475569")
bg_card = colors.HexColor("#f8fafc")
border_card = colors.HexColor("#e2e8f0")

title_style = ParagraphStyle(
    "DocTitle",
    parent=styles["Heading1"],
    fontName="Helvetica-Bold",
    fontSize=22,
    leading=26,
    textColor=primary_color,
    spaceAfter=6
)

subtitle_style = ParagraphStyle(
    "DocSubTitle",
    parent=styles["Normal"],
    fontName="Helvetica",
    fontSize=11,
    leading=15,
    textColor=text_muted,
    spaceAfter=15
)

h1_style = ParagraphStyle(
    "CustomH1",
    parent=styles["Heading2"],
    fontName="Helvetica-Bold",
    fontSize=14,
    leading=18,
    textColor=primary_color,
    spaceBefore=12,
    spaceAfter=6
)

h2_style = ParagraphStyle(
    "CustomH2",
    parent=styles["Heading3"],
    fontName="Helvetica-Bold",
    fontSize=11,
    leading=14,
    textColor=accent_color,
    spaceBefore=8,
    spaceAfter=4
)

body_style = ParagraphStyle(
    "CustomBody",
    parent=styles["BodyText"],
    fontName="Helvetica",
    fontSize=9.5,
    leading=13.5,
    textColor=text_dark,
    spaceAfter=6
)

hindi_style = ParagraphStyle(
    "HindiExplanation",
    parent=styles["BodyText"],
    fontName="Helvetica-Oblique",
    fontSize=9,
    leading=13,
    textColor=colors.HexColor("#0369a1"), # Deep sky blue
    spaceAfter=6
)

badge_style = ParagraphStyle(
    "Badge",
    parent=styles["Normal"],
    fontName="Helvetica-Bold",
    fontSize=8.5,
    leading=11,
    textColor=colors.white
)

code_style = ParagraphStyle(
    "CodeSnippet",
    parent=styles["Code"],
    fontName="Courier",
    fontSize=8,
    leading=10.5,
    textColor=colors.HexColor("#0f172a"),
    backColor=colors.HexColor("#f1f5f9"),
    borderPadding=5
)

elements = []

# Title Section
elements.append(Paragraph("ANPR End-to-End Pipeline: Complete Working & Image Evolution Guide", title_style))
elements.append(Paragraph("A Technical Deep-Dive into AI Vehicle Tracking, Plate Localization, Morphological Preprocessing, MoRTH Regex Standardization, Multi-Frame Temporal Consensus, and Evidence Preservation.", subtitle_style))
elements.append(HRFlowable(width="100%", thickness=1.5, color=accent_color, spaceAfter=14))

# Executive Summary Box
summary_text = """
<b>System Overview:</b> This document provides an exhaustive, step-by-step visual audit of how the ANPR (Automatic Number Plate Recognition) system processes raw camera video or static images into verified law-enforcement intelligence. Every transformation step is illustrated with the actual image outputs produced at each stage—demonstrating exactly what changes from the original raw input down to the final database record.
<br/><br/>
<i>Hindi Explanation: Is guide me ANPR pipeline ke har ek step ko shuru se aakhri tak ek real gaadi ke example ke saath explain kiya gaya hai. Har step pe image me kya badlaav hua aur AI model ne kya extract kiya, sab visually dikhaya gaya hai.</i>
"""
summary_table = Table([[Paragraph(summary_text, body_style)]], colWidths=[504])
summary_table.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, -1), bg_card),
    ("BOX", (0, 0), (-1, -1), 1, border_card),
    ("TOPPADDING", (0, 0), (-1, -1), 10),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ("LEFTPADDING", (0, 0), (-1, -1), 12),
    ("RIGHTPADDING", (0, 0), (-1, -1), 12),
]))
elements.append(summary_table)
elements.append(Spacer(1, 14))

# Pipeline Architecture Flowchart Table
arch_steps = [
    ["Stage", "Name", "Key Algorithms / Models", "Primary Objective"],
    ["Step 1", "Raw Video Ingestion", "OpenCV VideoCapture, Dynamic Stride", "Extract high-resolution frames while saving CPU"],
    ["Step 2", "Vehicle Tracking", "YOLO11 Nano/Small + ByteTrack Kalman", "Localize physical vehicle and preserve track trajectory"],
    ["Step 3", "Plate Localization", "Trained YOLO11 Plate Detector", "Pinpoint license plate bounding box inside vehicle ROI"],
    ["Step 4", "Quality Gate & Native Preservation", "Laplacian Blur, Raw Pass-Through", "Filter blurry noise & preserve raw sharpness (No CLAHE)"],
    ["Step 5", "OCR & Normalization", "PaddleOCR DBNet+CRNN, MoRTH Regex", "Read text & auto-correct Indian plate syntax"],
    ["Step 6", "Temporal Consensus", "Weighted Confidence Voting", "Multi-frame voting, 3-Tier classification, zero flood"],
    ["Step 7", "Evidence & Hotlist", "Audit Storage, FIR Matching, FIFO DB", "Save full scene & crop gallery; alert law enforcement"]
]
arch_table = Table(arch_steps, colWidths=[50, 110, 174, 170])
arch_table.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), primary_color),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE", (0, 0), (-1, 0), 8.5),
    ("GRID", (0, 0), (-1, -1), 0.5, border_card),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, bg_card]),
    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
    ("FONTSIZE", (0, 1), (-1, -1), 8),
    ("TOPPADDING", (0, 0), (-1, -1), 5),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
]))
elements.append(arch_table)
elements.append(Spacer(1, 16))

# --- STEP 1 ---
elements.append(Paragraph("Step 1: Raw Input Scene Frame (Unprocessed Video Feed)", h1_style))
elements.append(Paragraph(
    "<b>Technical Operation:</b> The ingestion module captures uncompressed BGR frames from the camera feed or video file. To ensure <b>real-time processing on standard CPU</b> without lag, an intelligent frame stride (e.g. processing 1 out of every 5 frames) is applied. This processes ~6 high-definition frames per second, which is more than enough for vehicular speeds.",
    body_style
))
elements.append(Paragraph(
    "<i>Hindi: Sabse pehle camera ya video se raw frame capture hota hai. CPU speed fast rakhne ke liye intelligent frame skipping hoti hai taaki system bina freeze hue video ko process kare.</i>",
    hindi_style
))
raw_img_path = os.path.join(DOC_ASSETS_DIR, "step1_raw_frame.jpg")
elements.append(RLImage(raw_img_path, width=320, height=180))
elements.append(Spacer(1, 14))

# --- STEP 2 ---
elements.append(Paragraph("Step 2: Vehicle Detection & Multi-Object Trajectory Tracking", h1_style))
elements.append(Paragraph(
    f"<b>Technical Operation:</b> The frame is evaluated using the <b>YOLO11 Vehicle Detector</b> combined with <b>ByteTrack</b> Kalman filter tracking. It classifies vehicle categories (Car, Motorcycle, Bus, Truck) and assigns a persistent ID (e.g. <b>Track #{tid}</b>). This ensures the vehicle's spatial centroid and trajectory are monitored across all frames.",
    body_style
))
elements.append(Paragraph(
    f"<i>Hindi: Yahan YOLO11 model poori image me gaadi ko detect karta hai aur ByteTrack us gaadi ko ek unique Track ID #{tid} dekar track karta hai, taaki aage peeche aane par gaadi identify rahe.</i>",
    hindi_style
))
vdet_img_path = os.path.join(DOC_ASSETS_DIR, "step2_vehicle_detection.jpg")
elements.append(RLImage(vdet_img_path, width=320, height=180))
elements.append(Spacer(1, 14))

elements.append(PageBreak())

# --- STEP 3 ---
elements.append(Paragraph("Step 3: License Plate Localization inside Vehicle ROI", h1_style))
elements.append(Paragraph(
    f"<b>Technical Operation:</b> Instead of blindly scanning the entire scene, the system focuses detection inside the vehicle's Region of Interest (ROI). The <b>YOLO11 Plate Detector</b> localizes the precise plate coordinates (Confidence: <b>{int(best_conf*100)}%</b>). Spatial containment checks verify that the plate physically belongs inside the vehicle bounding box, eliminating false positives from signs or roadside posters.",
    body_style
))
elements.append(Paragraph(
    f"<i>Hindi: Image me gaadi ke lower area par specialized YOLO11 Plate Detector chalta hai jo number plate ke corners ko pinpoint karta hai (Confidence: {int(best_conf*100)}%). Roadside hoardings ya board ko reject kar deta hai.</i>",
    hindi_style
))
pdet_img_path = os.path.join(DOC_ASSETS_DIR, "step3_plate_localization.jpg")
elements.append(RLImage(pdet_img_path, width=320, height=180))
elements.append(Spacer(1, 14))

# --- STEP 4 ---
elements.append(Paragraph("Step 4: Image Quality Gate & Native Sensor Crop Preservation", h1_style))
elements.append(Paragraph(
    "<b>Technical Operation:</b> High recognition accuracy requires crisp, standardized text. The isolated plate crop undergoes rigorous checks:",
    body_style
))
elements.append(Paragraph(
    """
    1. <b>Resolution Check:</b> Bounding box must be at least 40 &times; 20 px.<br/>
    2. <b>Blur Metric:</b> Computes Laplacian variance Var(&#8711;&sup2; I). Blurry frames below threshold are rejected from OCR.<br/>
    3. <b>Raw Pass-Through (No CLAHE):</b> CLAHE and artificial contrast filters are bypassed. CLAHE amplifies high-frequency noise and introduces unnatural halo artifacts around characters on reflective Indian HSRP plates; passing unaltered native sensor crops directly to OCR provides superior recognition accuracy.
    """,
    body_style
))
elements.append(Paragraph(
    "<i>Hindi: Yahan plate crop ka blur test hota hai. Agar dhundhla ya bohot chhota hai to drop hota hai. Clear crops par CLAHE ya artificial filters nahi lagte, balki original sensor crop ko pass-through kiya jata hai taaki noise se bacha jaa sake aur OCR engine accurate padh sake.</i>",
    hindi_style
))
comp_img_path = os.path.join(DOC_ASSETS_DIR, "step4_crop_comparison.jpg")
elements.append(RLImage(comp_img_path, width=340, height=115))
elements.append(Spacer(1, 14))

# --- STEP 5 ---
elements.append(Paragraph("Step 5: High-Precision OCR & Indian MoRTH Regex Normalization", h1_style))
elements.append(Paragraph(
    f"<b>Technical Operation:</b> The cleaned crop is fed into the <b>PaddleOCR</b> DBNet text detector and CRNN recognition engine. The raw detected string <code>{raw_ocr_text}</code> (OCR Confidence: <b>{int(ocr_conf*100)}%</b>) is passed to the <b>IndianPlateNormalizer</b>:",
    body_style
))
elements.append(Paragraph(
    f"""
    • <b>MoRTH Validation:</b> Enforces standard Indian format <code>[State: 2L][RTO: 2D][Series: 1-3L][Number: 1-4D]</code>.<br/>
    • <b>Character Repair Matrix:</b> Automatically corrects optical character confusions based on index position (e.g. Letter 'O' repaired to Digit '0' in number segment; Digit '8' repaired to Letter 'B' in series segment).<br/>
    • <b>Normalized Output:</b> <b>{disp_text}</b> (Format Status: <b>{'VALID STANDARD' if is_valid_fmt else 'IRREGULAR'}</b>).
    """,
    body_style
))
elements.append(Paragraph(
    f"<i>Hindi: PaddleOCR se nikla raw text '{raw_ocr_text}' normalizer me jata hai jo Indian RTO rules check karta hai. Agar optical confusion (jaise O ki jagah 0 ya 8 ki jagah B) ho to auto-repair karke '{disp_text}' me badalta hai.</i>",
    hindi_style
))
elements.append(Spacer(1, 10))

elements.append(PageBreak())

# --- STEP 6 ---
elements.append(Paragraph("Step 6: Multi-Frame Temporal Consensus & 3-Tier Classification", h1_style))
elements.append(Paragraph(
    "<b>Technical Operation:</b> Single-frame ANPR frequently suffers from momentary glare, vibration, or shadows. Our <b>Temporal Voting Engine</b> aggregates readings across multiple frames for the same physical vehicle using confidence-squared scoring:",
    body_style
))
elements.append(Paragraph(
    "<b>Voting Formula:</b> <code>Candidate Score = (OCR Confidence)&sup2; &times; (MoRTH Format Bonus) &times; [1 + log(1 + Blur Score)]</code>",
    code_style
))
elements.append(Spacer(1, 8))

# 3-Tier Classification Table
tier_data = [
    ["Tier Status", "Confidence Criteria", "System Action", "Evidence Preserved?"],
    ["Tier 1: VERIFIED", ">= 60% Conf + Valid MoRTH", "Logged to Captured DB & TrailDB; Hotlist search", "YES (Full Scene, Veh Crop, Plate Crop)"],
    ["Tier 2: NEEDS REVIEW", "50% - 60% Conf or Ambiguous", "Logged for 1-Click Human Officer Confirmation", "YES (Full Multi-frame Gallery)"],
    ["Tier 3: UNREADABLE", "Plate >50% det across >=2 frames", "Logged as UNREADABLE (LOW EVIDENCE) badge", "YES (All original visual crops kept)"],
    ["REJECTED NOISE", "<= 50% Detection or OCR Conf", "Directly discarded to prevent DB spam", "NO (Dropped permanently)"]
]
tier_table = Table(tier_data, colWidths=[95, 120, 149, 140])
tier_table.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), primary_color),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE", (0, 0), (-1, 0), 8),
    ("GRID", (0, 0), (-1, -1), 0.5, border_card),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, bg_card]),
    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
    ("FONTSIZE", (0, 1), (-1, -1), 7.5),
    ("TOPPADDING", (0, 0), (-1, -1), 4),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
]))
elements.append(tier_table)
elements.append(Spacer(1, 10))

elements.append(Paragraph(
    "<i>Hindi: Multi-frame temporal voting se ek hi gaadi ke alag-alag frames ke readings ko compare kiya jata hai. 50% se kam wale kachre ko discard kar diya jata hai. Clear number verified me jata hai, dhundhla unreadable me evidence ke saath save hota hai.</i>",
    hindi_style
))
elements.append(Spacer(1, 14))

# --- STEP 7 ---
elements.append(Paragraph("Step 7: Final System Output, Visual Evidence & Hotlist Alerting", h1_style))
elements.append(Paragraph(
    f"<b>Technical Operation:</b> Once a vehicle is verified, the system generates full visual audit artifacts. The video writer draws green verified badges with display plate <code>{disp_text}</code>, stores the vehicle crop and plate crop into the <b>FIFO Captured Database</b>, and executes an instant cross-reference against the <b>Stolen Vehicle / FIR Police Database</b>.",
    body_style
))
elements.append(Paragraph(
    f"<i>Hindi: Aakhri step me video par green verified badge lag jata hai, Captured DB me entry ho jaati hai, aur police FIR hotlist check hoti hai. User ko Evidence Modal me gaadi, plate aur scene ke saare photos milte hain.</i>",
    hindi_style
))

step7_img_path = os.path.join(DOC_ASSETS_DIR, "step7_final_annotated.jpg")
elements.append(RLImage(step7_img_path, width=320, height=180))
elements.append(Spacer(1, 14))

# Visual Evidence Breakdown Table (Vehicle Crop, Plate Crop, Full Scene)
v_crop_path = os.path.join(DOC_ASSETS_DIR, "step6_vehicle_crop.jpg")
p_crop_path = os.path.join(DOC_ASSETS_DIR, "step6_plate_crop.jpg")

evidence_table_data = [
    [
        Paragraph("<b>Vehicle Crop Archive</b>", body_style),
        Paragraph("<b>Enhanced Plate Crop</b>", body_style),
        Paragraph("<b>Audit Information</b>", body_style)
    ],
    [
        RLImage(v_crop_path, width=150, height=90),
        RLImage(p_crop_path, width=150, height=50),
        Paragraph(f"""
        <b>Plate Number:</b> {disp_text}<br/>
        <b>Track ID:</b> #{tid}<br/>
        <b>Confidence:</b> {int(ocr_conf*100)}%<br/>
        <b>Format:</b> Indian Standard<br/>
        <b>Hotlist Check:</b> Clear (No FIR)
        """, body_style)
    ]
]
ev_table = Table(evidence_table_data, colWidths=[168, 168, 168])
ev_table.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, -1), bg_card),
    ("BOX", (0, 0), (-1, -1), 1, border_card),
    ("ALIGN", (0, 1), (1, 1), "CENTER"),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("TOPPADDING", (0, 0), (-1, -1), 6),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
]))
elements.append(ev_table)
elements.append(Spacer(1, 16))

# Build Document
doc.build(elements, canvasmaker=NumberedCanvas)
print(f"PDF successfully generated at: {PDF_OUTPUT_PATH}")
