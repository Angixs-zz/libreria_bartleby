# Manual de Usuario - Libreria Bartleby

Version inicial: 29/05/2026

## 1. Objetivo del sistema

Libreria Bartleby es un sistema web para administrar la operacion de una libreria: catalogo publico, apartados de libros, punto de venta, inventario, proveedores, adquisiciones, clientes, reportes, alertas y control de personal.

El sistema esta dividido por roles. Cada usuario ve opciones distintas segun sus permisos.

## 2. Roles de usuario

### Cliente

Puede consultar el catalogo, registrarse, iniciar sesion, agregar libros a la bolsa, confirmar reservas, consultar sus apartados y cancelar reservas pendientes.

### Cajero o staff

Puede operar el punto de venta, gestionar reservas, consultar clientes y atender operaciones diarias. El acceso aparece en la barra superior como accesos a POS, Reservas y Catalogo.

### Director o administrador

Tiene acceso completo a las areas administrativas: inventario, agregar libros, proveedores, adquisiciones, reportes, alertas, clientes, personal y auditoria.

## 3. Acceso al sistema

### Iniciar sesion con contrasena

1. Entrar a la opcion **Ingresar**.
2. Escribir usuario y contrasena.
3. Confirmar el inicio de sesion.

Si las credenciales son correctas, el sistema redirige al usuario a las funciones disponibles para su rol.

### Iniciar sesion con codigo

1. Entrar a **Ingresar**.
2. Elegir la opcion de acceso con codigo, si esta disponible.
3. Escribir el correo o usuario solicitado.
4. Revisar el codigo enviado por correo.
5. Capturar el codigo en la pantalla de verificacion.

### Recuperar contrasena

1. Entrar a **Recuperar contrasena** desde la pantalla de inicio de sesion.
2. Escribir el correo registrado.
3. Revisar el codigo enviado por correo.
4. Ingresar el codigo y capturar la nueva contrasena.

## 4. Navegacion general

La barra superior contiene accesos principales:

- **Conocenos**: informacion general de la libreria.
- **Catalogo**: listado publico de libros disponibles.
- **Bolsa**: libros seleccionados para apartado.
- **Mis reservas**: reservas activas e historial del cliente.
- **Perfil**: datos personales, actividad y accesos rapidos.
- **Gestion**: menu administrativo visible para directores.
- **POS** y **Reservas**: accesos operativos visibles para staff.

El sistema tambien permite cambiar entre modo claro y oscuro desde el boton de tema.

## 5. Catalogo publico

### Buscar libros

1. Entrar a **Catalogo**.
2. Usar el campo de busqueda para escribir titulo, autor o ISBN.
3. Opcionalmente aplicar filtros por genero o rango de precio.
4. Presionar el boton de busqueda.

El sistema muestra los ejemplares que coinciden con los filtros seleccionados.

### Ver detalle de un libro

1. Desde el catalogo, seleccionar una tarjeta de libro.
2. Revisar titulo, autor, categoria, precio, estado fisico, descripcion y disponibilidad.
3. Si el libro esta disponible, usar la opcion para agregarlo a la bolsa.

### Agregar libros a la bolsa

1. Abrir el detalle del libro o usar el boton disponible desde el catalogo.
2. Presionar **Agregar** o la accion equivalente.
3. El contador de la bolsa se actualiza en la barra superior.

La bolsa representa una seleccion temporal antes de confirmar el apartado.

## 6. Reservas para clientes

### Confirmar una reserva

1. Entrar a **Bolsa**.
2. Revisar los libros seleccionados y el total.
3. Quitar libros si ya no se desean apartar.
4. Presionar **Confirmar reserva**.

El sistema genera un ticket con codigo tipo `BART-XXXX`. La reserva queda pendiente de recoleccion.

### Vigencia de reservas

Las reservas tienen una vigencia de 72 horas desde su creacion. Si no se completan dentro de ese periodo, pueden cancelarse o liberarse para devolver el stock al catalogo.

### Consultar mis reservas

1. Iniciar sesion como cliente.
2. Entrar a **Mis reservas**.
3. Revisar reservas pendientes, completadas o canceladas.
4. Abrir el ticket para ver el detalle.

### Cancelar una reserva

1. Entrar a **Mis reservas**.
2. Ubicar la reserva pendiente.
3. Usar la opcion **Cancelar**.
4. Confirmar la accion.

Al cancelar, los ejemplares dejan de estar apartados.

## 7. Punto de venta

Disponible para cajeros, staff y administradores.

### Registrar una venta

1. Entrar a **POS**.
2. Buscar o escanear el codigo/SKU del ejemplar.
3. Agregar los libros a la venta.
4. Revisar cantidades, precios y total.
5. Seleccionar metodo de pago: efectivo, tarjeta o transferencia.
6. Cobrar la venta.

Al confirmar el cobro, el sistema registra la venta y descuenta el stock de los ejemplares vendidos.

### Recomendaciones operativas

- Verificar que el SKU corresponda al ejemplar fisico entregado.
- Revisar el total antes de cobrar.
- Asociar la venta a un cliente cuando sea posible para conservar historial.

## 8. Gestion de reservas para staff

Disponible desde **Reservas** o **Gestor de reservas**.

### Consultar reservas activas

1. Entrar a **Reservas**.
2. Revisar la lista de apartados pendientes.
3. Usar los indicadores de urgencia:
   - Verde: quedan mas de 24 horas.
   - Amarillo: quedan entre 6 y 24 horas.
   - Rojo: quedan 6 horas o menos, o la reserva esta vencida.

### Entregar una reserva

1. Buscar la reserva por cliente, codigo o listado.
2. Abrir o revisar el ticket.
3. Confirmar que el cliente recoja y pague los libros.
4. Marcar la reserva como entregada.

La reserva pasa a estado completado.

### Liberar una reserva

1. Ubicar una reserva pendiente o vencida.
2. Usar la accion **Liberar**.
3. Confirmar la liberacion.

El sistema libera los ejemplares para que vuelvan a estar disponibles.

## 9. Inventario

Disponible para directores o administradores.

### Consultar inventario

1. Entrar a **Gestion > Inventario**.
2. Revisar el listado de ejemplares.
3. Buscar por titulo, autor, ISBN o SKU.
4. Abrir el detalle de un ejemplar para editar informacion especifica.

### Agregar libro o ejemplar

1. Entrar a **Gestion > Agregar Libro**.
2. Capturar datos bibliograficos: titulo, autor, ISBN, editorial, ano de publicacion, categoria y descripcion.
3. Capturar datos del ejemplar: estado fisico, descripcion del estado, precio de compra, precio de venta y stock.
4. Guardar el registro.

El sistema genera o conserva el SKU del ejemplar y aplica el precio de venta con ajuste psicologico si corresponde.

### Editar ejemplar

1. Entrar al detalle del ejemplar desde inventario.
2. Modificar datos de libro o ejemplar.
3. Guardar cambios.

### Eliminar ejemplar

1. Entrar a **Gestion > Inventario**.
2. Ubicar el ejemplar.
3. Usar la accion de eliminar.
4. Confirmar la eliminacion.

Esta accion debe usarse solo cuando el ejemplar no debe formar parte del inventario operativo.

### Importar y exportar inventario

Desde la pantalla de inventario se puede exportar la informacion disponible y, si el usuario tiene permisos, importar registros mediante archivo.

## 10. Proveedores y adquisiciones

Disponible para administradores.

### Registrar proveedor

1. Entrar a **Gestion > Proveedores**.
2. Presionar **Nuevo proveedor**.
3. Capturar nombre, contacto, telefono, correo, direccion y estado activo.
4. Guardar.

### Editar proveedor

1. Entrar a **Proveedores**.
2. Ubicar el proveedor.
3. Usar la opcion de edicion.
4. Actualizar los datos necesarios.
5. Guardar cambios.

### Registrar adquisicion identificada

1. Entrar a **Gestion > Adquisiciones**.
2. Presionar **Registrar adquisicion**.
3. Seleccionar proveedor.
4. Elegir el tipo de adquisicion identificada.
5. Agregar libros sueltos con cantidad y costo unitario.
6. Guardar.

El sistema actualiza el stock y el costo de compra de los ejemplares relacionados.

### Registrar lote cerrado

1. Entrar a **Registrar adquisicion**.
2. Seleccionar proveedor.
3. Elegir tipo **Lote cerrado**.
4. Capturar cantidad estimada de libros, costo del lote y observaciones.
5. Guardar.

El lote queda como **Por inventariar** hasta que se registren los libros incluidos.

### Inventariar lote

1. Entrar al historial o detalle del proveedor.
2. Abrir el lote con estado **Por inventariar**.
3. Agregar ejemplares existentes o nuevos.
4. Capturar costo unitario y cantidad.
5. Cuando el lote este completo, marcarlo como completado.

## 11. Clientes

Disponible para staff y administradores.

### Consultar clientes

1. Entrar a **Gestion > Clientes** o al panel de clientes.
2. Buscar por usuario, nombre, correo o telefono.
3. Aplicar filtros de actividad cuando esten disponibles.
4. Abrir la ficha del cliente.

### Ficha de cliente

La ficha muestra datos del cliente, reservas activas, historial de compras, actividad y notas internas.

### Agregar nota interna

1. Abrir la ficha del cliente.
2. Escribir la nota en la seccion **Notas**.
3. Guardar.

Las notas son internas y sirven para seguimiento operativo.

### Restablecer contrasena de cliente

1. Abrir la ficha del cliente.
2. Ir a la seccion **Contrasena**.
3. Capturar y confirmar la nueva contrasena.
4. Guardar el cambio.

## 12. Personal y auditoria

Disponible para el director o superusuario.

### Gestionar personal

1. Entrar a **Gestion > Personal**.
2. Revisar cuentas de administracion y staff activo.
3. Crear, editar, desactivar o reactivar cuentas internas segun corresponda.

### Crear cuenta de staff

1. Presionar **Nuevo empleado** o accion equivalente.
2. Capturar nombre, apellido, usuario, correo y contrasena.
3. Seleccionar permisos o rol operativo.
4. Guardar.

### Restablecer contrasena de personal

1. Entrar a **Personal**.
2. Ubicar el usuario.
3. Usar la accion de restablecimiento.
4. Capturar y confirmar la nueva contrasena.

### Revisar auditoria

1. Entrar a **Gestion > Auditoria**.
2. Filtrar por usuario, entidad o descripcion.
3. Revisar eventos recientes.

La auditoria permite dar seguimiento a acciones relevantes realizadas dentro del sistema.

## 13. Reportes y alertas

Disponible para administradores.

### Dashboard de reportes

1. Entrar a **Gestion > Reportes**.
2. Seleccionar el periodo de analisis.
3. Revisar indicadores de ventas, reservas, inventario, clientes y libros destacados.
4. Exportar a PDF si se requiere compartir o archivar el reporte.

### Centro de alertas

1. Entrar a **Gestion > Alertas**.
2. Revisar los bloques operativos:
   - Reservas por vencer.
   - Stock agotado o critico.
   - Ventas sin cliente asignado.
   - Proveedores inactivos.
   - Clientes frecuentes sin actividad reciente.
3. Abrir la ficha, ticket o modulo relacionado para dar seguimiento.

## 14. Perfil de usuario

Cada usuario autenticado puede entrar a **Mi perfil** desde la barra superior.

Segun el rol, la pantalla puede mostrar:

- Datos personales.
- Reservas activas.
- Historial.
- Resumen de jornada.
- Accesos rapidos.
- Metricas rapidas.
- Acceso maestro para administradores.

Tambien se puede editar informacion personal cuando el formulario esta disponible.

## 15. Documentos legales

El sistema incluye acceso publico a:

- Aviso de privacidad.
- Terminos y condiciones.

Estos documentos aparecen en el pie de pagina y en algunas pantallas publicas.

## 16. Buenas practicas de uso

- Cerrar sesion al terminar la jornada.
- No compartir cuentas entre empleados.
- Verificar SKU y estado fisico antes de vender o entregar.
- Mantener actualizado el stock despues de cada adquisicion.
- Liberar reservas vencidas para evitar inventario bloqueado.
- Registrar proveedor y costo de compra para conservar trazabilidad.
- Asociar ventas a clientes siempre que sea posible.
- Revisar alertas y reportes al inicio o cierre de cada dia.

## 17. Secciones pendientes por ampliar

Este primer borrador puede completarse por secciones con capturas, ejemplos y reglas internas de la libreria. Se recomienda ampliar en este orden:

1. Manual del cliente: catalogo, bolsa, reservas y perfil.
2. Manual del cajero: POS, entrega de reservas y clientes.
3. Manual del administrador: inventario, proveedores, adquisiciones y reportes.
4. Manual del director: personal, auditoria, metricas y control operativo.
5. Anexos: preguntas frecuentes, errores comunes, politicas internas y glosario.
