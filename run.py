import uvicorn
import os

if __name__ == "__main__":
    # Asegúrate de que el directorio actual esté en el PATH para que Python encuentre los módulos
    # Esto es útil cuando se ejecuta desde un .exe
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)  # Cambia el directorio de trabajo al del script

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
