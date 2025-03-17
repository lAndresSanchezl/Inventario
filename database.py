from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class Usuario(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    correo = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Producto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item = db.Column(db.Integer, unique=True, nullable=False)
    equipo = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.String(200))
    serial = db.Column(db.String(100))
    ubicacion = db.Column(db.String(100))
    responsable = db.Column(db.String(100))
    observaciones = db.Column(db.Text)
    marca = db.Column(db.String(100))
    modelo = db.Column(db.String(100))
    estado = db.Column(db.String(50))
    cantidad = db.Column(db.Integer, nullable=False, default=1)
    valor = db.Column(db.Float, nullable=True)
    fecha_modificacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# Asegúrate de tener esta clase
class LogCambios(db.Model):
    __tablename__ = 'log_cambios'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=False)
    campo = db.Column(db.String(100))
    valor_anterior = db.Column(db.String(255))
    valor_nuevo = db.Column(db.String(255))
    fecha_cambio = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('Usuario', backref='logs_cambios')
    product = db.relationship('Producto', backref='logs_cambios')

# ===========================
# TABLA CELULAR unificada
# ===========================
class Celular(db.Model):
    __tablename__ = "celulares"

    id = db.Column(db.Integer, primary_key=True)
    item = db.Column(db.Integer, unique=True, nullable=False)

    marca = db.Column(db.String(100))
    numero_serial = db.Column(db.String(100))
    numeros = db.Column(db.Text)      # Almacena 1 o 2 números, con salto de línea si hay 2
    operadores = db.Column(db.Text)   # Almacena 1 o 2 operadores, con salto de línea si hay 2

    cargador = db.Column(db.Boolean, default=False)
    base = db.Column(db.Boolean, default=False)
    observaciones = db.Column(db.Text)

    fecha_modificacion = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
