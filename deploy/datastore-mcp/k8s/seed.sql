-- Demo analytic data store for the AI Workspace MCP demo.
-- UNCLASSIFIED. Entirely synthetic. Fictional places, organizations, and
-- events. Do NOT load real or sensitive data here.
--
-- Loaded by the postgres image entrypoint (mounted into
-- /docker-entrypoint-initdb.d). Creates a least-privilege read-only role
-- (mcp_ro) that the datastore MCP server connects as.

BEGIN;

CREATE TABLE regions (
    id          serial PRIMARY KEY,
    name        text NOT NULL UNIQUE,
    description text NOT NULL
);

CREATE TABLE entities (
    id         serial PRIMARY KEY,
    name       text NOT NULL,
    -- kind is one of: organization, infrastructure, program.
    kind       text NOT NULL,
    region     text NOT NULL,
    first_seen date NOT NULL,
    notes      text NOT NULL
);

CREATE TABLE reports (
    id          serial PRIMARY KEY,
    report_date date NOT NULL,
    region      text NOT NULL,
    -- topic is one of: logistics, infrastructure, public-health, weather,
    -- supply-chain, economic.
    topic       text NOT NULL,
    -- source_type is one of: open-source, press, sensor, partner.
    source_type text NOT NULL,
    -- confidence is one of: low, moderate, high.
    confidence  text NOT NULL,
    title       text NOT NULL,
    summary     text NOT NULL
);

CREATE TABLE report_entities (
    report_id integer NOT NULL REFERENCES reports(id),
    entity_id integer NOT NULL REFERENCES entities(id),
    PRIMARY KEY (report_id, entity_id)
);

INSERT INTO regions (name, description) VALUES
 ('Northland',   'Northern continental sector. Cold climate, rail-dependent logistics.'),
 ('Eastvale',    'Eastern river valley. Agricultural and light manufacturing.'),
 ('Sablestone',  'Arid plateau. Mining and energy infrastructure.'),
 ('Port Meridian','Coastal trade hub. Container shipping and fishing.');

INSERT INTO entities (name, kind, region, first_seen, notes) VALUES
 ('Northland Rail Authority', 'organization',  'Northland',    '2024-02-11', 'Operates the northern freight rail network.'),
 ('Meridian Port Trust',      'organization',  'Port Meridian','2023-11-03', 'Manages container terminals at Port Meridian.'),
 ('Eastvale Grain Cooperative','organization', 'Eastvale',     '2024-05-19', 'Regional grain storage and distribution.'),
 ('Sablestone Power Grid',    'infrastructure','Sablestone',   '2023-09-27', 'High-voltage transmission across the plateau.'),
 ('North Bridge Crossing',    'infrastructure','Northland',    '2024-01-08', 'Primary rail bridge over the North river.'),
 ('Meridian Desalination',    'infrastructure','Port Meridian','2024-03-22', 'Coastal freshwater supply for the port city.'),
 ('Clearwater Health Program','program',       'Eastvale',     '2024-06-30', 'Public-health surveillance pilot in Eastvale.'),
 ('Plateau Solar Initiative', 'program',       'Sablestone',   '2024-04-14', 'Solar capacity expansion on the plateau.'),
 ('Harbor Cold Chain',        'infrastructure','Port Meridian','2024-02-02', 'Refrigerated storage at the fishing harbor.'),
 ('Northland Snowfleet',      'organization',  'Northland',    '2024-12-01', 'Seasonal road-clearing fleet operator.'),
 ('Eastvale Mill Works',      'organization',  'Eastvale',     '2023-10-17', 'Light manufacturing and milling.'),
 ('Sablestone Water Board',   'organization',  'Sablestone',   '2024-07-05', 'Manages scarce water allocation.');

INSERT INTO reports (report_date, region, topic, source_type, confidence, title, summary) VALUES
 ('2025-01-12','Northland','infrastructure','open-source','high',   'North Bridge maintenance window announced','Northland Rail Authority scheduled a maintenance closure of North Bridge Crossing, rerouting freight for two weeks.'),
 ('2025-01-20','Northland','weather','sensor','high',               'Severe snow disrupts northern rail','Heavy snowfall reduced rail throughput; Northland Snowfleet deployed across primary corridors.'),
 ('2025-02-03','Eastvale','supply-chain','open-source','moderate',  'Grain shipments delayed at Eastvale','Eastvale Grain Cooperative reported backlog due to rail rerouting from the north.'),
 ('2025-02-15','Port Meridian','logistics','press','moderate',      'Container volumes rise at Port Meridian','Meridian Port Trust noted a seasonal increase in container throughput.'),
 ('2025-02-28','Sablestone','infrastructure','partner','high',      'Plateau grid stability advisory','Sablestone Power Grid issued a stability advisory during peak demand.'),
 ('2025-03-05','Eastvale','public-health','open-source','low',      'Clearwater pilot expands sampling','Clearwater Health Program widened water-quality sampling across Eastvale.'),
 ('2025-03-18','Sablestone','economic','press','moderate',          'Solar tender opens on the plateau','Plateau Solar Initiative opened a procurement tender for new capacity.'),
 ('2025-03-25','Port Meridian','infrastructure','sensor','high',    'Desalination output dips','Meridian Desalination reported reduced output during a maintenance cycle.'),
 ('2025-04-02','Northland','logistics','open-source','high',        'Freight reroute normalizes','Northland Rail Authority restored normal routing after North Bridge work completed.'),
 ('2025-04-14','Eastvale','supply-chain','press','moderate',        'Mill output steady despite delays','Eastvale Mill Works maintained output using buffer stocks.'),
 ('2025-04-22','Sablestone','public-health','partner','low',        'Heat advisory affects water demand','Sablestone Water Board flagged elevated demand during an early heat wave.'),
 ('2025-05-01','Port Meridian','supply-chain','open-source','high', 'Cold-chain capacity expanded','Harbor Cold Chain added refrigerated capacity ahead of the fishing season.'),
 ('2025-05-10','Northland','infrastructure','sensor','moderate',    'Bridge sensors flag vibration','North Bridge Crossing sensors recorded elevated vibration; inspection scheduled.'),
 ('2025-05-19','Eastvale','economic','press','moderate',            'Cooperative invests in storage','Eastvale Grain Cooperative announced new silo capacity.'),
 ('2025-05-27','Sablestone','infrastructure','open-source','high',  'Solar capacity comes online','Plateau Solar Initiative connected its first new array to the grid.'),
 ('2025-06-03','Port Meridian','weather','sensor','high',           'Storm surge watch at the harbor','Sensors warned of an incoming storm surge affecting harbor operations.'),
 ('2025-06-11','Northland','supply-chain','open-source','moderate', 'Seasonal stockpiling begins','Operators began winter stockpiling earlier than usual across Northland.'),
 ('2025-06-18','Eastvale','public-health','partner','moderate',     'Clearwater detects seasonal pattern','Clearwater Health Program reported a recurring seasonal water-quality pattern.'),
 ('2025-06-25','Sablestone','economic','press','low',               'Water pricing under review','Sablestone Water Board opened a review of allocation pricing.'),
 ('2025-07-02','Port Meridian','logistics','open-source','high',    'Port automation milestone','Meridian Port Trust completed a terminal automation milestone.'),
 ('2025-07-09','Northland','weather','sensor','moderate',           'Late-season thaw raises river levels','A late thaw raised North river levels near the bridge crossing.'),
 ('2025-07-16','Eastvale','supply-chain','open-source','high',      'Grain export window opens','Eastvale Grain Cooperative began seasonal exports through Port Meridian.'),
 ('2025-07-23','Sablestone','infrastructure','partner','moderate',  'Grid maintenance scheduled','Sablestone Power Grid scheduled maintenance on a key transmission line.'),
 ('2025-07-30','Port Meridian','public-health','press','low',       'Harbor water testing routine','Routine harbor water testing reported nominal results.'),
 ('2025-08-06','Northland','infrastructure','open-source','high',   'Bridge inspection clears crossing','North Bridge Crossing passed inspection after vibration alerts.');

INSERT INTO report_entities (report_id, entity_id) VALUES
 (1,1),(1,5),(2,1),(2,10),(3,3),(3,1),(4,2),(5,4),(6,7),(7,8),
 (8,6),(9,1),(9,5),(10,11),(11,12),(12,9),(13,5),(14,3),(15,8),(16,2),
 (17,1),(18,7),(19,12),(20,2),(21,5),(22,3),(22,2),(23,4),(24,2),(25,5);

-- Least-privilege read-only role used by the datastore MCP server.
DO $$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'mcp_ro') THEN
      CREATE ROLE mcp_ro LOGIN PASSWORD 'mcp_ro_demo_pw';
   END IF;
END
$$;

ALTER ROLE mcp_ro SET default_transaction_read_only = on;
ALTER ROLE mcp_ro SET statement_timeout = '8s';
GRANT CONNECT ON DATABASE demo TO mcp_ro;
GRANT USAGE ON SCHEMA public TO mcp_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO mcp_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO mcp_ro;

COMMIT;
