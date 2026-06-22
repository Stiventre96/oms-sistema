import psycopg2
import os
import streamlit as st

# Intentamos obtener la conexión de los Secretos seguros de Streamlit.
# Si no estamos en la nube (ej. corriendo local), intentará usar variables de entorno.
try:
    DB_URI = st.secrets["DATABASE_URL"]
except Exception:
    DB_URI = os.getenv("DATABASE_URL")

if not DB_URI:
    raise ValueError("No se encontró la conexión a la base de datos (DATABASE_URL) en los secretos.")

@st.cache_resource(ttl=3600)
def _create_connection():
    return psycopg2.connect(DB_URI, connect_timeout=10)

def get_connection():
    conn = _create_connection()
    if conn.closed != 0:
        _create_connection.clear() # Si la conexión se cayó, limpiamos la caché
        conn = _create_connection() # Y creamos una nueva
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY,
            sku TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            category TEXT DEFAULT 'General',
            base_price REAL DEFAULT 0.0,
            current_stock REAL DEFAULT 0.0
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS inventory_movements (
            id SERIAL PRIMARY KEY,
            product_id INTEGER,
            type TEXT NOT NULL,
            quantity REAL NOT NULL,
            reference_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(product_id) REFERENCES products(id)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            order_number TEXT UNIQUE NOT NULL,
            external_order_id TEXT,
            order_date DATE NOT NULL,
            customer_name TEXT NOT NULL,
            customer_cedula TEXT NOT NULL,
            customer_phone TEXT,
            customer_address TEXT,
            customer_city TEXT,
            customer_department TEXT,
            sales_channel TEXT NOT NULL,
            payment_method TEXT NOT NULL,
            status TEXT NOT NULL,
            is_paid BOOLEAN DEFAULT FALSE,
            invoice_number TEXT,
            tracking_number TEXT,
            total_amount REAL NOT NULL,
            created_by TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS order_items (
            id SERIAL PRIMARY KEY,
            order_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity REAL NOT NULL,
            applied_discount REAL DEFAULT 0.0,
            unit_price REAL NOT NULL,
            FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE,
            FOREIGN KEY(product_id) REFERENCES products(id)
        )
    ''')

    users_data = [
        ('admin', 'admin123', 'Admin'),
        ('ventas1', 'ventas123', 'Ventas'),
        ('cartera1', 'cartera123', 'Cartera'),
        ('logistica1', 'logistica123', 'Logistica')
    ]
    
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        c.executemany("INSERT INTO users (username, password, role) VALUES (%s, %s, %s)", users_data)
        
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Base de datos inicializada/actualizada en PostgreSQL.")
