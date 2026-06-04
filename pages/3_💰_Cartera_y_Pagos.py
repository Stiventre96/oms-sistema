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

tab1, tab2, tab3 = st.tabs(["Gestión de Cartera y Pagos", "Control Contra Entrega", "Cancelar Pedidos"])

# ─── PESTAÑA 1: GESTIÓN DE CARTERA ────────────────────────────────────────────
with tab1:
    st.subheader("Gestión General de Pedidos")
    st.caption("👆 Haz clic en un pedido para ver sus detalles y aprobarlo o modificar su facturación.")

    col_f1, _ = st.columns([2, 1])
    with col_f1:
        estado_filtro = st.selectbox("Filtrar por Estado", ["Todos", "Pendiente de Pago", "Listo para Despachar", "Despachado", "Entregado", "Contra Entrega Sin Factura"], key="filtro_general")
    estado_map = {
        "Todos": None, "Pendiente de Pago": "PENDING_PAYMENT",
        "Listo para Despachar": "PENDING_DISPATCH", "Despachado": "DISPATCHED", "Entregado": "DELIVERED"
    , "Contra Entrega Sin Factura": "CONTRA_ENTREGA_SIN_FACTURA"}

    where_clause = ""
    if estado_map[estado_filtro] == "CONTRA_ENTREGA_SIN_FACTURA":
        where_clause = "WHERE o.payment_method = 'Contra Entrega' AND (o.invoice_number IS NULL OR o.invoice_number = '') AND o.status IN ('PENDING_DISPATCH', 'DISPATCHED', 'DELIVERED')"
    elif estado_map[estado_filtro]:
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
               o.total_amount AS "Total",
               o.status AS raw_status,
               o.is_paid,
               o.invoice_number
        FROM orders o
        {where_clause}
        ORDER BY o.created_at DESC
    """, conn)

    if df_orders.empty:
        st.info("No hay pedidos para mostrar con el filtro seleccionado.")
    else:
        # Hide raw status, is_paid and invoice_number from the table
        display_df = df_orders.drop(columns=['id', 'raw_status', 'is_paid', 'invoice_number'])
        event_detail = st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="tabla_gestion_cartera"
        )

        selected_det = event_detail.selection.rows
        if selected_det and selected_det[0] < len(df_orders):
            row_sel = df_orders.iloc[selected_det[0]]
            order_id_sel = int(row_sel['id'])
            
            # Traer los datos crudos completos
            df_full = pd.read_sql("SELECT * FROM orders WHERE id=%s", conn, params=(order_id_sel,))
            row = df_full.iloc[0]

            st.divider()
            with st.container(border=True):
                st.markdown(f"### Pedido: `{row['order_number']}`")
                
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    st.markdown("##### 🧾 Cliente")
                    st.markdown(f"**Nombre:** {row['customer_name']}")
                    st.markdown(f"**Cédula / NIT:** {row['customer_cedula']}")
                    st.markdown(f"**Teléfono:** {row['customer_phone'] or 'Sin registrar'}")
                with c2:
                    st.markdown("##### 📍 Destino")
                    st.markdown(f"**Dirección:** {row['customer_address'] or 'Sin registrar'}")
                    st.markdown(f"**Ciudad:** {row['customer_city'] or 'Sin registrar'}")
                    st.markdown(f"**Depto:** {row['customer_department'] or 'Sin registrar'}")
                with c3:
                    st.markdown("##### 📋 Facturación y Envío")
                    st.markdown(f"**Medio de Pago:** {row['payment_method']}")
                    pagado = "✅ Sí" if row['is_paid'] else "❌ No"
                    st.markdown(f"**Pagado:** {pagado}")
                    st.markdown(f"**Factura Ext:** {row['invoice_number'] or 'Sin factura'}")
                    st.markdown(f"**Guía Coord:** {row['tracking_number'] or 'Sin guía asignada'}")
                with c4:
                    st.markdown("##### ℹ️ Info Comercial")
                    st.markdown(f"**Fecha:** {row['order_date']}")
                    st.markdown(f"**Canal:** {row['sales_channel']}")
                    st.markdown(f"**ID Externo:** {row['external_order_id'] or 'Sin ID'}")
                    st.markdown(f"**Vendedor:** {row['created_by']}")

                st.markdown("#### 🛒 Productos")
                df_items = pd.read_sql("""
                    SELECT p.sku AS "SKU", p.name AS "Producto", oi.quantity AS "Cant",
                           oi.applied_discount AS "Dcto", oi.unit_price AS "Precio",
                           (oi.quantity * oi.unit_price) AS "Subtotal"
                    FROM order_items oi JOIN products p ON oi.product_id = p.id
                    WHERE oi.order_id = %s
                """, conn, params=(order_id_sel,))
                
                df_items['Dcto'] = df_items['Dcto'].apply(lambda x: f"{int(x*100)}%")
                st.dataframe(df_items, use_container_width=True, hide_index=True)
                
                st.markdown(f"## 💵 **Total del Pedido: ${row['total_amount']:,.2f}**")
                
                st.divider()

                # --- ACCIONES DINÁMICAS SEGÚN EL ESTADO ---
                if row['status'] == 'PENDING_PAYMENT' or (row['status'] == 'PENDING_DISPATCH' and row['payment_method'] != 'Contra Entrega' and not row['is_paid']):
                    st.markdown("#### ✅ Aprobar Pago y Enviar a Logística")
                    colA, colB = st.columns(2)
                    with colA:
                        payment_status = st.radio("Estado del Pago", ["Pagado", "Es Contra Entrega", "Producto en Consignación"], key=f"rad_pay_{order_id_sel}")
                    with colB:
                        invoice_num = st.text_input("Número de Factura Externa (si se facturó)", key=f"inv_pay_{order_id_sel}")

                    if st.button("Confirmar y Enviar a Logística", type="primary", key=f"btn_approve_{order_id_sel}"):
                        try:
                            c = conn.cursor()
                            is_paid = True if payment_status == "Pagado" else False
                            c.execute("""
                                UPDATE orders
                                SET is_paid = %s, invoice_number = %s, status = 'PENDING_DISPATCH'
                                WHERE id = %s
                            """, (is_paid, invoice_num, order_id_sel))
                            conn.commit()
                            st.success(f"Pedido {row['order_number']} aprobado. Pasó a Logística.")
                            st.rerun()
                        except Exception as e:
                            conn.rollback()
                            st.error(f"Error: {e}")

                elif row['status'] in ['PENDING_DISPATCH', 'DISPATCHED', 'DELIVERED']:
                    st.markdown("#### ✏️ Corregir o Modificar Pago/Factura")
                    colA, colB, colC = st.columns(3)
                    pay_status_opts = ["Pagado", "No Pagado / Contra Entrega", "Producto en Consignación"]
                    current_is_paid_label = "Pagado" if row['is_paid'] else "No Pagado / Contra Entrega"

                    with colA:
                        new_pay_status = st.radio("Estado del Pago", pay_status_opts,
                            index=pay_status_opts.index(current_is_paid_label) if current_is_paid_label in pay_status_opts else 1,
                            key=f"mod_rad_{order_id_sel}")
                    with colB:
                        new_invoice = st.text_input("Número de Factura",
                            value=row['invoice_number'] or "", key=f"mod_inv_{order_id_sel}")
                    with colC:
                        pay_method_opts = ["Efectivo", "Wompy", "Contra Entrega", "Bancolombia",
                                           "Nequi", "Davivienda", "Canje por Publicidad", "sistecredito", "Embajador"]
                        curr_method = row['payment_method']
                        new_pay_method = st.selectbox("Corregir Método de Pago", pay_method_opts,
                            index=pay_method_opts.index(curr_method) if curr_method in pay_method_opts else 0,
                            key=f"mod_sel_{order_id_sel}")

                    if st.button("💾 Guardar Corrección", type="primary", key=f"mod_btn_{order_id_sel}"):
                        try:
                            c = conn.cursor()
                            new_is_paid = True if new_pay_status == "Pagado" else False
                            c.execute("""
                                UPDATE orders
                                SET is_paid = %s, invoice_number = %s, payment_method = %s
                                WHERE id = %s
                            """, (new_is_paid, new_invoice, new_pay_method, order_id_sel))
                            conn.commit()
                            st.success("¡Corrección guardada exitosamente!")
                            st.rerun()
                        except Exception as e:
                            conn.rollback()
                            st.error(f"Error: {e}")
        else:
            st.info("☝️ Selecciona un pedido de la tabla superior para gestionarlo.")


# ─── PESTAÑA 2: CONTRA ENTREGA ─────────────────────────────────────────────────
with tab2:
    st.subheader("Control de Pedidos Contra Entrega (Pendientes de Cierre)")
    st.caption("👆 Estos pedidos están en logística, despachados o entregados, pero aún no se ha anexado la factura de venta para cerrar la contabilidad.")

    df_ce = pd.read_sql("""
        SELECT o.id, o.order_number AS "N° Pedido", o.order_date AS "Fecha",
               o.customer_name AS "Cliente", o.customer_city AS "Ciudad",
               CASE 
                   WHEN o.status='PENDING_DISPATCH' THEN '📦 En Logística'
                   WHEN o.status='DISPATCHED' THEN '🚚 Despachado'
                   WHEN o.status='DELIVERED' THEN '✅ Entregado'
                   ELSE o.status 
               END AS "Estado de Envío",
               o.tracking_number AS "Guía",
               o.total_amount AS "Total"
        FROM orders o
        WHERE o.payment_method = 'Contra Entrega' 
          AND (o.invoice_number IS NULL OR o.invoice_number = '')
          AND o.status IN ('PENDING_DISPATCH', 'DISPATCHED', 'DELIVERED')
        ORDER BY o.created_at DESC
    """, conn)

    if df_ce.empty:
        st.info("¡Excelente! No hay pedidos Contra Entrega pendientes de anexar factura.")
    else:
        event_ce = st.dataframe(
            df_ce.drop(columns=['id']),
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="tabla_ce"
        )

        selected_ce = event_ce.selection.rows
        if selected_ce and selected_ce[0] < len(df_ce):
            row_ce = df_ce.iloc[selected_ce[0]]
            order_id_ce = int(row_ce['id'])
            
            with st.container(border=True):
                st.markdown(f"#### Cerrando Pedido Contra Entrega: `{row_ce['N° Pedido']}`")
                st.markdown(f"**Cliente:** {row_ce['Cliente']} | **Valor a cobrar:** ${row_ce['Total']:,.2f}")
                st.markdown(f"**Estado de envío:** {row_ce['Estado de Envío']} | **Guía:** {row_ce['Guía'] or 'Sin guía aún'}")
                
                st.divider()
                st.markdown("⚠️ **Cuando la transportadora consigne el dinero, ingresa la factura para cerrar el pedido:**")
                colA, colB = st.columns([1, 2])
                with colA:
                    inv_ce = st.text_input("Número de Factura Externa", key=f"inv_ce_{order_id_ce}")
                with colB:
                    st.write("")
                    st.write("")
                    if st.button("✅ Anexar Factura y Cerrar Pedido (Marcar Pagado)", type="primary", key=f"btn_ce_{order_id_ce}"):
                        if not inv_ce:
                            st.error("Por favor, ingresa el número de factura.")
                        else:
                            try:
                                c = conn.cursor()
                                c.execute("""
                                    UPDATE orders
                                    SET is_paid = TRUE, invoice_number = %s
                                    WHERE id = %s
                                """, (inv_ce, order_id_ce))
                                conn.commit()
                                st.success(f"¡El pedido {row_ce['N° Pedido']} ha sido facturado y cerrado!")
                                st.rerun()
                            except Exception as e:
                                conn.rollback()
                                st.error(f"Error: {e}")
        else:
            st.info("☝️ Selecciona un pedido para anexar su factura y cerrarlo.")


# ─── PESTAÑA 3: CANCELAR ──────────────────────────────────────────────────────
with tab3:
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
