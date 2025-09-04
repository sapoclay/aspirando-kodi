# Aspirando Kodi 

<img width="1024" height="1024" alt="icono" src="https://github.com/user-attachments/assets/3321db4d-e6e0-4619-9027-7db537574499" />

Herramienta de limpieza y optimización para Kodi: caché, thumbnails, paquetes, temporales, buffering y más. Incluye pruebas de velocidad, backups de configuración y un servicio opcional para limpieza automática al iniciar Kodi.

## Requisitos
- Kodi 19 o superior (Python 3). El addon requiere `xbmc.python` 3.0.0.
- Sistema con permisos para leer/escribir en `~/.kodi/userdata/`.
- Nota de plataforma: en Linux (incluye LibreELEC/CoreELEC) todas las funciones están disponibles. En Android algunas funciones (como redirigir `special://temp` mediante symlink) no están soportadas por el sistema; ver sección "Compatibilidad".

## Instalación
- Desde Kodi: Add-ons > Instalar desde un archivo .zip > seleccionar el zip del addon (p. ej., `script.aspirando-kodi-1.0.35.zip`).
- Si el instalador falla, instalación manual:En el addon
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
  - Programar limpieza al iniciar (modos: una vez, persistente o desactivar; con aviso previo).
  - Gestión de Buffering (submenú agrupado por funcionalidades).
  - Ajustes rápidos: acceso directo a “PVR IPTV Simple Client” (pantalla de Timeshift).
  - Reiniciar Kodi y Acerca de.

## Cómo usar
- Limpieza básica:
  1) Abre el addon y elige qué limpiar (Caché, Thumbnails, Paquetes, Temporales) o usa “Limpieza Completa”.
  2) Revisa el resumen y confirma.
- Limpieza al iniciar:
  1) En el menú principal > “Programar limpieza al iniciar”.
  2) Elige “una vez” o “persistente”. Para detenerla, vuelve y selecciona “desactivar”.
- Buffering (recomendado):
  1) Entra en “Gestión de Buffering”.
  2) Empieza por “Configurar buffering básico” o usa “Test de velocidad y recomendación”.
  3) Opcional: “Configurar USB como cache (directo)” crea KodiCache en el USB y ajusta cachepath y buffermode.
  4) Tras aplicar cambios, reinicia Kodi.
- Optimizaciones de Video:
  1) Desde "Gestión de Buffering" > "Optimizaciones de Video".
  2) Configura aceleración por hardware, calidad de reproducción, audio, escalado y opciones avanzadas según tu dispositivo.
  3) Usa "Restablecer configuración de video" si experimentas problemas.
- IPTV y Timeshift (IPTV Simple):
  1) En “Gestión de Buffering” > “PVR / Timeshift” > “Abrir ajustes de Timeshift…”.
  2) Si PVR IPTV Simple no está instalado/habilitado, el addon intentará instalarlo/habilitarlo y abrir su configuración.
  3) En “PVR IPTV Simple”: activa el addon y configura tu lista M3U/EPG.
  4) Para Timeshift: Ajustes de Kodi > TV en directo > Timeshift y ajusta según tu dispositivo.

Notas Android
- El atajo a IPTV Simple intenta instalar/habilitar el addon y abrir su configuración con reintentos; si no aparece a la primera, espera ~1 s y vuelve a pulsar.
- Watchdog PVR: tras habilitar Timeshift y reiniciar, si la TV en directo se queda cargando sin mostrar canales, el servicio del addon detecta el bloqueo y ofrece acciones de recuperación (deshabilitar IPTV Simple o aplicar un buffering seguro en RAM y reiniciar Kodi).
- Auto-limpieza silenciosa: cuando detienes la reproducción y tienes activada la auto-limpieza de cache USB, si no hay un cachepath válido no se mostrarán avisos intrusivos (se omite la limpieza de forma silenciosa).
- La redirección de special://temp por symlink no está disponible; usa cachepath en USB o buffer en RAM.

## Gestión de Buffering (submenú)
- Ver configuración actual: muestra `advancedsettings.xml` (si existe) o los valores por defecto.
- Ver valores de advancedsettings.xml: lectura amigable de parámetros clave.
  - Muestra `Cache path` si está activo y el espacio libre del USB (libre/total).
- Configurar buffering básico: valores recomendados estándar (50 MB, factor 4.0).
- Configurar buffering avanzado: eliges tamaño de buffer y factor de lectura.
- Guardar configuración en USB: copia el `advancedsettings.xml` al USB (carpeta `KodiConfig/`).
  - Opción para configurar el USB como cache externo (cachepath) y `buffermode=2`.
- Configurar USB como cache (directo): selecciona un USB y crea `KodiCache` como destino de cache.
  - Aplica `buffermode=2`, `cachemembuffersize=0` y establece `cachepath` al USB.
- Crear/Restaurar copia de seguridad: backups automáticos en el directorio de datos del addon.
- Eliminar configuración de buffering: borra `advancedsettings.xml` (Kodi vuelve a valores por defecto).
- Diagnóstico USB: muestra dispositivos montados y estado de escritura.
- Test de velocidad y recomendación: descarga breve y propone buffer/factor según Mbps.
- Test de velocidad (elegir servidor): permite seleccionar el servidor del test (ThinkBroadband / DigitalOcean / Hetzner / OVH).
- Modo streaming (ajuste por bitrate): elige el bitrate objetivo (SD/HD/FullHD/4K) y aplica valores; si ya existe `cachepath`, se preserva y se prioriza disco (buffer en RAM a 0).
- Optimización automática: ajusta según RAM disponible y heurísticas del sistema.

Tras aplicar cambios de buffering, reiniciar Kodi para asegurar que se apliquen.

## Optimizaciones de Video (submenú)
- Configurar aceleración por hardware: selecciona el método más adecuado para tu dispositivo:
  - AUTO: detección automática del mejor método disponible.
  - VAAPI: recomendado para Intel y AMD en Linux.
  - VDPAU: recomendado para NVIDIA en Linux.
  - DXVA2: recomendado para Windows.
  - MediaCodec: recomendado para Android.
- Optimizar reproducción de video: configura perfiles de calidad según el tipo de contenido:
  - Máxima calidad: prioriza calidad sobre rendimiento.
  - Balanceado: equilibrio entre calidad y rendimiento.
  - Máximo rendimiento: prioriza fluidez sobre calidad.
  - Personalizado: configuración manual detallada.
- Configurar tasa de refresco: ajusta automáticamente la frecuencia del display:
  - Siempre activado: cambia automáticamente para cualquier contenido.
  - Solo videos 23.976/24fps: activado únicamente para contenido cinematográfico.
  - Desactivado: mantiene la frecuencia actual del sistema.
- Configurar audio: optimiza la configuración de audio según tu setup:
  - Normalización de volumen: nivela diferencias de volumen entre contenidos.
  - Passthrough AC3/DTS: transmisión directa para sistemas de sonido envolvente.
  - Upsampling de audio: mejora la calidad de audio de baja resolución.
  - Corrección de sincronización: ajusta el delay audio/video.
- Configurar escalado de video: selecciona el método de escalado óptimo:
  - Bilinear: rápido, calidad básica.
  - Bicubic: equilibrio calidad/rendimiento.
  - Lanczos: máxima calidad, más demandante.
  - SPLINE36: alta calidad con buen rendimiento.
- Optimizaciones de streaming: configura buffers específicos por tipo de bitrate:
  - Streaming bajo (SD): optimizado para conexiones lentas.
  - Streaming medio (HD): equilibrio para HD estándar.
  - Streaming alto (Full HD): optimizado para alta definición.
  - Streaming 4K: configuración para contenido Ultra HD.
- Configurar decodificación avanzada: opciones técnicas para usuarios avanzados:
  - Métodos de desentrelazado para contenido entrelazado.
  - Postprocesado para mejorar calidad visual.
  - Multithreading para aprovechar múltiples núcleos de CPU.
  - Skip loop filter para mejorar rendimiento en H.264.
- Configuración específica para IPTV: optimizaciones especializadas para streaming IPTV:
  - Buffering específico con perfiles según tipo de dispositivo.
  - Timeouts de red optimizados para estabilidad IPTV.
  - Prioridades de codec para mejor compatibilidad.
  - Seeking optimizado para Live TV, VOD y Catchup.
  - Optimización de caché EPG según tamaño de lista.
  - Corrección de sincronización A/V progresiva (nuevo).
  - Configuración completa IPTV con un solo clic.
- Restablecer configuración de video: elimina todas las configuraciones de video personalizadas.

Tras aplicar optimizaciones de video, se recomienda reiniciar Kodi para asegurar que todos los cambios se apliquen correctamente.

## Configuraciones específicas para IPTV
La sección "Configuración específica para IPTV" dentro de "Optimizaciones de Video" ofrece ajustes especializados para streaming IPTV:

### Buffering específico IPTV
- **Buffer pequeño** (20MB): ideal para dispositivos con memoria limitada o conexiones muy estables.
- **Buffer medio** (50MB): configuración recomendada para la mayoría de dispositivos.
- **Buffer grande** (100MB): para conexiones inestables o contenido de alta calidad.
- **Buffer personalizado**: permite ajustar manualmente el tamaño y factor de lectura.

### Timeouts de red para IPTV
- **Conexión rápida**: timeouts cortos para conexiones estables de alta velocidad.
- **Conexión estándar**: configuración equilibrada recomendada para la mayoría de usuarios.
- **Conexión lenta/inestable**: timeouts largos con más reintentos para conexiones problemáticas.
- **Configuración personalizada**: ajuste manual de timeouts y reintentos.

### Prioridades de codec
- **Hardware First**: prioriza aceleración por hardware (más eficiente energéticamente).
- **Software First**: prioriza decodificación por software (más compatible con formatos variados).
- **Balanced**: equilibrio entre hardware y software (recomendado).

### Configuración de seeking
- **Live TV (timeshift)**: optimizado para canales en vivo con timeshift limitado.
- **VOD**: configuración completa para contenido bajo demanda con seeking completo.
- **Catchup**: configuración mixta para contenido programado.
- **Desactivar seeking**: solo reproducción secuencial sin saltos.

### Optimización de caché EPG
- **Lista pequeña** (< 500 canales): configuración ligera para listas pequeñas.
- **Lista mediana** (500-2000 canales): configuración equilibrada.
- **Lista grande** (> 2000 canales): configuración optimizada para listas extensas.
- **Sin EPG**: desactiva completamente el EPG para mejor rendimiento.

### Configuración completa IPTV
Aplica automáticamente un conjunto completo de optimizaciones:
- Buffer de 50MB con factor 3.0
- Timeouts de red estándar
- Prioridades de codec balanceadas
- Seeking optimizado para Live TV
- EPG configurado para listas medianas
- Refresh rate automático activado

**Importante**: Tras aplicar configuraciones IPTV, reiniciar Kodi es esencial para que todos los cambios surtan efecto.

## Corrección de Sincronización A/V Progresiva
**NUEVA FUNCIONALIDAD v1.0.35**: Solución específica para el problema común de audio que se adelanta progresivamente al video durante la reproducción de contenido IPTV.

### ¿Cuándo usar esta función?
- Audio que se desfasa gradualmente del video durante la reproducción
- Audio que se adelanta progresivamente a medida que avanza el contenido
- Problemas de sincronización que empeoran con el tiempo de reproducción
- Drift temporal entre audio y video en streaming IPTV

### Métodos de corrección disponibles

#### **Método 1: Configurar timestamps A/V** (Recomendado primer intento)
- **Display como reloj maestro**: Usa la pantalla como referencia temporal
- **Resample forzado**: Audio a 48kHz para consistencia
- **Sincronización por video**: Evita drift progresivo del audio
- **Buffer conservador**: 40MB para máxima estabilidad
- **Cuándo usar**: Primer método a probar, resuelve la mayoría de casos

#### **Método 2: Buffers A/V separados** 
- **Procesamiento independiente**: Separa buffers de audio y video
- **60MB total**: 30MB para memoria, mejor gestión de recursos
- **Sincronización por audio**: Usa audio como referencia temporal
- **Calidad alta**: Resample de alta calidad para audio
- **Cuándo usar**: Si el Método 1 no funciona o hardware tiene problemas de timing

#### **Método 3: Corrección de drift de reloj**
Tres niveles progresivos de corrección:
- **Conservador**: Ajustes mínimos (2% máximo) - probar primero
- **Moderado**: Equilibrado (5% máximo) - si conservador no funciona
- **Agresivo**: Máxima corrección (10% máximo) - último recurso
- **Cuándo usar**: Para problemas de reloj del sistema o hardware específico

#### **Método 4: Configuración conservadora completa**
- **Último recurso**: Sacrifica calidad por estabilidad máxima
- **Sin aceleración HW**: Elimina variables de hardware
- **Audio básico**: 44.1kHz estéreo sin optimizaciones
- **Buffer mínimo**: 20MB, máxima compatibilidad
- **Cuándo usar**: Cuando todos los otros métodos fallan

### Función de diagnóstico
- **Análisis automático**: Detecta configuración actual del sistema
- **Información detallada**: Sample rates, métodos de render, configuración de buffers
- **Recomendaciones**: Guía específica según el problema detectado

### Cómo usar la corrección A/V
1. **Acceder**: Gestión de Buffering > Optimizaciones de Video > Configuración específica para IPTV > "Corregir sincronización A/V progresiva"
2. **Diagnóstico**: Usar "Diagnosticar problema actual" para analizar la situación
3. **Probar métodos en orden**: Empezar con Método 1, continuar secuencialmente si persiste
4. **Reiniciar Kodi**: Esencial tras aplicar cualquier método
5. **Verificar**: Probar contenido IPTV para confirmar corrección

### Notas importantes
- **Reiniciar siempre**: Kodi debe reiniciarse tras aplicar cualquier corrección
- **Probar secuencialmente**: No saltar métodos, cada uno resuelve problemas específicos
- **Backup recomendado**: Crear copia de seguridad antes de aplicar métodos agresivos
- **Reversible**: Usar "Restablecer configuración de video" para volver al estado original

## Special://temp y caché temporal
- Visor de `special://temp` y `special://cache`: lista contenidos y permite pruebas de escritura/limpieza.
- Redirección de `special://temp` a USB mediante enlace simbólico (solo Linux):
  - Crea un symlink desde la carpeta temporal de Kodi hacia un directorio del USB para que los temporales de streaming/pistas se escriban en el USB.
  - Incluye opciones de estado y "Revertir redirección" para volver al estado original.
- En Android no es posible crear esta redirección por restricciones del sistema (SELinux/almacenamiento con ámbito). Ver alternativas en la sección de Compatibilidad.

## Rutas importantes
- Configuración global de buffering: `~/.kodi/userdata/advancedsettings.xml`
- Copias de seguridad: `~/.kodi/userdata/addon_data/script.aspirando-kodi/backups/`
- Directorio de paquetes de addons (para limpieza): `~/.kodi/addons/packages/`
- Bases de datos: `special://database/` (Kodi las gestiona; la compactación se hace desde el addon).

## Limpieza programada al iniciar
- La opción “Programar limpieza al iniciar Kodi” permite elegir:
  - Ejecutar una vez en el próximo arranque.
  - Ejecutar en cada arranque (modo persistente).
  - Desactivar la programación.
- En modo persistente, la limpieza se ejecuta en todos los inicios hasta que la desactives manualmente.

## Consejos y solución de problemas
- Error al instalar zip “first item is folder: false”: reempaquetar asegurando que el zip contenga la carpeta `script.aspirando-kodi/` como raíz.
- Instalación manual: copiar la carpeta `script.aspirando-kodi/` a `~/.kodi/addons/` y reiniciar.
- USB no aparece o no guarda: verificar que el dispositivo esté montado en `/media`, `/mnt` o `/run/media` y que tenga permisos de escritura. Formatos soportados típicos: vfat, ntfs, exfat, ext*.
- Cambios de buffering no surten efecto: reiniciar Kodi después de aplicar ajustes; comprobar que `advancedsettings.xml` existe y no tiene errores.
- Problemas de reproducción tras optimizaciones de video: usar "Restablecer configuración de video" y reiniciar Kodi; verificar que el método de aceleración por hardware sea compatible con tu dispositivo.
- Aceleración por hardware no funciona: probar diferentes métodos (VAAPI, VDPAU, DXVA2, MediaCodec) según tu sistema operativo y hardware; en caso de problemas, volver a AUTO o desactivar.
- Audio desincronizado: ajustar la corrección de sincronización en "Configurar audio" o verificar la configuración de passthrough si usas sistema de sonido envolvente.
- Problemas con streaming IPTV: usar "Configuración específica para IPTV" para optimizar buffering, timeouts y seeking según tu tipo de conexión y contenido.
- IPTV con cortes frecuentes: probar buffer más grande y timeouts más largos en la configuración específica IPTV; verificar estabilidad de la conexión de red.
- EPG IPTV carga lentamente: ajustar configuración de caché EPG según el tamaño de tu lista de canales; para listas muy grandes, considerar reducir días de EPG.
- Seeking no funciona en IPTV: verificar que el proveedor IPTV soporte seeking; usar configuración específica según tipo de contenido (Live TV vs VOD).
- Audio se adelanta progresivamente al video: usar "Corregir sincronización A/V progresiva" en configuraciones IPTV; probar los 4 métodos secuencialmente hasta encontrar solución.
- Drift temporal en streaming IPTV: aplicar corrección de timestamps A/V (Método 1) o buffers separados (Método 2) según la severidad del problema.
- El USB debe permanecer montado en la misma ruta. Si cambia la ruta de montaje, reconfigura el cachepath.
- Android: si no abre la configuración de IPTV Simple, verifica que el addon esté instalado y habilitado. El atajo del addon intentará hacerlo por ti y mostrará el buscador si falta.
- Android (post-Timeshift): si tras habilitar Timeshift y reiniciar Kodi no aparece la lista de canales, espera ~35 s; el servicio mostrará un diálogo con opciones para recuperar (deshabilitar IPTV Simple o aplicar buffering en RAM y reiniciar). Si no ves el diálogo, abre el addon y usa “Abrir ajustes de Timeshift…”.
- Android (auto-limpieza): si deshabilitas Timeshift o eliminas cachepath y estás reproduciendo, no debería saltar el aviso “No hay cachepath válido configurado”; la auto-limpieza se comporta en modo silencioso.

## Compatibilidad
- Linux (PC, LibreELEC/CoreELEC): soporte completo, incluida la redirección de `special://temp` a USB mediante symlink y todas las optimizaciones de video (VAAPI/VDPAU recomendados).
- Android (TV/Box/Tablet):
  - Funciones soportadas: limpieza (caché, thumbnails, paquetes, temporales), compactación de BBDD, tests de velocidad, configuración de buffering en `advancedsettings.xml`, optimizaciones de video (MediaCodec recomendado), diagnósticos básicos y atajo a IPTV Simple.
  - Funciones limitadas/no soportadas: redirección de `special://temp` por symlink (no permitida), acceso directo a ciertas rutas de USB sin SAF, y algunas detecciones automáticas de montajes.
  - Recomendaciones: usar el selector de carpeta del addon para elegir rutas dentro del espacio accesible de Kodi; mantener `cachemembuffersize` > 0 si no se dispone de ruta externa fiable; considerar tarjetas SD/USB que aparezcan en `/storage` con permisos de escritura para Kodi.
  - Notas de la edición Android: detección de almacenamiento en `/storage/*` y `/mnt/media_rw/*`, pruebas de lectura/escritura con `xbmcvfs`, navegador de carpetas adaptado, y opciones no soportadas (como symlink de `special://temp`) ocultas. Incluye un watchdog del PVR que ayuda a recuperar si la TV en directo queda bloqueada tras habilitar Timeshift.

## Privacidad y seguridad
- El addon no envía datos a terceros. El test de velocidad descarga archivos públicos (sin datos personales) para estimar Mbps.
- Las rutas de usuario se manejan dentro del perfil de Kodi.

## Créditos
- Autor: entreunosyceros
- Repositorio: https://github.com/sapoclay/aspirando-kodi

---
