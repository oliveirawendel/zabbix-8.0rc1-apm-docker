import os
import random
import time
import uuid

import requests

BASE = os.getenv("TARGET", "http://shop-api:8000")
INTERVAL = float(os.getenv("INTERVAL", "0.5"))
PRODUCTS = ["Notebook", "Mouse", "Teclado", "Monitor", "Headset", "Webcam", "Dock USB-C"]
STATUS = ["pending", "paid", "shipped", "cancelled"]


def call(method, path, **kw):
    try:
        r = requests.request(method, BASE + path, timeout=15, **kw)
        print(f"{method} {path} -> {r.status_code}", flush=True)
        return r
    except requests.RequestException as exc:
        print(f"{method} {path} -> ERRO {exc}", flush=True)
        return None


def json_list(path):
    r = call("GET", path)
    try:
        return r.json() if r is not None and r.ok else []
    except ValueError:
        return []


def list_users():
    call("GET", "/api/users")


def get_user():
    ids = [u["id"] for u in json_list("/api/users")]
    if ids:
        call("GET", f"/api/users/{random.choice(ids)}")


def create_user():
    n = uuid.uuid4().hex[:8]
    call("POST", "/api/users", json={"name": f"Cliente {n}", "email": f"{n}@loadgen.test"})


def update_user():
    ids = [u["id"] for u in json_list("/api/users")]
    if ids:
        call("PUT", f"/api/users/{random.choice(ids)}", json={"name": f"Renomeado {uuid.uuid4().hex[:4]}"})


def delete_user():
    ids = [u["id"] for u in json_list("/api/users") if u["email"].endswith("@loadgen.test")]
    if ids:
        call("DELETE", f"/api/users/{random.choice(ids)}")  # pode dar 409 se tiver pedido


def create_order():
    ids = [u["id"] for u in json_list("/api/users")]
    if ids:
        call("POST", "/api/orders", json={
            "user_id": random.choice(ids), "product": random.choice(PRODUCTS),
            "amount": round(random.uniform(20, 5000), 2),
        })


def create_order_invalid_user():
    call("POST", "/api/orders", json={"user_id": 999999, "product": "Fantasma", "amount": 10})


def list_orders():
    call("GET", "/api/orders")


def update_order():
    ids = [o["id"] for o in json_list("/api/orders")]
    if ids:
        call("PUT", f"/api/orders/{random.choice(ids)}/status", json={"status": random.choice(STATUS)})


def delete_order():
    ids = [o["id"] for o in json_list("/api/orders")]
    if len(ids) > 5:
        call("DELETE", f"/api/orders/{random.choice(ids)}")


def report():
    call("GET", "/api/orders/report")


def summary():
    ids = [u["id"] for u in json_list("/api/users")]
    if ids:
        call("GET", f"/api/summary/{random.choice(ids)}")


def not_found():
    call("GET", "/api/users/999999")


def slow():
    call("GET", "/api/slow")


def boom():
    call("GET", "/api/boom")


ACTIONS = [
    (list_users, 20), (get_user, 15), (create_user, 8), (update_user, 8), (delete_user, 5),
    (create_order, 15), (list_orders, 10), (update_order, 8), (delete_order, 4),
    (report, 5), (summary, 10), (not_found, 3), (create_order_invalid_user, 3),
    (slow, 3), (boom, 2),
]


def main():
    print(f"loadgen iniciando, alvo {BASE}", flush=True)
    while True:  # espera a api subir
        try:
            if requests.get(BASE + "/health", timeout=3).ok:
                break
        except requests.RequestException:
            pass
        time.sleep(2)
    funcs, weights = zip(*ACTIONS)
    while True:
        random.choices(funcs, weights)[0]()
        time.sleep(random.uniform(INTERVAL / 2, INTERVAL * 1.5))


if __name__ == "__main__":
    main()
