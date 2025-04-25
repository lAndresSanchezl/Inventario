from flask import Flask, render_template, request, redirect, url_for, flash, send_file
import os
import pandas as pd
import io
import logging
from datetime import datetime, timedelta
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from flask_migrate import Migrate
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from itsdangerous import URLSafeTimedSerializer, SignatureExpired
from flask_mail import Mail, Message
from flask import g
from sqlalchemy import func 
# Importar modelos y db desde database.py
from database import db, Usuario, Producto, LogCambios, Celular, Computer, SimCard

# Asegurarse de que exista la carpeta "instance"
if not os.path.exists('instance'):
    os.makedirs('instance')

app = Flask(__name__)
app.secret_key = "supersecretkey"
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

import os
# … tus otros imports …
from flask_migrate import Migrate
from flask_mail import Mail

# ---------------------------
# Configuración de la Base de Datos
# ---------------------------
# Usar DATABASE_URL si existe (por ejemplo, una DB gestionada en Render);
# en caso contrario caer en SQLite local en instance/database.db
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///basededatos.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# ---------------------------
# Configuración de Flask-Mail
# ---------------------------
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'andres.sanchez@hablame.co'
app.config['MAIL_PASSWORD'] = 'Hablame2025'
app.config['MAIL_DEFAULT_SENDER'] = 'soporte@hablemecolombia.com'

# ---------------------------
# Inicialización de Extensiones
# ---------------------------
db.init_app(app)
migrate = Migrate(app, db)
mail = Mail(app)

logging.basicConfig(
    filename='app.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


@app.template_filter('local_time')
def local_time_filter(value):
    """Convierte una hora en UTC a la hora local (ej: UTC -5)"""
    if value is None:
        return value
    return value - timedelta(hours=5)

# ---------------------------
# Configuración de Flask-Login
# ---------------------------
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Por favor, inicia sesión para acceder a esta página."
login_manager.login_message_category = "info"

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(Usuario, int(user_id))

with app.app_context():
    # Si usas migraciones, comenta o elimina esta línea.
    db.create_all()
    print("Base de datos creada correctamente")

@app.before_request
def actualizar_ultimo_acceso():
    if current_user.is_authenticated:
        current_user.ultimo_acceso = datetime.utcnow()
        db.session.commit()

# ---------------------------
# Context processor para notificaciones
# ---------------------------
@app.context_processor
def inject_notifications():
    if current_user.is_authenticated and current_user.rol == 'admin':
        pending_requests = Usuario.query.filter_by(aprobado=False).all()
    else:
        pending_requests = []
    return dict(pending_requests=pending_requests)

import phonenumbers
from phonenumbers import geocoder

def detectar_pais(numero):
    try:
        p = phonenumbers.parse(numero, None)
        if phonenumbers.is_possible_number(p):
            return p.country_code, geocoder.region_code_for_number(p)
    except:
        pass
    return None, None

s = URLSafeTimedSerializer(app.secret_key)


# ---------------------------
# Inicialización del Generador de Tokens para Reset de Contraseña
# ---------------------------
s = URLSafeTimedSerializer(app.secret_key)

# ---------------------------
# Función para Registrar Cambios en Productos
# ---------------------------
def registrar_cambios(objeto, form, user_id, tabla='producto'):
    cambios = []
    # Excluir campos irrelevantes
    campos = [c.name for c in objeto.__table__.columns 
              if c.name not in ('id', 'fecha_modificacion')]
    
    # Detectar diferencias
    for campo in campos:
        anterior = str(getattr(objeto, campo) or "")
        nuevo    = form.get(campo, anterior)
        if anterior != nuevo:
            cambios.append((campo, anterior, nuevo))
    
    # Si no hubo cambios, salir rápido
    if not cambios:
        return False
    
    # Registrar cada cambio
    for campo, anterior, nuevo in cambios:
        log = LogCambios(
            user_id        = user_id,
            product_id     = getattr(objeto, 'id', None),
            item_registro  = getattr(objeto, 'item', None) or getattr(objeto, 'numero', None),
            tabla_afectada = tabla,
            campo          = campo,
            valor_anterior = anterior,
            valor_nuevo    = nuevo,
            tipo           = 'edicion',
            fecha_cambio   = datetime.utcnow()
        )
        db.session.add(log)
    
    # Un solo commit
    db.session.commit()
    return True

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        correo = request.form.get('correo')
        contraseña = request.form.get('contraseña')

        # Validar si ya existe el correo
        if Usuario.query.filter_by(correo=correo).first():
            flash('Este correo ya está registrado.', 'danger')
            return redirect(url_for('registro'))

        # Verificar cuántos usuarios hay en total
        total_usuarios = Usuario.query.count()

        # Crear nuevo usuario con datos básicos
        nuevo_usuario = Usuario(nombre=nombre, correo=correo)
        nuevo_usuario.set_password(contraseña)

        # Si es el primer usuario, darle rol de admin y marcar como aprobado
        if total_usuarios == 0:
            nuevo_usuario.rol = 'admin'
            nuevo_usuario.aprobado = True
            flash('Se creó el primer administrador correctamente.', 'success')
        else:
            nuevo_usuario.rol = 'usuario'  # o el valor por defecto
            nuevo_usuario.aprobado = False
            flash('Registro exitoso. Tu cuenta está pendiente de aprobación.', 'info')

        db.session.add(nuevo_usuario)
        db.session.commit()

        return redirect(url_for('login'))

    return render_template('registro.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        correo = request.form.get('correo')
        contraseña = request.form.get('contraseña')
        usuario = Usuario.query.filter_by(correo=correo).first()
        if usuario and usuario.check_password(contraseña):
            if not usuario.aprobado:
                flash('Tu cuenta está pendiente de aprobación.', 'warning')
                return redirect(url_for('login'))
            login_user(usuario)
            db.session.commit()
            flash('Inicio de sesión exitoso', 'success')
            return redirect(request.args.get('next') or url_for('index'))
        else:
            flash('Correo o contraseña incorrectos.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Sesión cerrada con éxito', 'info')
    return redirect(url_for('login'))

# ---------------------------
# Rutas para Restablecer Contraseña
# ---------------------------
@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password_request():
    # ... sin cambios ...
    return render_template('reset_password_request.html')

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password_token(token):
    # ... sin cambios ...
    return render_template('reset_password_token.html')

# ---------------------------
# Menú Usuarios
# ---------------------------
@app.route('/usuarios')
@login_required
def usuarios():
    usuarios = Usuario.query.all()
    return render_template("usuarios.html", usuarios=usuarios, now=datetime.utcnow())

# ---------------------------
# Rutas para cambio de rol y eliminación de usuarios
# ---------------------------
@app.route('/cambiar_rol/<int:user_id>', methods=['POST'])
@login_required
def cambiar_rol(user_id):
    if current_user.rol != 'admin':
        flash('Acceso denegado', 'danger')
        return redirect(url_for('usuarios'))
    if user_id == current_user.id:
        flash('No puedes cambiar tu propio rol.', 'warning')
        return redirect(url_for('usuarios'))
    u = Usuario.query.get_or_404(user_id)
    nuevo_rol = request.form['rol']
    u.rol = nuevo_rol
    db.session.commit()
    flash(f'Rol de {u.nombre} actualizado.', 'success')
    return redirect(url_for('usuarios'))

@app.route('/eliminar_usuario/<int:user_id>', methods=['POST'])
@login_required
def eliminar_usuario(user_id):
    if current_user.rol != 'admin':
        flash('Acceso denegado', 'danger')
        return redirect(url_for('usuarios'))
    if user_id == current_user.id:
        flash('No puedes eliminar tu propia cuenta.', 'warning')
        return redirect(url_for('usuarios'))
    u = Usuario.query.get_or_404(user_id)
    try:
        # 1) Eliminar todos sus logs
        LogCambios.query.filter_by(user_id=u.id).delete()
        # 2) Eliminar todos sus productos
        Producto.query.filter_by(user_id=u.id).delete()
        # 3) Finalmente, eliminar el usuario
        db.session.delete(u)
        db.session.commit()
        flash(f'Usuario {u.nombre} y sus datos eliminados con éxito.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar usuario: {e}', 'danger')
    return redirect(url_for('usuarios'))

@app.route('/aprobar/<int:user_id>', methods=['POST'])
@login_required
def aprobar(user_id):
    if current_user.rol != 'admin':
        flash('Acceso denegado', 'danger')
        return redirect(url_for('index'))
    u = Usuario.query.get_or_404(user_id)
    u.aprobado = True
    db.session.commit()
    flash(f'Usuario {u.nombre} aprobado.', 'success')
    return redirect(url_for('index'))

@app.route('/rechazar/<int:user_id>', methods=['POST'])
@login_required
def rechazar(user_id):
    if current_user.rol != 'admin':
        flash('Acceso denegado', 'danger')
        return redirect(url_for('index'))
    u = Usuario.query.get_or_404(user_id)
    db.session.delete(u)
    db.session.commit()
    flash(f'Usuario {u.nombre} rechazado.', 'info')
    return redirect(url_for('index'))


# ---------------------------
# Única ruta para Celulares (evitando duplicados)
# ---------------------------
@app.route('/celulares', endpoint='celulares_index')
@login_required
def celulares_index():
    celulares = Celular.query.order_by(Celular.item.asc()).all()
    computers = Computer.query.order_by(Computer.item.asc()).all()
    simcards = SimCard.query.order_by(SimCard.numero.asc()).all()
    return render_template('inventario_tecnologia.html',
                           celulares=celulares,
                           computers=computers,
                           simcards=simcards,
                           datetime=datetime,)

# =========================
# RUTAS PARA CELULARES CON HISTORIAL
# =========================

@app.route('/agregar_celular', methods=['POST'])
@login_required
def agregar_celular():
    current_tab = request.args.get('tab', 'celulares')
    # Obtención de datos desde el formulario
    marca = request.form.get('marca', '').strip()
    numero_serial = request.form.get('numero_serial', '').strip()
    # Validaciones básicas
    if not marca or not numero_serial:
        flash('Marca y Serial son obligatorios.', 'danger')
        return redirect(url_for('celulares_index', tab=current_tab))
    # Calcular siguiente ítem
    ultimo = db.session.query(db.func.max(Celular.item)).scalar()
    nuevo_item = 1 if ultimo is None else ultimo + 1

    # Construcción de la instancia
    nuevo = Celular(
        item=nuevo_item,
        marca=marca,
        numero_serial=numero_serial,
        cargador=('cargador' in request.form),
        base=('base' in request.form),
        observaciones=request.form.get('observaciones', '').strip()
    )
    db.session.add(nuevo)
    db.session.flush()  # para obtener nuevo.id y nuevo.item

    # Registrar logs de agregado
    for campo in ['marca', 'numero_serial', 'cargador', 'base', 'observaciones']:
        valor = getattr(nuevo, campo)
        log = LogCambios(
            user_id=current_user.id,
            product_id=nuevo.id,
            item_registro=nuevo.item,
            tabla_afectada='celulares',
            campo=campo,
            valor_anterior=None,
            valor_nuevo=str(valor),
            tipo='agregado',
            fecha_cambio=datetime.utcnow()
        )
        db.session.add(log)

    db.session.commit()
    flash('Celular agregado con éxito.', 'success')
    return redirect(url_for('celulares_index', tab=current_tab))


@app.route('/editar_celular/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_celular(id):
    current_tab = request.args.get('tab', 'celulares')
    cel = Celular.query.get_or_404(id)
    if request.method == 'POST':
        # Registrar cambios
        registrar_cambios(cel, request.form, current_user.id, tabla='celulares')
        # Actualizar campos
        cel.marca = request.form.get('marca', '').strip()
        cel.numero_serial = request.form.get('numero_serial', '').strip()
        cel.cargador = 'cargador' in request.form
        cel.base = 'base' in request.form
        cel.observaciones = request.form.get('observaciones', '').strip()
        db.session.commit()
        flash('Celular actualizado con éxito.', 'success')
        return redirect(url_for('celulares_index', tab=current_tab))
    # GET: renderizar formulario
    return render_template('editar_celular.html', cel=cel, tab=current_tab)


@app.route('/eliminar_celular/<int:id>', methods=['POST'])
@login_required
def eliminar_celular(id):
    current_tab = request.args.get('tab', 'celulares')
    cel = Celular.query.get_or_404(id)
    try:
        # Log de eliminación
        log = LogCambios(
            user_id=current_user.id,
            product_id=cel.id,
            item_registro=cel.item,
            tabla_afectada='celulares',
            campo=None,
            valor_anterior=str(cel.marca),
            valor_nuevo=None,
            tipo='eliminacion',
            fecha_cambio=datetime.utcnow()
        )
        db.session.add(log)
        db.session.delete(cel)
        db.session.commit()
        flash('Celular eliminado con éxito.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar celular: {e}', 'danger')
    return redirect(url_for('celulares_index', tab=current_tab))


# =========================
# RUTAS PARA COMPUTERS CON HISTORIAL
# =========================

@app.route('/agregar_computer', methods=['POST'])
@login_required
def agregar_computer():
    current_tab = request.args.get('tab', 'computers')
    marca = request.form.get('marca', '').strip()
    modelo = request.form.get('modelo', '').strip()
    usuario_asignado = request.form.get('usuario_asignado', '').strip()
    estado = request.form.get('estado', '').strip()
    if not marca or not usuario_asignado or not estado:
        flash('Marca, Usuario Asignado y Estado son obligatorios.', 'danger')
        return redirect(url_for('celulares_index', tab=current_tab))
    ultimo = db.session.query(db.func.max(Computer.item)).scalar()
    nuevo_item = 1 if ultimo is None else ultimo + 1

    comp = Computer(
        item=nuevo_item,
        marca=marca,
        modelo=modelo,
        usuario_asignado=usuario_asignado,
        estado=estado
    )
    db.session.add(comp)
    db.session.flush()

    for campo in ['marca', 'modelo', 'usuario_asignado', 'estado']:
        valor = getattr(comp, campo)
        log = LogCambios(
            user_id=current_user.id,
            product_id=comp.id,
            item_registro=comp.item,
            tabla_afectada='computers',
            campo=campo,
            valor_anterior=None,
            valor_nuevo=str(valor),
            tipo='agregado',
            fecha_cambio=datetime.utcnow()
        )
        db.session.add(log)

    db.session.commit()
    flash('Computador agregado con éxito.', 'success')
    return redirect(url_for('celulares_index', tab=current_tab))


@app.route('/editar_computer/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_computer(id):
    current_tab = request.args.get('tab', 'computers')
    comp = Computer.query.get_or_404(id)
    if request.method == 'POST':
        registrar_cambios(comp, request.form, current_user.id, tabla='computers')
        comp.marca = request.form.get('marca', '').strip()
        comp.modelo = request.form.get('modelo', '').strip()
        comp.usuario_asignado = request.form.get('usuario_asignado', '').strip()
        comp.estado = request.form.get('estado', '').strip()
        db.session.commit()
        flash('Computador actualizado con éxito.', 'success')
        return redirect(url_for('celulares_index', tab=current_tab))
    return render_template('editar_computer.html', computer=comp, tab=current_tab)


@app.route('/eliminar_computer/<int:id>', methods=['POST'])
@login_required
def eliminar_computer(id):
    current_tab = request.args.get('tab', 'computers')
    comp = Computer.query.get_or_404(id)
    try:
        log = LogCambios(
            user_id=current_user.id,
            product_id=comp.id,
            item_registro=comp.item,
            tabla_afectada='computers',
            campo=None,
            valor_anterior=str(comp.marca),
            valor_nuevo=None,
            tipo='eliminacion',
            fecha_cambio=datetime.utcnow()
        )
        db.session.add(log)
        db.session.delete(comp)
        db.session.commit()
        flash('Computador eliminado con éxito.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar computador: {e}', 'danger')
    return redirect(url_for('celulares_index', tab=current_tab))


# =========================
# RUTAS PARA SIMCARDS CON HISTORIAL
# =========================

@app.route('/agregar_simcard', methods=['POST'])
@login_required
def agregar_simcard():
    current_tab = request.args.get('tab', 'simcards')
    numero = request.form.get('numero', '').strip()
    operador = request.form.get('operador', '').strip()
    observaciones = request.form.get('observaciones', '').strip()
    if not numero or not operador:
        flash('Número y Operador son obligatorios.', 'danger')
        return redirect(url_for('celulares_index', tab=current_tab))
    if SimCard.query.filter_by(numero=numero).first():
        flash('La SIM ya existe.', 'warning')
        return redirect(url_for('celulares_index', tab=current_tab))
    sim = SimCard(numero=numero, operador=operador, observaciones=observaciones)
    db.session.add(sim)
    db.session.flush()

    for campo in ['numero', 'operador', 'observaciones']:
        valor = getattr(sim, campo)
        log = LogCambios(
            user_id=current_user.id,
            product_id=sim.id,
            item_registro=sim.numero,
            tabla_afectada='simcards',
            campo=campo,
            valor_anterior=None,
            valor_nuevo=str(valor),
            tipo='agregado',
            fecha_cambio=datetime.utcnow()
        )
        db.session.add(log)

    db.session.commit()
    flash('SimCard agregada con éxito.', 'success')
    return redirect(url_for('celulares_index', tab=current_tab))


@app.route('/editar_simcard/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_simcard(id):
    current_tab = request.args.get('tab', 'simcards')
    sim = SimCard.query.get_or_404(id)
    if request.method == 'POST':
        registrar_cambios(sim, request.form, current_user.id, tabla='simcards')
        sim.numero = request.form.get('numero', '').strip()
        sim.operador = request.form.get('operador', '').strip()
        sim.observaciones = request.form.get('observaciones', '').strip()
        db.session.commit()
        flash('SimCard actualizada con éxito.', 'success')
        return redirect(url_for('celulares_index', tab=current_tab))
    return render_template('editar_simcard.html', sim=sim, tab=current_tab)


@app.route('/eliminar_simcard/<int:id>', methods=['POST'])
@login_required
def eliminar_simcard(id):
    current_tab = request.args.get('tab', 'simcards')
    sim = SimCard.query.get_or_404(id)
    try:
        log = LogCambios(
            user_id=current_user.id,
            product_id=sim.id,
            item_registro=sim.numero,
            tabla_afectada='simcards',
            campo=None,
            valor_anterior=str(sim.numero),
            valor_nuevo=None,
            tipo='eliminacion',
            fecha_cambio=datetime.utcnow()
        )
        db.session.add(log)
        db.session.delete(sim)
        db.session.commit()
        flash('SimCard eliminada con éxito.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar SimCard: {e}', 'danger')
    return redirect(url_for('celulares_index', tab=current_tab))

# ---------------------------
# Rutas para Historial y Perfil
# ---------------------------
@app.route('/historial')
@login_required
def historial():
    fecha_desde = request.args.get('fecha_desde')
    fecha_hasta = request.args.get('fecha_hasta')
    tabla_sel   = request.args.get('tabla')

    logs = LogCambios.query
    if tabla_sel:
        logs = logs.filter(LogCambios.tabla_afectada == tabla_sel)
    if fecha_desde:
        logs = logs.filter(LogCambios.fecha_cambio >= fecha_desde)
    if fecha_hasta:
        logs = logs.filter(LogCambios.fecha_cambio <= fecha_hasta)

    logs = logs.order_by(LogCambios.fecha_cambio.desc()).all()
    return render_template('historial.html', logs=logs, now=datetime.utcnow())


@app.route('/perfil', methods=['GET', 'POST'])
@login_required
def perfil():
    user = current_user

    if request.method == 'POST':
        form_type = request.form.get('form_type')

        # 1) Actualizar sólo el avatar
        if form_type == 'personalizacion_avatar':
            nuevo_avatar = request.form.get('avatar_clase', '').strip()
            if nuevo_avatar:
                user.avatar_clase = nuevo_avatar
                db.session.commit()
                flash('Avatar actualizado correctamente.', 'success')
            else:
                flash('Selecciona un avatar válido.', 'danger')
            return redirect(url_for('perfil'))

        # 2) Actualizar colores y notificaciones
        if form_type == 'personalizacion_colores':
            user.primary_color = request.form.get('primary_color', user.primary_color)
            user.secondary_color = request.form.get('secondary_color', user.secondary_color)
            user.toggleNotifications = (request.form.get('toggleNotifications') == 'on')
            db.session.commit()
            flash('Preferencias de colores y notificaciones guardadas.', 'success')
            return redirect(url_for('perfil'))

        # 3) Actualizar datos personales y contraseña
        # — Nombre
        nuevo_nombre = request.form.get('nombre', '').strip()
        if nuevo_nombre:
            user.nombre = nuevo_nombre

        # — Contraseña
        old_pw = request.form.get('old_password', '')
        new_pw = request.form.get('new_password', '')
        conf_pw = request.form.get('confirm_password', '')
        if old_pw or new_pw or conf_pw:
            if not old_pw:
                flash('Debes ingresar tu contraseña actual para cambiarla.', 'danger')
                return redirect(url_for('perfil'))
            if not user.check_password(old_pw):
                flash('La contraseña actual es incorrecta.', 'danger')
                return redirect(url_for('perfil'))
            if not new_pw or not conf_pw:
                flash('Debes ingresar la nueva contraseña y su confirmación.', 'danger')
                return redirect(url_for('perfil'))
            if new_pw != conf_pw:
                flash('Las contraseñas no coinciden.', 'danger')
                return redirect(url_for('perfil'))
            user.set_password(new_pw.strip())

        db.session.commit()
        flash('Datos personales actualizados exitosamente.', 'success')
        return redirect(url_for('perfil'))

    # GET → recuperar últimas actividades y conteo
    ult_logs = (LogCambios.query
                .filter_by(user_id=user.id)
                .order_by(LogCambios.fecha_cambio.desc())
                .limit(5)
                .all())
    actividades = [
        f"[MODIFICADO] {log.campo}: '{log.valor_anterior}' ➜ '{log.valor_nuevo}' "
        f"({log.fecha_cambio.strftime('%Y-%m-%d %H:%M:%S')})"
        for log in ult_logs
    ]
    total_cambios = LogCambios.query.filter_by(user_id=user.id).count()

    return render_template('perfil.html',
                           user=user,
                           actividades=actividades,
                           total_cambios=total_cambios)


# Ruta para eliminar cuenta (se mantiene sin cambios)
@app.route('/eliminar_cuenta', methods=['POST'])
@login_required
def eliminar_cuenta():
    password_confirm = request.form.get('password_confirm', '')
    if not password_confirm:
        flash("Debe confirmar su contraseña para eliminar la cuenta.", "danger")
        return redirect(url_for('perfil'))
    if not current_user.check_password(password_confirm):
        flash("La contraseña de confirmación no coincide.", "danger")
        return redirect(url_for('perfil'))
    try:
        # Elimina los logs y el usuario
        LogCambios.query.filter_by(user_id=current_user.id).delete()
        db.session.delete(current_user)
        db.session.commit()
        flash('Cuenta eliminada exitosamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error al eliminar la cuenta: ' + str(e), 'danger')
        return redirect(url_for('perfil'))
    logout_user()
    return redirect(url_for('registro'))


# ---------------------------
# Rutas de Inventario y CRUD para Productos (Datacenter)
# ---------------------------
from datetime import datetime

@app.route('/')
@login_required
def index():
    """Listado de productos con orden y total."""
    orden = request.args.get('ordenar_por', 'item')
    validas = ['item', 'equipo', 'ubicacion', 'marca']
    if orden not in validas:
        orden = 'item'
    if orden == 'item':
        productos = Producto.query.order_by(db.cast(Producto.item, db.Integer)).all()
    else:
        productos = Producto.query.order_by(getattr(Producto, orden)).all()
    # Asegurar valor no nulo
    for p in productos:
        if p.valor is None:
            p.valor = 0.0
    total_valor = db.session.query(db.func.sum(Producto.valor * Producto.cantidad)).scalar() or 0.0
    return render_template(
        'inventario_datacenter.html',
        productos=productos,
        orden_actual=orden,
        valor_total=total_valor,
        datetime=datetime
    )

@app.route('/agregar', methods=['POST'])
@login_required
def agregar():
    """Crea un producto y registra logs de agregado."""
    try:
        # Calcular siguiente ítem automáticamente
        ultimo = db.session.query(db.func.max(Producto.item)).scalar()
        next_item = 1 if ultimo is None else int(ultimo) + 1

        # Crear instancia
        producto = Producto(
            item=next_item,
            equipo=request.form['equipo'],
            descripcion=request.form.get('descripcion'),
            serial=request.form.get('serial'),
            ubicacion=request.form.get('ubicacion'),
            responsable=request.form.get('responsable'),
            observaciones=request.form.get('observaciones'),
            marca=request.form.get('marca'),
            modelo=request.form.get('modelo'),
            estado=request.form.get('estado'),
            cantidad=int(request.form.get('cantidad', 1)),
            valor=float(request.form.get('valor')) if request.form.get('valor') else None,
            user_id=current_user.id
        )
        db.session.add(producto)
        db.session.flush()  # para obtener producto.id

        # Registrar log de agregado
        campos = [
            'equipo','descripcion','serial','ubicacion','responsable',
            'observaciones','marca','modelo','estado','cantidad','valor'
        ]
        for campo in campos:
            log = LogCambios(
                user_id=current_user.id,
                product_id=producto.id,
                item_registro=producto.item,
                tabla_afectada='producto',
                campo=campo,
                valor_anterior=None,
                valor_nuevo=str(getattr(producto, campo)),
                tipo='agregado',
                fecha_cambio=datetime.utcnow()
            )
            db.session.add(log)

        db.session.commit()
        flash('Producto agregado con éxito.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al agregar producto: {e}', 'danger')
    return redirect(url_for('index'))

@app.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    """Editar un producto y registrar cambios."""
    producto = Producto.query.get_or_404(id)
    if request.method == 'POST':
        try:
            # Registrar solo campos modificados
            registrar_cambios(producto, request.form, current_user.id, tabla='producto')

            # Actualizar
            producto.equipo = request.form['equipo']
            producto.descripcion = request.form.get('descripcion', '')
            producto.serial = request.form.get('serial', '')
            producto.ubicacion = request.form.get('ubicacion', '')
            producto.responsable = request.form.get('responsable', '')
            producto.observaciones = request.form.get('observaciones', '')
            producto.marca = request.form.get('marca', '')
            producto.modelo = request.form.get('modelo', '')
            producto.estado = request.form.get('estado', '')
            producto.cantidad = int(request.form.get('cantidad', 1))
            val = request.form.get('valor')
            producto.valor = float(val) if val else None

            db.session.commit()
            flash('Producto actualizado con éxito.', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar producto: {e}', 'danger')
    return render_template('editar.html', producto=producto)

@app.route('/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar(id):
    producto = Producto.query.get_or_404(id)
    try:
        # 1) Log de eliminación
        log = LogCambios(
            user_id=current_user.id,
            product_id=producto.id,
            item_registro=producto.item,
            tabla_afectada='producto',
            campo=None,
            valor_anterior=str(producto.equipo),
            valor_nuevo=None,
            tipo='eliminacion',
            fecha_cambio=datetime.utcnow()
        )
        db.session.add(log)

        # 2) Borrar el producto
        db.session.delete(producto)
        db.session.commit()

        # 3) REORDENAR ÍTEMS de forma manual
        productos = Producto.query.order_by(Producto.item.asc()).all()
        for idx, p in enumerate(productos, start=1):
            p.item = idx
        db.session.commit()

        flash('Producto eliminado y lista reordenada con éxito.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar producto: {e}', 'danger')
    return redirect(url_for('index'))


#Limpiar Historial#
@app.route('/limpiar_historial', methods=['POST'])
@login_required
def limpiar_historial():
    try:
        LogCambios.query.delete()
        db.session.commit()
        flash("Historial limpiado correctamente.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error al limpiar el historial: {e}", "danger")
    return redirect(url_for('historial'))

# ---------------------------
# Rutas de Exportación
# ---------------------------

@app.route('/exportar_excel')
@login_required
def exportar_excel():
    tipo = request.args.get('tipo')
    data = []

    if tipo == 'celulares':
        registros = Celular.query.order_by(Celular.item.asc()).all()
        for c in registros:
            data.append({
                "Ítem": c.item,
                "Marca": c.marca,
                "Serial": c.numero_serial,
                "Números": c.numeros,
                "Operadores": c.operadores,
                "Cargador": "Sí" if c.cargador else "No",
                "Base": "Sí" if c.base else "No",
                "Observaciones": c.observaciones,
                "Fecha Mod.": c.fecha_modificacion.strftime("%Y-%m-%d %H:%M:%S")
                               if c.fecha_modificacion else "-"
            })

    elif tipo == 'computadores':
        registros = Computer.query.order_by(Computer.item.asc()).all()
        for comp in registros:
            data.append({
                "Ítem": comp.item,
                "Marca": comp.marca,
                "Modelo": comp.modelo,
                "Usuario Asignado": comp.usuario_asignado,
                "Estado": comp.estado,
                "Fecha Mod.": comp.fecha_modificacion.strftime("%Y-%m-%d %H:%M:%S")
                               if comp.fecha_modificacion else "-"
            })

    elif tipo == 'simcards':
        registros = SimCard.query.order_by(SimCard.numero.asc()).all()
        for s in registros:
            data.append({
                "Número": s.numero,
                "Operador": s.operador,
                "Observaciones": s.observaciones,
                "Fecha Mod.": s.fecha_modificacion.strftime("%Y-%m-%d %H:%M:%S")
                               if s.fecha_modificacion else "-"
            })

    elif tipo == 'datacenter':
        # Aquí no filtramos: exportamos todos los Producto
        registros = Producto.query.order_by(Producto.item.asc()).all()
        if not registros:
            flash("No hay productos para exportar en Datacenter.", "warning")
        for p in registros:
            data.append({
                "Ítem":           p.item,
                "Equipo":         p.equipo,
                "Descripción":    p.descripcion,
                "Serial":         p.serial,
                "Ubicación":      p.ubicacion,
                "Responsable":    p.responsable,
                "Observaciones":  p.observaciones,
                "Marca":          p.marca,
                "Modelo":         p.modelo,
                "Estado":         p.estado,
                "Cantidad":       getattr(p, 'cantidad', ""),
                "Valor":          "{:,.2f}".format(p.valor) 
                                   if getattr(p, 'valor', None) is not None else "",
                "Fecha Mod.":     p.fecha_modificacion.strftime("%Y-%m-%d %H:%M:%S")
                                   if p.fecha_modificacion else "-"
            })

    else:
        flash("No se especificó el tipo de exportación.", "warning")
        return redirect(url_for('index'))

    # Generar y enviar Excel
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Inventario')
    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name=f"inventario_{tipo}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@app.route('/exportar_pdf')
@login_required
def exportar_pdf():
    tipo = request.args.get('tipo')
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=landscape(A4))
    width, height = landscape(A4)
    pdf.setFont("Helvetica-Bold", 10)

    if tipo == 'celulares':
        registros = Celular.query.order_by(Celular.item.asc()).all()
        encabezado = "Reporte de Celulares"
        columnas = ["Ítem","Marca","Serial","Números","Operadores","Cargador","Base","Observaciones","Fecha Mod."]
        x_positions = [30, 60, 110, 160, 240, 320, 380, 440, 520]

    elif tipo == 'computadores':
        registros = Computer.query.order_by(Computer.item.asc()).all()
        encabezado = "Reporte de Computadores"
        columnas = ["Ítem","Marca","Modelo","Usuario Asignado","Estado","Fecha Mod."]
        x_positions = [30, 70, 120, 220, 390, 460]

    elif tipo == 'simcards':
        registros = SimCard.query.order_by(SimCard.numero.asc()).all()
        encabezado = "Reporte de Tarjetas SIM"
        columnas = ["Número","Operador","Observaciones","Fecha Mod."]
        x_positions = [30, 100, 170, 250]

    elif tipo == 'datacenter':
        registros = Producto.query.order_by(Producto.item.asc()).all()
        encabezado = "Reporte de Datacenter"
        columnas = [
            "Ítem","Equipo","Descripción","Serial","Ubicación",
            "Responsable","Observaciones","Marca","Modelo",
            "Estado","Cantidad","Valor","Fecha Mod."
        ]
        x_positions = [30,70,180,300,390,480,580,700,820,920,1000,1080,1160]

    else:
        flash("No se especificó el tipo de exportación.", "warning")
        return redirect(url_for('index'))

    # Dibuja encabezado
    pdf.drawString(30, height - 30, encabezado)
    pdf.setFont("Helvetica", 8)
    y = height - 50
    for i, col in enumerate(columnas):
        pdf.drawString(x_positions[i], y, col)
    pdf.line(30, y - 2, width - 30, y - 2)
    y -= 20

    # Dibuja filas
    for reg in registros:
        if tipo == 'celulares':
            valores = [
                str(reg.item), reg.marca or "", reg.numero_serial or "",
                reg.numeros or "", reg.operadores or "",
                "Sí" if reg.cargador else "No", "Sí" if reg.base else "No",
                reg.observaciones or "",
                reg.fecha_modificacion.strftime("%Y-%m-%d %H:%M:%S") if reg.fecha_modificacion else "-"
            ]
        elif tipo == 'computadores':
            valores = [
                str(reg.item), reg.marca or "", reg.modelo or "",
                reg.usuario_asignado or "", reg.estado or "",
                reg.fecha_modificacion.strftime("%Y-%m-%d %H:%M:%S") if reg.fecha_modificacion else ""
            ]
        elif tipo == 'simcards':
            valores = [
                reg.numero or "", reg.operador or "",
                reg.observaciones or "",
                reg.fecha_modificacion.strftime("%Y-%m-%d %H:%M:%S") if reg.fecha_modificacion else ""
            ]
        else:  # datacenter
            valores = [
                str(reg.item), reg.equipo or "", reg.descripcion or "",
                reg.serial or "", reg.ubicacion or "", reg.responsable or "",
                reg.observaciones or "", reg.marca or "", reg.modelo or "",
                reg.estado or "",
                str(getattr(reg,'cantidad',"")),
                "{:,.2f}".format(getattr(reg,'valor',0)) 
                if getattr(reg,'valor',None) is not None else "",
                reg.fecha_modificacion.strftime("%Y-%m-%d %H:%M:%S") 
                if reg.fecha_modificacion else "-"
            ]

        for i, v in enumerate(valores):
            pdf.drawString(x_positions[i], y, v)
        y -= 12
        if y < 40:
            pdf.showPage()
            pdf.setFont("Helvetica-Bold", 10)
            pdf.drawString(30, height - 30, encabezado)
            pdf.setFont("Helvetica", 8)
            y = height - 50
            for i, col in enumerate(columnas):
                pdf.drawString(x_positions[i], y, col)
            pdf.line(30, y - 2, width - 30, y - 2)
            y -= 12

    pdf.save()
    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name=f"inventario_{tipo}.pdf",
        mimetype="application/pdf"
    )

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.debug = True
    app.run(debug=True, host='0.0.0.0', port=port)
