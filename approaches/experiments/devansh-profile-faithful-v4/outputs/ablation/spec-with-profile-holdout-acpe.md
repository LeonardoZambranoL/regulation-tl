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

- Product: Acceleration Control for Pedal Error (ACPE) system: a driver-assistance function that limits or suppresses propulsion torque when a sudden, strong accelerator pedal input (likely a pedal error instead of braking) occurs at low parking or manoeuvring speed while an obstacle is detected ahead of or behind the vehicle.
- Vehicle categories: M1 (passenger car) and N1 (light goods vehicle) with automatic transmission, in petrol, hybrid and battery-electric variants. Manual-transmission vehicles and other categories are not stated.
- Mounting: Vehicle-integrated system distributed over the vehicle. Ultrasonic sensors are at the front and rear; their exact location (presumably the bumpers) is not stated. The camera is front-facing; its exact location (e.g. windscreen or grille) is not stated. The ACPE software runs in the powertrain control unit. The accelerator pedal position sensor is at the accelerator pedal. The tell-tale and buzzer are in the instrument cluster. The deactivation switch is in the infotainment menu. Mounting positions, heights and aiming of the sensors and camera are unknown.

### Functions
- Obstacle detection ahead of the vehicle (front ultrasonic sensors and front camera) at parking and manoeuvring speeds
- Obstacle detection behind the vehicle (rear ultrasonic sensors) at parking and manoeuvring speeds
- Detection of pedal error: a sudden, strong accelerator pedal input via the accelerator pedal position sensor (rate and stroke thresholds not stated)
- Acceleration control intervention: limiting or suppressing propulsion torque when an obstacle is detected and a pedal error is detected (forward and reverse direction implied)
- Driver warning on intervention: visual (instrument cluster tell-tale) and acoustic (buzzer)
- Manual deactivation by the driver through the infotainment menu
- Automatic reactivation (default ON) at the next engine start / start of propulsion system
- Fault detection and failure warning to the driver

### Components
- Front ultrasonic sensors: housing PBT-GF30 (representative value); detect obstacles ahead
- Rear ultrasonic sensors: housing PBT-GF30 (representative value); detect obstacles behind
- Front camera: aluminium die-cast housing with PC lens (representative value); detects obstacles ahead
- Powertrain control unit hosting the ACPE software function: PCB with microcontroller in an aluminium housing (representative value); does decision logic and torque limitation or suppression
- Accelerator pedal position sensor (material not stated): measures accelerator pedal position and application rate to detect pedal error
- Instrument cluster tell-tale (material not stated): visual intervention and fault warning
- Instrument cluster buzzer (material not stated): acoustic intervention warning
- Deactivation switch, implemented as a software menu item in the infotainment system: lets the driver deactivate the system
- Wiring harness: copper conductors with PVC / XLPE insulation (representative value); power supply and signal connection
- Note: the spec says all materials are representative values to be confirmed against the actual bill of materials

### Configuration
- Sensor fusion architecture: front ultrasonic sensors plus front camera for the forward direction; rear ultrasonic sensors only for the reverse direction (no rear camera stated)
- ACPE is a software function integrated in the existing powertrain control unit, not a dedicated ECU
- Intervention acts on propulsion torque (engine, hybrid or electric motor torque request); use of brake intervention is not stated
- HMI is shared: tell-tale and buzzer in the instrument cluster, deactivation through an infotainment menu (soft switch, not a dedicated hardware switch)
- Default state is ON at each engine start; the deactivated state is not retained
- Electronics: microcontroller-based PCB; communication bus between sensors, powertrain control unit and cluster is not stated
- Applied across powertrains: petrol ICE, hybrid and BEV, automatic transmission only
- No exploded-view image attached; configuration derived from the spec text only

### Performance targets (from image / spec)
- No numeric or test targets are stated in the spec (no speed threshold, obstacle distance, pedal rate or stroke threshold, torque or acceleration limit, or detection range); all are unknown
- Operating condition stated qualitatively: 'at low speed near an obstacle' / 'parking and manoeuvring speeds'
- Pedal error criterion stated qualitatively: 'sudden, strong accelerator pedal input'
- Reactivation condition: 'reactivates at the next engine start'

### Features the product HAS
- Forward obstacle detection (ultrasonic plus camera)
- Rearward obstacle detection (ultrasonic)
- Propulsion torque limitation or suppression on detected pedal error
- Visual intervention warning (tell-tale)
- Acoustic intervention warning (buzzer)
- Driver deactivation via infotainment menu
- Automatic reactivation at next engine start
- Fault reporting to the driver
- Applicability to ICE, hybrid and BEV powertrains

### Optional features NOT stated in the spec (experts still list rules that apply only if such a feature is used, written WITH their condition, e.g. 'In case replaceable light source modules are used, ...': keep those rules and state the condition; drop only rules for functions or components the product clearly does not have)
- Pedal error mitigation without an obstacle present (obstacle-independent acceleration suppression) – not stated
- Speed range or upper operating speed threshold – unknown
- Accelerator pedal rate or stroke threshold values – unknown
- Obstacle types detected (vehicle, wall, pedestrian, cyclist) and detection distances – unknown
- Brake intervention (automatic braking) in addition to torque reduction – not stated
- Driver override conditions (e.g. pedal release and re-application, kick-down) – unknown
- Separate fault tell-tale vs shared tell-tale; tell-tale symbol and colour – unknown
- Deactivation tell-tale or indication of OFF state – not stated
- Whether deactivation needs more than one deliberate action – unknown
- Tell-tale bulb check at ignition ON – not stated
- Behaviour when sensors are blocked or dirty (soiling or degradation detection) – not stated
- Behaviour on gradients or with a trailer – unknown
- Support for manual-transmission vehicles – not stated (automatic only)
- Rear camera – not stated
- Over-the-air or software update capability – unknown
- Cybersecurity measures – not stated
- Data recording or logging – not stated
- Interaction with other ADAS (AEBS, parking assist, ACC) – unknown
- Sensor heating or cleaning – not stated
- Ingress protection rating and temperature range of sensors or camera – unknown

### Requirement topics an expert expects
- Scope and applicability: M1/N1 vehicles fitted with ACPE (triggered by vehicle categories and automatic transmission)
- General ACPE performance requirements: suppressing acceleration on pedal error with an obstacle ahead and behind (triggered by front and rear obstacle detection and torque suppression)
- Pedal error detection criteria and false-intervention avoidance in normal driving (triggered by the sudden, strong pedal input logic)
- Test procedures and conditions: test track, obstacle target, approach distance, vehicle starting from standstill, forward and reverse runs, pedal application method (triggered by the intervention function; no numeric targets stated, so they must be obtained)
- Performance limits: maximum vehicle speed or acceleration reached, or no collision with the target during tests (triggered by torque limitation; values unknown)
- Driver override and operation conditions (triggered by torque suppression acting on the driver's command)
- Driver warning on intervention: optical and acoustic signal requirements (triggered by tell-tale and buzzer)
- Manual deactivation requirements: means of deactivation, deliberate action, indication of deactivated state (triggered by infotainment menu deactivation)
- Automatic reactivation at each start cycle (triggered by reactivation at next engine start)
- Failure detection and failure warning signal, including non-electrical failures such as sensor blockage (triggered by fault reporting)
- Tell-tale identification, symbols and colour per UN R121 if applicable (triggered by instrument cluster tell-tale)
- Safety of complex electronic control systems: functional safety documentation, safety concept, verification and audit annex (triggered by software in the powertrain control unit and sensor fusion)
- Electromagnetic compatibility per UN R10 (triggered by ultrasonic sensors, camera, microcontroller ECU and wiring harness)
- Cybersecurity per UN R155 and software updates per UN R156 where applicable (triggered by software-based function in a networked ECU and infotainment interface)
- Interaction with other systems (AEBS, parking aids) and powertrain variants ICE, hybrid and BEV (triggered by multi-powertrain applicability)
- Information for users: owner's manual description of the system, limitations and deactivation (triggered by driver-assistance nature and deactivation)
- Periodic technical inspection provisions, e.g. verifying the operational status of the system (triggered by electronic safety system with fault reporting)
- Environmental robustness of sensors and camera (water, dust, temperature, vibration), typically covered in the CEL/functional safety assessment rather than separate component tests (triggered by exterior-mounted ultrasonic sensors and camera)
- Type-approval documentation, marking of approval on the vehicle approval, and conformity of production (triggered by vehicle-level type approval of the system)
