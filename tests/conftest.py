import sys
import os

# Asegura que la carpeta raíz del proyecto esté en sys.path para poder importar main.py
top_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if top_dir not in sys.path:
    sys.path.insert(0, top_dir)
