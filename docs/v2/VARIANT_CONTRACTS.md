# Variant Contracts (VoltForge 2.0)

Living document. Equations and worked examples are expanded as parsers/evaluators land.
**Do not** claim two families are equivalent merely because they share Solomon geometry.

| Family | Folder | Status (Milestone 1/2 slice) |
|--------|--------|------------------------------|
| Schneider E-VRPTW | `dataset/schneider` | Legacy loader **validated** (frozen Experiment A/B) |
| Montoya E-VRP-NL | `dataset/montoya-et-al-2017` | Inventory + hashes; nonlinear XML parser pending |
| Bezzi & Ceselli EVRP-MRT | `dataset/Bezzi & Ceselli EVRP-MRT` | Inventory + hashes; multitech XML parser pending |
| Goeke PDPTW-EV | `dataset/goeke-2018` | Inventory + hashes; PD pairing parser pending |
| Hiermann H2E-FTW | `dataset/hiermann-et-al-2017-set-1` | Inventory + hashes; heterogeneous fleet parser pending |

## Schneider (legacy contract — must not weaken)

- Homogeneous EV, capacity, time windows, full recharge, Euclidean travel.
- Objective protocol: fleet size then distance (as in existing evaluator).
- Held-out RC2 remains untouched for development feedback.

## Montoya (pending)

- Nonlinear piecewise charging functions; partial charging decisions.
- Units: km, km/h, Wh; double-precision Euclidean distances (per dataset readme).

## Bezzi EVRP-MRT (pending)

- Multiple charging technologies with technology-specific times/costs.
- Published optima used only for final reporting validation, never for construction.

## Goeke PDPTW-EV (pending)

- Pickup/delivery pairs (`cp`/`cd`, PartnerID), precedence, same-vehicle, load dynamics.

## Hiermann H2E-FTW (pending)

- Heterogeneous fleet; do **not** collapse to homogeneous all-electric VRP.

See `docs/v2/CURRENT_SYSTEM_AUDIT.md` for migration boundaries.
