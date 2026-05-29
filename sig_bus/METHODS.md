# SIG-Bus — Demand Allocation Method

**Version:** 0.2  
**Author:** Diego Camargo  
**Project:** PIBIC DPPG 113/2021  
**Last updated:** 2026-05-29

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Data Sources](#2-data-sources)
3. [The Boarding Load Profile Method](#3-the-boarding-load-profile-method)
4. [Spatial Join: Demand Points to GTFS Stops](#4-spatial-join-demand-points-to-gtfs-stops)
5. [Representative Service Pattern Selection](#5-representative-service-pattern-selection)
6. [Hourly Decomposition](#6-hourly-decomposition)
7. [Assumptions Summary](#7-assumptions-summary)
8. [Limitations and Their Practical Impact](#8-limitations-and-their-practical-impact)
9. [References](#9-references)

---

## 1. Problem Statement

Transit planners and researchers need to know the **passenger load** on each segment
of a bus route — i.e., how many passengers are on board the vehicle as it travels
between consecutive stops. This quantity drives fleet-sizing decisions, informs
capacity analysis, and is required for the calculation of passenger-kilometres
(a key service quality indicator).

Direct measurement of loads requires automatic passenger counters (APC) or on-board
surveys. When only boarding data are available (the common case for many Brazilian
operators, including BHTrans), load profiles must be **estimated** from boardings
using simplifying assumptions.

SIG-Bus implements the **boarding-only load profile** method, integrating:

- **GTFS** (*General Transit Feed Specification*) — provides the route geometry,
  stop sequence, and service frequency.
- **SIU-BHTrans demand data** — provides observed boardings per stop per hour for
  each route and direction.

---

## 2. Data Sources

### 2.1 GTFS

GTFS is the de facto standard for publishing public transit schedules
(Google, 2006; GTFS.org). A GTFS feed is a ZIP archive containing a set of
comma-separated text files:

| File | Key fields used | Role in SIG-Bus |
|------|----------------|-----------------|
| `routes.txt` | `route_id`, `route_short_name` | Links demand `LINHA` to the GTFS route graph |
| `trips.txt` | `trip_id`, `route_id`, `shape_id`, `direction_id` | Identifies service patterns and directions |
| `stop_times.txt` | `trip_id`, `stop_id`, `stop_sequence`, `departure_time` | Provides ordered stop lists and departure times |
| `stops.txt` | `stop_id`, `stop_lat`, `stop_lon`, `stop_name` | Geographic position of each stop |
| `shapes.txt` | `shape_id`, `shape_pt_lat`, `shape_pt_lon`, `shape_pt_sequence` | Route alignment geometry |
| `calendar.txt` | `service_id`, day flags, date range | Identifies which services run on a given day |

The BHTrans GTFS feed (2024) covers 327 routes in the Belo Horizonte metropolitan
area. The `shape_id` field is a sequential integer (1–1109) with no direct relation
to the route number; all joins use `route_short_name` as the human-readable key.

### 2.2 SIU-BHTrans Boarding Data

The *Sistema de Informações do Usuário* (SIU) records passenger boardings collected
by automatic fare validators on BHTrans buses. The exported CSV contains one row per
stop per route, with:

- `LINHA`: route code (matches `route_short_name` in GTFS).
- `PC`: direction code — `1` for outbound (*ida*), `2` for inbound (*volta*).
- `Seq`: sequential position of the stop along the route (1-based).
- Columns `0`–`23`: boardings observed in each hour of the day.
- ` Total geral `: total boardings across the full day.
- Coordinates in WGS84 (latitude/longitude) and SIRGAS 2000 UTM 23S (X/Y).

> The geographic coordinates in the SIU data represent the **boarding point** as
> registered by the fare system, which may differ slightly from the nearest GTFS
> stop due to GPS drift or stop relocation.

---

## 3. The Boarding Load Profile Method

### 3.1 Notation

Let a route in direction *d* be served by stops s₀, s₁, …, sₙ (in travel order).
Define:

- **B(i)** — observed boardings at stop sᵢ (from the SIU data).
- **A(i)** — alightings at stop sᵢ (not measured).
- **L(i)** — passenger load on segment [sᵢ → sᵢ₊₁] (the quantity we want).

The **exact load profile** satisfies the flow conservation identity:

```
L(i) = L(i−1) + B(i) − A(i),   i = 1, …, n−1
L(0) = B(0)   (no passengers board before the first stop)
A(n) = L(n−1) + B(n)   (all remaining passengers alight at the last stop)
```

Because alighting data are unavailable, SIG-Bus applies the **boarding-only
approximation**:

```
A(i) = 0   for all i < n
```

This yields the **accumulated boarding profile**:

```
L̂(i) = Σⱼ₌₀ⁱ B(j)
```

which is the value stored in the `passageiros_acum` field of `tramos_demanda`.

### 3.2 Interpretation

Because A(i) ≥ 0 for all i, we have L̂(i) ≥ L(i): the accumulated boarding
profile is an **upper bound** on the true load. The profile grows monotonically
from the first stop to the last, which is realistic for routes whose dominant
flow is unidirectional (e.g. suburb-to-centre in the morning peak).

For routes with significant intermediate exchange (passengers boarding and
alighting throughout the route), L̂ can overestimate the true load substantially.
The deviation is largest in the middle of the route, where actual loads plateau
or decline.

### 3.3 Per-trip load

The boarding values in the SIU data are **aggregated across all trips** that
operated in a given hour. To estimate the average per-trip load, divide by the
number of trips:

```
L̂_trip(i, h) = L̂(i, h) / n_viagens(h)
```

where `n_viagens(h)` is the count of trips that **departed** the first stop in
hour *h* according to the GTFS schedule. This field is provided in `tramos_demanda`
to allow the user to perform this calculation in QGIS (e.g. via the Field Calculator).

---

## 4. Spatial Join: Demand Points to GTFS Stops

The SIU boarding data contains the geographic coordinates of each boarding point,
but these coordinates do not correspond one-to-one with GTFS stop IDs. A spatial
join is required to map each SIU point to its nearest GTFS stop.

### 4.1 Algorithm

For each SIU demand point *p* with coordinates (λₚ, φₚ), the plugin finds the
GTFS stop *s* ∈ *S(route, direction)* — restricted to the stop sequence of the
selected route's dominant shape — that minimises:

```
d(p, s) = sqrt((λₚ − λₛ)² + (φₚ − φₛ)²)
```

where coordinates are in WGS84 decimal degrees.

### 4.2 Geometric distortion

The Euclidean distance in WGS84 degrees is not isotropic. At latitude φ:

```
1° longitude ≈ 111.32 × cos(φ) km
1° latitude  ≈ 111.32 km
```

At Belo Horizonte's latitude (φ ≈ −20°):

```
1° longitude ≈ 104.6 km
1° latitude  ≈ 111.3 km
aspect ratio ≈ 104.6 / 111.3 ≈ 0.940
```

The ~6% anisotropy means that two stops at equal true distances north and east
of a demand point will be assigned slightly different computed distances. For
stops separated by typical urban bus spacings (150–400 m ≈ 0.0013–0.0036°), the
absolute positional error introduced by the anisotropy is well under 1 metre —
negligible for stop-matching purposes.

A projection-aware distance (e.g. in SIRGAS 2000 UTM 23S, which is available in
the SIU data) would eliminate the anisotropy but is not necessary at this scale.

### 4.3 Candidate restriction

The candidate set for each demand point is restricted to the stops of the
**dominant shape** (Section 5) of the selected route and direction. This prevents
a demand point from being matched to a stop of a geometrically nearby but
operationally different route.

### 4.4 Known failure modes

| Scenario | Effect | Frequency |
|----------|--------|-----------|
| Shared physical stop (multiple routes, same pole) | Correct route restriction mitigates but does not eliminate the risk | Low — typical at major terminals |
| Parallel alignments with stops < 30 m apart | Nearest-stop heuristic may match to wrong stop | Very low in BH network |
| GPS drift in SIU coordinates | Demand point offset from true stop location | Occasional; usually < 50 m |
| Stop relocated between SIU survey and GTFS publication dates | Systematic mismatch for the affected stops | Rare; check if feeds are co-temporal |

The `Seq` field in the SIU data provides the sequential order of each boarding
point along the route and could be used in a future version to enforce
route-order matching, reducing residual ambiguity.

---

## 5. Representative Service Pattern Selection

A single route can have multiple **shapes** — distinct geometric alignments used
by different trips (e.g. a variant that serves an extra terminal or takes a
different access road). For the load profile calculation, a single representative
sequence of stops is required.

### 5.1 Dominant shape

SIG-Bus selects the shape that serves the largest number of trips for the route,
direction, and hour combination — the **dominant shape**:

```sql
SELECT shape_id, COUNT(*) AS trip_count
FROM trips
WHERE route_id = :rid AND direction_id = :did
GROUP BY shape_id
ORDER BY trip_count DESC
LIMIT 1
```

When a specific hour *h* is selected, the count is restricted to trips whose
**first-stop departure time** falls in hour *h*:

```sql
... AND CAST(SUBSTR(departure_time, 1, 2) AS INTEGER) = :h
```

### 5.2 Justification

The dominant shape captures the operational pattern that accounts for the most
service kilometres in the selected time window. Minor variants typically serve
a small fraction of trips and their stop-sequence differences (usually one or
two additional stops) have negligible impact on the overall load profile.

### 5.3 Limitation

Itinerary variations within the same shape — cases where different trips follow
the same `shape_id` but serve a different subset of stops — are not detected.
The stop sequence is read from a single representative trip of the dominant
shape. This is consistent with standard GTFS practice, where shape-level
variation is encoded in different `shape_id` values.

---

## 6. Hourly Decomposition

The SIU data provides boardings aggregated by calendar hour (columns `0`–`23`),
where column `h` contains all boardings at stops where the validator was activated
between `h:00:00` and `h:59:59`.

The GTFS `departure_time` for the first stop of a trip defines when that trip
*departs* from the origin terminal. SIG-Bus uses this as the proxy for **when the
trip is in service** at the early stops of the route: a trip departing at 07:15
contributes its passengers to the `07h` hour slot.

This approximation is valid for short-to-medium routes (travel time < 60 min).
For long routes where the travel time from the first to the last stop spans more
than one hour, a single departure-hour label understates the service coverage
in the later part of the route.

### Hour `00h` and overnight trips

GTFS allows `departure_time` values greater than `23:59:59` to represent trips
that span midnight without calendar discontinuity (e.g. `"24:15:00"` for a trip
departing at 00:15 on the following service day). The current implementation
extracts the hour as `CAST(SUBSTR(departure_time,1,2) AS INTEGER)`, which returns
`24` for these trips. Such trips are therefore **excluded** from `n_viagens` for
the `00h` slot. This is a known limitation with low practical impact, as
overnight service frequencies are typically very low.

---

## 7. Assumptions Summary

| # | Assumption | Effect if violated |
|---|-----------|-------------------|
| A1 | No alighting before the last stop | `passageiros_acum` overestimates true load; error grows toward the middle of the route |
| A2 | Dominant shape is representative of all trips in the hour | Load profile may miss stops served only by minority-variant trips |
| A3 | Nearest GTFS stop (Euclidean, within the route's stop set) corresponds to the SIU boarding point | Boardings may be assigned to the wrong stop on shared-platform corridors |
| A4 | Trip departure hour ≈ service hour for all stops | Underestimates `n_viagens` at the tail of long routes during hour transitions |
| A5 | SIU and GTFS data are co-temporal (same service period) | Route-stop mismatches if network changed between data collection dates |

---

## 8. Limitations and Their Practical Impact

### Overestimation of load (A1)

The boarding-only load profile systematically overestimates true loads on routes
with significant intra-route passenger exchange. An approximate correction is
possible if origin-destination (O-D) data are available:

```
L_corrected(i) = L̂(i) − Σⱼ₌₀ⁱ A_estimated(j)
```

where `A_estimated` can be derived from an O-D matrix or from survey data. In the
absence of such data, `passageiros_acum` should be interpreted as an upper bound
and used in comparisons between routes or time periods rather than as an absolute
measure of vehicle occupancy.

### Shape representativeness (A2)

On routes where a minority variant serves a significant terminal or activity
centre, the dominant shape may omit those stops entirely. Users should cross-check
the `shapes` layer in QGIS to verify that the highlighted alignment covers the
area of interest.

### Spatial join accuracy (A3)

See Section 4.4 for a full discussion. The practical recommendation is to inspect
`tramos_demanda` visually: unexpected zero-boarding segments near known terminals
are a reliable indicator of mismatched stops.

### Overnight service (A4 + `departure_time > 23:59`)

The `n_viagens = 0` case for `00h` when all overnight trips have
`departure_time ≥ "24:00:00"` causes the allocation to fall back to the daily
dominant shape with `n_viagens = 0`. The `passageiros_acum` values are still
computed from the SIU `0` column boardings, but the per-trip load estimate
(`passageiros_acum / n_viagens`) is undefined. Users working with `00h` data
should treat this column with caution.

---

## 9. References

- **GTFS reference:** Google LLC. (2006–present). *General Transit Feed
  Specification*. https://gtfs.org/documentation/schedule/reference/

- **Load profile fundamentals:** Vuchic, V. R. (2005). *Urban Transit: Operations,
  Planning, and Economics*. John Wiley & Sons. (Chapter 4: Line Capacity and
  Level of Service.)

- **Boarding-only estimation:** Furth, P. G., & Rahbee, A. B. (2000). Optimal bus
  stop spacing through dynamic programming and geographic modeling. *Transportation
  Research Record*, 1731(1), 15–22.

- **GTFS Loader (adapted reader):** CTU GeoForAll Lab. *QGIS GTFS Loader Plugin*.
  https://github.com/ctu-geoforall-lab/qgis-gtfs-plugin (GPL v2+).

- **BHTrans GTFS feed:** Empresa de Transporte e Trânsito de Belo Horizonte
  (BHTrans). *GTFS BH*, 2024 edition.
  https://dados.pbh.gov.br/ (open data portal, CC BY 4.0).
