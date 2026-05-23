from fastapi import FastAPI

# Creamos la aplicación principal de tu ERP
app = FastAPI(
    title="ConstructPro ERP",
    description="Sistema de Gestión para la Construcción - Módulos de Cotizaciones, Cobranza e Inventario",
    version="1.0.0"
)

# Creamos la ruta inicial de bienvenida (Página de inicio)
@app.get("/")
def inicio():
    return {
        "estado": "En línea",
        "mensaje": "¡Bienvenido a ConstructPro-ERP, Osvaldo! El motor está corriendo con éxito en tu servidor."
    }
