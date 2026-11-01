-- Dev only: mock MES schema with seed data and a SELECT-only reader.
-- Dev-only credentials; must match MES_DB_URL in .env.
CREATE DATABASE IF NOT EXISTS mes CHARACTER SET utf8mb4;

CREATE USER IF NOT EXISTS 'mes_reader'@'%' IDENTIFIED BY 'readerpass';
GRANT SELECT ON mes.* TO 'mes_reader'@'%';

USE mes;

CREATE TABLE IF NOT EXISTS equipment (
  equipment_id  VARCHAR(64)  PRIMARY KEY,
  name          VARCHAR(255) NOT NULL,
  area          VARCHAR(64)  NOT NULL,
  type          VARCHAR(64)  NOT NULL,
  status        VARCHAR(32)  NOT NULL,
  status_since  DATETIME(3)  NOT NULL
);

CREATE TABLE IF NOT EXISTS sensor_tags (
  equipment_id  VARCHAR(64) NOT NULL,
  tag           VARCHAR(64) NOT NULL,
  unit          VARCHAR(16) NOT NULL,
  lo_limit      DOUBLE      NULL,
  hi_limit      DOUBLE      NULL,
  PRIMARY KEY (equipment_id, tag)
);

CREATE TABLE IF NOT EXISTS sensor_readings (
  equipment_id  VARCHAR(64) NOT NULL,
  tag           VARCHAR(64) NOT NULL,
  ts            DATETIME(3) NOT NULL,
  value         DOUBLE      NOT NULL,
  PRIMARY KEY (equipment_id, tag, ts)
);

CREATE TABLE IF NOT EXISTS alarms (
  alarm_id      BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  equipment_id  VARCHAR(64)  NOT NULL,
  code          VARCHAR(32)  NOT NULL,
  text          VARCHAR(255) NOT NULL,
  severity      TINYINT      NOT NULL,
  start_ts      DATETIME(3)  NOT NULL,
  end_ts        DATETIME(3)  NULL,
  KEY idx_equipment_start (equipment_id, start_ts)
);

INSERT IGNORE INTO equipment VALUES
  ('PRESS-01', 'Hydraulic press 1', 'Stamping', 'press', 'RUNNING', NOW(3) - INTERVAL 3 DAY),
  ('PRESS-04', 'Hydraulic press 4', 'Stamping', 'press', 'STOPPED', NOW(3) - INTERVAL 1 DAY),
  ('CNC-07',   'CNC mill 7',        'Machining', 'cnc',  'RUNNING', NOW(3) - INTERVAL 6 DAY),
  ('OVEN-02',  'Curing oven 2',     'Finishing', 'oven', 'IDLE',    NOW(3) - INTERVAL 2 HOUR);

INSERT IGNORE INTO sensor_tags VALUES
  ('PRESS-01', 'pressure',    'bar',  80, 220),
  ('PRESS-01', 'oil_temp',    'degC', 20,  65),
  ('PRESS-04', 'pressure',    'bar',  80, 220),
  ('PRESS-04', 'oil_temp',    'degC', 20,  65),
  ('CNC-07',   'spindle_rpm', 'rpm', 500, 12000),
  ('CNC-07',   'vibration',   'mm/s', 0,   7.1),
  ('OVEN-02',  'zone1_temp',  'degC', 150, 210),
  ('OVEN-02',  'zone2_temp',  'degC', 150, 210);

-- 7 days of 1-minute readings per tag (~80k rows). PRESS-04 oil_temp climbs past
-- its limit before the stop yesterday, so the agent has something to find.
SET SESSION cte_max_recursion_depth = 20000;
INSERT IGNORE INTO sensor_readings (equipment_id, tag, ts, value)
WITH RECURSIVE m(n) AS (SELECT 0 UNION ALL SELECT n + 1 FROM m WHERE n < 10079)
SELECT t.equipment_id, t.tag,
       NOW(3) - INTERVAL 7 DAY + INTERVAL m.n MINUTE,
       CASE
         WHEN t.equipment_id = 'PRESS-04' AND t.tag = 'oil_temp' AND m.n BETWEEN 7900 AND 8640
           THEN 50 + (m.n - 7900) * 0.03 + RAND() * 2
         ELSE (t.lo_limit + t.hi_limit) / 2 + (t.hi_limit - t.lo_limit) * (RAND() - 0.5) * 0.3
       END
FROM sensor_tags t CROSS JOIN m
WHERE NOT (t.equipment_id = 'PRESS-04' AND m.n > 8640);

INSERT INTO alarms (equipment_id, code, text, severity, start_ts, end_ts) VALUES
  ('PRESS-04', 'HYD-TEMP-HI', 'Hydraulic oil temperature high', 2,
     NOW(3) - INTERVAL 1 DAY - INTERVAL 40 MINUTE, NOW(3) - INTERVAL 1 DAY),
  ('PRESS-04', 'HYD-TRIP',    'Hydraulic pump tripped',         3,
     NOW(3) - INTERVAL 1 DAY, NULL),
  ('PRESS-01', 'DOOR-OPEN',   'Safety door opened',             1,
     NOW(3) - INTERVAL 2 DAY, NOW(3) - INTERVAL 2 DAY + INTERVAL 3 MINUTE),
  ('CNC-07',   'VIB-HI',      'Spindle vibration high',         2,
     NOW(3) - INTERVAL 5 DAY, NOW(3) - INTERVAL 5 DAY + INTERVAL 12 MINUTE),
  ('OVEN-02',  'ZONE2-LO',    'Zone 2 below setpoint',          1,
     NOW(3) - INTERVAL 3 HOUR, NOW(3) - INTERVAL 2 HOUR);

ANALYZE TABLE equipment, sensor_tags, sensor_readings, alarms;
