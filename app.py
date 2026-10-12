
import streamlit as st
import gspread
import pandas as pd
import re
import html

from google.oauth2.service_account import Credentials


# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================

st.set_page_config(
    page_title="MONITOR DE KILOMETRAJE",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="collapsed"
)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# Archivo KM_DISTRIBUCION
NOMBRE_ARCHIVO_DISTRIBUCION = "KM_DISTRIBUCION"
NOMBRE_HOJA_DISTRIBUCION = "Distribucion"

# Archivo KM_PERDIDAS
NOMBRE_HOJA_PERDIDAS = "ControlPerdidas"


# ============================================================
# CONEXIÓN GOOGLE SHEETS
# ============================================================

@st.cache_resource
def conectar_google():
    credenciales = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=SCOPES
    )

    return gspread.authorize(credenciales)


def obtener_hoja_distribucion():
    cliente = conectar_google()

    archivo = cliente.open_by_key(
        st.secrets["SPREADSHEET_ID_DISTRIBUCION"]
    )

    return archivo.worksheet(
        NOMBRE_HOJA_DISTRIBUCION
    )


def obtener_hoja_perdidas():
    cliente = conectar_google()

    archivo = cliente.open_by_key(
        st.secrets["SPREADSHEET_ID_PERDIDAS"]
    )

    # Buscar la hoja ignorando espacios,
    # guiones, guiones bajos y mayúsculas.
    def normalizar_nombre(nombre):
        return re.sub(
            r"[^a-z0-9]",
            "",
            nombre.strip().lower()
        )

    nombre_buscado = normalizar_nombre(
        NOMBRE_HOJA_PERDIDAS
    )

    for hoja in archivo.worksheets():
        if normalizar_nombre(hoja.title) == nombre_buscado:
            return hoja

    nombres_disponibles = [
        hoja.title for hoja in archivo.worksheets()
    ]

    raise ValueError(
        f"No se encontró la hoja '{NOMBRE_HOJA_PERDIDAS}'. "
        f"Hojas disponibles: {nombres_disponibles}"
    )


# ============================================================
# ENCABEZADOS DE LAS DOS BASES DE DATOS
# ============================================================

COLUMNAS_DISTRIBUCION = [
    "Fecha",
    "Placa",
    "Hora Inicio",
    "Km Inicial",
    "Hora Fin",
    "Km Final",
    "Tot Recorrido",
    "Nom Personal",
    "Celular",
    "Cuadrilla",
    "Item",
    "Unidad Negocio",
    "Servicio Electrico",
    "Nº OM | Cod. Recibo",
    "Descripcion Actividad",
    "CECO",
    "Foto KM Inicial",
    "Foto KM Final",
    "Ubicacion Inicial",
    "Ubicacion Final",
    "Observacion"
]

# Se conserva el orden de columnas de la primera aplicación.
COLUMNAS_PERDIDAS = [
    "Fecha",
    "Placa",
    "Km Inicial",
    "Km Final",
    "Tot Recorrido",
    "Nom Personal",
    "Celular",
    "Cuadrilla",
    "Item",
    "Unidad Negocio",
    "Servicio Electrico",
    "CECO",
    "Foto KM Inicial",
    "Foto KM Final",
    "Ubicacion Inicial",
    "Ubicacion Final",
    "Observacion"
]


# ============================================================
# CARGAR DATOS
# ============================================================

def cargar_datos(hoja, columnas):
    cantidad_columnas = len(columnas)

    # Leer los valores directamente de Google Sheets.
    valores = hoja.get(
        f"A:{chr(64 + cantidad_columnas)}",
        value_render_option="FORMATTED_VALUE"
    )

    if not valores or len(valores) <= 1:
        return pd.DataFrame(columns=columnas)

    filas = []

    for fila in valores[1:]:
        fila = list(fila)

        if len(fila) < cantidad_columnas:
            fila += [""] * (
                cantidad_columnas - len(fila)
            )

        filas.append(fila[:cantidad_columnas])

    df = pd.DataFrame(
        filas,
        columns=columnas
    )

    # Eliminar filas completamente vacías.
    df = df[
        df.astype(str).apply(
            lambda fila: fila.str.strip().ne("").any(),
            axis=1
        )
    ].copy()

    return df


# ============================================================
# NORMALIZAR Y PREPARAR DATOS
# ============================================================

def normalizar_texto(valor):
    if pd.isna(valor):
        return ""

    return str(valor).strip()


def preparar_datos(df):
    df = df.copy()

    if df.empty:
        df["Estado"] = pd.Series(dtype=str)
        return df

    for columna in df.columns:
        df[columna] = df[columna].apply(
            normalizar_texto
        )

    df["Estado"] = df["Km Final"].apply(
        lambda valor:
        "🟢 COMPLETADO"
        if valor != ""
        else "🟠 PENDIENTE KM FINAL"
    )

    return df


# ============================================================
# EXTRAER URL DE FOTOS Y UBICACIONES
# ============================================================

def extraer_url(valor):
    valor = normalizar_texto(valor)

    if not valor:
        return ""

    # Fórmulas HYPERLINK devueltas como texto.
    if "HYPERLINK" in valor.upper():
        encontrado = re.search(
            r'"(https?://[^"]+)"',
            valor,
            flags=re.IGNORECASE
        )

        if encontrado:
            return encontrado.group(1)

    # URL directa.
    if valor.startswith(("http://", "https://")):
        return valor

    return ""


def convertir_enlace_foto(valor):
    url = extraer_url(valor)

    if not url:
        return "—"

    url_segura = html.escape(url, quote=True)

    return (
        f'<a href="{url_segura}" '
        f'target="_blank" rel="noopener noreferrer">'
        '📷 Ver foto</a>'
    )


def convertir_enlace_ubicacion(valor):
    url = extraer_url(valor)

    if not url:
        valor = normalizar_texto(valor)

        return html.escape(valor) if valor else "—"

    url_segura = html.escape(url, quote=True)

    return (
        f'<a href="{url_segura}" '
        f'target="_blank" rel="noopener noreferrer">'
        '📍 Ver ubicación</a>'
    )


# ============================================================
# FILTRAR DATOS
# ============================================================

def aplicar_filtros(df):
    st.markdown("### 🔎 FILTROS")

    col1, col2, col3, col4 = st.columns(4)

    fechas = sorted(
        [
            x for x in df["Fecha"].unique().tolist()
            if str(x).strip()
        ],
        reverse=True
    )

    placas = sorted(
        [
            x for x in df["Placa"].unique().tolist()
            if str(x).strip()
        ]
    )

    personales = sorted(
        [
            x for x in df["Nom Personal"].unique().tolist()
            if str(x).strip()
        ]
    )

    with col1:
        fecha_filtro = st.selectbox(
            "📅 Fecha",
            ["TODAS"] + fechas,
            key="filtro_fecha"
        )

    with col2:
        placa_filtro = st.selectbox(
            "🚗 Placa",
            ["TODAS"] + placas,
            key="filtro_placa"
        )

    with col3:
        personal_filtro = st.selectbox(
            "👷 Personal",
            ["TODOS"] + personales,
            key="filtro_personal"
        )

    with col4:
        estado_filtro = st.selectbox(
            "📌 Estado",
            [
                "TODOS",
                "🟠 PENDIENTE KM FINAL",
                "🟢 COMPLETADO"
            ],
            key="filtro_estado"
        )

    col5, col6, col7, col8 = st.columns(4)

    unidades = sorted(
        [
            x for x in df["Unidad Negocio"].unique().tolist()
            if str(x).strip()
        ]
    )

    servicios = sorted(
        [
            x for x in df["Servicio Electrico"].unique().tolist()
            if str(x).strip()
        ]
    )

    items = sorted(
        [
            x for x in df["Item"].unique().tolist()
            if str(x).strip()
        ]
    )

    cecos = sorted(
        [
            x for x in df["CECO"].unique().tolist()
            if str(x).strip()
        ]
    )

    with col5:
        unidad_filtro = st.selectbox(
            "🏢 Unidad de Negocio",
            ["TODAS"] + unidades,
            key="filtro_unidad"
        )

    with col6:
        servicio_filtro = st.selectbox(
            "⚡ Servicio Eléctrico",
            ["TODOS"] + servicios,
            key="filtro_servicio"
        )

    with col7:
        item_filtro = st.selectbox(
            "📋 Ítem",
            ["TODOS"] + items,
            key="filtro_item"
        )

    with col8:
        ceco_filtro = st.selectbox(
            "🏷️ CECO",
            ["TODOS"] + cecos,
            key="filtro_ceco"
        )

    df_filtrado = df.copy()

    filtros = [
        ("Fecha", fecha_filtro, "TODAS"),
        ("Placa", placa_filtro, "TODAS"),
        ("Nom Personal", personal_filtro, "TODOS"),
        ("Estado", estado_filtro, "TODOS"),
        ("Unidad Negocio", unidad_filtro, "TODAS"),
        ("Servicio Electrico", servicio_filtro, "TODOS"),
        ("Item", item_filtro, "TODOS"),
        ("CECO", ceco_filtro, "TODOS")
    ]

    for columna, valor, valor_todos in filtros:
        if valor != valor_todos:
            df_filtrado = df_filtrado[
                df_filtrado[columna] == valor
            ]

    return df_filtrado


# ============================================================
# MOSTRAR RESUMEN
# ============================================================

def mostrar_resumen(df):
    total_registros = len(df)

    total_vehiculos = (
        df["Placa"].replace("", pd.NA).dropna().nunique()
    )

    total_personal = (
        df["Nom Personal"].replace("", pd.NA).dropna().nunique()
    )

    total_pendientes = int(
        (df["Km Final"] == "").sum()
    )

    total_completados = int(
        (df["Km Final"] != "").sum()
    )

    st.markdown("### 📊 RESUMEN")

    k1, k2, k3, k4, k5 = st.columns(5)

    k1.metric("📋 Registros", total_registros)
    k2.metric("🚗 Vehículos", total_vehiculos)
    k3.metric("👷 Personal", total_personal)
    k4.metric("🟠 Pendientes", total_pendientes)
    k5.metric("🟢 Completados", total_completados)


# ============================================================
# MOSTRAR TABLA
# ============================================================

def mostrar_tabla(df, columnas_mostrar):
    st.markdown("### 📋 REGISTROS")

    if df.empty:
        st.warning(
            "No existen registros con los filtros seleccionados."
        )
        return

    df_mostrar = df.copy()

    df_mostrar["📷 KM Inicial"] = (
        df_mostrar["Foto KM Inicial"]
        .apply(convertir_enlace_foto)
    )

    df_mostrar["📷 KM Final"] = (
        df_mostrar["Foto KM Final"]
        .apply(convertir_enlace_foto)
    )

    df_mostrar["📍 Ubicación Inicial"] = (
        df_mostrar["Ubicacion Inicial"]
        .apply(convertir_enlace_ubicacion)
    )

    df_mostrar["📍 Ubicación Final"] = (
        df_mostrar["Ubicacion Final"]
        .apply(convertir_enlace_ubicacion)
    )

    tabla = df_mostrar[columnas_mostrar].copy()

    # Escapar los datos de texto antes de insertar los enlaces.
    columnas_enlaces = [
        "📷 KM Inicial",
        "📷 KM Final",
        "📍 Ubicación Inicial",
        "📍 Ubicación Final"
    ]

    for columna in tabla.columns:
        if columna not in columnas_enlaces:
            tabla[columna] = tabla[columna].apply(
                lambda x: html.escape(str(x))
                if pd.notna(x) else ""
            )

    html_tabla = tabla.to_html(
        index=False,
        escape=False,
        border=0
    )

    st.markdown(
        """
        <style>
        .contenedor-tabla-supervisor {
            width: 100%;
            overflow-x: auto;
            margin-top: 10px;
        }

        .contenedor-tabla-supervisor table {
            width: 100%;
            min-width: 1500px;
            border-collapse: collapse;
            font-size: 13px;
        }

        .contenedor-tabla-supervisor th {
            background-color: #1f2937 !important;
            color: #ffffff !important;
            padding: 8px;
            border: 1px solid #4b5563;
            text-align: center;
            white-space: nowrap;
            font-weight: 700;
        }

        .contenedor-tabla-supervisor td {
            padding: 8px;
            border: 1px solid #4b5563;
            white-space: nowrap;
        }

        .contenedor-tabla-supervisor a {
            color: #2563eb;
            text-decoration: none;
            font-weight: bold;
        }

        @media (prefers-color-scheme: dark) {
            .contenedor-tabla-supervisor td {
                color: #f3f4f6;
                background-color: #1f2937;
                border-color: #4b5563;
            }

            .contenedor-tabla-supervisor a {
                color: #60a5fa;
            }
        }

        @media (prefers-color-scheme: light) {
            .contenedor-tabla-supervisor td {
                color: #111827;
                background-color: #ffffff;
            }
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    st.markdown(
        f"""
        <div class="contenedor-tabla-supervisor">
            {html_tabla}
        </div>
        """,
        unsafe_allow_html=True
    )


# ============================================================
# ENCABEZADO PRINCIPAL
# ============================================================

st.markdown(
    """
    <h1 style="text-align:center; margin-bottom:0;">
        🚗 MONITOR GENERAL DE KILOMETRAJE
    </h1>
    <p style="
        text-align:center;
        color:#777;
        font-size:15px;
        margin-top:4px;
    ">
        Supervisión de KM_DISTRIBUCION y KM_PERDIDAS
    </p>
    """,
    unsafe_allow_html=True
)

st.markdown("---")


# ============================================================
# SELECTOR DE MÓDULO
# ============================================================

modulo = st.radio(
    "📂 SELECCIONAR MÓDULO",
    [
        "🛻 KM_DISTRIBUCIÓN",
        "🚗 KM_PÉRDIDAS"
    ],
    horizontal=True,
    key="modulo_kilometraje"
)

st.markdown("---")


# ============================================================
# CONFIGURAR MÓDULO SELECCIONADO
# ============================================================

if modulo == "🛻 KM_DISTRIBUCIÓN":

    titulo_modulo = "MONITOR DE KILOMETRAJE DISTRIBUCIÓN"

    columnas = COLUMNAS_DISTRIBUCION

    columnas_mostrar = [
        "Fecha",
        "Placa",
        "Hora Inicio",
        "Km Inicial",
        "Hora Fin",
        "Km Final",
        "Tot Recorrido",
        "Nom Personal",
        "Celular",
        "Cuadrilla",
        "Item",
        "Unidad Negocio",
        "Servicio Electrico",
        "Nº OM | Cod. Recibo",
        "Descripcion Actividad",
        "CECO",
        "Estado",
        "📷 KM Inicial",
        "📷 KM Final",
        "📍 Ubicación Inicial",
        "📍 Ubicación Final",
        "Observacion"
    ]

    funcion_obtener_hoja = obtener_hoja_distribucion

    texto_fuente = (
        "Los datos se consultan desde el archivo "
        "configurado en SPREADSHEET_ID_PERDIDAS."
    )

else:

    titulo_modulo = "MONITOR DE KILOMETRAJES KM_PERDIDAS"

    columnas = COLUMNAS_PERDIDAS

    columnas_mostrar = [
        "Fecha",
        "Placa",
        "Nom Personal",
        "Celular",
        "Cuadrilla",
        "Item",
        "Unidad Negocio",
        "Servicio Electrico",
        "CECO",
        "Km Inicial",
        "Km Final",
        "Tot Recorrido",
        "Estado",
        "📷 KM Inicial",
        "📷 KM Final",
        "📍 Ubicación Inicial",
        "📍 Ubicación Final",
        "Observacion"
    ]

    funcion_obtener_hoja = obtener_hoja_perdidas

    texto_fuente = (
        "Los datos se consultan desde la hoja "
        "ControlPerdidas del archivo configurado "
        "en SPREADSHEET_ID."
    )


st.markdown(
    f"""
    <h2 style="text-align:center;">
        {titulo_modulo}
    </h2>
    """,
    unsafe_allow_html=True
)


# ============================================================
# CONSULTAR Y MOSTRAR DATOS
# ============================================================

try:
    hoja = funcion_obtener_hoja()

    df = cargar_datos(
        hoja,
        columnas
    )

    df = preparar_datos(df)

except Exception as e:
    st.error(
        "❌ No se pudo conectar con Google Sheets. "
        "Verifique los secretos, el nombre del archivo "
        "y los permisos de la cuenta de servicio."
    )

    st.exception(e)
    st.stop()


if df.empty:
    st.info(
        "ℹ️ No existen registros en este módulo."
    )

else:
    df_filtrado = aplicar_filtros(df)

    mostrar_resumen(df_filtrado)

    mostrar_tabla(
        df_filtrado,
        columnas_mostrar
    )


# ============================================================
# BOTÓN ACTUALIZAR
# ============================================================

st.markdown("---")

col_actualizar, col_info = st.columns([1, 4])

with col_actualizar:
    if st.button(
        "🔄 Actualizar",
        use_container_width=True
    ):
        st.rerun()

with col_info:
    st.caption(
        "📡 " + texto_fuente
        + " Presione «Actualizar» para consultar "
        "los registros más recientes."
    )
