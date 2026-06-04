import streamlit as st
import database
import warnings
warnings.filterwarnings('ignore', category=UserWarning)
import pandas as pd
import requests

if "password_correct" not in st.session_state or not st.session_state["password_correct"]:
    st.warning("Por favor inicia sesión desde la página principal.")
    st.stop()

role = st.session_state["role"]
if role not in ["Admin", "Logistica", "Ventas"]:
    st.error("No tienes permisos para acceder a Logística.")
    st.stop()

st.title("🚚 Logística y Despachos")
conn = database.get_connection()

tab1, tab_ce, tab2, tab3 = st.tabs(["📦 Pedidos (Pagados)", "💵 Pedidos (Contra Entrega)", "🔍 Rastrear Guías", "❌ Cancelar Pedido"])

# ─── PESTAÑA 1: DESPACHAR ─────────────────────────────────────────────────────
with tab1:
    st.subheader("Pedidos Pagados listos para despachar")
    st.caption("👆 Haz clic en un pedido de la tabla para ver su detalle y gestionar el despacho.")

    df_dispatch = pd.read_sql("""
        SELECT o.id, o.order_number AS "N° Pedido", o.order_date AS "Fecha",
               o.customer_name AS "Cliente", o.customer_cedula AS "Cédula", o.customer_city AS "Ciudad",
               o.customer_phone AS "Teléfono", o.customer_address AS "Dirección",
               o.customer_department AS "Departamento",
               o.payment_method AS "Método Pago",
               CASE WHEN o.is_paid=TRUE THEN '✅ Pagado' ELSE '❌ Cobrar en destino' END AS "Estado Pago",
               o.total_amount AS "Total", o.tracking_number AS "Guía Actual",
               o.external_order_id AS "ID Externo",
               o.sales_channel AS "Canal",
               o.created_by AS "Vendedor",
               o.invoice_number AS "Factura"
        FROM orders o
        WHERE o.status = 'PENDING_DISPATCH' AND o.payment_method != 'Contra Entrega'
        ORDER BY o.created_at DESC
    """, conn)

    if df_dispatch.empty:
        st.info("No hay pedidos pendientes de despacho en este momento.")
    else:
        event = st.dataframe(
            df_dispatch.drop(columns=['id']),
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="tabla_despacho_pagados"
        )

        selected_rows = event.selection.rows
        if selected_rows and selected_rows[0] < len(df_dispatch):
            row = df_dispatch.iloc[selected_rows[0]]
            order_id = int(row['id'])

            st.divider()
            st.markdown(f"### Pedido seleccionado: `{row['N° Pedido']}` — {row['Cliente']}")

            # Datos del cliente resumidos para crear la guía
            with st.container(border=True):
                st.markdown("#### 📦 Datos Completos del Pedido")
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    st.markdown("##### 🧾 Cliente")
                    st.markdown(f"**Nombre:** {row['Cliente']}")
                    st.markdown(f"**Cédula / NIT:** {row['Cédula']}")
                    st.markdown(f"**Teléfono:** {row['Teléfono'] or 'Sin registrar'}")
                with c2:
                    st.markdown("##### 📍 Destino")
                    st.markdown(f"**Dirección:** {row['Dirección'] or 'Sin registrar'}")
                    st.markdown(f"**Ciudad:** {row['Ciudad'] or 'Sin registrar'}")
                    st.markdown(f"**Depto:** {row['Departamento'] or 'Sin registrar'}")
                with c3:
                    st.markdown("##### 📋 Facturación y Envío")
                    st.markdown(f"**Medio de Pago:** {row['Método Pago']}")
                    st.markdown(f"**Pagado:** {row['Estado Pago']}")
                    st.markdown(f"**Factura Ext:** {row['Factura'] or 'Sin factura'}")
                    st.markdown(f"**Guía Coord:** {row['Guía Actual'] or 'Sin guía asignada'}")
                    if row['Estado Pago'] == '❌ Cobrar en destino':
                        st.error(f"Cobrar en destino: **${row['Total']:,.2f}**")
                with c4:
                    st.markdown("##### ℹ️ Info Comercial")
                    st.markdown(f"**Fecha:** {row['Fecha']}")
                    st.markdown(f"**Canal:** {row['Canal']}")
                    st.markdown(f"**ID Externo:** {row['ID Externo'] or 'Sin ID'}")
                    st.markdown(f"**Vendedor:** {row['Vendedor']}")

                # Productos del pedido
                df_items = pd.read_sql("""
                    SELECT p.name AS "Producto", oi.quantity AS "Cantidad",
                           oi.unit_price AS "Precio Unit.",
                           (oi.quantity * oi.unit_price) AS "Subtotal"
                    FROM order_items oi JOIN products p ON oi.product_id = p.id
                    WHERE oi.order_id = %s
                """, conn, params=(order_id,))
                st.markdown("**Contenido del paquete:**")
                st.dataframe(df_items, use_container_width=True, hide_index=True)
                st.markdown(f"**💵 Valor declarado total: ${row['Total']:,.2f}**")

            # Formulario de despacho
            if role in ["Admin", "Logistica"]:
                with st.container(border=True):
                    st.markdown("#### 🚚 Confirmar Despacho")
                    guia_actual = row['Guía Actual']
                    if guia_actual:
                        st.info(f"Guía registrada actualmente: `{guia_actual}`")

                    new_tracking = st.text_input("Número de Guía Coordinadora",
                                                  value=guia_actual or "",
                                                  placeholder="Ej: 9876543210",
                                                  key=f"tracking_p_{order_id}")

                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("✅ Confirmar Despacho y Descontar Inventario",
                                     type="primary", key=f"dispatch_p_{order_id}"):
                            if not new_tracking:
                                st.error("Ingresa el número de guía.")
                            else:
                                try:
                                    c = conn.cursor()
                                    c.execute("SELECT product_id, quantity FROM order_items WHERE order_id = %s", (order_id,))
                                    for prod_id, qty in c.fetchall():
                                        c.execute("INSERT INTO inventory_movements (product_id, type, quantity, reference_id) VALUES (%s, 'OUT', %s, %s)",
                                                  (prod_id, qty, row['N° Pedido']))
                                        c.execute("UPDATE products SET current_stock = current_stock - %s WHERE id = %s", (qty, prod_id))
                                    c.execute("UPDATE orders SET status='DISPATCHED', tracking_number=%s WHERE id=%s",
                                              (new_tracking, order_id))
                                    conn.commit()
                                    st.success(f"¡Pedido {row['N° Pedido']} despachado con guía {new_tracking}! Inventario descontado.")
                                    st.rerun()
                                except Exception as e:
                                    conn.rollback()
                                    st.error(f"Error: {e}")
                    with col_btn2:
                        if guia_actual and st.button("✏️ Solo actualizar guía (sin descontar inventario)",
                                                      key=f"update_track_p_{order_id}"):
                            if not new_tracking:
                                st.error("Ingresa el número de guía.")
                            else:
                                try:
                                    c = conn.cursor()
                                    c.execute("UPDATE orders SET tracking_number=%s WHERE id=%s", (new_tracking, order_id))
                                    conn.commit()
                                    st.success(f"Guía actualizada a {new_tracking}.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error: {e}")
        else:
            st.info("☝️ Selecciona un pedido de la tabla para ver los detalles y gestionar el despacho.")

# ─── PESTAÑA CONTRA ENTREGA ──────────────────────────────────────────────────
with tab_ce:
    st.subheader("Pedidos Contra Entrega listos para despachar")
    st.caption("👆 Haz clic en un pedido de la tabla para ver su detalle y gestionar el despacho.")

    df_dispatch = pd.read_sql("""
        SELECT o.id, o.order_number AS "N° Pedido", o.order_date AS "Fecha",
               o.customer_name AS "Cliente", o.customer_cedula AS "Cédula", o.customer_city AS "Ciudad",
               o.customer_phone AS "Teléfono", o.customer_address AS "Dirección",
               o.customer_department AS "Departamento",
               o.payment_method AS "Método Pago",
               CASE WHEN o.is_paid=TRUE THEN '✅ Pagado' ELSE '❌ Cobrar en destino' END AS "Estado Pago",
               o.total_amount AS "Total", o.tracking_number AS "Guía Actual",
               o.external_order_id AS "ID Externo",
               o.sales_channel AS "Canal",
               o.created_by AS "Vendedor",
               o.invoice_number AS "Factura"
        FROM orders o
        WHERE o.status = 'PENDING_DISPATCH' AND o.payment_method = 'Contra Entrega'
        ORDER BY o.created_at DESC
    """, conn)

    if df_dispatch.empty:
        st.info("No hay pedidos pendientes de despacho en este momento.")
    else:
        event = st.dataframe(
            df_dispatch.drop(columns=['id']),
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="tabla_despacho_ce"
        )

        selected_rows = event.selection.rows
        if selected_rows and selected_rows[0] < len(df_dispatch):
            row = df_dispatch.iloc[selected_rows[0]]
            order_id = int(row['id'])

            st.divider()
            st.markdown(f"### Pedido seleccionado: `{row['N° Pedido']}` — {row['Cliente']}")

            # Datos del cliente resumidos para crear la guía
            with st.container(border=True):
                st.markdown("#### 📦 Datos Completos del Pedido")
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    st.markdown("##### 🧾 Cliente")
                    st.markdown(f"**Nombre:** {row['Cliente']}")
                    st.markdown(f"**Cédula / NIT:** {row['Cédula']}")
                    st.markdown(f"**Teléfono:** {row['Teléfono'] or 'Sin registrar'}")
                with c2:
                    st.markdown("##### 📍 Destino")
                    st.markdown(f"**Dirección:** {row['Dirección'] or 'Sin registrar'}")
                    st.markdown(f"**Ciudad:** {row['Ciudad'] or 'Sin registrar'}")
                    st.markdown(f"**Depto:** {row['Departamento'] or 'Sin registrar'}")
                with c3:
                    st.markdown("##### 📋 Facturación y Envío")
                    st.markdown(f"**Medio de Pago:** {row['Método Pago']}")
                    st.markdown(f"**Pagado:** {row['Estado Pago']}")
                    st.markdown(f"**Factura Ext:** {row['Factura'] or 'Sin factura'}")
                    st.markdown(f"**Guía Coord:** {row['Guía Actual'] or 'Sin guía asignada'}")
                    if row['Estado Pago'] == '❌ Cobrar en destino':
                        st.error(f"Cobrar en destino: **${row['Total']:,.2f}**")
                with c4:
                    st.markdown("##### ℹ️ Info Comercial")
                    st.markdown(f"**Fecha:** {row['Fecha']}")
                    st.markdown(f"**Canal:** {row['Canal']}")
                    st.markdown(f"**ID Externo:** {row['ID Externo'] or 'Sin ID'}")
                    st.markdown(f"**Vendedor:** {row['Vendedor']}")

                # Productos del pedido
                df_items = pd.read_sql("""
                    SELECT p.name AS "Producto", oi.quantity AS "Cantidad",
                           oi.unit_price AS "Precio Unit.",
                           (oi.quantity * oi.unit_price) AS "Subtotal"
                    FROM order_items oi JOIN products p ON oi.product_id = p.id
                    WHERE oi.order_id = %s
                """, conn, params=(order_id,))
                st.markdown("**Contenido del paquete:**")
                st.dataframe(df_items, use_container_width=True, hide_index=True)
                st.markdown(f"**💵 Valor declarado total: ${row['Total']:,.2f}**")

            # Formulario de despacho
            if role in ["Admin", "Logistica"]:
                with st.container(border=True):
                    st.markdown("#### 🚚 Confirmar Despacho")
                    guia_actual = row['Guía Actual']
                    if guia_actual:
                        st.info(f"Guía registrada actualmente: `{guia_actual}`")

                    new_tracking = st.text_input("Número de Guía Coordinadora",
                                                  value=guia_actual or "",
                                                  placeholder="Ej: 9876543210",
                                                  key=f"tracking_ce_{order_id}")

                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("✅ Confirmar Despacho y Descontar Inventario",
                                     type="primary", key=f"dispatch_ce_{order_id}"):
                            if not new_tracking:
                                st.error("Ingresa el número de guía.")
                            else:
                                try:
                                    c = conn.cursor()
                                    c.execute("SELECT product_id, quantity FROM order_items WHERE order_id = %s", (order_id,))
                                    for prod_id, qty in c.fetchall():
                                        c.execute("INSERT INTO inventory_movements (product_id, type, quantity, reference_id) VALUES (%s, 'OUT', %s, %s)",
                                                  (prod_id, qty, row['N° Pedido']))
                                        c.execute("UPDATE products SET current_stock = current_stock - %s WHERE id = %s", (qty, prod_id))
                                    c.execute("UPDATE orders SET status='DISPATCHED', tracking_number=%s WHERE id=%s",
                                              (new_tracking, order_id))
                                    conn.commit()
                                    st.success(f"¡Pedido {row['N° Pedido']} despachado con guía {new_tracking}! Inventario descontado.")
                                    st.rerun()
                                except Exception as e:
                                    conn.rollback()
                                    st.error(f"Error: {e}")
                    with col_btn2:
                        if guia_actual and st.button("✏️ Solo actualizar guía (sin descontar inventario)",
                                                      key=f"update_track_ce_{order_id}"):
                            if not new_tracking:
                                st.error("Ingresa el número de guía.")
                            else:
                                try:
                                    c = conn.cursor()
                                    c.execute("UPDATE orders SET tracking_number=%s WHERE id=%s", (new_tracking, order_id))
                                    conn.commit()
                                    st.success(f"Guía actualizada a {new_tracking}.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error: {e}")
        else:
            st.info("☝️ Selecciona un pedido de la tabla para ver los detalles y gestionar el despacho.")

# ─── PESTAÑA 2: RASTREAR ──────────────────────────────────────────────────────
with tab2:
    st.subheader("Historial de envíos y rastreo")
    st.caption("👆 Haz clic en un pedido para consultar su estado en Coordinadora.")

    df_history = pd.read_sql("""
        SELECT id, order_number AS "N° Pedido", tracking_number AS "Guía",
               customer_name AS "Cliente", customer_cedula AS "Cédula",
               customer_phone AS "Teléfono", customer_address AS "Dirección",
               customer_city AS "Ciudad", customer_department AS "Departamento",
               status AS "Estado"
        FROM orders
        WHERE status IN ('DISPATCHED', 'DELIVERED')
        ORDER BY created_at DESC
    """, conn)

    def rastrear_guia_real(guia):
        try:
            url = f"https://www.coordinadora.com/portafolio-de-servicios/servicios-en-linea/rastrear-guias/?guia={guia}"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                text = response.text.lower()
                if "entregado" in text or "entrega exitosa" in text:
                    return "✅ Entregado Exitosamente"
                elif "en reparto" in text or "reparto" in text:
                    return "🚴 En Reparto"
                elif "novedad" in text:
                    return "⚠️ Novedad en la entrega"
                elif "tránsito" in text or "transito" in text:
                    return "🚚 En Tránsito"
                else:
                    return "❓ No se pudo extraer el estado (página protegida)"
            return f"Error HTTP {response.status_code}"
        except Exception as e:
            return f"Error de conexión: {str(e)}"

    if df_history.empty:
        st.write("Aún no hay pedidos despachados.")
    else:
        event_hist = st.dataframe(
            df_history.drop(columns=['id']),
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="tabla_historial"
        )

        selected_hist = event_hist.selection.rows
        if selected_hist and selected_hist[0] < len(df_history):
            row_h = df_history.iloc[selected_hist[0]]
            guia = row_h['Guía']

            with st.container(border=True):
                st.markdown(f"**Pedido:** `{row_h['N° Pedido']}` | **Guía:** `{guia}` | **Cliente:** {row_h['Cliente']}")
                if st.button("🔍 Consultar último estado en Coordinadora", type="primary", key="btn_rastrear"):
                    with st.spinner(f"Consultando la guía {guia} en Coordinadora..."):
                        estado = rastrear_guia_real(guia)
                    if "Entregado" in estado:
                        st.success(f"**Último Estado:** {estado}")
                        c = conn.cursor()
                        c.execute("UPDATE orders SET status='DELIVERED' WHERE tracking_number=%s", (guia,))
                        conn.commit()
                        st.toast("Pedido marcado como ENTREGADO en la base de datos.")
                    elif "Error" in estado or "No se pudo" in estado:
                        st.warning(estado)
                    else:
                        st.info(f"**Último Estado:** {estado}")
        else:
            st.info("☝️ Selecciona un pedido de la tabla para rastrear su guía.")

# ─── PESTAÑA 3: CANCELAR ──────────────────────────────────────────────────────
with tab3:
    if role not in ["Admin", "Logistica"]:
        st.error("Solo el personal de Logística puede cancelar pedidos desde este módulo.")
    else:
        st.subheader("Cancelar Pedido")
        st.caption("👆 Haz clic en un pedido de la tabla para cancelarlo.")

        df_cancel_log = pd.read_sql("""
            SELECT id, order_number AS "N° Pedido", order_date AS "Fecha",
                   customer_name AS "Cliente", total_amount AS "Total"
            FROM orders WHERE status = 'PENDING_DISPATCH'
        """, conn)

        if df_cancel_log.empty:
            st.info("No hay pedidos listos para despachar que se puedan cancelar.")
        else:
            event_cancel = st.dataframe(
                df_cancel_log.drop(columns=['id']),
                use_container_width=True,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
                key="tabla_cancel_log"
            )
            selected_cancel = event_cancel.selection.rows
            if selected_cancel and selected_cancel[0] < len(df_cancel_log):
                row_c = df_cancel_log.iloc[selected_cancel[0]]
                with st.container(border=True):
                    st.warning(f"¿Cancelar el pedido **{row_c['N° Pedido']}** de **{row_c['Cliente']}**?")
                    if st.button("❌ Sí, cancelar este pedido", type="primary", key="btn_cancel_log"):
                        try:
                            c = conn.cursor()
                            c.execute("UPDATE orders SET status='CANCELLED' WHERE id=%s", (int(row_c['id']),))
                            conn.commit()
                            st.success("¡Pedido cancelado exitosamente!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")
            else:
                st.info("☝️ Selecciona un pedido de la tabla para cancelarlo.")
