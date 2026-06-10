#!/usr/bin/env python3
"""Deterministic synthetic-data generator for the demo analytic data store.

Emits SQL that APPENDS to the committed seed (regions 1-4, entities 1-12,
reports 1-25 already exist). UNCLASSIFIED, entirely fictional. Plants three
analyzable patterns:
  A) Northland escalation: rising report volume + confidence on the rail/bridge
     corridor through 2025, culminating in a late-2025 incident.
  B) Connector entity (id 13, Transcontinental Freight Consortium) referenced
     across the most regions and the most reports.
  C) Anomalies: an out-of-region high-confidence partner link, and a sensor
     spike month in an otherwise quiet region.
Output: stdout = SQL additions.
"""
import random

random.seed(1742)

def q(s):
    return "'" + s.replace("'", "''") + "'"

REGIONS_NEW = [
    (5, "Highmoor", "Inland highland region. Hydropower, alpine roads, sparse sensors."),
    (6, "Calder Basin", "Low-lying river delta and wetlands. Barge traffic and flood control."),
]
REGION_NAMES = ["Northland", "Eastvale", "Sablestone", "Port Meridian", "Highmoor", "Calder Basin"]

# Existing entity ids by region (for linking).
EXISTING = {
    "Northland": [1, 5, 10], "Eastvale": [3, 7, 11], "Sablestone": [4, 8, 12],
    "Port Meridian": [2, 6, 9], "Highmoor": [], "Calder Basin": [],
}

# New entities (id, name, kind, region, first_seen, notes). id 13 = connector.
NEW_ENTITIES = [
    (13, "Transcontinental Freight Consortium", "organization", "Port Meridian", "2023-08-12",
     "Multi-regional freight broker coordinating rail, road, and barge movements."),
    (14, "Northland Signal Network", "infrastructure", "Northland", "2024-01-15", "Rail signaling and dispatch control for the northern corridor."),
    (15, "North River Locks", "infrastructure", "Northland", "2023-12-02", "Navigation locks upstream of the North bridge crossing."),
    (16, "Northland Fuel Depot", "infrastructure", "Northland", "2024-03-09", "Strategic diesel reserve for rail and road fleets."),
    (17, "Borealis Mining Group", "organization", "Northland", "2023-07-21", "Extracts ore shipped south by rail."),
    (18, "Eastvale Cannery Union", "organization", "Eastvale", "2024-02-28", "Seasonal food processing cooperative."),
    (19, "Eastvale Irrigation Board", "infrastructure", "Eastvale", "2023-11-19", "Canal network for valley agriculture."),
    (20, "Greenline Biofuel Program", "program", "Eastvale", "2024-08-04", "Pilot converting crop residue to fuel."),
    (21, "Eastvale Rail Spur", "infrastructure", "Eastvale", "2024-04-17", "Branch line connecting the valley to the northern trunk."),
    (22, "Sablestone Lithium Works", "organization", "Sablestone", "2023-10-08", "Brine extraction and processing on the plateau."),
    (23, "Plateau Wind Array", "infrastructure", "Sablestone", "2024-05-30", "Wind generation feeding the plateau grid."),
    (24, "Sablestone Rail Terminal", "infrastructure", "Sablestone", "2024-02-11", "Bulk mineral loading terminal."),
    (25, "Arid Zone Water Pact", "program", "Sablestone", "2024-09-22", "Multi-board water-sharing agreement."),
    (26, "Meridian Container Lines", "organization", "Port Meridian", "2023-09-14", "Container shipping operator at the port."),
    (27, "Harbor Pilot Service", "organization", "Port Meridian", "2024-01-30", "Marine pilotage for harbor approaches."),
    (28, "Meridian Customs Authority", "organization", "Port Meridian", "2023-11-25", "Port-of-entry inspection and clearance."),
    (29, "Seawall Defense Works", "infrastructure", "Port Meridian", "2024-06-19", "Storm-surge barriers protecting the harbor."),
    (30, "Highmoor Hydro Station", "infrastructure", "Highmoor", "2023-08-30", "Mountain reservoir hydroelectric plant."),
    (31, "Highmoor Pass Authority", "organization", "Highmoor", "2024-03-05", "Maintains the alpine road passes."),
    (32, "Summit Telemetry Network", "infrastructure", "Highmoor", "2024-07-12", "Remote sensor network across the highlands."),
    (33, "Highmoor Forestry Board", "organization", "Highmoor", "2023-10-27", "Manages timber and wildfire response."),
    (34, "Alpine Relief Program", "program", "Highmoor", "2024-11-08", "Winter resupply for isolated settlements."),
    (35, "Calder Barge Cooperative", "organization", "Calder Basin", "2023-09-03", "River barge freight in the delta."),
    (36, "Calder Flood Control", "infrastructure", "Calder Basin", "2024-02-20", "Levees and pumping stations across the basin."),
    (37, "Delta Fisheries Board", "organization", "Calder Basin", "2024-04-29", "Manages wetland fisheries."),
    (38, "Calder Wetland Survey", "program", "Calder Basin", "2024-10-14", "Ecological monitoring of the delta."),
    (39, "Basin Grain Terminal", "infrastructure", "Calder Basin", "2024-01-22", "Transships grain from rail to barge."),
    (40, "Northland Cold Storage", "infrastructure", "Northland", "2024-05-06", "Frozen freight buffer near the rail yard."),
    (41, "Eastvale Power Co-op", "organization", "Eastvale", "2023-12-15", "Rural electric distribution."),
    (42, "Sablestone Haul Roads", "infrastructure", "Sablestone", "2024-03-28", "Heavy-vehicle mining roads."),
    (43, "Meridian Bunker Supply", "organization", "Port Meridian", "2024-07-01", "Marine fuel bunkering at the port."),
    (44, "Highmoor Avalanche Watch", "program", "Highmoor", "2024-12-09", "Snowpack and avalanche advisories."),
    (45, "Calder Levee Authority", "organization", "Calder Basin", "2023-11-11", "Operates the basin levee system."),
    (46, "Northland Border Yard", "infrastructure", "Northland", "2024-06-25", "Interchange yard at the northern frontier."),
    (47, "Eastvale Seed Bank", "program", "Eastvale", "2024-09-17", "Regional crop seed reserve."),
    (48, "Sablestone Solar Storage", "infrastructure", "Sablestone", "2024-08-21", "Grid battery paired with the solar initiative."),
    (49, "Meridian Dredging Service", "organization", "Port Meridian", "2024-02-05", "Keeps harbor channels navigable."),
    (50, "Highmoor Microgrid", "infrastructure", "Highmoor", "2024-10-30", "Islanded grid for remote valleys."),
    (51, "Calder Pump Station 7", "infrastructure", "Calder Basin", "2024-05-13", "Key drainage pump for the lower basin."),
    (52, "Continental Logistics Audit", "program", "Port Meridian", "2025-01-20", "Independent review of cross-regional freight flows."),
]
ENT_BY_REGION = {r: list(EXISTING[r]) for r in REGION_NAMES}
for eid, name, kind, region, fs, notes in NEW_ENTITIES:
    ENT_BY_REGION[region].append(eid)

CONNECTOR = 13
NORTH_RAIL = [1, 5, 10, 14, 15, 16, 17, 46]  # Northland rail/bridge cluster

TOPICS = ["logistics", "infrastructure", "public-health", "weather", "supply-chain", "economic"]
SOURCES = ["open-source", "press", "sensor", "partner"]
CONF = ["low", "moderate", "high"]

TITLE = {
    "logistics": ["{r} freight schedule revised", "Throughput shifts at {r}", "{r} routing update issued"],
    "infrastructure": ["{r} maintenance window set", "{r} asset condition advisory", "{r} capacity change reported"],
    "public-health": ["{r} sampling results posted", "{r} health surveillance update", "{r} water testing summary"],
    "weather": ["{r} weather impact noted", "Storm activity over {r}", "{r} seasonal advisory issued"],
    "supply-chain": ["{r} stock levels reported", "{r} supply backlog noted", "{r} export window update"],
    "economic": ["{r} tender opened", "{r} pricing under review", "{r} investment announced"],
}
SUMM = {
    "logistics": "Operators in {r} adjusted movements; {e} cited in the coordination.",
    "infrastructure": "Condition of {e} in {r} prompted an operational advisory.",
    "public-health": "Sampling across {r} updated baselines; {e} contributed data.",
    "weather": "Weather over {r} affected operations near {e}.",
    "supply-chain": "Supply flows through {r} shifted; {e} adjusted buffers.",
    "economic": "An economic action in {r} involved {e}.",
}

ENT_NAME = {e[0]: e[1] for e in NEW_ENTITIES}
ENT_NAME.update({1: "Northland Rail Authority", 2: "Meridian Port Trust", 3: "Eastvale Grain Cooperative",
    4: "Sablestone Power Grid", 5: "North Bridge Crossing", 6: "Meridian Desalination",
    7: "Clearwater Health Program", 8: "Plateau Solar Initiative", 9: "Harbor Cold Chain",
    10: "Northland Snowfleet", 11: "Eastvale Mill Works", 12: "Sablestone Water Board"})

months = [(y, m) for y in (2024, 2025) for m in range(1, 13)]

reports = []   # (id, date, region, topic, source, conf, title, summary)
links = []     # (report_id, entity_id)
rid = 26

def day(y, m):
    return f"{y}-{m:02d}-{random.randint(1,28):02d}"

def add(region, topic, source, conf, ents, y, m, title=None, summary=None):
    global rid
    e0 = ents[0]
    t = title or random.choice(TITLE[topic]).format(r=region)
    s = summary or SUMM[topic].format(r=region, e=ENT_NAME.get(e0, "local operators"))
    reports.append((rid, day(y, m), region, topic, source, conf, t, s))
    for e in ents:
        links.append((rid, e))
    rid += 1

# Baseline volume per region per month (noise), with Northland escalating.
north_q = {2024: [2, 2, 2, 3], 2025: [3, 4, 6, 8]}  # reports/quarter for Northland
for (y, m) in months:
    quarter = (m - 1) // 3
    for region in REGION_NAMES:
        if region == "Northland":
            base = 0  # handled separately below
        else:
            base = random.choice([1, 1, 2])
        for _ in range(base):
            topic = random.choice(TOPICS)
            source = random.choice(SOURCES)
            conf = random.choices(CONF, weights=[2, 3, 2])[0]
            pool = ENT_BY_REGION[region] or [CONNECTOR]
            ents = random.sample(pool, min(len(pool), random.choice([1, 1, 2])))
            # Connector entity threads through logistics/supply-chain across regions.
            if topic in ("logistics", "supply-chain") and random.random() < 0.5:
                if CONNECTOR not in ents:
                    ents = [CONNECTOR] + ents
            add(region, topic, source, conf, ents, y, m)

# A) Northland escalation: rail/bridge corridor, rising volume + confidence.
north_titles = [
    ("infrastructure", "North Bridge vibration trend worsens", "Repeated sensor alerts on North Bridge Crossing show a worsening vibration trend; rail loads under review."),
    ("infrastructure", "Load limits imposed on North Bridge", "Northland Rail Authority imposed axle-load limits on North Bridge Crossing pending structural assessment."),
    ("logistics", "Northern freight rerouted around bridge", "Freight via the Transcontinental Freight Consortium was rerouted as North Bridge capacity fell."),
    ("weather", "Storms accelerate northern corridor stress", "Severe weather compounded structural stress on the northern rail corridor."),
    ("infrastructure", "Partial closure of North Bridge Crossing", "A partial closure of North Bridge Crossing was ordered after inspection findings."),
    ("infrastructure", "North Bridge Crossing incident reported", "A structural failure event closed North Bridge Crossing; emergency rerouting via Sablestone and barge began."),
]
ni = 0
for y in (2024, 2025):
    for quarter in range(4):
        cnt = north_q[y][quarter]
        m = quarter * 3 + random.randint(1, 3)
        for k in range(cnt):
            late = (y == 2025 and quarter >= 2)
            conf = "high" if late else random.choice(["moderate", "high"])
            if y == 2025 and quarter == 3 and ni < len(north_titles):
                topic, t, s = north_titles[min(ni + 2, len(north_titles) - 1)]
            elif late and ni < len(north_titles):
                topic, t, s = north_titles[ni % len(north_titles)]
            else:
                topic = random.choice(["infrastructure", "weather", "logistics"])
                t = random.choice(TITLE[topic]).format(r="Northland")
                s = SUMM[topic].format(r="Northland", e="North Bridge Crossing")
            ni += 1
            ents = random.sample(NORTH_RAIL, random.choice([1, 2]))
            if topic == "logistics":
                ents = [CONNECTOR] + ents
            add("Northland", topic, random.choice(["sensor", "open-source", "partner", "press"]), conf, ents, y, m, t, s)
# Culminating incident, Dec 2025, high confidence, multi-source corroboration.
add("Northland", "infrastructure", "sensor", "high", [5, 1, 14], 2025, 12, north_titles[5][1], north_titles[5][2])
add("Northland", "logistics", "partner", "high", [CONNECTOR, 5], 2025, 12,
    "Freight network absorbs North Bridge outage", "The Transcontinental Freight Consortium activated barge and plateau-rail detours after the North Bridge incident.")

# B) Ensure connector entity spans >=5 regions and leads on report count.
for region in REGION_NAMES:
    for _ in range(4):
        y = random.choice([2024, 2025]); m = random.randint(1, 12)
        topic = random.choice(["logistics", "supply-chain"])
        ents = [CONNECTOR] + random.sample(ENT_BY_REGION[region] or [CONNECTOR], 1)
        add(region, topic, random.choice(SOURCES), random.choice(["moderate", "high"]), ents, y, m,
            f"Consortium coordinates {region} corridor",
            f"The Transcontinental Freight Consortium coordinated multi-modal freight through {region}.")

# C) Anomalies.
# C1: out-of-region high-confidence partner link of an Eastvale health program to Sablestone.
add("Sablestone", "public-health", "partner", "high", [7, 25], 2025, 7,
    "Cross-region health task force convenes", "Unusually, the Eastvale Clearwater Health Program was tasked into Sablestone under the Arid Zone Water Pact during a heat emergency.")
# C2: sensor spike in normally quiet Highmoor in Sep 2025.
for _ in range(6):
    add("Highmoor", random.choice(["weather", "infrastructure"]), "sensor", random.choice(["moderate", "high"]),
        random.sample([30, 31, 32, 44, 50], 2), 2025, 9,
        "Highmoor sensor cluster flags anomaly", "A dense burst of Summit Telemetry Network readings flagged unusual highland activity.")

# ---- emit SQL ----
out = []
out.append("-- ===== Expanded synthetic analysis dataset (appended) =====")
out.append("-- UNCLASSIFIED, fictional. Generated deterministically (gen_seed.py, seed 1742).")
out.append("INSERT INTO regions (id, name, description) VALUES")
out.append(",\n".join(f" ({i}, {q(n)}, {q(d)})" for i, n, d in REGIONS_NEW) + ";")
out.append("")
out.append("INSERT INTO entities (id, name, kind, region, first_seen, notes) VALUES")
out.append(",\n".join(f" ({e[0]}, {q(e[1])}, {q(e[2])}, {q(e[3])}, '{e[4]}', {q(e[5])})" for e in NEW_ENTITIES) + ";")
out.append("")
out.append("INSERT INTO reports (id, report_date, region, topic, source_type, confidence, title, summary) VALUES")
out.append(",\n".join(f" ({r[0]}, '{r[1]}', {q(r[2])}, {q(r[3])}, {q(r[4])}, {q(r[5])}, {q(r[6])}, {q(r[7])})" for r in reports) + ";")
out.append("")
# de-dup links (report_id, entity_id) unique
seen = set(); uniq = []
for a, b in links:
    if (a, b) not in seen:
        seen.add((a, b)); uniq.append((a, b))
out.append("INSERT INTO report_entities (report_id, entity_id) VALUES")
out.append(",\n".join(f" ({a},{b})" for a, b in uniq) + ";")
out.append("")
out.append("SELECT setval('regions_id_seq', (SELECT max(id) FROM regions));")
out.append("SELECT setval('entities_id_seq', (SELECT max(id) FROM entities));")
out.append("SELECT setval('reports_id_seq', (SELECT max(id) FROM reports));")
print("\n".join(out))

import sys
sys.stderr.write(f"regions+={len(REGIONS_NEW)} entities+={len(NEW_ENTITIES)} reports+={len(reports)} links+={len(uniq)}\n")

# Regenerate + splice into seed.sql (the appended rows live between the existing
# data and the mcp_ro role block):
#   python3 deploy/datastore-mcp/gen_seed.py > /tmp/additions.sql
#   awk '/-- Least-privilege read-only role/{while((getline l < "/tmp/additions.sql")>0) print l; print ""} {print}' \
#       deploy/datastore-mcp/k8s/seed.sql > /tmp/seed.new && mv /tmp/seed.new deploy/datastore-mcp/k8s/seed.sql
# Validate by loading into a throwaway postgres before committing.
