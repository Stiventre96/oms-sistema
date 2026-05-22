import streamlit as st
import database
import warnings
warnings.filterwarnings('ignore', category=UserWarning)
import pandas as pd
import plotly.express as px
from io import BytesIO
import os

if "password_correct" not in st.session_state or not st.session_state["password_correct"]:
    st.warning("Por favor inicia sesión desde la página principal.")
    st.stop()

role = st.session_state["role"]
if role not in ["Admin", "Ventas", "Cartera", "Logistica"]:
    st.error("No tienes permisos para acceder a Reportes.")
    st.stop()

st.title("📊 Dashboard y Reportes de Ventas")

conn = database.get_connection()

query_ventas = """
    SELECT o.id, o.order_number, o.external_order_id, o.order_date, o.customer_name, o.customer_cedula,
           o.customer_phone, o.customer_city, o.sales_channel, o.status, o.total_amount, o.tracking_number,
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

df_ventas['order_date'] = pd.to_datetime(df_ventas['order_date'])

st.sidebar.header("🔍 Filtros de Reporte")
categorias = ["Todas"] + list(df_ventas['category'].unique())
cat_filtro = st.sidebar.selectbox("Filtrar por Categoría", categorias)

canales = ["Todos"] + list(df_ventas['sales_channel'].unique())
canal_filtro = st.sidebar.selectbox("Filtrar por Canal de Venta", canales)

df_filtrado = df_ventas.copy()
if cat_filtro != "Todas":
    df_filtrado = df_filtrado[df_filtrado['category'] == cat_filtro]
if canal_filtro != "Todos":
    df_filtrado = df_filtrado[df_filtrado['sales_channel'] == canal_filtro]

st.subheader("Resumen General")
col1, col2, col3 = st.columns(3)
total_ingresos = df_filtrado.drop_duplicates(subset=['order_number'])['total_amount'].sum()
total_pedidos = df_filtrado['order_number'].nunique()
unidades_vendidas = df_filtrado['quantity'].sum()

col1.metric("Ingresos Totales", f"${total_ingresos:,.2f}")
col2.metric("Pedidos Totales", total_pedidos)
col3.metric("Unidades Vendidas", unidades_vendidas)

st.divider()

colA, colB = st.columns(2)
with colA:
    st.write("### 📈 Ventas Diarias (Ingresos)")
    ventas_diarias = df_filtrado.drop_duplicates(subset=['order_number']).groupby('order_date')['total_amount'].sum().reset_index()
    if not ventas_diarias.empty:
        fig1 = px.line(ventas_diarias, x='order_date', y='total_amount', markers=True, title="Ingresos por Día")
        st.plotly_chart(fig1, use_container_width=True)

with colB:
    st.write("### 📦 Unidades Vendidas por Producto")
    ventas_prod = df_filtrado.groupby('product_name')['quantity'].sum().reset_index()
    if not ventas_prod.empty:
        fig2 = px.bar(ventas_prod, x='product_name', y='quantity', color='product_name', title="Top Productos")
        st.plotly_chart(fig2, use_container_width=True)

st.write("### 📑 Base de Datos de Ventas Detallada")

output = BytesIO()
with pd.ExcelWriter(output, engine='openpyxl') as writer:
    df_excel = df_filtrado.copy()
    df_excel['order_date'] = df_excel['order_date'].dt.strftime('%Y-%m-%d')
    df_excel.rename(columns={
        'order_number': 'Número Pedido', 'external_order_id': 'ID Externo', 
        'order_date': 'Fecha', 'customer_name': 'Cliente', 'customer_cedula': 'Cédula', 
        'customer_phone': 'Teléfono', 'customer_city': 'Ciudad', 'sales_channel': 'Canal', 
        'status': 'Estado OMS', 'tracking_number': 'Guía Coordinadora', 
        'product_name': 'Producto', 'quantity': 'Cant', 'unit_price': 'Precio Unit.', 
        'total_amount': 'Total Pedido'
    }, inplace=True)
    df_excel.drop(columns=['id'], inplace=True, errors='ignore')
    
    df_excel.to_excel(writer, index=False, sheet_name='Reporte OMS')

excel_data = output.getvalue()

col_btn1, col_btn2 = st.columns(2)

with col_btn1:
    st.download_button(
        label="📥 Exportar Todo a Excel (.xlsx)",
        data=excel_data,
        file_name="reporte_ventas_oms.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary"
    )

# Solo el Administrador puede descargar la base de datos cruda
if role == "Admin":
    with col_btn2:
        db_path = "oms_system.db"
        if os.path.exists(db_path):
            with open(db_path, "rb") as f:
                db_data = f.read()
            st.download_button(
                label="🔒 Descargar Copia de Seguridad Profunda (.db)",
                data=db_data,
                file_name="oms_system_backup.db",
                mime="application/octet-stream",
                help="Guarda este archivo en un USB o Drive. Contiene la estructura y todos los datos del sistema."
            )
        else:
            st.error("No se pudo localizar el archivo de la base de datos.")

st.dataframe(df_filtrado[['order_date', 'order_number', 'product_name', 'category', 'quantity', 'total_amount', 'sales_channel', 'status']], use_container_width=True)
