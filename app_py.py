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
# 2. PROCESAMIENTO INTELIGENTE DE DATOS
# ==========================================
@st.cache_data
def load_and_process_data(sales_file, promo_file):
    
    # Función que detecta si es Excel o CSV
    def leer_archivo(archivo):
        if archivo.name.endswith('.csv'):
            try:
                # Intenta UTF-8 estándar
                return pd.read_csv(archivo, encoding='utf-8')
            except UnicodeDecodeError:
                # Si falla, usa Latin-1 (para Excel en español)
                archivo.seek(0)
                return pd.read_csv(archivo, encoding='latin-1')
        else:
            # Si es .xlsx o .xls
            return pd.read_excel(archivo)

    df_sales = leer_archivo(sales_file)
    df_promo = leer_archivo(promo_file)
    
    # Estandarizar fechas
    df_sales['fecha'] = pd.to_datetime(df_sales['fecha'])
    df_promo['fecha'] = pd.to_datetime(df_promo['fecha'])
    
    # Hacer el cruce
    df = pd.merge(df_sales, df_promo[['fecha', 'sku', 'promo_activa']], on=['fecha', 'sku'], how='left')
    
    # Limpiar columnas
    df['promo_activa'] = df['promo_activa'].fillna(0).astype(int)
    df['unidades_vendidas'] = pd.to_numeric(df['unidades_vendidas'], errors='coerce').fillna(0)
    df['precio'] = pd.to_numeric(df['precio'], errors='coerce').fillna(0)
    df['costo'] = pd.to_numeric(df['costo'], errors='coerce').fillna(0)
    
    # Calcular métricas financieras
    df['ingresos'] = df['unidades_vendidas'] * df['precio']
    df['ganancias'] = df['unidades_vendidas'] * (df['precio'] - df['costo'])
    
    return df

# ==========================================
# 3. BARRA LATERAL: CARGA DE ARCHIVOS
# ==========================================
st.sidebar.header("📁 Carga de Datos")
st.sidebar.markdown("*Ahora soporta CSV y Excel (.xlsx)*")

# Actualizamos los uploaders para que acepten Excel
sales_csv = st.sidebar.file_uploader("1. Histórico de Ventas", type=['csv', 'xlsx', 'xls'], help="Columnas requeridas: fecha, sku, dpto, subdpto, unidades_vendidas, precio, costo")
promo_csv = st.sidebar.file_uploader("2. Base de Promociones", type=['csv', 'xlsx', 'xls'], help="Columnas requeridas: fecha, sku, promo_activa")

if not sales_csv or not promo_csv:
    st.info("👋 Por favor, carga ambos archivos en el menú lateral para comenzar.")
    st.stop()

# Cargar el dataframe maestro
df_trabajo = load_and_process_data(sales_csv, promo_csv)

# ==========================================
# 4. FILTROS INTERACTIVOS
# ==========================================
st.markdown("### 🔍 Filtros de Análisis")
col_f1, col_f2, col_f3 = st.columns(3)

dptos = ['Todos'] + sorted(df_trabajo['dpto'].dropna().unique().tolist())
with col_f1:
    sel_dpto = st.selectbox("Departamento", dptos)

mask_dpto = df_trabajo['dpto'] == sel_dpto if sel_dpto != 'Todos' else df_trabajo['dpto'].notna()
subdptos = ['Todos'] + sorted(df_trabajo[mask_dpto]['subdpto'].dropna().unique().tolist())
with col_f2:
    sel_subdpto = st.selectbox("Subdepartamento", subdptos)

mask_sub = df_trabajo['subdpto'] == sel_subdpto if sel_subdpto != 'Todos' else df_trabajo['subdpto'].notna()
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
            fig_3p.add_trace(go.Scatter(x=etiquetas_x, y=df_promedios['unidades'], mode='lines+markers+text', 
                                        name='Unidades', text=df_promedios['unidades'].round(1), textposition="top center", 
                                        marker=dict(size=14, color='#3b82f6')))
            fig_3p.add_trace(go.Scatter(x=etiquetas_x, y=df_promedios['ingresos'], mode='lines+markers+text', 
                                        name='Ingresos', text=df_promedios['ingresos'].round(1), textposition="bottom center", 
                                        marker=dict(size=14, color='#10b981')))
            fig_3p.add_trace(go.Scatter(x=etiquetas_x, y=df_promedios['ganancias'], mode='lines+markers+text', 
                                        name='Ganancias', text=df_promedios['ganancias'].round(1), textposition="bottom right", 
                                        marker=dict(size=14, color='#8b5cf6')))
            
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
        prompt = f"""
        Actúa como un experto analista de datos de retail. Basado en los siguientes KPIs de un dashboard de promociones: 
        - Ingresos Totales: ${total_ingresos:,.2f}
        - Unidades Vendidas: {total_unidades:,.0f}
        - Porcentaje de días con promoción: {dias_promo_pct:.1f}%
        
        Genera una conclusión en español de máximo 2 párrafos sobre el impacto y rentabilidad aparente de las promociones.
        Da consejos de negocio accionables.
        """
        
        # AQUÍ PON TU API KEY
        api_key = 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
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "qwen/qwen-2.5-72b-instruct",
            "messages": [{"role": "user", "content": prompt}]
        }
        
        try:
            response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
            if response.status_code == 200:
                insight = response.json()['choices'][0]['message']['content']
                st.success(insight)
            else:
                st.error("Error al comunicarse con la API del LLM. Por favor revisa tu API KEY.")
        except Exception as e:
            st.error(f"Error en la red: {e}")
