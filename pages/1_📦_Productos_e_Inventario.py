import streamlit as st
import database
import warnings
warnings.filterwarnings('ignore', category=UserWarning)
import pandas as pd

if "password_correct" not in st.session_state or not st.session_state["password_correct"]:
    st.warning("Por favor inicia sesión desde la página principal.")
    st.stop()

role = st.session_state["role"]

# Restricción estricta: Solo el administrador puede entrar a este módulo
if role != "Admin":
    st.error("Acceso Denegado. Solo el Administrador puede gestionar productos e inventarios.")
    st.stop()

st.title("📦 Productos e Inventario")

conn = database.get_connection()

tab1, tab2, tab3 = st.tabs(["1. Catálogo y Creación", "2. Ajustes (Entradas/Salidas)", "3. Eliminar Producto"])

with tab1:
    st.subheader("Catálogo Actual")
    
    with st.expander("➕ Crear Nuevo Producto"):
        with st.form("new_product"):
            col1, col2 = st.columns(2)
            with col1:
                sku = st.text_input("SKU")
                name = st.text_input("Nombre del Producto")
            with col2:
                category = st.selectbox("Categoría", ["Suplementos", "Ropa", "Accesorios", "General", "Promocional"])
                base_price = st.number_input("Precio Base ($)", min_value=0.0, step=1000.0)
                
            submit = st.form_submit_button("Crear")
            if submit:
                if sku and name and base_price >= 0:
                    try:
                        c = conn.cursor()
                        c.execute("INSERT INTO products (sku, name, category, base_price) VALUES (%s, %s, %s, %s)", (sku, name, category, base_price))
                        conn.commit()
                        st.success(f"Producto {name} creado exitosamente.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error (¿SKU duplicado?): {e}")
                else:
                    st.error("Llenar todos los campos correctamente.")
    
    df_prods = pd.read_sql("SELECT id, sku, name, category, base_price, current_stock FROM products", conn)
    st.dataframe(df_prods, use_container_width=True, hide_index=True)


with tab2:
    st.subheader("Ajustes Manuales de Inventario")
    st.write("Registra ingreso de nueva mercancía o salidas manuales (pérdidas, mermas, garantías).")
    
    df_list = pd.read_sql("SELECT id, name, current_stock FROM products", conn)
    if df_list.empty:
        st.warning("No hay productos creados aún.")
    else:
        colA, colB = st.columns(2)
        
        with colA:
            st.write("#### 📥 Ingreso (Suma)")
            with st.form("inventory_in"):
                prod_options = dict(zip(df_list['name'] + " (Stock: " + df_list['current_stock'].astype(str) + ")", df_list['id']))
                selected_prod_in = st.selectbox("Producto a Ingresar", options=list(prod_options.keys()))
                qty_in = st.number_input("Cantidad a Ingresar", min_value=1.0, step=1.0)
                ref_in = st.text_input("Motivo / Factura (IN)")
                submit_in = st.form_submit_button("Registrar Ingreso")
                
                if submit_in:
                    prod_id = prod_options[selected_prod_in]
                    c = conn.cursor()
                    try:
                        c.execute("INSERT INTO inventory_movements (product_id, type, quantity, reference_id) VALUES (%s, 'IN', %s, %s)",
                                  (prod_id, qty_in, ref_in))
                        c.execute("UPDATE products SET current_stock = current_stock + %s WHERE id = %s", (qty_in, prod_id))
                        conn.commit()
                        st.success(f"Se sumaron {qty_in} unidades correctamente.")
                        st.rerun()
                    except Exception as e:
                        conn.rollback()
                        st.error(f"Error al ingresar: {e}")

        with colB:
            st.write("#### 📤 Salida (Resta)")
            with st.form("inventory_out"):
                selected_prod_out = st.selectbox("Producto a Retirar", options=list(prod_options.keys()))
                qty_out = st.number_input("Cantidad a Retirar", min_value=1.0, step=1.0)
                ref_out = st.text_input("Motivo de Salida (OUT)")
                submit_out = st.form_submit_button("Registrar Salida")
                
                if submit_out:
                    prod_id = prod_options[selected_prod_out]
                    c = conn.cursor()
                    try:
                        c.execute("INSERT INTO inventory_movements (product_id, type, quantity, reference_id) VALUES (%s, 'OUT_MANUAL', %s, %s)",
                                  (prod_id, qty_out, ref_out))
                        c.execute("UPDATE products SET current_stock = current_stock - %s WHERE id = %s", (qty_out, prod_id))
                        conn.commit()
                        st.success(f"Se restaron {qty_out} unidades correctamente.")
                        st.rerun()
                    except Exception as e:
                        conn.rollback()
                        st.error(f"Error al retirar: {e}")

with tab3:
    st.subheader("Eliminar Producto del Sistema")
    st.warning("⚠️ Precaución: Eliminar un producto es irreversible.")
    
    if df_list.empty:
        st.write("No hay productos.")
    else:
        with st.form("delete_product_form"):
            prod_del_options = dict(zip(df_list['name'], df_list['id']))
            selected_to_delete = st.selectbox("Seleccionar producto a eliminar", options=list(prod_del_options.keys()))
            confirm_delete = st.form_submit_button("Eliminar Permanentemente")
            
            if confirm_delete:
                prod_id = prod_del_options[selected_to_delete]
                c = conn.cursor()
                
                # Check if it has sales history to prevent breaking reports
                c.execute("SELECT COUNT(*) FROM order_items WHERE product_id = %s", (prod_id,))
                ventas_asociadas = c.fetchone()[0]
                
                if ventas_asociadas > 0:
                    st.error(f"No se puede eliminar '{selected_to_delete}' porque ya tiene ventas o pedidos registrados en el sistema. Para no afectar la contabilidad, te sugerimos hacerle una salida manual de inventario para dejar su stock en 0.")
                else:
                    try:
                        # Si no tiene ventas, se puede eliminar seguro
                        c.execute("DELETE FROM inventory_movements WHERE product_id = %s", (prod_id,))
                        c.execute("DELETE FROM products WHERE id = %s", (prod_id,))
                        conn.commit()
                        st.success(f"Producto '{selected_to_delete}' eliminado correctamente.")
                        st.rerun()
                    except Exception as e:
                        conn.rollback()
                        st.error(f"Error al eliminar: {e}")
