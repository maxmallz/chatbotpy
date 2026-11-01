-- chatbotpy schema (read/write). ADK creates sessions/events/app_states/user_states itself.
-- Dev-only credentials; must match APP_DB_URL in .env.
CREATE DATABASE IF NOT EXISTS chatbotpy CHARACTER SET utf8mb4;

CREATE USER IF NOT EXISTS 'chatbotpy'@'%' IDENTIFIED BY 'chatbotpypass';
GRANT ALL PRIVILEGES ON chatbotpy.* TO 'chatbotpy'@'%';

USE chatbotpy;

CREATE TABLE IF NOT EXISTS host_apps (
  id              VARCHAR(64)  PRIMARY KEY,
  name            VARCHAR(255) NOT NULL,
  allowed_origin  VARCHAR(255) NULL,
  enabled         BOOLEAN      NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS analysis_embeddings (
  id            BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  project_id    VARCHAR(64)   NOT NULL,
  equipment_id  VARCHAR(64)   NOT NULL,
  period_start  DATETIME(3)   NOT NULL,
  period_end    DATETIME(3)   NOT NULL,
  content       TEXT          NOT NULL,
  content_sha   CHAR(64)      NOT NULL,
  embedding     VECTOR(768)   NOT NULL,        -- = EMBED_DIM
  embed_model   VARCHAR(64)   NOT NULL,
  session_id    VARCHAR(128)  NULL,
  created_at    TIMESTAMP(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  UNIQUE KEY uq_model_sha (embed_model, content_sha),
  KEY idx_project_equipment_period (project_id, equipment_id, period_start)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO host_apps (id, name, allowed_origin) VALUES
  ('oee-dashboard', 'OEE Dashboard', 'http://localhost:5173');

ANALYZE TABLE host_apps, analysis_embeddings;
