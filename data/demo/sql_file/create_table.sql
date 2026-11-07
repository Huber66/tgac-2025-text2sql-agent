CREATE TABLE IF NOT EXISTS demo_sessions (
    event_date STRING COMMENT 'Synthetic event date in YYYYMMDD format',
    player_id STRING COMMENT 'Synthetic player identifier',
    game_id STRING COMMENT 'Synthetic game identifier',
    play_minutes INT COMMENT 'Session duration in minutes'
)
ENGINE=OLAP
DUPLICATE KEY (event_date, player_id)
DISTRIBUTED BY HASH (player_id) BUCKETS 1
PROPERTIES ('replication_num' = '1');

CREATE TABLE IF NOT EXISTS demo_player_tags (
    snapshot_date STRING COMMENT 'Synthetic tag snapshot date',
    player_id STRING COMMENT 'Synthetic player identifier',
    player_segment STRING COMMENT 'returning or new'
)
ENGINE=OLAP
DUPLICATE KEY (snapshot_date, player_id)
DISTRIBUTED BY HASH (player_id) BUCKETS 1
PROPERTIES ('replication_num' = '1');
