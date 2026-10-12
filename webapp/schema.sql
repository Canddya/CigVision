PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS batches (
 id TEXT PRIMARY KEY, created_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'uploaded',
 model_name TEXT, model_sha256 TEXT, device TEXT, imgsz INTEGER NOT NULL DEFAULT 800
);
CREATE TABLE IF NOT EXISTS images (
 id TEXT PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
 ordinal INTEGER NOT NULL, filename TEXT NOT NULL, storage_name TEXT NOT NULL UNIQUE,
 width INTEGER NOT NULL, height INTEGER NOT NULL, size_bytes INTEGER NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending', class_name TEXT,
 confidence REAL CHECK(confidence BETWEEN 0 AND 1), elapsed_ms REAL, error TEXT,
 UNIQUE(batch_id, ordinal)
);
CREATE INDEX IF NOT EXISTS idx_batches_created ON batches(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_images_batch_status ON images(batch_id,status);
CREATE TABLE IF NOT EXISTS line_interface_config (
 id INTEGER PRIMARY KEY CHECK(id=1),
 enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
 line_name TEXT NOT NULL DEFAULT '1号包装线',
 device_code TEXT NOT NULL DEFAULT 'LINE-01',
 api_key_hash TEXT,
 updated_at TEXT NOT NULL
);
INSERT OR IGNORE INTO line_interface_config(id,enabled,line_name,device_code,updated_at)
 VALUES (1,0,'1号包装线','LINE-01',strftime('%Y-%m-%dT%H:%M:%fZ','now'));
CREATE TABLE IF NOT EXISTS line_events (
 id TEXT PRIMARY KEY,
 batch_id TEXT NOT NULL UNIQUE REFERENCES batches(id) ON DELETE CASCADE,
 device_code TEXT NOT NULL,
 client_image_id TEXT,
 received_at TEXT NOT NULL,
 UNIQUE(device_code,client_image_id)
);
CREATE INDEX IF NOT EXISTS idx_line_events_received ON line_events(received_at DESC);
CREATE VIEW IF NOT EXISTS batch_summary AS
 SELECT b.*, count(i.id) total,
 sum(CASE WHEN i.status='done' THEN 1 ELSE 0 END) completed,
 sum(CASE WHEN i.status='error' THEN 1 ELSE 0 END) failed,
 sum(CASE WHEN i.class_name='Right' THEN 1 ELSE 0 END) good,
 sum(CASE WHEN i.class_name='Wrong' THEN 1 ELSE 0 END) defect
 FROM batches b LEFT JOIN images i ON i.batch_id=b.id GROUP BY b.id;
