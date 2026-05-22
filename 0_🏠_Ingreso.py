import streamlit as st
import database
import warnings
warnings.filterwarnings('ignore', category=UserWarning)
import warnings
warnings.filterwarnings('ignore', category=UserWarning)
import os

st.set_page_config(page_title="Ingreso OMS", page_icon="🔐", layout="wide")

# Inicializar DB en arranque
database.init_db()

import glob

# Agregar Logos al inicio del menú lateral (sidebar)
logo1_files = glob.glob("one_element.*")
logo2_files = glob.glob("evoke.*")

for f in logo1_files:
    if f.lower().endswith(('.png', '.jpg', '.jpeg')):
        st.sidebar.image(f, use_container_width=True)
        break

for f in logo2_files:
    if f.lower().endswith(('.png', '.jpg', '.jpeg')):
        st.sidebar.image(f, use_container_width=True)
        break
    
st.sidebar.markdown("---")

def check_password():
    """Returns `True` if the user had the correct password."""
    def password_entered():
        import sqlite3
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("SELECT role FROM users WHERE username=%s AND password=%s", 
                  (st.session_state["username"], st.session_state["password"]))
        result = c.fetchone()
        if result:
            st.session_state["password_correct"] = True
            st.session_state["role"] = result[0]
            st.session_state["logged_in_user"] = st.session_state["username"]
            del st.session_state["password"]  # don't store password
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # First run, show inputs for username + password.
        st.title("🔐 Ingreso al Sistema OMS")
        st.text_input("Usuario", key="username")
        st.text_input("Contraseña", type="password", key="password")
        st.button("Entrar", on_click=password_entered)
        return False
    elif not st.session_state["password_correct"]:
        # Password not correct, show input + error.
        st.title("🔐 Ingreso al Sistema OMS")
        st.text_input("Usuario", key="username")
        st.text_input("Contraseña", type="password", key="password")
        st.button("Entrar", on_click=password_entered)
        st.error("❌ Usuario o contraseña incorrectos")
        return False
    else:
        # Password correct.
        return True

if check_password():
    st.write(f"# 👋 Bienvenido al Sistema OMS")
    st.write(f"Has iniciado sesión como: **{st.session_state.get('logged_in_user', '')}** con rol **{st.session_state['role']}**")
    st.info("👈 Por favor selecciona un módulo en el panel izquierdo según tu rol.")
