CREATE TABLE IF NOT EXISTS rooms (
    code TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'waiting'
);

CREATE TABLE IF NOT EXISTS players (
    id SERIAL PRIMARY KEY,
    room_code TEXT NOT NULL REFERENCES rooms(code),
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS questions (
    id SERIAL PRIMARY KEY,
    room_code TEXT NOT NULL REFERENCES rooms(code),
    text TEXT NOT NULL,
    revealed BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS votes (
    id SERIAL PRIMARY KEY,
    question_id INTEGER NOT NULL REFERENCES questions(id),
    voter_id INTEGER NOT NULL REFERENCES players(id),
    target_id INTEGER NOT NULL REFERENCES players(id),
    UNIQUE (question_id, voter_id),
    CHECK (voter_id <> target_id)
);
