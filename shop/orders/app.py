import os

import psycopg2
import psycopg2.errors
import psycopg2.extras
import requests
from flask import Flask, jsonify, request

app = Flask(__name__)
USERS_URL = os.getenv("USERS_URL", "http://shop-users:5001")
VALID_STATUS = {"pending", "paid", "shipped", "cancelled"}


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


COLS = "id, user_id, product, amount, status, created_at"


@app.get("/orders")
def list_orders():
    return jsonify(query(f"SELECT {COLS} FROM orders ORDER BY id DESC LIMIT 100"))


@app.get("/orders/report")
def report():
    return jsonify(query(
        "SELECT status, count(*) AS total, COALESCE(sum(amount), 0) AS amount "
        "FROM orders GROUP BY status ORDER BY status"
    ))


@app.get("/orders/user/<int:uid>")
def orders_by_user(uid):
    return jsonify(query(f"SELECT {COLS} FROM orders WHERE user_id = %s ORDER BY id", (uid,)))


@app.get("/orders/<int:oid>")
def get_order(oid):
    row = query(f"SELECT {COLS} FROM orders WHERE id = %s", (oid,), "one")
    if not row:
        return jsonify(error="order not found"), 404
    return jsonify(row)


@app.post("/orders")
def create_order():
    data = request.get_json(silent=True) or {}
    if not all(k in data for k in ("user_id", "product", "amount")):
        return jsonify(error="user_id, product and amount are required"), 400

    # Chamada ao servico de usuarios: gera o span cliente -> servidor entre servicos
    try:
        r = requests.get(f"{USERS_URL}/users/{data['user_id']}", timeout=3)
    except requests.RequestException as exc:
        return jsonify(error="users service unavailable", detail=str(exc)), 502
    if r.status_code == 404:
        return jsonify(error="user not found"), 404
    if not r.ok:
        return jsonify(error="users service error"), 502

    row = query(
        f"INSERT INTO orders (user_id, product, amount) VALUES (%s, %s, %s) RETURNING {COLS}",
        (data["user_id"], data["product"], data["amount"]), "one",
    )
    return jsonify(row), 201


@app.put("/orders/<int:oid>/status")
def update_status(oid):
    data = request.get_json(silent=True) or {}
    if data.get("status") not in VALID_STATUS:
        return jsonify(error=f"status must be one of {sorted(VALID_STATUS)}"), 400
    row = query(f"UPDATE orders SET status = %s WHERE id = %s RETURNING {COLS}", (data["status"], oid), "one")
    if not row:
        return jsonify(error="order not found"), 404
    return jsonify(row)


@app.delete("/orders/<int:oid>")
def delete_order(oid):
    n = query("DELETE FROM orders WHERE id = %s", (oid,), "count")
    if n == 0:
        return jsonify(error="order not found"), 404
    return jsonify(deleted=oid)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002, threaded=True)
