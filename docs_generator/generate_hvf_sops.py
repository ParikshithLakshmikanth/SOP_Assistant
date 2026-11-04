#!/usr/bin/env python3
"""
HVF / AVNL Enterprise Standard Operating Procedure (SOP) PDF Generator
======================================================================
Generates 5 distinct, strictly 8-page Standard Operating Procedure (SOP) PDF
documents for Heavy Vehicles Factory (HVF), A Unit of Armoured Vehicles Nigam
Limited (AVNL), Ministry of Defence, Avadi, Chennai.

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

# Initialize Faker with a deterministic seed for consistent, safe page budgeting
fake = Faker("en_IN")
Faker.seed(2026)


# ============================================================================
# 2. TWO-PASS CANVAS FOR RUNNING HEADERS & DYNAMIC "Page X of 8" FOOTERS
# ============================================================================
class DPSUNumberedCanvas(canvas.Canvas):
    """
    Two-pass ReportLab Canvas that captures all page states before committing
    to disk, enabling dynamic 'Page X of Y' numbering alongside HVF/AVNL
    military-industrial security headers and confidentiality footers.
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
            "HEAVY VEHICLES FACTORY (HVF) | AVNL AVADI",
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
            "PROPRIETARY DPSU TECHNICAL DOCUMENT — ARMOURED VEHICLES NIGAM LIMITED (MINISTRY OF DEFENCE, GOVT. OF INDIA)",
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
    """
    Constructs custom ParagraphStyle configurations with strict font size and
    leading rules to prevent text collisions and orphaned headings.
    """
    base_styles = getSampleStyleSheet()

    styles = {
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
            fontSize=20.0,
            leading=24.0,  # Strict 20pt / 24pt lead
            textColor=NAVY_PRIMARY,
            alignment=TA_LEFT,
            spaceBefore=2,
            spaceAfter=10,
            keepWithNext=True,
        ),
        "H1": ParagraphStyle(
            name="SOPH1",
            parent=base_styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=12.0,
            leading=16.0,  # Strict 12pt / 16pt lead
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
            leading=14.5,  # Strict 10pt / 14.5pt lead
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
    return styles


# ============================================================================
# 4. 5 DISTINCT DEFENCE PRODUCTION DATASETS
# ============================================================================
SOP_DATASETS = [
    {
        "filename": "HVF_SOP_1_Hull_Welding.pdf",
        "doc_code": "HVF/AVNL/SOP-MBT/HW-101",
        "rev": "Rev 4.2 (2026)",
        "platform": "MBT T-90S Bhishma / Arjun Mk-1A",
        "shop": "Heavy Hull Fabrication & Robotic Welding Shop (Shop-04)",
        "security_class": "RESTRICTED — DEFENCE PRODUCTION",
        "title": "Armoured Hull Fabrications & High-Tensile Steel Welds",
        "exec_summary": (
            "This Standard Operating Procedure (SOP) establishes the mandatory metallurgical, "
            "dimensional, and weld-integrity protocols for fabricating main battle tank (MBT) "
            "armoured hulls using Rolled Homogeneous Armour (RHA) and High-Hardness Armour (HHA) "
            "plates at Heavy Vehicles Factory (HVF), Avadi. All fabrication bays must enforce "
            "controlled pre-heating, austenitic/low-hydrogen filler wire selection, multi-pass "
            "submerged arc and pulse-GMAW sequencing, and 100% ultrasonic phased-array inspection "
            "to prevent hydrogen-induced cold cracking and ballistic seam failure."
        ),
        "scope_kpis": [
            ("Base Material Spec", "MIL-DTL-12560 / DMR-1700 Ultra-High-Strength RHA (380–440 BHN)"),
            ("Preheat & Interpass", "150°C min preheat; 220°C max interpass (IR pyrometer verified)"),
            ("NDT Acceptance", "100% Phased-Array Ultrasonic Testing (PAUT) & Magnetic Particle (MPI)"),
            ("Dimensional Datum", "Laser Tracker Hull Envelope Tolerance ≤ ±0.80 mm across 6.8 m length"),
        ],
        "sections": [
            {
                "num": "1.0",
                "title": "RHA Plate Receiving, Spectrographic Verification & Edge Beveling",
                "domain_lead": (
                    "Incoming Rolled Homogeneous Armour (RHA) plates from defence metallurgical mills "
                    "must undergo optical emission spectroscopy, Brinell hardness mapping, and laminar "
                    "ultrasonic scanning prior to CNC plasma/oxy-fuel bevel preparation."
                ),
                "metrics": [
                    ("1.1", "Chemical Equivalence (CEV)", "0.62 – 0.68 CEV max", "Optical Emission Spectrometer", "100% Heat Batches"),
                    ("1.2", "Surface Brinell Hardness", "400 – 440 HBW", "King Brinell Indenter (3000 kgf)", "5 Points / Plate"),
                    ("1.3", "Double-V Root Face & Angle", "2.0 mm ± 0.3 mm / 60° ± 1.5°", "Laser Bevel Profile Gauge", "Every 500 mm"),
                    ("1.4", "Heat-Affected Zone (HAZ) Dress", "≤ 0.4 mm carbide removal", "Carbide Rotary Grinding Check", "Continuous Visual"),
                    ("1.5", "Moisture & Oxide Clearance", "Zero hydrocarbon / scale residue", "White-Cloth Acetone Wipe Test", "Pre-Fitup Hold Point"),
                ],
            },
            {
                "num": "2.0",
                "title": "Hull Jig Fixture Datum Locking & Root Gap Dimensional Control",
                "domain_lead": (
                    "Glacis, belly pan, sponson, and bulkhead armour plates are loaded into the "
                    "60-tonne hydraulic turnover trunnion jig. Laser tracker targets establish the "
                    "master hull centreline before hydraulic clamping cylinders lock root gaps."
                ),
                "metrics": [
                    ("2.1", "Hull Master Centreline Datum", "± 0.35 mm to master CAD", "Leica Laser Tracker AT960", "Pre-Tack Sign-off"),
                    ("2.2", "Glacis-to-Belly Root Gap", "2.5 mm ± 0.4 mm", "Calibrated Go/No-Go Feeler", "Every 250 mm"),
                    ("2.3", "Bulkhead Squareness", "≤ 0.50 mm over 2,000 mm", "Optical Autocollimator", "4 Hull Stations"),
                    ("2.4", "Hydraulic Clamp Pressure", "165 bar ± 5 bar", "Digital Manifold Transducer", "Continuous Log"),
                    ("2.5", "Tack Weld Pitch & Length", "45 mm length @ 300 mm pitch", "AWS Certified Weld Gauge", "100% Tack Seams"),
                ],
            },
            {
                "num": "3.0",
                "title": "Induction Pre-Heating & Low-Hydrogen Consumable Conditioning",
                "domain_lead": (
                    "To eliminate diffusible hydrogen and martensitic cold cracking in thick armour "
                    "sections, high-frequency induction blankets heat the weld zone uniformly while "
                    "electrodes and flux are dispensed from calibrated holding ovens."
                ),
                "metrics": [
                    ("3.1", "Soak Preheat Temperature", "150°C – 175°C (75 mm soak zone)", "Dual-Laser IR Pyrometer", "Every 15 Minutes"),
                    ("3.2", "Interpass Temperature Ceiling", "≤ 220°C strict maximum", "Contact Thermocouple Probe", "Prior to Each Pass"),
                    ("3.3", "Diffusible Hydrogen Content", "≤ 4.0 ml / 100g deposit (H4)", "Gas Chromatography Cert", "Per Consumable Lot"),
                    ("3.4", "Electrode Baking & Quiver", "350°C bake (2 hr) / 110°C quiver", "Calibrated Oven Chart", "Shift Issue Log"),
                    ("3.5", "Shielding Gas Dew Point", "80% Ar / 20% CO2 ≤ -50°C dew pt", "Inline Hygrometer Sensor", "Continuous Flow"),
                ],
            },
            {
                "num": "4.0",
                "title": "Multi-Pass Pulse-GMAW & Robotic Submerged Arc Welding Execution",
                "domain_lead": (
                    "Root, fill, and capping passes follow a balanced back-step and symmetrical twin-side "
                    "welding sequence across port and starboard hull seams to neutralize angular distortion "
                    "and maintain optimal heat input between 1.2 and 1.8 kJ/mm."
                ),
                "metrics": [
                    ("4.1", "Arc Heat Input Envelope", "1.20 – 1.80 kJ/mm", "Robotic Weld Data Logger", "100% Real-Time"),
                    ("4.2", "Root Pass Current & Voltage", "210 – 235 A / 24.5 – 26.5 V", "Calibrated Hall-Effect Clamp", "Per Seam Segment"),
                    ("4.3", "Fill/Cap Travel Speed", "320 – 380 mm/min", "CNC Gantry Encoder", "Automated Trace"),
                    ("4.4", "Weld Reinforcement Crown", "0.5 mm – 2.2 mm flush profile", "Bridge Cam Weld Gauge", "Every 200 mm"),
                    ("4.5", "Port/Starboard Thermal Delta", "≤ 25°C differential", "Thermal Imaging Camera", "Continuous Sync"),
                ],
            },
            {
                "num": "5.0",
                "title": "Post-Weld Thermal Blanket Slow-Cooling & Stress-Relief Annealing",
                "domain_lead": (
                    "Immediately upon seam completion, ceramic-fibre thermal blankets are secured over "
                    "the hull joint to enforce controlled hydrogen effusion cooling at ≤ 35°C/hour, "
                    "followed by vibratory and localized thermal stress stabilization."
                ),
                "metrics": [
                    ("5.1", "Post-Weld Hydrogen Soak", "200°C held for 180 minutes", "Multi-Channel Strip Recorder", "100% Ballistic Seams"),
                    ("5.2", "Controlled Cooling Rate", "≤ 35°C / hour to 60°C", "Thermocouple Array Log", "Full Cooling Cycle"),
                    ("5.3", "Residual Stress Peak Reduction", "≥ 35% reduction post-stabilize", "X-Ray Diffraction (XRD)", "4 Reference Nodes"),
                    ("5.4", "Torsion Box Bore Twist", "≤ 0.40 mm across hull stations", "Laser Bore Alignment System", "Post-Cool Inspection"),
                    ("5.5", "Turret Ring Plinth Flatness", "≤ 0.60 mm prior to machining", "Precision Electronic Level", "360° Azimuth Scan"),
                ],
            },
            {
                "num": "6.0",
                "title": "100% Phased-Array Ultrasonic (PAUT) & Ballistic Seam Certification",
                "domain_lead": (
                    "After 48 hours of ambient stabilization to allow delayed hydrogen cracking detection, "
                    "DGQA and HVF Quality Assurance inspectors perform full-volume PAUT, TOFD, and "
                    "wet fluorescent magnetic particle inspection across all structural armour welds."
                ),
                "metrics": [
                    ("6.1", "Delayed NDT Hold Period", "≥ 48 Hours post-cooling to ambient", "QA Time-Stamp Ledger", "Mandatory Hold"),
                    ("6.2", "PAUT Volumetric Scan", "Zero cracks, zero lack of fusion", "64-Element Phased Array UT", "100% Seam Length"),
                    ("6.3", "Porosity Cluster Limit", "≤ 1.5 mm isolated; zero linear", "Time-of-Flight Diffraction", "100% Seam Length"),
                    ("6.4", "Toe Crack Surface Check", "Zero linear indications > 0.5 mm", "Wet Fluorescent MPI (AC Yoke)", "100% Weld Toes"),
                    ("6.5", "Final Hull Passport Stamp", "DGQA & HVF Chief Metallurgist", "Hard-Stamp & Digital Twin", "Before Paint Shop"),
                ],
            },
        ],
    },
    {
        "filename": "HVF_SOP_2_Turret_Integration.pdf",
        "doc_code": "HVF/AVNL/SOP-MBT/TI-204",
        "rev": "Rev 3.8 (2026)",
        "platform": "MBT T-90S Bhishma / Arjun Mk-1A",
        "shop": "Turret Integration & Fire Control Assembly Bay (Shop-09)",
        "security_class": "RESTRICTED — DEFENCE PRODUCTION",
        "title": "Turret Mount System Alignment & Ring Gear Fitting",
        "exec_summary": (
            "This Standard Operating Procedure (SOP) governs the precision machining verification, "
            "selective ball/roller raceway assembly, pinion backlash calibration, and electro-hydraulic "
            "traverse drive integration for Main Battle Tank (MBT) turret ring systems at HVF Avadi. "
            "Adherence to micron-level flatness and runout tolerances is critical to guarantee "
            "stabilized fire-on-the-move accuracy and zero binding under 48-tonne combat shock loads."
        ),
        "scope_kpis": [
            ("Plinth Flatness", "≤ 0.05 mm total indicator reading (TIR) across 2,240 mm pitch circle"),
            ("Gear Backlash", "0.18 mm – 0.26 mm between traverse drive pinion and internal ring gear"),
            ("Breakaway Torque", "≤ 420 Nm static breakaway torque across full 360° continuous rotation"),
            ("Electrical Slip-Ring", "Insulation resistance ≥ 500 MΩ at 500 VDC; contact noise ≤ 15 mΩ"),
        ],
        "sections": [
            {
                "num": "1.0",
                "title": "Hull Plinth & Turret Base Ring Co-Planarity Laser Metrology",
                "domain_lead": (
                    "Prior to lowering the turret race ring, the CNC vertical-bored hull plinth and "
                    "mating turret base flange are mapped across 36 azimuth stations using a laser "
                    "interferometer and electronic spirit levels to verify co-planarity and concentricity."
                ),
                "metrics": [
                    ("1.1", "Hull Plinth Surface Flatness", "≤ 0.05 mm TIR over 360°", "Leica Laser Tracker / Level", "Every 10° Azimuth"),
                    ("1.2", "Spigot Bore Concentricity", "≤ 0.04 mm radial runout", "Precision Dial Bore Indicator", "12 Radial Points"),
                    ("1.3", "Mating Surface Roughness", "Ra ≤ 1.6 µm machined finish", "Portable Profilometer", "8 Quadrant Spots"),
                    ("1.4", "Tapped Mounting Hole Pitch", "± 0.08 mm true position", "CMM Optical Verification", "All 72 Bolt Holes"),
                    ("1.5", "Selective Shim Pack Thickness", "0.02 mm increment stainless shims", "Digital Micrometer (0.001 mm)", "As Mapped per Sector"),
                ],
            },
            {
                "num": "2.0",
                "title": "Four-Point Contact Ball / Cross-Roller Bearing Raceway Assembly",
                "domain_lead": (
                    "Induction-hardened raceways and matched-grade chrome-molybdenum bearing elements "
                    "with brass spacer cages are installed via the loading plug port and lubricated "
                    "with MIL-PRF-10924 extreme-pressure synthetic aviation/armour grease."
                ),
                "metrics": [
                    ("2.1", "Bearing Ball Diameter Grading", "± 0.002 mm within matched lot", "Laser Micrometer Bench", "100% Bearing Lot"),
                    ("2.2", "Raceway Case Hardness", "58 – 62 HRC (depth ≥ 4.5 mm)", "Ultrasonic Contact Impedance", "12 Azimuth Stations"),
                    ("2.3", "Axial Play Preload Clearance", "0.03 – 0.07 mm axial lift", "Magnetic Base Dial Gauge", "4 Quadrant Lifts"),
                    ("2.4", "Loading Plug Retention Lock", "Flush ± 0.01 mm; tapered pin lock", "Depth Micrometer & MPI", "100% Plug Assembly"),
                    ("2.5", "Initial Grease Charge Mass", "4.8 kg ± 0.15 kg MIL-PRF-10924", "Gravimetric Dispense Meter", "Full Perimeter Purge"),
                ],
            },
            {
                "num": "3.0",
                "title": "Internal Ring Gear Mounting, Eccentricity & Pinion Backlash Tuning",
                "domain_lead": (
                    "The internal spur gear ring is aligned to the turret traverse gearbox output pinion. "
                    "Eccentric mounting sleeve adjustments establish uniform tooth flank contact and "
                    "eliminate tight spots across the entire 360-degree traverse envelope."
                ),
                "metrics": [
                    ("3.1", "Gear Pitch Circle Runout", "≤ 0.06 mm radial eccentricity", "Roll Tester & Master Pin", "Every 15° Tooth Sector"),
                    ("3.2", "Pinion-to-Ring Gear Backlash", "0.18 mm – 0.26 mm", "Lead-Wire & Dial Indicator", "12 Azimuth Positions"),
                    ("3.3", "Tooth Flank Prussian Blue", "≥ 80% central tooth contact area", "Prussian Blue Transfer Mesh", "4 Quadrant Sectors"),
                    ("3.4", "Ring Bolt Torque Sequence", "340 Nm ± 10 Nm (3-stage star)", "DC Transducer Torque Wrench", "All 72 Class 12.9 Bolts"),
                    ("3.5", "Retaining Wire / Lock Tab", "0.8 mm Inconel safety wire lock", "Visual & Pull-Tension Check", "100% Bolt Pairs"),
                ],
            },
            {
                "num": "4.0",
                "title": "Overhead Crane Turret Mating & Ballistic Retention Ring Torquing",
                "domain_lead": (
                    "Using the synchronized 30-tonne overhead bridge crane and four-point load-cell "
                    "spreader beam, the combat turret is lowered within 0.5 degrees of level onto the "
                    "hull bearing ring and secured against ballistic overturn forces."
                ),
                "metrics": [
                    ("4.1", "Spreader Beam Level Tilt", "≤ 0.25° pitch/roll during drop", "Biaxial Digital Inclinometer", "Continuous Crane Drop"),
                    ("4.2", "Turret Base Seating Gap", "Zero feeler entry (0.03 mm blade)", "Precision Feeler Gauge", "360° Perimeter Check"),
                    ("4.3", "Outer Ring Clamp Torque", "410 Nm ± 12 Nm wet torque", "Hydraulic/DC Torque System", "All 64 Outer Studs"),
                    ("4.4", "Ballistic Labyrinth Seal Gap", "1.5 mm ± 0.3 mm uniform clearance", "Non-Metallic Gap Gauge", "Every 30° Azimuth"),
                    ("4.5", "NBC Overpressure Seal Leak", "≤ 1.5 L/min drop at 3.5 kPa", "Differential Pressure Decay", "Post-Mate NBC Test"),
                ],
            },
            {
                "num": "5.0",
                "title": "Rotary Electrical Slip-Ring & Electro-Hydraulic Traverse Drive",
                "domain_lead": (
                    "The central multi-channel rotary electrical/fibre-optic slip-ring unit and the "
                    "stabilized electro-hydraulic/brushless-DC traverse actuator are coupled and verified "
                    "for signal continuity, high-current power transfer, and deadband response."
                ),
                "metrics": [
                    ("5.1", "Slip-Ring Concentricity", "≤ 0.10 mm to rotation axis", "Dial Indicator on Center Post", "Pre-Coupling Check"),
                    ("5.2", "Dynamic Contact Resistance", "≤ 15 mΩ variation at 30 deg/s", "4-Wire Micro-Ohmmeter", "All Power/Signal Rings"),
                    ("5.3", "Insulation Resistance", "≥ 500 MΩ at 500 VDC megger", "Digital Insulation Tester", "Channel-to-Chassis"),
                    ("5.4", "Max Slew Rate Velocity", "≥ 40.0 deg/sec stabilized slew", "Gyro Rate Table Telemetry", "CW and CCW Full Slew"),
                    ("5.5", "Minimum Tracking Speed", "≤ 0.05 mrad/sec smooth creep", "Autocollimator Target Track", "Fire-Control Closed Loop"),
                ],
            },
            {
                "num": "6.0",
                "title": "360-Degree Dynamic Rotational Torque & Stabilization Acceptance",
                "domain_lead": (
                    "Final turret integration acceptance requires continuous 360-degree rotational "
                    "torque profiling under simulated hull cant angles (up to 15 degrees) and main gun "
                    "2-axis stabilization lock verification on the HVF dynamic tilt test rig."
                ),
                "metrics": [
                    ("6.1", "Breakaway Torque (Flat Hull)", "≤ 420 Nm CW and CCW", "Inline Rotary Torque Sensor", "8 Azimuth Headings"),
                    ("6.2", "Running Torque Ripple (15° Tilt)", "≤ ± 8% torque fluctuation", " Servo Current Telemetry", "3 Continuous Revolutions"),
                    ("6.3", "Emergency Manual Hand-Crank", "≤ 35 N handle force", "Digital Push-Pull Dynamometer", "Full 360° Manual Sweep"),
                    ("6.4", "Azimuth Resolver Accuracy", "≤ 0.15 mrad angular error", "Theodolite Reference Prism", "Every 30° Index"),
                    ("6.5", "Turret Travel Lock Engagement", "Zero play; micro-switch interlock", "Mechanical & FCS Interlock", "5 Consecutive Cycles"),
                ],
            },
        ],
    },
    {
        "filename": "HVF_SOP_3_Engine_Alignment.pdf",
        "doc_code": "HVF/AVNL/SOP-MBT/EA-309",
        "rev": "Rev 5.1 (2026)",
        "platform": "MBT T-90S (V-92S2 1000 HP) / CVRDE 1500 HP Powerpack",
        "shop": "Powerpack Integration & Dynamometer Test Cell (Shop-12)",
        "security_class": "RESTRICTED — DEFENCE PRODUCTION",
        "title": "High-Power Multi-Fuel V12 Engine Dropping & Alignment",
        "exec_summary": (
            "This Standard Operating Procedure (SOP) defines the engineering sequence for "
            "lowering, trunnion-mounting, laser-aligning, and fluid/electrical coupling of the "
            "1,000–1,500 HP turbocharged V12 multi-fuel diesel engine and planetary transmission "
            "powerpack into the MBT rear hull compartment at HVF Avadi. Strict coaxial alignment "
            "between the engine output damper and gearbox input shaft prevents spline fretting "
            "and torsional vibration failure under severe cross-country combat loads."
        ),
        "scope_kpis": [
            ("Shaft Coaxiality", "Radial offset ≤ 0.05 mm; angular misalignment ≤ 0.04 mm/100 mm"),
            ("Mount Load Balance", "Trunnion & resilient pad load distribution within ± 3.5% design mass"),
            ("Cooling Loop Seal", "Zero pressure decay at 2.2 bar pneumatic/hydrostatic test for 30 min"),
            ("Hot-Cell Test Run", "Full rated power (736–1,103 kW) @ 2,000 RPM; oil pressure 4.5–6.0 bar"),
        ],
        "sections": [
            {
                "num": "1.0",
                "title": "Engine Bay Hull Pedestal Inspection & Resilient Mount Pre-Calibration",
                "domain_lead": (
                    "Before powerpack lowering, the rear hull engine bay floor, machined side trunnion "
                    "brackets, and final-drive bulkhead bores are cleaned, dimensionally surveyed, and "
                    "fitted with pre-measured shim packs for the four main mounting pads."
                ),
                "metrics": [
                    ("1.1", "Mounting Pedestal Co-Planarity", "≤ 0.08 mm across 4 hull pads", "Laser Level & Optical Prism", "Pre-Drop Survey"),
                    ("1.2", "Final Drive Bore Coaxiality", "≤ 0.06 mm port-to-starboard", "Laser Bore Alignment Kit", "100% Hull Bays"),
                    ("1.3", "Elastomeric/Solid Pad Stiffness", "Within ± 4% rated kN/mm curve", "Hydraulic Compression Bench", "Matched Set of 4"),
                    ("1.4", "Bilge Scavenge Valve Operation", "≥ 65 L/min evacuation flow", "Flowmeter Functional Check", "Pre-Drop Verification"),
                    ("1.5", "Fire-Wire Thermal Loop Continuity", "24.0 Ω ± 0.5 Ω loop resistance", "AFDSS Test Harness Box", "Dual Zone Loops"),
                ],
            },
            {
                "num": "2.0",
                "title": "V12 Powerpack Hoisting, Trunnion Lowering & Shim Pack Selection",
                "domain_lead": (
                    "The dressed V12 multi-fuel engine and hydraulic-mechanical transmission sub-frame "
                    "are hoisted using the calibrated 5-tonne four-point turnbuckle rig, lowered "
                    "through the deck opening, and seated onto the hull mounting trunnions."
                ),
                "metrics": [
                    ("2.1", "Hoist Sling Load Symmetry", "± 2.5% across 4 crane load cells", "Wireless Shackle Load Cells", "Continuous Lift"),
                    ("2.2", "Deck Clearance Envelope", "≥ 18.0 mm minimum wall clearance", "Go/No-Go Clearance Wand", "4 Hull Corners"),
                    ("2.3", "Pad Seating Unclamped Gap", "≤ 0.04 mm after shim insertion", "Calibrated Stainless Feeler", "All 4 Mount Pads"),
                    ("2.4", "Primary Mount Bolt Torque", "520 Nm ± 15 Nm + 60° angle turn", "Electronic Torque-Angle Tool", "16 Main Anchor Bolts"),
                    ("2.5", "Chassis Ground Bonding Strap", "≤ 1.2 mΩ hull-to-crankcase", "Kelvin Bridge Micro-Ohmmeter", "Dual Braided Straps"),
                ],
            },
            {
                "num": "3.0",
                "title": "Dual-Laser Crankshaft-to-Transmission Input Shaft Coaxial Alignment",
                "domain_lead": (
                    "A dual-laser shaft alignment system is clamped to the V12 flywheel torsional "
                    "damper flange and the transmission input hub. Horizontal and vertical shimming "
                    "compensates for cold-to-hot thermal growth (+0.12 mm vertical rise at 95°C)."
                ),
                "metrics": [
                    ("3.1", "Parallel Radial Offset (Cold)", "≤ 0.05 mm TIR (target -0.12 mm V)", "Dual-Laser Shaft Aligner", "9-12-3-6 O'Clock Sweep"),
                    ("3.2", "Angular Face Misalignment", "≤ 0.04 mm per 100 mm diameter", "Dual-Laser Shaft Aligner", "Continuous 360° Sweep"),
                    ("3.3", "Gear Coupling Axial Float", "1.50 mm – 2.20 mm axial end-play", "Magnetic Base Dial Gauge", "Post-Coupling Check"),
                    ("3.4", "Final Drive Cardan Spline Runout", "≤ 0.07 mm radial runout", "Dial Indicator on Yoke Hub", "Port & Starboard Drives"),
                    ("3.5", "Torsional Damper Fastener Torque", "195 Nm ± 6 Nm (Loctite 262)", "Calibrated Click/Digital Wrench", "All 12 Coupling Bolts"),
                ],
            },
            {
                "num": "4.0",
                "title": "High-Pressure Fuel, Dry-Sump Lubrication & Cooling Loop Coupling",
                "domain_lead": (
                    "High-pressure braided PTFE fuel lines, dry-sump scavenging oil pipes, and ethylene-glycol "
                    "radiator manifolds are connected via quick-disconnect self-sealing couplings and "
                    "subjected to hydrostatic and pneumatic pressure-hold testing."
                ),
                "metrics": [
                    ("4.1", "Fuel Supply & Return Proof Test", "6.0 bar hydrostatic for 20 min", "Digital Pressure Recorder", "Zero Weepage Allowed"),
                    ("4.2", "Dry-Sump Oil Circuit Flush", "NAS 1638 Class 6 cleanliness", "Laser Particle Counter", "15-Min Bypass Flush"),
                    ("4.3", "Coolant System Pressure Hold", "2.2 bar pneumatic for 30 min", "Differential Decay Gauge", "≤ 0.02 bar Drop"),
                    ("4.4", "High-Pressure Air Start Bottle", "150 bar charge; zero leak soap test", "Calibrated Bourdon/Digital", "Dual Air Cylinders"),
                    ("4.5", "Hose Clamp Torque & Fire Sleeve", "8.5 Nm ± 0.5 Nm on twin clamps", "Calibrated Torque Screwdriver", "100% Fluid Joints"),
                ],
            },
            {
                "num": "5.0",
                "title": "Cyclonic Air Filtration, Turbocharger Ducting & Exhaust Sealing",
                "domain_lead": (
                    "Two-stage cyclonic dust-ejection air cleaner cassettes, compressor intake V-band "
                    "bellows, and Inconel exhaust ejector manifolds are sealed and vacuum-tested to "
                    "prevent desert silica ingestion and deep-fording water ingress."
                ),
                "metrics": [
                    ("5.1", "Intake Tract Vacuum Decay", "Hold -15 kPa for 120 seconds", "Manometer Vacuum Rig", "Compressor Inlet Seal"),
                    ("5.2", "Cyclone Dust Scavenge Ejector", "≥ 98.5% separation efficiency", "Differential Pressure Sensor", "Exhaust Ejector Port"),
                    ("5.3", "Exhaust Manifold V-Band Torque", "28 Nm ± 2 Nm with anti-seize", "Calibrated Torque Wrench", "All 8 V-Band Clamps"),
                    ("5.4", "Deep-Fording Exhaust Valve Seal", "Zero bubble leak at 5.0 m head", "Hydrostatic Back-Pressure Rig", "Snorkel Mode Interlock"),
                    ("5.5", "Thermal Insulation Blanket Temp", "Surface ≤ 140°C at full load", "IR Thermal Imaging Camera", "Exhaust Shroud Survey"),
                ],
            },
            {
                "num": "6.0",
                "title": "Cold Motoring, Hot-Run Hull Telemetry & Vibration Signature Sign-Off",
                "domain_lead": (
                    "With pre-lube oil pressure established via the electric priming pump, the V12 engine "
                    "is motored, started, and stepped through idle, mid-range, and full-load stall tests "
                    "while triaxial accelerometers record hull vibration velocity."
                ),
                "metrics": [
                    ("6.1", "Pre-Start Oil Priming Pressure", "≥ 1.8 bar within 12 seconds", "Cockpit & CAN-Bus Transducer", "Mandatory Start Interlock"),
                    ("6.2", "Rated Speed & Oil Pressure", "2,000 RPM / 4.5 – 6.0 bar @ 90°C", "Engine Control Telemetry", "30-Min Sustained Run"),
                    ("6.3", "Turbo Boost & Exhaust Gas Temp", "2.4 bar abs boost / EGT ≤ 680°C", "K-Type Thermocouple Array", "Full Stall Load Test"),
                    ("6.4", "Triaxial Vibration Velocity", "≤ 4.5 mm/s RMS (ISO 10816-6)", "FFT Vibration Analyzer", "All 4 Engine Mounts"),
                    ("6.5", "Hot-State Laser Re-Alignment", "≤ 0.04 mm radial offset at 95°C", "Dual-Laser Hot Verification", "Immediate Post-Shutdown"),
                ],
            },
        ],
    },
    {
        "filename": "HVF_SOP_4_Torsion_Suspension.pdf",
        "doc_code": "HVF/AVNL/SOP-MBT/TS-412",
        "rev": "Rev 4.0 (2026)",
        "platform": "MBT T-90S Bhishma / Tracked Running Gear Platform",
        "shop": "Undercarriage, Suspension & Track Assembly Line (Shop-06)",
        "security_class": "RESTRICTED — DEFENCE PRODUCTION",
        "title": "Torsion Bar Installation & Track Tensioning Systems",
        "exec_summary": (
            "This Standard Operating Procedure (SOP) specifies the assembly, directional spline "
            "indexing, hydraulic road-wheel arm pre-loading, rotary/linear shock absorber coupling, "
            "and dynamic track tension calibration for heavy tracked armoured fighting vehicles at "
            "HVF Avadi. Strict directional separation of Left (L) and Right (R) shot-peened torsion "
            "bars is mandatory to prevent catastrophic shear fracture during high-speed cross-country mobility."
        ),
        "scope_kpis": [
            ("Directional Indexing", "100% Left/Right preset torsion bar verification prior to spline insertion"),
            ("Ground Clearance", "450 mm ± 6 mm static hull belly clearance across all 12 road-wheel stations"),
            ("Wheel Alignment", "≤ 1.2 mm lateral toe/camber deviation along road-wheel, idler, and sprocket plane"),
            ("Track Catenary Tension", "Upper track sag 32 mm – 38 mm; worm-eccentric tensioner lock verified"),
        ],
        "sections": [
            {
                "num": "1.0",
                "title": "Torsion Bar Metallurgical Stamp Audit, Shot-Peening & Spline Prep",
                "domain_lead": (
                    "High-yield 45KhNMFA vacuum-remelted steel torsion bars undergo magnetic particle "
                    "inspection, anti-corrosion protective coating audit, and strict Left ('L') versus "
                    "Right ('R') pre-twist directional verification before greased insertion."
                ),
                "metrics": [
                    ("1.1", "Directional Stamp Audit (L vs R)", "100% match to Port/Starboard side", "Dual Inspector Visual + Barcode", "All 12 Torsion Stations"),
                    ("1.2", "Core & Surface Hardness", "47 – 52 HRC (shot-peened skin)", "Ultrasonic Hardness Tester", "Lot Sampling & Cert"),
                    ("1.3", "Involute Spline Tooth Profile", "Zero burrs; Go/No-Go ring pass", "Master Spline Ring Gauge", "Both Anchor & Lever Ends"),
                    ("1.4", "Protective Shaft Coating", "≥ 120 µm epoxy-polyamide intact", "Eddy-Current Coating Gauge", "Full Bar Shaft Length"),
                    ("1.5", "Spline Anti-Fretting Paste", "MoS2 paste (MIL-PRF-907) coat", "100% Tooth Flank Coverage", "Pre-Insertion Check"),
                ],
            },
            {
                "num": "2.0",
                "title": "Balancer Arm Needle-Bearing Housing & Labyrinth Seal Assembly",
                "domain_lead": (
                    "Hull side suspension housings are fitted with double-lip fluorocarbon labyrinth "
                    "mud seals, precision needle/roller sleeve bearings, and forged road-wheel balancer "
                    "arms, then pressure-purged with water-resistant lithium-complex grease."
                ),
                "metrics": [
                    ("2.1", "Housing Bore Cylindrical Tolerance", "H7 tolerance (± 0.021 mm)", "Three-Point Internal Micrometer", "All 12 Hull Housings"),
                    ("2.2", "Balancer Arm Radial Play", "0.04 mm – 0.09 mm mounted play", "Magnetic Dial Indicator", "Each Installed Arm"),
                    ("2.3", "Labyrinth Seal Hydrostatic Hold", "Hold 1.5 bar grease pressure", "Pneumatic Grease Gun Gauge", "Until Clean Purge"),
                    ("2.4", "Axial Retaining Ring Seating", "Full groove bottoming + lock bolt", "Feeler Gauge & 180 Nm Torque", "All 12 Balancer Hubs"),
                    ("2.5", "Bump-Stop Volute Spring Height", "215 mm ± 2.0 mm free height", "Vernier Height Caliper", "Stations 1, 2, 6 (L & R)"),
                ],
            },
            {
                "num": "3.0",
                "title": "Spline Vernier Indexing & Hydraulic Jack Pre-Load Angle Setting",
                "domain_lead": (
                    "Using the hydraulic balancer-arm lifting fixture, each road-wheel arm is positioned "
                    "at its design free-drop angle while the torsion bar is engaged into the differential "
                    "vernier splines to equalize static wheel load across all six axle stations."
                ),
                "metrics": [
                    ("3.1", "Free-Drop Balancer Arm Angle", "34.5° ± 0.3° to hull datum plane", "Digital Precision Inclinometer", "All 12 Wheel Stations"),
                    ("3.2", "Spline Vernier Engagement Depth", "68.0 mm ± 0.5 mm full engagement", "Depth Micrometer to End-Cap", "Anchor & Lever Ends"),
                    ("3.3", "Anchor Plug Retention Torque", "450 Nm ± 15 Nm + lock plate", "Calibrated Torque Multiplier", "All 12 Anchor Caps"),
                    ("3.4", "Static Hull Belly Clearance", "450 mm ± 6 mm under full combat wt", "Laser Height Distance Meter", "Fore, Mid & Aft Hull"),
                    ("3.5", "Port-to-Starboard Roll Level", "≤ 1.5 mm height delta across hull", "Optical Water/Laser Level", "Settled Suspension"),
                ],
            },
            {
                "num": "4.0",
                "title": "Hydraulic Rotary Damper Calibration & Road-Wheel Hub Torquing",
                "domain_lead": (
                    "Hydraulic rotary shock absorbers on stations 1, 2, and 6 are bench-verified for "
                    "compression/rebound damping force, coupled via splined link arms, and followed by "
                    "dual rubber-tyred aluminum road-wheel hub assembly."
                ),
                "metrics": [
                    ("4.1", "Rebound Damping Force @ 0.5 m/s", "42.0 kN ± 3.0 kN on servo bench", "Hydraulic Damper Dyno Cert", "Stations 1, 2, 6 (L & R)"),
                    ("4.2", "Damper Spline Link Clamp Torque", "280 Nm ± 10 Nm", "Calibrated Torque Wrench", "All 6 Damper Levers"),
                    ("4.3", "Road-Wheel Taper Roller End-Play", "0.05 mm – 0.12 mm axial play", "Dial Indicator on Hub Flange", "All 12 Wheel Hubs"),
                    ("4.4", "Wheel Stud Nut Tightening", "480 Nm ± 15 Nm (crisscross seq)", "Pneumatic/DC Nutrunner", "10 Studs × 12 Stations"),
                    ("4.5", "Hub Sight-Glass Oil Fill", "MIL-PRF-2105E SAE 80W-90 to line", "Visual Level & Plug Torque", "100% Road & Return Rollers"),
                ],
            },
            {
                "num": "5.0",
                "title": "Drive Sprocket, Idler Crank & Road-Wheel Laser Plane Alignment",
                "domain_lead": (
                    "A continuous laser reference plane is projected from the rear final-drive sprocket "
                    "teeth across the six dual road-wheels and three track return rollers to the front "
                    "eccentric idler wheel to prevent track-horn climbing and throwing."
                ),
                "metrics": [
                    ("5.1", "Sprocket-to-Idler Co-Planarity", "≤ 1.2 mm lateral offset over 6.5 m", "Long-Range Laser Line Target", "Port & Starboard Sides"),
                    ("5.2", "Road-Wheel Guide-Horn Gap", "± 0.8 mm centerline alignment", "Optical Track Plane Gauge", "All 6 Stations / Side"),
                    ("5.3", "Sprocket Ring Bolt Torque", "390 Nm ± 12 Nm + tab washer bend", "Calibrated Torque Wrench", "All 22 Bolts / Sprocket"),
                    ("5.4", "Return Roller Coaxial Alignment", "≤ 1.0 mm to track center plane", "Laser Target Jig", "6 Return Rollers"),
                    ("5.5", "Idler Spindle Eccentric Play", "≤ 0.08 mm radial bearing clearance", "Dial Indicator Check", "Port & Starboard Idlers"),
                ],
            },
            {
                "num": "6.0",
                "title": "Double-Pin Track Link Wrapping, Tensioning & 5 km Shakedown Audit",
                "domain_lead": (
                    "Rubber-bushed double-pin steel track bands are winched over the sprocket and idler, "
                    "connected with end-connectors and central wedges, tensioned via the worm-gear "
                    "eccentric mechanism, and validated on the HVF 5 km figure-eight test track."
                ),
                "metrics": [
                    ("6.1", "Track Pin Wedge & End-Connector", "360 Nm ± 10 Nm (re-torque @ 5 km)", "Calibrated Torque Wrench", "100% Track Links (160/side)"),
                    ("6.2", "Static Upper Track Catenary Sag", "32 mm – 38 mm above 2nd roller", "Straightedge & Depth Rule", "Port & Starboard Tracks"),
                    ("6.3", "Idler Worm Lock Pin Engagement", "Full tooth mesh + safety cotter", "Visual & Mechanical Pry Test", "Both Idler Tensioners"),
                    ("6.4", "Post-Shakedown Hub Temperature", "≤ 75°C after 5 km @ 40 km/h", "IR Thermal Camera Scan", "All Hubs & Dampers"),
                    ("6.5", "Post-Run Track Sag Drift", "≤ 3.0 mm sag change post-5 km", "Straightedge Re-Verification", "Final QA Sign-Off"),
                ],
            },
        ],
    },
    {
        "filename": "HVF_SOP_5_Gun_Calibration.pdf",
        "doc_code": "HVF/AVNL/SOP-MBT/GC-518",
        "rev": "Rev 4.6 (2026)",
        "platform": "125mm Smoothbore 2A46M-5 / 120mm Ordnance System",
        "shop": "Main Armament Integration & Optical Boresight Bay (Shop-15)",
        "security_class": "RESTRICTED — DEFENCE PRODUCTION",
        "title": "Main Gun Barrel Fitment & Muzzle Reference Calibration",
        "exec_summary": (
            "This Standard Operating Procedure (SOP) establishes the precision ordnance integration "
            "and fire-control harmonization protocol for mounting the autofrettaged 125mm/120mm tank "
            "gun barrel into the cradle, charging the hydro-pneumatic recoil and recuperator cylinders, "
            "aligning the thermal shroud, and zeroing the Muzzle Reference System (MRS) mirror to "
            "the gunner's primary thermal/day sight within 0.05 milliradians at HVF Avadi."
        ),
        "scope_kpis": [
            ("Bore Straightness", "Electronic bore-straightness profile ≤ 0.15 mm/m; chrome bore intact"),
            ("Recoil & Recuperator", "Nitrogen pre-charge 62.0 ± 0.5 bar; artificial recoil stroke 290–310 mm"),
            ("Boresight Harmonization", "Gunner Day/Thermal Sight & Laser Rangefinder zeroed within ≤ 0.05 mrad"),
            ("MRS Mirror Zeroing", "Muzzle Reference System compensation error ≤ 0.03 mrad across ±1.5 mrad bend"),
        ],
        "sections": [
            {
                "num": "1.0",
                "title": "Autofrettaged Barrel Bore Metrology, Rifling/Chrome Audit & Breech Fit",
                "domain_lead": (
                    "Prior to turret insertion, the electro-slag remelted (ESR) autofrettaged gun tube "
                    "is inspected along its full bore length using a laser bore-straightness gauge, "
                    "digital air-gauge micrometer, and high-definition optical videoscope."
                ),
                "metrics": [
                    ("1.1", "Internal Bore Diameter Wear/Spec", "125.00 mm (+0.06 / -0.00 mm)", "Digital Tri-Lobe Air Gauge", "Every 100 mm Bore Station"),
                    ("1.2", "Chromium Plating Thickness", "≥ 180 µm; zero flaking or pitting", "Videoscope & Eddy-Current Probe", "100% Chamber & Bore"),
                    ("1.3", "Tube Centerline Straightness", "≤ 0.15 mm/m cumulative bow", "Laser Bore Straightness System", "Full 6,000 mm Tube"),
                    ("1.4", "Breech Ring Buttress Thread Contact", "≥ 85% load-flank Prussian blue", "Optical Thread Profile Check", "All Interrupted Sectors"),
                    ("1.5", "Semi-Automatic Wedge Drop Time", "≤ 0.18 seconds full closure", "High-Speed Opto-Timer", "10 Dry-Cycling Trials"),
                ],
            },
            {
                "num": "2.0",
                "title": "Cradle Slide Bush Insertion, Trunnion Balancing & Interrupted Thread Lock",
                "domain_lead": (
                    "The gun tube is guided through the turret mantlet bronze/PTFE cradle bushes, "
                    "rotated 45 degrees into the breech block interrupted buttress threads, locked via "
                    "the tapered key, and balanced about the elevation trunnion axis."
                ),
                "metrics": [
                    ("2.1", "Cradle Bronze Bush Clearance", "0.06 mm – 0.11 mm diametral", "Telescopic Bore & OD Gauge", "Fore & Aft Cradle Bushes"),
                    ("2.2", "Breech Coupling Lock-Key Seating", "Flush ± 0.10 mm; 290 Nm lock bolt", "Depth Gauge & Torque Wrench", "Primary Breech Key"),
                    ("2.3", "Elevation Trunnion Coaxiality", "≤ 0.03 mm port-to-starboard", "Optical Alignment Telescope", "Mantlet Trunnion Bores"),
                    ("2.4", "Static Trunnion Unbalance Torque", "≤ 18 Nm muzzle/breech imbalance", "Elevation Torque Transducer", "-5° to +15° Elevation"),
                    ("2.5", "Fume Extractor (Bore Evacuator)", "Hold 3.5 bar pneumatic for 15 min", "Digital Pressure Manometer", "Ball Check Nozzles & Seals"),
                ],
            },
            {
                "num": "3.0",
                "title": "Hydro-Pneumatic Recuperator & Hydraulic Recoil Buffer Charging",
                "domain_lead": (
                    "The hydraulic recoil buffer and hydro-pneumatic recuperator cylinders are filled "
                    "with filtered STEOL-M / MIL-H-5606 recoil fluid, bled of entrained air, charged "
                    "with dry nitrogen, and tested using the hydraulic pull-back artificial recoil rig."
                ),
                "metrics": [
                    ("3.1", "Recoil Buffer Fluid Volume", "7.40 L ± 0.05 L de-aerated fluid", "Volumetric Closed-Loop Rig", "Zero Air Foam Allowed"),
                    ("3.2", "Recuperator Nitrogen Pressure", "62.0 bar ± 0.5 bar (at 20°C)", "Calibrated Master Digital Gauge", "Temperature Compensated"),
                    ("3.3", "Artificial Recoil Pull-Back Stroke", "295 mm – 308 mm full stroke", "Hydraulic Pull-Back Cylinder", "3 Consecutive Pull Cycles"),
                    ("3.4", "Run-Out Return to Battery Time", "0.85 – 1.15 seconds smooth return", "Linear Displacement Transducer", "Zero Residual Shortfall"),
                    ("3.5", "Packing Gland Dynamic Weepage", "≤ 1 drop per 5 artificial strokes", "Visual Blotter Inspection", "Recoil & Recuperator Rods"),
                ],
            },
            {
                "num": "4.0",
                "title": "Multi-Section Thermal Shroud Fitment & Bore-Evacuator Concentricity",
                "domain_lead": (
                    "To minimize solar and cross-wind thermal bending of the gun tube, multi-section "
                    "double-wall aluminum/composite thermal sleeves are installed with calibrated "
                    "radial air-gap spacers and sealed against moisture ingress."
                ),
                "metrics": [
                    ("4.1", "Thermal Sleeve Radial Air Gap", "4.5 mm ± 0.4 mm uniform annulus", "Ultrasonic Gap / Feeler Probe", "5 Sleeve Sections"),
                    ("4.2", "Clamping Band Fastener Torque", "14.0 Nm ± 1.0 Nm (spring-loaded)", "Calibrated Torque Screwdriver", "All 18 Retention Bands"),
                    ("4.3", "Differential Solar Bend Reduction", "≤ 0.08 mrad tip deflection @ Δ20°C", "IR Lamp Thermal Chamber Test", "Muzzle Autocollimator"),
                    ("4.4", "Drain & Vent Port Orientation", "6 O'Clock bottom center ± 2°", "Inclinometer Protractor", "All 5 Shroud Segments"),
                    ("4.5", "Muzzle Brake / Clamp Ring Runout", "≤ 0.05 mm to bore axis", "Muzzle Mandrel Dial Gauge", "Muzzle End Assembly"),
                ],
            },
            {
                "num": "5.0",
                "title": "Muzzle Reference System (MRS) Mirror Zeroing & Autocollimator Alignment",
                "domain_lead": (
                    "The Muzzle Reference System (MRS) permittivity mirror assembly is mounted at the "
                    "gun muzzle tip and optically aligned to the turret-roof transceiver unit using a "
                    "muzzle boresight telescope and master calibration reticle at 1,000 meters equivalent."
                ),
                "metrics": [
                    ("5.1", "MRS Mirror Mount Seat Flatness", "≤ 0.015 mm across titanium flange", "Optical Flat & Monochromatic", "Muzzle Tip Dovetail"),
                    ("5.2", "Muzzle Telescope Optical Zero", "≤ 0.02 mrad rotation error (180°)", "Dioptometer & Collimator", "4-Quadrant Roll Check"),
                    ("5.3", "MRS Transceiver Return Signal", "≥ 85% photodiode intensity peak", "FCS Diagnostic Telemetry", "Azimuth & Elevation Channels"),
                    ("5.4", "Induced Bend Compensation Accuracy", "≤ 0.03 mrad residual error", "Calibrated Wedge Prism Test", "± 1.5 mrad Simulated Bend"),
                    ("5.5", "MRS Mirror Fastener Lock Torque", "32.0 Nm ± 1.5 Nm + wire lock", "Calibrated Torque Wrench", "4 Titanium Retaining Bolts"),
                ],
            },
            {
                "num": "6.0",
                "title": "Fire Control System (FCS) Optical/Thermal Sight & LRF Harmonization",
                "domain_lead": (
                    "On the 100-meter indoor collimated boresight range, the mechanical bore axis is "
                    "harmonized with the Gunner's Primary Sight (GPS) day channel, cooled thermal "
                    "imager (TI), Commander's Panoramic Sight, and eye-safe Laser Rangefinder (LRF)."
                ),
                "metrics": [
                    ("6.1", "Gunner Day Channel Coincidence", "≤ 0.05 mrad to mechanical bore", "100m Collimated Target Board", "Azimuth & Elevation Zero"),
                    ("6.2", "Thermal Imager (TI) Hot-Spot Zero", "≤ 0.06 mrad to day reticle", "Thermal Blackbody Crosshair", "WFOV & NFOV Channels"),
                    ("6.3", "Laser Rangefinder (LRF) Beam Axis", "≥ 90% energy within 0.25 mrad box", "IR Laser Beam Profiler Camera", "Boresight Target Matrix"),
                    ("6.4", "Commander Sight Slave Tracking", "≤ 0.10 mrad hunter-killer handoff", "Dual Sight Resolver Readout", "8 Azimuth / 3 Elev Angles"),
                    ("6.5", "Ballistic Computer Zero Store", "Non-volatile EEPROM checksum OK", "FCS Built-In Test (BIT) Log", "Final DGQA Seal & Lock"),
                ],
            },
        ],
    },
]


# ============================================================================
# 5. DETERMINISTIC FAKER TECHNICAL PROSE GENERATOR
# ============================================================================
def generate_technical_paragraph(domain_context: str, section_title: str, pass_idx: int) -> str:
    """
    Uses Faker programmatically inside the core section loop to synthesize
    dense, realistic military-industrial SOP body paragraphs with strictly
    controlled character budgets (~420-480 chars) so every page fills cleanly
    without ever overflowing to an unintended extra page.
    """
    faker_clause_1 = fake.sentence(nb_words=12).rstrip(".")
    faker_clause_2 = fake.sentence(nb_words=11).rstrip(".")
    batch_token = f"LOT-{fake.bothify(text='??-####').upper()}"
    gauge_id = f"CAL-HVF-{fake.numerify(text='####')}"

    if pass_idx == 1:
        text = (
            f"<b>Operational Execution Protocol:</b> {domain_context} "
            f"During shop-floor execution of <i>{section_title}</i>, the designated chargehand "
            f"shall verify that calibration certificate <b>{gauge_id}</b> and material traceability "
            f"record <b>{batch_token}</b> are logged in the AVNL Manufacturing Execution System (MES). "
            f"Furthermore, {faker_clause_1.lower()}, ensuring that all process parameters remain "
            f"within Class-1 Defence Quality Assurance (DGQA) acceptance envelopes."
        )
    else:
        text = (
            f"<b>Quality Assurance & Non-Conformance Control:</b> Any deviation exceeding the "
            f"specified tolerance band in Table {section_title.split()[0]} must trigger an immediate "
            f"Stage-Gate Hold and Material Review Board (MRB) disposition. Specifically, "
            f"{faker_clause_2.lower()}, while automated telemetry from station <b>{gauge_id}</b> "
            f"is archived against hull serial dossier <b>{batch_token}</b> prior to releasing the "
            f"assembly to the subsequent production workstation."
        )
    return text


# ============================================================================
# 6. PAGE BUILDERS (STRICTLY BUDGETED FOR 8 PAGES PER DOCUMENT)
# ============================================================================
def build_page_1_cover(sop: dict, styles: dict) -> list:
    """
    Builds Page 1: Document Title, Metadata Control Grid Table, Executive Summary,
    Scope & Key Performance Indicators Table, and Mandatory Safety/Compliance Notice.
    """
    story = []

    # Top classification & organizational sub-banner
    story.append(
        Paragraph(
            f"MINISTRY OF DEFENCE (DEPT. OF DEFENCE PRODUCTION) &bull; {sop['security_class']}",
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
    story.append(Paragraph("0.1 DOCUMENT CONTROL & METADATA MATRIX", styles["H1"]))

    meta_data = [
        [
            Paragraph("DOCUMENT ID", styles["TableHeader"]),
            Paragraph(sop["doc_code"], styles["TableCellBold"]),
            Paragraph("REVISION & DATE", styles["TableHeader"]),
            Paragraph(f"{sop['rev']} | 30-Oct-2026", styles["TableCell"]),
        ],
        [
            Paragraph("ISSUING AUTHORITY", styles["TableHeader"]),
            Paragraph("Heavy Vehicles Factory (HVF), Avadi", styles["TableCell"]),
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
            Paragraph("8 Pages (Controlled Distribution)", styles["TableCellBold"]),
        ],
        [
            Paragraph("APPLICABLE STD", styles["TableHeader"]),
            Paragraph("ISO 9001:2015 / GOST-V / MIL-STD-1949", styles["TableCell"]),
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
    story.append(Paragraph("0.2 EXECUTIVE SUMMARY & OPERATIONAL MANDATE", styles["H1"]))
    story.append(Paragraph(sop["exec_summary"], styles["Body"]))

    # Additional Faker-enriched executive context paragraph
    exec_context = (
        f"This controlled technical procedure applies to all CNC operators, defence metallurgists, "
        f"millwright technicians, and DGQA resident inspectors assigned to <b>{sop['shop']}</b> "
        f"at the HVF Avadi manufacturing complex. {fake.sentence(nb_words=14)} "
        f"All digital torque wrenches, laser trackers, and non-destructive testing (NDT) instruments "
        f"referenced herein must possess a valid NABL-traceable calibration sticker prior to shift "
        f"commencement. {fake.sentence(nb_words=13)}"
    )
    story.append(Paragraph(exec_context, styles["Body"]))
    story.append(Spacer(1, 6))

    # Critical Engineering KPI Summary Grid
    story.append(Paragraph("0.3 CRITICAL ENGINEERING ACCEPTANCE BENCHMARKS", styles["H1"]))
    kpi_rows = [
        [
            Paragraph("CRITICAL PARAMETER", styles["TableHeader"]),
            Paragraph("MANDATORY ENGINEERING ACCEPTANCE CRITERION", styles["TableHeader"]),
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
            "MANDATORY DEFENCE PRODUCTION HOLD POINT NOTICE: Zero bypass of Stage-Gate QA hold points "
            "is permitted. Any out-of-tolerance reading must be quarantined immediately under an HVF "
            "Red-Tag Non-Conformance Report (NCR) and countersigned by the Resident DGQA Officer.",
            styles["Callout"],
        )
    )

    # Explicit PageBreak after Page 1
    story.append(PageBreak())
    return story


def build_core_section_page(sop: dict, sec: dict, styles: dict) -> list:
    """
    Builds one core operational technical section page (Pages 2 to 7).
    Strictly budgets paragraphs, callout, and the dedicated technical tracking
    matrix table to fill a single page cleanly before calling PageBreak().
    """
    story = []

    # Section Heading (keepWithNext=True enforced in style)
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

    # Continuous Body Paragraphs generated with Faker + domain engineering prose
    story.append(
        Paragraph(
            generate_technical_paragraph(sec["domain_lead"], sec["title"], pass_idx=1),
            styles["Body"],
        )
    )
    story.append(
        Paragraph(
            generate_technical_paragraph(sec["domain_lead"], sec["title"], pass_idx=2),
            styles["Body"],
        )
    )

    # Sub-heading for Step-by-Step Shop Floor Controls
    story.append(
        Paragraph(
            f"{sec['num']}.A SHOP-FLOOR EXECUTION & METROLOGY VERIFICATION DIRECTIVES",
            styles["H2"],
        )
    )

    shop_directive_para = (
        f"Prior to initiating operation <b>{sec['num']}</b> on platform <i>{sop['platform']}</i>, "
        f"the Bay Supervisor shall confirm ambient shop temperature (20°C – 32°C), pneumatic/hydraulic "
        f"header stability, and EOT crane load-test certification. {fake.sentence(nb_words=14)} "
        f"All empirical measurements recorded during the inspection cycle must be transcribed into "
        f"the Technical Tracking Matrix below and digitally stamped by both Production and QA."
    )
    story.append(Paragraph(shop_directive_para, styles["Body"]))
    story.append(Spacer(1, 4))

    # Dedicated Technical Tracking Matrix Table wrapped in KeepTogether
    matrix_header = [
        Paragraph("STEP", styles["TableHeader"]),
        Paragraph("TECHNICAL PARAMETER / CHECKPOINT", styles["TableHeader"]),
        Paragraph("ACCEPTANCE TOLERANCE", styles["TableHeader"]),
        Paragraph("METROLOGY / GAUGE", styles["TableHeader"]),
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
                    f"TABLE {sec['num']} — TECHNICAL TRACKING & QA VERIFICATION MATRIX",
                    styles["H2"],
                ),
                tracking_table,
            ]
        )
    )
    story.append(Spacer(1, 8))

    # Empirical Station Log / Telemetry Recording Grid (wrapped in KeepTogether)
    log_rows = [
        [
            Paragraph("HULL / TURRET SERIAL NO.", styles["TableHeader"]),
            Paragraph("SHIFT / BAY CODE", styles["TableHeader"]),
            Paragraph("OPERATOR STAMP", styles["TableHeader"]),
            Paragraph("QA INSPECTOR STAMP", styles["TableHeader"]),
            Paragraph("DISPOSITION", styles["TableHeader"]),
        ],
        [
            Paragraph(f"HVF-{fake.numerify(text='2026-###')}", styles["TableCellBold"]),
            Paragraph(f"SHIFT-A / {sop['doc_code'][-6:]}", styles["TableCell"]),
            Paragraph(f"OP-{fake.numerify(text='###')} (Verified)", styles["TableCell"]),
            Paragraph(f"DGQA-{fake.numerify(text='##')} (Cleared)", styles["TableCell"]),
            Paragraph("ACCEPTED — PASS", styles["TableCellBold"]),
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

    # Critical safety/process warning box at bottom of section page
    story.append(
        Paragraph(
            f"STAGE-GATE WARNING (SECTION {sec['num']}): Do not advance the armoured assembly to "
            f"the next station until all five parameters in Table {sec['num']} are counter-stamped "
            f"in the hull e-Passport ledger.",
            styles["Callout"],
        )
    )

    # Explicit PageBreak to isolate each section onto its dedicated page (Pages 2 to 7)
    story.append(PageBreak())
    return story


def build_page_8_appendix_and_signoff(sop: dict, styles: dict) -> list:
    """
    Builds Page 8: Appendix (Applicable Defence Standards, Calibration & Environmental
    Controls, Revision History) and the Multi-Tier Official Sign-Off Signature Matrix.
    Does NOT append a trailing PageBreak so the PDF terminates cleanly at Page 8.
    """
    story = []

    story.append(
        Paragraph(
            "APPENDIX A — NORMATIVE DEFENCE STANDARDS, CALIBRATION & REVISION LEDGER",
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
        f"This Appendix establishes the normative statutory, metallurgical, and metrological "
        f"references governing <b>{sop['title']}</b> ({sop['doc_code']}) at Heavy Vehicles Factory "
        f"(HVF), Avadi. All instrumentation utilized in Sections 1.0 through 6.0 must maintain "
        f"unbroken calibration traceability to National Physical Laboratory (NPL) / NABL standards. "
        f"{fake.sentence(nb_words=13)}"
    )
    story.append(Paragraph(appendix_intro, styles["Body"]))

    # Appendix Reference Standards Table
    ref_rows = [
        [
            Paragraph("STD / CODE", styles["TableHeader"]),
            Paragraph("STANDARD TITLE & DEFENCE MANUFACTURING APPLICABILITY", styles["TableHeader"]),
            Paragraph("CUSTODIAN", styles["TableHeader"]),
        ],
        [
            Paragraph("DGAQA / DGQA-ARM-09", styles["TableCellBold"]),
            Paragraph("Quality Assurance Norms for Combat Vehicle Hull, Turret & Running Gear", styles["TableCell"]),
            Paragraph("DGQA (MoD)", styles["TableCell"]),
        ],
        [
            Paragraph("MIL-DTL-12560 / DMR", styles["TableCellBold"]),
            Paragraph("Armor Plate, Steel, Wrought, Homogeneous & High-Hardness Ballistic Spec", styles["TableCell"]),
            Paragraph("DMRL / HVF Met Lab", styles["TableCell"]),
        ],
        [
            Paragraph("ISO 10012 / NABL-141", styles["TableCellBold"]),
            Paragraph("Measurement Management Systems — Metrological Confirmation & Calibration", styles["TableCell"]),
            Paragraph("HVF Metrology Cell", styles["TableCell"]),
        ],
        [
            Paragraph("AVNL-HSE-SOP-014", styles["TableCellBold"]),
            Paragraph("Industrial Safety, Crane Rigging, Fume Extraction & Confined Space Entry", styles["TableCell"]),
            Paragraph("HVF Safety Dept", styles["TableCell"]),
        ],
    ]

    ref_table = Table(ref_rows, colWidths=[115, 290.2, 100])
    ref_table.setStyle(
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
    story.append(KeepTogether([ref_table]))
    story.append(Spacer(1, 10))

    # Multi-Tier Official Sign-Off Signature Matrix
    story.append(
        Paragraph(
            "APPENDIX B — MULTI-TIER OFFICIAL SIGN-OFF & AUTHORIZATION MATRIX",
            styles["H1"],
        )
    )
    story.append(
        Paragraph(
            "This Standard Operating Procedure is officially released for defence production upon "
            "execution of the four-tier authorization matrix below by designated HVF, AVNL, and "
            "DGQA authorities at Avadi, Chennai.",
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
            Paragraph("Deputy General Manager (Production Engg)\nHVF Avadi", styles["TableCell"]),
            Paragraph("Er. R. Venkataraman\nIOFS-4418", styles["TableCell"]),
            Paragraph("[DIGITALLY SIGNED]\nDGM/PE/HVF-AVADI", styles["TableCellBold"]),
            Paragraph("30-Oct-2026", styles["TableCell"]),
        ],
        [
            Paragraph("TIER 2: REVIEWED BY", styles["TableCellBold"]),
            Paragraph("Joint General Manager (Quality & Metallurgy)\nHVF Avadi", styles["TableCell"]),
            Paragraph("Dr. S. Muthukumar\nIOFS-3802", styles["TableCell"]),
            Paragraph("[DIGITALLY SIGNED]\nJGM/QA-MET/HVF", styles["TableCellBold"]),
            Paragraph("30-Oct-2026", styles["TableCell"]),
        ],
        [
            Paragraph("TIER 3: CONCURRENCE", styles["TableCellBold"]),
            Paragraph("Controller, Directorate General of Quality Assurance (DGQA Armoured Vehicles)", styles["TableCell"]),
            Paragraph("Brig. A. K. Rathore\nCQA(HV) Avadi", styles["TableCell"]),
            Paragraph("[SEAL & COUNTERSIGNED]\nCQA(HV)/MOD/GOI", styles["TableCellBold"]),
            Paragraph("30-Oct-2026", styles["TableCell"]),
        ],
        [
            Paragraph("TIER 4: APPROVED BY", styles["TableCellBold"]),
            Paragraph("Chief General Manager / Executive Director\nHeavy Vehicles Factory (AVNL)", styles["TableCell"]),
            Paragraph("Shri K. Parthasarathy\nCGM / HVF Avadi", styles["TableCell"]),
            Paragraph("[APPROVED FOR RELEASE]\nCGM-OFFICE/AVNL", styles["TableCellBold"]),
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
            "CONTROLLED COPY WARNING: Master copy resides in the HVF Avadi Central Technical "
            "Archive (PLM Vault). Printed copies are uncontrolled after 30 days from issue date.",
            styles["Callout"],
        )
    )

    return story


# ============================================================================
# 7. MAIN PDF GENERATION ORCHESTRATOR
# ============================================================================
def generate_all_hvf_sops(output_dir: str = ".") -> list:
    """
    Iterates through all 5 Defence Production SOP datasets and builds each
    strictly 8-page PDF document using SimpleDocTemplate and DPSUNumberedCanvas.
    """
    os.makedirs(output_dir, exist_ok=True)
    styles = build_styles()
    generated_files = []

    for idx, sop in enumerate(SOP_DATASETS, start=1):
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
            subject="Defence Production Standard Operating Procedure",
        )

        story = []

        # Page 1: Cover, Metadata Control Grid Table & Executive Summary
        story.extend(build_page_1_cover(sop, styles))

        # Pages 2 to 7: 6 Core Operational Technical Sections (1 section per page)
        assert len(sop["sections"]) == 6, "Each SOP dataset must contain exactly 6 sections."
        for sec in sop["sections"]:
            story.extend(build_core_section_page(sop, sec, styles))

        # Page 8: Appendix & Multi-Tier Official Sign-Off Signature Matrix
        story.extend(build_page_8_appendix_and_signoff(sop, styles))

        # Build PDF using the custom two-pass DPSUNumberedCanvas
        doc.build(story, canvasmaker=DPSUNumberedCanvas)
        generated_files.append(output_path)
        print(f"[{idx}/5] Successfully generated 8-page DPSU SOP PDF: {output_path}")

    return generated_files


if __name__ == "__main__":
    generate_all_hvf_sops()

