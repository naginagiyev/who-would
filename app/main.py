import os
import random
import string
import psycopg
from contextlib import asynccontextmanager
from paths import schema_path, templates_dir
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi import FastAPI, Form, HTTPException, Request

database_url = os.environ["DATABASE_URL"]
templates = Jinja2Templates(directory=templates_dir)

QUESTIONS = [
    "Who would buy an oxygen mask for the birthday of a friend with asthma?",
    "Who would get lost in their own city?",
    "Who would forget their own birthday?",
    "Who would survive a zombie apocalypse?",
    "Who would become famous on TikTok?",
    "Who would eat pizza for breakfast every day?",
    "Who would cry during a cartoon?",
    "Who would win a million and lose it in a week?",
    "Who would sleep through a fire alarm?",
    "Who would talk to a plant every morning?",
]

@asynccontextmanager
async def lifespan(app):
    with psycopg.connect(database_url) as conn:
        conn.execute(schema_path.read_text())
    yield

app = FastAPI(lifespan=lifespan)

def add_player(conn, code, name):
    query = "INSERT INTO players (room_code, name) VALUES (%s, %s) RETURNING id"
    player_id = conn.execute(query, (code, name)).fetchone()[0]
    return RedirectResponse(f"/rooms/{code}?player_id={player_id}", status_code=303)

@app.get("/health")
def health():
    try:
        with psycopg.connect(database_url, connect_timeout=3) as conn:
            conn.execute("SELECT 1")
    except psycopg.Error:
        raise HTTPException(500, "Database unreachable")
    return {"status": "ok"}

@app.get("/")
def index(request: Request):
    return templates.TemplateResponse(request, "index.html")

@app.post("/rooms")
def create_room(name: str = Form()):
    code = "".join(random.choices(string.ascii_uppercase, k=4))
    with psycopg.connect(database_url) as conn:
        conn.execute("INSERT INTO rooms (code) VALUES (%s)", (code,))
        return add_player(conn, code, name)

@app.post("/join")
def join_room(code: str = Form(), name: str = Form()):
    code = code.strip().upper()
    with psycopg.connect(database_url) as conn:
        room = conn.execute("SELECT code FROM rooms WHERE code = %s", (code,)).fetchone()
        if room is None:
            raise HTTPException(404, "Room not found")
        return add_player(conn, code, name)

@app.get("/rooms/{code}")
def room_page(request: Request, code: str, player_id: int):
    query = "SELECT id, name FROM players WHERE room_code = %s ORDER BY id"
    with psycopg.connect(database_url) as conn:
        players = conn.execute(query, (code,)).fetchall()
        query = "SELECT id, text, revealed FROM questions WHERE room_code = %s ORDER BY id DESC"
        question = conn.execute(query, (code,)).fetchone()
        voters, results = [], []
        if question:
            query = "SELECT voter_id FROM votes WHERE question_id = %s"
            voters = [row[0] for row in conn.execute(query, (question[0],))]
        if question and question[2]:
            query = (
                "SELECT p.id, p.name, COUNT(v.id) FROM players p LEFT JOIN votes v "
                "ON v.target_id = p.id AND v.question_id = %s "
                "WHERE p.room_code = %s GROUP BY p.id ORDER BY COUNT(v.id) DESC, p.id"
            )
            results = conn.execute(query, (question[0], code)).fetchall()
    if not players:
        raise HTTPException(404, "Room not found")
    context = {
        "code": code,
        "players": players,
        "player_id": player_id,
        "question": question,
        "voters": voters,
        "results": results,
    }
    return templates.TemplateResponse(request, "room.html", context)

@app.post("/rooms/{code}/questions")
def set_question(code: str, player_id: int = Form(), text: str = Form("")):
    text = text.strip() or random.choice(QUESTIONS)
    query = "INSERT INTO questions (room_code, text) VALUES (%s, %s)"
    with psycopg.connect(database_url) as conn:
        conn.execute(query, (code, text))
    return RedirectResponse(f"/rooms/{code}?player_id={player_id}", status_code=303)

@app.post("/questions/{question_id}/votes")
def vote(question_id: int, voter_id: int = Form(), target_id: int = Form()):
    query = "INSERT INTO votes (question_id, voter_id, target_id) VALUES (%s, %s, %s)"
    with psycopg.connect(database_url) as conn:
        room = conn.execute("SELECT room_code FROM questions WHERE id = %s", (question_id,))
        code = room.fetchone()[0]
        try:
            conn.execute(query, (question_id, voter_id, target_id))
        except psycopg.IntegrityError:
            raise HTTPException(400, "You already voted or voted for yourself")
    return RedirectResponse(f"/rooms/{code}?player_id={voter_id}", status_code=303)

@app.post("/questions/{question_id}/reveal")
def reveal(question_id: int, player_id: int = Form()):
    query = "UPDATE questions SET revealed = TRUE WHERE id = %s RETURNING room_code"
    with psycopg.connect(database_url) as conn:
        code = conn.execute(query, (question_id,)).fetchone()[0]
    return RedirectResponse(f"/rooms/{code}?player_id={player_id}", status_code=303)
