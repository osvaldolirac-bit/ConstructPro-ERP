import sys
import os

# 1. Le decimos al servidor dónde encontrar nuestro código del ERP
sys.path.insert(0, os.path.dirname(__file__))

# 2. Importamos la aplicación principal de FastAPI
# (Aún no creamos 'app.main', pero lo haremos en el próximo paso)
from app.main import app as application
