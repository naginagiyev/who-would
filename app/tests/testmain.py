import re
import pytest
from app.main import app
from fastapi.testclient import TestClient

@pytest.fixture(scope="module")
def client():
    with TestClient(app, follow_redirects=False) as test_client:
        yield test_client

@pytest.fixture
def game(client):
    host = client.post("/rooms", data={"name": "Host"}).headers["location"]
    code, host_id = re.search(r"/rooms/(\w+)\?player_id=(\d+)", host).groups()
    player = client.post("/join", data={"code": code, "name": "Ann"}).headers["location"]
    player_id = player.split("=")[1]
    client.post(f"/rooms/{code}/questions", data={"player_id": host_id, "text": "Who would win?"})
    page = client.get(f"/rooms/{code}?player_id={host_id}").text
    question_id = re.search(r"/questions/(\d+)/votes", page).group(1)
    return {"code": code, "host": host_id, "player": player_id, "question": question_id}

def vote(client, game, voter_id, target_id):
    data = {"voter_id": voter_id, "target_id": target_id}
    return client.post(f"/questions/{game['question']}/votes", data=data)

def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_self_vote_rejected(client, game):
    assert vote(client, game, game["player"], game["player"]).status_code == 400

def test_duplicate_vote_rejected(client, game):
    assert vote(client, game, game["player"], game["host"]).status_code == 303
    assert vote(client, game, game["player"], game["host"]).status_code == 400

def test_results_hidden_before_reveal(client, game):
    vote(client, game, game["player"], game["host"])
    room_url = f"/rooms/{game['code']}?player_id={game['player']}"
    assert '<ul class="results">' not in client.get(room_url).text
    client.post(f"/questions/{game['question']}/reveal", data={"player_id": game["host"]})
    assert '<ul class="results">' in client.get(room_url).text
