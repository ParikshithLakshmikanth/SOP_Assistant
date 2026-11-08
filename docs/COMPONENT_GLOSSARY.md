# HVF / AVNL SOP ASSISTANT — COMPONENT GLOSSARY
**Standard Operating Procedure Technical Reference**  
**Classification:** Defense Engineering Reference  
**Corpus Source:** HVF SOP 1 (Hull Welding), SOP 2 (Turret Integration), SOP 3 (Engine Alignment), SOP 4 (Torsion Suspension), SOP 5 (Main Gun Calibration)  
**Revision Scope:** Rev 4.2 (Baseline V1) and Rev 5.0 (Revised V2)

---

## Overview

This glossary provides authoritative, source-grounded definitions for physical components, major assemblies, and subsystems documented in the HVF / AVNL Standard Operating Procedures. Definitions strictly distinguish between **DIRECTLY_STATED** facts in the SOPs and **GENERAL_CONTEXT** explanations, ensuring zero ungrounded fabrication.

---

## 1. Hull & Hull Fabrication Subsystem

### Armoured Hull Tub Assembly
- **Entity Type:** `ASSEMBLY`
- **Aliases:** `hull`, `armoured hull`, `hull tub`, `hull structure`, `main hull body`
- **What it is:** The primary welded monocoque structural chassis and ballistic envelope of the combat vehicle housing the crew, powerpack, ammunition, and sub-systems.
- **What it does:** Provides all-aspect ballistic protection, absorbs dynamic operational shocks from cross-country terrain and main gun firing, and maintains rigid dimensional alignment across the suspension, engine bed, and turret plinth interfaces.
- **Where it fits:** Primary Vehicle Chassis and Base Structure.
- **Related parts:** Lower Hull Plate, Glacis Plate, Sponson Boxes, Transverse Bulkheads, Turret Ring Plinth, Torsion Bar Station Bores.
- **SOP Reference:** `HVF_SOP_1_Hull_Welding.pdf`, Section 1.0–2.0, Page 2.
- **Evidence Note:** DIRECTLY_STATED in Hull Welding SOP for structural tub assemblies and welds; broader vehicle monocoque role is GENERAL_CONTEXT.

### Glacis Plate
- **Entity Type:** `PHYSICAL_COMPONENT`
- **Aliases:** `glacis plate`, `glacis`, `upper frontal plate`, `front slope plate`
- **What it is:** A thick, highly sloped forward armour plate shielding the front of the vehicle hull.
- **What it does:** Presents a steeply angled ballistic deflection profile to ricochet and defeat incoming kinetic energy and shaped-charge projectiles.
- **Where it fits:** Armoured Hull Tub Assembly (Frontal Arc).
- **Related parts:** Lower Hull Plate, Sponson Box, Driver Hatch Aperture, Weld Joint Root Backing Strip.
- **SOP Reference:** `HVF_SOP_1_Hull_Welding.pdf`, Section 1.2 & 2.2, Page 2.
- **Evidence Note:** DIRECTLY_STATED (root gaps, bevel preparation, preheat temperatures, and root pass welding).

### Lower Hull Plate
- **Entity Type:** `PHYSICAL_COMPONENT`
- **Aliases:** `lower hull plate`, `belly plate`, `bottom plate`, `hull floor`
- **What it is:** The heavy bottom floor plate of the armoured vehicle tub fabricated from high-strength armour plate steel.
- **What it does:** Forms the structural floor of the hull, defends against mine and underbody blast energy, and provides foundation mounting points for transverse bulkheads and suspension tube sleeves.
- **Where it fits:** Armoured Hull Tub Assembly (Bottom Floor).
- **Related parts:** Glacis Plate, Sponson Box, Transverse Bulkheads, Torsion Bar Station Bores.
- **SOP Reference:** `HVF_SOP_1_Hull_Welding.pdf`, Section 1.1, Page 2.
- **Evidence Note:** DIRECTLY_STATED.

### Sponson Box
- **Entity Type:** `ASSEMBLY`
- **Aliases:** `sponson box`, `sponson`, `sponsons`, `sponson boxes`
- **What it is:** The lateral overhanging structural compartments projecting outward from the main hull tub sides over the track runs.
- **What it does:** Houses electrical wiring looms, fuel cells, air intake filtration ducts, and tools while stiffening the lateral sidewalls of the vehicle hull.
- **Where it fits:** Armoured Hull Tub Assembly (Port and Starboard Sides).
- **Related parts:** Lower Hull Plate, Glacis Plate, Track Sponson Flanges.
- **SOP Reference:** `HVF_SOP_1_Hull_Welding.pdf`, Section 1.3, Page 2.
- **Evidence Note:** DIRECTLY_STATED.

### Weld Joint Root Backing Strip
- **Entity Type:** `PHYSICAL_COMPONENT`
- **Aliases:** `weld joint`, `backing strip`, `root backing strip`
- **What it is:** A precision backing strip made from ceramic or sacrificial structural steel positioned behind heavy plate weld joints.
- **What it does:** Supports the molten weld pool during the high-amperage root pass, preventing burn-through and ensuring 100% root penetration across thick armour bevels.
- **Where it fits:** Armoured Plate Seams (Hull and Structure Joints).
- **Related parts:** Lower Hull Plate, Glacis Plate, Submerged Arc Weld Seams.
- **SOP Reference:** `HVF_SOP_1_Hull_Welding.pdf`, Section 2.3, Page 3.
- **Evidence Note:** DIRECTLY_STATED.

---

## 2. Turret Integration Subsystem

### Turret Mount System
- **Entity Type:** `ASSEMBLY`
- **Aliases:** `turret`, `turret system`, `turret structure`, `turret basket`
- **What it is:** The rotating armoured fighting structure mounted atop the vehicle hull that encloses the main gun, sighting systems, and crew stations.
- **What it does:** Provides 360-degree azimuth fire capability for the main gun and secondary armament while protecting the commander, gunner, and autoloader mechanism.
- **Where it fits:** Upper Vehicle Structure (mounted to the Hull Plinth via Turret Base Ring).
- **Related parts:** Turret Base Ring, 2A46M 125mm Gun Barrel, Rotary Slip-Ring Assembly, Azimuth Pinion Drive, Ballistic Retention Ring.
- **SOP Reference:** `HVF_SOP_2_Turret_Integration.pdf`, Section 1.0 & 2.0, Page 1.
- **Evidence Note:** DIRECTLY_STATED.

### Turret Base Ring
- **Entity Type:** `PHYSICAL_COMPONENT`
- **Aliases:** `turret base ring`, `turret ring`, `base ring`
- **What it is:** A precision-forged and machined heavy steel annular ring mounted on the vehicle hull's upper deck plinth.
- **What it does:** Provides the stationary circular foundation and bearing raceway seat that carries the rotating turret weight and reacts dynamic main gun firing loads.
- **Where it fits:** Turret Integration System / Hull Upper Deck Interface.
- **Related parts:** Cross-Roller Bearing Raceway, Internal Ring Gear, Azimuth Pinion Drive, Ballistic Retention Ring.
- **SOP Reference:** `HVF_SOP_2_Turret_Integration.pdf`, Section 1.1 & 2.1, Page 2.
- **Evidence Note:** DIRECTLY_STATED (plinth flatness 0.05 mm, torque 185 Nm in V1, 210 Nm in V2).

### Ceramic-Hybrid Cross-Roller Bearing
- **Entity Type:** `ASSEMBLY`
- **Aliases:** `ceramic-hybrid bearing`, `ceramic hybrid bearing`, `ceramic bearing`
- **What it is:** A heavy-duty precision turret bearing assembly featuring silicon nitride (Si3N4) ceramic rollers alternating between hardened steel raceways.
- **What it does:** Supports the 18-tonne rotating turret basket on the hull plinth, provides high-rigidity rotational motion with minimal friction, prevents electrical microwelding, and resists brinelling under extreme gun recoil shock.
- **Where it fits:** Turret Integration System (introduced in Rev 5.0 V2 to replace the Rev 4.2 four-point steel ball bearing).
- **Related parts:** Turret Base Ring, Cross-Roller Bearing Raceway, Ballistic Retention Ring, Ceramic Roller Sphericity.
- **SOP Reference:** `HVF_SOP_2_Turret_Integration_v2.pdf`, Section 2.1, Page 2.
- **Evidence Note:** DIRECTLY_STATED.

---

## 3. Powerpack & Engine Alignment Subsystem

### V12 Powerpack Engine Assembly
- **Entity Type:** `ASSEMBLY`
- **Aliases:** `v12 powerpack`, `powerpack`, `powerpack engine`, `engine`
- **What it is:** A unified, quick-disconnect power module integrating the 1000-hp V12 diesel engine, cooling radiators, dry-sump lubrication, turbochargers, and electrical interface.
- **What it does:** Serves as the complete self-contained vehicular power unit designed for rapid field replacement in under 45 minutes using standard recovery crane hoisting.
- **Where it fits:** Rear Engine Bay Compartment of the Hull.
- **Related parts:** Resilient Rubber-Metal Mount, Active Hydromount Damping, Crankshaft-to-Transmission Drive Shaft, Turbocharger Ducting, Dry-Sump Lubrication Loop.
- **SOP Reference:** `HVF_SOP_3_Engine_Alignment.pdf`, Section 1.0 & 2.1, Page 1.
- **Evidence Note:** DIRECTLY_STATED.

### Active Hydromount Damping Unit
- **Entity Type:** `PHYSICAL_COMPONENT`
- **Aliases:** `hydromount`, `hydromounts`, `hydraulic mount`, `active hydromount`
- **What it is:** An advanced fluid-filled elastomeric vibration isolation mount with electronically or hydraulically tuned fluid damping passages.
- **What it does:** Isolates the vehicle hull and transmission from engine low-frequency torque pulses and attenuates high-frequency vibration during high-speed tactical cross-country operations.
- **Where it fits:** V12 Powerpack Mounting Interface / Engine Bay Hull Pedestals (introduced in Rev 5.0 V2).
- **Related parts:** V12 Powerpack Engine, Crankshaft-to-Transmission Drive Shaft, Resilient Rubber-Metal Mount.
- **SOP Reference:** `HVF_SOP_3_Engine_Alignment_v2.pdf`, Section 1.2 & 2.1, Page 2.
- **Evidence Note:** DIRECTLY_STATED.

### Engine-to-Transmission Alignment System
- **Entity Type:** `ASSEMBLY`
- **Aliases:** `engine alignment`, `powerpack alignment`, `engine alignment procedure`
- **What it is:** The precision mechanical spatial and coaxial positioning of the V12 diesel engine crankshaft output flange relative to the transmission input shaft.
- **What it does:** Eliminates parallel radial offset and angular face misalignment, preventing catastrophic driveline vibration, premature bearing destruction, flexible coupling shear, and power transmission failure.
- **Where it fits:** Engine Bay Compartment between the V12 Powerpack and the cross-drive hydromechanical transmission.
- **Related parts:** Crankshaft Output Flange, Transmission Input Flange, Dial Indicator Gauge, Laser Alignment Tool, Alignment Shims, Hydromounts.
- **SOP Reference:** `HVF_SOP_3_Engine_Alignment.pdf` (Rev 4.2 / Rev 5.0), Section 2.0, 3.0 & 4.0, Page 2.
- **Evidence Note:** DIRECTLY_STATED. Dial indicator tolerances (0.05 mm V1, 0.02 mm V2) and shimming steps are directly stated in the Engine Alignment SOP.

---

## 4. Torsion Suspension & Running Gear Subsystem

### Torsion Bar
- **Entity Type:** `PHYSICAL_COMPONENT`
- **Aliases:** `torsion bar`, `torsion bars`, `suspension torsion bar`
- **What it is:** A high-strength alloy spring steel cylindrical shaft with precision splined ends that spans transversely across the bottom width of the vehicle hull.
- **What it does:** Acts as the primary suspension spring for each road wheel; twists elastically under balancer arm deflection to absorb shock loads and support vehicle sprung weight.
- **Where it fits:** Torsion Suspension Subsystem (installed inside transverse hull tube stations).
- **Related parts:** Balancer Arm, Needle-Bearing Housing, Road Wheel Hub, Anchor Plug, Hydraulic Rotary Damper.
- **SOP Reference:** `HVF_SOP_4_Torsion_Suspension.pdf`, Section 1.1 & 2.1, Page 1.
- **Evidence Note:** DIRECTLY_STATED (preset preload angle 32° ± 0.5°).

### Double-Pin Track System
- **Entity Type:** `ASSEMBLY`
- **Aliases:** `track`, `track system`, `tracks`, `track link`, `double-pin track`
- **What it is:** An endless continuous articulated belt consisting of forged steel track shoes linked together by rubber-bushed double pins and end-connectors.
- **What it does:** Distributes the vehicle's 45+ tonne weight across a broad ground contact area, engages the drive sprocket to propel the vehicle, and guides road wheel motion across obstacle terrain.
- **Where it fits:** Running Gear and Suspension Subsystem.
- **Related parts:** Double-Pin Track Link, Drive Sprocket, Road Wheel Hub, Track Pin Wedge & End-Connector, Idler Crank.
- **SOP Reference:** `HVF_SOP_4_Torsion_Suspension.pdf`, Section 4.0 & 5.0, Page 4.
- **Evidence Note:** DIRECTLY_STATED (static catenary sag 35–45 mm in V1, 25–35 mm in V2).
