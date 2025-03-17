# main.py

from flask import Flask, render_template, request, redirect, url_for, flash, send_file
import os
import pandas as pd
import io
import logging
from datetime import datetime
from reportlab.lib.pagesizes import A4, landscape, letter
from reportlab.pdfgen import canvas
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

from database import db, Usuario, Producto, LogCambios, Celular  # Importamos también Celular
from flask_login import LoginManager, login_user, logout_user, login_required, current_user

if not os.path.exists('instance'):
    os.makedirs('instance')

app = Flask(__name__)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'app.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = "supersecretkey"

db.init_app(app)
migrate = Migrate(app, db)

logging.basicConfig(
    filename='app.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Por favor, inicia sesión para acceder a esta página."
login_manager.login_message_category = "info"

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

with app.app_context():
    db.create_all()  # Si no quieres recrear DB cada vez, comenta esto
    print("Base de datos creada correctamente")

import phonenumbers
from phonenumbers import geocoder

def detectar_pais(numero_telefonico):
    # Intentar parsear, asumiendo por defecto que es "CO" (Colombia)
    try:
        phone_obj = phonenumbers.parse(numero_telefonico, None)
        if phonenumbers.is_possible_number(phone_obj):
            country_code = phone_obj.country_code
            region_code = geocoder.region_code_for_number(phone_obj)
            # Ej: country_code=57, region_code="CO"
            return country_code, region_code
        else:
            return None, None
    except:
        return None, None


# -----------------------------
# Rutas de registro / login
# -----------------------------
@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        correo = request.form.get('correo')
        contraseña = request.form.get('contraseña')

        usuario_existente = Usuario.query.filter_by(correo=correo).first()
        if usuario_existente:
            flash('Este correo ya está registrado.', 'danger')
            return redirect(url_for('registro'))

        nuevo_usuario = Usuario(nombre=nombre, correo=correo)
        nuevo_usuario.set_password(contraseña)
        db.session.add(nuevo_usuario)
        db.session.commit()

        flash('Registro exitoso. Ahora puedes iniciar sesión.', 'success')
        return redirect(url_for('login'))

    return render_template('registro.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        correo = request.form.get('correo')
        contraseña = request.form.get('contraseña')

        if 'next' in request.args:
            flash('Por favor, inicia sesión para acceder a esta página.', 'info')

        usuario = Usuario.query.filter_by(correo=correo).first()

        if usuario and usuario.check_password(contraseña):
            login_user(usuario)
            flash('Inicio de sesión exitoso', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            flash('Correo o contraseña incorrectos', 'danger')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Sesión cerrada con éxito', 'info')
    return redirect(url_for('login'))


# -----------------------------
# Función para registrar cambios
# -----------------------------
def registrar_cambios(producto, form, user_id):
    """
    Compara los valores antiguos de 'producto' con los nuevos en 'form'
    y crea registros LogCambios por cada campo diferente.
    """
    cambios = []
    campos_texto = [
        'equipo', 'descripcion', 'serial', 'ubicacion',
        'responsable', 'observaciones', 'marca', 'modelo', 'estado'
    ]
    for campo in campos_texto:
        valor_anterior = getattr(producto, campo) or ""
        valor_nuevo = form.get(campo, "")
        if valor_anterior != valor_nuevo:
            cambios.append((campo, valor_anterior, valor_nuevo))

    # Revisar campo 'cantidad'
    cant_anterior = str(producto.cantidad)
    cant_nueva = form.get('cantidad', "1")
    if cant_anterior != cant_nueva:
        cambios.append(('cantidad', cant_anterior, cant_nueva))

    # Revisar campo 'valor'
    val_anterior = str(producto.valor if producto.valor is not None else "")
    val_nuevo = form.get('valor', "")
    if val_anterior != val_nuevo:
        cambios.append(('valor', val_anterior, val_nuevo))

    # Crear registros
    for (campo, anterior, nuevo) in cambios:
        log = LogCambios(
            user_id=user_id,
            product_id=producto.id,
            campo=campo,
            valor_anterior=anterior,
            valor_nuevo=nuevo
        )
        db.session.add(log)


# -----------------------------
# Ruta principal (inventario)
# -----------------------------
@app.route('/')
@login_required
def index():
    orden_actual = request.args.get('ordenar_por', 'item')
    columnas_validas = ['item', 'equipo', 'marca']
    if orden_actual not in columnas_validas:
        orden_actual = 'item'

    if orden_actual == "item":
        productos = Producto.query.order_by(db.cast(Producto.item, db.Integer).asc()).all()
    else:
        productos = Producto.query.order_by(getattr(Producto, orden_actual).asc()).all()

    for producto in productos:
        if producto.valor is None:
            producto.valor = 0.0

    valor_total = db.session.query(db.func.sum(Producto.valor * Producto.cantidad)).scalar()
    if valor_total is None:
        valor_total = 0.0

    return render_template('inventario.html', productos=productos, orden_actual=orden_actual, valor_total=valor_total)


# ========== RUTA: CELULARES INDEX ==========
@app.route('/celulares', endpoint='celulares_index')
@login_required
def celulares_index():
    """Lista todos los celulares."""
    celulares = Celular.query.order_by(Celular.item.asc()).all()
    return render_template('celulares.html', celulares=celulares)

# ========== RUTA: AGREGAR CELULAR ==========
import re

@app.route('/agregar_celular', methods=['POST'])
@login_required
def agregar_celular():
    # Determinar item nuevo
    ultimo_item = db.session.query(db.func.max(Celular.item)).scalar()
    nuevo_item = (ultimo_item + 1) if ultimo_item else 1

    marca = request.form.get('marca', '').strip()
    numero_serial = request.form.get('numero_serial', '').strip()

    # 1) Limpiar dígitos
    raw_num1 = request.form.get('numero1', '').strip()
    raw_num2 = request.form.get('numero2', '').strip()
    num1 = re.sub(r'\D+', '', raw_num1)
    num2 = re.sub(r'\D+', '', raw_num2)

    # 2) Concatenar
    if num1 and num2:
        numeros_final = f"{num1}<br>{num2}"
    elif num1:
        numeros_final = num1
    elif num2:
        numeros_final = num2
    else:
        numeros_final = ""

    # 3) Operadores
    op1 = request.form.get('operador1', '').strip()
    op2 = request.form.get('operador2', '').strip()

    if op1 and op2:
        operadores_final = f"{op1}<br>{op2}"
    elif op1:
        operadores_final = op1
    elif op2:
        operadores_final = op2
    else:
        operadores_final = ""

    # 4) c = Celular(...)
    c = Celular(
        item=nuevo_item,
        marca=marca,
        numero_serial=numero_serial,
        numeros=numeros_final,
        operadores=operadores_final,
        cargador=('cargador' in request.form),
        base=('base' in request.form),
        observaciones=request.form.get('observaciones', '').strip()
    )
    db.session.add(c)
    db.session.commit()

    flash("Celular agregado con éxito", "success")
    return redirect(url_for('celulares_index'))

########################################
# FUNCIÓN PARA FORMATEAR NÚMEROS
########################################
def format_phone_number(num_raw: str) -> str:
    """
    - Recibe un string que puede contener letras/dígitos.
    - Lo filtra para solo dejar dígitos.
    - Si es un número de 10 dígitos que empieza por '3', asumimos Colombia => le ponemos +57.
    - De lo contrario, devolvemos el número sin prefijo.
    """
    digits_only = ''.join(ch for ch in num_raw if ch.isdigit())
    if not digits_only:
        return ""

    # Si es un 10 dígitos y empieza por '3', asumimos Colombia => +57
    if len(digits_only) == 10 and digits_only.startswith('3'):
        return f"+57 {digits_only}"
    else:
        # Simplemente devolvemos los dígitos
        return digits_only


########################################
# RUTAS DE CELULARES
########################################

@app.route('/celulares')  # <--- sin endpoint duplicado
@login_required
def lista_celulares():
    """Listar los celulares en la tabla."""
    lista_cel = Celular.query.order_by(Celular.item.asc()).all()
    return render_template('celulares.html', celulares=lista_cel)


@app.route('/agregar_celular', methods=['POST'])
@login_required
def agregar_celular():
    """Agregar un nuevo celular, juntando los 2 números y 2 operadores en un solo campo cada uno."""
    # Determinar nuevo ítem
    ultimo_item = db.session.query(db.func.max(Celular.item)).scalar()
    nuevo_item = 1 if ultimo_item is None else ultimo_item + 1

    # Leer campos del formulario
    marca = request.form.get('marca', '').strip()
    numero_serial = request.form.get('numero_serial', '').strip()

    # Números
    numero1 = request.form.get('numero1', '').strip()
    numero2 = request.form.get('numero2', '').strip()

    # Operadores
    operador1 = request.form.get('operador1', '').strip()
    operador2 = request.form.get('operador2', '').strip()

    # Checkbox
    cargador_val = ('cargador' in request.form)
    base_val = ('base' in request.form)
    observaciones = request.form.get('observaciones', '').strip()

    # Formatear y validar los números
    num1_formatted = format_phone_number(numero1)
    num2_formatted = format_phone_number(numero2)

    # Concatenar con salto de línea si hay 2
    if num1_formatted and num2_formatted:
        numeros_final = num1_formatted + "\n" + num2_formatted
    elif num1_formatted:
        numeros_final = num1_formatted
    elif num2_formatted:
        numeros_final = num2_formatted
    else:
        numeros_final = ""

    # Concatenar operadores con salto de línea si hay 2
    if operador1 and operador2:
        operadores_final = operador1 + "\n" + operador2
    elif operador1:
        operadores_final = operador1
    elif operador2:
        operadores_final = operador2
    else:
        operadores_final = ""

    # Crear Celular
    nuevo_cel = Celular(
        item=nuevo_item,
        marca=marca,
        numero_serial=numero_serial,
        numeros=numeros_final,
        operadores=operadores_final,
        cargador=cargador_val,
        base=base_val,
        observaciones=observaciones
    )
    db.session.add(nuevo_cel)
    db.session.commit()

    flash("Celular agregado con éxito", "success")
    return redirect(url_for('lista_celulares'))


@app.route('/editar_celular/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_celular(id):
    """Editar un celular, separando 'numeros' y 'operadores' en 2 campos cada uno (si existen)."""
    cel = Celular.query.get_or_404(id)

    if request.method == 'POST':
        try:
            marca = request.form.get('marca', '').strip()
            numero_serial = request.form.get('numero_serial', '').strip()

            numero1 = request.form.get('numero1', '').strip()
            numero2 = request.form.get('numero2', '').strip()
            op1 = request.form.get('operador1', '').strip()
            op2 = request.form.get('operador2', '').strip()

            cargador_val = ('cargador' in request.form)
            base_val = ('base' in request.form)
            obs = request.form.get('observaciones', '').strip()

            # Formatear números
            num1_formatted = format_phone_number(numero1)
            num2_formatted = format_phone_number(numero2)

            if num1_formatted and num2_formatted:
                numeros_final = num1_formatted + "\n" + num2_formatted
            elif num1_formatted:
                numeros_final = num1_formatted
            elif num2_formatted:
                numeros_final = num2_formatted
            else:
                numeros_final = ""

            # Operadores
            if op1 and op2:
                operadores_final = op1 + "\n" + op2
            elif op1:
                operadores_final = op1
            elif op2:
                operadores_final = op2
            else:
                operadores_final = ""

            # Asignar
            cel.marca = marca
            cel.numero_serial = numero_serial
            cel.numeros = numeros_final
            cel.operadores = operadores_final
            cel.cargador = cargador_val
            cel.base = base_val
            cel.observaciones = obs

            db.session.commit()
            flash('Celular actualizado con éxito', 'success')
            return redirect(url_for('lista_celulares'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar el celular: {str(e)}', 'danger')
            return redirect(url_for('lista_celulares'))
    else:
        # Separar en 2 los saltos de línea
        nums = (cel.numeros or "").split("\n")
        if len(nums) >= 2:
            numero1_edit = nums[0]
            numero2_edit = nums[1]
        else:
            numero1_edit = cel.numeros or ""
            numero2_edit = ""

        ops = (cel.operadores or "").split("\n")
        if len(ops) >= 2:
            operador1_edit = ops[0]
            operador2_edit = ops[1]
        else:
            operador1_edit = cel.operadores or ""
            operador2_edit = ""

        return render_template(
            'editar_celular.html',
            cel=cel,
            numero1_edit=numero1_edit,
            numero2_edit=numero2_edit,
            operador1_edit=operador1_edit,
            operador2_edit=operador2_edit
        )


@app.route('/eliminar_celular/<int:id>', methods=['POST'])
@login_required
def eliminar_celular(id):
    cel = Celular.query.get_or_404(id)
    try:
        db.session.delete(cel)
        db.session.commit()
        flash('Celular eliminado correctamente', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar el celular: {e}', 'danger')
    return redirect(url_for('lista_celulares'))


############################
# Exportar Excel / PDF
############################
@app.route('/exportar_excel_celulares')
@login_required
def exportar_excel_celulares():
    celulares = Celular.query.all()
    data = []
    for c in celulares:
        data.append({
            "Item": c.item,
            "Marca": c.marca or "-",
            "Núm. Serial": c.numero_serial or "-",
            "Números": c.numeros or "-",
            "Operadores": c.operadores or "-",
            "Cargador": "Sí" if c.cargador else "No",
            "Base": "Sí" if c.base else "No",
            "Observaciones": c.observaciones or "-",
            "Fecha Mod.": c.fecha_modificacion.strftime("%Y-%m-%d %H:%M:%S") if c.fecha_modificacion else "-"
        })

    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Celulares')
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name="celulares.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@app.route('/exportar_pdf_celulares')
@login_required
def exportar_pdf_celulares():
    celulares = Celular.query.all()
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=landscape(A4))
    width, height = landscape(A4)

    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(30, height - 30, "Reporte de Celulares (Horizontal)")
    pdf.setFont("Helvetica", 8)

    encabezados = [
        "Item", "Marca", "Núm. Serial", "Números", "Operadores",
        "Cargador", "Base", "Observaciones"
    ]
    x_positions = [30, 80, 140, 220, 300, 380, 440, 500]

    y_position = height - 50
    for i, enc in enumerate(encabezados):
        pdf.drawString(x_positions[i], y_position, enc)
    pdf.line(30, y_position - 2, 700, y_position - 2)

    line_height = 12
    y_position -= 20

    for c in celulares:
        # Reemplazar salto de línea por " / " para que no se corte
        num_for_pdf = (c.numeros or "").replace("\n", " / ")
        op_for_pdf = (c.operadores or "").replace("\n", " / ")

        datos = [
            str(c.item),
            (c.marca or "")[:10],
            (c.numero_serial or "")[:10],
            num_for_pdf[:12],
            op_for_pdf[:12],
            "Sí" if c.cargador else "No",
            "Sí" if c.base else "No",
            (c.observaciones or "")[:15]
        ]
        for i, dato in enumerate(datos):
            pdf.drawString(x_positions[i], y_position, dato)
        y_position -= line_height

        if y_position < 40:
            pdf.showPage()
            pdf.setFont("Helvetica-Bold", 10)
            pdf.drawString(30, height - 30, "Reporte de Celulares (Horizontal)")
            pdf.setFont("Helvetica", 8)
            y_position = height - 50
            for j, enc in enumerate(encabezados):
                pdf.drawString(x_positions[j], y_position, enc)
            pdf.line(30, y_position - 2, 700, y_position - 2)
            y_position -= 20

    pdf.save()
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name="celulares.pdf",
        mimetype="application/pdf"
    )

# -----------------------------
# Función reordenar ítems
# -----------------------------
def reordenar_items():
    productos = Producto.query.order_by(Producto.item.asc()).all()
    for i, producto in enumerate(productos, start=1):
        producto.item = i
    db.session.commit()


# -----------------------------
# Ruta agregar producto
# -----------------------------
@app.route('/agregar', methods=['POST'])
def agregar():
    ultimo_item = db.session.query(db.func.max(Producto.item)).scalar()
    if ultimo_item is None:
        nuevo_item = 1
    else:
        try:
            nuevo_item = int(ultimo_item) + 1
        except ValueError:
            nuevo_item = 1

    valor = request.form.get("valor", "0")
    try:
        valor = float(valor)
    except ValueError:
        valor = 0.0

    nuevo_producto = Producto(
        item=nuevo_item,
        equipo=request.form['equipo'],
        descripcion=request.form.get('descripcion', ""),
        serial=request.form.get('serial', ""),
        ubicacion=request.form.get('ubicacion', ""),
        responsable=request.form.get('responsable', ""),
        observaciones=request.form.get('observaciones', ""),
        marca=request.form.get('marca', ""),
        modelo=request.form.get('modelo', ""),
        estado=request.form.get('estado', ""),
        cantidad=int(request.form.get('cantidad', 1)),
        valor=valor
    )
    db.session.add(nuevo_producto)
    db.session.commit()
    flash("Producto agregado con éxito", "success")
    return redirect(url_for('index'))


# -----------------------------
# Ruta editar producto
# -----------------------------
@app.route('/editar/<int:id>', methods=['GET', 'POST'])
def editar(id):
    producto = Producto.query.get_or_404(id)
    if request.method == 'POST':
        try:
            registrar_cambios(producto, request.form, current_user.id)

            producto.equipo = request.form['equipo']
            producto.descripcion = request.form.get('descripcion', "")
            producto.serial = request.form.get('serial', "")
            producto.ubicacion = request.form.get('ubicacion', "")
            producto.responsable = request.form.get('responsable', "")
            producto.observaciones = request.form.get('observaciones', "")
            producto.marca = request.form.get('marca', "")
            producto.modelo = request.form.get('modelo', "")
            producto.estado = request.form.get('estado', "")
            producto.cantidad = int(request.form.get('cantidad', 1))

            valor = request.form.get("valor")
            if valor is not None and valor.strip() != "":
                try:
                    producto.valor = float(valor)
                except ValueError:
                    flash("Error: El campo 'Valor' debe ser un número válido.", "danger")
                    return redirect(url_for('editar', id=id))
            else:
                producto.valor = None

            db.session.commit()
            flash('Producto actualizado con éxito', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar el producto: {str(e)}', 'danger')

    return render_template('editar.html', producto=producto)


# -----------------------------
# Ruta eliminar producto
# -----------------------------
@app.route('/eliminar/<int:id>', methods=['POST'])
def eliminar(id):
    producto = Producto.query.get_or_404(id)
    try:
        db.session.delete(producto)
        db.session.commit()
        reordenar_items()
        flash('Producto eliminado correctamente', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar el producto: {e}', 'danger')
    return redirect(url_for('index'))


# -----------------------------
# Ruta HISTORIAL de cambios
# -----------------------------
@app.route('/historial')
@login_required
def historial():
    logs = LogCambios.query.order_by(LogCambios.fecha_cambio.desc()).all()
    return render_template('historial.html', logs=logs)


# -----------------------------
# Ruta PERFIL (Mi Perfil)
# -----------------------------
@app.route('/perfil', methods=['GET', 'POST'])
@login_required
def perfil():
    user = current_user
    if request.method == 'POST':
        nuevo_nombre = request.form.get('nombre', '').strip()
        if nuevo_nombre:
            user.nombre = nuevo_nombre

        old_password = request.form.get('old_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        # Caso 1: No cambia contraseña
        if not old_password and not new_password and not confirm_password:
            db.session.commit()
            flash('Perfil actualizado con éxito (sin cambiar contraseña).', 'success')
            return redirect(url_for('perfil'))

        # Caso 2: Cambiar contraseña
        if not old_password:
            flash('Para cambiar tu contraseña, debes ingresar la contraseña actual.', 'danger')
            return redirect(url_for('perfil'))

        if not user.check_password(old_password):
            flash('La contraseña actual es incorrecta.', 'danger')
            return redirect(url_for('perfil'))

        if not new_password or not confirm_password:
            flash('Debes ingresar la nueva contraseña y su confirmación.', 'danger')
            return redirect(url_for('perfil'))

        if new_password != confirm_password:
            flash('Las contraseñas nuevas no coinciden.', 'danger')
            return redirect(url_for('perfil'))

        user.set_password(new_password.strip())
        db.session.commit()
        flash('Perfil y contraseña actualizados con éxito.', 'success')
        return redirect(url_for('perfil'))

    return render_template('perfil.html', user=user)


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
