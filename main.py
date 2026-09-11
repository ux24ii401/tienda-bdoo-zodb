import os
import transaction
from persistent import Persistent
from persistent.list import PersistentList
from ZODB import DB, FileStorage
from datetime import datetime


#CLASES PERSISTENTES (Modelo de Dominio BDOO sin Herencia)


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
        if cantidad > 0:
            self.existencias += cantidad

    def descontarStock(self, cantidad):
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
        self.ventas = PersistentList()  # Lista persistente de ventas


class Proveedor(Persistent):
    def __init__(self, idProveedor, razonSocial, contactoDirecto, telefono, email):
        self.idProveedor = idProveedor
        self.razonSocial = razonSocial
        self.contactoDirecto = contactoDirecto
        self.telefono = telefono
        self.email = email
        self.productos = PersistentList()


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
        self.cliente = cliente
        self.fechaHora = datetime.now()
        self.subtotal = 0.0
        self.impuesto = 0.0
        self.total = 0.0
        self.estado = "Pendiente"
        self.detalles = PersistentList()

    def anadirRenglon(self, producto, cantidad):
        if producto.descontarStock(cantidad):
            id_linea = f"DET-{len(self.detalles) + 1:03d}"
            detalle = DetalleVenta(id_linea, producto, cantidad)
            self.detalles.append(detalle)
            self.calcularMontos()
            return True
        return False

    def calcularMontos(self):
        self.subtotal = sum(d.subtotalCalculado for d in self.detalles)
        self.impuesto = self.subtotal * 0.16
        self.total = self.subtotal + self.impuesto

    def cerrarTransaccion(self):
        if self.detalles:
            self.estado = "Completada"
            # Opcional: abonar puntos al cliente
            if hasattr(self.cliente, 'puntosFidelidad'):
                self.cliente.puntosFidelidad += int(self.total // 10)


#MANEJADOR DE PERSISTENCIA Y CONSULTAS


class TiendaBDOO:
    def __init__(self, db_path="tienda_db.fs"):
        self.db_path = db_path
        self.storage = FileStorage.FileStorage(self.db_path)
        self.db = DB(self.storage)
        self.connection = self.db.open()
        self.dbroot = self.connection.root()

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

    def crear_producto(self, producto):
        self.dbroot['productos'].append(producto)
        if producto.proveedor and producto not in producto.proveedor.productos:
            producto.proveedor.productos.append(producto)
        transaction.commit()

    def consultar_productos(self):
        return list(self.dbroot['productos'])

    def modificar_precio(self, skuCode, nuevo_precio):
        for p in self.dbroot['productos']:
            if p.skuCode == skuCode:
                p.modificarPrecio(nuevo_precio)
                transaction.commit()
                return True
        return False

    def eliminar_producto(self, skuCode):
        for p in self.dbroot['productos']:
            if p.skuCode == skuCode:
                self.dbroot['productos'].remove(p)
                transaction.commit()
                return True
        return False

    def reporte_venta_total_diaria(self):
        return sum(v.total for v in self.dbroot['ventas'] if v.estado == "Completada")



#EJECUCIÓN Y DEMOSTRACIÓN DE PRUEBAS

if __name__ == "__main__":
    db_file = "tienda_db.fs"

    print("--- PASO 1: Creación de Objetos y Venta ---")
    app1 = TiendaBDOO(db_file)

    prov = Proveedor("PROV-01", "Distribuidora Tech SA", "Carlos Mendoza", "555-1234", "tech@dist.com")
    p1 = Producto("PROD-101", "Laptop Pro", "16GB RAM, 512GB SSD", 15000.0, 10, "Electrónica", prov)
    p2 = Producto("PROD-102", "Mouse Inalámbrico", "Óptico 1600 DPI", 350.0, 25, "Accesorios", prov)
    cli = Cliente("CLI-01", "Ana Gómez", "555-9876", "ana@email.com")

    app1.crear_producto(p1)
    app1.crear_producto(p2)
    app1.dbroot['clientes'].append(cli)

    # Registrar Venta y Actualizar Inventario
    v1 = Venta("VEN-2026-001", cli)
    v1.anadirRenglon(p1, 1)  # Stock baja a 9
    v1.anadirRenglon(p2, 2)  # Stock baja a 23
    v1.cerrarTransaccion()
    app1.dbroot['ventas'].append(v1)

    transaction.commit()
    app1.cerrar()
    print("-> Datos comiteados. Aplicación cerrada completamente.\n")

    print("--- PASO 2: Reapertura y Comprobación de Persistencia ---")
    app2 = TiendaBDOO(db_file)

    print(f"Productos recuperados: {len(app2.consultar_productos())}")
    print(f"Stock actual Laptop Pro: {app2.consultar_productos()[0].existencias} (Debe ser 9)")
    
    # Modificar producto
    app2.modificar_precio("PROD-102", 399.99)
    
    # Reporte de venta total diaria
    print(f"Total Venta Diaria: ${app2.reporte_venta_total_diaria():,.2f}")

    app2.cerrar()
    print("\n=== PRUEBAS CONCLUIDAS EXITOSAMENTE ===")