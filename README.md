# Aspirando Kodi



Addon para Kodi orientado a limpieza, mantenimiento y optimización de reproducción. Permite limpiar residuos que afectan al streaming y a listas M3U/IPTV, ajustar buffering, trabajar con almacenamiento USB y automatizar limpiezas al iniciar Kodi.

## Versión actual

- Addon: `script.aspirando-kodi`
- Versión: `1.0.37`
- Requisito mínimo: Kodi 19 o superior
- Runtime: Python 3 (`xbmc.python` 3.0.0)

## Funciones principales

- Limpieza de caché, thumbnails, paquetes y temporales.
- Limpieza específica de residuos de streaming, IPTV, PVR y EPG.
- Limpieza completa con resumen previo.
- Compactación de bases de datos de Kodi.
- Gestión de `advancedsettings.xml`.
- Buffering básico, avanzado y automático.
- Test de velocidad con recomendación.
- Guardado de configuración en USB.
- Configuración de USB como `cachepath` externo.
- Acceso a utilidades de IPTV Simple y Timeshift.
- Limpieza programada al iniciar Kodi.
- Auto-limpieza silenciosa del caché USB al parar la reproducción.

## Instalación

### Desde el Repositorio (Recomendado)

Para mantener el addon actualizado automáticamente, te recomendamos añadir la fuente oficial a tu instalación de Kodi.

### 1. Añadir la fuente a Kodi
1. Abre **Kodi** y haz clic en el icono de **Ajustes** (la rueda dentada).
2. Entra en **Explorador de archivos** (File Manager).
3. Haz clic en **Añadir fuente** (Add source).
4. En el campo `<Ninguno>`, escribe exactamente la siguiente URL:
   `https://sapoclay.github.io/aspirando-kodi/`
5. En el nombre de la fuente, escribe **Aspirando** (o el nombre que prefieras) y pulsa **OK**.

### 2. Instalar el Addon
1. Regresa al menú principal de Kodi y entra en la sección **Add-ons**.
2. Haz clic en el icono de la **caja abierta** (Instalador de paquetes) en la esquina superior izquierda.
3. Selecciona **Instalar desde archivo zip**.
4. *(Si es la primera vez, Kodi te pedirá activar "Orígenes desconocidos" en Ajustes. Hazlo y vuelve a este paso).*
5. Busca y selecciona la fuente **Aspirando** que añadiste anteriormente.
6. Haz clic en el archivo `.zip` disponible (ej: `script.aspirando-kodi-x.x.x.zip`).
7. Espera unos segundos hasta que aparezca la notificación de **"Add-on instalado"**.

### Desde Kodi

1. Abre Kodi.
2. Ve a Add-ons > Instalar desde un archivo .zip.
3. Selecciona el paquete del addon.

Paquete generado en este proyecto:

- `dist/script.aspirando-kodi-1.0.37.zip`

### Instalación manual

1. Descomprime el zip.
2. Comprueba que la carpeta raíz sea `script.aspirando-kodi/`.
3. Copia esa carpeta a `~/.kodi/addons/`.
4. Reinicia Kodi.

Si Kodi muestra `first item is folder: false`, el zip no tiene la estructura correcta.

## Uso rápido

1. Abre el addon desde Add-ons > Programas > Aspirando Kodi.
2. Usa `Limpieza Completa` o ejecuta solo la limpieza que necesites.
3. En `Gestión de Buffering`, aplica un perfil adecuado para tu equipo.
4. Reinicia Kodi después de cambiar buffering o ajustes de vídeo.

## Limpiezas disponibles

- `Limpiar Caché`
- `Limpiar Thumbnails`
- `Limpiar Paquetes`
- `Limpiar Temporales`
- `Limpieza Streaming/IPTV`
- `Limpieza Completa`

La limpieza de streaming/IPTV está pensada para eliminar residuos que suelen afectar a reproducción M3U, PVR, EPG y canales en directo.

## Limpieza programada al iniciar

El addon puede programar una limpieza:

- una sola vez en el próximo arranque
- en todos los arranques
- desactivada

El servicio se ha optimizado para consumir menos recursos y reutiliza el módulo principal al ejecutar la limpieza automática.

## Gestión de Buffering

Desde `Gestión de Buffering` puedes:

- ver la configuración actual
- revisar valores de `advancedsettings.xml`
- aplicar buffering básico
- aplicar buffering avanzado
- lanzar optimización automática
- crear y restaurar backups
- eliminar la configuración de buffering
- ejecutar test de velocidad y recomendación
- abrir accesos a IPTV / Timeshift

## USB y almacenamiento externo

El addon soporta dos usos principales de USB.

### Guardar configuración en USB

- Copia `advancedsettings.xml` al directorio `KodiConfig/` del USB.
- Es útil como respaldo o para reutilizar la configuración en otro equipo.

### Configurar USB como caché directa

- Crea `KodiCache` en el USB.
- Establece `buffermode=2`.
- Establece `cachemembuffersize=0`.
- Configura `cachepath` apuntando al USB.

### Recomendaciones para USB

- El USB debe estar montado y ser escribible por Kodi.
- Rutas típicas detectables: `/media`, `/mnt`, `/run/media`.
- Si cambia la ruta de montaje, hay que reconfigurar `cachepath`.
- Si el almacenamiento es lento o inestable, puede empeorar la reproducción.
- Conviene crear backup antes de usar el modo `Configurar USB como cache (directo)` si ya tienes un `advancedsettings.xml` personalizado.

## IPTV, M3U y Timeshift

El addon incluye funciones pensadas para entornos IPTV:

- acceso rápido a ajustes de IPTV Simple / Timeshift
- limpieza específica de residuos de streaming y PVR
- perfiles de buffering adecuados para reproducción continua
- auto-limpieza silenciosa del caché USB al detener reproducción

## Android

La versión 1.0.37 añade una protección específica para Android:

- detecta buffers excesivos al iniciar Kodi
- si el buffer supera 80 MB, muestra advertencia
- ofrece reducirlo automáticamente a un valor más seguro
- crea backup antes de aplicar cambios

Esto reduce el riesgo de cuelgues típicos en Android tras varios minutos de reproducción.

### Recomendaciones en Android

- Evita buffers en RAM por encima de 80 MB.
- Usa perfiles conservadores en dispositivos con poca memoria.
- Si usas USB como `cachepath`, prueba antes lectura y escritura desde el propio addon.
- La auto-limpieza USB se comporta en modo silencioso cuando no existe un `cachepath` válido durante la reproducción.

## Compatibilidad

### Linux / LibreELEC / CoreELEC

- Mejor soporte para montajes USB y mantenimiento general.

### Android y TV Box

- Compatible con buffering, perfiles seguros, Timeshift y `cachepath` externo.
- Algunas redirecciones de rutas temporales del sistema no son viables por restricciones de la plataforma.

### Windows

- Soporte general para limpieza y buffering.

## Problemas comunes

### El zip no instala

- Revisa que el zip tenga como raíz `script.aspirando-kodi/`.

### El USB no aparece o no guarda

- Comprueba que el dispositivo esté montado.
- Comprueba permisos de escritura.
- Vuelve a conectarlo antes de abrir el selector.

### La reproducción sigue fallando

- Reinicia Kodi tras cualquier cambio.
- Ejecuta `Limpieza Streaming/IPTV`.
- Revisa si el problema viene de IPTV Simple, EPG, lista M3U o almacenamiento USB lento.
- Prueba un perfil de buffering conservador.

### Android se congela tras unos minutos

- Reduce el buffer a un perfil seguro.
- Evita configuraciones agresivas en RAM.
- Revisa si el USB configurado como caché es lento o inestable.

## Estructura relevante del proyecto

- `default.py`: menú principal y orquestación general.
- `buffering.py`: lógica de buffering, USB, backups y `advancedsettings.xml`.
- `service.py`: servicio de inicio, limpieza programada y auto-limpieza al terminar reproducción.
- `addon.xml`: metadatos del addon.
- `dist/script.aspirando-kodi-1.0.37.zip`: paquete instalable.

## Cambios reflejados en esta documentación

- Integración de limpieza específica de streaming/IPTV.
- Optimización del servicio de arranque para reducir consumo.
- Auto-limpieza silenciosa del caché USB durante reproducción.
- Correcciones en los archivos empaquetados dentro de `dist/`.
- Documentación ajustada al comportamiento real del modo USB y de Android.

## Licencia

Consulta el archivo `LICENSE` del proyecto.
