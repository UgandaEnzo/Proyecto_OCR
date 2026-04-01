import uvicorn
import os

if __name__ == "__main__":
    # Asegúrate de que el directorio actual esté en el PATH para que Python encuentre los módulos
    # Esto es útil cuando se ejecuta desde un .exe
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir) # Cambia el directorio de trabajo al del script

    from main import app
    uvicorn.run(app, host="0.0.0.0", port=8000)
