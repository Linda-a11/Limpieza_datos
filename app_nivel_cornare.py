import requests
import pandas as pd
import numpy as np
import streamlit as st
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

LAT_DEFECTO = 6.059
LON_DEFECTO = -75.0066
API_BASE_URL = "https://marco.cornare.gov.co/api/v1/estaciones"

LLAVE_FECHA = "level_date"
LLAVE_VALOR = "level"
CANDIDATOS_LAT = ["lat", "latitude", "latitud"]
CANDIDATOS_LON = ["lng", "lon", "longitude", "longitud"]

st.set_page_config(page_title="Alerta de Crecidas — CORNARE", page_icon="🌊", layout="wide")

# ------------------------------------------------------------------
# Funciones de backend
# ------------------------------------------------------------------
def obtener_serie_nivel(codigo_estacion, desde, hasta, calidad=1, timeout=30):
    url = f"{API_BASE_URL}/{codigo_estacion}/nivel"
    params = {"desde": desde, "hasta": hasta, "calidad": calidad}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
    }
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=timeout, verify=False)
        if resp.status_code == 200:
            return resp.json(), None
        return None, f"HTTP {resp.status_code}"
    except requests.exceptions.RequestException as e:
        return None, f"Error de red: {e}"

def obtener_todas_las_paginas(datos_json, timeout=30):
    registros = list(datos_json.get("values", []))
    siguiente_url = datos_json.get("next")
    while siguiente_url:
        try:
            resp = requests.get(siguiente_url, timeout=timeout, verify=False)
        except requests.exceptions.RequestException:
            break
        if resp.status_code != 200:
            break
        pagina = resp.json()
        registros.extend(pagina.get("values", []))
        siguiente_url = pagina.get("next")
    return registros

def detectar_coordenadas(datos_json):
    if not isinstance(datos_json, dict):
        return LAT_DEFECTO, LON_DEFECTO, False
    lat = next((datos_json[k] for k in CANDIDATOS_LAT if k in datos_json), None)
    lon = next((datos_json[k] for k in CANDIDATOS_LON if k in datos_json), None)
    if lat is not None and lon is not None:
        try:
            return float(lat), float(lon), True
        except (TypeError, ValueError):
            pass
    return LAT_DEFECTO, LON_DEFECTO, False

def calcular_indice_calidad(df):
    if df.empty or len(df) < 2:
        return 0.0, 0, 0
    df_idx = df.set_index("fecha")
    frecuencia_tipica = df["fecha"].diff().dropna().mode()
    if len(frecuencia_tipica) == 0:
        return 0.0, 0, 0
    frecuencia_tipica = frecuencia_tipica[0]

    rango_completo = pd.date_range(start=df_idx.index.min(), end=df_idx.index.max(), freq=frecuencia_tipica)
    esperados = len(rango_completo)
    huecos = esperados - len(df_idx)
    completitud = max(0.0, 1 - (huecos / esperados)) if esperados > 0 else 0.0

    Q1, Q3 = df["nivel"].quantile(0.25), df["nivel"].quantile(0.75)
    IQR = Q3 - Q1
    lim_inf, lim_sup = Q1 - 1.5 * IQR, Q3 + 1.5 * IQR
    es_outlier = (df["nivel"] < lim_inf) | (df["nivel"] > lim_sup) | (df["nivel"] < 0)
    proporcion_outliers = es_outlier.mean()

    indice = (completitud * 0.7 + (1 - proporcion_outliers) * 0.3) * 100
    return round(indice, 1), int(huecos), int(es_outlier.sum())

# ------------------------------------------------------------------
# Sidebar Rediseñado
# ------------------------------------------------------------------
st.sidebar.title("🛠️ Panel de Control")

with st.sidebar.expander("👤 Datos de Consulta", expanded=True):
    nombre_estudiante = st.text_input("Consultante", "Linda Maria Perez Regino")
    codigo_estacion = st.text_input("Código Estación", "21")
    fecha_desde = st.date_input("Fecha Inicial", pd.to_datetime("2026-08-23")).strftime("%Y-%m-%d")
    fecha_hasta = st.date_input("Fecha Final", pd.to_datetime("2026-09-07")).strftime("%Y-%m-%d")
    calidad = st.selectbox("Calidad de Datos", [1, 0], index=0, help="1 = Datos validados")

with st.sidebar.expander("🚨 Cotas de Riesgo Configurada", expanded=True):
    u_amarillo = st.number_input("Cota Amarilla (m)", value=1.20, step=0.10)
    u_naranja = st.number_input("Cota Naranja (m)", value=1.80, step=0.10)
    u_rojo = st.number_input("Cota Roja (m)", value=2.50, step=0.10)

consultar = st.sidebar.button("🔍 Consultar y Analizar Riesgo", type="primary", use_container_width=True)

# ------------------------------------------------------------------
# Interfaz Principal
# ------------------------------------------------------------------
st.title("🌱🌊 EcoCaudal San Luis — Sistema de Alerta Temprana")
st.caption(f"Gestión del Riesgo Hidrológico · Consultante: **{nombre_estudiante}**")

# Bloque Informativo de Contexto Directo para la Comunidad
st.info(
    f"📍 **Estación Seleccionada:** Código `{codigo_estacion}` | "
    f"📅 **Rango:** `{fecha_desde}` a `{fecha_hasta}`\n\n"
    f"🚨 **Umbrales Activos:** 🟡 Amarilla: `{u_amarillo:.2f} m` | 🟠 Naranja: `{u_naranja:.2f} m` | 🔴 Roja: `{u_rojo:.2f} m`"
)

if consultar:
    with st.status("Conectando con la red CORNARE...", expanded=True) as status:
        st.write("Obteniendo registros hidrológicos...")
        datos_crudos, error = obtener_serie_nivel(codigo_estacion, fecha_desde, fecha_hasta, calidad)
        
        if not error:
            st.write("Procesando histórico de niveles...")
            registros = obtener_todas_las_paginas(datos_crudos)
            status.update(label="Consulta completada con éxito", state="complete", expanded=False)

    if error:
        st.error(f"❌ {error}")
    elif not registros:
        st.warning("No se encontraron datos para la estación y rango seleccionados.")
    else:
        df = pd.DataFrame(registros)
        df = df.rename(columns={LLAVE_FECHA: "fecha", LLAVE_VALOR: "nivel"})
        df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
        df["nivel"] = pd.to_numeric(df["nivel"], errors="coerce")
        df = df.dropna(subset=["fecha", "nivel"]).sort_values("fecha").reset_index(drop=True)

        lat, lon, coords_reales = detectar_coordenadas(datos_crudos)
        indice_calidad, huecos, n_outliers = calcular_indice_calidad(df)

        nivel_actual = df["nivel"].iloc[-1]
        nivel_max = df["nivel"].max()
        fecha_max = df.loc[df["nivel"].idxmax(), "fecha"]

        # Semáforo de Riesgo
        st.markdown("### 🚦 Estado de Alerta Operativa")
        if nivel_actual >= u_rojo:
            st.error(f"🔴 **ALERTA ROJA — DESBORDAMIENTO INMINENTE** (`{nivel_actual:.2f} m` >= `{u_rojo:.2f} m`) - Evacuar zonas vulnerables.")
        elif nivel_actual >= u_naranja:
            st.warning(f"🟠 **ALERTA NARANJA — CRECIDA SIGNIFICATIVA** (`{nivel_actual:.2f} m` >= `{u_naranja:.2f} m`) - Preparar planes de contingencia.")
        elif nivel_actual >= u_amarillo:
            st.info(f"🟡 **ALERTA AMARILLA — INCREMENTO DE NIVEL** (`{nivel_actual:.2f} m` >= `{u_amarillo:.2f} m`) - Monitoreo constante.")
        else:
            st.success(f"🟢 **ESTADO NORMAL** (`{nivel_actual:.2f} m`) - Nivel dentro del cauce ordinario.")

        # Métricas
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Último Nivel", f"{nivel_actual:.2f} m")
        c2.metric("Nivel Pico", f"{nivel_max:.2f} m")
        c3.metric("Promedio Serie", f"{df['nivel'].mean():.2f} m")
        c4.metric("Calidad Datos", f"{indice_calidad}%")

        # Visualización Hidrológica
        st.subheader("📈 Hidrograma con Umbrales Configurados")
        df_grafico = df.set_index("fecha")[["nivel"]].copy()
        df_grafico["Umbral Amarillo"] = u_amarillo
        df_grafico["Umbral Naranja"] = u_naranja
        df_grafico["Umbral Rojo"] = u_rojo
        st.line_chart(df_grafico, color=["#1f77b4", "#f1c40f", "#e67e22", "#e74c3c"])

        # Mapa y Descargas
        st.subheader("📍 Coordenadas de Monitoreo")
        st.map(pd.DataFrame({"lat": [lat], "lon": [lon]}), zoom=10)

        with st.expander("📄 Exportar y Ver Registros Crudos"):
            st.dataframe(df, use_container_width=True)
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button("⬇️ Descargar Serie (CSV)", csv, f"estacion_{codigo_estacion}.csv", "text/csv")
else:
    st.info("👈 Presiona **Consultar y Analizar Riesgo** en la barra lateral para obtener los datos más recientes.")
