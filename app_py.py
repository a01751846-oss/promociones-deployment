import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests

# ==========================================
# 1. CONFIGURACIÓN DE LA PÁGINA Y ESTÉTICA
# ==========================================
st.set_page_config(page_title="Promo Impact Analytics", layout="wide", page_icon="📈")

st.markdown("""
<style>
    div[data-testid="metric-container"] {
        background-color: rgba(30, 41, 59, 0.4);
        border: 1px solid rgba(255, 255, 255, 0.1);
        padding: 15px;
        border-radius: 10px;
    }
    .main-header {
        background: linear-gradient(135deg, #3b82f6, #8b5cf6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 700;
        font-size: 3rem;
        text-align: center;
        margin-bottom: 30px;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<h1 class="main-header">Dashboard de Impacto Promocional</h1>', unsafe_allow_html=True)

# ==========================================
# 2. PROCESAMIENTO DE DATOS EN CACHÉ
# ==========================================
def leer_archivo(archivo):
    """Lee archivo CSV o Excel de forma segura y limpia nombres de columnas."""
    nombre = archivo.name.lower()
    if nombre.endswith('.csv'):
        try:
            df = pd.read_csv(archivo, encoding='utf-8')
        except UnicodeDecodeError:
            archivo.seek(0)
            df = pd.read_csv(archivo, encoding='latin-1')
    elif nombre.endswith(('.xlsx', '.xls')):
        df = pd.read_excel(archivo)
    else:
        st.error(f"Formato no soportado: {nombre}")
        st.stop()
        
    # Limpiar columnas: minúsculas y sin espacios a los lados
    df.columns = df.columns.str.lower().str.strip()
    return df

@st.cache_data
def load_and_process_data(sales_file, promo_file):
    # Leer archivos
    df_sales = leer_archivo(sales_file)
    df_promo = leer_archivo(promo_file)
    
    # ----------------------------------------------------
    # MAPEO DE COLUMNAS PARA EL ARCHIVO DE VENTAS
    # ----------------------------------------------------
    columnas_ventas = {
        'tran_date': 'fecha',
        'dept_nm': 'dpto',
        'subdept_nm': 'subdpto',
        'prod_nm': 'sku',
        'qty': 'unidades_vendidas',
        'precio': 'precio'
    }
    
    # Renombrar columnas si existen
     # Renombrar columnas si existen
    df_sales = df_sales.rename(columns=columnas_ventas)
    
    # Forzar que precio sea numérico antes de hacer cálculos
    df_sales['precio'] = pd.to_numeric(df_sales['precio'], errors='coerce').fillna(0)
    
    # Manejar el costo si no está explícito pero tenemos 'diferencia_precio_costo'
    if 'costo' not in df_sales.columns and 'diferencia_precio_costo' in df_sales.columns:
        diferencia = pd.to_numeric(df_sales['diferencia_precio_costo'], errors='coerce').fillna(0)
        df_sales['costo'] = df_sales['precio'] - diferencia
    elif 'costo' not in df_sales.columns and 'cruce_costo' in df_sales.columns:
        df_sales['costo'] = pd.to_numeric(df_sales['cruce_costo'], errors='coerce').fillna(0)
    elif 'costo' not in df_sales.columns:
        df_sales['costo'] = 0  # Fallback si no hay nada

    elif 'costo' not in df_sales.columns and 'cruce_costo' in df_sales.columns:
        df_sales['costo'] = df_sales['cruce_costo']
    elif 'costo' not in df_sales.columns:
        df_sales['costo'] = 0  # Fallback si no hay nada
        
    # Mapeo de archivo de promociones (asumiendo que las columnas podrían ser parecidas)
    # Si la base de promos no trae "fecha" sino "tran_date" o "sku" en vez de "prod_nm"
    columnas_promo = {
        'tran_date': 'fecha',
        'prod_nm': 'sku',
        'promo': 'promo_activa'
    }
    df_promo = df_promo.rename(columns=columnas_promo)

    # Validar que ahora sí existan las obligatorias
    for col in ['fecha', 'sku']:
        if col not in df_sales.columns:
            st.error(f"Error crítico: No se pudo encontrar ni mapear la columna '{col}' en Ventas.")
            st.stop()
        if col not in df_promo.columns:
            st.error(f"Error crítico: No se pudo encontrar ni mapear la columna '{col}' en Promociones.")
            st.stop()
            
    # Estandarizar fechas
    df_sales['fecha'] = pd.to_datetime(df_sales['fecha'], errors='coerce')
    df_promo['fecha'] = pd.to_datetime(df_promo['fecha'], errors='coerce')
    
    # Hacer un left join para cruzar ventas con días de promoción
    # Si en promo no existe 'promo_activa', la creamos
    if 'promo_activa' not in df_promo.columns:
        df_promo['promo_activa'] = 1
        
    df = pd.merge(df_sales, df_promo[['fecha', 'sku', 'promo_activa']].drop_duplicates(), 
                  on=['fecha', 'sku'], how='left')
    
    # Limpiar columnas finales
    df['promo_activa'] = df['promo_activa'].fillna(0).astype(int)
    df['unidades_vendidas'] = pd.to_numeric(df['unidades_vendidas'], errors='coerce').fillna(0)
    df['precio'] = pd.to_numeric(df['precio'], errors='coerce').fillna(0)
    df['costo'] = pd.to_numeric(df['costo'], errors='coerce').fillna(0)
    
    # Usamos net_sale si está disponible, si no lo calculamos
    if 'net_sale' in df.columns:
        df['ingresos'] = pd.to_numeric(df['net_sale'], errors='coerce').fillna(0)
    else:
        df['ingresos'] = df['unidades_vendidas'] * df['precio']
        
    df['ganancias'] = df['ingresos'] - (df['unidades_vendidas'] * df['costo'])
    
    return df

# ==========================================
# 3. BARRA LATERAL: CARGA DE ARCHIVOS
# ==========================================
st.sidebar.header("📁 Carga de Datos")
sales_file = st.sidebar.file_uploader("1. Histórico de Ventas (CSV/Excel)", type=['csv', 'xlsx', 'xls'])
promo_file = st.sidebar.file_uploader("2. Base de Promociones (CSV/Excel)", type=['csv', 'xlsx', 'xls'])

if not sales_file or not promo_file:
    st.info("👋 Por favor, carga ambos archivos en el menú lateral para comenzar.")
    st.stop()

# Cargar el dataframe maestro
df_trabajo = load_and_process_data(sales_file, promo_file)

# ==========================================
# 4. FILTROS INTERACTIVOS
# ==========================================
st.markdown("### 🔍 Filtros de Análisis")
col_f1, col_f2, col_f3 = st.columns(3)

dptos = ['Todos'] + sorted(df_trabajo['dpto'].dropna().unique().tolist()) if 'dpto' in df_trabajo.columns else ['Todos']
with col_f1:
    sel_dpto = st.selectbox("Departamento", dptos)

mask_dpto = (df_trabajo['dpto'] == sel_dpto) if sel_dpto != 'Todos' else pd.Series(True, index=df_trabajo.index)

subdptos = ['Todos'] + sorted(df_trabajo[mask_dpto]['subdpto'].dropna().unique().tolist()) if 'subdpto' in df_trabajo.columns else ['Todos']
with col_f2:
    sel_subdpto = st.selectbox("Subdepartamento", subdptos)

mask_sub = (df_trabajo['subdpto'] == sel_subdpto) if sel_subdpto != 'Todos' else pd.Series(True, index=df_trabajo.index)

skus = ['Todos'] + sorted(df_trabajo[mask_dpto & mask_sub]['sku'].dropna().unique().tolist())
with col_f3:
    sel_sku = st.selectbox("SKU", skus)

df_filtered = df_trabajo[mask_dpto & mask_sub].copy()
if sel_sku != 'Todos':
    df_filtered = df_filtered[df_filtered['sku'] == sel_sku]

# ==========================================
# 5. TARJETAS DE KPIs
# ==========================================
st.markdown("---")
total_ingresos = df_filtered['ingresos'].sum()
total_unidades = df_filtered['unidades_vendidas'].sum()
total_ganancias = df_filtered['ganancias'].sum()
dias_promo_pct = (df_filtered[df_filtered['promo_activa'] == 1].shape[0] / max(df_filtered.shape[0], 1)) * 100

k1, k2, k3, k4 = st.columns(4)
k1.metric("Ingresos Totales", f"${total_ingresos:,.0f}")
k2.metric("Unidades Vendidas", f"{total_unidades:,.0f}")
k3.metric("Ganancias Totales", f"${total_ganancias:,.0f}")
k4.metric("Días con Promoción", f"{dias_promo_pct:.1f}%")

st.markdown("---")

# ==========================================
# 6. GRÁFICOS PRINCIPALES
# ==========================================
col_g1, col_g2 = st.columns([2, 1])

with col_g1:
    st.markdown("### Histórico de Ingresos (Línea de Tiempo)")
    df_time = df_filtered.groupby('fecha').agg(ingresos=('ingresos', 'sum'), promo=('promo_activa', 'max')).reset_index()
    
    fig_time = go.Figure()
    fig_time.add_trace(go.Scatter(x=df_time['fecha'], y=df_time['ingresos'], mode='lines', name='Ingresos', line=dict(color='#3b82f6')))
    
    promo_dates = df_time[df_time['promo'] == 1]['fecha']
    for pd_date in promo_dates:
        fig_time.add_vline(x=pd_date, line_width=1, line_dash="dash", line_color="rgba(139, 92, 246, 0.4)")
        
    fig_time.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', margin=dict(l=0, r=0, t=30, b=0))
    st.plotly_chart(fig_time, use_container_width=True)

with col_g2:
    st.markdown("### Top 10 SKUs (Efecto Promo)")
    df_promo_only = df_filtered[df_filtered['promo_activa'] == 1]
    top_skus = df_promo_only.groupby('sku')['unidades_vendidas'].sum().reset_index().sort_values('unidades_vendidas', ascending=False).head(10)
    top_skus.columns = ['SKU', 'Unidades en Promo']
    st.dataframe(top_skus, hide_index=True, use_container_width=True)

# ==========================================
# 7. GRÁFICO DE 3 FASES (ANTES, DURANTE, DESPUÉS)
# ==========================================
st.markdown("---")
st.markdown("### Efecto de Promoción por Fases (3 Puntos)")

if sel_sku == 'Todos':
    st.warning("⚠️ Selecciona un SKU específico en los filtros superiores para ver el análisis de 3 fases.")
else:
    df_sub = df_filtered.copy()
    fechas_promo = df_sub[df_sub['promo_activa'] == 1]['fecha'].unique()
    
    if len(fechas_promo) > 0:
        fecha_primera = fechas_promo.min()
        fecha_ultima = fechas_promo.max()
        
        def clasificar_dia_sku(fecha):
            if pd.isna(fecha_primera): return 'Sin Promociones'
            if fecha in fechas_promo: return '2. Durante'
            elif fecha < fecha_primera: return '1. Antes'
            elif fecha > fecha_ultima: return '3. Después'
            else: return 'Ignorar'
            
        df_sub['Periodo'] = df_sub['fecha'].apply(clasificar_dia_sku)
        df_periodos = df_sub[df_sub['Periodo'] != 'Ignorar']
        
        df_promedios = df_periodos.groupby('Periodo').agg(
            unidades=('unidades_vendidas', 'mean'),
            ingresos=('ingresos', 'mean'),
            ganancias=('ganancias', 'mean')
        ).reset_index().sort_values('Periodo')
        
        if not df_promedios.empty:
            etiquetas_x = [p.split('. ')[1] if '. ' in p else p for p in df_promedios['Periodo']]
            
            fig_3p = go.Figure()
            fig_3p.add_trace(go.Scatter(x=etiquetas_x, y=df_promedios['unidades'], mode='lines+markers+text', name='Unidades', text=df_promedios['unidades'].round(1), textposition="top center", marker=dict(size=14, color='#3b82f6')))
            fig_3p.add_trace(go.Scatter(x=etiquetas_x, y=df_promedios['ingresos'], mode='lines+markers+text', name='Ingresos', text=df_promedios['ingresos'].round(1), textposition="bottom center", marker=dict(size=14, color='#10b981')))
            fig_3p.add_trace(go.Scatter(x=etiquetas_x, y=df_promedios['ganancias'], mode='lines+markers+text', name='Ganancias', text=df_promedios['ganancias'].round(1), textposition="bottom right", marker=dict(size=14, color='#8b5cf6')))
            
            fig_3p.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_3p, use_container_width=True)
        else:
            st.info("No hay suficientes datos temporales para calcular el antes y el después de este SKU.")
    else:
        st.info(f"El SKU {sel_sku} no tiene periodos de promoción registrados.")

# ==========================================
# 8. INTEGRACIÓN DE INTELIGENCIA ARTIFICIAL (QWEN)
# ==========================================
st.markdown("---")
st.markdown("### ✨ Insights Asistidos por IA (Qwen)")

if st.button("Generar Conclusiones de Negocio"):
    with st.spinner("Analizando datos..."):
        prompt = f"Actúa como un experto analista de retail. Basado en estos KPIs: Ingresos ${total_ingresos:,.2f}, Unidades {total_unidades:,.0f}, Promociones {dias_promo_pct:.1f}%. Da conclusiones cortas y consejos."
        
        api_key = "TU_API_KEY_AQUI" 
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {"model": "qwen/qwen-2.5-72b-instruct", "messages": [{"role": "user", "content": prompt}]}
        
        try:
            response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
            if response.status_code == 200:
                st.success(response.json()['choices'][0]['message']['content'])
            else:
                st.error("Error con la API.")
        except Exception as e:
            st.error(f"Error de red: {e}")
