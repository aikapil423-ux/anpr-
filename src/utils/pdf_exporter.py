"""
PDF Exporter Module for Surveillance Audits.
Generates publication-quality, landscape forensic audit PDFs for:
1. Captured Faces (100 FIFO Biometric Recognition Ledger)
2. Captured Vehicles (100 FIFO ANPR Vehicle Detection Ledger)
"""

import os
import io
import datetime
from typing import List, Dict, Any, Optional

from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, Table, TableStyle, PageBreak, KeepTogether
)
from reportlab.pdfgen import canvas


class NumberedLandscapeCanvas(canvas.Canvas):
    """
    Two-pass canvas to dynamically compute and stamp total page numbers
    along with police audit headers and footers.
    """
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
            self.draw_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_decorations(self, total_pages: int):
        self.saveState()
        # Header (on page 2 and later)
        if self._pageNumber > 1:
            self.setFont("Helvetica-Bold", 8)
            self.setFillColor(colors.HexColor("#475569"))
            self.drawString(36, 568, "HARYANA POLICE / ICCC SMART SURVEILLANCE | OFFICIAL AUDIT RECORD")
            self.setFont("Helvetica", 8)
            self.drawRightString(805, 568, f"Log Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            self.setStrokeColor(colors.HexColor("#cbd5e1"))
            self.setLineWidth(0.6)
            self.line(36, 560, 805, 560)

        # Footer (all pages)
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748b"))
        self.setStrokeColor(colors.HexColor("#cbd5e1"))
        self.setLineWidth(0.6)
        self.line(36, 32, 805, 32)
        self.drawString(36, 20, "CONFIDENTIAL // LAW ENFORCEMENT & TRAFFIC COMMAND CENTER USE ONLY")
        self.drawRightString(805, 20, f"Page {self._pageNumber} of {total_pages}")
        self.restoreState()


def resolve_disk_image_path(web_path: Optional[str], base_dir: Optional[str] = None) -> Optional[str]:
    """Safely resolves web URLs / relative paths to actual disk paths."""
    if not web_path:
        return None
    if base_dir is None:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    clean = web_path.replace("\\", "/").lstrip("/")
    
    # 1. Direct path from project root
    p1 = os.path.join(base_dir, clean)
    if os.path.exists(p1) and os.path.isfile(p1):
        return p1

    # 2. static/frs/... -> data/frs/...
    if clean.startswith("static/frs/"):
        p2 = os.path.join(base_dir, "data", "frs", clean.replace("static/frs/", ""))
        if os.path.exists(p2) and os.path.isfile(p2):
            return p2

    # 3. data/frs/...
    p3 = os.path.join(base_dir, "data", clean)
    if os.path.exists(p3) and os.path.isfile(p3):
        return p3

    # 4. Search by filename across known directories
    fname = os.path.basename(clean)
    candidates = [
        os.path.join(base_dir, "data", "captured_crops", fname),
        os.path.join(base_dir, "data", "frs", "captured_face_crops", fname),
        os.path.join(base_dir, "data", "frs", "captured_face_scenes", fname),
        os.path.join(base_dir, "data", "vehicle_photos", fname),
    ]
    for c in candidates:
        if os.path.exists(c) and os.path.isfile(c):
            return c

    return None


# ==============================================================================
# 1. CAPTURED FACES AUDIT PDF GENERATOR
# ==============================================================================
def build_captured_faces_pdf(
    faces: List[Dict[str, Any]],
    stats: Optional[Dict[str, Any]] = None,
    base_dir: Optional[str] = None
) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=42
    )

    styles = getSampleStyleSheet()
    c_navy = colors.HexColor("#0f172a")
    c_slate = colors.HexColor("#334155")
    c_card_bg = colors.HexColor("#f8fafc")
    c_border = colors.HexColor("#e2e8f0")

    # Typography styles
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        textColor=c_navy,
        spaceAfter=2
    )
    sub_style = ParagraphStyle(
        "ReportSub",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#475569")
    )
    cell_bold = ParagraphStyle(
        "CellBold",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=c_navy
    )
    cell_norm = ParagraphStyle(
        "CellNorm",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=9.5,
        textColor=c_slate
    )
    badge_suspect = ParagraphStyle(
        "BadgeSuspect",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor("#dc2626")
    )
    badge_vip = ParagraphStyle(
        "BadgeVIP",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor("#7c3aed")
    )
    badge_hit = ParagraphStyle(
        "BadgeHit",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor("#059669")
    )

    elements = []

    # --- Header Banner Table ---
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total_cnt = len(faces)
    suspect_cnt = stats.get("suspects", sum(1 for f in faces if str(f.get("category", "")).upper() in ["SUSPECT", "WANTED"])) if stats else 0
    match_cnt = stats.get("matched_hits", sum(1 for f in faces if f.get("is_match_hit"))) if stats else 0

    header_data = [
        [
            Paragraph("<b>HARYANA POLICE / ICCC SMART SURVEILLANCE PLATFORM</b><br/><font size='10' color='#1e293b'><b>AUTOMATED AUDIT REPORT: CAPTURED FACES & BIOMETRIC RECOGNITION (100 FIFO)</b></font>", title_style),
            Paragraph(f"<b>Generated:</b> {now_str}<br/><b>Buffer Status:</b> {total_cnt} Records<br/><b>Suspect Hits:</b> <font color='#dc2626'>{suspect_cnt}</font> | <b>Matches:</b> <font color='#059669'>{match_cnt}</font>", sub_style)
        ]
    ]
    header_tbl = Table(header_data, colWidths=[520, 249])
    header_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(header_tbl)
    elements.append(Spacer(1, 8))

    # --- Table Definition ---
    # Width: 32 + 50 + 95 + 95 + 85 + 75 + 105 + 130 + 102 = 769 pt
    col_widths = [32, 52, 95, 95, 80, 75, 105, 130, 105]
    table_rows = [
        [
            Paragraph("<b>#</b>", cell_bold),
            Paragraph("<b>Face</b>", cell_bold),
            Paragraph("<b>Timestamp / Source</b>", cell_bold),
            Paragraph("<b>Subject Name</b>", cell_bold),
            Paragraph("<b>Category</b>", cell_bold),
            Paragraph("<b>Similarity</b>", cell_bold),
            Paragraph("<b>Quality & Pose</b>", cell_bold),
            Paragraph("<b>Location / Camera</b>", cell_bold),
            Paragraph("<b>Match Info</b>", cell_bold),
        ]
    ]

    for idx, f in enumerate(faces):
        rank = f"#{idx + 1}"
        face_path = resolve_disk_image_path(f.get("face_pic_path"), base_dir=base_dir)
        
        # Face thumbnail
        if face_path:
            try:
                thumb = RLImage(face_path, width=44, height=44)
            except Exception:
                thumb = Paragraph("<font color='#94a3b8'>[Err]</font>", cell_norm)
        else:
            thumb = Paragraph("<font color='#94a3b8'>[No Pic]</font>", cell_norm)

        # Captured time & source
        cap_time = f.get("captured_at", "")[:19]
        source = f.get("source_type", "Camera")
        time_para = Paragraph(f"<b>{cap_time}</b><br/><font color='#64748b'>{source}</font>", cell_norm)

        # Subject Name
        name = f.get("person_name") or "Unknown"
        name_para = Paragraph(f"<b>{name}</b><br/><font color='#64748b'>ID: {f.get('id')}</font>", cell_norm)

        # Category Badge
        cat = str(f.get("category", "UNKNOWN")).upper()
        if cat in ["SUSPECT", "WANTED"]:
            cat_para = Paragraph(f"● <b>{cat}</b>", badge_suspect)
        elif cat == "VIP":
            cat_para = Paragraph(f"★ <b>{cat}</b>", badge_vip)
        else:
            cat_para = Paragraph(f"<b>{cat}</b>", cell_norm)

        # Similarity
        sim = f.get("similarity_score", 0.0)
        is_hit = bool(f.get("is_match_hit"))
        if is_hit:
            sim_para = Paragraph(f"<b>{sim:.1f}%</b><br/><font color='#059669'>[VERIFIED]</font>", badge_hit)
        else:
            sim_para = Paragraph(f"{sim:.1f}%<br/><font color='#94a3b8'>[UNMATCHED]</font>", cell_norm)

        # Quality & Pose
        q_score = f.get("quality_score", 0.0)
        blur = f.get("blur_score", 0.0)
        yaw = f.get("yaw_angle", 0.0)
        pitch = f.get("pitch_angle", 0.0)
        qual_para = Paragraph(f"Qual: <b>{q_score:.0f}%</b> | Blur: {blur:.1f}<br/><font color='#64748b'>Yaw: {yaw:.1f}° | Pit: {pitch:.1f}°</font>", cell_norm)

        # Location
        loc = f.get("location") or "Main Gate"
        loc_para = Paragraph(f"{loc}", cell_norm)

        # Match Info
        m_info = f.get("match_info") or (f"Hit: {name}" if is_hit else "Routine Capture")
        match_para = Paragraph(f"{m_info}", cell_norm)

        table_rows.append([
            Paragraph(rank, cell_bold),
            thumb,
            time_para,
            name_para,
            cat_para,
            sim_para,
            qual_para,
            loc_para,
            match_para
        ])

    main_table = Table(table_rows, colWidths=col_widths, repeatRows=1)
    main_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, c_border),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, c_card_bg]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(main_table)

    doc.build(elements, canvasmaker=NumberedLandscapeCanvas)
    return buffer.getvalue()


# ==============================================================================
# 2. CAPTURED VEHICLES AUDIT PDF GENERATOR
# ==============================================================================
def build_captured_vehicles_pdf(
    vehicles: List[Dict[str, Any]],
    stats: Optional[Dict[str, Any]] = None,
    base_dir: Optional[str] = None
) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=42
    )

    styles = getSampleStyleSheet()
    c_navy = colors.HexColor("#0f172a")
    c_slate = colors.HexColor("#334155")
    c_card_bg = colors.HexColor("#f8fafc")
    c_border = colors.HexColor("#e2e8f0")

    title_style = ParagraphStyle(
        "VehReportTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        textColor=c_navy,
        spaceAfter=2
    )
    sub_style = ParagraphStyle(
        "VehReportSub",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#475569")
    )
    cell_bold = ParagraphStyle(
        "VehCellBold",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=c_navy
    )
    plate_style = ParagraphStyle(
        "VehPlateStyle",
        parent=styles["Normal"],
        fontName="Courier-Bold",
        fontSize=9.5,
        leading=11,
        textColor=colors.HexColor("#0f172a")
    )
    cell_norm = ParagraphStyle(
        "VehCellNorm",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=9.5,
        textColor=c_slate
    )
    badge_hotlist = ParagraphStyle(
        "BadgeHotlist",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor("#dc2626")
    )
    badge_normal = ParagraphStyle(
        "BadgeNormal",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor("#059669")
    )

    elements = []

    # --- Header Banner Table ---
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total_cnt = len(vehicles)
    hotlist_cnt = stats.get("hotlist_hits", sum(1 for v in vehicles if v.get("is_hotlist_hit"))) if stats else sum(1 for v in vehicles if v.get("is_hotlist_hit"))

    header_data = [
        [
            Paragraph("<b>HARYANA POLICE / ICCC SMART SURVEILLANCE PLATFORM</b><br/><font size='10' color='#1e293b'><b>AUTOMATED AUDIT REPORT: CAPTURED VEHICLES & ANPR LOG (100 FIFO)</b></font>", title_style),
            Paragraph(f"<b>Generated:</b> {now_str}<br/><b>Buffer Status:</b> {total_cnt} Records<br/><b>Hotlist / FIR Hits:</b> <font color='#dc2626'><b>{hotlist_cnt}</b></font>", sub_style)
        ]
    ]
    header_tbl = Table(header_data, colWidths=[520, 249])
    header_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(header_tbl)
    elements.append(Spacer(1, 8))

    # --- Table Definition ---
    # Width: 32 + 75 + 95 + 110 + 95 + 70 + 70 + 115 + 107 = 769 pt
    col_widths = [32, 75, 95, 110, 95, 70, 70, 115, 107]
    table_rows = [
        [
            Paragraph("<b>#</b>", cell_bold),
            Paragraph("<b>Plate Crop</b>", cell_bold),
            Paragraph("<b>Timestamp / Source</b>", cell_bold),
            Paragraph("<b>License Plate</b>", cell_bold),
            Paragraph("<b>Security Status</b>", cell_bold),
            Paragraph("<b>Det Conf</b>", cell_bold),
            Paragraph("<b>OCR Conf</b>", cell_bold),
            Paragraph("<b>Location / Camera</b>", cell_bold),
            Paragraph("<b>Audit Reason</b>", cell_bold),
        ]
    ]

    for idx, v in enumerate(vehicles):
        rank = f"#{idx + 1}"
        plate_path = resolve_disk_image_path(v.get("plate_pic_path"), base_dir=base_dir)
        
        # Plate Crop thumbnail (width 68, height 22)
        if plate_path:
            try:
                thumb = RLImage(plate_path, width=68, height=22)
            except Exception:
                thumb = Paragraph("<font color='#94a3b8'>[Err]</font>", cell_norm)
        else:
            thumb = Paragraph("<font color='#94a3b8'>[No Pic]</font>", cell_norm)

        # Captured time & source
        cap_time = str(v.get("captured_at", ""))[:19]
        source = v.get("source_type", "Camera")
        time_para = Paragraph(f"<b>{cap_time}</b><br/><font color='#64748b'>{source}</font>", cell_norm)

        # Plate Display
        plate_no = v.get("display_plate") or v.get("plate_number") or "N/A"
        plate_para = Paragraph(f"<b>{plate_no}</b><br/><font color='#64748b'>ID: {v.get('id')}</font>", plate_style)

        # Hotlist Status
        is_hot = bool(v.get("is_hotlist_hit"))
        hot_info = v.get("hotlist_info") or "Hotlist Match"
        if is_hot:
            status_para = Paragraph(f"🚨 <b>{hot_info}</b>", badge_hotlist)
        else:
            status_para = Paragraph("✓ <b>NORMAL (CLEAN)</b>", badge_normal)

        # Confidence
        det_conf = v.get("det_confidence", v.get("confidence", 0.0))
        ocr_conf = v.get("ocr_confidence", v.get("confidence", 0.0))
        det_para = Paragraph(f"<b>{det_conf:.1f}%</b>", cell_norm)
        ocr_para = Paragraph(f"<b>{ocr_conf:.1f}%</b>", cell_norm)

        # Location
        loc = v.get("location") or "Main Gate"
        loc_para = Paragraph(f"{loc}", cell_norm)

        # Audit Reason
        reason = v.get("quality_reason") or "Verified Ingestion"
        reason_para = Paragraph(f"{reason}", cell_norm)

        table_rows.append([
            Paragraph(rank, cell_bold),
            thumb,
            time_para,
            plate_para,
            status_para,
            det_para,
            ocr_para,
            loc_para,
            reason_para
        ])

    main_table = Table(table_rows, colWidths=col_widths, repeatRows=1)
    main_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, c_border),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, c_card_bg]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(main_table)

    doc.build(elements, canvasmaker=NumberedLandscapeCanvas)
    return buffer.getvalue()
