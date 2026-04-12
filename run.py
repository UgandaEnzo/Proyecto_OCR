import os
import sys
import uvicorn
from pathlib import Path
from dotenv import load_dotenv

if __name__ == "__main__":
    # Asegúrate de que el directorio actual esté en el PATH para que Python encuentre los módulos.
    # Esto es útil cuando se ejecuta desde un .exe empaquetado.
    script_path = Path(sys.executable if getattr(sys, 'frozen', False) else __file__).resolve()
    script_dir = script_path.parent
    os.chdir(script_dir)

    dotenv_path = None
    search_dirs = [script_dir, script_dir.parent, script_dir.parent.parent]
    for directory in search_dirs:
        candidate = directory / '.env'
        if candidate.exists():
            dotenv_path = candidate
            break

    if dotenv_path:
        load_dotenv(dotenv_path)
    else:
        print(f"Advertencia: no se encontró .env en {script_dir} ni en los directorios superiores. Usa variables de entorno o coloca .env junto al ejecutable.")

    from main import app

    host = os.getenv("UVICORN_HOST", os.getenv("HOST", "0.0.0.0"))
    port = int(os.getenv("UVICORN_PORT", os.getenv("PORT", "8000")))

    tried_ports = [port] + [port + i for i in range(1, 5)]
    for current_port in tried_ports:
        try:
            print(f"Iniciando servidor en {host}:{current_port}")
            uvicorn.run(app, host=host, port=current_port)
            break
        except OSError as exc:
            if exc.errno == 10048:
                print(f"Puerto {current_port} en uso. Intentando siguiente puerto...")
                continue
            raise
