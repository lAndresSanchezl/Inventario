from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
import os
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = "supersecretkey"

# 🔹 Inicializar la base de datos
db = SQLAlchemy(app)

# 🔹 Modelo de la base de datos
class Producto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item = db.Column(db.Integer, nullable=False, unique=True)
    equipo = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.String(200), nullable=True)
    serial = db.Column(db.String(100), nullable=True)
    ubicacion = db.Column(db.String(100), nullable=True)
    responsable = db.Column(db.String(100), nullable=True)
    observaciones = db.Column(db.String(255), nullable=True)
    marca = db.Column(db.String(50), nullable=True)
    modelo = db.Column(db.String(50), nullable=True)
    estado = db.Column(db.String(50), nullable=True)
    cantidad = db.Column(db.Integer, nullable=False, default=1)

# 🔹 Crear la base de datos dentro del contexto de la aplicación
with app.app_context():
    db.create_all()
    print("Base de datos creada correctamente")

@app.route('/')
def index():
    orden_actual = request.args.get('ordenar_por', 'item')

    columnas_validas = ['item', 'equipo', 'marca']
    if orden_actual not in columnas_validas:
        orden_actual = 'item'

    if orden_actual == "item":
        productos = Producto.query.order_by(db.cast(Producto.item, db.Integer).asc()).all()
    else:
        productos = Producto.query.order_by(getattr(Producto, orden_actual).asc()).all()

    return render_template('inventario.html', productos=productos, orden_actual=orden_actual)

# 🔹 Reordenar los items después de eliminar
def reordenar_items():
    productos = Producto.query.order_by(Producto.item.asc()).all()
    for i, producto in enumerate(productos, start=1):
        producto.item = i
    db.session.commit()

# 🔹 Agregar un nuevo producto
@app.route('/agregar', methods=['POST'])
def agregar():
    # 🔹 Buscar el mayor `item` actual asegurando que sea número
    ultimo_item = db.session.query(db.func.max(Producto.item)).scalar()

    # 🔹 Si no hay productos, comenzamos en 1
    if ultimo_item is None:
        nuevo_item = 1
    else:
        try:
            nuevo_item = int(ultimo_item) + 1  # Convertimos a número antes de sumar
        except ValueError:
            nuevo_item = 1  # Si hay un error, asignamos 1 para evitar fallos

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
        cantidad=int(request.form.get('cantidad', 1))
    )

    db.session.add(nuevo_producto)
    db.session.commit()
    
    return redirect('/')

# 🔹 Editar un producto existente
@app.route('/editar/<int:id>', methods=['GET', 'POST'])
def editar(id):
    producto = Producto.query.get_or_404(id)

    if request.method == 'POST':
        try:
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

            db.session.commit()
            flash('Producto actualizado con éxito', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar el producto: {str(e)}', 'danger')

    return render_template('editar.html', producto=producto)

# 🔹 Eliminar un producto y reordenar los ítems
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

# 🔹 Configuración para ejecutar la app en Render o localmente
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host='0.0.0.0', port=port)