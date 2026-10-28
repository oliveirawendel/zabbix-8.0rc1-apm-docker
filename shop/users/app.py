import os
import random

import psycopg2
import psycopg2.errors
import psycopg2.extras
from flask import Flask, jsonify, request

app = Flask(__name__)


def query(sql, params=None, fetch="all"):
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "shop-db"),
        dbname=os.getenv("DB_NAME", "shop"),
        user=os.getenv("DB_USER", "shop"),
        password=os.getenv("DB_PASSWORD", "shop"),
        connect_timeout=3,
    )
    try:
        with conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            if fetch == "all":
                return cur.fetchall()
            if fetch == "one":
                return cur.fetchone()
            return cur.rowcount
    finally:
        conn.close()


COLS = "id, name, email, created_at"


@app.get("/users")
def list_users():
    return jsonify(query(f"SELECT {COLS} FROM users ORDER BY id LIMIT 100"))


@app.get("/users/search")
def search_users():
    q = request.args.get("q", "")
    return jsonify(query(f"SELECT {COLS} FROM users WHERE name ILIKE %s ORDER BY id", (f"%{q}%",)))


@app.get("/users/<int:uid>")
def get_user(uid):
    row = query(f"SELECT {COLS} FROM users WHERE id = %s", (uid,), "one")
    if not row:
        return jsonify(error="user not found"), 404
    return jsonify(row)


@app.post("/users")
def create_user():
    data = request.get_json(silent=True) or {}
    if not data.get("name") or not data.get("email"):
        return jsonify(error="name and email are required"), 400
    try:
        row = query(
            f"INSERT INTO users (name, email) VALUES (%s, %s) RETURNING {COLS}",
            (data["name"], data["email"]), "one",
        )
    except psycopg2.errors.UniqueViolation:
        return jsonify(error="email already exists"), 409
    return jsonify(row), 201


@app.put("/users/<int:uid>")
def update_user(uid):
    data = request.get_json(silent=True) or {}
    if not data.get("name"):
        return jsonify(error="name is required"), 400
    row = query(f"UPDATE users SET name = %s WHERE id = %s RETURNING {COLS}", (data["name"], uid), "one")
    if not row:
        return jsonify(error="user not found"), 404
    return jsonify(row)


@app.delete("/users/<int:uid>")
def delete_user(uid):
    try:
        n = query("DELETE FROM users WHERE id = %s", (uid,), "count")
    except psycopg2.errors.ForeignKeyViolation:
        return jsonify(error="user has orders"), 409
    if n == 0:
        return jsonify(error="user not found"), 404
    return jsonify(deleted=uid)


@app.get("/slow")
def slow():
    """Query lenta de proposito (1 a 3 s) para ver latencia no APM."""
    secs = round(random.uniform(1, 3), 1)
    query("SELECT pg_sleep(%s)", (secs,), "one")
    return jsonify(slept=secs)


@app.get("/boom")
def boom():
    """Erro de proposito: tabela inexistente -> excecao no span do banco."""
    return jsonify(query("SELECT * FROM tabela_que_nao_existe"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, threaded=True)
