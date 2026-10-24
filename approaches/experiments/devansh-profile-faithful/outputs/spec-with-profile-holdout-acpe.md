# spec: Acceleration Control for Pedal Error (ACPE) system

## Product Type

Acceleration control system for pedal error: a driver-assistance function that suppresses unintended acceleration
when the driver presses the accelerator pedal by mistake (instead of the brake) at low speed near an obstacle.

## Vehicle Category

M1 (passenger car) and N1 (light goods vehicle), automatic transmission, petrol, hybrid and battery-electric variants.

## Function

- Detects obstacles ahead and behind the vehicle at parking and manoeuvring speeds
- Detects a sudden, strong accelerator pedal input that is likely a pedal error
- Limits or suppresses the propulsion torque when both occur
- Warns the driver (visual and acoustic) when it intervenes
- Can be deactivated by the driver and reactivates at the next engine start
- Reports system faults to the driver

## Main Parts

- Front and rear ultrasonic sensors
- Front camera
- ACPE software function in the powertrain control unit
- Accelerator pedal position sensor
- Instrument cluster tell-tale and buzzer
- Deactivation switch in the infotainment menu

## Materials

Representative values — confirm against actual bill of materials.

| Component | Typical material(s) |
| --- | --- |
| Ultrasonic sensor housing | PBT-GF30 |
| Camera housing | Aluminium die cast, PC lens |
| Control unit | PCB with microcontroller, aluminium housing |
| Wiring harness | Copper, PVC / XLPE insulation |

## Product profile (derived from the spec and the exploded view)

- Product: Acceleration Control for Pedal Error (ACPE) system: a driver-assistance function that detects obstacles ahead of and behind the vehicle at parking and manoeuvring speeds, recognises a sudden, strong accelerator pedal input likely to be a pedal error, and then limits or suppresses propulsion torque while warning the driver.
- Vehicle categories: M1 (passenger car) and N1 (light goods vehicle); automatic transmission only; petrol, hybrid and battery-electric variants. Manual-transmission variants, diesel variants and other categories are not stated.
- Mounting: Vehicle-integrated system distributed across the vehicle. Exact positions are not stated. Implied: ultrasonic sensors at the front and rear of the vehicle (likely the bumpers), a forward-facing front camera (location unknown, e.g. windscreen or grille), and software in the powertrain control unit. The accelerator pedal position sensor is at the accelerator pedal, the tell-tale and buzzer are in the instrument cluster, and the deactivation switch is in the infotainment menu.

### Functions
- Obstacle detection ahead of the vehicle at parking and manoeuvring speeds (front ultrasonic sensors and front camera)
- Obstacle detection behind the vehicle at parking and manoeuvring speeds (rear ultrasonic sensors); this implies ACPE in both the forward and reverse directions
- Pedal-error detection: recognising a sudden, strong accelerator pedal input likely made in error instead of the brake
- Acceleration control: limiting or suppressing propulsion torque when an obstacle is detected and pedal error is suspected
- Driver intervention warning: visual (tell-tale) and acoustic (buzzer) when the system intervenes
- Manual deactivation by the driver via the infotainment menu
- Automatic reactivation at the next engine start (start of each engine/propulsion start cycle)
- Failure warning: reporting system faults to the driver

### Components
- Front ultrasonic sensors: housing PBT-GF30 (representative value). Detect obstacles ahead at low speed.
- Rear ultrasonic sensors: housing PBT-GF30 (representative value). Detect obstacles behind at low speed.
- Front camera: aluminium die-cast housing with PC lens (representative). Detects obstacles ahead.
- ACPE software function: hosted in the powertrain control unit. Fuses sensor and pedal inputs, decides on intervention and commands torque limitation.
- Powertrain control unit: PCB with microcontroller in an aluminium housing (representative). Executes the ACPE logic and controls propulsion torque.
- Accelerator pedal position sensor: material not stated. Measures pedal position and rate of application for pedal-error detection.
- Instrument cluster tell-tale: material not stated. Gives the visual warning of intervention, and possibly of faults and deactivation status.
- Buzzer: material not stated. Gives the acoustic warning of intervention.
- Deactivation switch: a software menu item in the infotainment system that lets the driver deactivate the system.
- Wiring harness: copper conductors with PVC / XLPE insulation (representative). Provides electrical connection and signal transfer between components.

### Configuration
- Sensor fusion: front ultrasonic sensors and front camera cover the forward direction; rear ultrasonic sensors only cover the rearward direction (no rear camera stated).
- ACPE is implemented as a software function inside the existing powertrain control unit, not as a dedicated ECU.
- Intervention acts on propulsion torque limitation or suppression. Use of the service brake for active braking is not stated.
- Activation logic requires both an obstacle detection and a pedal-error-like accelerator input.
- Default state is ON: after driver deactivation the system reactivates automatically at the next engine start.
- Deactivation is through an infotainment menu, a soft switch. The number of steps or confirmation needed is not stated.
- Warnings are given through the existing instrument cluster tell-tale and buzzer.
- Powertrain coverage includes ICE (petrol), hybrid and BEV with automatic transmission, so torque control is implemented across different propulsion architectures.
- Material data are flagged as representative and must be confirmed against the actual bill of materials.

### Performance targets (from image / spec)
- No numeric performance or test targets are stated in the spec; no image was attached.
- Qualitative only: operation at 'low speed' / 'parking and manoeuvring speeds' (speed range not quantified).
- Qualitative only: triggering condition is a 'sudden, strong accelerator pedal input' (pedal travel or rate thresholds not quantified).
- Qualitative only: obstacle 'near' the vehicle (detection distance not quantified).

### Features the product HAS
- Forward obstacle detection (ultrasonic and camera)
- Rearward obstacle detection (ultrasonic)
- Pedal-error (misapplication) detection based on accelerator input
- Propulsion torque limitation/suppression
- Visual intervention warning (tell-tale)
- Acoustic intervention warning (buzzer)
- Driver-operable deactivation via infotainment menu
- Automatic reactivation at each engine start
- Failure/fault indication to the driver
- Applicability to petrol, hybrid and battery-electric automatic-transmission vehicles

### Optional features NOT stated in the spec (experts still list rules that apply only if such a feature is used, written WITH their condition, e.g. 'In case replaceable light source modules are used, ...': keep those rules and state the condition; drop only rules for functions or components the product clearly does not have)
- Numeric operating speed range (activation and deactivation speed thresholds)
- Detection range and field of view of sensors; obstacle types detected (vehicle target, wall, pedestrian, etc.)
- Accelerator pedal threshold values (travel, rate, time) for pedal-error recognition
- Behaviour without an obstacle (acceleration suppression when no obstacle is detected): not stated
- Whether active braking (service brake intervention) is used in addition to torque limitation
- Duration of intervention and conditions for ending the intervention or overriding it (e.g. kick-down, release-and-reapply)
- Effect of brake pedal application during intervention
- Whether the deactivation requires more than one deliberate action, and whether a deactivation status tell-tale is shown
- Exact tell-tale symbol, colour and whether it differs between intervention, deactivation and failure states
- Acoustic warning characteristics (sound level, duration)
- Behaviour in degraded sensor conditions (dirt, snow, rain, darkness, sensor blockage) and related driver information
- Operation on gradients, trailer attached, and towing mode behaviour
- Manual transmission, diesel or other powertrain variants
- Software update (OTA) capability and software identification
- Cyber-security measures
- Interaction with other ADAS (AEB, parking assist, DCAS) and arbitration logic
- Self-check at start-up and its duration
- Exact mounting positions and calibration/aiming procedure for sensors and camera
- Event data recording of ACPE interventions

### Requirement topics an expert expects
- Scope and applicability (UN Regulation on ACPE, M1/N1): triggered by the product being an acceleration control for pedal error system on M1 and N1 vehicles
- Definitions and system boundaries: triggered by the distributed system (sensors, powertrain ECU software, HMI)
- General requirements for obstacle-based acceleration suppression in the forward direction: triggered by front ultrasonic sensors and camera with torque limitation
- Requirements for rearward (reverse) acceleration suppression, if covered: triggered by rear ultrasonic sensors and detection behind the vehicle
- Performance test with obstacle (stationary vehicle near an obstacle, full or sudden accelerator application; no collision or limited impact speed): triggered by the torque suppression function. Thresholds are unknown in the spec.
- Requirements for situations without an obstacle (optional or conditional): triggered by the unknown no-obstacle behaviour
- Driver override and termination of intervention: triggered by torque suppression acting against driver input
- Warning / HMI requirements (visual and acoustic intervention warning): triggered by the tell-tale and buzzer
- Failure warning and fault detection: triggered by the stated fault reporting
- Deactivation and automatic reactivation requirements (default ON at each start cycle, deliberate deactivation action): triggered by the infotainment deactivation switch and reactivation at engine start
- Tell-tale symbol and colour (UN R121 controls, tell-tales and indicators): triggered by the instrument cluster tell-tale and infotainment control
- Safety of complex electronic control systems / functional safety documentation (CEL annex: system description, safety concept, verification): triggered by the software-based function in the powertrain ECU
- Electromagnetic compatibility (UN R10): triggered by the electronic control unit, sensors, camera and wiring harness
- Cyber-security and software updates (UN R155 / UN R156) at vehicle level: triggered by software-implemented control of propulsion torque
- Interaction with braking and powertrain systems (UN R13-H braking, UN R100 electric powertrain for BEV/hybrid): triggered by torque control on electrified powertrains and possible brake interaction
- Sensor robustness and environmental conditions (temperature, weather, sensor blockage information): triggered by ultrasonic sensors and camera exposed at the vehicle exterior
- Approval documentation, marking of approval and conformity of production: triggered by the system being type-approved at vehicle level
- Transitional provisions and variants (powertrain types, automatic transmission only): triggered by the multiple propulsion variants
