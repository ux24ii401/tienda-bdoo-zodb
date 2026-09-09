import os
import transaction
from persistent import Persistent
from persistent.list import PersistentList
from ZODB import DB, FileStorage
from datetime import datetime

# =====================================================================
# 1. IMPLEMENTACIÓN DE CLASES PERSISTENTES (Diseño de Dominio)
# =====================================================================

class Producto(Persistent):
    def __init__(self, skuCode, nombre, descripcion, precio, existencias, categoria, proveedor=None):
        self.skuCode = skuCode
        self.nombre = nombre
        self.descripcion = descripcion
        self.precio = precio
        self.existencias = existencias
        self.categoria = categoria
        self.proveedor = proveedor  # Referencia directa al objeto Proveedor

    def ingresarStock(self, cantidad):
        """Lógica de negocio: Incrementar existencias"""
        if cantidad > 0:
            self.existencias += cantidad

    def descontarStock(self, cantidad):
        """Lógica de negocio: Disminuir existencias"""
        if 0 < cantidad <= self.existencias:
            self.existencias -= cantidad
            return True
        return False

    def hayExistencias(self, cantidadReq):
        return self.existencias >= cantidadReq

    def modificarPrecio(self, monto):
        if monto > 0:
            self.precio = monto


class Cliente(Persistent):
    def __init__(self, idCliente, nombre, telefono, email):
        self.idCliente = idCliente
        self.nombre = nombre
        self.telefono = telefono
        self.email = email
        self.puntosFidelidad = 0
        self.ventas = PersistentList()  # Colección persistente de referencias a Ventas

    def sumarPuntos(self, monto):
        # 1 punto por cada $10 de compra
        self.puntosFidelidad += int(monto // 10)


class Proveedor(Persistent):
    def __init__(self, idProveedor, razonSocial, contactoDirecto, telefono, email):
        self.idProveedor = idProveedor
        self.razonSocial = razonSocial
        self.contactoDirecto = contactoDirecto
        self.telefono = telefono
        self.email = email
        self.productos = PersistentList()  # Referencias a productos surtidos


class DetalleVenta(Persistent):
    def __init__(self, idLinea, producto, cantidad):
        self.idLinea = idLinea
        self.producto = producto  # Referencia directa al objeto Producto
        self.cantidad = cantidad
        self.precioCapturado = producto.precio
        self.subtotalCalculado = self.calcularSubtotal()

    def calcularSubtotal(self):
        return self.precioCapturado * self.cantidad


class Venta(Persistent):
    def __init__(self, folioVenta, cliente):
        self.folioVenta = folioVenta
        self.cliente = cliente  # Referencia directa al Cliente
        self.fechaHora = datetime.now()
        self.subtotal = 0.0
        self.impuesto = 0.0
        self.total = 0.0
        self.estado = "Pendiente"
        self.detalles = PersistentList()  # Colección de objetos DetalleVenta

    def anadirRenglon(self, producto, cantidad):
        """Lógica de negocio: Agregar producto a la venta y actualizar inventario"""
        if producto.descontarStock(cantidad):
            id_linea = f"DET-{len(self.detalles) + 1:03d}"
            detalle = DetalleVenta(id_linea, producto, cantidad)
            self.detalles.append(detalle)
            self.calcularMontos()
            return True
        return False

    def calcularMontos(self):
        """Lógica de negocio: Calcular total de venta"""
        self.subtotal = sum(d.subtotalCalculado for d in self.detalles)
        self.impuesto = self.subtotal * 0.16  # IVA 16%
        self.total = self.subtotal + self.impuesto

    def cerrarTransaccion(self):
        if self.detalles:
            self.estado = "Completada"
            self.cliente.sumarPuntos(self.total)


# =====================================================================
# 2. GESTOR DE LA BASE DE DATOS BDOO (ZODB)
# =====================================================================

class TiendaBDOO:
    def __init__(self, db_path="tienda_db.fs"):
        self.db_path = db_path
        self.storage = FileStorage.FileStorage(self.db_path)
        self.db = DB(self.storage)
        self.connection = self.db.open()
        self.dbroot = self.connection.root()

        # Inicializar contenedores principales si no existen
        if 'productos' not in self.dbroot:
            self.dbroot['productos'] = PersistentList()
        if 'clientes' not in self.dbroot:
            self.dbroot['clientes'] = PersistentList()
        if 'proveedores' not in self.dbroot:
            self.dbroot['proveedores'] = PersistentList()
        if 'ventas' not in self.dbroot:
            self.dbroot['ventas'] = PersistentList()
        transaction.commit()

    def cerrar(self):
        self.connection.close()
        self.db.close()

    # --- OPERACIONES CRUD BÁSICAS ---
    def crear_producto(self, producto):
        self.dbroot['productos'].append(producto)
        if producto.proveedor and producto not in producto.proveedor.productos:
            producto.proveedor.productos.append(producto)
        transaction.commit()

    def consultar_productos(self):
        return list(self.dbroot['productos'])

    def modificar_precio_producto(self, skuCode, nuevo_precio):
        for prod in self.dbroot['productos']:
            if prod.skuCode == skuCode:
                prod.modificarPrecio(nuevo_precio)
                transaction.commit()
                return True
        return False

    def eliminar_producto(self, skuCode):
        for prod in self.dbroot['productos']:
            if prod.skuCode == skuCode:
                self.dbroot['productos'].remove(prod)
                transaction.commit()
                return True
        return False

    # --- CONSULTAS REQUERIDAS ---
    def productos_precio_mayor_a(self, monto):
        return [p for p in self.dbroot['productos'] if p.precio > monto]

    def productos_stock_menor_a(self, limite):
        return [p for p in self.dbroot['productos'] if p.existencias < limite]

    def productos_por_proveedor(self, idProveedor):
        return [p for p in self.dbroot['productos'] if p.proveedor and p.proveedor.idProveedor == idProveedor]

    def total_ventas_acumulado(self):
        return sum(v.total for v in self.dbroot['ventas'] if v.estado == "Completada")


# =====================================================================
# 3. DEMOSTRACIÓN DE PERSISTENCIA Y CICLO DE VIDA COMPLETO
# =====================================================================

def ejecutar_demostracion():
    db_file = "tienda_db.fs"

    print("=== PASO 1: Creación de objetos y guardado en ZODB ===")
    app1 = TiendaBDOO(db_file)

    # 1. Crear Proveedor
    prov1 = Proveedor("PROV-01", "Distribuidora Tech SA", "Carlos Mendoza", "555-1234", "contacto@tech.com")
    app1.dbroot['proveedores'].append(prov1)

    # 2. Crear Productos (Alta de objetos)
    p1 = Producto("PROD-101", "Laptop Pro", "16GB RAM, 512GB SSD", 15000.0, 10, "Electrónica", prov1)
    p2 = Producto("PROD-102", "Mouse Inalámbrico", "Óptico 1600 DPI", 350.0, 25, "Accesorios", prov1)
    p3 = Producto("PROD-103", "Teclado Mecánico", "Switch Blue RGB", 1200.0, 4, "Accesorios", prov1)

    app1.crear_producto(p1)
    app1.crear_producto(p2)
    app1.crear_producto(p3)

    # 3. Crear Cliente
    cli1 = Cliente("CLI-01", "Ana Gómez", "555-9876", "ana@email.com")
    app1.dbroot['clientes'].append(cli1)

    # 4. Registrar Venta (Lógica de Negocio)
    venta1 = Venta("VEN-2026-001", cli1)
    venta1.anadirRenglon(p1, 1)  # Agrega 1 Laptop (descuenta stock)
    venta1.anadirRenglon(p2, 2)  # Agrega 2 Mouses (descuenta stock)
    venta1.cerrarTransaccion()

    app1.dbroot['ventas'].append(venta1)
    cli1.ventas.append(venta1)

    # Confirmar cambios y cerrar la sesión de la app
    transaction.commit()
    print("-> Objetos creados. transaction.commit() ejecutado con éxito.")
    app1.cerrar()
    print("-> Aplicación cerrada completamente.\n")

    # -----------------------------------------------------------------

    print("=== PASO 2: Reapertura de la aplicación y verificación ===")
    app2 = TiendaBDOO(db_file)
    print("-> Aplicación reabierta. Recuperando datos desde ZODB...\n")

    # Comprobar que la información sigue disponible
    productos_recuperados = app2.consultar_productos()
    print(f"Total productos en base de datos: {len(productos_recuperados)}")

    # 5. Modificación de Objetos
    print("\n--- Modificación de Objetos ---")
    app2.modificar_precio_producto("PROD-102", 399.99)
    print("Precio de 'Mouse Inalámbrico' actualizado a $399.99.")

    p3_obj = [p for p in productos_recuperados if p.skuCode == "PROD-103"][0]
    p3_obj.ingresarStock(10)  # Incrementar existencias (Lógica de negocio)
    transaction.commit()
    print("Stock de 'Teclado Mecánico' incrementado en 10 unidades.")

    # 6. Consultas Requeridas
    print("\n--- EJECUCIÓN DE CONSULTAS REQUERIDAS ---")

    print("\n1. Mostrar todos los productos registrados:")
    for p in app2.consultar_productos():
        prov_nom = p.proveedor.razonSocial if p.proveedor else "Sin Proveedor"
        print(f" - [{p.skuCode}] {p.nombre} | Precio: ${p.precio} | Stock: {p.existencias} | Prov: {prov_nom}")

    print("\n2. Productos con precio superior a $1,000:")
    for p in app2.productos_precio_mayor_a(1000.0):
        print(f" - {p.nombre}: ${p.precio}")

    print("\n3. Productos con existencias menores a 10 unidades:")
    for p in app2.productos_stock_menor_a(10):
        print(f" - {p.nombre}: {p.existencias} unidades disponibles")

    print("\n4. Productos del proveedor 'PROV-01':")
    for p in app2.productos_por_proveedor("PROV-01"):
        print(f" - {p.nombre}")

    print("\n5. Total acumulado de ventas registradas:")
    print(f" Total procesado: ${app2.total_ventas_acumulado():,.2f}")

    # 7. Eliminación de Objetos
    print("\n--- Eliminación de Objetos ---")
    if app2.eliminar_producto("PROD-103"):
        print("Producto 'PROD-103' eliminado correctamente.")

    print(f"Productos restantes tras eliminación: {len(app2.consultar_productos())}")

    app2.cerrar()
    print("\n=== PRUEBA FINALIZADA EXITOSAMENTE ===")


if __name__ == "__main__":
    ejecutar_demostracion()