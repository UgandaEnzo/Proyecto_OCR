import ast
import os

def refactor_main():
    with open("main.py", "r", encoding="utf-8") as f:
        source = f.read()

    tree = ast.parse(source)

    # Classify routes
    routers = {
        "clientes": [],
        "pagos": [],
        "reportes": [],
        "gestion": [],
        "ia": []
    }

    # We will keep everything that is not a Pydantic model and not a route in main.py
    main_body = []
    
    def is_route(node):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return False
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                if getattr(dec.func.value, "id", "") == "app":
                    return True
        return False

    def get_route_path(node):
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                if getattr(dec.func.value, "id", "") == "app":
                    if dec.args and isinstance(dec.args[0], ast.Constant):
                        return dec.args[0].value
        return ""

    for node in tree.body:
        if isinstance(node, ast.ClassDef) and any(
            isinstance(b, ast.Name) and b.id in ["BaseModel", "ClienteBase", "Cliente"] for b in node.bases
        ):
            continue
            
        if is_route(node):
            path = get_route_path(node)
            if not path:
                main_body.append(node)
                continue
                
            if path.startswith("/cliente") or "/gestion/clientes" in path:
                routers["clientes"].append(node)
            elif path.startswith("/reportes"):
                routers["reportes"].append(node)
            elif path.startswith("/IA") or "/ia/" in path or path.startswith("/detectar-banco"):
                routers["ia"].append(node)
            elif "/gestion/db" in path or path.startswith("/gestion"):
                routers["gestion"].append(node)
            elif path == "/" or path == "/panel" or path == "/favicon.ico" or path == "/healthz":
                main_body.append(node)
            else:
                routers["pagos"].append(node)
        else:
            main_body.append(node)

    os.makedirs("routers", exist_ok=True)
    
    router_imports = """
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form, Header
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, desc, or_, text
from typing import Optional, List
from datetime import datetime
import os, io, csv, uuid, hashlib, tempfile, base64, re, json
import models, schemas, bank_rules, ocr_engine
from database import get_db
from config import get_config_value, set_config_value
from main import require_api_key, registrar_auditoria, logger, get_tasa_bcv, _get_sqlite_db_path, _get_database_type
from exchange import convertir_payments, TasaNoDisponibleError

"""

    for name, nodes in routers.items():
        if not nodes: continue
        with open(f"routers/{name}.py", "w", encoding="utf-8") as f:
            f.write(router_imports)
            f.write(f"router = APIRouter(tags=['{name}'])\n\n")
            for node in nodes:
                # Replace @app.get with @router.get
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and getattr(dec.func.value, "id", "") == "app":
                        dec.func.value.id = "router"
                code = ast.unparse(node)
                # Quick fix for type hints
                code = code.replace(": ClienteBase", ": schemas.ClienteBase")
                code = code.replace("-> Cliente:", "-> schemas.Cliente:")
                code = code.replace("-> List[Cliente]", "-> List[schemas.Cliente]")
                code = code.replace(": ClienteConPagos", ": schemas.ClienteConPagos")
                code = code.replace(": ChatQuery", ": schemas.ChatQuery")
                code = code.replace(": ConversionRequest", ": schemas.ConversionRequest")
                code = code.replace(": TasaBCVUpdate", ": schemas.TasaBCVUpdate")
                code = code.replace(": PagoManual", ": schemas.PagoManual")
                code = code.replace(": EstadoUpdate", ": schemas.EstadoUpdate")
                code = code.replace(": VisionBankDetectionRequest", ": schemas.VisionBankDetectionRequest")
                code = code.replace(": GestionApiKey", ": schemas.GestionApiKey")
                code = code.replace(": GestionCredentials", ": schemas.GestionCredentials")
                code = code.replace(": ConfirmBody", ": schemas.ConfirmBody")
                f.write(code + "\n\n")

    tree.body = main_body
    with open("main_refactored.py", "w", encoding="utf-8") as f:
        code = ast.unparse(tree)
        imports = """
import schemas
from routers import clientes, pagos, reportes, gestion, ia
from config import get_config_value, set_config_value

"""
        code = imports + code
        includes = """
app.include_router(clientes.router)
app.include_router(pagos.router)
app.include_router(reportes.router)
app.include_router(gestion.router)
app.include_router(ia.router)
"""
        code = code + includes
        f.write(code)

if __name__ == "__main__":
    refactor_main()
