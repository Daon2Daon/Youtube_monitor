-- SQLite: youtube_settings (부트스트랩 설정)
CREATE TABLE IF NOT EXISTS youtube_settings (
    setting_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    category     TEXT    NOT NULL,
    key          TEXT    NOT NULL,
    value        TEXT,
    value_enc    BLOB,
    value_type   TEXT    DEFAULT 'string',
    is_secret    INTEGER DEFAULT 0,
    description  TEXT,
    updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (category, key)
);
