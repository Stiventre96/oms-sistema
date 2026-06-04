import streamlit as st
import database
import warnings
warnings.filterwarnings('ignore', category=UserWarning)
import pandas as pd
import uuid
from datetime import date

if "password_correct" not in st.session_state or not st.session_state["password_correct"]:
    st.warning("Por favor inicia sesión desde la página principal.")
    st.stop()

role = st.session_state["role"]
if role not in ["Admin", "Ventas", "Logistica"]:
    st.error("No tienes permisos para acceder a Ventas.")
    st.stop()

st.title("🛒 Ventas y Creación de Pedidos")

conn = database.get_connection()

tab1, tab2, tab3 = st.tabs(["Crear Nuevo Pedido", "Modificar Pedido", "Cancelar Pedido"])

# ─── PESTAÑA 1: CREAR PEDIDO ──────────────────────────────────────────────────
with tab1:
    df_prods = pd.read_sql("SELECT id, name, base_price, current_stock FROM products", conn)

    if df_prods.empty:
        st.warning("No hay productos en el catálogo para vender.")
    else:
        if 'cart' not in st.session_state:
            st.session_state['cart'] = []

        st.subheader("1. Agregar Productos al Pedido")
        col1, col2, col3, col4, col5 = st.columns([3, 1, 2, 2, 1])

        prod_ids = dict(zip(df_prods['name'], df_prods['id']))
        prod_prices = dict(zip(df_prods['name'], df_prods['base_price']))

        with col1:
            selected_prod_name = st.selectbox("Producto", options=list(prod_ids.keys()), key="create_prod")
        with col2:
            qty = st.number_input("Cantidad", min_value=1.0, step=1.0, key="create_qty")
        with col3:
            discount_opts = {"0%": 0.0, "5%": 0.05, "10%": 0.10, "15%": 0.15, "20%": 0.20, "25%": 0.25, "30%": 0.30, "35%": 0.35, "40%": 0.40}
            discount_label = st.selectbox("Descuento", options=list(discount_opts.keys()), key="create_desc")
        with col4:
            base_p = prod_prices[selected_prod_name]
            discount_val = discount_opts[discount_label]
            final_price = base_p * (1 - discount_val)
            st.metric("Precio Final (Und)", f"${final_price:,.2f}")
        with col5:
            st.write("")
            st.write("")
            if st.button("Agregar", key="btn_add_create"):
                st.session_state['cart'].append({
                    "product_id": prod_ids[selected_prod_name],
                    "name": selected_prod_name,
                    "quantity": qty,
                    "discount_applied": discount_val,
                    "unit_price": final_price,
                    "total": qty * final_price
                })
                st.rerun()

        if st.session_state['cart']:
            st.write("### Carrito Actual")
            st.caption("👆 Haz clic en un artículo de la tabla si deseas eliminarlo individualmente.")
            df_cart = pd.DataFrame(st.session_state['cart'])
            event_cart = st.dataframe(
                df_cart[['name', 'quantity', 'discount_applied', 'unit_price', 'total']], 
                use_container_width=True,
                on_select="rerun",
                selection_mode="single-row",
                key="cart_selection_create"
            )

            sel_cart = event_cart.selection.rows
            if sel_cart and sel_cart[0] < len(st.session_state['cart']):
                idx_to_del = sel_cart[0]
                item_to_del = st.session_state['cart'][idx_to_del]['name']
                if st.button(f"🗑️ Eliminar '{item_to_del}'", key="btn_del_item_create"):
                    st.session_state['cart'].pop(idx_to_del)
                    st.rerun()

            if st.button("Limpiar Todo el Carrito", key="btn_clear_create"):
                st.session_state['cart'] = []
                st.rerun()

            total_order = df_cart['total'].sum()
            st.metric("Total del Pedido", f"${total_order:,.2f}")

            st.subheader("2. Datos del Pedido y Confirmación")
            with st.form("checkout_form"):
                st.write("#### Información del Cliente")
                colA, colB, colC = st.columns(3)
                with colA:
                    order_date = st.date_input("Fecha del Pedido", value=date.today())
                    cust_name = st.text_input("Nombre del Cliente *")
                with colB:
                    cust_cedula = st.text_input("Cédula / NIT *")
                    cust_phone = st.text_input("Teléfono")
                with colC:
                    cust_address = st.text_input("Dirección de Envío")
                    colC1, colC2 = st.columns(2)
                    with colC1:
                        cust_city = st.text_input("Ciudad")
                    with colC2:
                        cust_dept = st.text_input("Departamento")

                st.write("#### Detalles Comerciales")
                colD, colE, colF = st.columns(3)
                with colD:
                    sales_channel = st.selectbox("Canal de Venta", ["Whatsapp", "Woocommerce", "MercadoLibre", "Venta Física", "Shopify"])
                with colE:
                    ext_order_id = st.text_input("ID de Pedido (Ej. Woocommerce)")
                with colF:
                    payment_method = st.selectbox("Método de Pago", ["Efectivo", "Wompy", "Contra Entrega", "Bancolombia", "Nequi", "Davivienda", "Canje por Publicidad", "sistecredito", "Embajador" , "consignacion"])

                submit_order = st.form_submit_button("Confirmar Pedido")

                if submit_order:
                    if not cust_name or not cust_cedula:
                        st.error("Nombre y cédula son obligatorios.")
                    else:
                        try:
                            c = conn.cursor()
                            order_num = f"PED-{str(uuid.uuid4())[:8].upper()}"
                            status = 'PENDING_PAYMENT' if payment_method != "Contra Entrega" else 'PENDING_DISPATCH'

                            c.execute("""
                                INSERT INTO orders (
                                    order_number, external_order_id, order_date, customer_name, customer_cedula,
                                    customer_phone, customer_address, customer_city, customer_department,
                                    sales_channel, payment_method, status, total_amount, created_by
                                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                                RETURNING id
                            """, (order_num, ext_order_id, order_date, cust_name, cust_cedula,
                                  cust_phone, cust_address, cust_city, cust_dept,
                                  sales_channel, payment_method, status, float(total_order), st.session_state.get('logged_in_user', 'Desconocido')))

                            order_id = c.fetchone()[0]

                            for item in st.session_state['cart']:
                                c.execute("""
                                    INSERT INTO order_items (order_id, product_id, quantity, applied_discount, unit_price)
                                    VALUES (%s, %s, %s, %s, %s)
                                """, (order_id, item['product_id'], item['quantity'], item['discount_applied'], item['unit_price']))

                            conn.commit()
                            st.session_state['cart'] = []

                            if status == 'PENDING_PAYMENT':
                                st.success(f"¡Pedido {order_num} creado exitosamente! Pasó a Cartera para validación de pago.")
                            else:
                                st.success(f"¡Pedido {order_num} (Contra Entrega) creado! Pasó a Logística para despacho.")
                        except Exception as e:
                            conn.rollback()
                            st.error(f"Error al crear el pedido: {e}")

# ─── PESTAÑA 2: MODIFICAR PEDIDO ──────────────────────────────────────────────
with tab2:
    if role not in ["Admin", "Ventas"]:
        st.error("Solo el área de Ventas puede modificar pedidos.")
    else:
        st.subheader("Modificar Pedido Existente")
        st.caption("👆 Haz clic en un pedido de la tabla para editar sus datos personales o agregar/quitar artículos.")

        df_edit = pd.read_sql("""
            SELECT id, order_number AS "N° Pedido", order_date AS "Fecha",
                   customer_name AS "Cliente", customer_phone AS "Teléfono",
                   sales_channel AS "Canal", payment_method AS "Pago", status
            FROM orders
            WHERE status IN ('PENDING_PAYMENT', 'PENDING_DISPATCH')
            ORDER BY created_at DESC
        """, conn)

        if df_edit.empty:
            st.info("No hay pedidos activos que se puedan modificar.")
        else:
            event_edit = st.dataframe(
                df_edit.drop(columns=['id', 'status']),
                use_container_width=True,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
                key="tabla_mod_ventas"
            )

            selected_edit = event_edit.selection.rows
            if selected_edit and selected_edit[0] < len(df_edit):
                row_edit_id = int(df_edit.iloc[selected_edit[0]]['id'])

                # Controlar si cambiamos de pedido para recargar el carrito
                if st.session_state.get('edit_order_id') != row_edit_id:
                    st.session_state['edit_order_id'] = row_edit_id
                    # Cargar items actuales de este pedido
                    df_current_items = pd.read_sql("""
                        SELECT p.id as product_id, p.name, oi.quantity, oi.applied_discount as discount_applied, oi.unit_price, (oi.quantity * oi.unit_price) as total
                        FROM order_items oi
                        JOIN products p ON oi.product_id = p.id
                        WHERE oi.order_id = %s
                    """, conn, params=(row_edit_id,))
                    st.session_state['edit_cart'] = df_current_items.to_dict('records')

                df_full = pd.read_sql("SELECT * FROM orders WHERE id=%s", conn, params=(row_edit_id,))
                order_row = df_full.iloc[0]

                with st.container(border=True):
                    st.markdown(f"#### Editando Pedido: `{order_row['order_number']}`")
                    
                    # ─── MODIFICAR PRODUCTOS DEL CARRITO ───
                    st.markdown("##### 🛒 Artículos del Pedido")
                    if 'edit_cart' not in st.session_state:
                        st.session_state['edit_cart'] = []
                    
                    col_e1, col_e2, col_e3, col_e4, col_e5 = st.columns([3, 1, 2, 2, 1])
                    with col_e1:
                        sel_prod_edit = st.selectbox("Añadir producto", options=list(prod_ids.keys()), key="edit_prod")
                    with col_e2:
                        qty_edit = st.number_input("Cantidad", min_value=1.0, step=1.0, key="edit_qty")
                    with col_e3:
                        discount_opts = {"0%": 0.0, "5%": 0.05, "10%": 0.10, "15%": 0.15, "20%": 0.20, "25%": 0.25, "30%": 0.30, "35%": 0.35, "40%": 0.40}
                        desc_edit = st.selectbox("Descuento", options=list(discount_opts.keys()), key="edit_desc")
                    with col_e4:
                        fp_edit = prod_prices[sel_prod_edit] * (1 - discount_opts[desc_edit])
                        st.metric("Precio Final", f"${fp_edit:,.2f}")
                    with col_e5:
                        st.write("")
                        st.write("")
                        if st.button("Agregar", key="btn_add_edit"):
                            st.session_state['edit_cart'].append({
                                "product_id": prod_ids[sel_prod_edit],
                                "name": sel_prod_edit,
                                "quantity": qty_edit,
                                "discount_applied": discount_opts[desc_edit],
                                "unit_price": fp_edit,
                                "total": qty_edit * fp_edit
                            })
                            st.rerun()

                    if st.session_state['edit_cart']:
                        st.caption("👆 Haz clic en un artículo de la tabla si deseas eliminarlo individualmente.")
                        df_edit_cart = pd.DataFrame(st.session_state['edit_cart'])
                        event_edit_cart = st.dataframe(
                            df_edit_cart[['name', 'quantity', 'discount_applied', 'unit_price', 'total']], 
                            use_container_width=True,
                            on_select="rerun",
                            selection_mode="single-row",
                            key="cart_selection_edit"
                        )
                        
                        sel_ecart = event_edit_cart.selection.rows
                        if sel_ecart and sel_ecart[0] < len(st.session_state['edit_cart']):
                            idx_to_del = sel_ecart[0]
                            item_to_del = st.session_state['edit_cart'][idx_to_del]['name']
                            if st.button(f"🗑️ Eliminar '{item_to_del}'", key="btn_del_item_edit"):
                                st.session_state['edit_cart'].pop(idx_to_del)
                                st.rerun()

                        if st.button("Limpiar Todo el Carrito", key="btn_clear_edit"):
                            st.session_state['edit_cart'] = []
                            st.rerun()
                        edit_total_order = df_edit_cart['total'].sum()
                        st.markdown(f"**Total del Pedido Actualizado: ${edit_total_order:,.2f}**")
                    else:
                        edit_total_order = 0.0
                        st.error("El carrito está vacío. Debes agregar al menos un producto.")

                    st.markdown("---")

                    # ─── MODIFICAR DATOS DEL CLIENTE ───
                    with st.form(f"edit_order_form_{row_edit_id}"):
                        st.markdown("##### 👤 Datos del Cliente")
                        colA, colB, colC = st.columns(3)
                        with colA:
                            new_date = st.date_input("Fecha del Pedido", value=pd.to_datetime(order_row['order_date']).date())
                            new_name = st.text_input("Nombre del Cliente", value=order_row['customer_name'])
                        with colB:
                            new_cedula = st.text_input("Cédula / NIT", value=order_row['customer_cedula'])
                            new_phone = st.text_input("Teléfono", value=order_row['customer_phone'] or "")
                        with colC:
                            new_address = st.text_input("Dirección", value=order_row['customer_address'] or "")
                            colC1, colC2 = st.columns(2)
                            with colC1:
                                new_city = st.text_input("Ciudad", value=order_row['customer_city'] or "")
                            with colC2:
                                new_dept = st.text_input("Departamento", value=order_row['customer_department'] or "")

                        colD, colE, colF = st.columns(3)
                        channel_opts = ["Whatsapp", "Woocommerce", "MercadoLibre", "Venta Física", "Shopify"]
                        pay_opts = ["Efectivo", "Wompy", "Contra Entrega", "Bancolombia", "Nequi", "Davivienda", "Canje por Publicidad", "Embajador"]
                        with colD:
                            new_channel = st.selectbox("Canal de Venta", channel_opts,
                                                       index=channel_opts.index(order_row['sales_channel']) if order_row['sales_channel'] in channel_opts else 0)
                        with colE:
                            new_ext_id = st.text_input("ID Externo (Woocommerce)", value=order_row['external_order_id'] or "")
                        with colF:
                            new_pay = st.selectbox("Método de Pago", pay_opts,
                                                   index=pay_opts.index(order_row['payment_method']) if order_row['payment_method'] in pay_opts else 0)

                        save_edit = st.form_submit_button("Guardar Todos Los Cambios (Cliente + Productos)", type="primary")

                        if save_edit:
                            if not st.session_state['edit_cart']:
                                st.error("No puedes guardar un pedido sin productos.")
                            else:
                                try:
                                    c = conn.cursor()
                                    # Update order details
                                    c.execute("""
                                        UPDATE orders SET
                                            order_date=%s, customer_name=%s, customer_cedula=%s,
                                            customer_phone=%s, customer_address=%s, customer_city=%s, customer_department=%s,
                                            sales_channel=%s, external_order_id=%s, payment_method=%s, total_amount=%s
                                        WHERE id=%s
                                    """, (new_date, new_name, new_cedula, new_phone, new_address,
                                          new_city, new_dept, new_channel, new_ext_id, new_pay, float(edit_total_order),
                                          row_edit_id))
                                    
                                    # Update order items (delete old, insert new)
                                    c.execute("DELETE FROM order_items WHERE order_id = %s", (row_edit_id,))
                                    for item in st.session_state['edit_cart']:
                                        c.execute("""
                                            INSERT INTO order_items (order_id, product_id, quantity, applied_discount, unit_price)
                                            VALUES (%s, %s, %s, %s, %s)
                                        """, (row_edit_id, item['product_id'], item['quantity'], item['discount_applied'], item['unit_price']))
                                        
                                    conn.commit()
                                    st.success("¡Pedido y carrito actualizados correctamente!")
                                    st.rerun()
                                except Exception as e:
                                    conn.rollback()
                                    st.error(f"Error al actualizar: {e}")
            else:
                st.info("☝️ Selecciona un pedido de la tabla de arriba para editar sus datos o agregar/quitar artículos.")

# ─── PESTAÑA 3: CANCELAR PEDIDO ───────────────────────────────────────────────
with tab3:
    if role not in ["Admin", "Ventas"]:
        st.error("Solo el área de Ventas puede cancelar pedidos desde este módulo.")
    else:
        st.subheader("Cancelar Pedido")
        st.caption("👆 Haz clic en un pedido de la tabla para cancelarlo.")

        df_cancel = pd.read_sql("""
            SELECT id, order_number AS "N° Pedido", order_date AS "Fecha",
                   customer_name AS "Cliente", payment_method AS "Pago",
                   total_amount AS "Total"
            FROM orders
            WHERE status IN ('PENDING_PAYMENT', 'PENDING_DISPATCH')
        """, conn)

        if df_cancel.empty:
            st.info("No hay pedidos pendientes que se puedan cancelar en este momento.")
        else:
            event_cancel = st.dataframe(
                df_cancel.drop(columns=['id']),
                use_container_width=True,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
                key="tabla_cancel_ventas"
            )

            selected_cancel = event_cancel.selection.rows
            if selected_cancel and selected_cancel[0] < len(df_cancel):
                row_c = df_cancel.iloc[selected_cancel[0]]
                with st.container(border=True):
                    st.warning(f"¿Cancelar el pedido **{row_c['N° Pedido']}** de **{row_c['Cliente']}**?")
                    if st.button("❌ Sí, cancelar este pedido", type="primary", key="btn_cancel_ventas"):
                        try:
                            c = conn.cursor()
                            c.execute("UPDATE orders SET status='CANCELLED' WHERE id=%s", (int(row_c['id']),))
                            conn.commit()
                            st.success("¡El pedido ha sido cancelado exitosamente!")
                            st.rerun()
                        except Exception as e:
                            conn.rollback()
                            st.error(f"Error al cancelar: {e}")
            else:
                st.info("☝️ Selecciona un pedido de la tabla para cancelarlo.")
