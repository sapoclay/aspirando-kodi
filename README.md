# Aspirando Kodi (script.aspirando-kodi)

Herramienta de limpieza y optimización para Kodi: caché, thumbnails, paquetes, temporales, buffering y más. Incluye pruebas de velocidad, backups de configuración y un servicio opcional para limpieza automática al iniciar Kodi.

## Requisitos
- Kodi 19 o superior (Python 3). El addon requiere `xbmc.python` 3.0.0.
- Sistema con permisos para leer/escribir en `~/.kodi/userdata/`.

## Instalación
- Desde Kodi: Add-ons > Instalar desde un archivo .zip > seleccionar `script.aspirando-kodi.zip`.
- Si el instalador falla, instalación manual:
  1) Descomprimir el zip. Debe existir una carpeta raíz llamada `script.aspirando-kodi/`.
  2) Copiar esa carpeta a `~/.kodi/addons/` (crear si no existe).
  3) Reiniciar Kodi.

Nota sobre el zip: el primer elemento del zip debe ser la carpeta `script.aspirando-kodi/` (de lo contrario, Kodi puede mostrar “first item is folder: false”).

## Uso rápido
- Abrir en Kodi: Add-ons > Programas > Aspirando Kodi.
- Menú principal:
  - Limpiar Caché / Thumbnails / Paquetes / Temporales.
  - Limpieza Completa (todo lo anterior con resumen previo).
  - Compactar Bases de Datos (Textures, Addons, MyVideos).
  - Programar limpieza al iniciar (ejecución automática en el próximo arranque con aviso previo).
  - Gestión de Buffering (submenú).
  - Reiniciar Kodi y Acerca de.

## Gestión de Buffering (submenú)
- Ver configuración actual: muestra `advancedsettings.xml` (si existe) o los valores por defecto.
- Ver valores de advancedsettings.xml: lectura amigable de parámetros clave.
- Configurar buffering básico: valores recomendados estándar (50 MB, factor 4.0).
- Configurar buffering avanzado: eliges tamaño de buffer y factor de lectura.
- Guardar configuración en USB: copia el `advancedsettings.xml` al USB (carpeta `KodiConfig/`).
  - Opción para configurar el USB como cache externo (cachepath) y `buffermode=2`.
- Crear/Restaurar copia de seguridad: backups automáticos en el directorio de datos del addon.
- Eliminar configuración de buffering: borra `advancedsettings.xml` (Kodi vuelve a valores por defecto).
- Diagnóstico USB: muestra dispositivos montados y estado de escritura.
- Test de velocidad y recomendación: descarga breve y propone buffer/factor según Mbps.
- Test de velocidad (elegir servidor): permite seleccionar el servidor del test.
- Modo streaming (ajuste por bitrate): elige el bitrate objetivo (SD/HD/FullHD/4K) y aplica valores; si ya existe `cachepath`, se preserva y se prioriza disco (buffer en RAM a 0).
- Optimización automática: ajusta según RAM disponible y heurísticas del sistema.

Tras aplicar cambios de buffering, reiniciar Kodi para asegurar que se apliquen.

## Rutas importantes
- Configuración global de buffering: `~/.kodi/userdata/advancedsettings.xml`
- Copias de seguridad: `~/.kodi/userdata/addon_data/script.aspirando-kodi/backups/`
- Directorio de paquetes de addons (para limpieza): `~/.kodi/addons/packages/`
- Bases de datos: `special://database/` (Kodi las gestiona; la compactación se hace desde el addon).

## Limpieza programada al iniciar
- Opción “Programar limpieza al iniciar Kodi”: guarda una marca interna y, en el siguiente arranque, el servicio del addon muestra un resumen y ejecuta la limpieza completa.
- Tras ejecutarse, la programación se borra automáticamente.

## Consejos y solución de problemas
- Error al instalar zip “first item is folder: false”: reempaquetar asegurando que el zip contenga la carpeta `script.aspirando-kodi/` como raíz.
- Instalación manual: copiar la carpeta `script.aspirando-kodi/` a `~/.kodi/addons/` y reiniciar.
- USB no aparece o no guarda: verificar que el dispositivo esté montado en `/media`, `/mnt` o `/run/media` y que tenga permisos de escritura. Formatos soportados típicos: vfat, ntfs, exfat, ext*.
- Cambios de buffering no surten efecto: reiniciar Kodi después de aplicar ajustes; comprobar que `advancedsettings.xml` existe y no tiene errores.

## Privacidad y seguridad
- El addon no envía datos a terceros. El test de velocidad descarga archivos públicos (sin datos personales) para estimar Mbps.
- Las rutas de usuario se manejan dentro del perfil de Kodi.

## Registro de cambios (destacado)
- v1.0.6: Test de velocidad con elección de servidor; modo streaming por bitrate (preserva cachepath si existe).
- v1.0.5: Test de velocidad con recomendación automática de buffering.
- v1.0.4: Icono principal corregido.
- v1.0.3: Backups/Restauración; Optimización automática; Compactación de BBDD.

## Créditos
- Autor: entreunosyceros
- Repositorio: https://github.com/sapoclay/aspirando-kodi
