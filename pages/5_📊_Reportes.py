import streamlit as st
import database
import warnings
warnings.filterwarnings('ignore', category=UserWarning)
import pandas as pd
import plotly.express as px
from io import BytesIO
import os
from datetime import date, timedelta

if "password_correct" not in st.session_state or not st.session_state["password_correct"]:
    st.warning("Por favor inicia sesión desde la página principal.")
    st.stop()

role = st.session_state["role"]
if role not in ["Admin", "Ventas", "Cartera", "Logistica"]:
    st.error("No tienes permisos para acceder a Reportes.")
    st.stop()

st.set_page_config(layout="wide", page_title="Dashboard de Ventas")
st.title("📊 Dashboard de Inteligencia de Negocios (BI)")

conn = database.get_connection()

# Extraer todos los datos (incluyendo payment_method)
query_ventas = """
    SELECT o.id, o.order_number, o.external_order_id, o.order_date, o.customer_name, o.customer_cedula,
           o.customer_phone, o.customer_city, o.sales_channel, o.payment_method, o.status, o.total_amount, o.tracking_number,
           i.quantity, i.unit_price, p.name as product_name, p.category
    FROM orders o
    JOIN order_items i ON o.id = i.order_id
    JOIN products p ON i.product_id = p.id
    WHERE o.status != 'CANCELLED'
"""
df_ventas = pd.read_sql(query_ventas, conn)

if df_ventas.empty:
    st.info("Aún no hay datos de ventas para mostrar en el Dashboard.")
    st.stop()

# Convertir fechas asegurando que sean objetos de tipo date para filtrar fácilmente
df_ventas['order_date'] = pd.to_datetime(df_ventas['order_date']).dt.date

# ─── BARRA LATERAL: FILTROS GLOBALES ──────────────────────────────────────────
st.sidebar.header("🔍 Filtros Dinámicos")

# Rango de fechas (Default: últimos 30 días)
min_date = df_ventas['order_date'].min()
max_date = df_ventas['order_date'].max()
default_start = max_date - timedelta(days=30)
if default_start < min_date:
    default_start = min_date

fechas = st.sidebar.date_input("📅 Rango de Fechas", value=(default_start, max_date), min_value=min_date, max_value=max_date)

# Text Input para cliente
cliente_filtro = st.sidebar.text_input("👤 Buscar Cliente (Nombre)").lower()

# Multiselects
productos = sorted(df_ventas['product_name'].unique().tolist())
prod_filtro = st.sidebar.multiselect("📦 Filtrar por Producto", options=productos, default=[])

canales = sorted(df_ventas['sales_channel'].dropna().unique().tolist())
canal_filtro = st.sidebar.multiselect("📱 Canal de Venta", options=canales, default=[])

metodos = sorted(df_ventas['payment_method'].dropna().unique().tolist())
pago_filtro = st.sidebar.multiselect("💳 Método de Pago", options=metodos, default=[])

# ─── APLICAR FILTROS ──────────────────────────────────────────────────────────
df_filtrado = df_ventas.copy()

if isinstance(fechas, tuple) and len(fechas) == 2:
    start_d, end_d = fechas
    df_filtrado = df_filtrado[(df_filtrado['order_date'] >= start_d) & (df_filtrado['order_date'] <= end_d)]
elif isinstance(fechas, tuple) and len(fechas) == 1:
    df_filtrado = df_filtrado[df_filtrado['order_date'] >= fechas[0]]
elif fechas:
    df_filtrado = df_filtrado[df_filtrado['order_date'] == fechas]

if cliente_filtro:
    df_filtrado = df_filtrado[df_filtrado['customer_name'].str.lower().str.contains(cliente_filtro, na=False)]

if prod_filtro:
    df_filtrado = df_filtrado[df_filtrado['product_name'].isin(prod_filtro)]

if canal_filtro:
    df_filtrado = df_filtrado[df_filtrado['sales_channel'].isin(canal_filtro)]

if pago_filtro:
    df_filtrado = df_filtrado[df_filtrado['payment_method'].isin(pago_filtro)]

# Detener si no hay datos tras filtrar
if df_filtrado.empty:
    st.warning("⚠️ No hay datos que coincidan con los filtros seleccionados.")
    st.stop()


# ─── KPIs (INDICADORES CLAVE) ─────────────────────────────────────────────────
# Para KPIs financieros, es vital contar por pedido único (no sumar el total por cada producto del mismo pedido)
df_pedidos_unicos = df_filtrado.drop_duplicates(subset=['order_number'])

total_ingresos = df_pedidos_unicos['total_amount'].sum()
total_pedidos = df_pedidos_unicos['order_number'].nunique()
ticket_promedio = total_ingresos / total_pedidos if total_pedidos > 0 else 0
unidades_vendidas = df_filtrado['quantity'].sum()

col1, col2, col3, col4 = st.columns(4)
col1.metric("💵 Ingresos Totales", f"${total_ingresos:,.2f}")
col2.metric("🛍️ Total de Pedidos", f"{total_pedidos}")
col3.metric("🎟️ Ticket Promedio", f"${ticket_promedio:,.2f}")
col4.metric("📦 Unidades Vendidas", f"{unidades_vendidas:,.0f}")

st.divider()

# ─── GRÁFICAS ILUSTRATIVAS (PLOTLY) ───────────────────────────────────────────
# Fila 1 de Gráficos: Tendencias e Ingresos por Canal
row1_col1, row1_col2 = st.columns([2, 1])

with row1_col1:
    st.markdown("#### 📈 Tendencia de Ingresos Diarios")
    ventas_diarias = df_pedidos_unicos.groupby('order_date')['total_amount'].sum().reset_index()
    if not ventas_diarias.empty:
        fig_area = px.bar(ventas_diarias, x='order_date', y='total_amount', 
                           color_discrete_sequence=['#00D2D3'],
                           labels={'order_date': 'Fecha', 'total_amount': 'Ingresos ($)'})
        fig_area.update_layout(margin=dict(l=0, r=0, t=30, b=0), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_area, use_container_width=True)

with row1_col2:
    st.markdown("#### 📱 Ventas por Canal")
    canal_agg = df_pedidos_unicos.groupby('sales_channel')['total_amount'].sum().reset_index()
    if not canal_agg.empty:
        fig_canal = px.pie(canal_agg, values='total_amount', names='sales_channel', hole=0.5,
                           color_discrete_sequence=px.colors.qualitative.Pastel)
        fig_canal.update_traces(textposition='inside', textinfo='percent+label', showlegend=False)
        fig_canal.update_layout(margin=dict(l=0, r=0, t=30, b=0), paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_canal, use_container_width=True)

# Fila 2 de Gráficos: Top Productos y Métodos de Pago
st.write("")
row2_col1, row2_col2 = st.columns([2, 1])

with row2_col1:
    st.markdown("#### 🏆 Top Productos más Vendidos (Cantidad)")
    prod_agg = df_filtrado.groupby('product_name')['quantity'].sum().reset_index().sort_values(by='quantity', ascending=True).tail(10)
    if not prod_agg.empty:
        fig_bar = px.bar(prod_agg, x='quantity', y='product_name', orientation='h',
                         color='quantity', color_continuous_scale='Teal',
                         labels={'quantity': 'Unidades', 'product_name': ''})
        fig_bar.update_layout(margin=dict(l=0, r=0, t=30, b=0), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", showlegend=False)
        st.plotly_chart(fig_bar, use_container_width=True)

with row2_col2:
    st.markdown("#### 💳 Pagos por Método")
    pago_agg = df_pedidos_unicos.groupby('payment_method')['total_amount'].sum().reset_index()
    if not pago_agg.empty:
        fig_pago = px.pie(pago_agg, values='total_amount', names='payment_method', hole=0.5,
                          color_discrete_sequence=px.colors.qualitative.Set3)
        fig_pago.update_traces(textposition='inside', textinfo='percent+label', showlegend=False)
        fig_pago.update_layout(margin=dict(l=0, r=0, t=30, b=0), paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_pago, use_container_width=True)


st.divider()

# ─── TABLA DE DATOS Y EXPORTACIÓN ─────────────────────────────────────────────
st.markdown("### 📑 Base de Datos Filtrada (Vista Detallada)")

output = BytesIO()
with pd.ExcelWriter(output, engine='openpyxl') as writer:
    df_excel = df_filtrado.copy()
    df_excel.rename(columns={
        'order_number': 'Número Pedido', 'external_order_id': 'ID Externo', 
        'order_date': 'Fecha', 'customer_name': 'Cliente', 'customer_cedula': 'Cédula', 
        'customer_phone': 'Teléfono', 'customer_city': 'Ciudad', 'sales_channel': 'Canal', 
        'payment_method': 'Método Pago', 'status': 'Estado OMS', 'tracking_number': 'Guía Coordinadora', 
        'product_name': 'Producto', 'category': 'Categoría', 'quantity': 'Cant', 'unit_price': 'Precio Unit.', 
        'total_amount': 'Total Pedido'
    }, inplace=True)
    df_excel.drop(columns=['id'], inplace=True, errors='ignore')
    
    df_excel.to_excel(writer, index=False, sheet_name='Reporte OMS')

excel_data = output.getvalue()

col_btn1, col_btn2 = st.columns(2)

with col_btn1:
    st.download_button(
        label="📥 Exportar Resultados a Excel (.xlsx)",
        data=excel_data,
        file_name="reporte_ventas_oms.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary"
    )

# Solo el Administrador puede descargar la base de datos cruda completa
if role == "Admin":
    with col_btn2:
        db_path = "oms_system.db"
        if os.path.exists(db_path):
            with open(db_path, "rb") as f:
                db_data = f.read()
            st.download_button(
                label="⚙️ Descargar Copia de Seguridad SQLite Antigua (.db)",
                data=db_data,
                file_name="oms_system_backup.db",
                mime="application/octet-stream",
                help="Base de datos antigua en SQLite."
            )

st.dataframe(df_filtrado[['order_date', 'order_number', 'customer_name', 'product_name', 'quantity', 'total_amount', 'sales_channel', 'payment_method', 'status']], use_container_width=True)
