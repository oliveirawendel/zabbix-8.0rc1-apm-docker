CREATE TABLE users (
    id         SERIAL PRIMARY KEY,
    name       TEXT NOT NULL,
    email      TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Sem ON DELETE CASCADE de proposito: apagar usuario com pedido gera erro 409
CREATE TABLE orders (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id),
    product    TEXT NOT NULL,
    amount     NUMERIC(10,2) NOT NULL,
    status     TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_orders_user ON orders(user_id);

INSERT INTO users (name, email) VALUES
  ('Ana Souza',    'ana@example.com'),
  ('Bruno Lima',   'bruno@example.com'),
  ('Carla Mendes', 'carla@example.com'),
  ('Diego Rocha',  'diego@example.com'),
  ('Elisa Prado',  'elisa@example.com');

INSERT INTO orders (user_id, product, amount, status) VALUES
  (1, 'Notebook',  4500.00, 'paid'),
  (1, 'Mouse',       89.90, 'shipped'),
  (2, 'Monitor',   1200.00, 'pending'),
  (3, 'Teclado',    250.00, 'paid');
