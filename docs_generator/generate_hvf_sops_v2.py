#!/usr/bin/env python3
"""
HVF / AVNL Enterprise Standard Operating Procedure (SOP) PDF Generator - VERSION 2
==================================================================================
Generates 5 distinct, strictly 8-page Version 2 Standard Operating Procedure (SOP)
PDF documents for Heavy Vehicles Factory (HVF), A Unit of Armoured Vehicles Nigam
Limited (AVNL), Ministry of Defence, Avadi, Chennai.

Version 2 upgrades:
- Incorporates Engineering Change Orders (ECO / ECN-2026-V2 Series).
- Upgrades metrology to Industry 4.0 IoT telemetry, AI weld bead vision diagnostics,
  sub-micron multi-channel laser trackers, and automated digital passport logging.
- Retains exact 8-page structural budget with explicit PageBreak boundaries.

Dependencies:
    pip install reportlab faker
"""

import os
from datetime import datetime
from faker import Faker

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ============================================================================
# 1. CORPORATE-MILITARY & DPSU COLOR PALETTE
# ============================================================================
NAVY_PRIMARY = colors.HexColor("#1E3A8A")     # Deep Navy Blue
SLATE_DARK = colors.HexColor("#475569")       # Dark Slate Blue/Grey
SLATE_LIGHT = colors.HexColor("#94A3B8")      # Light Slate Blue/Grey
CRIMSON_ALERT = colors.HexColor("#B91C1C")    # Crisp Crimson Security Alert
CRIMSON_DARK = colors.HexColor("#991B1B")     # Deep Crimson Accent
SURFACE_TINT = colors.HexColor("#F8FAFC")     # Alternating Table Row Fill
HEADER_TINT = colors.HexColor("#EFF6FF")      # Subtle Navy Tint for Sub-Headers
TEXT_DARK = colors.HexColor("#0F172A")        # High-Contrast Charcoal Body Text

# Deterministic Faker seed for V2 generation
fake = Faker("en_IN")
Faker.seed(2027)


# ============================================================================
# 2. TWO-PASS CANVAS FOR RUNNING HEADERS & DYNAMIC "Page X of 8" FOOTERS
# ============================================================================
class DPSUNumberedCanvasV2(canvas.Canvas):
    """
    Two-pass ReportLab Canvas for Version 2 SOPs. Captures all page states
    before committing to disk, printing dynamic 'Page X of Y' alongside
    official HVF/AVNL defence classification headers and footer disclaimers.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_header_footer(total_pages)
            super().showPage()
        super().save()

    def _draw_header_footer(self, total_pages: int):
        self.saveState()
        page_width, page_height = A4
        left_margin = 45.0
        right_edge = page_width - 45.0

        # --- TOP RUNNING HEADER ---
        header_y = page_height - 34.0
        self.setFont("Helvetica-Bold", 7.5)
        self.setFillColor(CRIMSON_ALERT)
        self.drawString(
            left_margin,
            header_y,
            "RESTRICTED — FOR OFFICIAL USE ONLY (DEFENCE PRODUCTION)",
        )

        self.setFont("Helvetica-Bold", 7.5)
        self.setFillColor(NAVY_PRIMARY)
        self.drawRightString(
            right_edge,
            header_y,
            "HEAVY VEHICLES FACTORY (HVF) | AVNL AVADI [VER 2.0]",
        )

        # 0.75-width rule line separating header from body content
        self.setStrokeColor(SLATE_LIGHT)
        self.setLineWidth(0.75)
        self.line(left_margin, header_y - 6.0, right_edge, header_y - 6.0)

        # --- BOTTOM RUNNING FOOTER ---
        footer_line_y = 42.0
        self.setStrokeColor(SLATE_LIGHT)
        self.setLineWidth(0.75)
        self.line(left_margin, footer_line_y, right_edge, footer_line_y)

        # Confidentiality disclaimer on the left
        self.setFont("Helvetica", 7.0)
        self.setFillColor(SLATE_DARK)
        self.drawString(
            left_margin,
            footer_line_y - 11.0,
            "PROPRIETARY DPSU TECHNICAL DOCUMENT (VER 2.0) — ARMOURED VEHICLES NIGAM LIMITED (MOD, GOVT. OF INDIA)",
        )
        self.setFont("Helvetica-Oblique", 6.5)
        self.setFillColor(CRIMSON_DARK)
        self.drawString(
            left_margin,
            footer_line_y - 20.0,
            "Unauthorized reproduction, transmission, or disclosure is punishable under the Official Secrets Act, 1923.",
        )

        # Dynamic "Page X of 8" indicator on the right
        self.setFont("Helvetica-Bold", 8.0)
        self.setFillColor(NAVY_PRIMARY)
        self.drawRightString(
            right_edge,
            footer_line_y - 13.0,
            f"Page {self._pageNumber} of {total_pages}",
        )

        self.restoreState()


# ============================================================================
# 3. TYPOGRAPHY & PARAGRAPH STYLES
# ============================================================================
def build_styles() -> dict:
    base_styles = getSampleStyleSheet()

    return {
        "BannerSub": ParagraphStyle(
            name="BannerSub",
            parent=base_styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=12.0,
            textColor=CRIMSON_DARK,
            alignment=TA_LEFT,
            spaceAfter=4,
        ),
        "Title": ParagraphStyle(
            name="SOPTitle",
            parent=base_styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=19.0,
            leading=23.5,
            textColor=NAVY_PRIMARY,
            alignment=TA_LEFT,
            spaceBefore=2,
            spaceAfter=9,
            keepWithNext=True,
        ),
        "H1": ParagraphStyle(
            name="SOPH1",
            parent=base_styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=12.0,
            leading=16.0,
            textColor=NAVY_PRIMARY,
            alignment=TA_LEFT,
            spaceBefore=8,
            spaceAfter=6,
            keepWithNext=True,
        ),
        "H2": ParagraphStyle(
            name="SOPH2",
            parent=base_styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=14.0,
            textColor=SLATE_DARK,
            alignment=TA_LEFT,
            spaceBefore=8,
            spaceAfter=4,
            keepWithNext=True,
        ),
        "Body": ParagraphStyle(
            name="SOPBody",
            parent=base_styles["BodyText"],
            fontName="Helvetica",
            fontSize=10.0,
            leading=14.5,
            textColor=TEXT_DARK,
            alignment=TA_JUSTIFY,
            spaceBefore=0,
            spaceAfter=7,
        ),
        "Callout": ParagraphStyle(
            name="SOPCallout",
            parent=base_styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=9.0,
            leading=13.0,
            textColor=CRIMSON_DARK,
            alignment=TA_LEFT,
            backColor=colors.HexColor("#FEF2F2"),
            borderColor=CRIMSON_ALERT,
            borderWidth=0.75,
            borderPadding=7,
            spaceBefore=4,
            spaceAfter=8,
            keepWithNext=True,
        ),
        "TableHeader": ParagraphStyle(
            name="SOPTableHeader",
            parent=base_styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=11.5,
            textColor=colors.white,
            alignment=TA_LEFT,
        ),
        "TableCell": ParagraphStyle(
            name="SOPTableCell",
            parent=base_styles["Normal"],
            fontName="Helvetica",
            fontSize=8.2,
            leading=11.2,
            textColor=TEXT_DARK,
            alignment=TA_LEFT,
        ),
        "TableCellBold": ParagraphStyle(
            name="SOPTableCellBold",
            parent=base_styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.2,
            leading=11.2,
            textColor=NAVY_PRIMARY,
            alignment=TA_LEFT,
        ),
    }


# ============================================================================
# 4. 5 DISTINCT DEFENCE PRODUCTION TARGETS - VERSION 2 ENHANCED DATASETS
# ============================================================================
SOP_V2_DATASETS = [
    {
        "filename": "HVF_SOP_1_Hull_Welding_v2.pdf",
        "doc_code": "HVF/AVNL/SOP-MBT/HW-101-V2",
        "rev": "Rev 5.0 [Version 2.0]",
        "ecn_ref": "ECO-HVF-2026-WLD-881",
        "platform": "MBT T-90S Bhishma / Arjun Mk-1A (Batch-II Series)",
        "shop": "Advanced Robotic Hull Fabrication & Laser Cell (Shop-04A)",
        "security_class": "RESTRICTED — DEFENCE PRODUCTION",
        "title": "Armoured Hull Fabrications & High-Tensile Steel Welds (Version 2)",
        "exec_summary": (
            "Version 2.0 of this Standard Operating Procedure incorporates Engineering Change Order "
            "ECO-HVF-2026-WLD-881, integrating automated twin-wire pulse-GMAW robotics, real-time "
            "optical seam-tracking pyrometry, and AI-assisted volumetric Phased-Array Ultrasonic Testing "
            "(PAUT) for ultra-heavy RHA and composite glacis armour welds at Heavy Vehicles Factory (HVF), "
            "Avadi. All operations mandate strict closed-loop induction thermal envelopes to prevent "
            "micro-segregation and hydrogen embrittlement under combat shock loads."
        ),
        "scope_kpis": [
            ("Armour Metallurgy Spec", "MIL-DTL-12560K / DMR-1700B Ultra-Tough RHA (420–460 BHN)"),
            ("Adaptive Heat Control", "160°C min preheat; 210°C max interpass with closed-loop IR tracking"),
            ("Automated NDT Scan", "Full-volume 128-element PAUT + TOFD with automated defect classification"),
            ("Hull Datum Envelope", "6-DoF Laser Tracker Volumetric Envelope Tolerance ≤ ±0.50 mm (6.8 m span)"),
        ],
        "sections": [
            {
                "num": "1.0",
                "title": "RHA Plate Receiving, AI Ultrasonic Ingot Mapping & CNC Laser Beveling",
                "domain_lead": (
                    "Incoming high-hardness RHA armour plates undergo automated multi-channel ultrasonic "
                    "delamination scans, portable spark OES metallurgical confirmation, and multi-axis "
                    "fibre-laser weld bevel contouring to achieve exact double-V profiles."
                ),
                "metrics": [
                    ("1.1", "Laser Spark Spectrometry", "0.60 – 0.65 CEV strict limit", "Spectro-Optical Spark Analyzer", "100% Ingot Batches"),
                    ("1.2", "Through-Thickness Hardness", "420 – 460 HBW (10 mm depth)", "Automated King Indenter (3000 kgf)", "7 Points / Plate"),
                    ("1.3", "CNC Fibre-Laser Bevel Angle", "60° ± 0.8° / 2.2 ± 0.2 mm root", "Non-Contact Laser Profiler", "Every 300 mm"),
                    ("1.4", "Automated Laminar UT Scan", "Zero inclusions > 1.0 mm dia", "Automated Gantry C-Scan UT", "100% Plate Area"),
                    ("1.5", "Surface Oxide Micro-Etch", "Sa 2.5 grit blast cleanliness", "Surface Roughness Comparator", "Pre-Fitup Gate"),
                ],
            },
            {
                "num": "2.0",
                "title": "Robotic Turnover Jig Locking & Dual-Tracker 6-DoF Geometric Alignment",
                "domain_lead": (
                    "Armour assemblies are locked inside the servo-controlled 65-tonne turnover positioner. "
                    "Dual Leica AT960 laser trackers establish active real-time coordinate links to verify "
                    "hull symmetry, glacis angle, and belly plate flatness before robotic tacking."
                ),
                "metrics": [
                    ("2.1", "6-DoF Master Hull Centreline", "± 0.25 mm to master digital CAD", "Synchronized Dual Laser Trackers", "Continuous Feedback"),
                    ("2.2", "Glacis-to-Sponson Root Gap", "2.4 mm ± 0.25 mm uniform gap", "High-Resolution Laser Line Wand", "Every 200 mm"),
                    ("2.3", "Transverse Bulkhead Pitch", "≤ 0.35 mm across 2,400 mm frame", "Electronic Precision Autocollimator", "6 Hull Stations"),
                    ("2.4", "Hydraulic Clamping Servo Force", "180 bar ± 3 bar active hold", "Digital Transducer SCADA Array", "Real-Time Bus"),
                    ("2.5", "Pulse Tack Weld Energy", "0.85 – 1.05 kJ/mm pulse tack", "Digital Power Source Monitor", "100% Tack Welds"),
                ],
            },
            {
                "num": "3.0",
                "title": "Closed-Loop Induction Pre-Heating & Gas-Purged Consumable Vaults",
                "domain_lead": (
                    "High-frequency flexible induction coils provide closed-loop thermal regulation "
                    "across thick armour weld interfaces. Austenitic consumables are stored in nitrogen-"
                    "blanketed holding vaults to restrict diffusible hydrogen to ultra-low H2 levels."
                ),
                "metrics": [
                    ("3.1", "Induction Pre-Heat Uniformity", "160°C – 185°C (100 mm zone)", "Multi-Zone Closed-Loop Pyrometer", "Continuous Auto-Reg"),
                    ("3.2", "Peak Interpass Temperature", "≤ 210°C strict cutoff threshold", "Contact Thermocouple Array", "Pass-by-Pass Hold"),
                    ("3.3", "Diffusible Hydrogen Grade", "≤ 2.0 ml / 100g deposit (Grade H2)", "Gas Chromatography Lot Cert", "Per Consumable Spool"),
                    ("3.4", "Robotic Wire Feeder Enclosure", "Heated purge box @ 45°C / <15% RH", "Digital RH / Temp Logger", "Continuous Shift Run"),
                    ("3.5", "Quad-Mix Shielding Gas Purity", "Ar/CO2/O2/He blend dew pt <-55°C", "Inline Paramagnetic Dew Point Meter", "Continuous Header"),
                ],
            },
            {
                "num": "4.0",
                "title": "Synchronized Twin-Wire Tandem GMAW & Vision Seam-Tracking Robotics",
                "domain_lead": (
                    "Gantry-mounted 7-axis welding robots execute synchronized twin-wire submerged/pulse "
                    "GMAW passes. High-speed laser-vision tracking dynamically adjusts torch angles, "
                    "oscillation amplitude, and wire feed speeds to maintain constant heat input."
                ),
                "metrics": [
                    ("4.1", "Adaptive Heat Input Ceiling", "1.10 – 1.55 kJ/mm closed-loop", "Weld Controller Telemetry SCADA", "Millisecond Logging"),
                    ("4.2", "Lead/Trail Wire Synchronization", "Lead 240A / Trail 195A (± 5A)", "High-Speed Dual Amperage Shunts", "Every Pass Segment"),
                    ("4.3", "Optical Seam Tracking Offset", "≤ 0.20 mm torch-to-joint delta", "3D Optical Laser Vision Head", "50 Hz Auto-Correct"),
                    ("4.4", "Capping Bevel Symmetry", "1.2 mm – 2.0 mm flat reinforcement", "Laser Profile Bead Scanner", "Every 150 mm"),
                    ("4.5", "Hull Symmetric Distortion Delta", "≤ 15°C bilateral temperature delta", "Dual Thermal Flir Vision Matrix", "Continuous Twin Run"),
                ],
            },
            {
                "num": "5.0",
                "title": "Controlled Cryogenic/Induction Stress Neutralization & Annealing",
                "domain_lead": (
                    "Immediately post-welding, microprocessor-controlled ceramic heating blankets enforce "
                    "isothermal hydrogen bakeout followed by high-energy sub-resonant vibratory stress "
                    "relief (VSR) to eliminate micro-strains without compromising plate hardness."
                ),
                "metrics": [
                    ("5.1", "Hydrogen Effusion Bakeout", "220°C soak for 240 min continuous", "16-Channel SCADA Data Recorder", "100% Critical Joints"),
                    ("5.2", "Ramped Thermal Cooling Rate", "≤ 25°C / hour down to 50°C", "Automated Blanket Ramp Controller", "Full Post-Weld Cycle"),
                    ("5.3", "VSR Stress Peak Neutralization", "≥ 45% reduction in residual stress", "High-Speed Dynamic Strain Gauging", "6 Hull Reference Nodes"),
                    ("5.4", "Torsion Housing Alignment Shift", "≤ 0.25 mm total post-weld drift", "Laser Bore Inspection System", "Cold Hull Sign-Off"),
                    ("5.5", "Turret Base Mounting Plane Flat", "≤ 0.35 mm across 2.2 m circle", "Precision Electronic Inclinometer", "36-Point Radial Scan"),
                ],
            },
            {
                "num": "6.0",
                "title": "128-Element Phased-Array PAUT, TOFD & Digital Passport Archival",
                "domain_lead": (
                    "Following a mandatory 72-hour metallurgical stabilization window, automated "
                    "128-element PAUT, Time-of-Flight Diffraction (TOFD), and fluorescent magnetic "
                    "particle inspection generate a cryptographic digital twin inspection dossier."
                ),
                "metrics": [
                    ("6.1", "Stabilization Hold Window", "≥ 72 Hours ambient post-cooling", "MES Digital Timestamp Lockout", "Automated Gate"),
                    ("6.2", "128-Element PAUT Scan Map", "Zero planar defects, zero lack of fusion", "Phased-Array Encoder System", "100% Structural Welds"),
                    ("6.3", "TOFD Flaw Sizing Precision", "Height sizing accuracy ± 0.3 mm", "Dual-Probe TOFD Acoustic Gantry", "Full Ballistic Seams"),
                    ("6.4", "Sub-Surface Micro-Crack Check", "Zero indications > 0.3 mm length", "Wet Fluorescent Magnetic Particle", "100% Heat-Affected Zone"),
                    ("6.5", "AVNL Blockchain / Digital Stamp", "Signed by DGQA & HVF Chief Met", "Cryptographic Digital Twin Passport", "Release to Paint Bay"),
                ],
            },
        ],
    },
    {
        "filename": "HVF_SOP_2_Turret_Integration_v2.pdf",
        "doc_code": "HVF/AVNL/SOP-MBT/TI-204-V2",
        "rev": "Rev 4.5 [Version 2.0]",
        "ecn_ref": "ECO-HVF-2026-TUR-419",
        "platform": "MBT T-90S Bhishma / Arjun Mk-1A (Upgraded Turret)",
        "shop": "Digitized Turret Integration & Stabilized Drive Bay (Shop-09A)",
        "security_class": "RESTRICTED — DEFENCE PRODUCTION",
        "title": "Turret Mount System Alignment & Ring Gear Fitting (Version 2)",
        "exec_summary": (
            "Version 2.0 introduces upgraded sub-micron laser plinth mapping, high-load ceramic-hybrid "
            "bearing ball integration, dual-pinion anti-backlash electric traverse actuators, and "
            "contactless optical rotary slip-rings under ECO-HVF-2026-TUR-419. These enhancements "
            "maximize line-of-sight stabilization accuracy and prevent ring deflection under heavy "
            "high-explosive squash head (HESH) and kinetic energy armor impacts."
        ),
        "scope_kpis": [
            ("Plinth Flatness Matrix", "≤ 0.035 mm total indicator reading (TIR) across 2,240 mm pitch diameter"),
            ("Dual-Pinion Backlash", "0.14 mm – 0.20 mm electronically pre-loaded dual pinion drives"),
            ("Static Breakaway Torque", "≤ 380 Nm smooth breakaway across continuous 360° rotation"),
            ("Gigabit Optical Slip-Ring", "Fibre-optic rotary joint loss ≤ 1.2 dB; power channel isolation ≥ 1000 MΩ"),
        ],
        "sections": [
            {
                "num": "1.0",
                "title": "Sub-Micron Laser Tracker Plinth Mapping & Multi-Axis CNC Re-Facing",
                "domain_lead": (
                    "The hull upper plinth and turret lower base ring undergo high-density surface scanning "
                    "via 72 azimuth radial stations using laser interferometer tracking. Micron-level "
                    "high spots are corrected using portable orbital CNC milling heads prior to race fitment."
                ),
                "metrics": [
                    ("1.1", "Laser Plinth Flatness Mapping", "≤ 0.035 mm TIR across 360° circle", "Leica AT960 Absolute Tracker", "72 Azimuth Points"),
                    ("1.2", "Bearing Spigot Concentricity", "≤ 0.025 mm radial runout to datum", "Electronic Linear Variable Transducer", "24 Radial Sectors"),
                    ("1.3", "Milled Surface Finish", "Ra ≤ 0.8 µm super-finished plinth", "Digital Optical Stylus Profiler", "12 Sector Audits"),
                    ("1.4", "Fastener Hole Pitch Circle", "± 0.05 mm true position tolerance", "High-Precision Coordinate Probe", "All 72 M20 Holes"),
                    ("1.5", "Bimetallic Laser-Sintered Shims", "0.01 mm precision ground shims", "Sub-Micron Electronic Micrometer", "Custom Fit Matrix"),
                ],
            },
            {
                "num": "2.0",
                "title": "Ceramic-Hybrid Cross-Roller Bearing Assembly & Low-Temp Grease Injection",
                "domain_lead": (
                    "Silicon nitride (Si3N4) ceramic-hybrid roller elements and induction-hardened "
                    "titanium-nitride coated raceways are assembled under cleanroom Class-10000 conditions "
                    "and charged with nano-PTFE low-temperature synthetic grease (MIL-PRF-32014)."
                ),
                "metrics": [
                    ("2.1", "Ceramic Roller Sphericity", "± 0.001 mm diameter grouping", "Laser Bench Comparator (0.0005 mm)", "100% Roller Batches"),
                    ("2.2", "Raceway Surface Micro-Hardness", "60 – 64 HRC (case depth ≥ 5.0 mm)", "Micro-Vickers Hardness Tester", "16 Azimuth Checks"),
                    ("2.3", "Bearing Preload Axial Float", "0.020 – 0.045 mm calibrated float", "Digital Differential Dial Transducers", "8 Equal Quadrants"),
                    ("2.4", "Plinth Assembly Cleanliness", "ISO 14644-1 Class 7 clean tent", "Optical Airborne Particle Counter", "Pre-Assembly Check"),
                    ("2.5", "Synthetic Grease Mass Dose", "5.2 kg ± 0.10 kg MIL-PRF-32014", "Automated Dispense Flow Computer", "Dual Port Injection"),
                ],
            },
            {
                "num": "3.0",
                "title": "Dual-Pinion Anti-Backlash Gearbox Meshing & Tooth Profilometry",
                "domain_lead": (
                    "To eliminate mechanical deadband during stabilized high-speed gun tracking, "
                    "dual electronically pre-loaded drive pinions are engaged with the internal spur "
                    "ring gear and calibrated using non-contact optical gear flank profilers."
                ),
                "metrics": [
                    ("3.1", "Internal Gear Involute Error", "≤ 0.035 mm profile deviation", "Optical Coordinate Measuring Head", "Every 12th Tooth"),
                    ("3.2", "Dual-Pinion Backlash Envelope", "0.14 mm – 0.20 mm combined lash", "Electronic Master Pinion Transducer", "18 Azimuth Stations"),
                    ("3.3", "Dynamic Flank Contact Pattern", "≥ 85% flank face tooth engagement", "Fluorescent Contact Mesh Imaging", "4 Mesh Zones"),
                    ("3.4", "Torque-Angle Fastener Clamp", "360 Nm + 45° angle torque", "Smart DC Transducer Nutrunner", "All 72 Grade 12.9 Studs"),
                    ("3.5", "Fastener Ultrasonic Preload", "Within ± 4% target clamping force", "Ultrasonic Bolt Load Gauge", "100% Foundation Bolts"),
                ],
            },
            {
                "num": "4.0",
                "title": "Automated Crane Docking, Active Force Feedback & Overturn Clamping",
                "domain_lead": (
                    "A 35-tonne synchronized overhead crane with 4-point active load-cell balancing "
                    "lowers the fully integrated combat turret onto the bearing ring within 0.15 degrees "
                    "of level, followed by hydraulic torque-tensioning of the retention clamps."
                ),
                "metrics": [
                    ("4.1", "Crane Active Level Control", "≤ 0.12° tilt during full descent", "Wireless Real-Time Inclinometers", "Continuous Lowering"),
                    ("4.2", "Ring Flange Seating Uniformity", "Zero feeler clearance (0.02 mm leaf)", "Sub-Zero Feeler Gauge Blade", "360° Circumference"),
                    ("4.3", "Hydraulic Retention Nut Tension", "440 Nm ± 10 Nm active hydraulic", "Multi-Head Synchronous Tensioner", "All 64 Anchor Studs"),
                    ("4.4", "Ballistic Labyrinth Mud Clearance", "1.6 mm ± 0.2 mm calibrated gap", "Non-Ferrous Ultrasonic Gap Tool", "36 Points / Ring"),
                    ("4.5", "Hermetic NBC Seal Differential", "≤ 0.8 L/min decay @ 4.0 kPa test", "Automated Pressure Decay Unit", "15-Min Test Hold"),
                ],
            },
            {
                "num": "5.0",
                "title": "Fibre-Optic Rotary Joint (FORJ) Integration & Digital Servo Traverse Tuning",
                "domain_lead": (
                    "The combined contactless multi-channel fibre-optic rotary joint (FORJ) and 400A "
                    "power transfer slip-ring unit are coaxial-aligned, followed by digital CAN-Bus "
                    "servo tuning of the traverse drive amplifiers to achieve sub-milliradian response."
                ),
                "metrics": [
                    ("5.1", "FORJ Optical Insertion Loss", "≤ 1.2 dB across all 8 fibre cores", "Optical Time-Domain Reflectometer", "All Optical Channels"),
                    ("5.2", "High-Voltage Isolation Barrier", "≥ 1000 MΩ @ 1000 VDC test", "Digital Automated Megohmmeter", "Phase-to-Chassis"),
                    ("5.3", "Maximum Traverse Slew Rate", "≥ 42.0 deg/sec fully stabilized", "Precision Gyro Telemetry Bench", "360° CW & CCW Slew"),
                    ("5.4", "Micro-Stepping Creep Velocity", "≤ 0.025 mrad/sec jerk-free creep", "Laser Autocollimator Target", "Fine Tracking Loop"),
                    ("5.5", "CAN-Bus Latency Envelopes", "≤ 1.2 ms message update latency", "Network Bus Protocol Analyzer", "Continuous Drive Log"),
                ],
            },
            {
                "num": "6.0",
                "title": "Dynamic 3-Axis Shake Rig Testing, Gyro Drift & Final Sign-Off",
                "domain_lead": (
                    "The entire hull-turret assembly is subjected to 3-axis hydraulic road-vibration "
                    "simulation and 15-degree cant-angle rotational torque profiling to verify that "
                    "the line-of-sight stabilization loop maintains sub-milliradian lock."
                ),
                "metrics": [
                    ("6.1", "Cant-Angle Running Torque (15°)", "≤ 410 Nm dynamic continuous", "Wireless Telemetry Torque Flange", "3 Full Rotations"),
                    ("6.2", "Dynamic Stabilization Drift", "≤ 0.08 mrad RMS during shake", "Dual-Axis Optical Gyroscope", "5-Min Vibration Cycle"),
                    ("6.3", "Emergency Auxiliary Hand Drive", "≤ 30 N handle crank effort", "Digital Hand-Crank Dynamometer", "360° Manual Rotation"),
                    ("6.4", "True Azimuth Resolver Linearity", "≤ 0.10 mrad maximum deviation", "Master Optical Theodolite Grid", "Every 15° Index"),
                    ("6.5", "Turret Lock Pin Shear Test", "Zero deflection under 120 kN lock", "Hydraulic Verification Cylinder", "Lock Pin Engagement"),
                ],
            },
        ],
    },
    {
        "filename": "HVF_SOP_3_Engine_Alignment_v2.pdf",
        "doc_code": "HVF/AVNL/SOP-MBT/EA-309-V2",
        "rev": "Rev 6.0 [Version 2.0]",
        "ecn_ref": "ECO-HVF-2026-ENG-620",
        "platform": "MBT T-90S / Arjun Mk-1A (1500 HP Powerpack System)",
        "shop": "Digitized Powerpack Test Bay & Dyno Cell (Shop-12A)",
        "security_class": "RESTRICTED — DEFENCE PRODUCTION",
        "title": "High-Power Multi-Fuel V12 Engine Dropping & Alignment (Version 2)",
        "exec_summary": (
            "Version 2.0 of this SOP implements Engineering Change Order ECO-HVF-2026-ENG-620, "
            "standardizing the integration of the 1,500 HP electronically managed common-rail "
            "V12 multi-fuel powerpack with automatic powershift transmission at HVF Avadi. "
            "Key upgrades include wireless multi-sensor laser shaft alignment, automated quick-disconnect "
            "dry-break fluid headers, and dynamometer transient response certification."
        ),
        "scope_kpis": [
            ("Thermal Shaft Offset", "Cold offset targeting +0.10 mm vertical rise; running offset ≤ 0.035 mm"),
            ("Hydraulic Mount Damping", "Hydromount stiffness tuned within ± 2.0% dynamic load curve"),
            ("Automated Fluid Purge", "Helium leak detection ≤ 1.0 x 10^-5 mbar.L/s across high-pressure fuel lines"),
            ("Full Dyno Hot-Fire", "1,103 kW (1500 HP) @ 2,200 RPM; continuous telemetry data logging"),
        ],
        "sections": [
            {
                "num": "1.0",
                "title": "Rear Engine Bay Metrology, Hydromount Damping & Fire-Wire Sensor Checks",
                "domain_lead": (
                    "The rear hull engine compartment undergoes 3D coordinate scanning. Active hydromount "
                    "damping units are matched and calibrated, while optical fire-wire detection and "
                    "automatic fire extinguishing system (AFES) sensor loops are verified."
                ),
                "metrics": [
                    ("1.1", "Engine Bay Mount Co-Planarity", "≤ 0.05 mm across 4 chassis nodes", "High-Precision Laser Plane Tool", "Pre-Drop Survey"),
                    ("1.2", "Final Drive Input Concentricity", "≤ 0.04 mm bilateral runout", "Laser Bore Alignment Kit", "Port & Starboard"),
                    ("1.3", "Active Hydromount Damping Curve", "± 2.0% of nominal dynamic kN/mm", "Servo-Hydraulic Test Rig", "Matched Set of 4"),
                    ("1.4", "Automated Bilge Pump Output", "≥ 80 L/min high-head scavenge", "Digital Flowrate Transducer", "Pre-Install Gate"),
                    ("1.5", "Optical Flame Detector BIT", "Response time ≤ 45 milliseconds", "Calibrated UV/IR Test Source", "All Bay Detectors"),
                ],
            },
            {
                "num": "2.0",
                "title": "Powerpack Hoisting, 3D Guided Lowering & Hydraulic Trunnion Seating",
                "domain_lead": (
                    "The 5.5-tonne integrated powerpack assembly is rigged via a precision 4-point "
                    "servo hoist and lowered through the armoured deck aperture with real-time "
                    "proximity clearance telemetry before torquing the isolation trunnions."
                ),
                "metrics": [
                    ("2.1", "Wireless Hoist Load Symmetry", "Load delta ≤ 1.5% between cables", "Wireless Telemetry Load Shackles", "Full Lift Cycle"),
                    ("2.2", "Deck Aperture Edge Clearance", "≥ 22.0 mm uniform perimeter gap", "Laser Distance Sensor Array", "4 Hull Corners"),
                    ("2.3", "Mount Pad Dry Seating Gap", "≤ 0.025 mm before bolting", "Precision Feeler Ribbon Gauge", "All 4 Isolator Pads"),
                    ("2.4", "Electronic Torque-Angle Tighten", "560 Nm + 45° angle control", "Digital Recording Nutrunner", "16 High-Tensile Bolts"),
                    ("2.5", "Dual Grounding Mesh Resistance", "≤ 0.8 mΩ chassis-to-crankcase", "4-Wire Micro-Ohmmeter", "Both Braided Straps"),
                ],
            },
            {
                "num": "3.0",
                "title": "Wireless Multi-Sensor Dual-Laser Shaft Alignment & Thermal Compensation",
                "domain_lead": (
                    "Continuous wireless dual-laser sensors measure radial and angular offset between "
                    "the engine flywheel output and transmission input torque converter, compensating "
                    "for thermal chassis expansion (+0.10 mm vertical rise at full operating temp)."
                ),
                "metrics": [
                    ("3.1", "Parallel Radial Offset (Cold)", "≤ 0.035 mm TIR (target -0.10 mm V)", "Continuous Dual-Laser Aligner", "Full 360° Rotation"),
                    ("3.2", "Angular Face Misalignment", "≤ 0.025 mm per 100 mm diameter", "Multi-Sensor Wireless Aligner", "Clockwise Sweep"),
                    ("3.3", "Flexible Coupling Axial Gap", "2.00 mm ± 0.15 mm axial float", "Digital Depth Micrometer", "Post-Coupling Gate"),
                    ("3.4", "Intermediate Cardan Spline Play", "≤ 0.04 mm radial spline backlash", "Dial Test Indicator Setup", "Port & Starboard"),
                    ("3.5", "Coupling Stud Torque Retention", "210 Nm ± 5 Nm (Loctite 270)", "Calibrated DC Electronic Tool", "All 16 Drive Studs"),
                ],
            },
            {
                "num": "4.0",
                "title": "Common-Rail Fuel Lines, Dry-Break Quick-Disconnects & Helium Sniffing",
                "domain_lead": (
                    "Armoured double-walled high-pressure common-rail fuel manifolds, titanium dry-sump "
                    "lines, and ethylene-glycol cooling circuits are coupled using zero-leak quick-disconnect "
                    "fittings and tested using mass-spectrometer helium sniffing."
                ),
                "metrics": [
                    ("4.1", "Helium Leak Detection Test", "≤ 1.0 x 10^-5 mbar.L/s leak rate", "Mass Spectrometer Helium Sniffer", "100% Fuel Joints"),
                    ("4.2", "Dry-Sump Lubrication Flushing", "ISO 4406 Cleanliness 14/12/09", "Laser Particle Counter Unit", "20-Min Bypass Flush"),
                    ("4.3", "Dual Cooling Circuit Pressure", "2.5 bar hold for 45 minutes", "Digital Precision Pressure Decay", "Zero Loss Allowed"),
                    ("4.4", "Pneumatic Starter Tank Bottle", "200 bar dry nitrogen charge", "Digital Transducer Test Point", "Emergency Air Bottle"),
                    ("4.5", "Quick-Disconnect Latch Lock", "Full secondary detent engagement", "Audible & Visual Ring Gauge", "All Fluid Lines"),
                ],
            },
            {
                "num": "5.0",
                "title": "Multi-Cyclone Pre-Cleaners, Twin Wastegate Turbos & Thermal IR Shrouds",
                "domain_lead": (
                    "High-efficiency cyclonic vortex dust pre-cleaners, twin variable-geometry wastegate "
                    "turbochargers, and aerogel thermal insulation shrouds are vacuum-checked to ensure "
                    "reliable operation in 55°C desert environments and 5-meter deep-fording."
                ),
                "metrics": [
                    ("5.1", "Air Intake Vacuum Integrity", "Hold -20 kPa for 180 seconds", "Digital Vacuum Pressure Sensor", "Compressor Inlets"),
                    ("5.2", "Vortex Dust Scavenge Blower", "≥ 99.2% desert sand separation", "Differential Flow Transducer", "Scavenge Exit Port"),
                    ("5.3", "Turbo Clamp Retaining Torque", "32 Nm ± 1.5 Nm with nickel paste", "Calibrated Torque Screwdriver", "All Exhaust Clamps"),
                    ("5.4", "Fording Check Valve Ingress", "Zero water entry @ 0.6 bar head", "Hydrostatic Immersion Rig", "Fording Solenoids"),
                    ("5.5", "Thermal Aerogel Shield Surface", "Outer shell ≤ 115°C at full power", "Calibrated FLIR Thermal Camera", "Full Exhaust Bay"),
                ],
            },
            {
                "num": "6.0",
                "title": "Dyno Hot-Fire Telemetry, 1500 HP Power Sign-Off & Vibration FFT",
                "domain_lead": (
                    "The integrated powerpack is linked to the automated dynamometer test cell, stepped "
                    "to its rated 1,103 kW (1500 HP) output at 2,200 RPM, and evaluated via 24-channel FFT "
                    "vibration spectral analysis before final hull sign-off."
                ),
                "metrics": [
                    ("6.1", "Pre-Lube Auto Prime Pressure", "≥ 2.2 bar within 8 seconds", "CAN-Bus Telemetry Transducer", "Automated Interlock"),
                    ("6.2", "Rated Power Output & Speed", "1,103 kW (1500 HP) @ 2,200 RPM", "Eddy-Current Dyno Load Cell", "45-Min Continuous"),
                    ("6.3", "Charge-Air Boost & Exhaust Temp", "2.8 bar boost / EGT ≤ 640°C", "Dual K-Type Exhaust Probes", "Full Load Envelope"),
                    ("6.4", "Triaxial Vibration Spectrum", "≤ 3.2 mm/s RMS (ISO 10816-6)", "24-Channel FFT Spectrum Unit", "All 4 Mount Brackets"),
                    ("6.5", "Hot-State Re-Alignment Audit", "≤ 0.025 mm radial offset @ 95°C", "Wireless Dual-Laser Hot Check", "Immediate Shutdown"),
                ],
            },
        ],
    },
    {
        "filename": "HVF_SOP_4_Torsion_Suspension_v2.pdf",
        "doc_code": "HVF/AVNL/SOP-MBT/TS-412-V2",
        "rev": "Rev 5.2 [Version 2.0]",
        "ecn_ref": "ECO-HVF-2026-SUS-533",
        "platform": "MBT T-90S / Arjun Mk-1A Heavy Tracked Chassis",
        "shop": "Automated Running Gear & Hydro-Gas Suspension Line (Shop-06A)",
        "security_class": "RESTRICTED — DEFENCE PRODUCTION",
        "title": "Torsion Bar Installation & Track Tensioning Systems (Version 2)",
        "exec_summary": (
            "Version 2.0 incorporates ECO-HVF-2026-SUS-533, deploying robotic spline indexing, "
            "servo-hydraulic road-wheel balancing, integrated semi-active rotary magnetorheological "
            "dampers, and automated electro-hydraulic track tensioners at HVF Avadi. "
            "These protocols guarantee high-speed cross-country stability and zero track shed up to 70 km/h."
        ),
        "scope_kpis": [
            ("Digital Spline Vernier", "Automated barcode-guided Left/Right preset torsion bar orientation"),
            ("Ride Height Precision", "455 mm ± 4 mm hull belly clearance across all 12 road-wheel axles"),
            ("Track Dynamic Tension", "Automated hydraulic tensioner maintains 35 mm ± 2 mm catenary sag"),
            ("Running Gear Friction", "Free-wheeling rotational torque ≤ 18 Nm per road-wheel hub"),
        ],
        "sections": [
            {
                "num": "1.0",
                "title": "Torsion Bar Barcode Scanning, Ultrasonic Flaw Detection & Nano-Coatings",
                "domain_lead": (
                    "High-purity vacuum arc remelted (VAR) steel torsion bars undergo robotic barcode "
                    "orientation audits, multi-angle immersion ultrasonic scans, and hydrophobic "
                    "ceramic-epoxy protective shaft coating thickness audits."
                ),
                "metrics": [
                    ("1.1", "Robotic Barcode Direction Audit", "100% Left/Right port/stbd match", "Industrial Barcode Vision Camera", "All 12 Torsion Bars"),
                    ("1.2", "Immersion UT Flaw Sizing", "Zero defects > 0.4 mm equivalent", "Multi-Axis Ultrasonic Tank", "Full Bar Volume"),
                    ("1.3", "Spline Tooth Pitch Geometry", "Involute error ≤ 0.008 mm", "CNC Gear Tooth Inspection Bench", "Both Splined Ends"),
                    ("1.4", "Ceramic-Epoxy Layer Shield", "150 µm – 180 µm uniform coating", "Dual Eddy-Current Film Gauge", "Along 100% Shaft"),
                    ("1.5", "High-Load Fluorosilicone Grease", "MIL-PRF-83261 paste coat", "Automated Robotic Grease Nozzle", "100% Spline Teeth"),
                ],
            },
            {
                "num": "2.0",
                "title": "Balancer Arm Needle Bearing Housings & Triple-Lip Cassette Mud Seals",
                "domain_lead": (
                    "Cast-armour hull suspension pockets are fitted with precision spherical roller/needle "
                    "bearings and heavy-duty triple-lip PTFE cassette seals, followed by pressure-purging "
                    "with high-temperature extreme-pressure synthetic grease."
                ),
                "metrics": [
                    ("2.1", "Suspension Pocket Bore Grade", "H6 precision tolerance (± 0.016 mm)", "Three-Point Internal Micrometer", "All 12 Hull Stations"),
                    ("2.2", "Balancer Arm Radial Clearance", "0.035 mm – 0.070 mm mounted fit", "Digital Indicator on Arm Flange", "12 Balancer Arms"),
                    ("2.3", "Cassette Seal Pneumatic Hold", "Hold 2.0 bar air pressure test", "Differential Decay Leak Tester", "Each Seal Housing"),
                    ("2.4", "Retaining Clamp Ring Torque", "200 Nm ± 8 Nm + mechanical lock", "Calibrated DC Transducer Wrench", "All 12 Retaining Hubs"),
                    ("2.5", "Progressive Polyurethane Bump-Stop", "220 mm ± 1.5 mm uncompressed ht", "Digital Height Gauge Caliper", "Stations 1, 2, 6 (L/R)"),
                ],
            },
            {
                "num": "3.0",
                "title": "Servo-Hydraulic Arm Pre-Loading & Automated Vernier Angle Calibration",
                "domain_lead": (
                    "An automated servo-hydraulic positioning fixture raises each road-wheel arm to its "
                    "exact design inclination while the torsion bar is vernier-engaged into the inner "
                    "hull anchor splines, equalizing individual ground-contact load distributions."
                ),
                "metrics": [
                    ("3.1", "Digital Inclinometer Arm Angle", "35.0° ± 0.2° to hull reference plane", "Dual-Axis Electronic Inclinometer", "All 12 Axle Stations"),
                    ("3.2", "Spline Vernier Full Insertion", "72.0 mm ± 0.4 mm insertion depth", "Digital Depth Micrometer", "Anchor & Lever Bores"),
                    ("3.3", "Anchor Plug Retaining Torque", "480 Nm ± 12 Nm with lock wedge", "Calibrated Multiplier Tool", "All 12 Hull Anchors"),
                    ("3.4", "Static Combat Belly Clearance", "455 mm ± 4 mm hull ground clear", "Tri-Laser Distance Sensor Rig", "Fore, Mid & Aft Hull"),
                    ("3.5", "Port-Starboard Level Balance", "≤ 1.0 mm tilt differential", "Digital Precision Water Level", "Full Vehicle Weight"),
                ],
            },
            {
                "num": "4.0",
                "title": "Semi-Active Rotary Magnetorheological Damper & Road-Wheel Fitment",
                "domain_lead": (
                    "High-performance semi-active rotary magnetorheological (MR) dampers on stations "
                    "1, 2, 5, and 6 are dynamometer-certified, coupled via splined drag links, and "
                    "followed by aluminum-alloy road-wheel hub mounting with pre-set taper roller bearings."
                ),
                "metrics": [
                    ("4.1", "MR Damper Dynamic Force Band", "50.0 kN ± 2.5 kN peak resistance", "High-Rate Servo-Dyno Rig", "All 8 Rotary Dampers"),
                    ("4.2", "Damper Link Spline Clamp Nut", "310 Nm ± 10 Nm", "Calibrated Click Torque Wrench", "All Damper Link Arms"),
                    ("4.3", "Hub Taper Roller End-Play", "0.04 mm – 0.08 mm axial preload", "Dial Indicator on Wheel Hub", "All 12 Road Wheels"),
                    ("4.4", "Wheel Stud Fastener Tension", "510 Nm ± 15 Nm (automated star)", "Multi-Spindle DC Nutrunner", "10 Studs / Wheel"),
                    ("4.5", "Hub Synthetic Oil Level & Seal", "MIL-PRF-2105E 75W-90 synthetic", "Visual Oil Window & He Sniff", "100% Wheel Hubs"),
                ],
            },
            {
                "num": "5.0",
                "title": "Laser Alignment of Drive Sprockets, Return Rollers & Front Idlers",
                "domain_lead": (
                    "A multi-beam laser tracking line is projected from the final-drive sprocket outer "
                    "teeth across all road-wheels, track return rollers, and front tensioning idler "
                    "wheels to establish a coplanar running plane within 1.0 mm over 6.8 meters."
                ),
                "metrics": [
                    ("5.1", "Sprocket-to-Idler Plane Runout", "≤ 1.0 mm total lateral variation", "Multi-Beam Long-Range Laser Jig", "Port & Starboard"),
                    ("5.2", "Road-Wheel Guide Horn Gap", "± 0.6 mm symmetrical clearance", "Digital Optical Offset Gauge", "All 6 Stations / Side"),
                    ("5.3", "Drive Sprocket Bolt Preload", "420 Nm ± 12 Nm + locking plate", "DC Torque-Angle Tool", "All 24 Sprocket Studs"),
                    ("5.4", "Top Return Roller Coaxiality", "≤ 0.8 mm to master track axis", "Laser Reference Target Wand", "All 6 Return Rollers"),
                    ("5.5", "Front Idler Spindle Clearance", "≤ 0.05 mm bearing radial play", "Dial Test Indicator Setup", "Both Front Idlers"),
                ],
            },
            {
                "num": "6.0",
                "title": "Automated Electro-Hydraulic Track Tensioning & 10 km Mobility Trial",
                "domain_lead": (
                    "High-strength forged steel track bands with vulcanized rubber pads are mounted, "
                    "tensioned via the automatic electro-hydraulic worm tensioner, and validated "
                    "through an intensive 10 km obstacle course shakedown trial."
                ),
                "metrics": [
                    ("6.1", "Track Pin Wedge Nut Torque", "380 Nm ± 10 Nm (post-10 km check)", "Calibrated Pneumatic Nutrunner", "100% Track Wedges"),
                    ("6.2", "Catenary Track Sag Envelope", "35 mm ± 2 mm between 1st/2nd roller", "Precision Laser Distance Bar", "Both Track Bands"),
                    ("6.3", "Automatic Tensioner Interlock", "Maintains tension under 250 bar", "Digital SCADA Pressure Transducer", "In-Cab Telemetry"),
                    ("6.4", "Hub Operating Temperature", "≤ 68°C after 10 km @ 50 km/h", "Calibrated FLIR IR Camera", "All 12 Hubs & 8 Dampers"),
                    ("6.5", "Post-Run Track Sag Stability", "≤ 2.0 mm sag drift post-trial", "Laser Catenary Measurement", "Final DGQA Sign-Off"),
                ],
            },
        ],
    },
    {
        "filename": "HVF_SOP_5_Gun_Calibration_v2.pdf",
        "doc_code": "HVF/AVNL/SOP-MBT/GC-518-V2",
        "rev": "Rev 5.4 [Version 2.0]",
        "ecn_ref": "ECO-HVF-2026-GUN-904",
        "platform": "125mm Smoothbore 2A46M-5 / 120mm Gun-Missile System",
        "shop": "Ordnance Integration & Laser Boresight Test Bay (Shop-15A)",
        "security_class": "RESTRICTED — DEFENCE PRODUCTION",
        "title": "Main Gun Barrel Fitment & Muzzle Reference Calibration (Version 2)",
        "exec_summary": (
            "Version 2.0 incorporates ECO-HVF-2026-GUN-904, implementing digital laser bore-mapping, "
            "automated nitrogen/hydraulic recoil buffer charging, carbon-fibre thermal shroud fitment, "
            "and continuous closed-loop Muzzle Reference System (MRS) calibration linked to the digital "
            "ballistic computer at HVF Avadi. These enhancements achieve first-round hit probabilities "
            "exceeding 92% at 2,500 meters under dynamic firing conditions."
        ),
        "scope_kpis": [
            ("Digital Bore Straightness", "Sub-micron laser bore mapping straightness ≤ 0.10 mm/m along 6.0 m length"),
            ("Recoil Pre-Charge", "Recuperator dry nitrogen pressure 64.0 ± 0.3 bar; cycle time 0.80–1.05 sec"),
            ("Boresight Harmonization", "Gunner Day Channel, Cooled Thermal Imager & LRF zeroed within ≤ 0.035 mrad"),
            ("Continuous MRS Lock", "Dynamic thermal droop compensation tracking accuracy ≤ 0.020 mrad"),
        ],
        "sections": [
            {
                "num": "1.0",
                "title": "Laser Bore Profilometry, 3D Videoscope Inspection & Breech Block Fit",
                "domain_lead": (
                    "The autofrettaged chrome-plated gun barrel undergoes 3D internal laser profilometry, "
                    "high-resolution optical videoscope inspection for micro-cracks, and precision "
                    "buttress-thread contact mapping inside the breech ring."
                ),
                "metrics": [
                    ("1.1", "Laser Internal Bore Diameter", "125.00 mm (+0.04 / -0.00 mm)", "Multi-Axis Laser Bore Gauge", "Continuous 10 mm Pitch"),
                    ("1.2", "Hard-Chrome Plating Depth", "≥ 190 µm uniform; zero pitting", "Eddy-Current Coating Sensor", "Full Chamber & Bore"),
                    ("1.3", "Bore Cumulative Straightness", "≤ 0.10 mm/m total curvature", "Laser Collimated Bore System", "Full 6,000 mm Length"),
                    ("1.4", "Interrupted Thread Flank Mesh", "≥ 90% load contact area", "Optical Flank Contrast Scanner", "All Breech Sectors"),
                    ("1.5", "Breech Wedge Drop Mechanism", "≤ 0.15 seconds rapid closure", "Optoelectronic Time Recorder", "15 Dry Cycling Runs"),
                ],
            },
            {
                "num": "2.0",
                "title": "Mantlet Cradle Bushings, Trunnion Coaxiality & Dynamic Balancing",
                "domain_lead": (
                    "The barrel is inserted through the bronze/PTFE composite cradle bushes, locked with "
                    "the interrupted wedge key, and balanced about the elevation axis with dual laser "
                    "interferometers verifying elevation trunnion coaxiality."
                ),
                "metrics": [
                    ("2.1", "Cradle Bushing Radial Gap", "0.05 mm – 0.09 mm diametral fit", "Telescopic Cylinder Gauge", "Fore & Aft Bushings"),
                    ("2.2", "Breech Wedge Key Torquing", "320 Nm ± 10 Nm on locking bolt", "Calibrated Torque Multiplier", "Primary Wedge Key"),
                    ("2.3", "Elevation Trunnion Alignment", "≤ 0.02 mm bilateral deviation", "Laser Alignment Telescope", "Mantlet Trunnions"),
                    ("2.4", "Static Out-of-Balance Torque", "≤ 14 Nm muzzle-to-breech balance", "Digital Torque Transducer Bench", "-6° to +16° Elevation"),
                    ("2.5", "Bore Evacuator Pneumatic Test", "Hold 4.0 bar pressure for 20 min", "Digital Differential Manometer", "Venturi Check Nozzles"),
                ],
            },
            {
                "num": "3.0",
                "title": "Automated Nitrogen Recuperator & Recoil Damper Charging",
                "domain_lead": (
                    "Recoil dampers and the hydro-pneumatic recuperator are vacuum-evacuated, filled with "
                    "synthetic aircraft recoil fluid (MIL-PRF-5606H), pressurized with pure nitrogen, "
                    "and cycle-tested using the automated hydraulic pull-back machine."
                ),
                "metrics": [
                    ("3.1", "Recoil Synthetic Fluid Mass", "7.50 L ± 0.03 L degassed fluid", "Automated Fluid Metering Unit", "Zero Air Entrainment"),
                    ("3.2", "Recuperator Nitrogen Charge", "64.0 bar ± 0.3 bar @ 20°C ambient", "Digital Temperature-Compensated", "Pressure Cell Test"),
                    ("3.3", "Artificial Recoil Stroke Length", "298 mm – 306 mm simulated stroke", "Hydraulic Pull-Back Actuator", "5 Consecutive Cycles"),
                    ("3.4", "Battery Run-Out Recovery Time", "0.80 – 1.05 seconds full battery", "Linear Magnetic Encoder Scale", "Zero Latch Delay"),
                    ("3.5", "Recoil Piston Rod Seal Weepage", "Zero measurable fluid droplet loss", "Optical Fluorescent Dye Scan", "Both Damper Shafts"),
                ],
            },
            {
                "num": "4.0",
                "title": "Carbon-Fibre Composite Thermal Shroud Fitment & Concentricity",
                "domain_lead": (
                    "A multi-segment ultra-lightweight carbon-fibre composite thermal shroud is secured "
                    "over the gun barrel with spring-tensioned ceramic-insulated bands to suppress "
                    "asymmetric solar gun-barrel droop and thermal bending."
                ),
                "metrics": [
                    ("4.1", "Composite Shroud Annular Gap", "5.0 mm ± 0.3 mm uniform gap", "High-Frequency Ultrasonic Probe", "All 5 Shroud Segments"),
                    ("4.2", "Spring-Tensioned Band Torque", "16.0 Nm ± 0.8 Nm torque", "Calibrated Electronic Screwdriver", "All 18 Shroud Bands"),
                    ("4.3", "Thermal Gun Droop Suppression", "≤ 0.05 mrad deflection @ Δ25°C", "Solar Simulation Heat Lamp Rig", "Muzzle Autocollimator"),
                    ("4.4", "Condensation Scavenge Drain", "6 O'Clock bottom alignment ± 1°", "Digital Protractor Gauge", "All Drain Holes"),
                    ("4.5", "Muzzle Tip Clamp Ring Runout", "≤ 0.035 mm radial runout", "Dial Indicator on Muzzle Lip", "Clamp Fastener Ring"),
                ],
            },
            {
                "num": "5.0",
                "title": "Continuous Muzzle Reference System (MRS) Permittivity Mirror Zeroing",
                "domain_lead": (
                    "The Muzzle Reference System (MRS) collimating mirror unit is mounted on the barrel "
                    "muzzle and optically harmonized to the turret-roof transceiver unit using an automated "
                    "laser boresight collimator to continuously feed thermal droop data to the fire control system."
                ),
                "metrics": [
                    ("5.1", "MRS Mirror Dovetail Seating", "≤ 0.010 mm flatness across flange", "Laser Flatness Interferometer", "Muzzle Mounting Ring"),
                    ("5.2", "Optical Transceiver Collimation", "≤ 0.015 mrad roll/pitch error", "Dioptometer Target System", "4-Quadrant Collimator"),
                    ("5.3", "Continuous Return Signal Peak", "≥ 90% optical sensor amplitude", "FCS Real-Time Signal Scope", "Active Sighting Loop"),
                    ("5.4", "Thermal Bend Dynamic Correction", "≤ 0.020 mrad tracking error", "Motorized Prism Deflection Rig", "± 2.0 mrad Sweep"),
                    ("5.5", "Mirror Retaining Bolt Torquing", "34.0 Nm ± 1.0 Nm + titanium wire", "Calibrated Torque Wrench", "4 Titanium Bolts"),
                ],
            },
            {
                "num": "6.0",
                "title": "Fire Control System (FCS) Tri-Band Sighting Harmonization & Sign-Off",
                "domain_lead": (
                    "On the 100-meter digitized indoor collimation tunnel, the mechanical bore axis is "
                    "harmonized with the Gunner's Main Day Sight, High-Definition Cooled Thermal Imager "
                    "(MWIR), Eye-Safe LRF, and Panoramic Commander Sight before final digital lock."
                ),
                "metrics": [
                    ("6.1", "Gunner Day Sight Coincidence", "≤ 0.035 mrad to bore centerline", "Automated Digital Target Array", "Azimuth & Elevation"),
                    ("6.2", "MWIR Thermal Channel Zero", "≤ 0.040 mrad to optical crosshair", "Blackbody Thermal Target Board", "Narrow & Wide FOV"),
                    ("6.3", "Eye-Safe LRF Energy Centroid", "≥ 92% beam power in 0.20 mrad", "CCD Laser Beam Profiler", "Harmonization Target"),
                    ("6.4", "Commander Hunter-Killer Slew", "≤ 0.07 mrad target handoff error", "High-Resolution Optical Resolvers", "8 Target Angles"),
                    ("6.5", "Ballistic Computer Hash Seal", "SHA-256 Checksum locked in ROM", "DGQA Secure Encryption Terminal", "Final Release Seal"),
                ],
            },
        ],
    },
]


# ============================================================================
# 5. DETERMINISTIC FAKER TECHNICAL PROSE GENERATOR (V2)
# ============================================================================
def generate_v2_technical_paragraph(domain_context: str, section_title: str, pass_idx: int) -> str:
    """
    Synthesizes dense, realistic military-industrial SOP body paragraphs
    reflecting Version 2 enhancements with strictly controlled character budgets.
    """
    faker_clause_1 = fake.sentence(nb_words=12).rstrip(".")
    faker_clause_2 = fake.sentence(nb_words=11).rstrip(".")
    eco_token = f"ECO-HVF-2026-V2-{fake.numerify(text='###')}"
    gauge_id = f"IOT-HVF-{fake.numerify(text='####')}"

    if pass_idx == 1:
        text = (
            f"<b>Operational Execution Protocol (Ver 2.0):</b> {domain_context} "
            f"In accordance with Engineering Directive <b>{eco_token}</b>, the bay technician shall "
            f"confirm that digital calibration transponder <b>{gauge_id}</b> is synchronized with "
            f"the HVF Cloud Manufacturing Execution System. Additionally, {faker_clause_1.lower()}, "
            f"verifying that all sensor telemetry complies with Class-1 Defence Quality Assurance "
            f"(DGQA) statistical process capability indices (Cpk ≥ 1.67)."
        )
    else:
        text = (
            f"<b>Quality Assurance & Non-Conformance Gate:</b> Any reading exceeding the tight "
            f"Version 2 tolerance envelope in Table {section_title.split()[0]} triggers an automated "
            f"SCADA safety trip and digital quarantine hold. Specifically, {faker_clause_2.lower()}, "
            f"while encrypted data streams from IoT node <b>{gauge_id}</b> are compiled into hull "
            f"dossier <b>{eco_token}</b> prior to advancing the assembly to the subsequent bay."
        )
    return text


# ============================================================================
# 6. PAGE BUILDERS (STRICTLY BUDGETED FOR 8 PAGES PER DOCUMENT)
# ============================================================================
def build_page_1_cover_v2(sop: dict, styles: dict) -> list:
    """
    Builds Page 1 for Version 2 SOPs.
    """
    story = []

    # Top classification & organizational sub-banner
    story.append(
        Paragraph(
            f"MINISTRY OF DEFENCE (DEPT. OF DEFENCE PRODUCTION) &bull; {sop['security_class']} &bull; VERSION 2.0 RELEASE",
            styles["BannerSub"],
        )
    )
    story.append(
        Paragraph(
            f"STANDARD OPERATING PROCEDURE: {sop['title'].upper()}",
            styles["Title"],
        )
    )
    story.append(
        HRFlowable(
            width="100%",
            thickness=1.5,
            color=NAVY_PRIMARY,
            spaceBefore=2,
            spaceAfter=10,
        )
    )

    # Metadata Control Grid Table
    story.append(Paragraph("0.1 DOCUMENT CONTROL & METADATA MATRIX (VERSION 2.0)", styles["H1"]))

    meta_data = [
        [
            Paragraph("DOCUMENT ID", styles["TableHeader"]),
            Paragraph(sop["doc_code"], styles["TableCellBold"]),
            Paragraph("REVISION & DATE", styles["TableHeader"]),
            Paragraph(f"{sop['rev']} | 30-Oct-2026", styles["TableCellBold"]),
        ],
        [
            Paragraph("ECO / ECN NUMBER", styles["TableHeader"]),
            Paragraph(sop["ecn_ref"], styles["TableCellBold"]),
            Paragraph("CORPORATE ENTITY", styles["TableHeader"]),
            Paragraph("Armoured Vehicles Nigam Ltd (AVNL)", styles["TableCell"]),
        ],
        [
            Paragraph("TARGET PLATFORM", styles["TableHeader"]),
            Paragraph(sop["platform"], styles["TableCell"]),
            Paragraph("PRODUCTION SHOP", styles["TableHeader"]),
            Paragraph(sop["shop"], styles["TableCell"]),
        ],
        [
            Paragraph("QA SURVEILLANCE", styles["TableHeader"]),
            Paragraph("DGQA (Armoured Vehicle Electronics & Hull)", styles["TableCell"]),
            Paragraph("PAGE BUDGET", styles["TableHeader"]),
            Paragraph("8 Pages (Version 2 Controlled)", styles["TableCellBold"]),
        ],
        [
            Paragraph("SUPERSEDES", styles["TableHeader"]),
            Paragraph("Version 1.0 (All Previous Issues)", styles["TableCell"]),
            Paragraph("SECURITY CLASS", styles["TableHeader"]),
            Paragraph(
                f"<font color='#B91C1C'><b>{sop['security_class']}</b></font>",
                styles["TableCell"],
            ),
        ],
    ]

    meta_table = Table(meta_data, colWidths=[95, 157.6, 95, 157.6])
    meta_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), NAVY_PRIMARY),
                ("BACKGROUND", (2, 0), (2, -1), NAVY_PRIMARY),
                ("BACKGROUND", (1, 0), (1, -1), SURFACE_TINT),
                ("BACKGROUND", (3, 0), (3, -1), SURFACE_TINT),
                ("GRID", (0, 0), (-1, -1), 0.6, SLATE_LIGHT),
                ("BOX", (0, 0), (-1, -1), 1.0, NAVY_PRIMARY),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(KeepTogether([meta_table]))
    story.append(Spacer(1, 10))

    # Executive Summary Section
    story.append(Paragraph("0.2 EXECUTIVE SUMMARY & VERSION 2 OPERATIONAL MANDATE", styles["H1"]))
    story.append(Paragraph(sop["exec_summary"], styles["Body"]))

    exec_context = (
        f"This Version 2.0 release supersedes all prior production instructions for <b>{sop['shop']}</b> "
        f"at HVF Avadi. Key enhancements under {sop['ecn_ref']} mandate automated IoT process telemetry, "
        f"multi-sensor laser tracking, and automated digital passport archival. {fake.sentence(nb_words=13)} "
        f"All operators, supervisors, and DGQA inspectors must enforce the updated tolerances herein. "
        f"{fake.sentence(nb_words=12)}"
    )
    story.append(Paragraph(exec_context, styles["Body"]))
    story.append(Spacer(1, 6))

    # Critical Engineering KPI Summary Grid
    story.append(Paragraph("0.3 VERSION 2 CRITICAL ENGINEERING ACCEPTANCE BENCHMARKS", styles["H1"]))
    kpi_rows = [
        [
            Paragraph("CRITICAL PARAMETER", styles["TableHeader"]),
            Paragraph("MANDATORY VERSION 2 ACCEPTANCE CRITERION", styles["TableHeader"]),
        ]
    ]
    for param, spec in sop["scope_kpis"]:
        kpi_rows.append(
            [
                Paragraph(param, styles["TableCellBold"]),
                Paragraph(spec, styles["TableCell"]),
            ]
        )

    kpi_table = Table(kpi_rows, colWidths=[145, 360.2])
    kpi_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY_PRIMARY),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SURFACE_TINT]),
                ("GRID", (0, 0), (-1, -1), 0.5, SLATE_LIGHT),
                ("BOX", (0, 0), (-1, -1), 0.9, NAVY_PRIMARY),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(KeepTogether([kpi_table]))
    story.append(Spacer(1, 10))

    # Security & Safety Alert Callout
    story.append(
        Paragraph(
            "VERSION 2 COMPLIANCE HOLD POINT: Under DGQA circular AVNL/2026/V2, failure to capture "
            "automated IoT sensor logs constitutes an immediate Stop-Line condition. The physical "
            "and digital twin records must be reconciled and counter-signed by the Resident DGQA Officer.",
            styles["Callout"],
        )
    )

    story.append(PageBreak())
    return story


def build_core_section_page_v2(sop: dict, sec: dict, styles: dict) -> list:
    """
    Builds one core operational technical section page (Pages 2 to 7).
    """
    story = []

    story.append(
        Paragraph(
            f"SECTION {sec['num']} — {sec['title'].upper()}",
            styles["H1"],
        )
    )
    story.append(
        HRFlowable(
            width="100%",
            thickness=1.0,
            color=SLATE_DARK,
            spaceBefore=1,
            spaceAfter=8,
        )
    )

    story.append(
        Paragraph(
            generate_v2_technical_paragraph(sec["domain_lead"], sec["title"], pass_idx=1),
            styles["Body"],
        )
    )
    story.append(
        Paragraph(
            generate_v2_technical_paragraph(sec["domain_lead"], sec["title"], pass_idx=2),
            styles["Body"],
        )
    )

    story.append(
        Paragraph(
            f"{sec['num']}.A SHOP-FLOOR EXECUTION & IOT METROLOGY DIRECTIVES (VER 2.0)",
            styles["H2"],
        )
    )

    shop_directive_para = (
        f"Prior to initiating operation <b>{sec['num']}</b> on {sop['platform']}, the bay controller "
        f"shall verify that the IoT telemetry gateway is connected and active. {fake.sentence(nb_words=13)} "
        f"All sensor readings recorded during the cycle must be verified against the tightened "
        f"Version 2 tolerance bands specified in Table {sec['num']} below."
    )
    story.append(Paragraph(shop_directive_para, styles["Body"]))
    story.append(Spacer(1, 4))

    # Tracking Table
    matrix_header = [
        Paragraph("STEP", styles["TableHeader"]),
        Paragraph("V2 TECHNICAL PARAMETER / CHECKPOINT", styles["TableHeader"]),
        Paragraph("V2 ACCEPTANCE TOLERANCE", styles["TableHeader"]),
        Paragraph("IOT METROLOGY / GAUGE", styles["TableHeader"]),
        Paragraph("SAMPLING / HOLD", styles["TableHeader"]),
    ]
    matrix_rows = [matrix_header]

    for step_id, param_name, tol_spec, gauge_name, freq_hold in sec["metrics"]:
        matrix_rows.append(
            [
                Paragraph(step_id, styles["TableCellBold"]),
                Paragraph(param_name, styles["TableCell"]),
                Paragraph(tol_spec, styles["TableCellBold"]),
                Paragraph(gauge_name, styles["TableCell"]),
                Paragraph(freq_hold, styles["TableCell"]),
            ]
        )

    tracking_table = Table(
        matrix_rows,
        colWidths=[35, 138, 118, 118, 96.2],
    )
    tracking_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY_PRIMARY),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SURFACE_TINT]),
                ("GRID", (0, 0), (-1, -1), 0.5, SLATE_LIGHT),
                ("BOX", (0, 0), (-1, -1), 1.0, NAVY_PRIMARY),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )

    story.append(
        KeepTogether(
            [
                Paragraph(
                    f"TABLE {sec['num']} — VERSION 2 TECHNICAL TRACKING & IOT VERIFICATION MATRIX",
                    styles["H2"],
                ),
                tracking_table,
            ]
        )
    )
    story.append(Spacer(1, 8))

    # Empirical Station Log Table
    log_rows = [
        [
            Paragraph("V2 ASSET SERIAL NUMBER", styles["TableHeader"]),
            Paragraph("MES TELEMETRY GATEWAY", styles["TableHeader"]),
            Paragraph("IOT OPERATOR ID", styles["TableHeader"]),
            Paragraph("DGQA VERIFICATION", styles["TableHeader"]),
            Paragraph("V2 DISPOSITION", styles["TableHeader"]),
        ],
        [
            Paragraph(f"HVF-V2-{fake.numerify(text='2026-###')}", styles["TableCellBold"]),
            Paragraph(f"IOT-GW-04 / {sop['doc_code'][-6:]}", styles["TableCell"]),
            Paragraph(f"OP-{fake.numerify(text='###')} (Biometric)", styles["TableCell"]),
            Paragraph(f"DGQA-{fake.numerify(text='##')} (Crypto-Seal)", styles["TableCell"]),
            Paragraph("ACCEPTED — PASS V2", styles["TableCellBold"]),
        ],
    ]
    log_table = Table(log_rows, colWidths=[115, 95, 100, 105, 90.2])
    log_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), SLATE_DARK),
                ("BACKGROUND", (0, 1), (-1, 1), HEADER_TINT),
                ("GRID", (0, 0), (-1, -1), 0.5, SLATE_LIGHT),
                ("BOX", (0, 0), (-1, -1), 0.75, SLATE_DARK),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(KeepTogether([log_table]))
    story.append(Spacer(1, 8))

    # Safety/Process Warning Box
    story.append(
        Paragraph(
            f"VERSION 2 HOLD POINT (SECTION {sec['num']}): Ensure all 5 parameters in Table {sec['num']} "
            f"are verified via digital telemetry and recorded in the permanent AVNL manufacturing dossier.",
            styles["Callout"],
        )
    )

    story.append(PageBreak())
    return story


def build_page_8_appendix_and_signoff_v2(sop: dict, styles: dict) -> list:
    """
    Builds Page 8 for Version 2: Appendix & Multi-Tier Sign-Off Matrix.
    """
    story = []

    story.append(
        Paragraph(
            "APPENDIX A — VERSION 2 ENGINEERING CHANGE ORDER (ECO) & REVISION LEDGER",
            styles["H1"],
        )
    )
    story.append(
        HRFlowable(
            width="100%",
            thickness=1.0,
            color=NAVY_PRIMARY,
            spaceBefore=1,
            spaceAfter=8,
        )
    )

    appendix_intro = (
        f"This Appendix documents the formal Engineering Change Orders (ECO) incorporated into "
        f"<b>{sop['title']}</b> ({sop['doc_code']}) for Version 2.0 at Heavy Vehicles Factory (HVF), "
        f"Avadi. Traceability is maintained to National Physical Laboratory (NPL) standards and the "
        f"DGQA Defence Quality Assurance Plan 2026. {fake.sentence(nb_words=12)}"
    )
    story.append(Paragraph(appendix_intro, styles["Body"]))

    # ECO Revision Ledger Table
    eco_rows = [
        [
            Paragraph("REV / ECO CODE", styles["TableHeader"]),
            Paragraph("ENGINEERING CHANGE DESCRIPTION & UPGRADE RATIONALE", styles["TableHeader"]),
            Paragraph("EFFECTIVE DATE", styles["TableHeader"]),
        ],
        [
            Paragraph("Rev 1.0 (Baseline)", styles["TableCellBold"]),
            Paragraph("Initial production baseline release for MBT serial manufacturing", styles["TableCell"]),
            Paragraph("15-Jan-2024", styles["TableCell"]),
        ],
        [
            Paragraph(f"Rev 2.0 ({sop['ecn_ref']})", styles["TableCellBold"]),
            Paragraph(
                "Upgraded to Industry 4.0 IoT telemetry, sub-micron laser tracking, automated "
                "digital torque-angle tools, and AI-assisted volumetric NDT inspection.",
                styles["TableCell"],
            ),
            Paragraph("30-Oct-2026", styles["TableCellBold"]),
        ],
        [
            Paragraph("MIL-STD-1949 / ISO 9001", styles["TableCellBold"]),
            Paragraph("Harmonized with DGQA-ARM-09 (Rev 2026) Defence Manufacturing Quality Plan", styles["TableCell"]),
            Paragraph("Current Release", styles["TableCell"]),
        ],
        [
            Paragraph("AVNL-HSE-SOP-022", styles["TableCellBold"]),
            Paragraph("Updated high-voltage, laser safety, and robotic cell interlock protocols", styles["TableCell"]),
            Paragraph("Mandatory Active", styles["TableCell"]),
        ],
    ]

    eco_table = Table(eco_rows, colWidths=[115, 290.2, 100])
    eco_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY_PRIMARY),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SURFACE_TINT]),
                ("GRID", (0, 0), (-1, -1), 0.5, SLATE_LIGHT),
                ("BOX", (0, 0), (-1, -1), 0.9, NAVY_PRIMARY),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(KeepTogether([eco_table]))
    story.append(Spacer(1, 10))

    # Multi-Tier Official Sign-Off Signature Matrix (Version 2)
    story.append(
        Paragraph(
            "APPENDIX B — VERSION 2.0 MULTI-TIER OFFICIAL SIGN-OFF & RELEASE MATRIX",
            styles["H1"],
        )
    )
    story.append(
        Paragraph(
            "Version 2.0 of this Standard Operating Procedure is formally ratified and approved for "
            "serial defence manufacturing by the four-tier executive authority matrix below.",
            styles["Body"],
        )
    )

    sig_header = [
        Paragraph("TIER / ROLE", styles["TableHeader"]),
        Paragraph("DESIGNATION & DIRECTORATE", styles["TableHeader"]),
        Paragraph("OFFICER NAME & ID", styles["TableHeader"]),
        Paragraph("DIGITAL STAMP / SIGNATURE", styles["TableHeader"]),
        Paragraph("DATE", styles["TableHeader"]),
    ]

    sig_rows = [
        sig_header,
        [
            Paragraph("TIER 1: PREPARED BY", styles["TableCellBold"]),
            Paragraph("Deputy General Manager (Advanced Mfg)\nHVF Avadi", styles["TableCell"]),
            Paragraph("Er. R. Venkataraman\nIOFS-4418", styles["TableCell"]),
            Paragraph("[VER 2.0 APPROVED]\nDGM/AM/HVF-AVADI", styles["TableCellBold"]),
            Paragraph("30-Oct-2026", styles["TableCell"]),
        ],
        [
            Paragraph("TIER 2: REVIEWED BY", styles["TableCellBold"]),
            Paragraph("Joint General Manager (Quality & NDT)\nHVF Avadi", styles["TableCell"]),
            Paragraph("Dr. S. Muthukumar\nIOFS-3802", styles["TableCell"]),
            Paragraph("[VER 2.0 CONCURRED]\nJGM/QA/HVF", styles["TableCellBold"]),
            Paragraph("30-Oct-2026", styles["TableCell"]),
        ],
        [
            Paragraph("TIER 3: CONCURRENCE", styles["TableCellBold"]),
            Paragraph("Controller, Directorate General of Quality Assurance (DGQA Armoured Vehicles)", styles["TableCell"]),
            Paragraph("Brig. A. K. Rathore\nCQA(HV) Avadi", styles["TableCell"]),
            Paragraph("[VER 2.0 COUNTERSIGNED]\nCQA(HV)/MOD/GOI", styles["TableCellBold"]),
            Paragraph("30-Oct-2026", styles["TableCell"]),
        ],
        [
            Paragraph("TIER 4: APPROVED BY", styles["TableCellBold"]),
            Paragraph("Chief General Manager / Executive Director\nHeavy Vehicles Factory (AVNL)", styles["TableCell"]),
            Paragraph("Shri K. Parthasarathy\nCGM / HVF Avadi", styles["TableCell"]),
            Paragraph("[RELEASED FOR DEFENCE MFG]\nCGM-OFFICE/AVNL", styles["TableCellBold"]),
            Paragraph("30-Oct-2026", styles["TableCell"]),
        ],
    ]

    sig_table = Table(sig_rows, colWidths=[85, 145, 98, 112.2, 65])
    sig_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY_PRIMARY),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SURFACE_TINT]),
                ("GRID", (0, 0), (-1, -1), 0.6, SLATE_LIGHT),
                ("BOX", (0, 0), (-1, -1), 1.1, NAVY_PRIMARY),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(KeepTogether([sig_table]))
    story.append(Spacer(1, 10))

    story.append(
        Paragraph(
            "VERSION 2.0 ARCHIVAL NOTICE: Master encrypted electronic copy is archived in the HVF "
            "PLM Cloud Vault. All hard copies are strictly controlled and valid for 30 calendar days.",
            styles["Callout"],
        )
    )

    return story


# ============================================================================
# 7. MAIN PDF GENERATION ORCHESTRATOR
# ============================================================================
def generate_all_hvf_sops_v2(output_dir: str = ".") -> list:
    """
    Builds the 5 distinct Version 2 Defence Production SOP PDFs.
    """
    os.makedirs(output_dir, exist_ok=True)
    styles = build_styles()
    generated_files = []

    for idx, sop in enumerate(SOP_V2_DATASETS, start=1):
        output_path = os.path.join(output_dir, sop["filename"])

        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            leftMargin=45.0,
            rightMargin=45.0,
            topMargin=54.0,
            bottomMargin=54.0,
            title=f"{sop['doc_code']} - {sop['title']}",
            author="Heavy Vehicles Factory (HVF) | Armoured Vehicles Nigam Limited (AVNL)",
            subject="Defence Production Standard Operating Procedure (Version 2.0)",
        )

        story = []

        # Page 1: Cover, Metadata Control Grid Table & Executive Summary
        story.extend(build_page_1_cover_v2(sop, styles))

        # Pages 2 to 7: 6 Core Operational Technical Sections (1 section per page)
        assert len(sop["sections"]) == 6, "Each SOP dataset must contain exactly 6 sections."
        for sec in sop["sections"]:
            story.extend(build_core_section_page_v2(sop, sec, styles))

        # Page 8: Appendix & Multi-Tier Official Sign-Off Signature Matrix
        story.extend(build_page_8_appendix_and_signoff_v2(sop, styles))

        # Build PDF using the custom two-pass DPSUNumberedCanvasV2
        doc.build(story, canvasmaker=DPSUNumberedCanvasV2)
        generated_files.append(output_path)
        print(f"[{idx}/5] Successfully generated 8-page DPSU SOP Version 2 PDF: {output_path}")

    return generated_files


if __name__ == "__main__":
    generate_all_hvf_sops_v2()

