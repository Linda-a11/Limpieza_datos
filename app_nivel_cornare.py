"""
App de Streamlit — Nivel de ríos/quebradas (CORNARE / MARCO)
Módulo de Gestión del Riesgo: Alertador Temprano de Crecidas Rápidas
"""

import requests
import pandas as pd
import numpy as np
import streamlit as st
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ------------------------------------------------------------------
# Coordenadas por defecto (Institución Universitaria Pascual Bravo)
# ------------------------------------------------------------------
LAT_DEFECTO = 6.059
LON_DEFECTO = -75.0066

API_BASE_URL = "https://marco.cornare.gov.co/api/v1/estaciones"

LLAVE_FECHA = "level_date"
LLAVE_VALOR = "level"
CANDIDATOS_LAT = ["lat", "latitude", "latitud"]
CANDIDATOS_LON = ["lng", "lon", "longitude", "longitud"]

st.set_page_config(page_title="Alerta de Crecidas — CORNARE", page_icon="🌊", layout="wide")


# ------------------------------------------------------------------
# Funciones de consulta y procesamiento
# ------------------------------------------------------------------
def obtener_serie_nivel(codigo_estacion, desde, hasta, calidad=1, timeout=30):
    url = f"{API_BASE_URL}/{codigo_estacion}/nivel"
    params = {"desde": desde, "hasta": hasta, "calidad": calidad}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
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
# Sidebar — Parámetros de consulta y Umbrales Ambientales
# ------------------------------------------------------------------
st.sidebar.header("📋 Parámetros de Consulta")
nombre_estudiante = st.sidebar.text_input("Nombre del estudiante", "Tu Nombre Aquí")
codigo_estacion = st.sidebar.text_input("Código de estación", "42")
fecha_desde = st.sidebar.date_input("Desde", pd.to_datetime("2026-08-23")).strftime("%Y-%m-%d")
fecha_hasta = st.sidebar.date_input("Hasta", pd.to_datetime("2026-08-30")).strftime("%Y-%m-%d")
calidad = st.sidebar.selectbox("Calidad", [1, 0], index=0, help="1 = solo datos validados")

st.sidebar.markdown("---")
st.sidebar.header("🚨 Umbrales de Riesgo (Metros)")
st.sidebar.caption("Configura las cotas críticas según la sección hidrológica de la estación.")
u_amarillo = st.sidebar.number_input("Cota Amarilla (Vigilancia)", value=1.20, step=0.10)
u_naranja = st.sidebar.number_input("Cota Naranja (Aviso de Banca)", value=1.80, step=0.10)
u_rojo = st.sidebar.number_input("Cota Roja (Desbordamiento)", value=2.50, step=0.10)

consultar = st.sidebar.button("🔍 Consultar y Analizar Riesgo", type="primary")

# ------------------------------------------------------------------
# Encabezado Principal
# ------------------------------------------------------------------
st.title("🌊 Sistema Alertador de Riesgo por Crecidas Rápidas- Estacion San Luis (#21)")
st.caption(f"Proyecto de Ingeniería Ambiental · Estudiante: **{nombre_estudiante}** · Estación: **{codigo_estacion}**")

# ------------------------------------------------------------------
# Consulta y Procesamiento
# ------------------------------------------------------------------
if consultar:
    with st.spinner("Consultando la API de CORNARE y procesando riesgo..."):
        datos_crudos, error = obtener_serie_nivel(codigo_estacion, fecha_desde, fecha_hasta, calidad)

    if error:
        st.error(f"❌ {error}")
    else:
        registros = obtener_todas_las_paginas(datos_crudos)

        if not registros:
            st.warning("No hay registros para esta estación y rango de fechas. Prueba otro código u otro rango.")
        else:
            df = pd.DataFrame(registros)
            df = df.rename(columns={LLAVE_FECHA: "fecha", LLAVE_VALOR: "nivel"})
            df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
            df["nivel"] = pd.to_numeric(df["nivel"], errors="coerce")
            df = df.dropna(subset=["fecha", "nivel"]).sort_values("fecha").reset_index(drop=True)

            lat, lon, coords_reales = detectar_coordenadas(datos_crudos)
            indice_calidad, huecos, n_outliers = calcular_indice_calidad(df)

            # --- Variables Hidrológicas para Gestión del Riesgo ---
            nivel_actual = df["nivel"].iloc[-1]
            nivel_max = df["nivel"].max()
            fecha_max = df.loc[df["nivel"].idxmax(), "fecha"]

            # ------------------------------------------------------
            # MÓDULO NOVEDOSO: Semáforo de Riesgo Operativo
            # ------------------------------------------------------
            st.markdown("### 🚦 Estado de Alerta Hidrológica Actual")
            
            if nivel_actual >= u_rojo:
                st.error(
                    f"### 🔴 ALERTA ROJA — DESBORDAMIENTO INMINENTE O EN CURSO\n"
                    f"**Nivel actual:** `{nivel_actual:.2f} m` (Superó la cota crítica de {u_rojo:.2f} m).\n\n"
                    f"**Acción Ambiental/Gestión del Riesgo:** Activar protocolos de evacuación en zonas de alta vulnerabilidad. Notificar al Consejo Municipal para la Gestión del Riesgo de Desastres (CMGRD)."
                )
            elif nivel_actual >= u_naranja:
                st.warning(
                    f"### 🟠 ALERTA NARANJA — CRECIDA SIGNIFICATIVA\n"
                    f"**Nivel actual:** `{nivel_actual:.2f} m` (Superó la cota de prevención de {u_naranja:.2f} m).\n\n"
                    f"**Acción Ambiental/Gestión del Riesgo:** Alerta preventiva para comunidades ribereñas. Monitoreo constante del tiempo de concentración de la cuenca."
                )
            elif nivel_actual >= u_amarillo:
                st.info(
                    f"### 🟡 ALERTA AMARILLA — INCREMENTO DE NIVEL\n"
                    f"**Nivel actual:** `{nivel_actual:.2f} m` (Superó el umbral de vigilancia de {u_amarillo:.2f} m).\n\n"
                    f"**Acción Ambiental/Gestión del Riesgo:** Vigilancia continua del comportamiento pluviométrico en la cuenca alta."
                )
            else:
                st.success(
                    f"### 🟢 ESTADO NORMAL — CAUCE ORDINARIO\n"
                    f"**Nivel actual:** `{nivel_actual:.2f} m` (Por debajo de las cotas de advertencia).\n\n"
                    f"**Acción Ambiental/Gestión del Riesgo:** Condiciones hidrológicas estables."
                )

            st.markdown("---")

            # --- Métricas Principales ---
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Nivel Último Reporte", f"{nivel_actual:.2f} m")
            col2.metric("Nivel Máximo (Pico)", f"{nivel_max:.2f} m")
            col3.metric("Promedio de la Serie", f"{df['nivel'].mean():.2f} m")
            col4.metric("Índice Calidad Datos", f"{indice_calidad} / 100")

            # --- Gráfico con Líneas de Umbral de Riesgo ---
            st.subheader("📈 Hidrograma de Nivel con Cotas de Seguridad")
            
            # Crear dataframe para visualización comparativa con los umbrales
            df_grafico = df.set_index("fecha")[["nivel"]].copy()
            df_grafico["Umbral Amarillo"] = u_amarillo
            df_grafico["Umbral Naranja"] = u_naranja
            df_grafico["Umbral Rojo"] = u_rojo
            
            st.line_chart(df_grafico, color=["#1f77b4", "#f1c40f", "#e67e22", "#e74c3c"])

            # --- Ubicación de la Estación ---
            st.subheader("📍 Ubicación de la Estación de Monitoreo")
            if not coords_reales:
                st.caption("La API no trajo coordenadas reales. Mostrando punto de referencia predeterminado.")
            st.map(pd.DataFrame({"lat": [lat], "lon": [lon]}), zoom=10)

            # --- Detalles Técnicos y Descarga ---
            with st.expander("🔬 Evaluación de Calidad de Datos Hidrológicos"):
                st.write(f"- **Pico máximo registrado:** {nivel_max:.2f} m el `{fecha_max}`")
                st.write(f"- **Huecos de reporte detectados:** {huecos}")
                st.write(f"- **Anomalías/Outliers (IQR):** {n_outliers} lecturas de {len(df)}")

            with st.expander("📄 Ver Datos Crudos"):
                st.dataframe(df, use_container_width=True)

            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇️ Descargar Serie Histórica (CSV)",
                csv,
                file_name=f"alerta_crecidas_estacion_{codigo_estacion}.csv",
                mime="text/csv"
            )
else:
    st.info("Ajusta los parámetros y umbrales de riesgo en el menú izquierdo y presiona **Consultar y Analizar Riesgo**.")
