# Variant Contracts (VoltForge 2.0)

Formal problem contracts for each supported benchmark family.  
**Do not** claim two families are equivalent merely because they share Solomon-like coordinates.

Parsers emit `ProblemSpecV2` under `evrptw_autolab.problem.v2`. Legacy Schneider
`EVRPTWInstance` remains the Experiment A/B contract and is adapted via
`load_schneider_v2`.

| Family | Folder | Parser | Instance count (validated) |
|--------|--------|--------|----------------------------|
| Schneider E-VRPTW | `dataset/schneider` | `load_schneider_v2` | 92 |
| Montoya E-VRP-NL | `dataset/montoya-et-al-2017` | `load_montoya` | 120 |
| Bezzi EVRP-MRT | `dataset/Bezzi & Ceselli EVRP-MRT` | `load_bezzi` | 66 (`**/Instances/*.xml`; Solutions excluded) |
| Goeke PDPTW-EV | `dataset/goeke-2018` | `load_goeke` | 92 |
| Hiermann H2E-FTW | `dataset/hiermann-et-al-2017-set-1` | `load_hiermann` | 56 |

---

## 1. Schneider E-VRPTW

**Source:** Schneider et al. (2014).  
**Capabilities:** time windows, capacity, battery, full recharge, Euclidean distance.

### Physics (legacy evaluator — must not weaken)

- Distance: Euclidean \(d_{ij}=\sqrt{(x_i-x_j)^2+(y_i-y_j)^2}\).
- Travel time: \(t_{ij}=d_{ij}/v\).
- Energy: \(e_{ij}=r\cdot d_{ij}\) with linear consumption rate \(r\).
- Recharge: full recharge; duration \((\text{battery}-b)\cdot g\) with inverse refuel rate \(g\).

### Objective protocol

Minimize fleet size, then total distance (as in the frozen Schneider evaluator).

### Worked micro example

Private micro instance `micro_g1_one_customer`: depot→C1→depot is energy-feasible with a large battery and no station visit.

### Held-out rule

RC2 remains inaccessible to development feedback (Experiment A/B provenance).

---

## 2. Montoya E-VRP-NL

**Source:** Montoya et al. (2017), nonlinear charging.  
**Capabilities:** battery, partial recharge, **nonlinear** piecewise charging, Euclidean distances (14 decimals), max travel time. **No** customer time windows / freight capacity in the raw XML.

### Units (from dataset readme)

- Coordinates: km  
- Speed: km/h (`speed_factor`)  
- Energy: Wh  
- Time: hours  

### Energy / travel

\[
d_{ij}=\lVert (x_i,y_i)-(x_j,y_j)\rVert_2,\quad
t_{ij}=d_{ij}/\text{speed},\quad
e_{ij}=\text{consumption\_rate}\cdot d_{ij}.
\]

### Nonlinear charging

Each station has a `cs_type` ∈ {slow, normal, fast}. The vehicle provides a piecewise-linear charging function per type: breakpoints \((b_k,\tau_k)\) with battery level \(b\) (Wh) and cumulative charging time \(\tau\) (h). Charging duration between SoC levels uses linear interpolation along this curve. **Constant-rate charging is not an allowed substitute.**

### Route duration

`max_travel_time` bounds total route duration.

### Worked example

`tc0c10s2cf1.xml`: 10 customers, 2 fast stations, battery 16000 Wh, consumption 125 Wh/km, speed 40 km/h, max travel time 10 h, 4 breakpoints on the fast curve (0→13600→15200→16000 Wh).

---

## 3. Bezzi & Ceselli EVRP-MRT

**Source:** Bezzi & Ceselli multi-technology EVRP.  
**Capabilities:** capacity, battery, multiple charging technologies, **explicit travel/energy matrices**, max route duration. Customer TW are **not** present in the inspected instance XML.

### Distance / energy

Do **not** replace the provided `<links>` matrix with Euclidean distances:

\[
t_{ij}=\texttt{travel\_time}(i,j),\quad
e_{ij}=\texttt{energy\_consumption}(i,j).
\]

### Technologies

Stations declare `has_tech`. Vehicle `charging_techs` give parameters \((\gamma,\rho)\) per technology. Technology compatibility must be enforced by the evaluator.

### Solutions

`**/Solutions/*.xml` contain published optima for **validation/reporting only**. Parsers refuse to load them as problem instances.

### Worked example

`Dataset_A/Instances/C101-5.xml`: 5 customers, stations with tech 0/1, depot node 8, fleet capacity 200, battery 77, max travel 1236, 2 vehicles, explicit link matrix.

---

## 4. Goeke PDPTW-EV

**Source:** Goeke electric pickup-and-delivery with time windows.  
**Capabilities:** TW, capacity, battery, (partial) recharge, pickup–delivery precedence, Euclidean distance.

### Requests

- Types: `cp` (pickup), `cd` (delivery), `d` depot, `f` station.
- `PartnerID` pairs pickup and delivery; demand conserved (\(q_{p}=-q_{d}\), \(q_p>0\)).
- Same-vehicle and pickup-before-delivery are hard constraints.

### Physics

Same linear energy model as Schneider-style parameters: battery capacity, consumption rate, inverse recharging rate, velocity.

### Worked example

`c101C6.txt`: three PD pairs (C12↔C30, C64↔C85, C101↔C100), battery 77.75, capacity 200, \(r=1\), \(g=3.47\), \(v=1\).

---

## 5. Hiermann H2E-FTW (set 1)

**Source:** Hiermann et al. heterogeneous fleet with time windows.  
**Capabilities:** TW, capacity, heterogeneous fleet with **ICEV / PHEV / BEV**, station-specific `rechargingrate`, energy prices for fossil fuel and electricity.

### Fleet

Nine vehicle types (Small/Medium/Large × ICEV/PHEV/BEV) with capacity, fuel rate, battery, energy rate, and fixed cost.  
**Do not** convert this benchmark into a homogeneous all-electric VRP.

### Travel-time convention

The raw files do **not** state a velocity. The evaluator must apply the paper’s documented distance–time convention explicitly (`travel_time_model: unspecified_in_file` in metadata). Inventing a speed silently is forbidden.

### Worked example

`c101_21.txt`: 100 customers, 21 stations with recharge rate 4.75, 9 vehicle types, `fossil-fuel=2.0`, `electricity=0.3`.

---

## Cross-family transfer rules

A heuristic component may transfer only if its required `CapabilityFlags` are a subset of the target instance capabilities (e.g. a PD precedence operator must not run on Schneider).
