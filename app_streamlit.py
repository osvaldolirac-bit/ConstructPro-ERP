import streamlit as st
import pandas as pd

# Configuración de la interfaz
st.set_page_config(page_title="ConstructPro ERP - Laboratorio", layout="wide", page_icon="🏗️")

st.title("🏗️ ConstructPro ERP - Panel de Control Prototipo")
st.write("Simulación interactiva mientras el servidor principal de producción es desbloqueado.")

# Menú lateral
modulo = st.sidebar.selectbox(
    "Módulos del ERP",
    ["📊 Dashboard Ejecutivo", "📝 Cotizaciones y APU", "💰 Estados de Pago"]
)

# 1. DASHBOARD
if modulo == "📊 Dashboard Ejecutivo":
    st.header("📊 Resumen General de Obras")
    col1, col2 = st.columns(2)
    col1.metric("Flujo de Caja Real", "$45.200.000 CLP")
    col2.metric("Obras Activas", "Río Maipo")
    
    # Gráfico simple
    df = pd.DataFrame({"Estado": ["Aprobados", "Pendientes"], "Cantidad": [8, 3]})
    st.bar_chart(data=df, x="Estado", y="Cantidad")

# 2. COTIZACIONES
elif modulo == "📝 Cotizaciones y APU":
    st.header("📝 Análisis de Precios Unitarios (APU)")
    st.subheader("Cálculo estimado por m²")
    
    sacos = st.number_input("Precio saco Cemento ($)", value=4500)
    horas = st.number_input("Costo Hora Maestro ($)", value=5000)
    
    total = (sacos * 0.5) + (horas * 2)
    st.success(f"Costo estimado por m²: ${total:,.0f} CLP")

# 3. COBRANZA
elif modulo == "💰 Estados de Pago":
    st.header("💰 Registro y Control de Retenciones")
    datos = pd.DataFrame({
        'Obra': ['Condominio Río Maipo', 'Bodega Central'],
        'Facturado': [15000000, 8000000],
        'Retención Anticipo (10%)': [1500000, 800000]
    })
    st.dataframe(datos, use_container_width=True)
