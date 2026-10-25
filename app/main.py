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
    if not players:
        raise HTTPException(404, "Room not found")
    context = {"code": code, "players": players, "player_id": player_id}
    return templates.TemplateResponse(request, "room.html", context)
