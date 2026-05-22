import streamlit as st
import database
import warnings
warnings.filterwarnings('ignore', category=UserWarning)
import pandas as pd

if "password_correct" not in st.session_state or not st.session_state["password_correct"]:
    st.warning("Por favor inicia sesión desde la página principal.")
    st.stop()

role = st.session_state["role"]
if role not in ["Admin", "Cartera"]:
    st.error("No tienes permisos para acceder a Cartera.")
    st.stop()

st.title("💰 Cartera y Facturación")
conn = database.get_connection()

tab1, tab2, tab3, tab4 = st.tabs(["Detalle de Pedidos", "Aprobar Pagos", "Modificar Pago / Factura", "Cancelar Pedidos"])

# ─── PESTAÑA 1: DETALLE DE PEDIDOS ────────────────────────────────────────────
with tab1:
    st.subheader("Detalle Completo de Pedidos para Facturación")
    st.caption("👆 Haz clic en un pedido de la tabla para consultar su detalle y facturar.")

    col_f1, _ = st.columns([2, 1])
    with col_f1:
        estado_filtro = st.selectbox("Filtrar por Estado",
            ["Todos", "Pendiente de Pago", "Listo para Despachar", "Despachado"])
    estado_map = {
        "Todos": None, "Pendiente de Pago": "PENDING_PAYMENT",
        "Listo para Despachar": "PENDING_DISPATCH", "Despachado": "DISPATCHED"
    }

    where_clause = ""
    if estado_map[estado_filtro]:
        where_clause = f"WHERE o.status = '{estado_map[estado_filtro]}'"

    df_orders = pd.read_sql(f"""
        SELECT o.id, o.order_number AS "N° Pedido", o.order_date AS "Fecha",
               o.customer_name AS "Cliente", o.customer_cedula AS "Cédula",
               o.sales_channel AS "Canal", o.payment_method AS "Pago",
               CASE 
                   WHEN o.status='PENDING_PAYMENT' THEN '⏳ Pendiente'
                   WHEN o.status='PENDING_DISPATCH' THEN '📦 Despacho'
                   WHEN o.status='DISPATCHED' THEN '🚚 Despachado'
                   WHEN o.status='DELIVERED' THEN '✅ Entregado'
                   ELSE o.status 
               END AS "Estado",
               o.total_amount AS "Total"
        FROM orders o
        {where_clause}
        ORDER BY o.created_at DESC
    """, conn)

    if df_orders.empty:
        st.info("No hay pedidos para mostrar con el filtro seleccionado.")
    else:
        event_detail = st.dataframe(
            df_orders.drop(columns=['id']),
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="tabla_detalle"
        )

        selected_det = event_detail.selection.rows
        if selected_det and selected_det[0] < len(df_orders):
            order_id_sel = int(df_orders.iloc[selected_det[0]]['id'])
            
            # Traer los datos crudos completos
            df_full = pd.read_sql("SELECT * FROM orders WHERE id=%s", conn, params=(order_id_sel,))
            row = df_full.iloc[0]

            st.divider()
            with st.container(border=True):
                st.markdown(f"### Pedido seleccionado: `{row['order_number']}`")
                
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.markdown("#### 🧾 Cliente")
                    st.markdown(f"**Nombre:** {row['customer_name']}")
                    st.markdown(f"**Cédula / NIT:** {row['customer_cedula']}")
                    st.markdown(f"**Teléfono:** {row['customer_phone'] or '—'}")
                with c2:
                    st.markdown("#### 📍 Destino")
                    st.markdown(f"**Dirección:** {row['customer_address'] or '—'}")
                    st.markdown(f"**Ciudad:** {row['customer_city'] or '—'}")
                    st.markdown(f"**Depto:** {row['customer_department'] or '—'}")
                with c3:
                    st.markdown("#### 📋 Facturación")
                    st.markdown(f"**Método de Pago:** {row['payment_method']}")
                    pagado = "✅ Sí" if row['is_paid'] else "❌ No"
                    st.markdown(f"**Pagado:** {pagado}")
                    st.markdown(f"**Factura Ext:** {row['invoice_number'] or '—'}")

                st.markdown("#### 🛒 Productos")
                df_items = pd.read_sql("""
                    SELECT p.sku AS SKU, p.name AS Producto, oi.quantity AS Cant,
                           oi.applied_discount AS Dcto, oi.unit_price AS Precio,
                           (oi.quantity * oi.unit_price) AS Subtotal
                    FROM order_items oi JOIN products p ON oi.product_id = p.id
                    WHERE oi.order_id = %s
                """, conn, params=(order_id_sel,))
                
                df_items['Dcto'] = df_items['Dcto'].apply(lambda x: f"{int(x*100)}%")
                st.dataframe(df_items, use_container_width=True, hide_index=True)
                
                st.markdown(f"## 💵 **Total del Pedido: ${row['total_amount']:,.2f}**")
        else:
            st.info("☝️ Selecciona un pedido arriba para ver todo su detalle y productos.")

# ─── PESTAÑA 2: APROBAR PAGOS ─────────────────────────────────────────────────
with tab2:
    st.subheader("Aprobar Pago y Registrar Factura")
    st.caption("👆 Haz clic en un pedido pendiente para aprobarlo y enviarlo a Logística.")

    df_pending = pd.read_sql("""
        SELECT id, order_number AS "N° Pedido", order_date AS "Fecha",
               customer_name AS "Cliente", payment_method AS "Método Pago",
               total_amount AS "Total"
        FROM orders
        WHERE status = 'PENDING_PAYMENT' OR (payment_method = 'Contra Entrega' AND invoice_number IS NULL)
    """, conn)

    if df_pending.empty:
        st.info("No hay pedidos pendientes de verificación de pago en este momento.")
    else:
        event_pend = st.dataframe(
            df_pending.drop(columns=['id']),
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="tabla_aprobar"
        )

        selected_pend = event_pend.selection.rows
        if selected_pend and selected_pend[0] < len(df_pending):
            row_p = df_pending.iloc[selected_pend[0]]
            with st.container(border=True):
                st.markdown(f"#### Aprobando Pedido: `{row_p['N° Pedido']}` — {row_p['Cliente']}")
                
                col1, col2 = st.columns(2)
                with col1:
                    payment_status = st.radio("Estado del Pago", ["Pagado", "Es Contra Entrega", "Producto en Consignación"], key=f"rad_pay_{row_p['id']}")
                with col2:
                    invoice_num = st.text_input("Número de Factura Externa (si se facturó)", key=f"inv_pay_{row_p['id']}")

                if st.button("✅ Confirmar y Enviar a Logística", type="primary", key=f"btn_pay_{row_p['id']}"):
                    try:
                        c = conn.cursor()
                        is_paid = True if payment_status == "Pagado" else False
                        c.execute("""
                            UPDATE orders
                            SET is_paid = %s, invoice_number = %s, status = 'PENDING_DISPATCH'
                            WHERE id = %s
                        """, (is_paid, invoice_num, int(row_p['id'])))
                        conn.commit()
                        st.success(f"Pedido {row_p['N° Pedido']} aprobado. Pasó a Logística.")
                        st.rerun()
                    except Exception as e:
                        conn.rollback()
                        st.error(f"Error: {e}")
        else:
            st.info("☝️ Selecciona un pedido de la tabla para gestionarlo.")

# ─── PESTAÑA 3: MODIFICAR PAGO / FACTURA ──────────────────────────────────────
with tab3:
    st.subheader("Corregir o Modificar Pago y Factura")
    st.caption("👆 Selecciona un pedido para corregir su estado de pago, número de factura o método de pago.")

    df_mod = pd.read_sql("""
        SELECT id, order_number AS "N° Pedido", order_date AS "Fecha",
               customer_name AS "Cliente", payment_method AS "Pago",
               CASE WHEN is_paid=TRUE THEN 'Sí' ELSE 'No' END AS "Pagado",
               invoice_number AS "Factura"
        FROM orders
        WHERE status IN ('PENDING_PAYMENT', 'PENDING_DISPATCH', 'DISPATCHED', 'DELIVERED')
        ORDER BY created_at DESC
    """, conn)

    if df_mod.empty:
        st.info("No hay pedidos disponibles para modificar.")
    else:
        event_mod = st.dataframe(
            df_mod.drop(columns=['id']),
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="tabla_mod_cartera"
        )

        selected_mod = event_mod.selection.rows
        if selected_mod and selected_mod[0] < len(df_mod):
            row_mod = df_mod.iloc[selected_mod[0]]
            order_id_mod = int(row_mod['id'])
            
            # Traer data completa
            df_full_mod = pd.read_sql("SELECT * FROM orders WHERE id=%s", conn, params=(order_id_mod,))
            full_row_mod = df_full_mod.iloc[0]

            with st.container(border=True):
                st.markdown(f"#### Corrigiendo Pedido: `{row_mod['N° Pedido']}`")
                
                col1, col2, col3 = st.columns(3)
                pay_status_opts = ["Pagado", "No Pagado / Contra Entrega", "Producto en Consignación"]
                current_is_paid_label = "Pagado" if full_row_mod['is_paid'] else "No Pagado / Contra Entrega"

                with col1:
                    new_pay_status = st.radio("Estado del Pago", pay_status_opts,
                        index=pay_status_opts.index(current_is_paid_label) if current_is_paid_label in pay_status_opts else 1,
                        key=f"mod_rad_{order_id_mod}")
                with col2:
                    new_invoice = st.text_input("Número de Factura",
                        value=full_row_mod['invoice_number'] or "", key=f"mod_inv_{order_id_mod}")
                with col3:
                    pay_method_opts = ["Efectivo", "Wompy", "Contra Entrega", "Bancolombia",
                                       "Nequi", "Davivienda", "Canje por Publicidad", "Embajador"]
                    curr_method = full_row_mod['payment_method']
                    new_pay_method = st.selectbox("Corregir Método de Pago", pay_method_opts,
                        index=pay_method_opts.index(curr_method) if curr_method in pay_method_opts else 0,
                        key=f"mod_sel_{order_id_mod}")

                if st.button("💾 Guardar Corrección", type="primary", key=f"mod_btn_{order_id_mod}"):
                    try:
                        c = conn.cursor()
                        new_is_paid = True if new_pay_status == "Pagado" else False
                        c.execute("""
                            UPDATE orders
                            SET is_paid = %s, invoice_number = %s, payment_method = %s
                            WHERE id = %s
                        """, (new_is_paid, new_invoice, new_pay_method, order_id_mod))
                        conn.commit()
                        st.success("¡Corrección guardada exitosamente!")
                        st.rerun()
                    except Exception as e:
                        conn.rollback()
                        st.error(f"Error: {e}")
        else:
            st.info("☝️ Selecciona un pedido para editar sus datos financieros.")

# ─── PESTAÑA 4: CANCELAR ──────────────────────────────────────────────────────
with tab4:
    st.subheader("Cancelar Pedido desde Cartera")
    st.caption("👆 Haz clic en un pedido pendiente de pago para cancelarlo.")

    df_cancel = pd.read_sql("""
        SELECT id, order_number AS "N° Pedido", order_date AS "Fecha",
               customer_name AS "Cliente", payment_method AS "Pago",
               total_amount AS "Total"
        FROM orders
        WHERE status = 'PENDING_PAYMENT'
    """, conn)

    if df_cancel.empty:
        st.info("No hay pedidos pendientes de pago para cancelar desde Cartera.")
    else:
        event_cancel = st.dataframe(
            df_cancel.drop(columns=['id']),
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="tabla_cancel_cartera"
        )

        selected_cancel = event_cancel.selection.rows
        if selected_cancel and selected_cancel[0] < len(df_cancel):
            row_c = df_cancel.iloc[selected_cancel[0]]
            with st.container(border=True):
                st.warning(f"¿Cancelar el pedido **{row_c['N° Pedido']}** de **{row_c['Cliente']}**?")
                if st.button("❌ Sí, cancelar este pedido", type="primary", key="btn_cancel_cartera"):
                    try:
                        c = conn.cursor()
                        c.execute("UPDATE orders SET status='CANCELLED' WHERE id=%s", (int(row_c['id']),))
                        conn.commit()
                        st.success("¡Pedido cancelado exitosamente desde Cartera!")
                        st.rerun()
                    except Exception as e:
                        conn.rollback()
                        st.error(f"Error: {e}")
        else:
            st.info("☝️ Selecciona un pedido para cancelarlo.")
