-- Users table
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    password TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL
);

-- Locations table (with lat/lon included)
CREATE TABLE IF NOT EXISTS locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    address TEXT NOT NULL,
    lat REAL,
    lon REAL
);

-- Topics table (title made UNIQUE to avoid duplicate seeds)
CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL
);

-- Content sections for each topic
CREATE TABLE IF NOT EXISTS topic_sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    FOREIGN KEY (topic_id) REFERENCES topics(id)
);

-- Revision sheets
CREATE TABLE IF NOT EXISTS revision_sheets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    FOREIGN KEY (topic_id) REFERENCES topics(id)
);

-- Notes table (with foreign key to users)
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Seed topics (idempotent)
INSERT OR IGNORE INTO topics (title, description) VALUES
('Mathematics', 'Core mathematics topics: algebra, calculus, statistics.'),
('Science', 'Fundamental science topics: physics, chemistry, biology.'),
('Literature', 'Analysis and interpretation of prose and poetry.'),
('History', 'Key events and themes across history.');

-- Seed locations (all with lat/lon)
INSERT OR IGNORE INTO locations (name, address, lat, lon) VALUES
('City Library', '123 Main St', -27.4679, 153.0281),
('Campus Study Hall', 'Building A, Room 204', -27.4780, 153.0150),
('State Library of Queensland', 'Stanley Place, South Brisbane QLD 4101', -27.4735, 153.0181),
('Brisbane Square Library', '266 George St, Brisbane City QLD 4000', -27.4705, 153.0234);