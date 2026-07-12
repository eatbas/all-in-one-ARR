"""SQLite schema definitions for :mod:`core.db`."""

INIT_SQL = """
CREATE TABLE IF NOT EXISTS items (
    trakt_id INTEGER NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('movie','show')),
    title TEXT,
    year INTEGER,
    tmdb INTEGER,
    tvdb INTEGER,
    imdb TEXT,
    list_id TEXT NOT NULL,
    seer_request_id INTEGER,
    status TEXT NOT NULL
        CHECK(status IN ('synced','requested','available','removed')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (trakt_id, list_id)
);
CREATE INDEX IF NOT EXISTS idx_items_tmdb ON items(tmdb);
CREATE INDEX IF NOT EXISTS idx_items_tvdb ON items(tvdb);
CREATE INDEX IF NOT EXISTS idx_items_status ON items(status);

CREATE TABLE IF NOT EXISTS activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_activity_ts ON activity(ts);

CREATE TABLE IF NOT EXISTS list_state (
    list_id TEXT PRIMARY KEY,
    last_synced_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS findarr_processed (
    app TEXT NOT NULL CHECK(app IN ('sonarr','radarr')),
    mode TEXT NOT NULL CHECK(mode IN ('missing','upgrade')),
    item_id TEXT NOT NULL,
    title TEXT,
    processed_at TEXT NOT NULL,
    PRIMARY KEY (app, mode, item_id)
);
CREATE INDEX IF NOT EXISTS idx_findarr_processed_at
    ON findarr_processed(processed_at);

CREATE TABLE IF NOT EXISTS findarr_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    app TEXT NOT NULL CHECK(app IN ('sonarr','radarr')),
    mode TEXT NOT NULL CHECK(mode IN ('missing','upgrade','system')),
    item_id TEXT,
    title TEXT,
    status TEXT NOT NULL,
    detail TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_findarr_history_ts
    ON findarr_history(ts);
CREATE INDEX IF NOT EXISTS idx_findarr_history_app
    ON findarr_history(app);

CREATE TABLE IF NOT EXISTS findarr_run_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS findarr_totals (
    app TEXT NOT NULL CHECK(app IN ('sonarr','radarr')),
    mode TEXT NOT NULL CHECK(mode IN ('missing','upgrade')),
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (app, mode)
);

CREATE TABLE IF NOT EXISTS trending_feeds (
    source TEXT NOT NULL,
    media TEXT NOT NULL,
    category TEXT NOT NULL,
    window TEXT NOT NULL,
    rows_json TEXT NOT NULL,
    synced_at TEXT NOT NULL,
    PRIMARY KEY (source, media, category, window)
);

CREATE TABLE IF NOT EXISTS trending_cycle_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trending_ratings (
    key TEXT PRIMARY KEY,
    imdb_rating REAL,
    imdb_votes INTEGER,
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS omdb_usage (
    day TEXT PRIMARY KEY,
    count INTEGER NOT NULL
);
"""
