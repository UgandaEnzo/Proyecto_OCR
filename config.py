import os
from sqlalchemy.orm import Session
import models

def get_config_value(db: Session, key: str, default: str = "") -> str:
    conf = db.query(models.ConfiguracionSistema).filter(models.ConfiguracionSistema.clave == key).first()
    if conf and conf.valor is not None:
        return conf.valor
    return os.getenv(key, default)

def set_config_value(db: Session, key: str, value: str):
    conf = db.query(models.ConfiguracionSistema).filter(models.ConfiguracionSistema.clave == key).first()
    if not conf:
        conf = models.ConfiguracionSistema(clave=key, valor=value)
        db.add(conf)
    else:
        conf.valor = value
    db.commit()
