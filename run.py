import uvicorn

if __name__ == "__main__":
    # Importamos la app de FastAPI desde main.py.
    # Se hace aquí dentro para que PyInstaller la detecte correctamente.
    from main import app

    # Ejecutamos el servidor Uvicorn.
    # Usamos host="0.0.0.0" para que sea accesible desde otras máquinas en la red
    # y definimos un puerto estándar.
    uvicorn.run(app, host="0.0.0.0", port=8000)