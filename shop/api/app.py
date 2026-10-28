import os

import requests
from flask import Flask, Response, jsonify, request

app = Flask(__name__)
USERS_URL = os.getenv("USERS_URL", "http://shop-users:5001")
ORDERS_URL = os.getenv("ORDERS_URL", "http://shop-orders:5002")
METHODS = ["GET", "POST", "PUT", "DELETE"]


def forward(base, path):
    try:
        r = requests.request(
            request.method, f"{base}{path}",
            params=request.args, json=request.get_json(silent=True), timeout=8,
        )
    except requests.RequestException as exc:
        return jsonify(error="upstream unavailable", detail=str(exc)), 502
    return Response(r.content, status=r.status_code,
                    content_type=r.headers.get("Content-Type", "application/json"))


@app.route("/api/users", defaults={"p": ""}, methods=METHODS)
@app.route("/api/users/<path:p>", methods=METHODS)
def users(p):
    return forward(USERS_URL, "/users" + (f"/{p}" if p else ""))


@app.route("/api/orders", defaults={"p": ""}, methods=METHODS)
@app.route("/api/orders/<path:p>", methods=METHODS)
def orders(p):
    return forward(ORDERS_URL, "/orders" + (f"/{p}" if p else ""))


@app.get("/api/summary/<int:uid>")
def summary(uid):
    """Fan-out: a api chama users e depois orders e junta o resultado."""
    try:
        u = requests.get(f"{USERS_URL}/users/{uid}", timeout=5)
        if u.status_code == 404:
            return jsonify(error="user not found"), 404
        u.raise_for_status()
        o = requests.get(f"{ORDERS_URL}/orders/user/{uid}", timeout=5)
        o.raise_for_status()
    except requests.RequestException as exc:
        return jsonify(error="upstream error", detail=str(exc)), 502
    orders_list = o.json()
    return jsonify(user=u.json(), orders=orders_list, orders_count=len(orders_list))


@app.get("/api/slow")
def slow():
    return forward(USERS_URL, "/slow")


@app.get("/api/boom")
def boom():
    return forward(USERS_URL, "/boom")


@app.get("/health")
def health():
    return jsonify(status="ok")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, threaded=True)
