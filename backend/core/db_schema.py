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

-- Findarr per-unit retry state. ``attempts`` counts consecutive searches that
-- found nothing; ``next_eligible_at`` is when the unit may be searched again
-- (NULL only for rows written before the backoff existed: eligible at once).
CREATE TABLE IF NOT EXISTS findarr_processed (
    app TEXT NOT NULL CHECK(app IN ('sonarr','radarr')),
    mode TEXT NOT NULL CHECK(mode IN ('missing','upgrade')),
    item_id TEXT NOT NULL,
    title TEXT,
    processed_at TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_eligible_at TEXT,
    PRIMARY KEY (app, mode, item_id)
);
CREATE INDEX IF NOT EXISTS idx_findarr_processed_at
    ON findarr_processed(processed_at);

-- One row per Findarr search command sent to an Arr. Drives the hourly cap
-- (independent of the clearable history log) and the follow-up lookup of each
-- command's outcome; ``history_id`` links back to the History row to update.
CREATE TABLE IF NOT EXISTS findarr_searches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    app TEXT NOT NULL CHECK(app IN ('sonarr','radarr')),
    mode TEXT NOT NULL CHECK(mode IN ('missing','upgrade')),
    item_id TEXT NOT NULL,
    command_id INTEGER,
    history_id INTEGER,
    outcome TEXT NOT NULL
        CHECK(outcome IN ('pending','grabbed','not_found','failed','unknown'))
);
CREATE INDEX IF NOT EXISTS idx_findarr_searches_ts
    ON findarr_searches(ts);
CREATE INDEX IF NOT EXISTS idx_findarr_searches_pending
    ON findarr_searches(app, outcome);

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

CREATE TABLE IF NOT EXISTS app_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Languagarr replacement-search queue, keyed by the Sonarr episode file whose
-- audio is non-compliant. ``episode_ids`` is a JSON array of Sonarr episode ids.
CREATE TABLE IF NOT EXISTS languagarr_queue (
    episode_file_id INTEGER PRIMARY KEY,
    series_id INTEGER NOT NULL,
    series_slug TEXT,
    title TEXT NOT NULL,
    episode_ids TEXT NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending','searched','failed')),
    queued_at TEXT NOT NULL,
    searched_at TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT
);

CREATE INDEX IF NOT EXISTS idx_languagarr_queue_status
    ON languagarr_queue(status, queued_at);

-- Dashboard daily statistics: one value per metric per local day, kept for
-- DASHBOARD_SNAPSHOT_RETENTION_DAYS (core.db_dashboard).
CREATE TABLE IF NOT EXISTS dashboard_snapshots (
    day TEXT NOT NULL,
    metric TEXT NOT NULL,
    value REAL NOT NULL,
    recorded_at TEXT NOT NULL,
    PRIMARY KEY (day, metric)
);

CREATE INDEX IF NOT EXISTS idx_dashboard_snapshots_metric_day
    ON dashboard_snapshots(metric, day);

-- Cleanarr strike ledger: one row per struck Sonarr/Radarr queue download.
-- ``would_remove_logged`` stops a dry run from logging the same would-remove
-- entry on every run (core.db_cleanarr).
CREATE TABLE IF NOT EXISTS cleanarr_strikes (
    app TEXT NOT NULL CHECK(app IN ('sonarr','radarr')),
    download_id TEXT NOT NULL,
    queue_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    reason TEXT NOT NULL CHECK(reason IN ('failed_import','failed_download')),
    message TEXT NOT NULL DEFAULT '',
    strikes INTEGER NOT NULL DEFAULT 0,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    would_remove_logged INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (app, download_id)
);

-- Cleanarr audit log shown on the History tab; pruned after
-- CLEANARR_HISTORY_RETENTION_DAYS (core.db_cleanarr).
CREATE TABLE IF NOT EXISTS cleanarr_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    app TEXT NOT NULL CHECK(app IN ('sonarr','radarr','sabnzbd','system')),
    action TEXT NOT NULL,
    download_id TEXT,
    title TEXT,
    detail TEXT NOT NULL DEFAULT '',
    dry_run INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_cleanarr_history_ts
    ON cleanarr_history(ts);

CREATE TABLE IF NOT EXISTS cleanarr_run_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Cleanarr quarantine provenance: the category folder (NULL for the completed
-- folder itself) and category names of each quarantined entry, keyed by its
-- quarantined name, so the ignore lists still protect it at purge time
-- (core.db_cleanarr).
CREATE TABLE IF NOT EXISTS cleanarr_quarantine (
    name TEXT PRIMARY KEY,
    container TEXT,
    categories TEXT NOT NULL DEFAULT '[]',
    quarantined_at TEXT NOT NULL
);
"""
