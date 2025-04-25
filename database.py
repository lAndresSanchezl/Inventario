from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

# Inicializar SQLAlchemy
db = SQLAlchemy()

# Modelo de Usuario (con Flask-Login)
class Usuario(db.Model, UserMixin):
    __tablename__ = 'usuario'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    correo = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)

    # Roles y aprobación
    rol = db.Column(db.String(50), default='usuario')
    aprobado = db.Column(db.Boolean, default=False)
    ultimo_acceso = db.Column(db.DateTime, default=datetime.utcnow)
    

    # Campos para personalización:
    foto_perfil = db.Column(db.String(255), default='default.jpg')
    color_preferencia = db.Column(db.String(20), default='#ffffff')
    avatar_clase = db.Column(db.String(50), default='fas fa-user')
    primary_color = db.Column(db.String(20), default='#3498db')
    secondary_color = db.Column(db.String(20), default='#2ecc71')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


# Modelo de Productos (cada producto se vincula al usuario que lo crea)
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

    user_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    usuario = db.relationship('Usuario', backref='productos')


# Modelo de Log de Cambios
class LogCambios(db.Model):
    __tablename__ = 'log_cambios'

    id             = db.Column(db.Integer, primary_key=True)
    user_id        = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    product_id     = db.Column(db.Integer, nullable=True)     # eliminada la FK
    item_registro  = db.Column(db.String(100), nullable=True)
    campo          = db.Column(db.String(100))
    valor_anterior = db.Column(db.String(255))
    valor_nuevo    = db.Column(db.String(255))
    tipo           = db.Column(db.String(50))
    tabla_afectada = db.Column(db.String(50))
    fecha_cambio   = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('Usuario', backref='logs_cambios')

# Modelo de Celulares
class Celular(db.Model):
    __tablename__ = "celulares"

    id = db.Column(db.Integer, primary_key=True)
    item = db.Column(db.Integer, unique=True, nullable=False)
    marca = db.Column(db.String(100))
    numero_serial = db.Column(db.String(100), unique=True)
    numeros = db.Column(db.Text)
    operadores = db.Column(db.Text)
    cargador = db.Column(db.Boolean, default=False)
    base = db.Column(db.Boolean, default=False)
    observaciones = db.Column(db.Text)
    fecha_modificacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Modelo de Computadoras
class Computer(db.Model):
    __tablename__ = "computers"

    id = db.Column(db.Integer, primary_key=True)
    item = db.Column(db.Integer, unique=True, nullable=False)
    marca = db.Column(db.String(100))
    modelo = db.Column(db.String(100))
    usuario_asignado = db.Column(db.String(100))
    estado = db.Column(db.String(50))
    fecha_modificacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Modelo de SimCards
class SimCard(db.Model):
    __tablename__ = "simcards"

    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(20), unique=True, nullable=False)
    operador = db.Column(db.String(50))
    observaciones = db.Column(db.Text)
    fecha_modificacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
