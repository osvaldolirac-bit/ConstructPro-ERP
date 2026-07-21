# ConstructPro ERP — Carril Río Maipo

URL: **https://erpmaster.cl/riomaipo/**

## Por qué cae en La Concepción

En el VPS, nginx hoy hace:

```
/riomaipo  →  302  →  /laconcepcion/
```

porque **no existe** un `location /riomaipo/`.  
Los cambios en GitHub **no** modifican nginx solos: hay que instalar en el servidor.

## Modelo igual a producción / demo

| Ruta | App | Puerto |
|------|-----|--------|
| `/laconcepcion/` | Streamlit La Concepción | 85xx (ej. 8501) |
| `/demo/` | Streamlit Demo | otro 85xx |
| **`/riomaipo/`** | **Streamlit Río Maipo** | **8505** |

## Instalación en el VPS (obligatorio)

En el servidor (SSH), dentro del repo:

```bash
cd /var/www/erpmaster/constructpro-erp   # ajusta la ruta real
git pull
sudo bash scripts/install_riomaipo_vps.sh
```

Ese script:

1. Crea venv e instala dependencias  
2. Levanta systemd `riomaipo` en **127.0.0.1:8505** con `baseUrlPath=riomaipo`  
3. Crea `/etc/nginx/snippets/riomaipo-location.conf`  
4. Inserta el `include` **antes** del redirect a La Concepción  
5. Recarga nginx  

### Verificar

```bash
curl -sI https://erpmaster.cl/riomaipo/
# Debe ser HTTP 200 (NO 302 a /laconcepcion/)
```

En el navegador debe verse el banner **「ERP Master · Río Maipo」**.

Si sigue La Concepción:

```bash
sudo nginx -T 2>/dev/null | grep -n -E 'riomaipo|laconcepcion'
```

El `location /riomaipo` debe aparecer **antes** del `return 302 ... laconcepcion`.

## Módulos (estilo SOLUERP, gestión mejorada)

- **Dashboard** — embudo de cotizaciones, aging de cobranza, alertas de mora/vencimiento  
- **Clientes** — ficha + vista 360 (deuda y cotizaciones)  
- **Proveedores** / **Productos** — maestros para cotizar  
- **Cotizaciones** — ítems desde catálogo, estados, **generar CxC al aprobar**  
- **Cuentas por cobrar** — cartera, filtros, abonos, días de mora  
- **Administración** — mi empresa + parámetros (IVA, validez, crédito) 

## Local

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./scripts/start_riomaipo.sh
```

Abrir: http://127.0.0.1:8505/riomaipo/

## Nota FastAPI

También existe un carril FastAPI en `app/` (puerto 8010) como API/alternativa.  
En este VPS la ruta pública `/riomaipo` se publica con **Streamlit**, igual que demo y La Concepción.
