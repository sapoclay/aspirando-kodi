import xbmc
import xbmcgui
import xbmcaddon
import xbmcvfs
import sqlite3
import time
import urllib.request
import urllib.error
import os
import shutil
import json
import subprocess
import re
import datetime
import buffering as buffering_module
import updater
from buffering import (
    get_default_kodi_values,
    configure_basic_buffering,
    configure_advanced_buffering,
    configure_android_safe_profile,
    configure_iptv_low_latency_profile,
    show_current_buffering_config,
    show_buffering_values,
    get_usb_autoclean_enabled,
    toggle_usb_autoclean,
    clean_usb_cachepath,
    optimize_buffering_auto,
    backup_advancedsettings,
    restore_advancedsettings_interactive,
    streaming_mode_adjust,
    view_special_temp_cache,
    redirect_temp_cache_to_usb,
    revert_temp_cache_redirection,
    test_special_temp_cache_write,
    save_buffering_config_to_usb,
    detect_usb_devices,
    _translate as buffering_translate,
    temp_status_short as _temp_status_short,
    special_temp_path as _special_temp_path,
)
import xml.etree.ElementTree as ET

# Configuración del addon
addon = xbmcaddon.Addon()
addon_path = addon.getAddonInfo('path')
addon_name = addon.getAddonInfo('name')
addon_id = addon.getAddonInfo('id')
addon_version = addon.getAddonInfo('version')
try:
    addon_data_dir = xbmcvfs.translatePath('special://profile/addon_data/%s' % addon_id)
except Exception:
    addon_data_dir = os.path.expanduser('~/.kodi/userdata/addon_data/%s' % addon_id)
if not os.path.exists(addon_data_dir):
    try:
        os.makedirs(addon_data_dir)
    except Exception:
        pass

def log(message):
    """Log con identificador del addon"""
    xbmc.log('[%s] %s' % (addon_name, message), xbmc.LOGINFO)

def format_size(bytes_size):
    """Convierte bytes a formato legible (KB, MB, GB)"""
    if bytes_size < 1024:
        return "%d B" % bytes_size
    elif bytes_size < 1024 * 1024:
        return "%.1f KB" % (bytes_size / 1024.0)
    elif bytes_size < 1024 * 1024 * 1024:
        return "%.1f MB" % (bytes_size / (1024.0 * 1024.0))
    else:
        return "%.1f GB" % (bytes_size / (1024.0 * 1024.0 * 1024.0))


def _safe_int(value, default=0):
    """Convierte de forma segura a int desde distintos tipos/strings."""
    try:
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return int(value)
        s = str(value).strip()
        return int(s) if s else default
    except Exception:
        return default


def _safe_float(value, default=0.0):
    """Convierte de forma segura a float desde distintos tipos/strings."""
    try:
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return float(value)
        s = str(value).strip()
        return float(s) if s else default
    except Exception:
        return default


def _safe_int_from_elem(elem, default=0):
    """Extrae y convierte a int desde un elemento ElementTree de forma segura."""
    try:
        if elem is None or getattr(elem, 'text', None) is None:
            return default
        return _safe_int(elem.text, default)
    except Exception:
        return default

def get_folder_size(folder_path):
    """Calcula el tamaño total de una carpeta"""
    total_size = 0
    try:
        if os.path.exists(folder_path):
            for dirpath, dirnames, filenames in os.walk(folder_path):
                for filename in filenames:
                    file_path = os.path.join(dirpath, filename)
                    try:
                        total_size += os.path.getsize(file_path)
                    except (OSError, IOError):
                        continue
    except Exception as e:
        log('Error calculando tamaño de %s: %s' % (folder_path, str(e)))
    return total_size

def count_files_in_folder(folder_path):
    """Cuenta el número de archivos en una carpeta"""
    count = 0
    try:
        if os.path.exists(folder_path):
            for dirpath, dirnames, filenames in os.walk(folder_path):
                count += len(filenames)
    except Exception as e:
        log('Error contando archivos en %s: %s' % (folder_path, str(e)))
    return count

def safe_remove_folder_contents(folder_path):
    """Elimina el contenido de una carpeta de forma segura"""
    removed_count = 0
    removed_size = 0
    try:
        if os.path.exists(folder_path):
            for item in os.listdir(folder_path):
                item_path = os.path.join(folder_path, item)
                try:
                    if os.path.isfile(item_path):
                        size = os.path.getsize(item_path)
                        os.remove(item_path)
                        removed_size += size
                        removed_count += 1
                    elif os.path.isdir(item_path):
                        # Contar archivos dentro del directorio antes de eliminarlo
                        dir_file_count = count_files_in_folder(item_path)
                        size = get_folder_size(item_path)
                        shutil.rmtree(item_path)
                        removed_size += size
                        removed_count += dir_file_count  # Contar archivos reales, no directorios
                except Exception as e:
                    log('Error eliminando %s: %s' % (item_path, str(e)))
                    continue
    except Exception as e:
        log('Error accediendo a carpeta %s: %s' % (folder_path, str(e)))
    
    return removed_count, removed_size

def _translate(path):
    """Traduce rutas special:// de forma segura"""
    try:
        return xbmcvfs.translatePath(path)
    except AttributeError:
        # Versión antigua de Kodi
        try:
            return xbmc.translatePath(path)
        except Exception:
            # Fallback: devolver path sin traducir
            log('No se pudo traducir la ruta: %s' % path)
            return path
    except Exception as e:
        log('Error traduciendo ruta %s: %s' % (path, str(e)))
        return path

def get_kodi_paths():
    """Obtiene las rutas importantes de Kodi"""
    try:
        # Obtener ruta de datos de usuario de Kodi (perfil)
        kodi_data_path = _translate('special://userdata/')
        
        paths = {
            'cache': os.path.join(kodi_data_path, 'cache'),
            'thumbnails': os.path.join(kodi_data_path, 'Thumbnails'),
            # Paquetes están fuera de userdata normalmente
            'packages': os.path.join(_translate('special://home/'), 'addons', 'packages'),
            # Ruta real de temp debe venir de special://temp/
            'temp': _translate('special://temp/'),
            'log': os.path.join(kodi_data_path, 'kodi.log'),
            'advancedsettings': os.path.join(kodi_data_path, 'advancedsettings.xml')
        }
        
        return paths
    except Exception as e:
        log('Error obteniendo rutas de Kodi: %s' % str(e))
        return {}

def get_cache_info():
    """Obtiene información de caché"""
    paths = get_kodi_paths()
    cache_path = paths.get('cache', '')
    
    if not os.path.exists(cache_path):
        return 0, 0
    
    size = get_folder_size(cache_path)
    files = count_files_in_folder(cache_path)
    
    return size, files

def get_thumbnails_info():
    """Obtiene información de thumbnails"""
    paths = get_kodi_paths()
    thumbnails_path = paths.get('thumbnails', '')
    
    if not os.path.exists(thumbnails_path):
        return 0, 0
    
    size = get_folder_size(thumbnails_path)
    files = count_files_in_folder(thumbnails_path)
    
    return size, files

def get_packages_info():
    """Obtiene información de paquetes"""
    paths = get_kodi_paths()
    packages_path = paths.get('packages', '')
    
    if not os.path.exists(packages_path):
        return 0, 0
    
    size = get_folder_size(packages_path)
    files = count_files_in_folder(packages_path)
    
    return size, files

def get_temp_info():
    """Obtiene información de archivos temporales"""
    paths = get_kodi_paths()
    temp_path = paths.get('temp', '')
    
    if not os.path.exists(temp_path):
        return 0, 0
    
    size = get_folder_size(temp_path)
    files = count_files_in_folder(temp_path)
    
    return size, files


STREAMING_DB_PREFIXES = ('epg', 'tv', 'pvr')
STREAMING_CACHE_EXTENSIONS = ('.cache', '.tmp', '.temp', '.bak')


def _path_cleanup_stats(path):
    """Devuelve tamaño y número de archivos asociados a una ruta."""
    try:
        if not path or not os.path.exists(path):
            return 0, 0
        if os.path.isfile(path):
            return os.path.getsize(path), 1
        if os.path.isdir(path):
            return get_folder_size(path), count_files_in_folder(path)
    except Exception as e:
        log('Error obteniendo estadísticas de %s: %s' % (path, str(e)))
    return 0, 0


def _collect_streaming_artifact_targets():
    """Localiza residuos persistentes de IPTV/PVR sin tocar la configuración del usuario."""
    targets = []
    seen = set()
    paths = get_kodi_paths()

    def add_target(path):
        try:
            if not path or not os.path.exists(path):
                return
            normalized = os.path.normcase(os.path.normpath(path))
            if normalized in seen:
                return
            seen.add(normalized)
            targets.append(path)
        except Exception:
            return

    try:
        db_dir = _translate('special://database/')
        if os.path.isdir(db_dir):
            for name in os.listdir(db_dir):
                lower_name = name.lower()
                if name.endswith('.db') and lower_name.startswith(STREAMING_DB_PREFIXES):
                    add_target(os.path.join(db_dir, name))
    except Exception as e:
        log('Error localizando bases de datos IPTV/PVR: %s' % str(e))

    try:
        userdata_dir = os.path.dirname(paths.get('advancedsettings', ''))
        pvr_data_dir = os.path.join(userdata_dir, 'addon_data', 'pvr.iptvsimple')
        if os.path.isdir(pvr_data_dir):
            for item in os.listdir(pvr_data_dir):
                item_path = os.path.join(pvr_data_dir, item)
                lower_name = item.lower()
                if os.path.isdir(item_path) and lower_name in ('cache', 'temp'):
                    add_target(item_path)
                elif os.path.isfile(item_path) and lower_name != 'settings.xml':
                    if lower_name.endswith(STREAMING_CACHE_EXTENSIONS) or re.search(r'(iptv|m3u|xmltv|epg|pvr|playlist|timeshift)', lower_name):
                        add_target(item_path)
    except Exception as e:
        log('Error localizando cachés IPTV/PVR: %s' % str(e))

    return targets


def get_streaming_artifacts_info():
    """Devuelve el tamaño y número de archivos de residuos IPTV/PVR."""
    total_size = 0
    total_files = 0
    for target in _collect_streaming_artifact_targets():
        size, files = _path_cleanup_stats(target)
        total_size += size
        total_files += files
    return total_size, total_files


def _clean_target_paths(targets):
    """Elimina un conjunto de rutas concretas sin tocar directorios ajenos."""
    removed_count = 0
    removed_size = 0
    for target in targets:
        try:
            if not os.path.exists(target):
                continue
            if os.path.isfile(target):
                size = os.path.getsize(target)
                os.remove(target)
                removed_size += size
                removed_count += 1
            elif os.path.isdir(target):
                dir_removed_count, dir_removed_size = safe_remove_folder_contents(target)
                removed_count += dir_removed_count
                removed_size += dir_removed_size
        except Exception as e:
            log('Error eliminando residuo de streaming %s: %s' % (target, str(e)))
    return removed_count, removed_size


def clean_streaming_artifacts(interactive=True, notify=True):
    """Limpia residuos persistentes de IPTV/PVR que suelen interferir con listas M3U y EPG."""
    try:
        log('Iniciando limpieza específica de streaming/IPTV')
        targets = _collect_streaming_artifact_targets()
        total_size, total_files = get_streaming_artifacts_info()

        if total_size == 0 and total_files == 0:
            if notify:
                xbmcgui.Dialog().ok('Información', 'No se encontraron residuos de IPTV/PVR para limpiar.')
            return {'removed_count': 0, 'removed_size': 0}

        if interactive:
            message = ('Residuos de streaming/IPTV detectados:\n\n'
                      'Archivos: %d\n'
                      'Tamaño: %s\n\n'
                      'Se limpiarán bases de datos EPG/TV y cachés temporales de IPTV Simple sin borrar la configuración del usuario.\n\n'
                      '¿Continuar?') % (total_files, format_size(total_size))
            if not xbmcgui.Dialog().yesno('Limpieza Streaming/IPTV', message, yeslabel='Limpiar', nolabel='Cancelar'):
                return {'removed_count': 0, 'removed_size': 0}

        progress = None
        if interactive and notify:
            progress = xbmcgui.DialogProgress()
            progress.create('Limpieza Streaming/IPTV', 'Eliminando residuos persistentes de IPTV/PVR...')
            progress.update(0)

        removed_count, removed_size = _clean_target_paths(targets)

        if progress:
            progress.update(100, 'Limpieza completada')
            xbmc.sleep(500)
            progress.close()

        if notify:
            result_msg = ('Limpieza de streaming/IPTV finalizada:\n\n'
                         'Archivos eliminados: %d\n'
                         'Espacio liberado: %s\n\n'
                         'Kodi regenerará EPG y bases temporales cuando vuelvas a cargar tu lista.') % (
                             removed_count,
                             format_size(removed_size)
                         )
            xbmcgui.Dialog().ok('Limpieza Completada', result_msg)

        log('Limpieza streaming/IPTV: %d archivos, %s liberados' % (removed_count, format_size(removed_size)))
        return {'removed_count': removed_count, 'removed_size': removed_size}
    except Exception as e:
        log('Error en limpieza streaming/IPTV: %s' % str(e))
        if notify:
            xbmcgui.Dialog().ok('Error', 'Error limpiando residuos de streaming/IPTV: %s' % str(e))
        return {'removed_count': 0, 'removed_size': 0}

def get_default_kodi_values():
    """Proxy a buffering.py para mantener una única implementación."""
    return buffering_module.get_default_kodi_values()

def detect_usb_devices():
    """Proxy a buffering.py para mantener una única implementación."""
    return buffering_module.detect_usb_devices()

def _browse_for_usb_folder():
    """Permite al usuario elegir manualmente una carpeta (USB) cuando la detección falla."""
    try:
        dialog = xbmcgui.Dialog()
        # Intentar diálogo de exploración de carpetas
        try:
            # En Kodi, browse para carpetas suele ser type=3
            path = dialog.browse(3, 'Selecciona carpeta en tu USB', 'files', '', False, True, '/media')
        except Exception:
            path = ''
        if path and isinstance(path, str) and os.path.isdir(path):
            return path
        # Fallback: pedir ruta manualmente
        path = dialog.input('Introduce ruta del USB (p. ej. /media/USUARIO/NOMBRE)', type=xbmcgui.INPUT_ALPHANUM)
        if path and os.path.isdir(path):
            return path
    except Exception as e:
        log('Error en _browse_for_usb_folder: %s' % str(e))
    return None

def get_usb_info(path, name):
    """Proxy a buffering.py para mantener una única implementación."""
    return buffering_module.get_usb_info(path, name)

    

def clean_cache():
    """Limpia la caché de Kodi"""
    try:
        log('Iniciando limpieza de caché')
        paths = get_kodi_paths()
        cache_path = paths.get('cache', '')
        
        if not os.path.exists(cache_path):
            xbmcgui.Dialog().ok('Información', 'No se encontró carpeta de caché.')
            return
        
        # Obtener información antes de limpiar
        size, files = get_cache_info()
        
        if size == 0:
            xbmcgui.Dialog().ok('Información', 'La caché ya está vacía.')
            return
        
        # Confirmar limpieza
        message = ('Caché de Kodi:\n\n'
                  'Archivos: %d\n'
                  'Tamaño: %s\n\n'
                  '¿Eliminar caché?') % (files, format_size(size))
        
        if not xbmcgui.Dialog().yesno('Limpiar Caché', message, yeslabel='Eliminar', nolabel='Cancelar'):
            return
        
        # Mostrar progreso
        progress = xbmcgui.DialogProgress()
        progress.create('Limpiando Caché', 'Eliminando archivos de caché...')
        progress.update(0)
        
        # Limpiar caché
        removed_count, removed_size = safe_remove_folder_contents(cache_path)
        
        progress.update(100, 'Limpieza completada')
        xbmc.sleep(1000)
        progress.close()
        
        # Mostrar resultado
        result_msg = ('Caché limpiada exitosamente:\n\n'
                     'Archivos eliminados: %d\n'
                     'Espacio liberado: %s\n\n'
                     'Operación completada.') % (removed_count, format_size(removed_size))
        
        xbmcgui.Dialog().ok('Limpieza Completada', result_msg)
        log('Caché limpiada: %d archivos, %s liberados' % (removed_count, format_size(removed_size)))
        
    except Exception as e:
        log('Error limpiando caché: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error limpiando caché: %s' % str(e))

def clean_textures_database():
    """Limpia la base de datos de texturas (thumbnails)"""
    try:
        db_dir = _translate('special://database/')
        if not os.path.exists(db_dir):
            log('No se encontró directorio de base de datos')
            return False
        
        # Buscar base de datos de Textures
        textures_db = None
        for name in os.listdir(db_dir):
            if name.lower().startswith('textures') and name.endswith('.db'):
                textures_db = os.path.join(db_dir, name)
                break
        
        if not textures_db:
            log('No se encontró base de datos Textures')
            return False
        
        try:
            log('Limpiando base de datos: %s' % textures_db)
            conn = sqlite3.connect(textures_db)
            
            # Eliminar todas las entradas de texture
            conn.execute('DELETE FROM texture')
            conn.commit()
            
            # Compactar la base de datos
            conn.execute('VACUUM')
            conn.close()
            
            log('Base de datos Textures limpiada correctamente')
            return True
        except Exception as e:
            log('Error limpiando base de datos Textures: %s' % str(e))
            return False
            
    except Exception as e:
        log('Error en clean_textures_database: %s' % str(e))
        return False

def clean_thumbnails():
    """Limpia los thumbnails de Kodi y su base de datos"""
    try:
        log('Iniciando limpieza de thumbnails')
        paths = get_kodi_paths()
        thumbnails_path = paths.get('thumbnails', '')
        
        if not os.path.exists(thumbnails_path):
            xbmcgui.Dialog().ok('Información', 'No se encontró carpeta de thumbnails.')
            return
        
        # Obtener información antes de limpiar
        size, files = get_thumbnails_info()
        
        if size == 0:
            xbmcgui.Dialog().ok('Información', 'Los thumbnails ya están vacíos.')
            return
        
        # Confirmar limpieza
        message = ('Thumbnails de Kodi:\n\n'
                  'Archivos: %d\n'
                  'Tamaño: %s\n\n'
                  'NOTA: También se limpiará la base de datos de texturas.\n\n'
                  '¿Eliminar thumbnails?') % (files, format_size(size))
        
        if not xbmcgui.Dialog().yesno('Limpiar Thumbnails', message, yeslabel='Eliminar', nolabel='Cancelar'):
            return
        
        # Mostrar progreso
        progress = xbmcgui.DialogProgress()
        progress.create('Limpiando Thumbnails', 'Eliminando thumbnails...')
        progress.update(0)
        
        # Limpiar archivos de thumbnails
        removed_count, removed_size = safe_remove_folder_contents(thumbnails_path)
        
        progress.update(50, 'Limpiando base de datos de texturas...')
        
        # Limpiar base de datos de Textures
        db_cleaned = clean_textures_database()
        
        progress.update(100, 'Limpieza completada')
        xbmc.sleep(1000)
        progress.close()
        
        # Mostrar resultado
        db_msg = '\nBase de datos: %s' % ('Limpiada' if db_cleaned else 'No se pudo limpiar')
        result_msg = ('Thumbnails limpiados exitosamente:\n\n'
                     'Archivos eliminados: %d\n'
                     'Espacio liberado: %s%s\n\n'
                     'Operación completada.') % (removed_count, format_size(removed_size), db_msg)
        
        xbmcgui.Dialog().ok('Limpieza Completada', result_msg)
        log('Thumbnails limpiados: %d archivos, %s liberados, DB: %s' % (removed_count, format_size(removed_size), 'OK' if db_cleaned else 'FALLO'))
        
    except Exception as e:
        log('Error limpiando thumbnails: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error limpiando thumbnails: %s' % str(e))

def clean_packages():
    """Limpia los paquetes de addons de Kodi"""
    try:
        log('Iniciando limpieza de paquetes')
        paths = get_kodi_paths()
        packages_path = paths.get('packages', '')
        
        if not os.path.exists(packages_path):
            xbmcgui.Dialog().ok('Información', 'No se encontró carpeta de paquetes.')
            return
        
        # Obtener información antes de limpiar
        size, files = get_packages_info()
        
        if size == 0:
            xbmcgui.Dialog().ok('Información', 'No hay paquetes para eliminar.')
            return
        
        # Confirmar limpieza
        message = ('Paquetes de Addons:\n\n'
                  'Archivos: %d\n'
                  'Tamaño: %s\n\n'
                  '¿Eliminar paquetes de instalación?') % (files, format_size(size))
        
        if not xbmcgui.Dialog().yesno('Limpiar Paquetes', message, yeslabel='Eliminar', nolabel='Cancelar'):
            return
        
        # Mostrar progreso
        progress = xbmcgui.DialogProgress()
        progress.create('Limpiando Paquetes', 'Eliminando paquetes de addons...')
        progress.update(0)
        
        # Limpiar paquetes
        removed_count, removed_size = safe_remove_folder_contents(packages_path)
        
        progress.update(100, 'Limpieza completada')
        xbmc.sleep(1000)
        progress.close()
        
        # Mostrar resultado
        result_msg = ('Paquetes limpiados exitosamente:\n\n'
                     'Archivos eliminados: %d\n'
                     'Espacio liberado: %s\n\n'
                     'Operación completada.') % (removed_count, format_size(removed_size))
        
        xbmcgui.Dialog().ok('Limpieza Completada', result_msg)
        log('Paquetes limpiados: %d archivos, %s liberados' % (removed_count, format_size(removed_size)))
        
    except Exception as e:
        log('Error limpiando paquetes: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error limpiando paquetes: %s' % str(e))

def clean_temp():
    """Limpia archivos temporales de Kodi"""
    try:
        log('Iniciando limpieza de archivos temporales')
        paths = get_kodi_paths()
        temp_path = paths.get('temp', '')
        
        if not os.path.exists(temp_path):
            xbmcgui.Dialog().ok('Información', 'No se encontró carpeta temporal.')
            return
        
        # Si temp_path es un symlink, informar al usuario
        is_symlink = os.path.islink(temp_path)
        if is_symlink:
            real_path = os.path.realpath(temp_path)
            log('temp_path es un symlink a: %s' % real_path)
        
        # Obtener información antes de limpiar
        size, files = get_temp_info()
        
        if size == 0:
            xbmcgui.Dialog().ok('Información', 'No hay archivos temporales para eliminar.')
            return
        
        # Confirmar limpieza
        symlink_info = '\n(Redirigido a: %s)' % os.path.realpath(temp_path) if is_symlink else ''
        message = ('Archivos Temporales:%s\n\n'
                  'Archivos: %d\n'
                  'Tamaño: %s\n\n'
                  '¿Eliminar archivos temporales?') % (symlink_info, files, format_size(size))
        
        if not xbmcgui.Dialog().yesno('Limpiar Temporales', message, yeslabel='Eliminar', nolabel='Cancelar'):
            return
        
        # Mostrar progreso
        progress = xbmcgui.DialogProgress()
        progress.create('Limpiando Temporales', 'Eliminando archivos temporales...')
        progress.update(0)
        
        # Limpiar temporales
        removed_count, removed_size = safe_remove_folder_contents(temp_path)
        
        progress.update(100, 'Limpieza completada')
        xbmc.sleep(1000)
        progress.close()
        
        # Mostrar resultado
        result_msg = ('Archivos temporales limpiados:\n\n'
                     'Archivos eliminados: %d\n'
                     'Espacio liberado: %s\n\n'
                     'Operación completada.') % (removed_count, format_size(removed_size))
        
        xbmcgui.Dialog().ok('Limpieza Completada', result_msg)
        log('Temporales limpiados: %d archivos, %s liberados' % (removed_count, format_size(removed_size)))
        
    except Exception as e:
        log('Error limpiando archivos temporales: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error limpiando temporales: %s' % str(e))

def clean_all(interactive=True, notify=True):
    """Limpia todo: caché, thumbnails, paquetes, temporales y residuos IPTV/PVR."""
    try:
        log('Iniciando limpieza completa')

        # Obtener información de todas las categorías
        paths = get_kodi_paths()
        cache_size, cache_files = get_cache_info()
        thumb_size, thumb_files = get_thumbnails_info()
        pack_size, pack_files = get_packages_info()
        temp_size, temp_files = get_temp_info()
        streaming_size, streaming_files = get_streaming_artifacts_info()

        total_size = cache_size + thumb_size + pack_size + temp_size + streaming_size
        total_files = cache_files + thumb_files + pack_files + temp_files + streaming_files

        if total_size == 0:
            if notify:
                xbmcgui.Dialog().ok('Información', 'No hay archivos para limpiar.')
            return {'removed_count': 0, 'removed_size': 0}

        # Mostrar resumen antes de limpiar
        summary = ('Resumen de limpieza completa:\n\n'
                  'Caché: %d archivos (%s)\n'
                  'Thumbnails: %d archivos (%s)\n'
                  'Paquetes: %d archivos (%s)\n'
                  'Temporales: %d archivos (%s)\n'
                  'Streaming/IPTV: %d archivos (%s)\n\n'
                  'TOTAL: %d archivos (%s)\n\n'
                  '¿Proceder con la limpieza completa?') % (
                      cache_files, format_size(cache_size),
                      thumb_files, format_size(thumb_size), 
                      pack_files, format_size(pack_size),
                      temp_files, format_size(temp_size),
                      streaming_files, format_size(streaming_size),
                      total_files, format_size(total_size))

        if interactive:
            if not xbmcgui.Dialog().yesno('Limpieza Completa', summary, yeslabel='Limpiar Todo', nolabel='Cancelar'):
                return {'removed_count': 0, 'removed_size': 0}

        # Mostrar progreso
        progress = None
        if interactive and notify:
            progress = xbmcgui.DialogProgress()
            progress.create('Limpieza Completa', 'Iniciando limpieza completa...')

        total_removed_count = 0
        total_removed_size = 0

        def update_progress(percent, message):
            if progress:
                progress.update(percent, message)
        
        # Limpiar caché
        update_progress(10, 'Limpiando caché...')
        if cache_size > 0:
            removed_count, removed_size = safe_remove_folder_contents(paths.get('cache', ''))
            total_removed_count += removed_count
            total_removed_size += removed_size
        
        # Limpiar thumbnails
        update_progress(35, 'Limpiando thumbnails...')
        if thumb_size > 0:
            removed_count, removed_size = safe_remove_folder_contents(paths.get('thumbnails', ''))
            total_removed_count += removed_count
            total_removed_size += removed_size
            
            # Limpiar base de datos de Textures
            update_progress(45, 'Limpiando base de datos de texturas...')
            clean_textures_database()

        # Limpiar residuos persistentes de IPTV/PVR
        update_progress(60, 'Limpiando residuos de streaming/IPTV...')
        if streaming_size > 0:
            stream_result = clean_streaming_artifacts(interactive=False, notify=False)
            total_removed_count += stream_result.get('removed_count', 0)
            total_removed_size += stream_result.get('removed_size', 0)
        
        # Limpiar paquetes
        update_progress(78, 'Limpiando paquetes...')
        if pack_size > 0:
            removed_count, removed_size = safe_remove_folder_contents(paths.get('packages', ''))
            total_removed_count += removed_count
            total_removed_size += removed_size
        
        # Limpiar temporales
        update_progress(92, 'Limpiando archivos temporales...')
        if temp_size > 0:
            removed_count, removed_size = safe_remove_folder_contents(paths.get('temp', ''))
            total_removed_count += removed_count
            total_removed_size += removed_size

        update_progress(100, 'Limpieza completada')
        if progress:
            xbmc.sleep(500)
            progress.close()

        # Mostrar resultado final
        result_msg = ('Limpieza completa finalizada:\n\n'
                     'Total archivos eliminados: %d\n'
                     'Total espacio liberado: %s\n\n'
                     '¡Kodi está más limpio!') % (total_removed_count, format_size(total_removed_size))

        if notify:
            xbmcgui.Dialog().ok('Limpieza Completada', result_msg)
        log('Limpieza completa: %d archivos, %s liberados' % (total_removed_count, format_size(total_removed_size)))
        return {'removed_count': total_removed_count, 'removed_size': total_removed_size}
    except Exception as e:
        log('Error en limpieza completa: %s' % str(e))
        if notify:
            xbmcgui.Dialog().ok('Error', 'Error en limpieza completa: %s' % str(e))
        return {'removed_count': 0, 'removed_size': 0}

def schedule_clean_on_start():
    """Programa limpieza al inicio: una vez o en cada inicio; también permite desactivar."""
    try:
        log('Preparando programación de limpieza al iniciar')
        # Obtener información actual
        cache_size, cache_files = get_cache_info()
        thumb_size, thumb_files = get_thumbnails_info()
        pack_size, pack_files = get_packages_info()
        temp_size, temp_files = get_temp_info()
        streaming_size, streaming_files = get_streaming_artifacts_info()

        total_size = cache_size + thumb_size + pack_size + temp_size + streaming_size
        total_files = cache_files + thumb_files + pack_files + temp_files + streaming_files

        dialog = xbmcgui.Dialog()
        # Opción para desactivar incluso si no hay nada que limpiar ahora
        if total_size == 0:
            choice = dialog.select('Limpieza al inicio', [
                'Desactivar limpieza al iniciar',
                'Cancelar'
            ])
            if choice == 0:
                try:
                    os.remove(os.path.join(addon_data_dir, 'schedule_clean.json'))
                except Exception:
                    pass
                dialog.ok('Limpieza al inicio', 'Limpieza programada desactivada.')
            return

        # Resumen y opciones de programación
        summary = (
            'Resumen estimado:\n\n'
            '- Caché: %d archivos (%s)\n'
            '- Thumbnails: %d archivos (%s)\n'
            '- Paquetes: %d archivos (%s)\n'
            '- Temporales: %d archivos (%s)\n'
            '- Streaming/IPTV: %d archivos (%s)\n\n'
            'TOTAL: %d archivos (%s)\n\n'
            'Elige el modo:'
        ) % (
            cache_files, format_size(cache_size),
            thumb_files, format_size(thumb_size),
            pack_files, format_size(pack_size),
            temp_files, format_size(temp_size),
            streaming_files, format_size(streaming_size),
            total_files, format_size(total_size)
        )
        choice = dialog.select('Programar limpieza al iniciar', [
            'Ejecutar en el próximo inicio (una vez)',
            'Ejecutar en cada inicio (persistente)',
            'Desactivar limpieza al iniciar',
            'Cancelar'
        ], useDetails=True)
        if choice in (-1, 3):
            log('Usuario canceló programación')
            return
        if choice == 2:
            try:
                os.remove(os.path.join(addon_data_dir, 'schedule_clean.json'))
            except Exception:
                pass
            dialog.ok('Limpieza al inicio', 'Limpieza programada desactivada.')
            return

        # Guardar marca en addon_data_dir
        schedule_path = os.path.join(addon_data_dir, 'schedule_clean.json')
        data = {
            'scheduled': True,
            'repeat': (choice == 1),
            'created': __import__('datetime').datetime.now().isoformat(),
            'planned': {
                'cache': {'files': cache_files, 'size': cache_size},
                'thumbnails': {'files': thumb_files, 'size': thumb_size},
                'packages': {'files': pack_files, 'size': pack_size},
                'temp': {'files': temp_files, 'size': temp_size},
                'streaming': {'files': streaming_files, 'size': streaming_size},
                'total': {'files': total_files, 'size': total_size}
            },
            'summary': summary
        }
        try:
            os.makedirs(addon_data_dir, exist_ok=True)
            with open(schedule_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            log('Limpieza programada (%s). Archivo: %s' % ('persistente' if data['repeat'] else 'una vez', schedule_path))
            dialog.ok('Limpieza programada', 'Se ejecutará %s.' % ('en cada inicio' if data['repeat'] else 'en el próximo inicio'))
        except Exception as e:
            log('No se pudo programar la limpieza: %s' % str(e))
            dialog.ok('Error', 'No se pudo programar la limpieza: %s' % str(e))
    except Exception as e:
        log('Error programando limpieza al iniciar: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error programando limpieza: %s' % str(e))

def manage_buffering():
    """Gestión de buffering con menús agrupados por categorías"""
    try:
        log('Iniciando gestión de buffering (agrupado)')

        while True:
            dialog = xbmcgui.Dialog()
            paths = get_kodi_paths()
            advancedsettings_path = paths.get('advancedsettings', '')

            current_config = "Configurado" if os.path.exists(advancedsettings_path) else "No configurado"
            auto_clean = 'ON' if get_usb_autoclean_enabled() else 'OFF'
            is_android = xbmc.getCondVisibility('system.platform.android')

            # Estado corto de special://temp
            try:
                temp_root = _special_temp_path()
                if os.path.islink(temp_root):
                    temp_hint = 'temp: enlace -> %s' % os.path.realpath(temp_root)
                else:
                    temp_hint = 'temp: local'
            except Exception:
                temp_hint = 'temp: desconocido'

            # Submenús
            def submenu_estado():
                while True:
                    label_temp_status = 'Estado de caché temp: %s' % temp_hint
                    opciones = [
                        'Ver configuración actual',
                        'Ver valores de advancedsettings.xml',
                        label_temp_status,
                        'Ver caché actual (special://temp)',
                        'Probar escritura en special://temp/cache',
                        'Volver'
                    ]
                    i = dialog.select('Estado y visualización', opciones)
                    if i in (-1, len(opciones)-1):
                        break
                    if i == 0:
                        show_current_buffering_config(advancedsettings_path)
                    elif i == 1:
                        show_buffering_values(advancedsettings_path)
                    elif i == 2:
                        try:
                            temp_root2 = _special_temp_path()
                            is_link = os.path.islink(temp_root2)
                            target = os.path.realpath(temp_root2) if is_link else temp_root2
                            msg = ['Estado de special://temp', '']
                            msg.append('Ruta: %s' % temp_root2)
                            msg.append('Tipo: %s' % ('ENLACE (symlink)' if is_link else 'Local'))
                            if is_link:
                                msg.append('Destino: %s' % target)
                                cache_dir = os.path.join(target, 'cache')
                                msg.append('Destino/cache existe: %s' % ('Sí' if os.path.exists(cache_dir) else 'No'))
                            xbmcgui.Dialog().textviewer('Estado de special://temp', '\n'.join(msg))
                        except Exception:
                            xbmcgui.Dialog().ok('Error', 'No se pudo obtener el estado de temp')
                    elif i == 3:
                        view_special_temp_cache()
                    elif i == 4:
                        test_special_temp_cache_write()

            def submenu_config():
                while True:
                    opciones = [
                        'Configurar buffering básico',
                        'Configurar buffering avanzado',
                        'Perfil Android (seguro)',
                        'Perfil IPTV (latencia baja)',
                        'Modo streaming (ajuste por bitrate)',
                        'Optimización automática de buffering',
                        'Volver'
                    ]
                    i = dialog.select('Configuración de buffering', opciones)
                    if i in (-1, len(opciones)-1):
                        break
                    if i == 0:
                        configure_basic_buffering(advancedsettings_path)
                    elif i == 1:
                        configure_advanced_buffering(advancedsettings_path)
                    elif i == 2:
                        configure_android_safe_profile(advancedsettings_path)
                    elif i == 3:
                        configure_iptv_low_latency_profile(advancedsettings_path)
                    elif i == 4:
                        streaming_mode_adjust(advancedsettings_path)
                    elif i == 5:
                        optimize_buffering_auto(advancedsettings_path)

            def submenu_usb():
                while True:
                    opciones = [
                        'Guardar configuración en USB',
                        'Configurar USB como cache (directo)',
                        'Probar cache USB (lectura/escritura)',
                        'Auto-limpiar cache USB al parar reproducción (%s)' % ('ON' if get_usb_autoclean_enabled() else 'OFF'),
                        'Limpiar cache USB ahora',
                        'Volver'
                    ]
                    i = dialog.select('Cache en USB', opciones)
                    if i in (-1, len(opciones)-1):
                        break
                    if i == 0:
                        save_buffering_config_to_usb(advancedsettings_path)
                    elif i == 1:
                        configure_usb_cachepath(advancedsettings_path)
                    elif i == 2:
                        test_usb_cachepath(advancedsettings_path)
                    elif i == 3:
                        toggle_usb_autoclean()
                    elif i == 4:
                        clean_usb_cachepath(advancedsettings_path)

            def submenu_speed_diag():
                while True:
                    opciones = [
                        'Test de velocidad y recomendación',
                        'Test de velocidad (elegir servidor)',
                        'Diagnóstico USB',
                        'Volver'
                    ]
                    i = dialog.select('Velocidad y diagnóstico', opciones)
                    if i in (-1, len(opciones)-1):
                        break
                    if i == 0:
                        speed_test_and_recommend(advancedsettings_path)
                    elif i == 1:
                        urls = choose_speed_server()
                        if urls:
                            speed_test_and_recommend(advancedsettings_path, urls)
                    elif i == 2:
                        show_usb_diagnostic()

            def submenu_temp_redirect():
                while True:
                    opciones = [
                        'Redirigir caché a USB (enlace simbólico)',
                        'Revertir redirección de caché (temp local)',
                        'Volver'
                    ]
                    i = dialog.select('Redirección de special://temp', opciones)
                    if i in (-1, len(opciones)-1):
                        break
                    if i == 0:
                        redirect_temp_cache_to_usb()
                    elif i == 1:
                        revert_temp_cache_redirection()

            def submenu_timeshift():
                while True:
                    opciones = [
                        'Abrir ajustes de Timeshift (PVR & TV en directo)',
                        'Volver'
                    ]
                    i = dialog.select('PVR / Timeshift', opciones)
                    if i in (-1, len(opciones)-1):
                        break
                    if i == 0:
                        open_timeshift_settings()

            def submenu_video_optimizations():
                while True:
                    opciones = [
                        'Configurar aceleración por hardware',
                        'Optimizar reproducción de video',
                        'Configurar refresh rate automático',
                        'Ajustar configuración de audio',
                        'Configurar escalado de video',
                        'Optimizaciones para streaming',
                        'Configuración específica para IPTV',
                        'Configuración avanzada de decodificación',
                        'Resetear todas las configuraciones de video',
                        'Volver'
                    ]
                    i = dialog.select('Optimizaciones de Video', opciones)
                    if i in (-1, len(opciones)-1):
                        break
                    if i == 0:
                        configure_hardware_acceleration()
                    elif i == 1:
                        optimize_video_playback()
                    elif i == 2:
                        configure_refresh_rate()
                    elif i == 3:
                        configure_audio_settings()
                    elif i == 4:
                        configure_video_scaling()
                    elif i == 5:
                        configure_streaming_optimizations()
                    elif i == 6:
                        configure_iptv_optimizations()
                    elif i == 7:
                        configure_advanced_decoding()
                    elif i == 8:
                        reset_video_settings()

            def submenu_backups():
                while True:
                    opciones = [
                        'Crear copia de seguridad',
                        'Restaurar copia de seguridad',
                        'Eliminar configuración de buffering',
                        'Volver'
                    ]
                    i = dialog.select('Copias de seguridad', opciones)
                    if i in (-1, len(opciones)-1):
                        break
                    if i == 0:
                        backup_advancedsettings(advancedsettings_path, manual=True)
                    elif i == 1:
                        restore_advancedsettings_interactive(advancedsettings_path)
                    elif i == 2:
                        remove_buffering_config(advancedsettings_path)

            # Menú principal agrupado
            categorias = []
            handlers = []
            categorias.append('Estado y visualización (%s)' % temp_hint); handlers.append(submenu_estado)
            categorias.append('Configuración de buffering (%s)' % current_config); handlers.append(submenu_config)
            categorias.append('Cache en USB (AutoClean: %s)' % auto_clean); handlers.append(submenu_usb)
            categorias.append('Velocidad y diagnóstico'); handlers.append(submenu_speed_diag)
            if not is_android:
                categorias.append('Redirección de temp a USB'); handlers.append(submenu_temp_redirect)
            categorias.append('PVR / Timeshift'); handlers.append(submenu_timeshift)
            categorias.append('Optimizaciones de Video'); handlers.append(submenu_video_optimizations)
            categorias.append('Copias de seguridad'); handlers.append(submenu_backups)
            categorias.append('Volver'); handlers.append(None)

            seleccion = dialog.select('Gestión de Buffering', categorias)
            if seleccion == -1 or seleccion == len(categorias) - 1:
                log('Salir de gestión de buffering (agrupado)')
                break
            handler = handlers[seleccion]
            if callable(handler):
                handler()

    except Exception as e:
        log('Error gestionando buffering (agrupado): %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error gestionando buffering: %s' % str(e))

def show_current_buffering_config(config_path):
    """Proxy a buffering.py para mantener una única implementación."""
    return buffering_module.show_current_buffering_config(config_path)

def get_system_ram():
    """Obtiene la RAM total del sistema en bytes"""
    try:
        with open('/proc/meminfo') as f:
            for line in f:
                if line.startswith('MemTotal:'):
                    parts = line.split()
                    return _safe_int(parts[1]) * 1024 if len(parts) > 1 else 2 * 1024 * 1024 * 1024  # kB -> bytes
    except Exception:
        pass
    return 2 * 1024 * 1024 * 1024  # 2GB por defecto

def detect_network_type():
    """Detecta el tipo de conexión de red (WiFi, Ethernet, Desconocido)"""
    try:
        import subprocess
        # Intentar detectar interfaces de red activas
        result = subprocess.run(['ip', 'link', 'show'], capture_output=True, text=True, timeout=2)
        output = result.stdout.lower()
        
        if 'wlan' in output or 'wlp' in output:
            return 'WiFi'
        elif 'eth' in output or 'enp' in output:
            return 'Ethernet'
    except:
        pass
    return 'Desconocido'

def recommend_buffer_size(ram_bytes, is_android=False):
    """Recomienda tamaño de buffer según RAM disponible"""
    # Usar entre 5-10% de la RAM, con límites
    recommended = ram_bytes // 16  # ~6.25% de RAM
    
    # Aplicar límites
    if is_android:
        # Android: más conservador
        recommended = min(max(recommended, 20*1024*1024), 100*1024*1024)  # 20MB-100MB
    else:
        # Otros sistemas
        recommended = min(max(recommended, 30*1024*1024), 200*1024*1024)  # 30MB-200MB
    
    return recommended

def configure_basic_buffering(config_path):
    """Proxy a buffering.py para mantener una única implementación."""
    return buffering_module.configure_basic_buffering(config_path)

def configure_advanced_buffering(config_path):
    """Proxy a buffering.py para mantener una única implementación."""
    return buffering_module.configure_advanced_buffering(config_path)

def parse_advancedsettings_values(config_path):
    """Proxy a buffering.py para mantener una única implementación."""
    return buffering_module.parse_advancedsettings_values(config_path)

def show_buffering_values(config_path):
    """Proxy a buffering.py para mantener una única implementación."""
    return buffering_module.show_buffering_values(config_path)

def _autoclean_flag_path():
    return os.path.join(addon_data_dir, 'usb_autoclean.json')

def get_usb_autoclean_enabled():
    try:
        p = _autoclean_flag_path()
        if os.path.exists(p):
            with open(p, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return bool(data.get('enabled', False))
    except Exception as e:
        log('No se pudo leer usb_autoclean.json: %s' % str(e))
    return False

def set_usb_autoclean_enabled(val: bool):
    try:
        p = _autoclean_flag_path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w', encoding='utf-8') as f:
            json.dump({'enabled': bool(val)}, f)
        log('usb_autoclean = %s' % ('ON' if val else 'OFF'))
    except Exception as e:
        log('No se pudo escribir usb_autoclean.json: %s' % str(e))

def toggle_usb_autoclean():
    cur = get_usb_autoclean_enabled()
    set_usb_autoclean_enabled(not cur)
    xbmcgui.Dialog().notification(addon_name, 'Auto-limpiar cache USB: %s' % ('ON' if not cur else 'OFF'), time=3000)

def clean_usb_cachepath(config_path, silent=False):
    """Proxy a buffering.py para mantener una única implementación."""
    return buffering_module.clean_usb_cachepath(config_path, silent=silent)

def optimize_buffering_auto(config_path):
    """Proxy a buffering.py para mantener una única implementación."""
    return buffering_module.optimize_buffering_auto(config_path)

def _backup_dir():
    # Directorio de backups dentro del addon_data_dir
    d = os.path.join(addon_data_dir, 'backups')
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d

def backup_advancedsettings(config_path, manual=False):
    """Proxy a buffering.py para mantener una única implementación."""
    return buffering_module.backup_advancedsettings(config_path, manual=manual)

def _list_backups():
    d = _backup_dir()
    try:
        items = [f for f in os.listdir(d) if f.startswith('advancedsettings_') and f.endswith('.xml')]
        items.sort(reverse=True)
        return [os.path.join(d, f) for f in items]
    except Exception:
        return []

def restore_advancedsettings_interactive(config_path):
    """Proxy a buffering.py para mantener una única implementación."""
    return buffering_module.restore_advancedsettings_interactive(config_path)

def vacuum_databases():
    """Compacta bases de datos de Kodi (Textures, Addons, Videos)"""
    try:
        paths = get_kodi_paths()
        # directorio Database suele estar en special://database/
        db_dir = _translate('special://database/')
        if not os.path.exists(db_dir):
            xbmcgui.Dialog().ok('Información', 'No se encontró el directorio de bases de datos.')
            return

        # Localizar DBs comunes
        targets = []
        for name in os.listdir(db_dir):
            if name.lower().startswith(('textures', 'addons', 'myvideos')) and name.endswith('.db'):
                targets.append(os.path.join(db_dir, name))

        if not targets:
            xbmcgui.Dialog().ok('Información', 'No se encontraron bases de datos para compactar.')
            return

        # Confirmación
        msg = 'Se compactarán las siguientes bases de datos:\n\n' + '\n'.join('- ' + os.path.basename(t) for t in targets)
        if not xbmcgui.Dialog().yesno('Compactar Bases de Datos', msg, yeslabel='Compactar', nolabel='Cancelar'):
            return

        progress = xbmcgui.DialogProgress()
        progress.create('Compactando bases de datos', 'Iniciando...')
        for i, db_path in enumerate(targets, 1):
            percent = int((i / len(targets)) * 100) if len(targets) else 0
            progress.update(percent, 'Compactando %s' % os.path.basename(db_path))
            try:
                # Asegurar que no está en uso: pequeño sleep para dar tiempo a addons
                time.sleep(0.2)
                conn = sqlite3.connect(db_path)
                conn.execute('VACUUM')
                conn.close()
            except Exception as e:
                log('Error compactando %s: %s' % (db_path, str(e)))
        progress.close()
        xbmcgui.Dialog().ok('Completado', 'Compactación finalizada.')
    except Exception as e:
        log('Error compactando bases de datos: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error al compactar: %s' % str(e))

def _read_cachepath_from_config(config_path):
    try:
        if not os.path.exists(config_path):
            return None
        root = ET.parse(config_path).getroot()
        el = root.find('cache/cachepath')
        if el is not None and el.text:
            path = el.text.strip()
            return path
    except Exception as e:
        log('Error leyendo cachepath: %s' % str(e))
    return None

def test_usb_cachepath(config_path):
    """Prueba lectura/escritura en el cachepath configurado (KodiCache en USB)."""
    try:
        dialog = xbmcgui.Dialog()
        cpath = _read_cachepath_from_config(config_path)
        if not cpath:
            # Si se usa redirección de temp, sugerir la prueba alternativa
            temp_root = _special_temp_path()
            if os.path.islink(temp_root):
                if dialog.yesno('Sin cachepath (usando temp)',
                                 'No hay cachepath en advancedsettings.xml, pero special://temp está redirigido.\n\n'
                                 '¿Quieres probar escritura en special://temp/cache en su lugar?',
                                 yeslabel='Probar', nolabel='Cancelar'):
                    test_special_temp_cache_write()
                return
            dialog.ok('Prueba de cache', 'No hay cachepath configurado en advancedsettings.xml')
            return
        # Crear carpeta si no existe
        try:
            os.makedirs(cpath, exist_ok=True)
        except Exception:
            pass
        test_file = os.path.join(cpath, '.cache_test.txt')
        # Escribir
        write_ok = False
        read_ok = False
        try:
            with open(test_file, 'w', encoding='utf-8') as f:
                f.write('kodi-cache-test')
            write_ok = True
        except Exception as e:
            log('Fallo de escritura en cachepath: %s' % str(e))
        # Leer
        if write_ok:
            try:
                with open(test_file, 'r', encoding='utf-8') as f:
                    data = f.read().strip()
                read_ok = (data == 'kodi-cache-test')
            except Exception as e:
                log('Fallo de lectura en cachepath: %s' % str(e))
        # Borrar
        try:
            if os.path.exists(test_file):
                os.remove(test_file)
        except Exception:
            pass

        # Espacio libre
        try:
            st = os.statvfs(cpath)
            free = st.f_frsize * st.f_bavail
            total = st.f_frsize * st.f_blocks
            free_txt = '%s libres de %s' % (format_size(free), format_size(total))
        except Exception:
            free_txt = 'desconocido'

        msg = [
            'Cache path: %s' % cpath,
            'Espacio: %s' % free_txt,
            'Escritura: %s' % ('OK' if write_ok else 'FALLO'),
            'Lectura: %s' % ('OK' if read_ok else 'FALLO')
        ]
        dialog.ok('Prueba de cache USB', '\n'.join(msg))
    except Exception as e:
        log('Error en test_usb_cachepath: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error en prueba de cache: %s' % str(e))

def _special_temp_path():
    try:
        p = _translate('special://temp/')
        # Normalizar para funciones de os.path (quitar barra final)
        return os.path.normpath(p)
    except Exception:
        # Fallback razonable
        return os.path.expanduser('~/.kodi/temp')

def _temp_symlink_state_path():
    return os.path.join(addon_data_dir, 'temp_symlink_state.json')

def _is_linux_desktop():
    try:
        # Evitar Android
        if xbmc.getCondVisibility('system.platform.android'):
            return False
        return xbmc.getCondVisibility('system.platform.linux')
    except Exception:
        return os.name == 'posix'

def view_special_temp_cache():
    """Muestra información y algunos archivos recientes en special://temp"""
    try:
        dialog = xbmcgui.Dialog()
        temp_root = _special_temp_path()
        cache_dir = os.path.join(temp_root, 'cache')
        target = cache_dir if os.path.exists(cache_dir) else temp_root

        total_size = get_folder_size(target)
        total_files = count_files_in_folder(target)

        # Recopilar últimos archivos modificados
        recent = []
        for dirpath, dirnames, filenames in os.walk(target):
            for fn in filenames:
                fp = os.path.join(dirpath, fn)
                try:
                    st = os.stat(fp)
                except Exception:
                    continue
                recent.append((st.st_mtime, os.path.relpath(fp, target), st.st_size))
        recent.sort(reverse=True)
        lines = []
        lines.append('RUTA DE CACHÉ EN USO (special://temp)')
        lines.append('')
        lines.append('Temp real: %s%s' % (temp_root, ' (ENLACE)' if os.path.islink(temp_root) else ''))
        if os.path.exists(cache_dir):
            lines.append('Subcarpeta cache: %s' % cache_dir)
        lines.append('Archivos: %d' % total_files)
        lines.append('Tamaño total: %s' % format_size(total_size))
        lines.append('')
        lines.append('Archivos recientes:')
        for i, (mt, rel, sz) in enumerate(recent[:50], 1):
            ts = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mt))
            lines.append('%02d) %s  [%s]  %s' % (i, rel, format_size(sz), ts))
        if total_files == 0:
            lines.append('(No se encontraron archivos)')
        dialog.textviewer('Caché actual (special://temp)', '\n'.join(lines))
    except Exception as e:
        log('Error en view_special_temp_cache: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'No se pudo mostrar la caché: %s' % str(e))

def redirect_temp_cache_to_usb():
    """Crea un enlace simbólico desde special://temp hacia una carpeta en USB."""
    try:
        dialog = xbmcgui.Dialog()
        if not _is_linux_desktop():
            dialog.ok('No compatible', 'Esta función requiere Linux (no Android).')
            return

        temp_root = _special_temp_path()
        if not temp_root or not os.path.exists(os.path.dirname(temp_root)):
            dialog.ok('Error', 'No se resolvió la ruta de temp.')
            return

        # Elegir USB
        devices = detect_usb_devices()
        if not devices:
            sel = _browse_for_usb_folder()
            if sel:
                devices = [{'name': os.path.basename(sel) or 'USB seleccionado', 'path': sel}]
        if not devices:
            dialog.ok('Sin USBs', 'No se detectaron USBs y no se seleccionó carpeta.')
            return
        labels = ['%s (%s)' % (d['path'], d.get('free', '')) for d in devices]
        idx = dialog.select('Selecciona USB para redirigir la caché', labels)
        if idx == -1:
            return
        selected = devices[idx]
        target_dir = os.path.join(selected['path'], 'KodiTemp')
        try:
            os.makedirs(target_dir, exist_ok=True)
        except Exception as e:
            dialog.ok('Error', 'No se pudo crear carpeta en USB: %s' % str(e))
            return

        warn = ('Se redirigirá special://temp a:\n%s\n\n' % target_dir +
                'Se creará un enlace simbólico en:\n%s\n\n' % temp_root +
                'Recomendado: no reproduzcas contenido durante el cambio.\n\n' +
                '¿Continuar?')
        if not dialog.yesno('Redirigir caché a USB', warn, yeslabel='Continuar', nolabel='Cancelar'):
            return

        # Preparar temp actual
        backup_path = None
        try:
            if os.path.islink(temp_root):
                # Quitar enlace previo
                os.unlink(temp_root)
            elif os.path.exists(temp_root):
                if os.listdir(temp_root):
                    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                    backup_path = temp_root + '.bak-' + ts
                    os.rename(temp_root, backup_path)
                else:
                    # Vacía, eliminar
                    os.rmdir(temp_root)
        except Exception as e:
            dialog.ok('Error', 'No se pudo preparar temp: %s' % str(e))
            return

        # Crear enlace simbólico
        try:
            os.symlink(target_dir, temp_root)
        except Exception as e:
            # Intentar revertir si creamos backup
            try:
                if backup_path and not os.path.exists(temp_root):
                    os.rename(backup_path, temp_root)
            except Exception:
                pass
            dialog.ok('Error', 'No se pudo crear el enlace simbólico: %s' % str(e))
            return

        # Verificación rápida de escritura
        try:
            test_file = os.path.join(temp_root, '.temp_test')
            with open(test_file, 'w') as f:
                f.write('ok')
            os.remove(test_file)
            ok = True
        except Exception:
            ok = False

        # Guardar estado
        try:
            st = {
                'linked': True,
                'link': temp_root,
                'target': target_dir,
                'backup': backup_path,
                'created_at': datetime.datetime.now().isoformat()
            }
            with open(_temp_symlink_state_path(), 'w', encoding='utf-8') as f:
                json.dump(st, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

        dialog.ok('Redirección aplicada', 'special://temp -> %s\nEscritura: %s\nReinicia Kodi para asegurar el uso.' % (target_dir, 'OK' if ok else 'FALLO'))
        log('Temp redirigida a %s (ok=%s)' % (target_dir, ok))
    except Exception as e:
        log('Error en redirect_temp_cache_to_usb: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error redirigiendo cache: %s' % str(e))

def revert_temp_cache_redirection():
    """Elimina el symlink y restaura temp local."""
    try:
        dialog = xbmcgui.Dialog()
        temp_root = _special_temp_path()
        state = None
        try:
            p = _temp_symlink_state_path()
            if os.path.exists(p):
                with open(p, 'r', encoding='utf-8') as f:
                    state = json.load(f)
        except Exception:
            state = None

        if not os.path.islink(temp_root):
            dialog.ok('Sin enlace', 'La carpeta temp actual no es un enlace simbólico.')
            return

        if not dialog.yesno('Revertir redirección', 'Se eliminará el enlace y se recreará temp local. ¿Continuar?', yeslabel='Revertir', nolabel='Cancelar'):
            return

        # Quitar symlink
        try:
            os.unlink(temp_root)
        except Exception as e:
            dialog.ok('Error', 'No se pudo eliminar el enlace: %s' % str(e))
            return

        # Restaurar desde backup si existe
        restored = False
        backup_path = state.get('backup') if isinstance(state, dict) else None
        try:
            if backup_path and os.path.exists(backup_path):
                os.rename(backup_path, temp_root)
                restored = True
            else:
                os.makedirs(temp_root, exist_ok=True)
        except Exception as e:
            dialog.ok('Error', 'No se pudo restaurar temp: %s' % str(e))
            return

        # Actualizar estado
        try:
            with open(_temp_symlink_state_path(), 'w', encoding='utf-8') as f:
                json.dump({'linked': False, 'link': temp_root, 'restored': restored, 'updated_at': datetime.datetime.now().isoformat()}, f)
        except Exception:
            pass

        dialog.ok('Listo', 'Temp local %s.' % ('restaurada desde backup' if restored else 'recreada vacía'))
        log('Temp revertida; restored=%s' % restored)
    except Exception as e:
        log('Error en revert_temp_cache_redirection: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error revirtiendo redirección: %s' % str(e))

def test_special_temp_cache_write():
    """Crea la subcarpeta cache y prueba escritura/lectura en special://temp/cache"""
    try:
        dialog = xbmcgui.Dialog()
        temp_root = _special_temp_path()
        cache_dir = os.path.join(temp_root, 'cache')
        try:
            os.makedirs(cache_dir, exist_ok=True)
        except Exception as e:
            dialog.ok('Error', 'No se pudo crear cache: %s' % str(e))
            return
        # Prueba
        tf = os.path.join(cache_dir, '.write_test')
        ok_w = ok_r = False
        try:
            with open(tf, 'wb') as f:
                f.write(b'aspirando-kodi')
            ok_w = True
        except Exception as e:
            log('Fallo escritura temp/cache: %s' % str(e))
        if ok_w:
            try:
                with open(tf, 'rb') as f:
                    ok_r = (f.read() == b'aspirando-kodi')
            except Exception as e:
                log('Fallo lectura temp/cache: %s' % str(e))
        try:
            if os.path.exists(tf):
                os.remove(tf)
        except Exception:
            pass
        # Informe
        target = os.path.realpath(cache_dir) if os.path.islink(cache_dir) else cache_dir
        dialog.ok('Prueba special://temp/cache', 'Ruta: %s\nEscritura: %s\nLectura: %s' % (target, 'OK' if ok_w else 'FALLO', 'OK' if ok_r else 'FALLO'))
    except Exception as e:
        log('Error en test_special_temp_cache_write: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error en prueba de temp/cache: %s' % str(e))

def open_timeshift_settings():
    """Abre los ajustes de IPTV Simple (pvr.iptvsimple) con tratamiento especial en Android."""
    try:
        dialog = xbmcgui.Dialog()
        is_android = xbmc.getCondVisibility('system.platform.android')

        def _has_addon(addon_id: str) -> bool:
            try:
                addon = xbmcaddon.Addon(addon_id)
                return True
            except Exception:
                return False

        def _is_addon_enabled(addon_id: str) -> bool:
            try:
                return xbmc.getCondVisibility('System.HasAddon(%s)' % addon_id)
            except Exception:
                return False

        def _open_addon_settings(addon_id: str):
            """Abre los ajustes del addon con múltiples métodos de fallback"""
            try:
                # Método 1: Comando directo
                xbmc.executebuiltin('Addon.OpenSettings(%s)' % addon_id)
                xbmc.sleep(500)
                return True
            except Exception:
                pass
            
            try:
                # Método 2: Activar ventana con parámetros
                xbmc.executebuiltin('ActivateWindow(addonsettings,%s)' % addon_id)
                xbmc.sleep(500)
                return True
            except Exception:
                pass
                
            try:
                # Método 3: Abrir desde browser de addons
                xbmc.executebuiltin('ActivateWindow(addonbrowser,addons://enabled/xbmc.pvrclient/%s/,return)' % addon_id)
                xbmc.sleep(500)
                return True
            except Exception:
                pass
                
            return False

        # Verificar si IPTV Simple está instalado
        if not _has_addon('pvr.iptvsimple'):
            if dialog.yesno('IPTV Simple Client',
                             'El addon IPTV Simple Client no está instalado.\n\n'
                             '¿Deseas instalarlo desde el repositorio?',
                             yeslabel='Instalar', nolabel='Cancelar'):
                try:
                    # Intentar instalación automática
                    xbmc.executebuiltin('InstallAddon(pvr.iptvsimple)')
                    dialog.notification('Instalando', 'Instalando IPTV Simple Client...', time=3000)
                    
                    # Esperar hasta 30 segundos para que se instale
                    for i in range(60):
                        xbmc.sleep(500)
                        if _has_addon('pvr.iptvsimple'):
                            dialog.notification('Instalado', 'IPTV Simple Client instalado correctamente', time=2000)
                            break
                        if i == 30:  # Después de 15 segundos, mostrar progreso
                            dialog.notification('Instalando', 'Sigue instalando... por favor espera', time=2000)
                    else:
                        # Si falla la instalación automática, abrir browser
                        xbmc.executebuiltin('ActivateWindow(addonbrowser,addons://search/pvr.iptvsimple/,return)')
                        dialog.notification('Manual', 'Busca e instala "IPTV Simple Client" manualmente', time=4000)
                        return
                except Exception as e:
                    log('Error instalando IPTV Simple: %s' % str(e))
                    xbmc.executebuiltin('ActivateWindow(addonbrowser,addons://search/pvr.iptvsimple/,return)')
                    dialog.notification('Error', 'Instala IPTV Simple Client manualmente', time=4000)
                    return
            else:
                return

        # Verificar si está habilitado
        if not _is_addon_enabled('pvr.iptvsimple'):
            try:
                xbmc.executebuiltin('EnableAddon(pvr.iptvsimple)')
                xbmc.sleep(1000)  # Dar tiempo para que se habilite
                log('IPTV Simple Client habilitado')
            except Exception as e:
                log('Error habilitando IPTV Simple: %s' % str(e))

        # Intentar abrir configuración
        success = _open_addon_settings('pvr.iptvsimple')
        
        if success:
            dialog.notification('Configuración', 'Abriendo ajustes de IPTV Simple Client', time=2000)
        else:
            # Fallback: abrir configuraciones PVR generales
            log('No se pudo abrir configuración de IPTV Simple, abriendo PVR general')
            try:
                xbmc.executebuiltin('ActivateWindow(pvrsettings)')
                xbmc.sleep(500)
            except Exception:
                try:
                    xbmc.executebuiltin('ActivateWindow(settings,pvr,return)')
                    xbmc.sleep(500)
                except Exception:
                    xbmc.executebuiltin('ActivateWindow(settings)')
                    
            dialog.notification('Configuración PVR', 
                              'Ve a: TV en directo → General → Cliente PVR', 
                              time=5000)
                              
    except Exception as e:
        log('Error abriendo ajustes de Timeshift: %s' % str(e))
        xbmcgui.Dialog().notification('Error', 'No se pudieron abrir los ajustes: %s' % str(e), time=4000)

def get_user_readbufferfactor():
    """Obtiene el readbufferfactor personalizado del usuario desde settings"""
    try:
        if addon.getSettingBool('custom_readbufferfactor_enabled'):
            factor = addon.getSettingNumber('custom_readbufferfactor')
            return float(factor) if factor is not None else 0.0
    except Exception:
        pass
    return 0.0

def apply_android_optimizations():
    """Verifica si las optimizaciones de Android están habilitadas"""
    try:
        return addon.getSettingBool('android_optimize_enabled')
    except Exception:
        return True  # Por defecto habilitado

def get_android_buffer_limit():
    """Obtiene el límite de buffer para Android desde settings"""
    try:
        limit_idx = addon.getSettingInt('buffer_size_limit_android')
        if limit_idx is None:
            limit_idx = 1  # Default a 32MB
        limits = [24, 32, 48, 64, 128]  # MB
        if 0 <= limit_idx < len(limits):
            return limits[limit_idx] * 1024 * 1024
        return 64 * 1024 * 1024  # 64MB por defecto
    except Exception:
        return 64 * 1024 * 1024  # 64MB por defecto

def get_sync_corrections():
    """Obtiene las correcciones de sincronización de audio/video desde settings"""
    try:
        sync_enabled = addon.getSettingBool('audio_sync_enabled')
        video_delay = addon.getSettingInt('video_delay_correction') if sync_enabled else 0
        audio_delay = addon.getSettingInt('audio_delay_correction') if sync_enabled else 0
        return {
            'enabled': sync_enabled,
            'video_delay': video_delay if video_delay is not None else 0,
            'audio_delay': audio_delay if audio_delay is not None else 0
        }
    except Exception:
        return {'enabled': False, 'video_delay': 0, 'audio_delay': 0}

def get_buffering_preferences():
    """Obtiene las preferencias de buffering desde settings"""
    try:
        conservative = addon.getSettingBool('conservative_buffering')
        aggressive = addon.getSettingBool('aggressive_prefetch')
        return {
            'conservative': conservative if conservative is not None else False,
            'aggressive': aggressive if aggressive is not None else False
        }
    except Exception:
        return {'conservative': False, 'aggressive': False}

def apply_sync_corrections_to_config(config_xml):
    """Aplica las correcciones de sincronización al XML de configuración"""
    try:
        sync = get_sync_corrections()
        prefs = get_buffering_preferences()
        
        if not sync['enabled']:
            return config_xml
            
        # Buscar la sección de video y agregar configuraciones A/V
        video_section = ""
        if sync['video_delay'] != 0:
            video_section += f"        <displaydelay>{sync['video_delay']}</displaydelay>\n"
        if sync['audio_delay'] != 0:
            video_section += f"        <audiodelay>{sync['audio_delay']}</audiodelay>\n"
        
        # Configuraciones adicionales para mejor sincronización
        if prefs['conservative']:
            video_section += "        <adjustrefreshrate>0</adjustrefreshrate>\n"
            video_section += "        <pauseafterrefreshchange>0</pauseafterrefreshchange>\n"
        
        # Si hay configuraciones de video que agregar
        if video_section:
            # Insertar en la sección <video>
            if "<video>" in config_xml and "</video>" in config_xml:
                # Reemplazar la sección existente
                import re
                pattern = r'(<video>)(.*?)(</video>)'
                def replace_video(match):
                    start, content, end = match.groups()
                    # Mantener contenido existente y agregar nuevas configuraciones
                    new_content = content.rstrip() + "\n" + video_section
                    return start + new_content + "    " + end
                config_xml = re.sub(pattern, replace_video, config_xml, flags=re.DOTALL)
            
        log(f'Correcciones de sincronización aplicadas: video={sync["video_delay"]}ms, audio={sync["audio_delay"]}ms')
        return config_xml
    except Exception as e:
        log(f'Error aplicando correcciones de sincronización: {str(e)}')
        return config_xml

def reset_android_pvr_warning():
    """Resetea la bandera del warning de PVR en Android para que vuelva a aparecer"""
    try:
        addon_data_dir = xbmcvfs.translatePath('special://profile/addon_data/%s' % addon_id)
        android_pvr_handled_file = os.path.join(addon_data_dir, 'android_pvr_handled.flag')
        
        if os.path.exists(android_pvr_handled_file):
            os.remove(android_pvr_handled_file)
            xbmcgui.Dialog().ok('Reseteo Completo', 
                              'Se reseteó el estado de verificación PVR.\n\n'
                              'Al reiniciar Kodi, se volverá a verificar\n'
                              'el funcionamiento del PVR en Android.\n\n'
                              'Nota: Ahora espera hasta 180 segundos\n'
                              'para que los canales se carguen.')
            log('Bandera de PVR Android reseteada')
        else:
            xbmcgui.Dialog().ok('Info', 
                              'No hay estado de verificación PVR para resetear.\n\n'
                              'La verificación se ejecutará automáticamente\n'
                              'en el próximo reinicio de Kodi.')
    except Exception as e:
        log('Error reseteando bandera PVR Android: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error reseteando bandera: %s' % str(e))

def restore_kodi_defaults():
    """Restaura Kodi a valores de fábrica con backup automático y opciones personalizables"""
    try:
        dialog = xbmcgui.Dialog()
        
        # Opciones de restauración
        reset_options = dialog.select(
            'Restaurar a Valores de Fábrica',
            [
                '🔧 Restauración básica (solo configuración de buffering)',
                '⚙️ Restauración completa (recomendado)',
                '🗑️ Restauración completa + limpieza profunda',
                '❌ Cancelar'
            ]
        )
        
        if reset_options in (-1, 3):  # Cancelar
            return
        
        # Determinar qué incluir según la opción
        basic_reset = (reset_options == 0)
        deep_clean = (reset_options == 2)
        
        # Advertencia según el tipo de restauración
        if basic_reset:
            warning_msg = ('Restauración Básica:\n\n'
                          '• Se eliminará advancedsettings.xml\n'
                          '• Se resetearán configuraciones de buffering\n'
                          '• NO se eliminarán datos personales\n'
                          '• NO se limpiarán cachés\n\n'
                          '¿Continuar?')
        elif deep_clean:
            warning_msg = ('⚠️ RESTAURACIÓN COMPLETA + LIMPIEZA ⚠️\n\n'
                          'Se eliminará TODO:\n'
                          '• Configuración de buffering\n'
                          '• Configuraciones de video/audio\n'
                          '• Caché, thumbnails, temporales\n'
                          '• Base de datos de texturas\n'
                          '• Paquetes de addons\n'
                          '• Configuraciones del addon\n\n'
                          '¡Kodi quedará como recién instalado!\n\n'
                          '¿Estás SEGURO?')
        else:  # Completa estándar
            warning_msg = ('⚠️ RESTAURACIÓN COMPLETA ⚠️\n\n'
                          'Se restaurará:\n'
                          '• Configuración de buffering\n'
                          '• Configuraciones de video/audio\n'
                          '• Configuraciones del addon\n'
                          '• Se limpiarán configuraciones temporales\n\n'
                          'NO se eliminarán:\n'
                          '• Bibliotecas de medios\n'
                          '• Addons instalados\n'
                          '• Thumbnails generados\n\n'
                          '¿Continuar?')
        
        if not dialog.yesno('Confirmar Restauración', warning_msg, yeslabel='Sí', nolabel='No'):
            return
        
        # Confirmación final para restauración profunda
        if deep_clean or not basic_reset:
            if not dialog.yesno('Confirmación Final',
                               'Esta es tu última oportunidad.\n\n'
                               '¿REALMENTE deseas continuar?',
                               yeslabel='Confirmar',
                               nolabel='Cancelar'):
                return
        
        log('Iniciando restauración a valores de fábrica (tipo: %d)' % reset_options)
        
        # Crear backup automático de advancedsettings.xml
        try:
            paths = get_kodi_paths()
            advancedsettings_path = paths.get('advancedsettings', '')
            if advancedsettings_path and os.path.exists(advancedsettings_path):
                backup_advancedsettings(advancedsettings_path, manual=False)
                log('Backup automático de advancedsettings.xml creado')
        except Exception as e:
            log('No se pudo crear backup automático: %s' % str(e))
        
        # Mostrar progreso
        progress = xbmcgui.DialogProgress()
        progress.create('Restaurando a Valores de Fábrica', 'Iniciando restauración...')
        
        restored_items = []
        errors = []
        total_steps = 10 if deep_clean else (6 if not basic_reset else 3)
        current_step = 0
        
        def update_progress(message):
            nonlocal current_step
            current_step += 1
            percent = int((current_step / total_steps) * 100) if total_steps else 0
            progress.update(percent, message)
            xbmc.sleep(300)
        
        # 1. Eliminar advancedsettings.xml
        update_progress('Eliminando configuración de buffering...')
        try:
            paths = get_kodi_paths()
            advancedsettings_path = paths.get('advancedsettings', '')
            
            if advancedsettings_path and os.path.exists(advancedsettings_path):
                os.remove(advancedsettings_path)
                restored_items.append('✓ advancedsettings.xml eliminado')
                log('advancedsettings.xml eliminado')
            else:
                restored_items.append('• advancedsettings.xml no existía')
        except Exception as e:
            error_msg = 'advancedsettings.xml: %s' % str(e)
            errors.append(error_msg)
            log('Error: ' + error_msg)
        
        if not basic_reset:
            # 2. Limpiar bases de datos
            update_progress('Limpiando base de datos de texturas...')
            try:
                if clean_textures_database():
                    restored_items.append('✓ Base de datos de texturas limpiada')
                else:
                    restored_items.append('• Base de datos de texturas no encontrada')
            except Exception as e:
                errors.append('Base de datos: %s' % str(e))
            
            # 3. Resetear configuraciones del addon
            update_progress('Reseteando configuraciones del addon...')
            try:
                addon_data_path = addon_data_dir
                if os.path.exists(addon_data_path):
                    config_files = [
                        'android_pvr_handled.flag',
                        'schedule_clean.json',
                        'usb_autoclean.json',
                        'temp_symlink_state.json'
                    ]
                    
                    removed_configs = 0
                    for config_file in config_files:
                        file_path = os.path.join(addon_data_path, config_file)
                        if os.path.exists(file_path):
                            os.remove(file_path)
                            removed_configs += 1
                    
                    if removed_configs > 0:
                        restored_items.append('✓ %d archivo(s) de configuración eliminados' % removed_configs)
                    else:
                        restored_items.append('• No había archivos de configuración')
            except Exception as e:
                errors.append('Configs addon: %s' % str(e))
            
            # 4. Resetear ajustes del addon
            update_progress('Reseteando ajustes del addon...')
            try:
                # Intentar resetear configuraciones guardadas
                reset_count = 0
                try:
                    addon.setSettingBool('custom_readbufferfactor_enabled', False)
                    reset_count += 1
                except:
                    pass
                try:
                    addon.setSettingNumber('custom_readbufferfactor', 4.0)
                    reset_count += 1
                except:
                    pass
                try:
                    addon.setSettingBool('android_optimize_enabled', True)
                    reset_count += 1
                except:
                    pass
                
                if reset_count > 0:
                    restored_items.append('✓ %d ajuste(s) del addon reseteados' % reset_count)
            except Exception as e:
                errors.append('Ajustes: %s' % str(e))
            
            # 5. Resetear configuraciones de Kodi mediante JSON-RPC
            update_progress('Reseteando configuraciones de video/audio...')
            try:
                kodi_settings = {
                    'videoplayer.adjustrefreshrate': 0,
                    'videoplayer.usedisplayasclock': True,
                    'audiooutput.audiodevice': 'default',
                    'audiooutput.passthrough': False,
                    'audiooutput.ac3passthrough': False,
                    'audiooutput.dtspassthrough': False,
                }
                
                reset_settings = 0
                for setting, default_value in kodi_settings.items():
                    try:
                        json_cmd = json.dumps({
                            "jsonrpc": "2.0",
                            "method": "Settings.SetSettingValue",
                            "params": {"setting": setting, "value": default_value},
                            "id": 1
                        })
                        xbmc.executeJSONRPC(json_cmd)
                        reset_settings += 1
                    except:
                        pass
                
                if reset_settings > 0:
                    restored_items.append('✓ %d configuración(es) de Kodi reseteadas' % reset_settings)
            except Exception as e:
                errors.append('Settings Kodi: %s' % str(e))
            
            # 6. Limpiar archivos de configuración temporal
            update_progress('Limpiando archivos temporales de configuración...')
            try:
                temp_cleaned = 0
                paths = get_kodi_paths()
                
                for path_type in ['temp', 'cache']:
                    path = paths.get(path_type, '')
                    if path and os.path.exists(path):
                        for item in os.listdir(path):
                            if item.endswith(('.xml', '.tmp', '.cache')):
                                try:
                                    item_path = os.path.join(path, item)
                                    if os.path.isfile(item_path):
                                        os.remove(item_path)
                                        temp_cleaned += 1
                                except:
                                    pass
                
                if temp_cleaned > 0:
                    restored_items.append('✓ %d archivo(s) temporal(es) limpiados' % temp_cleaned)
            except Exception as e:
                errors.append('Archivos temp: %s' % str(e))
        
        if deep_clean:
            # 7. Limpieza profunda - Caché
            update_progress('Limpiando caché completa...')
            try:
                paths = get_kodi_paths()
                cache_path = paths.get('cache', '')
                if cache_path and os.path.exists(cache_path):
                    removed_count, removed_size = safe_remove_folder_contents(cache_path)
                    restored_items.append('✓ Caché limpiada: %d archivos (%s)' % (removed_count, format_size(removed_size)))
            except Exception as e:
                errors.append('Caché: %s' % str(e))
            
            # 8. Limpieza profunda - Thumbnails
            update_progress('Limpiando thumbnails...')
            try:
                paths = get_kodi_paths()
                thumbnails_path = paths.get('thumbnails', '')
                if thumbnails_path and os.path.exists(thumbnails_path):
                    removed_count, removed_size = safe_remove_folder_contents(thumbnails_path)
                    clean_textures_database()  # Ya se hizo antes, pero asegurar
                    restored_items.append('✓ Thumbnails limpiados: %d archivos (%s)' % (removed_count, format_size(removed_size)))
            except Exception as e:
                errors.append('Thumbnails: %s' % str(e))
            
            # 9. Limpieza profunda - Paquetes
            update_progress('Limpiando paquetes de addons...')
            try:
                paths = get_kodi_paths()
                packages_path = paths.get('packages', '')
                if packages_path and os.path.exists(packages_path):
                    removed_count, removed_size = safe_remove_folder_contents(packages_path)
                    restored_items.append('✓ Paquetes limpiados: %d archivos (%s)' % (removed_count, format_size(removed_size)))
            except Exception as e:
                errors.append('Paquetes: %s' % str(e))
            
            # 10. Limpieza profunda - Temporales
            update_progress('Limpiando archivos temporales...')
            try:
                paths = get_kodi_paths()
                temp_path = paths.get('temp', '')
                if temp_path and os.path.exists(temp_path):
                    removed_count, removed_size = safe_remove_folder_contents(temp_path)
                    restored_items.append('✓ Temporales limpiados: %d archivos (%s)' % (removed_count, format_size(removed_size)))
            except Exception as e:
                errors.append('Temporales: %s' % str(e))
        
        progress.update(100, 'Restauración completada')
        xbmc.sleep(1000)
        progress.close()
        
        # Generar resumen
        if basic_reset:
            title = 'Restauración Básica Completada'
        elif deep_clean:
            title = 'Restauración Completa + Limpieza Profunda'
        else:
            title = 'Restauración Completa Exitosa'
        
        summary_lines = [title, '=' * 50, '']
        
        if restored_items:
            summary_lines.append('ACCIONES REALIZADAS:')
            summary_lines.extend(restored_items)
        
        if errors:
            summary_lines.extend(['', 'ERRORES (no críticos):'])
            for error in errors:
                summary_lines.append('✗ ' + error)
        
        summary_lines.extend([
            '',
            '=' * 50,
            'SIGUIENTE PASO:',
            '',
            '🔄 DEBES REINICIAR KODI para que todos',
            '   los cambios surtan efecto.',
            '',
            '📝 Después del reinicio:',
            '   • Reconfigura tus preferencias personales',
            '   • Ajusta buffering si es necesario',
            '   • Verifica configuraciones de video/audio'
        ])
        
        if not basic_reset:
            summary_lines.extend([
                '',
                '💾 NOTA: Se creó un backup automático de',
                '   advancedsettings.xml que puedes restaurar',
                '   desde: Gestión de Buffering > Backups'
            ])
        
        summary_text = '\n'.join(summary_lines)
        dialog.textviewer(title, summary_text)
        
        log('Restauración completada: %d acciones, %d errores' % (len(restored_items), len(errors)))
        
        # Preguntar si reiniciar
        if dialog.yesno('Reiniciar Kodi',
                       '✅ Restauración completada exitosamente.\n\n'
                       'Es NECESARIO reiniciar Kodi para aplicar\n'
                       'todos los cambios correctamente.\n\n'
                       '¿Reiniciar Kodi ahora?',
                       yeslabel='Reiniciar Ahora',
                       nolabel='Reiniciar Más Tarde'):
            log('Reiniciando Kodi después de restauración')
            xbmc.executebuiltin('RestartApp')
        else:
            dialog.ok('Recordatorio',
                     '⚠️ Recuerda reiniciar Kodi manualmente\n'
                     'para que los cambios surtan efecto.\n\n'
                     'Algunos ajustes no se aplicarán hasta\n'
                     'que reinicies Kodi.')
            
    except Exception as e:
        log('Error en restore_kodi_defaults: %s' % str(e))
        xbmcgui.Dialog().ok('Error',
                           'Error durante la restauración:\n\n%s\n\n'
                           'Es posible que algunos cambios no\n'
                           'se hayan aplicado correctamente.' % str(e))

def configure_hardware_acceleration():
    """Configura la aceleración por hardware según la plataforma"""
    try:
        dialog = xbmcgui.Dialog()
        
        # Detectar plataforma
        is_android = xbmc.getCondVisibility('system.platform.android')
        is_linux = xbmc.getCondVisibility('system.platform.linux')
        is_windows = xbmc.getCondVisibility('system.platform.windows')
        
        platform_info = []
        if is_android:
            platform_info.append('Plataforma: Android')
        elif is_linux:
            platform_info.append('Plataforma: Linux')
        elif is_windows:
            platform_info.append('Plataforma: Windows')
        else:
            platform_info.append('Plataforma: Otra')
            
        platform_info.extend([
            '',
            'Selecciona el tipo de aceleración por hardware:',
            '',
            '• AUTO: Kodi decide automáticamente',
            '• VAAPI: Intel/AMD en Linux',
            '• VDPAU: NVIDIA en Linux',
            '• DXVA2: Windows con DirectX',
            '• MediaCodec: Android moderno',
            '• Deshabilitado: Solo software'
        ])
        
        opciones = [
            'AUTO (Recomendado)',
            'VAAPI (Intel/AMD Linux)',
            'VDPAU (NVIDIA Linux)', 
            'DXVA2 (Windows)',
            'MediaCodec (Android)',
            'Deshabilitar aceleración por hardware'
        ]
        
        dialog.textviewer('Información de Aceleración por Hardware', '\n'.join(platform_info))
        
        choice = dialog.select('Configurar Aceleración por Hardware', opciones)
        if choice == -1:
            return
            
        settings_map = {
            0: {'videoplayer.usevaapih264': True, 'videoplayer.usevaapihevc': True, 'videoplayer.usevaapiav1': True},  # AUTO
            1: {'videoplayer.usevaapih264': True, 'videoplayer.usevaapihevc': True, 'videoplayer.usevaapiav1': True},  # VAAPI
            2: {'videoplayer.usevdpau': True, 'videoplayer.usevaapih264': False},  # VDPAU
            3: {'videoplayer.usedxva2': True},  # DXVA2
            4: {'videoplayer.useamcodecav1': True, 'videoplayer.useamcodech264': True},  # MediaCodec
            5: {'videoplayer.usevaapih264': False, 'videoplayer.usevaapihevc': False, 'videoplayer.usevaapiav1': False, 'videoplayer.usevdpau': False, 'videoplayer.usedxva2': False, 'videoplayer.useamcodecav1': False, 'videoplayer.useamcodech264': False}  # Disabled
        }
        
        if choice in settings_map:
            applied_settings = []
            for setting, value in settings_map[choice].items():
                try:
                    json_cmd = {
                        "jsonrpc": "2.0",
                        "method": "Settings.SetSettingValue",
                        "params": {"setting": setting, "value": value},
                        "id": 1
                    }
                    result = xbmc.executeJSONRPC(json.dumps(json_cmd))
                    applied_settings.append(f'{setting}: {value}')
                except Exception as e:
                    log(f'Error configurando {setting}: {str(e)}')
            
            dialog.ok('Configuración Aplicada',
                     f'Aceleración por hardware configurada: {opciones[choice]}\n\n'
                     'Se recomienda reiniciar Kodi para aplicar los cambios.')
            log(f'Aceleración por hardware configurada: {opciones[choice]}')
            
    except Exception as e:
        log('Error configurando aceleración por hardware: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error configurando aceleración: %s' % str(e))

def optimize_video_playback():
    """Optimiza configuraciones generales de reproducción de video"""
    try:
        dialog = xbmcgui.Dialog()
        
        info_text = [
            'OPTIMIZACIONES DE REPRODUCCIÓN DE VIDEO',
            '=' * 40,
            '',
            'Selecciona el perfil de optimización:',
            '',
            '• CALIDAD MÁXIMA: Mejor calidad visual',
            '  - Desentrelazado avanzado',
            '  - Escalado de alta calidad',
            '  - Sin salto de frames',
            '',
            '• RENDIMIENTO: Mejor fluidez',
            '  - Desentrelazado rápido',
            '  - Escalado optimizado',
            '  - Permite salto de frames',
            '',
            '• EQUILIBRADO: Balance calidad/rendimiento',
            '  - Configuraciones intermedias',
            '  - Recomendado para la mayoría'
        ]
        
        dialog.textviewer('Información de Optimización', '\n'.join(info_text))
        
        opciones = [
            'Calidad Máxima (hardware potente)',
            'Rendimiento (hardware limitado)', 
            'Equilibrado (recomendado)',
            'Personalizado'
        ]
        
        choice = dialog.select('Optimizar Reproducción de Video', opciones)
        if choice == -1:
            return
            
        settings_profiles = {
            0: {  # Calidad máxima
                'videoplayer.adjustrefreshrate': 2,  # Siempre ajustar
                'videoplayer.usedisplayasclock': True,
                'videoplayer.synctype': 2,  # Video clock resample
                'videoplayer.deinterlacemethod': 1,  # VAAPI/DXVA deinterlace
                'videoplayer.scalingmethod': 2,  # Bicubic
                'videoplayer.hqscalers': True
            },
            1: {  # Rendimiento
                'videoplayer.adjustrefreshrate': 1,  # En reproducción
                'videoplayer.usedisplayasclock': False,
                'videoplayer.synctype': 0,  # Audio clock
                'videoplayer.deinterlacemethod': 0,  # Rápido
                'videoplayer.scalingmethod': 0,  # Rápido
                'videoplayer.hqscalers': False
            },
            2: {  # Equilibrado
                'videoplayer.adjustrefreshrate': 1,  # En reproducción
                'videoplayer.usedisplayasclock': True,
                'videoplayer.synctype': 1,  # Clock resample
                'videoplayer.deinterlacemethod': 0,  # Auto
                'videoplayer.scalingmethod': 1,  # Lanczos
                'videoplayer.hqscalers': False
            }
        }
        
        if choice in settings_profiles:
            applied_settings = []
            for setting, value in settings_profiles[choice].items():
                try:
                    json_cmd = {
                        "jsonrpc": "2.0",
                        "method": "Settings.SetSettingValue",
                        "params": {"setting": setting, "value": value},
                        "id": 1
                    }
                    xbmc.executeJSONRPC(json.dumps(json_cmd))
                    applied_settings.append(f'{setting}: {value}')
                except Exception as e:
                    log(f'Error configurando {setting}: {str(e)}')
            
            dialog.ok('Optimización Aplicada',
                     f'Perfil aplicado: {opciones[choice]}\n\n'
                     'Configuraciones aplicadas correctamente.\n'
                     'Se recomienda probar la reproducción.')
            log(f'Optimización de video aplicada: {opciones[choice]}')
            
        elif choice == 3:  # Personalizado
            dialog.ok('Configuración Personalizada',
                     'Usa las otras opciones del menú para\n'
                     'configurar aspectos específicos:\n\n'
                     '• Refresh rate automático\n'
                     '• Escalado de video\n'
                     '• Configuración de audio\n'
                     '• Configuración avanzada')
            
    except Exception as e:
        log('Error optimizando reproducción de video: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error en optimización: %s' % str(e))

def configure_refresh_rate():
    """Configura el ajuste automático del refresh rate"""
    try:
        dialog = xbmcgui.Dialog()
        
        info_text = [
            'CONFIGURACIÓN DE REFRESH RATE',
            '=' * 30,
            '',
            'El ajuste automático del refresh rate adapta',
            'la frecuencia de la pantalla al contenido.',
            '',
            'Opciones disponibles:',
            '',
            '• DESACTIVADO: Sin cambios automáticos',
            '• EN REPRODUCCIÓN: Solo al reproducir',
            '• SIEMPRE: Al navegar y reproducir',
            '',
            'Recomendado: EN REPRODUCCIÓN para la',
            'mayoría de configuraciones.'
        ]
        
        dialog.textviewer('Información Refresh Rate', '\n'.join(info_text))
        
        opciones = [
            'Desactivado',
            'En reproducción (recomendado)',
            'Siempre activo'
        ]
        
        choice = dialog.select('Configurar Refresh Rate Automático', opciones)
        if choice == -1:
            return
            
        refresh_values = {0: 0, 1: 1, 2: 2}
        
        if choice in refresh_values:
            try:
                json_cmd = {
                    "jsonrpc": "2.0",
                    "method": "Settings.SetSettingValue",
                    "params": {"setting": "videoplayer.adjustrefreshrate", "value": refresh_values[choice]},
                    "id": 1
                }
                xbmc.executeJSONRPC(json.dumps(json_cmd))
                
                dialog.ok('Configuración Aplicada',
                         f'Refresh rate configurado: {opciones[choice]}\n\n'
                         'La configuración se aplicará en la\n'
                         'próxima reproducción.')
                log(f'Refresh rate configurado: {opciones[choice]}')
                
            except Exception as e:
                dialog.ok('Error', f'Error configurando refresh rate: {str(e)}')
                
    except Exception as e:
        log('Error configurando refresh rate: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error en configuración: %s' % str(e))

def configure_audio_settings():
    """Configura optimizaciones de audio"""
    try:
        dialog = xbmcgui.Dialog()
        
        info_text = [
            'CONFIGURACIONES DE AUDIO',
            '=' * 25,
            '',
            'Optimizaciones disponibles:',
            '',
            '• NORMALIZACIÓN: Ecualiza volumen',
            '• PASSTHROUGH: Audio directo al receptor',
            '• UPSAMPLING: Mejora calidad de audio',
            '• SINCRONIZACIÓN: Corrige desfases A/V',
            '',
            'Selecciona la configuración a ajustar:'
        ]
        
        dialog.textviewer('Información de Audio', '\n'.join(info_text))
        
        opciones = [
            'Configurar normalización de volumen',
            'Configurar passthrough AC3/DTS',
            'Configurar upsampling de audio',
            'Configurar sincronización A/V',
            'Resetear configuración de audio'
        ]
        
        choice = dialog.select('Configurar Audio', opciones)
        if choice == -1:
            return
            
        if choice == 0:  # Normalización
            norm_options = ['Desactivado', 'Activado (recomendado)']
            norm_choice = dialog.select('Normalización de Volumen', norm_options)
            if norm_choice != -1:
                try:
                    json_cmd = {
                        "jsonrpc": "2.0",
                        "method": "Settings.SetSettingValue",
                        "params": {"setting": "audiooutput.normalizelevels", "value": bool(norm_choice)},
                        "id": 1
                    }
                    xbmc.executeJSONRPC(json.dumps(json_cmd))
                    dialog.notification('Audio', f'Normalización: {norm_options[norm_choice]}', time=2000)
                except Exception as e:
                    dialog.ok('Error', f'Error configurando normalización: {str(e)}')
                    
        elif choice == 1:  # Passthrough
            pass_options = ['Desactivado', 'AC3 y DTS', 'Solo AC3', 'Solo DTS']
            pass_choice = dialog.select('Configurar Passthrough', pass_options)
            if pass_choice != -1:
                settings_map = {
                    0: {'audiooutput.ac3passthrough': False, 'audiooutput.dtspassthrough': False},
                    1: {'audiooutput.ac3passthrough': True, 'audiooutput.dtspassthrough': True},
                    2: {'audiooutput.ac3passthrough': True, 'audiooutput.dtspassthrough': False},
                    3: {'audiooutput.ac3passthrough': False, 'audiooutput.dtspassthrough': True}
                }
                
                for setting, value in settings_map[pass_choice].items():
                    try:
                        json_cmd = {
                            "jsonrpc": "2.0",
                            "method": "Settings.SetSettingValue",
                            "params": {"setting": setting, "value": value},
                            "id": 1
                        }
                        xbmc.executeJSONRPC(json.dumps(json_cmd))
                    except Exception:
                        pass
                dialog.notification('Audio', f'Passthrough: {pass_options[pass_choice]}', time=2000)
                
        elif choice == 2:  # Upsampling
            upsample_options = ['Desactivado', '48 kHz', '96 kHz', '192 kHz']
            upsample_choice = dialog.select('Configurar Upsampling', upsample_options)
            if upsample_choice != -1:
                upsample_values = {0: 0, 1: 48000, 2: 96000, 3: 192000}
                try:
                    json_cmd = {
                        "jsonrpc": "2.0",
                        "method": "Settings.SetSettingValue",
                        "params": {"setting": "audiooutput.samplerate", "value": upsample_values[upsample_choice]},
                        "id": 1
                    }
                    xbmc.executeJSONRPC(json.dumps(json_cmd))
                    dialog.notification('Audio', f'Upsampling: {upsample_options[upsample_choice]}', time=2000)
                except Exception as e:
                    dialog.ok('Error', f'Error configurando upsampling: {str(e)}')
                    
        elif choice == 3:  # Sincronización A/V
            dialog.ok('Sincronización A/V',
                     'Para configurar sincronización A/V usa:\n\n'
                     'Gestión de Buffering > Configuración de buffering\n\n'
                     'Allí encontrarás opciones específicas para\n'
                     'corrección de retrasos de audio y video.')
                     
        elif choice == 4:  # Reset
            if dialog.yesno('Resetear Audio',
                           'Esto restaurará todas las configuraciones\n'
                           'de audio a los valores predeterminados.\n\n'
                           '¿Continuar?'):
                audio_defaults = {
                    'audiooutput.normalizelevels': False,
                    'audiooutput.ac3passthrough': False,
                    'audiooutput.dtspassthrough': False,
                    'audiooutput.samplerate': 0
                }
                
                for setting, value in audio_defaults.items():
                    try:
                        json_cmd = {
                            "jsonrpc": "2.0",
                            "method": "Settings.SetSettingValue",
                            "params": {"setting": setting, "value": value},
                            "id": 1
                        }
                        xbmc.executeJSONRPC(json.dumps(json_cmd))
                    except Exception:
                        pass
                        
                dialog.ok('Reset Completado', 'Configuraciones de audio restablecidas.')
                
    except Exception as e:
        log('Error configurando audio: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error en configuración de audio: %s' % str(e))

def configure_video_scaling():
    """Configura métodos de escalado de video"""
    try:
        dialog = xbmcgui.Dialog()
        
        info_text = [
            'MÉTODOS DE ESCALADO DE VIDEO',
            '=' * 30,
            '',
            'El escalado mejora la calidad visual cuando',
            'el video se redimensiona.',
            '',
            'Métodos disponibles:',
            '',
            '• RÁPIDO: Menor calidad, mejor rendimiento',
            '• LANCZOS: Balance calidad/rendimiento',
            '• BICÚBICO: Mejor calidad, más exigente',
            '',
            'Para hardware limitado: RÁPIDO',
            'Para hardware potente: BICÚBICO'
        ]
        
        dialog.textviewer('Información de Escalado', '\n'.join(info_text))
        
        opciones = [
            'Rápido (mejor rendimiento)',
            'Lanczos (equilibrado)', 
            'Bicúbico (mejor calidad)',
            'Configuración avanzada'
        ]
        
        choice = dialog.select('Configurar Escalado de Video', opciones)
        if choice == -1:
            return
            
        if choice < 3:
            scaling_values = {0: 0, 1: 1, 2: 2}  # Fast, Lanczos, Bicubic
            
            try:
                json_cmd = {
                    "jsonrpc": "2.0",
                    "method": "Settings.SetSettingValue",
                    "params": {"setting": "videoplayer.scalingmethod", "value": scaling_values[choice]},
                    "id": 1
                }
                xbmc.executeJSONRPC(json.dumps(json_cmd))
                
                dialog.ok('Escalado Configurado',
                         f'Método de escalado: {opciones[choice]}\n\n'
                         'El cambio se aplicará en la próxima\n'
                         'reproducción de video.')
                log(f'Escalado de video configurado: {opciones[choice]}')
                
            except Exception as e:
                dialog.ok('Error', f'Error configurando escalado: {str(e)}')
                
        elif choice == 3:  # Configuración avanzada
            hq_choice = dialog.yesno('Escaladores de Alta Calidad',
                                   'Los escaladores de alta calidad mejoran\n'
                                   'la calidad visual pero requieren más\n'
                                   'potencia de procesamiento.\n\n'
                                   '¿Activar escaladores de alta calidad?',
                                   yeslabel='Activar',
                                   nolabel='Desactivar')
            try:
                json_cmd = {
                    "jsonrpc": "2.0",
                    "method": "Settings.SetSettingValue",
                    "params": {"setting": "videoplayer.hqscalers", "value": hq_choice},
                    "id": 1
                }
                xbmc.executeJSONRPC(json.dumps(json_cmd))
                
                status = 'activados' if hq_choice else 'desactivados'
                dialog.notification('Escalado', f'Escaladores HQ {status}', time=2000)
                
            except Exception as e:
                dialog.ok('Error', f'Error configurando escaladores HQ: {str(e)}')
                
    except Exception as e:
        log('Error configurando escalado de video: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error en escalado: %s' % str(e))

def configure_streaming_optimizations():
    """Configura optimizaciones específicas para streaming"""
    try:
        dialog = xbmcgui.Dialog()
        
        info_text = [
            'OPTIMIZACIONES PARA STREAMING',
            '=' * 30,
            '',
            'Configuraciones específicas para mejorar',
            'la experiencia de streaming online.',
            '',
            'Incluye:',
            '• Configuración de buffering optimizada',
            '• Ajustes de red para streaming',
            '• Manejo de conexiones inestables',
            '• Optimización de memoria'
        ]
        
        dialog.textviewer('Información de Streaming', '\n'.join(info_text))
        
        opciones = [
            'Streaming SD (hasta 2 Mbps)',
            'Streaming HD (2-8 Mbps)',
            'Streaming Full HD (8-25 Mbps)',
            'Streaming 4K (25+ Mbps)',
            'Configuración personalizada'
        ]
        
        choice = dialog.select('Optimizar para Streaming', opciones)
        if choice == -1:
            return
            
        streaming_configs = {
            0: {'buffer_mb': 20, 'factor': 2.0, 'description': 'SD'},
            1: {'buffer_mb': 50, 'factor': 3.0, 'description': 'HD'},
            2: {'buffer_mb': 100, 'factor': 4.0, 'description': 'Full HD'},
            3: {'buffer_mb': 200, 'factor': 6.0, 'description': '4K'}
        }
        
        if choice in streaming_configs:
            config = streaming_configs[choice]
            
            # Crear configuración optimizada para streaming
            buffer_size = config['buffer_mb'] * 1048576  # Convert to bytes
            factor = config['factor']
            
            streaming_config = f'''<advancedsettings>
    <network>
        <buffermode>1</buffermode>
        <cachemembuffersize>{buffer_size}</cachemembuffersize>
        <readbufferfactor>{factor}</readbufferfactor>
        <curlclienttimeout>30</curlclienttimeout>
        <curllowspeedtime>20</curllowspeedtime>
        <curlretries>3</curlretries>
    </network>
    <video>
        <memorysize>{buffer_size}</memorysize>
        <readbufferfactor>{factor}</readbufferfactor>
    </video>
    <cache>
        <!-- Configuración optimizada para streaming {config['description']} -->
    </cache>
</advancedsettings>'''
            
            # Aplicar configuración de buffering
            paths = get_kodi_paths()
            config_path = paths.get('advancedsettings', '')
            
            if config_path:
                try:
                    # Backup automático
                    backup_advancedsettings(config_path)
                    
                    # Escribir nueva configuración
                    with open(config_path, 'w', encoding='utf-8') as f:
                        f.write(streaming_config)
                        
                    dialog.ok('Streaming Optimizado',
                             f'Configuración aplicada para {config["description"]}\n\n'
                             f'Buffer: {config["buffer_mb"]} MB\n'
                             f'Factor de lectura: {factor}\n\n'
                             'Reinicia Kodi para aplicar los cambios.')
                    log(f'Streaming optimizado para {config["description"]}')
                    
                except Exception as e:
                    dialog.ok('Error', f'Error aplicando configuración: {str(e)}')
            else:
                dialog.ok('Error', 'No se pudo obtener ruta de configuración')
                
        elif choice == 4:  # Personalizada
            dialog.ok('Configuración Personalizada',
                     'Para configuración personalizada usa:\n\n'
                     'Gestión de Buffering > Configurar buffering avanzado\n\n'
                     'Allí puedes ajustar manualmente:\n'
                     '• Tamaño de buffer\n'
                     '• Factor de lectura\n'
                     '• Configuraciones específicas')
                     
    except Exception as e:
        log('Error configurando streaming: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error en optimización de streaming: %s' % str(e))

def configure_advanced_decoding():
    """Configura opciones avanzadas de decodificación"""
    try:
        dialog = xbmcgui.Dialog()
        
        info_text = [
            'CONFIGURACIÓN AVANZADA DE DECODIFICACIÓN',
            '=' * 40,
            '',
            'Opciones avanzadas para usuarios experimentados:',
            '',
            '• DESENTRELAZADO: Métodos para video entrelazado',
            '• POSTPROCESADO: Filtros de mejora de imagen',
            '• MULTIHILO: Uso de múltiples núcleos CPU',
            '• SKIP LOOP FILTER: Mejora rendimiento H.264',
            '',
            '⚠️ ADVERTENCIA: Cambios incorrectos pueden',
            'causar problemas de reproducción.'
        ]
        
        dialog.textviewer('Decodificación Avanzada', '\n'.join(info_text))
        
        opciones = [
            'Configurar desentrelazado',
            'Configurar postprocesado',
            'Configurar decodificación multihilo',
            'Configurar skip loop filter',
            'Aplicar configuración conservadora',
            'Aplicar configuración agresiva'
        ]
        
        choice = dialog.select('Configuración Avanzada', opciones)
        if choice == -1:
            return
            
        if choice == 0:  # Desentrelazado
            deint_options = ['Auto', 'Desactivado', 'Forzado']
            deint_choice = dialog.select('Método de Desentrelazado', deint_options)
            if deint_choice != -1:
                try:
                    json_cmd = {
                        "jsonrpc": "2.0",
                        "method": "Settings.SetSettingValue",
                        "params": {"setting": "videoplayer.deinterlacemethod", "value": deint_choice},
                        "id": 1
                    }
                    xbmc.executeJSONRPC(json.dumps(json_cmd))
                    dialog.notification('Decodificación', f'Desentrelazado: {deint_options[deint_choice]}', time=2000)
                except Exception as e:
                    dialog.ok('Error', f'Error configurando desentrelazado: {str(e)}')
                    
        elif choice == 1:  # Postprocesado
            post_choice = dialog.yesno('Postprocesado de Video',
                                     'El postprocesado mejora la calidad\n'
                                     'visual pero consume más recursos.\n\n'
                                     '¿Activar postprocesado?',
                                     yeslabel='Activar',
                                     nolabel='Desactivar')
            try:
                json_cmd = {
                    "jsonrpc": "2.0",
                    "method": "Settings.SetSettingValue", 
                    "params": {"setting": "videoplayer.postprocess", "value": post_choice},
                    "id": 1
                }
                xbmc.executeJSONRPC(json.dumps(json_cmd))
                status = 'activado' if post_choice else 'desactivado'
                dialog.notification('Decodificación', f'Postprocesado {status}', time=2000)
            except Exception as e:
                dialog.ok('Error', f'Error configurando postprocesado: {str(e)}')
                
        elif choice == 4:  # Conservadora
            conservative_settings = {
                'videoplayer.deinterlacemethod': 0,  # Auto
                'videoplayer.postprocess': False,
                'videoplayer.multithreaded': True,
                'videoplayer.skiploopfilter': 0  # Enabled
            }
            
            for setting, value in conservative_settings.items():
                try:
                    json_cmd = {
                        "jsonrpc": "2.0",
                        "method": "Settings.SetSettingValue",
                        "params": {"setting": setting, "value": value},
                        "id": 1
                    }
                    xbmc.executeJSONRPC(json.dumps(json_cmd))
                except Exception:
                    pass
                    
            dialog.ok('Configuración Aplicada',
                     'Configuración conservadora aplicada:\n\n'
                     '• Desentrelazado automático\n'
                     '• Postprocesado desactivado\n'
                     '• Multihilo activado\n'
                     '• Loop filter activado')
                     
        elif choice == 5:  # Agresiva
            if dialog.yesno('Configuración Agresiva',
                           '⚠️ ADVERTENCIA ⚠️\n\n'
                           'La configuración agresiva prioriza\n'
                           'el rendimiento sobre la calidad.\n\n'
                           'Puede causar artefactos visuales.\n\n'
                           '¿Continuar?'):
                aggressive_settings = {
                    'videoplayer.deinterlacemethod': 1,  # None
                    'videoplayer.postprocess': False,
                    'videoplayer.multithreaded': True,
                    'videoplayer.skiploopfilter': 2  # All frames
                }
                
                for setting, value in aggressive_settings.items():
                    try:
                        json_cmd = {
                            "jsonrpc": "2.0",
                            "method": "Settings.SetSettingValue",
                            "params": {"setting": setting, "value": value},
                            "id": 1
                        }
                        xbmc.executeJSONRPC(json.dumps(json_cmd))
                    except Exception:
                        pass
                        
                dialog.ok('Configuración Aplicada',
                         'Configuración agresiva aplicada:\n\n'
                         '• Desentrelazado desactivado\n'
                         '• Postprocesado desactivado\n'
                         '• Multihilo activado\n'
                         '• Skip loop filter agresivo\n\n'
                         'Recomendado para hardware limitado.')
                         
    except Exception as e:
        log('Error en configuración avanzada: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error en configuración: %s' % str(e))

def configure_iptv_optimizations():
    """Configura optimizaciones específicas para reproducción IPTV"""
    try:
        dialog = xbmcgui.Dialog()
        
        info_text = [
            'OPTIMIZACIONES ESPECÍFICAS PARA IPTV',
            '=' * 35,
            '',
            'Configuraciones especializadas para streaming IPTV:',
            '',
            '• BUFFERING IPTV: Buffer específico para canales',
            '• NETWORK TIMEOUTS: Timeouts optimizados',
            '• CODEC PRIORITIES: Prioridades de decodificación',
            '• SEEKING: Configuración de búsqueda en stream',
            '• EPG CACHE: Optimización de guía EPG',
            '',
            'Estas optimizaciones mejoran la estabilidad',
            'y fluidez del streaming IPTV.'
        ]
        
        dialog.textviewer('Optimizaciones IPTV', '\n'.join(info_text))
        
        opciones = [
            'Configurar buffering específico IPTV',
            'Optimizar timeouts de red para IPTV',
            'Configurar prioridades de codec',
            'Ajustar configuración de seeking',
            'Optimizar caché de EPG',
            'Corregir sincronización A/V progresiva',
            'Aplicar configuración completa IPTV',
            'Volver'
        ]
        
        choice = dialog.select('Configuración IPTV', opciones)
        
        if choice == 0:  # Buffering específico IPTV
            configure_iptv_buffering()
        elif choice == 1:  # Timeouts de red
            configure_iptv_network_timeouts()
        elif choice == 2:  # Prioridades de codec
            configure_iptv_codec_priorities()
        elif choice == 3:  # Configuración de seeking
            configure_iptv_seeking()
        elif choice == 4:  # Caché de EPG
            configure_iptv_epg_cache()
        elif choice == 5:  # Sincronización A/V
            fix_progressive_av_sync()
        elif choice == 6:  # Configuración completa
            apply_complete_iptv_optimization()
                         
    except Exception as e:
        log('Error en optimizaciones IPTV: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error en configuración IPTV: %s' % str(e))

def configure_iptv_buffering():
    """Configura buffering específico para IPTV"""
    try:
        dialog = xbmcgui.Dialog()
        buffer_size = 0
        factor = 0.0
        
        opciones = [
            'Buffer pequeño (dispositivos limitados)',
            'Buffer medio (recomendado)',
            'Buffer grande (conexiones inestables)',
            'Buffer personalizado'
        ]
        
        choice = dialog.select('Buffer IPTV', opciones)
        
        if choice < 0:
            return
            
        if choice == 0:  # Buffer pequeño
            buffer_size = 20971520  # 20MB
            factor = 2.0
        elif choice == 1:  # Buffer medio
            buffer_size = 52428800  # 50MB
            factor = 3.0
        elif choice == 2:  # Buffer grande
            buffer_size = 104857600  # 100MB
            factor = 4.0
        elif choice == 3:  # Personalizado
            kb = dialog.numeric(0, 'Tamaño buffer (MB)', '50')
            if not kb:
                return
            buffer_size = _safe_int(kb) * 1024 * 1024
            
            factor_str = dialog.numeric(0, 'Factor de lectura (1-8)', '3')
            if not factor_str:
                return
            factor = _safe_float(factor_str)
        
        # Configuraciones específicas IPTV
        iptv_settings = {
            'network': {
                'curlclienttimeout': 30,
                'curllowspeedtime': 20,
                'curlretries': 2
            },
            'cache': {
                'memorysize': buffer_size,
                'readfactor': factor,
                'buffermode': 1  # Todos los archivos de red
            },
            'videoplayer': {
                'adjustrefreshrate': 1,  # Siempre para IPTV
                'pauseafterrefreshchange': 0
            }
        }
        
        try:
            advancedsettings_path = xbmcvfs.translatePath('special://userdata/advancedsettings.xml')
            
            # Crear o modificar advancedsettings.xml
            if xbmcvfs.exists(advancedsettings_path):
                with open(advancedsettings_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                try:
                    root = ET.fromstring(content)
                except Exception:
                    # Si no se puede parsear, crear nuevo
                    root = ET.Element('advancedsettings')
            else:
                # Crear nuevo archivo
                root = ET.Element('advancedsettings')
            
            # Configurar network
            network = root.find('network')
            if network is None:
                network = ET.SubElement(root, 'network')
            
            for key, value in iptv_settings['network'].items():
                elem = network.find(key)
                if elem is None:
                    elem = ET.SubElement(network, key)
                elem.text = str(value)
            
            # Configurar cache
            cache = root.find('cache')
            if cache is None:
                cache = ET.SubElement(root, 'cache')
            
            for key, value in iptv_settings['cache'].items():
                elem = cache.find(key)
                if elem is None:
                    elem = ET.SubElement(cache, key)
                elem.text = str(value)
            
            # Configurar videoplayer
            videoplayer = root.find('videoplayer')
            if videoplayer is None:
                videoplayer = ET.SubElement(root, 'videoplayer')
            
            for key, value in iptv_settings['videoplayer'].items():
                elem = videoplayer.find(key)
                if elem is None:
                    elem = ET.SubElement(videoplayer, key)
                elem.text = str(value)
            
            # Guardar archivo
            tree = ET.ElementTree(root)
            tree.write(advancedsettings_path, encoding='utf-8', xml_declaration=True)
            
            dialog.ok('Buffer IPTV Configurado',
                     f'Configuración aplicada:\n\n'
                     f'• Buffer: {buffer_size // (1024*1024)} MB\n'
                     f'• Factor de lectura: {factor}\n'
                     f'• Timeouts optimizados para IPTV\n'
                     f'• Refresh rate automático activado\n\n'
                     'Reinicia Kodi para aplicar los cambios.')
            
            log(f'Buffer IPTV configurado: {buffer_size // (1024*1024)}MB, factor {factor}')
            
        except Exception as e:
            dialog.ok('Error', f'Error configurando buffer IPTV: {str(e)}')
            
    except Exception as e:
        log('Error en buffering IPTV: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error en buffer IPTV: %s' % str(e))

def configure_iptv_network_timeouts():
    """Configura timeouts de red optimizados para IPTV"""
    try:
        dialog = xbmcgui.Dialog()
        timeout_settings = {}
        
        opciones = [
            'Conexión rápida (timeouts cortos)',
            'Conexión estándar (recomendado)',
            'Conexión lenta/inestable (timeouts largos)',
            'Configuración personalizada'
        ]
        
        choice = dialog.select('Timeouts de Red IPTV', opciones)
        
        if choice < 0:
            return
            
        if choice == 0:  # Rápida
            timeout_settings = {
                'curlclienttimeout': 15,
                'curllowspeedtime': 10,
                'curlretries': 1,
                'curllowspeedlimit': 1000
            }
        elif choice == 1:  # Estándar
            timeout_settings = {
                'curlclienttimeout': 30,
                'curllowspeedtime': 20,
                'curlretries': 2,
                'curllowspeedlimit': 500
            }
        elif choice == 2:  # Lenta
            timeout_settings = {
                'curlclienttimeout': 60,
                'curllowspeedtime': 40,
                'curlretries': 3,
                'curllowspeedlimit': 200
            }
        elif choice == 3:  # Personalizada
            timeout = dialog.numeric(0, 'Timeout cliente (segundos)', '30')
            if not timeout:
                return
            
            lowspeed_time = dialog.numeric(0, 'Tiempo baja velocidad (segundos)', '20')
            if not lowspeed_time:
                return
                
            retries = dialog.numeric(0, 'Número de reintentos', '2')
            if not retries:
                return
            
            timeout_settings = {
                'curlclienttimeout': _safe_int(timeout),
                'curllowspeedtime': _safe_int(lowspeed_time),
                'curlretries': _safe_int(retries),
                'curllowspeedlimit': 500
            }
        
        # Aplicar configuración
        try:
            advancedsettings_path = xbmcvfs.translatePath('special://userdata/advancedsettings.xml')
            
            if xbmcvfs.exists(advancedsettings_path):
                with open(advancedsettings_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                try:
                    root = ET.fromstring(content)
                except Exception:
                    root = ET.Element('advancedsettings')
            else:
                root = ET.Element('advancedsettings')
            
            # Configurar network
            network = root.find('network')
            if network is None:
                network = ET.SubElement(root, 'network')
            
            for key, value in timeout_settings.items():
                elem = network.find(key)
                if elem is None:
                    elem = ET.SubElement(network, key)
                elem.text = str(value)
            
            # Guardar archivo
            tree = ET.ElementTree(root)
            tree.write(advancedsettings_path, encoding='utf-8', xml_declaration=True)
            
            dialog.ok('Timeouts IPTV Configurados',
                     f'Configuración aplicada:\n\n'
                     f'• Client timeout: {timeout_settings["curlclienttimeout"]}s\n'
                     f'• Low speed time: {timeout_settings["curllowspeedtime"]}s\n'
                     f'• Reintentos: {timeout_settings["curlretries"]}\n\n'
                     'Reinicia Kodi para aplicar los cambios.')
            
            log(f'Timeouts IPTV configurados: {timeout_settings}')
            
        except Exception as e:
            dialog.ok('Error', f'Error configurando timeouts: {str(e)}')
            
    except Exception as e:
        log('Error en timeouts IPTV: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error en timeouts: %s' % str(e))

def configure_iptv_codec_priorities():
    """Configura prioridades de codec para IPTV"""
    try:
        dialog = xbmcgui.Dialog()
        priority_msg = ''
        
        info_text = [
            'PRIORIDADES DE CODEC PARA IPTV',
            '=' * 30,
            '',
            'Optimiza el orden de decodificadores para',
            'mejorar la compatibilidad con streams IPTV.',
            '',
            'Configuraciones disponibles:',
            '',
            '• HARDWARE FIRST: Prioriza aceleración HW',
            '• SOFTWARE FIRST: Prioriza decodificación SW',
            '• BALANCED: Equilibrio entre HW y SW',
            '',
            'Hardware es más eficiente, pero Software',
            'es más compatible con formatos variados.'
        ]
        
        dialog.textviewer('Prioridades de Codec', '\n'.join(info_text))
        
        opciones = [
            'Hardware First (más eficiente)',
            'Software First (más compatible)',
            'Balanced (recomendado)',
            'Configuración actual (no cambiar)'
        ]
        
        choice = dialog.select('Prioridad de Codec', opciones)
        
        if choice < 0 or choice == 3:
            return
        
        try:
            # Configurar según la elección
            if choice == 0:  # Hardware First
                json_cmd = {
                    "jsonrpc": "2.0",
                    "method": "Settings.SetSettingValue",
                    "params": {"setting": "videoplayer.useomxplayer", "value": True},
                    "id": 1
                }
                xbmc.executeJSONRPC(json.dumps(json_cmd))
                
                json_cmd = {
                    "jsonrpc": "2.0",
                    "method": "Settings.SetSettingValue",
                    "params": {"setting": "videoplayer.usemediacodec", "value": True},
                    "id": 1
                }
                xbmc.executeJSONRPC(json.dumps(json_cmd))
                
                priority_msg = 'Hardware First configurado'
                
            elif choice == 1:  # Software First
                json_cmd = {
                    "jsonrpc": "2.0",
                    "method": "Settings.SetSettingValue",
                    "params": {"setting": "videoplayer.useomxplayer", "value": False},
                    "id": 1
                }
                xbmc.executeJSONRPC(json.dumps(json_cmd))
                
                priority_msg = 'Software First configurado'
                
            elif choice == 2:  # Balanced
                # Configuración equilibrada usando advancedsettings.xml
                advancedsettings_path = xbmcvfs.translatePath('special://userdata/advancedsettings.xml')
                
                if xbmcvfs.exists(advancedsettings_path):
                    with open(advancedsettings_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                        try:
                            root = ET.fromstring(content)
                        except Exception:
                            root = ET.Element('advancedsettings')
                else:
                    root = ET.Element('advancedsettings')
                
                # Configurar videoplayer para balance
                videoplayer = root.find('videoplayer')
                if videoplayer is None:
                    videoplayer = ET.SubElement(root, 'videoplayer')
                
                # Configuraciones balanceadas
                balanced_settings = {
                    'usevaapi': 'true',
                    'usevdpau': 'true',
                    'usedxva2': 'true',
                    'usemediacodec': 'true',
                    'allowhwaccel': 'true'
                }
                
                for key, value in balanced_settings.items():
                    elem = videoplayer.find(key)
                    if elem is None:
                        elem = ET.SubElement(videoplayer, key)
                    elem.text = value
                
                # Guardar archivo
                tree = ET.ElementTree(root)
                tree.write(advancedsettings_path, encoding='utf-8', xml_declaration=True)
                
                priority_msg = 'Configuración balanceada aplicada'
            
            dialog.ok('Prioridades de Codec',
                     f'{priority_msg}\n\n'
                     'Esta configuración optimiza la\n'
                     'decodificación para streams IPTV.\n\n'
                     'Reinicia Kodi para aplicar los cambios.')
            
            log(f'Prioridades de codec IPTV configuradas: {choice}')
            
        except Exception as e:
            dialog.ok('Error', f'Error configurando prioridades: {str(e)}')
            
    except Exception as e:
        log('Error en prioridades de codec: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error en configuración: %s' % str(e))

def configure_iptv_seeking():
    """Configura búsqueda/seeking optimizada para IPTV"""
    try:
        dialog = xbmcgui.Dialog()
        seeking_settings = {}
        config_name = ''
        
        info_text = [
            'CONFIGURACIÓN DE SEEKING PARA IPTV',
            '=' * 32,
            '',
            'El seeking en streams IPTV en vivo está',
            'limitado, pero para contenido VOD puede',
            'optimizarse para mejor experiencia.',
            '',
            '• TIMESHIFT: Para canales en vivo',
            '• VOD: Para contenido bajo demanda',
            '• CATCHUP: Para contenido programado',
            '',
            'Nota: El seeking en streams en vivo',
            'requiere que el proveedor IPTV lo soporte.'
        ]
        
        dialog.textviewer('Seeking IPTV', '\n'.join(info_text))
        
        opciones = [
            'Optimizar para Live TV (timeshift)',
            'Optimizar para VOD (seeking completo)',
            'Optimizar para Catchup (mixto)',
            'Desactivar seeking (solo reproducción)',
            'Configuración actual (no cambiar)'
        ]
        
        choice = dialog.select('Tipo de Contenido IPTV', opciones)
        
        if choice < 0 or choice == 4:
            return
        
        try:
            advancedsettings_path = xbmcvfs.translatePath('special://userdata/advancedsettings.xml')
            
            if xbmcvfs.exists(advancedsettings_path):
                with open(advancedsettings_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                try:
                    root = ET.fromstring(content)
                except Exception:
                    root = ET.Element('advancedsettings')
            else:
                root = ET.Element('advancedsettings')
            
            # Configurar videoplayer
            videoplayer = root.find('videoplayer')
            if videoplayer is None:
                videoplayer = ET.SubElement(root, 'videoplayer')
            
            if choice == 0:  # Live TV / Timeshift
                seeking_settings = {
                    'seeksteps': '-30,-10,-5,5,10,30',
                    'seekdelay': '750',
                    'ignoreatstart': '10',
                    'ignoreatend': '10'
                }
                config_name = 'Live TV / Timeshift'
                
            elif choice == 1:  # VOD
                seeking_settings = {
                    'seeksteps': '-600,-180,-30,-10,10,30,180,600',
                    'seekdelay': '300',
                    'ignoreatstart': '3',
                    'ignoreatend': '3'
                }
                config_name = 'VOD (completo)'
                
            elif choice == 2:  # Catchup
                seeking_settings = {
                    'seeksteps': '-300,-60,-30,-10,10,30,60,300',
                    'seekdelay': '500',
                    'ignoreatstart': '5',
                    'ignoreatend': '5'
                }
                config_name = 'Catchup (mixto)'
                
            elif choice == 3:  # Desactivar
                seeking_settings = {
                    'seeksteps': '10,30',
                    'seekdelay': '2000',
                    'ignoreatstart': '0',
                    'ignoreatend': '0'
                }
                config_name = 'Seeking desactivado'
            
            for key, value in seeking_settings.items():
                elem = videoplayer.find(key)
                if elem is None:
                    elem = ET.SubElement(videoplayer, key)
                elem.text = str(value)
            
            # Guardar archivo
            tree = ET.ElementTree(root)
            tree.write(advancedsettings_path, encoding='utf-8', xml_declaration=True)
            
            dialog.ok('Seeking IPTV Configurado',
                     f'Configuración aplicada: {config_name}\n\n'
                     'Pasos de seeking y delays optimizados\n'
                     'para el tipo de contenido seleccionado.\n\n'
                     'Reinicia Kodi para aplicar los cambios.')
            
            log(f'Seeking IPTV configurado: {config_name}')
            
        except Exception as e:
            dialog.ok('Error', f'Error configurando seeking: {str(e)}')
            
    except Exception as e:
        log('Error en seeking IPTV: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error en configuración: %s' % str(e))

def configure_iptv_epg_cache():
    """Configura optimización de caché EPG para IPTV"""
    try:
        dialog = xbmcgui.Dialog()
        epg_settings = {}
        config_name = ''
        
        info_text = [
            'OPTIMIZACIÓN DE CACHÉ EPG',
            '=' * 25,
            '',
            'El EPG (Electronic Program Guide) puede',
            'optimizarse para mejor rendimiento con',
            'listas IPTV grandes.',
            '',
            '• TAMAÑO CACHÉ: Memoria para EPG',
            '• TIMEOUT: Tiempo límite de carga',
            '• FRECUENCIA: Intervalo de actualización',
            '',
            'Una configuración optimizada mejora',
            'la carga de la guía de programación.'
        ]
        
        dialog.textviewer('Caché EPG', '\n'.join(info_text))
        
        opciones = [
            'Lista pequeña (< 500 canales)',
            'Lista mediana (500-2000 canales)',
            'Lista grande (> 2000 canales)',
            'Sin EPG (solo canales)',
            'Configuración personalizada'
        ]
        
        choice = dialog.select('Tamaño de Lista IPTV', opciones)
        
        if choice < 0:
            return
        
        try:
            if choice == 0:  # Lista pequeña
                epg_settings = {
                    'epgtimespan': '3',
                    'epgupdatecheckinterval': '300',
                    'epglingertime': '30'
                }
                
            elif choice == 1:  # Lista mediana
                epg_settings = {
                    'epgtimespan': '7',
                    'epgupdatecheckinterval': '600',
                    'epglingertime': '60'
                }
                
            elif choice == 2:  # Lista grande
                epg_settings = {
                    'epgtimespan': '1',
                    'epgupdatecheckinterval': '1800',
                    'epglingertime': '120'
                }
                
            elif choice == 3:  # Sin EPG
                epg_settings = {
                    'epgtimespan': '0',
                    'epgupdatecheckinterval': '0',
                    'epglingertime': '0'
                }
                
            elif choice == 4:  # Personalizada
                timespan = dialog.numeric(0, 'Días de EPG a cargar (0-14)', '7')
                if not timespan:
                    return
                
                interval = dialog.numeric(0, 'Intervalo actualización (segundos)', '600')
                if not interval:
                    return
                
                linger = dialog.numeric(0, 'Tiempo linger (segundos)', '60')
                if not linger:
                    return
                
                epg_settings = {
                    'epgtimespan': timespan,
                    'epgupdatecheckinterval': interval,
                    'epglingertime': linger
                }
            
            # Aplicar configuración usando JSON-RPC
            for setting, value in epg_settings.items():
                json_cmd = {
                    "jsonrpc": "2.0",
                    "method": "Settings.SetSettingValue",
                    "params": {"setting": f"epg.{setting}", "value": _safe_int(value)},
                    "id": 1
                }
                xbmc.executeJSONRPC(json.dumps(json_cmd))
            
            if choice == 3:
                config_name = 'EPG desactivado'
            else:
                config_name = f'EPG optimizado ({epg_settings["epgtimespan"]} días)'
            
            dialog.ok('Caché EPG Configurado',
                     f'Configuración aplicada: {config_name}\n\n'
                     f'• Días de EPG: {epg_settings["epgtimespan"]}\n'
                     f'• Intervalo: {epg_settings["epgupdatecheckinterval"]}s\n'
                     f'• Linger time: {epg_settings["epglingertime"]}s\n\n'
                     'Los cambios se aplicarán inmediatamente.')
            
            log(f'EPG IPTV configurado: {epg_settings}')
            
        except Exception as e:
            dialog.ok('Error', f'Error configurando EPG: {str(e)}')
            
    except Exception as e:
        log('Error en EPG IPTV: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error en configuración EPG: %s' % str(e))

def fix_progressive_av_sync():
    """Corrige problemas de sincronización A/V progresiva en streaming IPTV"""
    try:
        dialog = xbmcgui.Dialog()
        
        info_text = [
            'CORRECCIÓN DE SINCRONIZACIÓN A/V PROGRESIVA',
            '=' * 43,
            '',
            'Este problema ocurre cuando el audio se adelanta',
            'gradualmente al video durante la reproducción.',
            '',
            'Soluciones disponibles:',
            '',
            '• MÉTODO 1: Configuración de timestamps',
            '• MÉTODO 2: Ajuste de buffers A/V separados',
            '• MÉTODO 3: Corrección de drift de reloj',
            '• MÉTODO 4: Configuración conservadora completa',
            '',
            '⚠️ Se recomienda probar los métodos en orden',
            'hasta encontrar el que funcione mejor.'
        ]
        
        dialog.textviewer('Sincronización A/V Progresiva', '\n'.join(info_text))
        
        opciones = [
            'Método 1: Configurar timestamps A/V',
            'Método 2: Buffers A/V separados',
            'Método 3: Corrección de drift de reloj',
            'Método 4: Configuración conservadora completa',
            'Diagnosticar problema actual',
            'Volver'
        ]
        
        choice = dialog.select('Corrección A/V Progresiva', opciones)
        
        if choice == 0:  # Método 1: Timestamps
            fix_av_timestamps()
        elif choice == 1:  # Método 2: Buffers separados
            fix_av_separate_buffers()
        elif choice == 2:  # Método 3: Drift de reloj
            fix_av_clock_drift()
        elif choice == 3:  # Método 4: Configuración conservadora
            apply_conservative_av_config()
        elif choice == 4:  # Diagnóstico
            diagnose_av_sync_problem()
                         
    except Exception as e:
        log('Error en corrección A/V: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error en sincronización A/V: %s' % str(e))

def fix_av_timestamps():
    """Método 1: Configura timestamps A/V para evitar drift progresivo"""
    try:
        dialog = xbmcgui.Dialog()
        
        # Configuración para corregir timestamps
        advancedsettings_path = xbmcvfs.translatePath('special://userdata/advancedsettings.xml')
        
        if xbmcvfs.exists(advancedsettings_path):
            with open(advancedsettings_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            try:
                root = ET.fromstring(content)
            except Exception:
                root = ET.Element('advancedsettings')
        else:
            root = ET.Element('advancedsettings')
        
        # Configurar videoplayer para timestamps A/V
        videoplayer = root.find('videoplayer')
        if videoplayer is None:
            videoplayer = ET.SubElement(root, 'videoplayer')
        
        # Configuraciones específicas para evitar drift A/V
        timestamp_settings = {
            'usedisplayasclock': 'true',  # Usar display como referencia de tiempo
            'synctype': '2',  # Sincronización por video
            'maxspeedadjust': '5.0',  # Máximo ajuste de velocidad
            'resamplequality': '1',  # Calidad de resample medio
            'stereoscopicplaybackmode': '0',  # Desactivar 3D
            'allowhwaccel': 'true',
            'adjustrefreshrate': '1'  # Ajustar refresh rate
        }
        
        for key, value in timestamp_settings.items():
            elem = videoplayer.find(key)
            if elem is None:
                elem = ET.SubElement(videoplayer, key)
            elem.text = value
        
        # Configurar audio específicamente
        audio = root.find('audio')
        if audio is None:
            audio = ET.SubElement(root, 'audio')
        
        audio_settings = {
            'resample': '48000',  # Forzar resample a 48kHz
            'stereoupmix': 'false',  # Desactivar upmix
            'normalizelevels': 'false',  # Desactivar normalización
            'guisoundmode': '1',  # Solo sonidos GUI básicos
        }
        
        for key, value in audio_settings.items():
            elem = audio.find(key)
            if elem is None:
                elem = ET.SubElement(audio, key)
            elem.text = value
        
        # Configurar cache específico para A/V sync
        cache = root.find('cache')
        if cache is None:
            cache = ET.SubElement(root, 'cache')
        
        cache_settings = {
            'memorysize': '41943040',  # 40MB - buffer más pequeño
            'readfactor': '2.0',  # Factor conservador
            'buffermode': '1'  # Solo archivos de red
        }
        
        for key, value in cache_settings.items():
            elem = cache.find(key)
            if elem is None:
                elem = ET.SubElement(cache, key)
            elem.text = value
        
        # Guardar archivo
        tree = ET.ElementTree(root)
        tree.write(advancedsettings_path, encoding='utf-8', xml_declaration=True)
        
        dialog.ok('Timestamps A/V Configurados',
                 'Configuración aplicada:\n\n'
                 '✓ Display como referencia de tiempo\n'
                 '✓ Sincronización por video\n'
                 '✓ Resample de audio a 48kHz\n'
                 '✓ Buffer conservador (40MB)\n'
                 '✓ Refresh rate automático\n\n'
                 '🔄 REINICIA KODI para aplicar los cambios.\n\n'
                 'Prueba reproducir contenido IPTV para\n'
                 'verificar si se corrige la desincronización.')
        
        log('Configuración timestamps A/V aplicada')
        
    except Exception as e:
        xbmcgui.Dialog().ok('Error', f'Error configurando timestamps: {str(e)}')

def fix_av_separate_buffers():
    """Método 2: Configura buffers A/V separados"""
    try:
        dialog = xbmcgui.Dialog()
        
        # Usar JSON-RPC para configurar buffers separados
        audio_settings = [
            ('audiooutput.audiodevice', 'ALSA:default'),
            ('audiooutput.channels', 2),  # Estéreo
            ('audiooutput.samplerate', 48000),  # 48kHz fijo
            ('audiooutput.processquality', 30),  # Calidad media
        ]
        
        video_settings = [
            ('videoplayer.rendermethod', 'AUTO'),
            ('videoplayer.processingquality', 3),  # Calidad media
            ('videoplayer.usedisplayasclock', True),
        ]
        
        # Aplicar configuraciones de audio
        for setting, value in audio_settings:
            try:
                json_cmd = {
                    "jsonrpc": "2.0",
                    "method": "Settings.SetSettingValue",
                    "params": {"setting": setting, "value": value},
                    "id": 1
                }
                xbmc.executeJSONRPC(json.dumps(json_cmd))
            except:
                pass  # Continuar si alguna configuración falla
        
        # Aplicar configuraciones de video
        for setting, value in video_settings:
            try:
                json_cmd = {
                    "jsonrpc": "2.0",
                    "method": "Settings.SetSettingValue",
                    "params": {"setting": setting, "value": value},
                    "id": 1
                }
                xbmc.executeJSONRPC(json.dumps(json_cmd))
            except:
                pass
        
        # Configurar advancedsettings.xml para buffers separados
        advancedsettings_path = xbmcvfs.translatePath('special://userdata/advancedsettings.xml')
        
        if xbmcvfs.exists(advancedsettings_path):
            with open(advancedsettings_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            try:
                root = ET.fromstring(content)
            except Exception:
                root = ET.Element('advancedsettings')
        else:
            root = ET.Element('advancedsettings')
        
        # Configurar buffers separados
        cache = root.find('cache')
        if cache is None:
            cache = ET.SubElement(root, 'cache')
        
        separate_buffer_settings = {
            'memorysize': '62914560',  # 60MB total
            'readfactor': '2.5',  # Factor moderado
            'buffermode': '1',  # Solo red
            'cachemembuffersize': '31457280'  # 30MB para buffer memoria
        }
        
        for key, value in separate_buffer_settings.items():
            elem = cache.find(key)
            if elem is None:
                elem = ET.SubElement(cache, key)
            elem.text = value
        
        # Configuración específica para A/V
        videoplayer = root.find('videoplayer')
        if videoplayer is None:
            videoplayer = ET.SubElement(root, 'videoplayer')
        
        av_buffer_settings = {
            'usedisplayasclock': 'true',
            'synctype': '1',  # Sincronización por audio
            'maxspeedadjust': '3.0',
            'resamplequality': '2'  # Calidad alta de resample
        }
        
        for key, value in av_buffer_settings.items():
            elem = videoplayer.find(key)
            if elem is None:
                elem = ET.SubElement(videoplayer, key)
            elem.text = value
        
        # Guardar archivo
        tree = ET.ElementTree(root)
        tree.write(advancedsettings_path, encoding='utf-8', xml_declaration=True)
        
        dialog.ok('Buffers A/V Separados Configurados',
                 'Configuración aplicada:\n\n'
                 '✓ Buffers A/V independientes\n'
                 '✓ Audio: 48kHz estéreo fijo\n'
                 '✓ Video: Display como reloj\n'
                 '✓ Sincronización por audio\n'
                 '✓ Buffer total: 60MB (30MB memoria)\n\n'
                 '🔄 REINICIA KODI para aplicar los cambios.\n\n'
                 'Esta configuración separa el procesamiento\n'
                 'de audio y video para evitar drift.')
        
        log('Configuración buffers A/V separados aplicada')
        
    except Exception as e:
        xbmcgui.Dialog().ok('Error', f'Error configurando buffers separados: {str(e)}')

def fix_av_clock_drift():
    """Método 3: Corrige drift de reloj del sistema"""
    try:
        dialog = xbmcgui.Dialog()
        
        info_text = [
            'CORRECCIÓN DE DRIFT DE RELOJ',
            '=' * 28,
            '',
            'El drift de reloj ocurre cuando el reloj del',
            'sistema no está perfectamente sincronizado.',
            '',
            'Configuraciones disponibles:',
            '',
            '• CONSERVADOR: Ajustes mínimos (recomendado)',
            '• MODERADO: Ajustes equilibrados',
            '• AGRESIVO: Máxima corrección (último recurso)',
            '',
            '⚠️ Empezar con CONSERVADOR y subir si es necesario.'
        ]
        
        dialog.textviewer('Drift de Reloj', '\n'.join(info_text))
        
        opciones = [
            'Conservador (ajustes mínimos)',
            'Moderado (equilibrado)',
            'Agresivo (máxima corrección)',
            'Volver'
        ]
        
        choice = dialog.select('Nivel de Corrección', opciones)

        if choice < 0 or choice == 3:
            return

        # Valores por defecto
        max_adjust = '5.0'
        resample_quality = '2'
        sync_type = '2'

        # Configurar según el nivel elegido
        if choice == 0:  # Conservador
            max_adjust = '2.0'
            resample_quality = '1'
            sync_type = '2'  # Por video

        elif choice == 1:  # Moderado
            max_adjust = '5.0'
            resample_quality = '2'
            sync_type = '1'  # Por audio

        elif choice == 2:  # Agresivo
            max_adjust = '10.0'
            resample_quality = '3'
            sync_type = '0'  # Automático
        
        # Aplicar configuración
        advancedsettings_path = xbmcvfs.translatePath('special://userdata/advancedsettings.xml')
        
        if xbmcvfs.exists(advancedsettings_path):
            with open(advancedsettings_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            try:
                root = ET.fromstring(content)
            except Exception:
                root = ET.Element('advancedsettings')
        else:
            root = ET.Element('advancedsettings')
        
        # Configurar videoplayer para corrección de drift
        videoplayer = root.find('videoplayer')
        if videoplayer is None:
            videoplayer = ET.SubElement(root, 'videoplayer')
        
        drift_settings = {
            'usedisplayasclock': 'true',
            'synctype': sync_type,
            'maxspeedadjust': max_adjust,
            'resamplequality': resample_quality,
            'adjustrefreshrate': '1',
            'pauseafterrefreshchange': '0'
        }
        
        for key, value in drift_settings.items():
            elem = videoplayer.find(key)
            if elem is None:
                elem = ET.SubElement(videoplayer, key)
            elem.text = value
        
        # Configurar audio para drift
        audio = root.find('audio')
        if audio is None:
            audio = ET.SubElement(root, 'audio')
        
        audio_drift_settings = {
            'resample': '48000',
            'stereoupmix': 'false',
            'maintainoriginalvolume': 'true'
        }
        
        for key, value in audio_drift_settings.items():
            elem = audio.find(key)
            if elem is None:
                elem = ET.SubElement(audio, key)
            elem.text = value
        
        # Guardar archivo
        tree = ET.ElementTree(root)
        tree.write(advancedsettings_path, encoding='utf-8', xml_declaration=True)
        
        level_name = ['Conservador', 'Moderado', 'Agresivo'][choice]
        
        dialog.ok('Corrección de Drift Configurada',
                 f'Configuración aplicada: {level_name}\n\n'
                 f'✓ Ajuste máximo de velocidad: {max_adjust}%\n'
                 f'✓ Calidad de resample: {resample_quality}\n'
                 f'✓ Tipo de sincronización: {sync_type}\n'
                 '✓ Display como reloj maestro\n'
                 '✓ Refresh rate automático\n\n'
                 '🔄 REINICIA KODI para aplicar los cambios.\n\n'
                 'Si el problema persiste, prueba el\n'
                 'siguiente nivel de corrección.')
        
        log(f'Configuración drift de reloj aplicada: {level_name}')
        
    except Exception as e:
        xbmcgui.Dialog().ok('Error', f'Error configurando drift de reloj: {str(e)}')

def apply_conservative_av_config():
    """Método 4: Aplica configuración conservadora completa para A/V sync"""
    try:
        dialog = xbmcgui.Dialog()
        
        if not dialog.yesno('Configuración Conservadora Completa',
                           'Esta configuración aplicará ajustes muy\n'
                           'conservadores que sacrifican algo de calidad\n'
                           'por estabilidad de sincronización A/V.\n\n'
                           '⚠️ Se recomienda como último recurso.\n\n'
                           '¿Continuar?',
                           yeslabel='Aplicar',
                           nolabel='Cancelar'):
            return
        
        # Configuración ultra conservadora
        advancedsettings_path = xbmcvfs.translatePath('special://userdata/advancedsettings.xml')
        
        root = ET.Element('advancedsettings')
        
        # Cache ultra conservador
        cache = ET.SubElement(root, 'cache')
        cache_settings = {
            'memorysize': '20971520',  # Solo 20MB
            'readfactor': '1.5',  # Factor muy bajo
            'buffermode': '0',  # Todos los archivos
            'cachemembuffersize': '0'  # Sin buffer en memoria
        }
        
        for key, value in cache_settings.items():
            elem = ET.SubElement(cache, key)
            elem.text = value
        
        # Video ultra conservador
        videoplayer = ET.SubElement(root, 'videoplayer')
        video_settings = {
            'usedisplayasclock': 'false',  # No usar display como reloj
            'synctype': '2',  # Sincronización por video
            'maxspeedadjust': '1.0',  # Ajuste mínimo
            'resamplequality': '0',  # Calidad mínima
            'adjustrefreshrate': '0',  # No ajustar refresh rate
            'pauseafterrefreshchange': '2000',
            'allowhwaccel': 'false',  # Sin aceleración HW
            'usevaapi': 'false',
            'usevdpau': 'false',
            'usedxva2': 'false',
            'usemediacodec': 'false'
        }
        
        for key, value in video_settings.items():
            elem = ET.SubElement(videoplayer, key)
            elem.text = value
        
        # Audio ultra conservador
        audio = ET.SubElement(root, 'audio')
        audio_settings = {
            'resample': '44100',  # 44.1kHz estándar
            'stereoupmix': 'false',
            'normalizelevels': 'false',
            'maintainoriginalvolume': 'true',
            'guisoundmode': '0'  # Sin sonidos GUI
        }
        
        for key, value in audio_settings.items():
            elem = ET.SubElement(audio, key)
            elem.text = value
        
        # Network conservador
        network = ET.SubElement(root, 'network')
        network_settings = {
            'curlclienttimeout': '10',  # Timeout corto
            'curllowspeedtime': '5',
            'curlretries': '1',
            'cachemembuffersize': '0'
        }
        
        for key, value in network_settings.items():
            elem = ET.SubElement(network, key)
            elem.text = value
        
        # Guardar archivo
        tree = ET.ElementTree(root)
        tree.write(advancedsettings_path, encoding='utf-8', xml_declaration=True)
        
        # También configurar ajustes del sistema
        system_settings = [
            ('audiooutput.samplerate', 44100),
            ('audiooutput.channels', 2),
            ('videoplayer.rendermethod', 'SOFTWARE'),
            ('videoplayer.processingquality', 1)
        ]
        
        for setting, value in system_settings:
            try:
                json_cmd = {
                    "jsonrpc": "2.0",
                    "method": "Settings.SetSettingValue",
                    "params": {"setting": setting, "value": value},
                    "id": 1
                }
                xbmc.executeJSONRPC(json.dumps(json_cmd))
            except:
                pass
        
        dialog.ok('Configuración Conservadora Aplicada',
                 'Configuración ultra conservadora aplicada:\n\n'
                 '✓ Buffer: Solo 20MB sin HW\n'
                 '✓ Audio: 44.1kHz estéreo básico\n'
                 '✓ Video: Software rendering\n'
                 '✓ Sin aceleración por hardware\n'
                 '✓ Sincronización básica por video\n'
                 '✓ Timeouts de red cortos\n\n'
                 '🔄 REINICIA KODI INMEDIATAMENTE.\n\n'
                 '⚠️ Esta configuración reduce la calidad\n'
                 'pero debería eliminar problemas de A/V sync.')
        
        log('Configuración conservadora completa aplicada')
        
    except Exception as e:
        xbmcgui.Dialog().ok('Error', f'Error aplicando configuración conservadora: {str(e)}')

def diagnose_av_sync_problem():
    """Diagnostica el problema específico de sincronización A/V"""
    try:
        dialog = xbmcgui.Dialog()
        
        diagnostic_info = []
        diagnostic_info.append('DIAGNÓSTICO DE SINCRONIZACIÓN A/V')
        diagnostic_info.append('=' * 34)
        diagnostic_info.append('')
        
        # Obtener información del sistema
        try:
            # Información de audio
            json_cmd = {
                "jsonrpc": "2.0",
                "method": "Settings.GetSettingValue",
                "params": {"setting": "audiooutput.samplerate"},
                "id": 1
            }
            response = xbmc.executeJSONRPC(json.dumps(json_cmd))
            import json as json_mod
            result = json_mod.loads(response)
            audio_samplerate = result.get('result', {}).get('value', 'N/A')
            
            json_cmd['params']['setting'] = 'audiooutput.channels'
            response = xbmc.executeJSONRPC(json.dumps(json_cmd))
            result = json_mod.loads(response)
            audio_channels = result.get('result', {}).get('value', 'N/A')
            
            # Información de video
            json_cmd['params']['setting'] = 'videoplayer.rendermethod'
            response = xbmc.executeJSONRPC(json.dumps(json_cmd))
            result = json_mod.loads(response)
            video_render = result.get('result', {}).get('value', 'N/A')
            
            diagnostic_info.append(f'Audio Sample Rate: {audio_samplerate} Hz')
            diagnostic_info.append(f'Audio Channels: {audio_channels}')
            diagnostic_info.append(f'Video Render: {video_render}')
            diagnostic_info.append('')
            
        except:
            diagnostic_info.append('No se pudo obtener información del sistema')
            diagnostic_info.append('')
        
        # Verificar advancedsettings.xml
        advancedsettings_path = xbmcvfs.translatePath('special://userdata/advancedsettings.xml')
        
        if xbmcvfs.exists(advancedsettings_path):
            try:
                with open(advancedsettings_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                try:
                    root = ET.fromstring(content)
                except Exception:
                    root = ET.Element('advancedsettings')
                
                diagnostic_info.append('CONFIGURACIÓN ACTUAL:')
                diagnostic_info.append('-' * 20)
                
                # Verificar cache
                cache = root.find('cache')
                if cache is not None:
                    memory = cache.find('memorysize')
                    factor = cache.find('readfactor')
                    mode = cache.find('buffermode')
                    
                    if memory is not None:
                        try:
                            mem_val = memory.text.strip() if memory.text else ''
                            mem_mb = _safe_int(mem_val) // (1024*1024)
                            diagnostic_info.append(f'Buffer: {mem_mb} MB')
                        except Exception:
                            diagnostic_info.append(f'Buffer: {memory.text or "N/A"}')
                    if factor is not None:
                        diagnostic_info.append(f'Read Factor: {factor.text}')
                    if mode is not None:
                        diagnostic_info.append(f'Buffer Mode: {mode.text}')
                
                # Verificar videoplayer
                videoplayer = root.find('videoplayer')
                if videoplayer is not None:
                    usedisplay = videoplayer.find('usedisplayasclock')
                    synctype = videoplayer.find('synctype')
                    maxadjust = videoplayer.find('maxspeedadjust')
                    
                    if usedisplay is not None:
                        diagnostic_info.append(f'Use Display Clock: {usedisplay.text}')
                    if synctype is not None:
                        sync_types = {'0': 'Auto', '1': 'Audio', '2': 'Video'}
                        st = synctype.text if synctype.text is not None else ''
                        diagnostic_info.append(f'Sync Type: {sync_types.get(st, st)}')
                    if maxadjust is not None:
                        diagnostic_info.append(f'Max Speed Adjust: {maxadjust.text}%')
                
                diagnostic_info.append('')
                
            except Exception as e:
                diagnostic_info.append(f'Error leyendo advancedsettings.xml: {str(e)}')
                diagnostic_info.append('')
        else:
            diagnostic_info.append('No hay advancedsettings.xml configurado')
            diagnostic_info.append('')
        
        # Recomendaciones
        diagnostic_info.append('RECOMENDACIONES:')
        diagnostic_info.append('-' * 15)
        diagnostic_info.append('')
        diagnostic_info.append('Para audio que se adelanta progresivamente:')
        diagnostic_info.append('')
        diagnostic_info.append('1. MÉTODO 1: Probar timestamps A/V')
        diagnostic_info.append('   - Configura el display como reloj maestro')
        diagnostic_info.append('   - Fuerza resample de audio a 48kHz')
        diagnostic_info.append('')
        diagnostic_info.append('2. MÉTODO 2: Si persiste, usar buffers separados')
        diagnostic_info.append('   - Separa procesamiento A/V')
        diagnostic_info.append('   - Sincronización por audio')
        diagnostic_info.append('')
        diagnostic_info.append('3. MÉTODO 3: Corrección de drift de reloj')
        diagnostic_info.append('   - Ajustes progresivos de velocidad')
        diagnostic_info.append('   - Empezar con nivel conservador')
        diagnostic_info.append('')
        diagnostic_info.append('4. MÉTODO 4: Configuración conservadora')
        diagnostic_info.append('   - Último recurso, sacrifica calidad')
        diagnostic_info.append('   - Desactiva aceleración HW')
        
        dialog.textviewer('Diagnóstico A/V Sync', '\n'.join(diagnostic_info))
        
    except Exception as e:
        xbmcgui.Dialog().ok('Error', f'Error en diagnóstico: {str(e)}')

def apply_complete_iptv_optimization():
    """Aplica una configuración completa optimizada para IPTV"""
    try:
        dialog = xbmcgui.Dialog()
        
        info_text = [
            'CONFIGURACIÓN COMPLETA IPTV',
            '=' * 27,
            '',
            'Esta opción aplicará un conjunto completo',
            'de optimizaciones para IPTV:',
            '',
            '✓ Buffer optimizado (50MB, factor 3.0)',
            '✓ Timeouts de red estándar',
            '✓ Prioridades de codec balanceadas',
            '✓ Seeking optimizado para Live TV',
            '✓ EPG configurado para listas medianas',
            '✓ Refresh rate automático',
            '',
            '⚠️ Esto sobrescribirá configuraciones',
            'existentes en advancedsettings.xml'
        ]
        
        if not dialog.yesno('Configuración Completa IPTV',
                           '\n'.join(info_text),
                           yeslabel='Aplicar',
                           nolabel='Cancelar'):
            return
        
        try:
            # Crear configuración completa
            root = ET.Element('advancedsettings')
            
            # Network settings
            network = ET.SubElement(root, 'network')
            network_settings = {
                'curlclienttimeout': '30',
                'curllowspeedtime': '20',
                'curlretries': '2',
                'curllowspeedlimit': '500'
            }
            
            for key, value in network_settings.items():
                elem = ET.SubElement(network, key)
                elem.text = value
            
            # Cache settings
            cache = ET.SubElement(root, 'cache')
            cache_settings = {
                'memorysize': '52428800',  # 50MB
                'readfactor': '3.0',
                'buffermode': '1'  # Todos los archivos de red
            }
            
            for key, value in cache_settings.items():
                elem = ET.SubElement(cache, key)
                elem.text = value
            
            # Videoplayer settings
            videoplayer = ET.SubElement(root, 'videoplayer')
            videoplayer_settings = {
                'adjustrefreshrate': '1',
                'pauseafterrefreshchange': '0',
                'seeksteps': '-30,-10,-5,5,10,30',
                'seekdelay': '750',
                'ignoreatstart': '10',
                'ignoreatend': '10',
                'usevaapi': 'true',
                'usevdpau': 'true',
                'usedxva2': 'true',
                'usemediacodec': 'true',
                'allowhwaccel': 'true'
            }
            
            for key, value in videoplayer_settings.items():
                elem = ET.SubElement(videoplayer, key)
                elem.text = value
            
            # Guardar archivo
            advancedsettings_path = xbmcvfs.translatePath('special://userdata/advancedsettings.xml')
            tree = ET.ElementTree(root)
            tree.write(advancedsettings_path, encoding='utf-8', xml_declaration=True)
            
            # Configurar EPG usando JSON-RPC
            epg_settings = {
                'epgtimespan': 7,
                'epgupdatecheckinterval': 600,
                'epglingertime': 60
            }
            
            for setting, value in epg_settings.items():
                json_cmd = {
                    "jsonrpc": "2.0",
                    "method": "Settings.SetSettingValue",
                    "params": {"setting": f"epg.{setting}", "value": value},
                    "id": 1
                }
                xbmc.executeJSONRPC(json.dumps(json_cmd))
            
            dialog.ok('Configuración IPTV Completa Aplicada',
                     'Optimizaciones aplicadas exitosamente:\n\n'
                     '✓ Buffer: 50MB con factor 3.0\n'
                     '✓ Timeouts de red optimizados\n'
                     '✓ Codecs balanceados (HW + SW)\n'
                     '✓ Seeking para Live TV\n'
                     '✓ EPG para listas medianas\n'
                     '✓ Refresh rate automático\n\n'
                     '🔄 REINICIA KODI para aplicar todos\n'
                     'los cambios correctamente.')
            
            log('Configuración completa IPTV aplicada exitosamente')
            
        except Exception as e:
            dialog.ok('Error', f'Error aplicando configuración completa: {str(e)}')
            
    except Exception as e:
        log('Error en configuración completa IPTV: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error en configuración: %s' % str(e))

def reset_video_settings():
    """Resetea todas las configuraciones de video a valores predeterminados"""
    try:
        dialog = xbmcgui.Dialog()
        
        if not dialog.yesno('Resetear Configuraciones de Video',
                           '⚠️ ADVERTENCIA ⚠️\n\n'
                           'Esto restaurará TODAS las configuraciones\n'
                           'de video a los valores predeterminados:\n\n'
                           '• Aceleración por hardware\n'
                           '• Métodos de escalado\n'
                           '• Refresh rate\n'
                           '• Decodificación\n'
                           '• Audio\n\n'
                           '¿Continuar?'):
            return
            
        # Configuraciones predeterminadas de video
        default_video_settings = {
            # Hardware acceleration
            'videoplayer.usevaapih264': True,
            'videoplayer.usevaapihevc': True,
            'videoplayer.usevaapiav1': True,
            'videoplayer.usevdpau': False,
            'videoplayer.usedxva2': False,
            'videoplayer.useamcodecav1': False,
            'videoplayer.useamcodech264': False,
            
            # Video playback
            'videoplayer.adjustrefreshrate': 0,
            'videoplayer.usedisplayasclock': True,
            'videoplayer.synctype': 1,
            'videoplayer.deinterlacemethod': 0,
            'videoplayer.scalingmethod': 1,
            'videoplayer.hqscalers': False,
            'videoplayer.postprocess': False,
            'videoplayer.multithreaded': True,
            'videoplayer.skiploopfilter': 0,
            
            # Audio
            'audiooutput.normalizelevels': False,
            'audiooutput.ac3passthrough': False,
            'audiooutput.dtspassthrough': False,
            'audiooutput.samplerate': 0
        }
        
        applied_count = 0
        failed_count = 0
        
        for setting, value in default_video_settings.items():
            try:
                json_cmd = {
                    "jsonrpc": "2.0",
                    "method": "Settings.SetSettingValue",
                    "params": {"setting": setting, "value": value},
                    "id": 1
                }
                xbmc.executeJSONRPC(json.dumps(json_cmd))
                applied_count += 1
            except Exception as e:
                failed_count += 1
                log(f'Error reseteando {setting}: {str(e)}')
                
        # Mostrar resumen
        summary = [
            'RESET DE CONFIGURACIONES COMPLETADO',
            '=' * 35,
            '',
            f'✓ Configuraciones aplicadas: {applied_count}',
            f'✗ Errores: {failed_count}',
            '',
            'Configuraciones restauradas:',
            '• Aceleración por hardware: Auto',
            '• Refresh rate: Desactivado',
            '• Escalado: Lanczos',
            '• Desentrelazado: Auto',
            '• Audio: Valores predeterminados',
            '',
            'RECOMENDACIÓN:',
            '• Reinicia Kodi para aplicar cambios',
            '• Reconfigura según tus preferencias'
        ]
        
        dialog.textviewer('Reset Completado', '\n'.join(summary))
        
        # Preguntar si reiniciar
        if dialog.yesno('Reiniciar Kodi',
                       'Se recomienda reiniciar Kodi para aplicar\n'
                       'todos los cambios correctamente.\n\n'
                       '¿Reiniciar ahora?',
                       yeslabel='Reiniciar',
                       nolabel='Más tarde'):
            xbmc.executebuiltin('RestartApp')
            
        log('Reset de configuraciones de video completado')
        
    except Exception as e:
        log('Error reseteando configuraciones de video: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error durante el reset: %s' % str(e))

def perform_speed_test(timeout=15, urls=None):
    """Realiza una prueba de velocidad con URLs de test específicas"""
    """Realiza una descarga corta para estimar velocidad (Mbps)"""
    try:
        # Archivos públicos (fallback si falla el primero)
        urls = urls or [
            'https://download.thinkbroadband.com/10MB.zip',  # UK (fiable)
            'https://speedtest-fra1.digitalocean.com/10mb.test',  # DE (DO FRA1)
            'https://speedtest-nyc3.digitalocean.com/10mb.test',  # US (DO NYC3)
            'https://speedtest-sgp1.digitalocean.com/10mb.test',  # SG (DO SGP1)
            'https://speed.hetzner.de/10MB.bin',  # DE (Hetzner)
            'https://proof.ovh.net/files/10Mb.dat'  # OVH EU (corrigido)
        ]
        size_bytes = None
        total_read = 0
        start = time.time()
        for url in urls:
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Kodi-SpeedTest'})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    size_bytes = _safe_int(resp.headers.get('Content-Length', '0')) or None
                    chunk = resp.read(1024 * 64)
                    total_read += len(chunk)
                    # Leer ~2MB para estimar
                    while total_read < 2 * 1024 * 1024:
                        chunk = resp.read(1024 * 64)
                        if not chunk:
                            break
                        total_read += len(chunk)
                break
            except Exception:
                continue
        elapsed = max(0.001, time.time() - start)
        mbps = (total_read * 8) / (elapsed * 1_000_000)  # megabits por segundo
        return round(mbps, 2), total_read, elapsed
    except Exception as e:
        log('Error en perform_speed_test: %s' % str(e))
        return 0.0, 0, 0.0
    """Realiza una descarga corta para estimar velocidad (Mbps)"""
    try:
        # Archivos públicos (fallback si falla el primero)
        urls = urls or [
            'https://download.thinkbroadband.com/10MB.zip',  # UK (fiable)
            'https://speedtest-fra1.digitalocean.com/10mb.test',  # DE (DO FRA1)
            'https://speedtest-nyc3.digitalocean.com/10mb.test',  # US (DO NYC3)
            'https://speedtest-sgp1.digitalocean.com/10mb.test',  # SG (DO SGP1)
            'https://speed.hetzner.de/10MB.bin',  # DE (Hetzner)
            'https://proof.ovh.net/files/10Mb.dat'  # OVH EU (corrigido)
        ]
        size_bytes = None
        total_read = 0
        start = time.time()
        for url in urls:
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Kodi-SpeedTest'})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    size_bytes = _safe_int(resp.headers.get('Content-Length', '0')) or None
                    chunk = resp.read(1024 * 64)
                    total_read += len(chunk)
                    # Leer ~2MB para estimar
                    while total_read < 2 * 1024 * 1024:
                        chunk = resp.read(1024 * 64)
                        if not chunk:
                            break
                        total_read += len(chunk)
                break
            except Exception:
                continue
        elapsed = max(0.001, time.time() - start)
        mbps = (total_read * 8) / (elapsed * 1_000_000)  # megabits por segundo
        return round(mbps, 2), total_read, elapsed
    except Exception as e:
        log('Error en perform_speed_test: %s' % str(e))
        return 0.0, 0, 0.0

def speed_test_and_recommend(config_path, urls=None):
    """Ejecuta test de velocidad y propone una configuración de buffering"""
    try:
        dialog = xbmcgui.Dialog()
        dialog.notification('Aspirando Kodi', 'Iniciando test de velocidad...', time=3000)
        mbps, read_bytes, elapsed = perform_speed_test(urls=urls)
        if mbps <= 0:
            dialog.ok('Test de velocidad', 'No se pudo medir la velocidad. Revisa tu conexión.')
            return
        
        # Verificar si hay readbufferfactor personalizado
        custom_factor = get_user_readbufferfactor()
        is_android = xbmc.getCondVisibility('system.platform.android')
        android_optimizations = apply_android_optimizations()
        
        # Heurística: Android usa valores conservadores para evitar desincronización A/V
        if is_android and android_optimizations:
            android_limit = get_android_buffer_limit()
            if mbps <= 5:
                buf = 24 * 1024 * 1024; factor = custom_factor or 2.2
            elif mbps <= 20:
                buf = 48 * 1024 * 1024; factor = custom_factor or 2.8
            elif mbps <= 50:
                buf = 64 * 1024 * 1024; factor = custom_factor or 3.2
            else:
                buf = 64 * 1024 * 1024; factor = custom_factor or 3.5
            # Aplicar límite de buffer si está configurado
            if android_limit > 0:
                buf = min(buf, android_limit)
        else:
            # Mapeo estándar para otras plataformas o Android sin optimizaciones
            if mbps <= 5:
                buf = 20 * 1024 * 1024; factor = custom_factor or 3.0
            elif mbps <= 20:
                buf = 50 * 1024 * 1024; factor = custom_factor or 4.0
            elif mbps <= 50:
                buf = 100 * 1024 * 1024; factor = custom_factor or 6.0
            else:
                buf = 200 * 1024 * 1024; factor = custom_factor or 8.0

        msg = ('Resultado del test:\n\n'
               'Velocidad estimada: %.2f Mbps\n'
               'Datos leídos: %.1f MB en %.1f s\n\n'
               'Recomendación%s:\n'
               '- Buffer en memoria: %s\n'
               '- ReadBufferFactor: %.1f%s\n\n'
               '¿Aplicar esta configuración?') % (
                mbps, read_bytes/1024/1024, elapsed, 
                ' (Android optimizado)' if (is_android and android_optimizations) else '',
                format_size(buf), factor,
                ' (personalizado)' if custom_factor else '')

        if not dialog.yesno('Test de velocidad', msg, yeslabel='Aplicar', nolabel='Cancelar'):
            return

        # Escribir configuración propuesta
        config = '''<advancedsettings>
    <network>
        <buffermode>1</buffermode>
        <cachemembuffersize>%d</cachemembuffersize>
        <readbufferfactor>%.1f</readbufferfactor>
    </network>
    <video>
        <memorysize>%d</memorysize>
        <readbufferfactor>%.1f</readbufferfactor>
    </video>
    <cache>
    </cache>
</advancedsettings>''' % (buf, factor, buf, factor)

        # Aplicar correcciones de sincronización si están habilitadas
        config = apply_sync_corrections_to_config(config)

        # Backup y escritura
        backup_advancedsettings(config_path)
        parent = os.path.dirname(config_path)
        try:
            if parent and not os.path.exists(parent):
                os.makedirs(parent, exist_ok=True)
        except Exception:
            pass
        wrote = False
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(config)
            wrote = True
        except Exception:
            try:
                fh = xbmcvfs.File(config_path, 'w')
                fh.write(config)
                fh.close()
                wrote = True
            except Exception as e2:
                dialog.ok('Error', 'No se pudo escribir advancedsettings.xml: %s' % str(e2))
                return
        dialog.ok('Configuración aplicada', 'Reinicia Kodi para aplicar los cambios.')
    except Exception as e:
        log('Error en test de velocidad: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error en test de velocidad: %s' % str(e))

def choose_speed_server():
    """Permite elegir un servidor/ubicación para el test de velocidad"""
    choices = [
        ('Europa (UK - ThinkBroadband)', 'https://download.thinkbroadband.com/10MB.zip'),
        ('Europa (DE - DO FRA1)', 'https://speedtest-fra1.digitalocean.com/10mb.test'),
        ('Europa (DE - Hetzner)', 'https://speed.hetzner.de/10MB.bin'),
        ('Norteamérica (US - DO NYC3)', 'https://speedtest-nyc3.digitalocean.com/10mb.test'),
        ('Asia (SG - DO SGP1)', 'https://speedtest-sgp1.digitalocean.com/10mb.test'),
        ('Europa (OVH)', 'https://proof.ovh.net/files/10Mb.dat')
    ]
    labels = [c[0] for c in choices]
    idx = xbmcgui.Dialog().select('Elegir servidor para el test', labels)
    if idx == -1:
        return None
    return [choices[idx][1]]

def streaming_mode_adjust(config_path):
    """Ajusta buffering según bitrate del vídeo a reproducir"""
    try:
        dialog = xbmcgui.Dialog()
        # Solicitar bitrate objetivo
        bitrates = ['2 Mbps (SD)', '5 Mbps (HD)', '10 Mbps (FullHD)', '25 Mbps (4K comprimido)', '50 Mbps (4K alto)']
        idx = dialog.select('Selecciona bitrate objetivo', bitrates)
        if idx == -1:
            return
        mapping = [2, 5, 10, 25, 50]
        mbps = mapping[idx]

        # Calcular buffer para ~10-20s de vídeo
        seconds = 15
        buffer_bits = mbps * 1_000_000 * seconds
        buf = max(20*1024*1024, min(buffer_bits // 8, 200*1024*1024))
        
        # Obtener factor personalizado del usuario o usar por defecto
        custom_factor = get_user_readbufferfactor()
        if custom_factor > 0:
            factor = custom_factor
        else:
            factor = 4.0 if mbps <= 10 else (6.0 if mbps <= 25 else 8.0)

        # En Android, sin cachepath, limitar a valores conservadores para estabilidad A/V
        is_android = xbmc.getCondVisibility('system.platform.android')
        if is_android and apply_android_optimizations():
            cachepath_android = None
            try:
                if os.path.exists(config_path):
                    root_tmp = ET.parse(config_path).getroot()
                    el_tmp = root_tmp.find('cache/cachepath')
                    if el_tmp is not None and el_tmp.text:
                        cachepath_android = el_tmp.text.strip()
            except Exception:
                pass
            if not cachepath_android:
                android_buffer_limit = get_android_buffer_limit()
                buf = min(buf, android_buffer_limit)
                # Escalar factor máximo en Android solo si no hay factor personalizado
                if custom_factor <= 0:
                    factor = min(factor, 3.2)

        # Preservar cachepath si existe en el XML actual
        cachepath = None
        try:
            if os.path.exists(config_path):
                root = ET.parse(config_path).getroot()
                el = root.find('cache/cachepath')
                if el is not None and el.text:
                    cachepath = el.text.strip()
        except Exception:
            pass

        config = '''<advancedsettings>
    <network>
        <buffermode>%d</buffermode>
        <cachemembuffersize>%d</cachemembuffersize>
        <readbufferfactor>%.1f</readbufferfactor>
    </network>
    <video>
        <memorysize>%d</memorysize>
        <readbufferfactor>%.1f</readbufferfactor>
    </video>
    <cache>
%s
    </cache>
</advancedsettings>''' % (
            2 if cachepath else 1,
            buf if not cachepath else 0,  # si hay cachepath, prioriza disco
            factor,
            buf if not cachepath else 0,
            factor,
            ("        <cachepath>%s</cachepath>\n" % cachepath) if cachepath else ''
        )

        msg_parts = ['Modo streaming:\n\nBitrate objetivo: %d Mbps' % mbps]
        msg_parts.append('Buffer en memoria: %s' % format_size(buf))
        
        # Indicar si se usa factor personalizado o Android optimizado
        factor_info = 'ReadBufferFactor: %.1f' % factor
        if custom_factor > 0:
            factor_info += ' (personalizado)'
        elif is_android and apply_android_optimizations():
            factor_info += ' (Android optimizado)'
        msg_parts.append(factor_info)
        
        if cachepath:
            msg_parts.append('Cachepath: %s' % cachepath)
        
        msg_parts.append('\n¿Aplicar?')
        msg = '\n'.join(msg_parts)
        
        if not dialog.yesno('Modo streaming', msg, yeslabel='Aplicar', nolabel='Cancelar'):
            return

        # Backup y escritura
        backup_advancedsettings(config_path)
        parent = os.path.dirname(config_path)
        try:
            if parent and not os.path.exists(parent):
                os.makedirs(parent, exist_ok=True)
        except Exception:
            pass
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(config)
        except Exception:
            fh = xbmcvfs.File(config_path, 'w')
            fh.write(config)
            fh.close()
        dialog.ok('Configuración aplicada', 'Reinicia Kodi para aplicar los cambios.')
    except Exception as e:
        log('Error en modo streaming: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error en modo streaming: %s' % str(e))

def save_buffering_to_usb(usb_path, config_content):
    """Guarda la configuración de buffering en USB de forma segura"""
    try:
        log('Intentando guardar configuración en: %s' % usb_path)
        
        # Verificar que el USB sigue accesible
        if not os.path.exists(usb_path):
            raise Exception('El USB ya no está accesible en: %s' % usb_path)
        
        if not os.access(usb_path, os.W_OK):
            raise Exception('No se puede escribir en el USB: %s' % usb_path)
        
        # Crear carpeta para configuraciones de Kodi si no existe
        kodi_config_dir = os.path.join(usb_path, 'KodiConfig')
        log('Creando directorio de configuración: %s' % kodi_config_dir)
        
        try:
            if not os.path.exists(kodi_config_dir):
                os.makedirs(kodi_config_dir, mode=0o755)
                log('Directorio creado: %s' % kodi_config_dir)
        except Exception as e:
            raise Exception('No se pudo crear directorio KodiConfig: %s' % str(e))
        
        # Generar nombre de archivo con timestamp
        import datetime
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = 'advancedsettings_%s.xml' % timestamp
        file_path = os.path.join(kodi_config_dir, filename)
        
        log('Guardando archivo: %s' % file_path)
        
        # Guardar archivo
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(config_content)
            
            # Verificar que se guardó correctamente
            if not os.path.exists(file_path):
                raise Exception('El archivo no se creó correctamente')
                
            # Verificar el contenido
            with open(file_path, 'r', encoding='utf-8') as f:
                saved_content = f.read()
                
            if saved_content != config_content:
                raise Exception('El contenido guardado no coincide')
                
        except Exception as e:
            raise Exception('Error escribiendo archivo: %s' % str(e))
        
        log('Configuración guardada exitosamente en USB: %s' % file_path)
        return file_path
        
    except Exception as e:
        log('Error guardando en USB: %s' % str(e))
        raise e

def save_buffering_config_to_usb(config_path):
    """Permite al usuario guardar la configuración de buffering en USB"""
    try:
        dialog = xbmcgui.Dialog()
        log('Iniciando proceso de guardado en USB')
        
        # Verificar si hay configuración para guardar
        if not os.path.exists(config_path):
            log('No existe configuración personalizada')
            # No hay configuración personalizada, ofrecer crear una
            if dialog.yesno('Sin Configuración Personalizada',
                           'No hay configuración de buffering personalizada.\n\n'
                           '¿Deseas crear una configuración básica\n'
                           'antes de guardar en USB?',
                           yeslabel='Crear y Guardar',
                           nolabel='Cancelar'):
                log('Usuario eligió crear configuración básica')
                configure_basic_buffering(config_path)
                if not os.path.exists(config_path):
                    log('No se creó configuración básica, cancelando')
                    return  # Usuario canceló la creación
            else:
                log('Usuario canceló creación de configuración')
                return
        
        # Detectar USBs conectados
        log('Detectando dispositivos USB')
        usb_devices = detect_usb_devices()
        
        if not usb_devices:
            log('Detección automática falló. Ofreciendo selector manual de carpeta USB')
            sel = _browse_for_usb_folder()
            if sel:
                # Construir info mínima del USB seleccionado
                try:
                    stat = os.statvfs(sel)
                    total_space = stat.f_frsize * stat.f_blocks
                    free_space = stat.f_frsize * stat.f_bavail
                    usb_devices = [{
                        'name': os.path.basename(sel) or 'USB seleccionado',
                        'path': sel,
                        'size': format_size(total_space),
                        'free': format_size(free_space),
                        'device': os.path.basename(sel),
                        'total_bytes': total_space,
                        'free_bytes': free_space
                    }]
                    log('USB establecido manualmente: %s' % sel)
                except Exception as e:
                    log('No se pudo obtener info del USB seleccionado: %s' % str(e))
                    usb_devices = [{'name': 'USB seleccionado', 'path': sel}]
            else:
                dialog.ok('Sin USBs',
                          'No se detectaron USBs y no se seleccionó carpeta.\n'
                          'Comprueba el montaje o introduce la ruta manualmente.')
                return
        
        # Mostrar lista de USBs disponibles
        usb_options = []
        for i, usb in enumerate(usb_devices):
            label = '%s - %s libre (%s en %s)' % (
                usb['name'], 
                usb.get('free', 'N/A'), 
                usb.get('size', 'N/A'),
                usb['path']
            )
            usb_options.append(label)
            log('USB opción %d: %s' % (i, label))
        
        usb_selection = dialog.select('Seleccionar USB para Guardar', usb_options)
        
        if usb_selection == -1:
            log('Usuario canceló selección de USB')
            return
        
        selected_usb = usb_devices[usb_selection]
        log('USB seleccionado: %s' % selected_usb['path'])
        
        # Leer configuración actual
        log('Leyendo configuración actual')
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_content = f.read()
            log('Configuración leída, %d caracteres' % len(config_content))
        except Exception as e:
            dialog.ok('Error', 'Error leyendo configuración: %s' % str(e))
            return
        
        # Confirmar guardado
        confirm_msg = ('Guardar configuración en:\n\n'
                      'USB: %s\n'
                      'Ruta: %s\n'
                      'Espacio libre: %s\n\n'
                      '¿Continuar?') % (
                          selected_usb['name'],
                          selected_usb['path'],
                          selected_usb.get('free', 'Desconocido')
                      )
        
        if not dialog.yesno('Confirmar Guardado', confirm_msg, yeslabel='Guardar', nolabel='Cancelar'):
            log('Usuario canceló confirmación de guardado')
            return
        
        # Guardar en USB
        log('Iniciando guardado en USB')
        try:
            saved_file = save_buffering_to_usb(selected_usb['path'], config_content)
            
            # Mostrar resultado
            result_msg = ('Configuración guardada exitosamente:\n\n'
                         'Archivo: %s\n'
                         'Ubicación: %s\n\n'
                         'Puedes usar este archivo para restaurar\n'
                         'la configuración en otros equipos Kodi\n'
                         'copiándolo a:\n'
                         '~/.kodi/userdata/advancedsettings.xml') % (
                             os.path.basename(saved_file),
                             os.path.dirname(saved_file)
                         )
            
            dialog.ok('Guardado Completado', result_msg)
            log('Guardado completado exitosamente: %s' % saved_file)
            
        except Exception as e:
            error_msg = 'Error guardando en USB:\n\n%s\n\nVerifica que:\n• El USB sigue conectado\n• Hay espacio suficiente\n• Tienes permisos de escritura' % str(e)
            dialog.ok('Error de Guardado', error_msg)
            log('Error en guardado: %s' % str(e))

        # Ofrecer configurar el USB como cache externo
        if dialog.yesno('Usar USB para buffering',
                        '¿Deseas que Kodi use este USB como directorio de cache (cachepath)\n'
                        'para el buffering? Esto permite usar más espacio que la RAM.\n\n'
                        'Nota: El medio debe ser rápido y estar siempre conectado.',
                        yeslabel='Configurar', nolabel='No'):
            try:
                # Construir nueva configuración con cachepath y buffermode=2
                cache_dir = os.path.join(selected_usb['path'], 'KodiCache')
                try:
                    os.makedirs(cache_dir, exist_ok=True)
                except Exception:
                    pass

                new_config = '''<advancedsettings>
    <network>
        <buffermode>2</buffermode>
        <cachemembuffersize>0</cachemembuffersize>
        <readbufferfactor>4.0</readbufferfactor>
    </network>
    <video>
        <memorysize>0</memorysize>
        <readbufferfactor>4.0</readbufferfactor>
    </video>
    <cache>
        <cachepath>%s</cachepath>
    </cache>
</advancedsettings>''' % cache_dir

                # Asegurar directorio y escribir
                parent = os.path.dirname(config_path)
                try:
                    if parent and not os.path.exists(parent):
                        os.makedirs(parent, exist_ok=True)
                except Exception:
                    pass

                # Backup automático
                backup_advancedsettings(config_path)

                wrote = False
                try:
                    with open(config_path, 'w', encoding='utf-8') as f:
                        f.write(new_config)
                    wrote = True
                except Exception:
                    try:
                        fh = xbmcvfs.File(config_path, 'w')
                        fh.write(new_config)
                        fh.close()
                        wrote = True
                    except Exception as e2:
                        dialog.ok('Error', 'No se pudo escribir advancedsettings.xml: %s' % str(e2))
                        return

                dialog.ok('Buffer en USB configurado',
                          'Se configuró cachepath en:\n%s\n\n'
                          'Reinicia Kodi para aplicar los cambios.' % cache_dir)
                log('Cachepath configurado en USB: %s' % cache_dir)
            except Exception as e:
                log('Error configurando cachepath: %s' % str(e))
                dialog.ok('Error', 'Error configurando cache en USB: %s' % str(e))
        
    except Exception as e:
        log('Error general en save_buffering_config_to_usb: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error guardando en USB: %s' % str(e))

def remove_buffering_config(config_path):
    """Elimina la configuración de buffering"""
    try:
        if not os.path.exists(config_path):
            xbmcgui.Dialog().ok('Información', 'No hay configuración de buffering para eliminar.')
            return
        
        if xbmcgui.Dialog().yesno('Eliminar Configuración', 
                                 'Esto eliminará toda la configuración\n'
                                 'de buffering personalizada.\n\n'
                                 '¿Continuar?', 
                                 yeslabel='Eliminar', nolabel='Cancelar'):
            os.remove(config_path)
            xbmcgui.Dialog().ok('Configuración Eliminada', 
                              'Configuración de buffering eliminada.\n\n'
                              'Kodi usará valores por defecto.')
            log('Configuración de buffering eliminada')
        
    except Exception as e:
        log('Error eliminando configuración: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error eliminando configuración: %s' % str(e))

def configure_usb_cachepath(config_path):
    """Configura directamente un USB como cachepath (buffermode=2, cachemembuffersize=0)."""
    try:
        dialog = xbmcgui.Dialog()
        # Detectar USBs o permitir selección manual
        devices = detect_usb_devices()
        if not devices:
            sel = _browse_for_usb_folder()
            if sel:
                devices = [{'name': os.path.basename(sel) or 'USB seleccionado', 'path': sel}]
        if not devices:
            dialog.ok('Sin USBs', 'No se detectaron USBs y no se seleccionó carpeta.')
            return
        labels = ['%s (%s)' % (d['path'], d.get('free', '')) for d in devices]
        idx = dialog.select('Selecciona USB para cache', labels)
        if idx == -1:
            return
        selected = devices[idx]
        cache_dir = os.path.join(selected['path'], 'KodiCache')
        try:
            os.makedirs(cache_dir, exist_ok=True)
        except Exception:
            pass

        config = '''<advancedsettings>
    <network>
        <buffermode>2</buffermode>
        <cachemembuffersize>0</cachemembuffersize>
        <readbufferfactor>4.0</readbufferfactor>
    </network>
    <video>
        <memorysize>0</memorysize>
        <readbufferfactor>4.0</readbufferfactor>
    </video>
    <cache>
        <cachepath>%s</cachepath>
    </cache>
</advancedsettings>''' % cache_dir

        # Backup y escritura
        backup_advancedsettings(config_path)
        parent = os.path.dirname(config_path)
        try:
            if parent and not os.path.exists(parent):
                os.makedirs(parent, exist_ok=True)
        except Exception:
            pass
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(config)
        except Exception:
            fh = xbmcvfs.File(config_path, 'w')
            fh.write(config)
            fh.close()
        dialog.ok('Cache en USB configurada', 'cachepath: %s\nReinicia Kodi para aplicar.' % cache_dir)
        log('cachepath configurado en: %s' % cache_dir)
    except Exception as e:
        log('Error configurando USB como cache: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error configurando cache en USB: %s' % str(e))

def show_about():
    """Muestra ventana Acerca de con logo usando notificación + textviewer"""
    try:
        log('Mostrando Acerca de con logo y información')
        
        # Verificar si existe el logo
        logo_path = os.path.join(addon_path, 'logo.png')
        if os.path.exists(logo_path):
            log('Mostrando notificación con logo: %s' % logo_path)
            # Mostrar notificación con logo como icono
            xbmc.executebuiltin('Notification(Aspirando Kodi v%s,Limpiador y optimizador de Kodi,%s,%s)' % (addon_version, 5000, logo_path))
            # Esperar un momento para que se vea la notificación
            xbmc.sleep(2000)
        else:
            log('Logo no encontrado en: %s' % logo_path)
            # Notificación sin logo
            xbmc.executebuiltin('Notification(Aspirando Kodi v%s,Limpiador y optimizador de Kodi,5000)' % addon_version)
            xbmc.sleep(2000)
        
        dialog = xbmcgui.Dialog()
        
        # Información completa del addon
        info_text = ('Aspirando Kodi v%s\n\n'
                    'Limpiador y optimizador de Kodi\n\n'
                    'Funcionalidades principales:\n'
                    '• Limpieza de cache y temporales\n'
                    '• Gestión de paquetes\n'
                    '• Optimización del rendimiento\n'
                    '• Reinicio seguro de Kodi\n'
                    '• Configuración de buffering\n'
                    '• Compactación de bases de datos\n\n'
                    'Versión: %s\n'
                    'Por: entreunosyceros\n\n'
                    'Repositorio: github.com/sapoclay/aspirando-kodi')
        info_text = info_text % (addon_version, addon_version)
        
        # Mostrar información completa con scroll
        dialog.textviewer('Aspirando Kodi - Información Completa', info_text)
        
        # Preguntar si quiere abrir el repositorio
        if dialog.yesno('Repositorio GitHub', 
                       'github.com/sapoclay/aspirando-kodi\n\n'
                       '¿Abrir repositorio en el navegador?',
                       yeslabel='Abrir',
                       nolabel='Cerrar'):
            try:
                import webbrowser
                webbrowser.open('https://github.com/sapoclay/aspirando-kodi')
                log('Repositorio abierto en navegador')
            except Exception as e:
                log('Error abriendo navegador: %s' % str(e))
                # Mostrar URL si no se puede abrir navegador
                dialog.ok('Repositorio', 'https://github.com/sapoclay/aspirando-kodi')
        
    except Exception as e:
        log('Error en show_about: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error mostrando información: %s' % str(e))

def restart_kodi():
    """Reinicia Kodi después de confirmación del usuario"""
    try:
        if xbmcgui.Dialog().yesno('Aspirando Kodi', '¿Reiniciar Kodi ahora?'):
            log('Usuario confirmó reinicio de Kodi')
            # Cerrar todos los diálogos
            xbmc.executebuiltin('Dialog.Close(all)')
            # Reiniciar Kodi
            xbmc.executebuiltin('RestartApp')
        else:
            log('Usuario canceló reinicio de Kodi')
    except Exception as e:
        log('Error en restart_kodi: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error reiniciando Kodi: %s' % str(e))


def check_addon_updates():
    """Comprueba e instala actualizaciones del addon desde la URL oficial"""
    try:
        log('Comprobando actualizaciones del addon')
        dialog = xbmcgui.Dialog()
        result = updater.check_for_updates(force=True, ignore_ignored=True)

        if not result.get('ok'):
            dialog.ok('Actualizaciones', 'No se pudo comprobar si hay actualizaciones.\n\n%s' % result.get('error', 'Error desconocido'))
            return

        if not result.get('available_remotely'):
            dialog.ok('Actualizaciones', 'Ya tienes instalada la ultima version disponible.\n\n%s' % updater.build_update_message(result))
            return

        message = updater.build_update_message(result) + '\n\n¿Descargar e instalar ahora la actualizacion?'
        if not dialog.yesno('Actualizacion disponible', message, yeslabel='Actualizar', nolabel='Mas tarde'):
            log('Usuario aplazo la actualizacion manual a %s' % result.get('remote_version', ''))
            return

        install_result = updater.install_update(result, interactive=True)
        dialog.ok(
            'Actualizacion instalada',
            'Se ha instalado la version %s correctamente.\n\nArchivos actualizados: %d' % (
                install_result.get('remote_version', result.get('remote_version', '')),
                int(install_result.get('copied_files', 0) or 0),
            ),
        )
        updater.prompt_restart_after_update()
    except Exception as e:
        log('Error actualizando addon: %s' % str(e))
        xbmcgui.Dialog().ok('Actualizaciones', 'Error durante la actualizacion: %s' % str(e))

def main():
    """Función principal del addon con bucle continuo"""
    log('Iniciando Aspirando Kodi v%s' % addon_version)
    
    while True:
        try:
            # Mostrar menú principal
            dialog = xbmcgui.Dialog()
            
            opciones = [
                'Limpiar Caché',
                'Limpiar Thumbnails', 
                'Limpiar Paquetes',
                'Limpiar Temporales',
                'Limpieza Streaming/IPTV',
                'Limpieza Completa',
                'Compactar Bases de Datos',
                'Programar limpieza al iniciar',
                'Gestión de Buffering',
                'Restaurar valores predeterminados',
                'Resetear aviso PVR Android',
                'Buscar actualizaciones',
                'Reiniciar Kodi',
                'Acerca de',
                'Salir'
            ]
            
            seleccion = dialog.select('Aspirando Kodi - Menú Principal', opciones)
            
            if seleccion == -1 or seleccion == 14:  # Usuario canceló o seleccionó Salir
                log('Usuario salió del addon')
                break
            
            if seleccion == 0:  # Limpiar Caché
                log('Usuario seleccionó: Limpiar Caché')
                clean_cache()
                
            elif seleccion == 1:  # Limpiar Thumbnails
                log('Usuario seleccionó: Limpiar Thumbnails')
                clean_thumbnails()
                
            elif seleccion == 2:  # Limpiar Paquetes
                log('Usuario seleccionó: Limpiar Paquetes')
                clean_packages()
                
            elif seleccion == 3:  # Limpiar Temporales
                log('Usuario seleccionó: Limpiar Temporales')
                clean_temp()
                
            elif seleccion == 4:  # Limpieza Streaming/IPTV
                log('Usuario seleccionó: Limpieza Streaming/IPTV')
                clean_streaming_artifacts()

            elif seleccion == 5:  # Limpieza Completa
                log('Usuario seleccionó: Limpieza Completa')
                clean_all()
            
            elif seleccion == 6:  # Compactar Bases de Datos
                log('Usuario seleccionó: Compactar Bases de Datos')
                vacuum_databases()
            
            elif seleccion == 7:  # Programar limpieza al iniciar
                log('Usuario seleccionó: Programar limpieza al iniciar')
                schedule_clean_on_start()
                
            elif seleccion == 8:  # Gestión de Buffering
                log('Usuario seleccionó: Gestión de Buffering')
                manage_buffering()
                
            elif seleccion == 9:  # Restaurar valores predeterminados
                log('Usuario seleccionó: Restaurar valores predeterminados')
                restore_kodi_defaults()
                
            elif seleccion == 10:  # Resetear aviso PVR Android
                log('Usuario seleccionó: Resetear aviso PVR Android')
                reset_android_pvr_warning()
                
            elif seleccion == 11:  # Buscar actualizaciones
                log('Usuario seleccionó: Buscar actualizaciones')
                check_addon_updates()

            elif seleccion == 12:  # Reiniciar Kodi
                log('Usuario seleccionó: Reiniciar Kodi')
                restart_kodi()
                # Si el usuario confirma reiniciar, salimos del bucle
                # porque Kodi se va a reiniciar
                break
                
            elif seleccion == 13:  # Acerca de
                log('Usuario seleccionó: Acerca de')
                show_about()
                
        except Exception as e:
            log('Error en main: %s' % str(e))
            xbmcgui.Dialog().ok('Error', 'Error en addon: %s' % str(e))
            # En caso de error, también salimos del bucle para evitar loops infinitos
            break

def show_usb_diagnostic():
    """Muestra información de diagnóstico sobre USBs"""
    try:
        dialog = xbmcgui.Dialog()
        log('Iniciando diagnóstico USB')
        
        diagnostic_info = []
        diagnostic_info.append('DIAGNÓSTICO DE DISPOSITIVOS USB')
        diagnostic_info.append('=' * 40)
        diagnostic_info.append('')
        
        # Verificar directorios de montaje
        mount_dirs = ['/media', '/mnt', '/run/media']
        for mount_dir in mount_dirs:
            if os.path.exists(mount_dir):
                diagnostic_info.append('✓ %s existe' % mount_dir)
                try:
                    items = os.listdir(mount_dir)
                    diagnostic_info.append('  Contenido: %s' % ', '.join(items[:5]))
                except:
                    diagnostic_info.append('  Error listando contenido')
            else:
                diagnostic_info.append('✗ %s no existe' % mount_dir)
        
        diagnostic_info.append('')
        
        # Intentar detectar USBs
        diagnostic_info.append('DETECCIÓN DE DISPOSITIVOS:')
        diagnostic_info.append('-' * 25)
        
        usb_devices = detect_usb_devices()
        if usb_devices:
            for i, usb in enumerate(usb_devices):
                diagnostic_info.append('USB %d:' % (i+1))
                diagnostic_info.append('  Nombre: %s' % usb['name'])
                diagnostic_info.append('  Ruta: %s' % usb['path'])
                diagnostic_info.append('  Tamaño: %s' % usb.get('size', 'N/A'))
                diagnostic_info.append('  Libre: %s' % usb.get('free', 'N/A'))
                diagnostic_info.append('')
        else:
            diagnostic_info.append('No se detectaron dispositivos USB')
        
        # Verificar /proc/mounts
        diagnostic_info.append('INFORMACIÓN DE /proc/mounts:')
        diagnostic_info.append('-' * 30)
        try:
            with open('/proc/mounts', 'r') as f:
                mounts = f.read()
            
            usb_mounts = []
            for line in mounts.split('\n'):
                if any(path in line for path in ['/media/', '/mnt/', '/run/media/']):
                    usb_mounts.append(line.strip())
            
            if usb_mounts:
                for mount in usb_mounts[:10]:  # Limitar a 10 líneas
                    diagnostic_info.append(mount)
            else:
                diagnostic_info.append('No se encontraron montajes USB')
                
        except Exception as e:
            diagnostic_info.append('Error leyendo /proc/mounts: %s' % str(e))
        
        # Mostrar información
        diagnostic_text = '\n'.join(diagnostic_info)
        dialog.textviewer('Diagnóstico USB', diagnostic_text)
        
        # Ofrecer guardar log en archivo local
        if dialog.yesno('Guardar Diagnóstico',
                       'Los detalles están en el log de Kodi.\n\n'
                       '¿Deseas que intente guardar un archivo\n'
                       'de diagnóstico en el directorio home?',
                       yeslabel='Guardar',
                       nolabel='No'):
            try:
                home_dir = os.path.expanduser('~')
                diag_file = os.path.join(home_dir, 'aspirando_kodi_usb_diagnostic.txt')
                with open(diag_file, 'w') as f:
                    f.write(diagnostic_text)
                dialog.ok('Guardado', 'Diagnóstico guardado en:\n%s' % diag_file)
            except Exception as e:
                dialog.ok('Error', 'No se pudo guardar: %s' % str(e))
        
    except Exception as e:
        log('Error en diagnóstico USB: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error en diagnóstico: %s' % str(e))

if __name__ == '__main__':
    main()
