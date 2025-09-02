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
from buffering import (
    get_default_kodi_values,
    configure_basic_buffering,
    configure_advanced_buffering,
    show_current_buffering_config,
    show_buffering_values,
    get_usb_autoclean_enabled,
    toggle_usb_autoclean,
    clean_usb_cachepath,
    optimize_buffering_auto,
    backup_advancedsettings,
    restore_advancedsettings_interactive,
    test_usb_cachepath,
    configure_usb_cachepath,
    choose_speed_server,
    speed_test_and_recommend,
    streaming_mode_adjust,
    view_special_temp_cache,
    redirect_temp_cache_to_usb,
    revert_temp_cache_redirection,
    test_special_temp_cache_write,
    save_buffering_config_to_usb,
    remove_buffering_config,
    detect_usb_devices,
    _translate as buffering_translate,
    temp_status_short as _temp_status_short,
    special_temp_path as _special_temp_path,
)

# Configuración del addon
addon = xbmcaddon.Addon()
addon_path = addon.getAddonInfo('path')
addon_name = addon.getAddonInfo('name')
addon_id = addon.getAddonInfo('id')
addon_version = addon.getAddonInfo('version')
try:
    addon_data_dir = xbmc.translatePath('special://profile/addon_data/%s' % addon_id)
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
                        size = get_folder_size(item_path)
                        shutil.rmtree(item_path)
                        removed_size += size
                        removed_count += 1
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
    except Exception:
        try:
            return xbmc.translatePath(path)
        except Exception:
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

## Funciones de buffering ahora viven en buffering.py

## detect_usb_devices ahora en buffering.detect_usb_devices

## browse_for_usb_folder ahora en buffering

## get_usb_info ahora en buffering

    

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

def clean_thumbnails():
    """Limpia los thumbnails de Kodi"""
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
                  '¿Eliminar thumbnails?') % (files, format_size(size))
        
        if not xbmcgui.Dialog().yesno('Limpiar Thumbnails', message, yeslabel='Eliminar', nolabel='Cancelar'):
            return
        
        # Mostrar progreso
        progress = xbmcgui.DialogProgress()
        progress.create('Limpiando Thumbnails', 'Eliminando thumbnails...')
        progress.update(0)
        
        # Limpiar thumbnails
        removed_count, removed_size = safe_remove_folder_contents(thumbnails_path)
        
        progress.update(100, 'Limpieza completada')
        xbmc.sleep(1000)
        progress.close()
        
        # Mostrar resultado
        result_msg = ('Thumbnails limpiados exitosamente:\n\n'
                     'Archivos eliminados: %d\n'
                     'Espacio liberado: %s\n\n'
                     'Operación completada.') % (removed_count, format_size(removed_size))
        
        xbmcgui.Dialog().ok('Limpieza Completada', result_msg)
        log('Thumbnails limpiados: %d archivos, %s liberados' % (removed_count, format_size(removed_size)))
        
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
        
        # Obtener información antes de limpiar
        size, files = get_temp_info()
        
        if size == 0:
            xbmcgui.Dialog().ok('Información', 'No hay archivos temporales para eliminar.')
            return
        
        # Confirmar limpieza
        message = ('Archivos Temporales:\n\n'
                  'Archivos: %d\n'
                  'Tamaño: %s\n\n'
                  '¿Eliminar archivos temporales?') % (files, format_size(size))
        
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

def clean_all():
    """Limpia todo: caché, thumbnails, paquetes y temporales"""
    try:
        log('Iniciando limpieza completa')
        
        # Obtener información de todas las categorías
        cache_size, cache_files = get_cache_info()
        thumb_size, thumb_files = get_thumbnails_info()
        pack_size, pack_files = get_packages_info()
        temp_size, temp_files = get_temp_info()
        
        total_size = cache_size + thumb_size + pack_size + temp_size
        total_files = cache_files + thumb_files + pack_files + temp_files
        
        if total_size == 0:
            xbmcgui.Dialog().ok('Información', 'No hay archivos para limpiar.')
            return
        
        # Mostrar resumen antes de limpiar
        summary = ('Resumen de limpieza completa:\n\n'
                  'Caché: %d archivos (%s)\n'
                  'Thumbnails: %d archivos (%s)\n'
                  'Paquetes: %d archivos (%s)\n'
                  'Temporales: %d archivos (%s)\n\n'
                  'TOTAL: %d archivos (%s)\n\n'
                  '¿Proceder con la limpieza completa?') % (
                      cache_files, format_size(cache_size),
                      thumb_files, format_size(thumb_size), 
                      pack_files, format_size(pack_size),
                      temp_files, format_size(temp_size),
                      total_files, format_size(total_size))
        
        if not xbmcgui.Dialog().yesno('Limpieza Completa', summary, yeslabel='Limpiar Todo', nolabel='Cancelar'):
            return
        
        # Mostrar progreso
        progress = xbmcgui.DialogProgress()
        progress.create('Limpieza Completa', 'Iniciando limpieza completa...')
        
        total_removed_count = 0
        total_removed_size = 0
        
        # Limpiar caché
        progress.update(10, 'Limpiando caché...')
        if cache_size > 0:
            paths = get_kodi_paths()
            removed_count, removed_size = safe_remove_folder_contents(paths.get('cache', ''))
            total_removed_count += removed_count
            total_removed_size += removed_size
        
        # Limpiar thumbnails
        progress.update(40, 'Limpiando thumbnails...')
        if thumb_size > 0:
            paths = get_kodi_paths()
            removed_count, removed_size = safe_remove_folder_contents(paths.get('thumbnails', ''))
            total_removed_count += removed_count
            total_removed_size += removed_size
        
        # Limpiar paquetes
        progress.update(70, 'Limpiando paquetes...')
        if pack_size > 0:
            paths = get_kodi_paths()
            removed_count, removed_size = safe_remove_folder_contents(paths.get('packages', ''))
            total_removed_count += removed_count
            total_removed_size += removed_size
        
        # Limpiar temporales
        progress.update(90, 'Limpiando archivos temporales...')
        if temp_size > 0:
            paths = get_kodi_paths()
            removed_count, removed_size = safe_remove_folder_contents(paths.get('temp', ''))
            total_removed_count += removed_count
            total_removed_size += removed_size
        
        progress.update(100, 'Limpieza completada')
        xbmc.sleep(1000)
        progress.close()
        
        # Mostrar resultado final
        result_msg = ('Limpieza completa finalizada:\n\n'
                     'Total archivos eliminados: %d\n'
                     'Total espacio liberado: %s\n\n'
                     '¡Kodi está más limpio!') % (total_removed_count, format_size(total_removed_size))
        
        xbmcgui.Dialog().ok('Limpieza Completada', result_msg)
        log('Limpieza completa: %d archivos, %s liberados' % (total_removed_count, format_size(total_removed_size)))
        
    except Exception as e:
        log('Error en limpieza completa: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error en limpieza completa: %s' % str(e))

def schedule_clean_on_start():
    """Muestra un resumen y programa una limpieza completa al iniciar Kodi"""
    try:
        log('Preparando programación de limpieza al iniciar')
        # Obtener información actual
        cache_size, cache_files = get_cache_info()
        thumb_size, thumb_files = get_thumbnails_info()
        pack_size, pack_files = get_packages_info()
        temp_size, temp_files = get_temp_info()

        total_size = cache_size + thumb_size + pack_size + temp_size
        total_files = cache_files + thumb_files + pack_files + temp_files

        if total_size == 0:
            xbmcgui.Dialog().ok('Sin limpieza necesaria', 'No hay archivos para limpiar. No se programó ninguna acción.')
            return

        # Resumen para mostrar al usuario
        summary = (
            'Se programará una limpieza completa al iniciar Kodi.\n\n'
            'Se eliminarán:\n'
            '- Caché: %d archivos (%s)\n'
            '- Thumbnails: %d archivos (%s)\n'
            '- Paquetes: %d archivos (%s)\n'
            '- Temporales: %d archivos (%s)\n\n'
            'TOTAL: %d archivos (%s)\n\n'
            '¿Deseas programar esta limpieza para el próximo inicio?'
        ) % (
            cache_files, format_size(cache_size),
            thumb_files, format_size(thumb_size),
            pack_files, format_size(pack_size),
            temp_files, format_size(temp_size),
            total_files, format_size(total_size)
        )

        dialog = xbmcgui.Dialog()
        if not dialog.yesno('Programar limpieza al iniciar', summary, yeslabel='Programar', nolabel='Cancelar'):
            log('Usuario canceló la programación de limpieza')
            return

        # Guardar marca en addon_data_dir
        schedule_path = os.path.join(addon_data_dir, 'schedule_clean.json')
        data = {
            'scheduled': True,
            'created': __import__('datetime').datetime.now().isoformat(),
            'planned': {
                'cache': {'files': cache_files, 'size': cache_size},
                'thumbnails': {'files': thumb_files, 'size': thumb_size},
                'packages': {'files': pack_files, 'size': pack_size},
                'temp': {'files': temp_files, 'size': temp_size},
                'total': {'files': total_files, 'size': total_size}
            }
        }
        try:
            with open(schedule_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            log('Limpieza programada. Archivo: %s' % schedule_path)
            dialog.ok('Limpieza programada', 'Se ejecutará una limpieza completa al iniciar Kodi.')
        except Exception as e:
            log('No se pudo programar la limpieza: %s' % str(e))
            dialog.ok('Error', 'No se pudo programar la limpieza: %s' % str(e))
    except Exception as e:
        log('Error programando limpieza al iniciar: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error programando limpieza: %s' % str(e))

def manage_buffering():
    """Gestiona la configuración de buffering de Kodi con bucle de opciones"""
    try:
        log('Iniciando gestión de buffering')
        
        while True:
            dialog = xbmcgui.Dialog()
            paths = get_kodi_paths()
            advancedsettings_path = paths.get('advancedsettings', '')

            current_config = "Configurado" if os.path.exists(advancedsettings_path) else "No configurado"
            auto_clean = 'ON' if get_usb_autoclean_enabled() else 'OFF'
            temp_hint = _temp_status_short()
            is_android = xbmc.getCondVisibility('system.platform.android')

            # Submenús como funciones internas para claridad
            def submenu_estado():
                while True:
                    label_temp_status = 'Estado de caché temp: %s' % _temp_status_short()
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
                            temp_root = _special_temp_path()
                            is_link = os.path.islink(temp_root)
                            target = os.path.realpath(temp_root) if is_link else temp_root
                            msg = ['Estado de special://temp', '']
                            msg.append('Ruta: %s' % temp_root)
                            msg.append('Tipo: %s' % ('ENLACE (symlink)' if is_link else 'Local'))
                            if is_link:
                                msg.append('Destino: %s' % target)
                                cache_dir = os.path.join(target, 'cache')
                                msg.append('Destino/cache existe: %s' % ('Sí' if os.path.exists(cache_dir) else 'No'))
                            xbmcgui.Dialog().textviewer('Estado de special://temp', '\n'.join(msg))
                        except Exception as e:
                            log('Error mostrando estado temp: %s' % str(e))
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
                        streaming_mode_adjust(advancedsettings_path)
                    elif i == 3:
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

            # Menú principal de gestión de buffering (agrupado, dinámico)
            categorias = []
            handlers = []
            categorias.append('Estado y visualización (%s)' % temp_hint); handlers.append(submenu_estado)
            categorias.append('Configuración de buffering (%s)' % current_config); handlers.append(submenu_config)
            categorias.append('Cache en USB (AutoClean: %s)' % auto_clean); handlers.append(submenu_usb)
            categorias.append('Velocidad y diagnóstico'); handlers.append(submenu_speed_diag)
            if not is_android:
                categorias.append('Redirección de temp a USB'); handlers.append(submenu_temp_redirect)
            categorias.append('PVR / Timeshift'); handlers.append(submenu_timeshift)
            categorias.append('Copias de seguridad'); handlers.append(submenu_backups)
            categorias.append('Volver'); handlers.append(None)

            seleccion = dialog.select('Gestión de Buffering', categorias)

            if seleccion == -1 or seleccion == len(categorias) - 1:
                log('Usuario salió de gestión de buffering (agrupado)')
                break

            handler = handlers[seleccion]
            if callable(handler):
                handler()
            
    except Exception as e:
        log('Error gestionando buffering: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error gestionando buffering: %s' % str(e))

## show_current_buffering_config ahora proviene de buffering

## configure_basic_buffering ahora proviene de buffering

def configure_advanced_buffering(config_path):
    """Configura buffering avanzado personalizable"""
    try:
        dialog = xbmcgui.Dialog()
        
        # Solicitar configuración personalizada
        buffer_size = dialog.select('Tamaño de Buffer', 
                                   ['20 MB (básico)', '50 MB (recomendado)', '100 MB (alto)', '200 MB (máximo)'])
        
        if buffer_size == -1:
            return
        
        sizes = [20971520, 52428800, 104857600, 209715200]  # 20MB, 50MB, 100MB, 200MB
        size_names = ['20 MB', '50 MB', '100 MB', '200 MB']
        
        selected_size = sizes[buffer_size]
        selected_name = size_names[buffer_size]
        
        read_factor = dialog.select('Factor de Lectura', 
                                   ['2.0 (conservador)', '4.0 (recomendado)', '8.0 (agresivo)'])
        
        if read_factor == -1:
            return
        
        factors = [2.0, 4.0, 8.0]
        factor_names = ['2.0', '4.0', '8.0']
        
        selected_factor = factors[read_factor]
        selected_factor_name = factor_names[read_factor]
        
        # Configuración avanzada
        advanced_config = '''<advancedsettings>
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
        <!-- Puedes establecer un cachepath externo si lo configuras desde USB -->
    </cache>
</advancedsettings>''' % (selected_size, selected_factor, selected_size, selected_factor)
        
        message = ('Configuración avanzada:\n\n'
                  'Buffer de memoria: %s\n'
                  'Factor de lectura: %s\n\n'
                  '¿Aplicar configuración?') % (selected_name, selected_factor_name)
        
        if dialog.yesno('Configurar Buffering Avanzado', message, yeslabel='Aplicar', nolabel='Cancelar'):
            # Backup automático
            backup_advancedsettings(config_path)
            # Asegurar directorio padre
            parent = os.path.dirname(config_path)
            try:
                if parent and not os.path.exists(parent):
                    os.makedirs(parent, exist_ok=True)
            except Exception:
                pass
            # Intentar escritura estándar, luego fallback a xbmcvfs
            wrote = False
            try:
                with open(config_path, 'w', encoding='utf-8') as f:
                    f.write(advanced_config)
                wrote = True
            except Exception as e:
                log('Fallo escritura estándar: %s' % str(e))
            if not wrote:
                try:
                    fh = xbmcvfs.File(config_path, 'w')
                    fh.write(advanced_config)
                    fh.close()
                    wrote = True
                except Exception as e2:
                    raise e2
            
            dialog.ok('Configuración Aplicada', 
                     'Buffering avanzado configurado.\n\n'
                     'Reinicia Kodi para aplicar los cambios.')
            log('Configuración avanzada de buffering aplicada: %s, %s' % (selected_name, selected_factor_name))
        
    except Exception as e:
        log('Error configurando buffering avanzado: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error configurando buffering: %s' % str(e))

def parse_advancedsettings_values(config_path):
    """Parsea advancedsettings.xml y devuelve valores de buffering relevantes"""
    result = {}
    try:
        import xml.etree.ElementTree as ET
        tree = ET.parse(config_path)
        root = tree.getroot()

        def find_text(path_list):
            for p in path_list:
                el = root.find(p)
                if el is not None and (el.text is not None):
                    return el.text.strip()
            return None

        # Buscar en <network> y alternativas
        buffermode = find_text(['network/buffermode', 'cache/buffermode'])
        cachemem = find_text(['network/cachemembuffersize', 'cache/memorysize'])
        readfactor_n = find_text(['network/readbufferfactor'])
        # Buscar en <video> y alternativas
        memorysize = find_text(['video/memorysize', 'cache/memorysize'])
        readfactor_v = find_text(['video/readbufferfactor'])

        if buffermode is not None:
            result['Buffer mode'] = buffermode
        if cachemem is not None:
            try:
                result['Cache memory buffer'] = '%s (%s)' % (cachemem, format_size(int(cachemem)))
            except Exception:
                result['Cache memory buffer'] = cachemem
        if readfactor_n is not None:
            result['Read buffer factor (network)'] = readfactor_n
        if memorysize is not None:
            try:
                result['Video memory size'] = '%s (%s)' % (memorysize, format_size(int(memorysize)))
            except Exception:
                result['Video memory size'] = memorysize
        if readfactor_v is not None:
            result['Read buffer factor (video)'] = readfactor_v

        # cachepath
        try:
            el = root.find('cache/cachepath')
            if el is not None and el.text:
                cpath = el.text.strip()
                result['Cache path'] = cpath
                try:
                    if os.path.exists(cpath):
                        st = os.statvfs(cpath)
                        free = st.f_frsize * st.f_bavail
                        total = st.f_frsize * st.f_blocks
                        result['Cache free space'] = '%s libres de %s' % (format_size(free), format_size(total))
                except Exception:
                    pass
        except Exception:
            pass

        if not result:
            result['Info'] = 'No se encontraron valores de buffering específicos.'
    except Exception as e:
        log('Error parseando advancedsettings.xml: %s' % str(e))
        result['Error'] = 'No se pudo parsear el archivo.'
    return result

def show_buffering_values(config_path):
    """Muestra valores clave de advancedsettings.xml en formato legible"""
    try:
        if not os.path.exists(config_path):
            xbmcgui.Dialog().ok('Sin configuración', 'No existe advancedsettings.xml en tu perfil.')
            return
        values = parse_advancedsettings_values(config_path)
        lines = ['VALORES DE ADVANCEDSETTINGS.XML', '']
        for k, v in values.items():
            lines.append('%s: %s' % (k, v))
        xbmcgui.Dialog().textviewer('Valores de Buffering', '\n'.join(lines))
    except Exception as e:
        log('Error mostrando valores de buffering: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error mostrando valores: %s' % str(e))

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

def clean_usb_cachepath(config_path):
    """Limpia el contenido de la carpeta cachepath si existe."""
    try:
        dialog = xbmcgui.Dialog()
        cpath = _read_cachepath_from_config(config_path)
        if not cpath or not os.path.isdir(cpath):
            # Fallback: si special://temp está redirigido por symlink, ofrecer limpiar allí
            temp_root = _special_temp_path()
            if os.path.islink(temp_root):
                target_root = os.path.realpath(temp_root)
                target_cache = os.path.join(target_root, 'cache')
                use_target = target_cache if os.path.exists(target_cache) else target_root
                msg = ('No hay cachepath en advancedsettings.xml.\n\n'
                       'Se detectó redirección de special://temp a:\n%s\n\n'
                       '¿Limpiar la carpeta de caché en ese destino?') % use_target
                if dialog.yesno('Cache en USB (temp redirigido)', msg, yeslabel='Limpiar', nolabel='Cancelar'):
                    removed_count, removed_size = safe_remove_folder_contents(use_target)
                    dialog.ok('Cache en USB', 'Eliminados %d elementos (%s liberados).' % (removed_count, format_size(removed_size)))
                    log('Limpieza via temp redirigido: %d, %s' % (removed_count, format_size(removed_size)))
                return
            dialog.ok('Cache USB', 'No hay cachepath válido configurado.')
            return
        removed_count, removed_size = safe_remove_folder_contents(cpath)
        xbmcgui.Dialog().ok('Cache USB', 'Eliminados %d elementos (%s liberados).' % (removed_count, format_size(removed_size)))
        log('Auto-limpieza manual: %d, %s' % (removed_count, format_size(removed_size)))
    except Exception as e:
        log('Error limpiando cache USB: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error limpiando cache USB: %s' % str(e))

def optimize_buffering_auto(config_path):
    """Ajusta buffering según RAM disponible y tipo de almacenamiento"""
    try:
        # Calcular RAM disponible
        mem_total = 0
        try:
            with open('/proc/meminfo') as f:
                for line in f:
                    if line.startswith('MemTotal:'):
                        mem_total = int(line.split()[1]) * 1024  # kB -> bytes
                        break
        except Exception:
            mem_total = 512 * 1024 * 1024  # 512MB por defecto

        # Heurística: usar 1/8 de la RAM para buffer, con límites
        buffer_bytes = max(20*1024*1024, min(mem_total // 8, 200*1024*1024))
        read_factor = 4.0 if buffer_bytes <= 50*1024*1024 else (6.0 if buffer_bytes <= 100*1024*1024 else 8.0)

        # Detectar almacenamiento principal del userdata (SSD vs HDD vs SD)
        paths = get_kodi_paths()
        userdata = os.path.dirname(paths.get('advancedsettings', ''))
        dev = None
        try:
            with open('/proc/mounts') as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2 and parts[1] == userdata:
                        dev = parts[0]
                        break
        except Exception:
            pass

        # Ajuste de factor de lectura según medio (muy heurístico)
        if dev and ('mmcblk' in dev or 'sd' in dev):
            read_factor = max(3.0, read_factor - 1.0)

        advanced_config = '''<advancedsettings>
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
        <!-- Puedes establecer un cachepath externo si lo configuras desde USB -->
    </cache>
</advancedsettings>''' % (buffer_bytes, read_factor, buffer_bytes, read_factor)

        msg = ('Optimización automática propuesta:\n\n'
               'RAM total: %s\n'
               'Buffer en memoria: %s\n'
               'ReadBufferFactor: %.1f\n\n'
               '¿Aplicar estos valores?') % (
                   format_size(mem_total), format_size(buffer_bytes), read_factor)

        if xbmcgui.Dialog().yesno('Optimización automática', msg, yeslabel='Aplicar', nolabel='Cancelar'):
            # Backup automático
            backup_advancedsettings(config_path)
            # Asegurar directorio y escribir
            parent = os.path.dirname(config_path)
            try:
                if parent and not os.path.exists(parent):
                    os.makedirs(parent, exist_ok=True)
            except Exception:
                pass
            wrote = False
            try:
                with open(config_path, 'w', encoding='utf-8') as f:
                    f.write(advanced_config)
                wrote = True
            except Exception:
                try:
                    fh = xbmcvfs.File(config_path, 'w')
                    fh.write(advanced_config)
                    fh.close()
                    wrote = True
                except Exception as e2:
                    xbmcgui.Dialog().ok('Error', 'No se pudo escribir configuración: %s' % str(e2))
                    return
            xbmcgui.Dialog().ok('Optimización aplicada', 'Reinicia Kodi para aplicar los cambios.')
            log('Optimización aplicada: buffer=%s, factor=%.1f' % (format_size(buffer_bytes), read_factor))
    except Exception as e:
        log('Error en optimización automática: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error optimizando buffering: %s' % str(e))

def _backup_dir():
    # Directorio de backups dentro del addon_data_dir
    d = os.path.join(addon_data_dir, 'backups')
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d

def backup_advancedsettings(config_path, manual=False):
    """Crea copia de advancedsettings.xml si existe"""
    try:
        if not os.path.exists(config_path):
            if manual:
                xbmcgui.Dialog().ok('Copia de seguridad', 'No existe advancedsettings.xml para respaldar.')
            return None
        import datetime
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        dest = os.path.join(_backup_dir(), f'advancedsettings_{ts}.xml')
        shutil.copy2(config_path, dest)
        log('Backup creado: %s' % dest)
        if manual:
            xbmcgui.Dialog().ok('Copia de seguridad', 'Backup creado:\n%s' % dest)
        return dest
    except Exception as e:
        log('Error creando backup: %s' % str(e))
        if manual:
            xbmcgui.Dialog().ok('Error', 'No se pudo crear el backup: %s' % str(e))
        return None

def _list_backups():
    d = _backup_dir()
    try:
        items = [f for f in os.listdir(d) if f.startswith('advancedsettings_') and f.endswith('.xml')]
        items.sort(reverse=True)
        return [os.path.join(d, f) for f in items]
    except Exception:
        return []

def restore_advancedsettings_interactive(config_path):
    """Permite elegir un backup y restaurarlo"""
    try:
        backups = _list_backups()
        if not backups:
            xbmcgui.Dialog().ok('Restaurar', 'No hay copias de seguridad disponibles.')
            return
        labels = [os.path.basename(p) for p in backups]
        idx = xbmcgui.Dialog().select('Selecciona backup a restaurar', labels)
        if idx == -1:
            return
        src = backups[idx]
        # Confirmar
        if not xbmcgui.Dialog().yesno('Restaurar', 'Se restaurará:\n%s\n\n¿Continuar?' % labels[idx], yeslabel='Restaurar', nolabel='Cancelar'):
            return
        # Asegurar directorio padre
        parent = os.path.dirname(config_path)
        try:
            if parent and not os.path.exists(parent):
                os.makedirs(parent, exist_ok=True)
        except Exception:
            pass
        shutil.copy2(src, config_path)
        xbmcgui.Dialog().ok('Restaurado', 'Archivo restaurado. Reinicia Kodi para aplicar cambios.')
        log('Restaurado desde %s' % src)
    except Exception as e:
        log('Error restaurando backup: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'No se pudo restaurar: %s' % str(e))

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
            progress.update(int(i*100/len(targets)), 'Compactando %s' % os.path.basename(db_path))
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
        import xml.etree.ElementTree as ET
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

def _shorten_path(p: str, max_len: int = 28) -> str:
    try:
        if len(p) <= max_len:
            return p
        return '…' + p[-max_len:]
    except Exception:
        return p

def _temp_status_short() -> str:
    """Devuelve un texto corto con el estado de special://temp (local o enlace y destino)."""
    try:
        temp_root = _special_temp_path()
        if os.path.islink(temp_root):
            target = os.path.realpath(temp_root)
            return 'temp: enlace -> %s' % _shorten_path(target)
        return 'temp: local'
    except Exception:
        return 'temp: desconocido'

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
            from buffering import browse_for_usb_folder
            sel = browse_for_usb_folder()
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
    """Intenta abrir la pantalla de ajustes de Timeshift del PVR."""
    try:
        # 1) Si está instalado iptvsimple, abrir directamente sus ajustes
        try:
            xbmcaddon.Addon('pvr.iptvsimple')
            xbmc.executebuiltin('Addon.OpenSettings(pvr.iptvsimple)')
            # Dar tiempo a que se abra la ventana y no forzar más diálogos
            xbmc.sleep(800)
            return
        except Exception:
            pass

        # 2) Abrir ajustes de PVR/Timeshift como fallback
        tried = []
        def _try(cmd, wait=600):
            tried.append(cmd)
            xbmc.executebuiltin(cmd)
            xbmc.sleep(wait)

        _try('ActivateWindow(pvrsettings)')
        # Algunos builds aceptan parámetros de categoría en settings
        _try('ActivateWindow(settings,pvr,return)')
        _try('ActivateWindow(settings)')

        # 3) Como último recurso, abrir el navegador de addons en clientes PVR
        _try('ActivateWindow(AddonBrowser,addons://all/pvr/,return)', wait=400)

        # Pequeña ayuda si no se logró abrir directamente
        msg = (
            'Si no se abrió directamente Timeshift o el cliente IPTV Simple, ve a:\n'
            '- Ajustes (modo Experto)\n'
            '- TV en directo / PVR & Live TV\n'
            '- Timeshift\n\n'
            'Para iptvsimple: Ajustes -> Add-ons -> Mis add-ons -> Clientes PVR -> IPTV Simple Client\n\n'
            'Intentos ejecutados:\n' + '\n'.join(tried)
        )
        xbmcgui.Dialog().ok('Ajustes de Timeshift', msg)
    except Exception as e:
        log('Error abriendo ajustes de Timeshift: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'No se pudieron abrir los ajustes: %s' % str(e))

def perform_speed_test(timeout=15, urls=None):
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
                    size_bytes = int(resp.headers.get('Content-Length', '0')) or None
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
        # Heurística simple: asignar buffer en memoria basado en Mbps
        # 0-5 Mbps: 20 MB, 5-20: 50 MB, 20-50: 100 MB, >50: 200 MB
        if mbps <= 5:
            buf = 20 * 1024 * 1024; factor = 3.0
        elif mbps <= 20:
            buf = 50 * 1024 * 1024; factor = 4.0
        elif mbps <= 50:
            buf = 100 * 1024 * 1024; factor = 6.0
        else:
            buf = 200 * 1024 * 1024; factor = 8.0

        msg = ('Resultado del test:\n\n'
               'Velocidad estimada: %.2f Mbps\n'
               'Datos leídos: %.1f MB en %.1f s\n\n'
               'Recomendación:\n'
               '- Buffer en memoria: %s\n'
               '- ReadBufferFactor: %.1f\n\n'
               '¿Aplicar esta configuración?') % (
                mbps, read_bytes/1024/1024, elapsed, format_size(buf), factor)

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
        factor = 4.0 if mbps <= 10 else (6.0 if mbps <= 25 else 8.0)

        # Preservar cachepath si existe en el XML actual
        cachepath = None
        try:
            if os.path.exists(config_path):
                import xml.etree.ElementTree as ET
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

        msg = ('Modo streaming:\n\nBitrate objetivo: %d Mbps\nBuffer en memoria: %s\nReadBufferFactor: %.1f%s\n\n¿Aplicar?') % (
            mbps, format_size(buf), factor, ('\nCachepath: %s' % cachepath) if cachepath else '')
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
            from buffering import browse_for_usb_folder
            sel = browse_for_usb_folder()
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
            from buffering import browse_for_usb_folder
            sel = browse_for_usb_folder()
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

def main():
    """Función principal del addon con bucle continuo"""
    log('Iniciando Aspirando Kodi v%s' % addon_version)
    
    while True:
        try:
            # Mostrar menú principal
            dialog = xbmcgui.Dialog()
            
            # Indicador de estado de temp al final del título de menú
            temp_hint = _temp_status_short()
            opciones = [
                'Limpiar Caché',
                'Limpiar Thumbnails', 
                'Limpiar Paquetes',
                'Limpiar Temporales',
                'Limpieza Completa',
                'Compactar Bases de Datos',
                'Programar limpieza al iniciar',
                'Gestión de Buffering (%s)' % temp_hint,
                'Reiniciar Kodi',
                'Acerca de',
                'Salir'
            ]
            
            seleccion = dialog.select('Aspirando Kodi - Menú Principal', opciones)
            
            if seleccion == -1 or seleccion == 10:  # Usuario canceló o seleccionó Salir
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
                
            elif seleccion == 4:  # Limpieza Completa
                log('Usuario seleccionó: Limpieza Completa')
                clean_all()
            
            elif seleccion == 5:  # Compactar Bases de Datos
                log('Usuario seleccionó: Compactar Bases de Datos')
                vacuum_databases()
            
            elif seleccion == 6:  # Programar limpieza al iniciar
                log('Usuario seleccionó: Programar limpieza al iniciar')
                schedule_clean_on_start()
                
            elif seleccion == 7:  # Gestión de Buffering
                log('Usuario seleccionó: Gestión de Buffering')
                manage_buffering()
                
            elif seleccion == 8:  # Reiniciar Kodi
                log('Usuario seleccionó: Reiniciar Kodi')
                restart_kodi()
                # Si el usuario confirma reiniciar, salimos del bucle
                # porque Kodi se va a reiniciar
                break
                
            elif seleccion == 9:  # Acerca de
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
