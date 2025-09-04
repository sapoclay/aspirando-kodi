import xbmc
import xbmcgui
import xbmcaddon
import xbmcvfs
import os
import shutil
import json
import time
import datetime
import urllib.request

# Contexto del addon (local a este módulo)
addon = xbmcaddon.Addon()
addon_name = addon.getAddonInfo('name')
addon_id = addon.getAddonInfo('id')
try:
    addon_data_dir = xbmc.translatePath('special://profile/addon_data/%s' % addon_id)
except Exception:
    addon_data_dir = os.path.expanduser('~/.kodi/userdata/addon_data/%s' % addon_id)

# Utilidades locales (para evitar dependencias circulares)
def log(message: str):
    xbmc.log('[%s] %s' % (addon_name, message), xbmc.LOGINFO)

def format_size(bytes_size: int) -> str:
    if bytes_size < 1024:
        return "%d B" % bytes_size
    elif bytes_size < 1024 * 1024:
        return "%.1f KB" % (bytes_size / 1024.0)
    elif bytes_size < 1024 * 1024 * 1024:
        return "%.1f MB" % (bytes_size / (1024.0 * 1024.0))
    else:
        return "%.1f GB" % (bytes_size / (1024.0 * 1024.0 * 1024.0))

def _translate(path: str) -> str:
    try:
        return xbmcvfs.translatePath(path)
    except Exception:
        try:
            return xbmc.translatePath(path)
        except Exception:
            return path

def get_kodi_paths():
    try:
        kodi_data_path = _translate('special://userdata/')
        return {
            'cache': os.path.join(kodi_data_path, 'cache'),
            'thumbnails': os.path.join(kodi_data_path, 'Thumbnails'),
            'packages': os.path.join(_translate('special://home/'), 'addons', 'packages'),
            'temp': _translate('special://temp/'),
            'log': os.path.join(kodi_data_path, 'kodi.log'),
            'advancedsettings': os.path.join(kodi_data_path, 'advancedsettings.xml'),
        }
    except Exception as e:
        log('Error obteniendo rutas de Kodi: %s' % str(e))
        return {}

# Estado de special://temp
def special_temp_path() -> str:
    try:
        p = _translate('special://temp/')
        return os.path.normpath(p)
    except Exception:
        return os.path.expanduser('~/.kodi/temp')

def temp_symlink_state_path():
    return os.path.join(addon_data_dir, 'temp_symlink_state.json')

def is_linux_desktop() -> bool:
    try:
        if xbmc.getCondVisibility('system.platform.android'):
            return False
        return xbmc.getCondVisibility('system.platform.linux')
    except Exception:
        return os.name == 'posix'

def is_android() -> bool:
    try:
        return xbmc.getCondVisibility('system.platform.android')
    except Exception:
        return False

def device_label() -> str:
    return 'Almacenamiento externo' if is_android() else 'USB'

def shorten_path(p: str, max_len: int = 28) -> str:
    try:
        if len(p) <= max_len:
            return p
        return '…' + p[-max_len:]
    except Exception:
        return p

def temp_status_short() -> str:
    try:
        temp_root = special_temp_path()
        if os.path.islink(temp_root):
            target = os.path.realpath(temp_root)
            return 'temp: enlace -> %s' % shorten_path(target)
        return 'temp: local'
    except Exception:
        return 'temp: desconocido'

# USB helpers
def get_usb_info(path, name):
    try:
        if not os.path.exists(path) or not os.access(path, os.W_OK):
            return None
        try:
            test_file = os.path.join(path, '.aspirando_write_test')
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
        except Exception:
            return None
        try:
            stat = os.statvfs(path)
            total_space = stat.f_frsize * stat.f_blocks
            free_space = stat.f_frsize * stat.f_bavail
            return {
                'name': name,
                'path': path,
                'size': format_size(total_space),
                'free': format_size(free_space),
                'device': name,
                'total_bytes': total_space,
                'free_bytes': free_space
            }
        except Exception as e:
            log('Error obteniendo estadísticas de %s: %s' % (path, str(e)))
            return {
                'name': name,
                'path': path,
                'size': 'Desconocido',
                'free': 'Desconocido',
                'device': name,
                'total_bytes': 0,
                'free_bytes': 0
            }
    except Exception as e:
        log('Error obteniendo info de USB %s: %s' % (path, str(e)))
        return None

def detect_usb_devices():
    usb_devices = []
    try:
        mount_bases = ['/media', '/mnt', '/run/media']
        if is_android():
            # En Android intentamos en /storage y /mnt/media_rw
            mount_bases.extend(['/storage', '/mnt/media_rw'])
        for base_path in mount_bases:
            if os.path.exists(base_path):
                try:
                    for user_dir in os.listdir(base_path):
                        user_path = os.path.join(base_path, user_dir)
                        if os.path.isdir(user_path):
                            if base_path == '/run/media':
                                try:
                                    for device_dir in os.listdir(user_path):
                                        device_path = os.path.join(user_path, device_dir)
                                        if os.path.isdir(device_path) and os.access(device_path, os.W_OK):
                                            usb_info = get_usb_info(device_path, device_dir)
                                            if usb_info and not any(usb['path'] == device_path for usb in usb_devices):
                                                usb_devices.append(usb_info)
                                except Exception:
                                    continue
                            else:
                                if os.access(user_path, os.W_OK):
                                    try:
                                        test_file = os.path.join(user_path, '.aspirando_test')
                                        with open(test_file, 'w') as f:
                                            f.write('test')
                                        os.remove(test_file)
                                        usb_info = get_usb_info(user_path, user_dir)
                                        if usb_info and not any(usb['path'] == user_path for usb in usb_devices):
                                            usb_devices.append(usb_info)
                                    except Exception:
                                        continue
                except Exception as e:
                    log('Error listando %s: %s' % (base_path, str(e)))
        try:
            with open('/proc/mounts', 'r') as f:
                mounts = f.read()
            for line in mounts.split('\n'):
                if line.strip():
                    parts = line.split()
                    if len(parts) >= 3:
                        mountpoint = parts[1]
                        fstype = parts[2]
                        if (mountpoint.startswith('/media/') or mountpoint.startswith('/mnt/') or mountpoint.startswith('/run/media/') or mountpoint.startswith('/storage/')) and \
                           fstype in ['vfat', 'ntfs', 'exfat', 'ext4', 'ext3', 'ext2']:
                            if os.path.exists(mountpoint) and os.access(mountpoint, os.W_OK):
                                try:
                                    test_file = os.path.join(mountpoint, '.aspirando_test')
                                    with open(test_file, 'w') as f:
                                        f.write('test')
                                    os.remove(test_file)
                                    name = os.path.basename(mountpoint)
                                    usb_info = get_usb_info(mountpoint, name)
                                    if usb_info and not any(usb['path'] == mountpoint for usb in usb_devices):
                                        usb_devices.append(usb_info)
                                except Exception:
                                    continue
        except Exception as e:
            log('Error leyendo /proc/mounts: %s' % str(e))
    except Exception as e:
        log('Error general detectando USBs: %s' % str(e))
    return usb_devices

def browse_for_usb_folder():
    try:
        dialog = xbmcgui.Dialog()
        try:
            start_dir = '/storage' if is_android() else '/media'
            path = dialog.browse(3, 'Selecciona carpeta en tu %s' % device_label(), 'files', '', False, True, start_dir)
        except Exception:
            path = ''
        if path and isinstance(path, str) and os.path.isdir(path):
            return path
        placeholder = '/storage/XXXX-XXXX' if is_android() else '/media/USUARIO/NOMBRE'
        path = dialog.input('Introduce ruta (%s)' % placeholder, type=xbmcgui.INPUT_ALPHANUM)
        if path and os.path.isdir(path):
            return path
    except Exception as e:
        log('Error en browse_for_usb_folder: %s' % str(e))
    return None

# Configuración y visualización
def get_default_kodi_values():
    return {
        'buffermode': '1 (Buffer todo tipo de contenido)',
        'cachemembuffersize': '20971520 (20 MB)',
        'readbufferfactor': '4.0 (Factor estándar)',
        'memorysize': '20971520 (20 MB)',
        'description': 'Configuración por defecto de Kodi'
    }

def parse_advancedsettings_values(config_path):
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
        buffermode = find_text(['network/buffermode', 'cache/buffermode'])
        cachemem = find_text(['network/cachemembuffersize', 'cache/memorysize'])
        readfactor_n = find_text(['network/readbufferfactor'])
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

def show_current_buffering_config(config_path):
    try:
        if not os.path.exists(config_path):
            defaults = get_default_kodi_values()
            default_info = ('CONFIGURACIÓN POR DEFECTO DE KODI\n\n'
                           'Buffer Mode: %s\n'
                           'Cache Memory Buffer: %s\n'
                           'Read Buffer Factor: %s\n'
                           'Video Memory Size: %s\n\n'
                           'Nota: Estos son los valores que Kodi\n'
                           'utiliza cuando no hay configuración\n'
                           'personalizada (advancedsettings.xml).\n\n'
                           'Para optimizar el rendimiento, puedes\n'
                           'crear una configuración personalizada\n'
                           'usando las opciones del menú.') % (
                               defaults['buffermode'],
                               defaults['cachemembuffersize'], 
                               defaults['readbufferfactor'],
                               defaults['memorysize']
                           )
            xbmcgui.Dialog().textviewer('Configuración Actual - Valores por Defecto', default_info)
            return
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()
        values = parse_advancedsettings_values(config_path)
        lines = [
            'CONFIGURACIÓN PERSONALIZADA ACTIVA',
            '=====================================',
            '',
            'VALORES DETECTADOS:'
        ]
        for k, v in values.items():
            lines.append('• %s: %s' % (k, v))
        lines.append('')
        lines.append('--- Contenido XML ---')
        lines.append(content)
        xbmcgui.Dialog().textviewer('Configuración Actual - Personalizada', '\n'.join(lines))
    except Exception as e:
        log('Error mostrando configuración: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error leyendo configuración: %s' % str(e))

def backup_dir():
    d = os.path.join(addon_data_dir, 'backups')
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d

def backup_advancedsettings(config_path, manual=False):
    try:
        if not os.path.exists(config_path):
            if manual:
                xbmcgui.Dialog().ok('Copia de seguridad', 'No existe advancedsettings.xml para respaldar.')
            return None
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        dest = os.path.join(backup_dir(), f'advancedsettings_{ts}.xml')
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

def list_backups():
    d = backup_dir()
    try:
        items = [f for f in os.listdir(d) if f.startswith('advancedsettings_') and f.endswith('.xml')]
        items.sort(reverse=True)
        return [os.path.join(d, f) for f in items]
    except Exception:
        return []

def restore_advancedsettings_interactive(config_path):
    try:
        backups = list_backups()
        if not backups:
            xbmcgui.Dialog().ok('Restaurar', 'No hay copias de seguridad disponibles.')
            return
        labels = [os.path.basename(p) for p in backups]
        idx = xbmcgui.Dialog().select('Selecciona backup a restaurar', labels)
        if idx == -1:
            return
        src = backups[idx]
        if not xbmcgui.Dialog().yesno('Restaurar', 'Se restaurará:\n%s\n\n¿Continuar?' % labels[idx], yeslabel='Restaurar', nolabel='Cancelar'):
            return
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

def read_cachepath_from_config(config_path):
    try:
        if not os.path.exists(config_path):
            return None
        import xml.etree.ElementTree as ET
        root = ET.parse(config_path).getroot()
        el = root.find('cache/cachepath')
        if el is not None and el.text:
            return el.text.strip()
    except Exception as e:
        log('Error leyendo cachepath: %s' % str(e))
    return None

def clean_usb_cachepath(config_path):
    try:
        dialog = xbmcgui.Dialog()
        cpath = read_cachepath_from_config(config_path)
        if not cpath or not os.path.isdir(cpath):
            temp_root = special_temp_path()
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

# Necesitamos estas utilidades aquí; se pasarán desde default si están allí.
# Para evitar circularidad, las reimplementamos mínimamente.
def get_folder_size(folder_path):
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
    count = 0
    try:
        if os.path.exists(folder_path):
            for dirpath, dirnames, filenames in os.walk(folder_path):
                count += len(filenames)
    except Exception as e:
        log('Error contando archivos en %s: %s' % (folder_path, str(e)))
    return count

def safe_remove_folder_contents(folder_path):
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

# Flags de auto-clean
def autoclean_flag_path():
    return os.path.join(addon_data_dir, 'usb_autoclean.json')

def get_usb_autoclean_enabled():
    try:
        p = autoclean_flag_path()
        if os.path.exists(p):
            with open(p, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return bool(data.get('enabled', False))
    except Exception as e:
        log('No se pudo leer usb_autoclean.json: %s' % str(e))
    return False

def set_usb_autoclean_enabled(val: bool):
    try:
        p = autoclean_flag_path()
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

# Funciones de configuración de buffering
def configure_basic_buffering(config_path):
    try:
        basic_config = '''<advancedsettings>
    <network>
        <buffermode>1</buffermode>
        <cachemembuffersize>52428800</cachemembuffersize>
        <readbufferfactor>4.0</readbufferfactor>
    </network>
    <video>
        <memorysize>52428800</memorysize>
        <readbufferfactor>4.0</readbufferfactor>
    </video>
    <cache>
        <!-- Puedes establecer un cachepath externo si lo configuras desde USB -->
    </cache>
</advancedsettings>'''
        message = ('Configuración básica de buffering:\n\n'
                  '• Buffer de memoria: 50 MB\n'
                  '• Factor de lectura: 4.0\n'
                  '• Optimizado para streaming\n\n'
                  '¿Aplicar configuración básica?')
        if xbmcgui.Dialog().yesno('Configurar Buffering Básico', message, yeslabel='Aplicar', nolabel='Cancelar'):
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
                    f.write(basic_config)
                wrote = True
            except Exception as e:
                log('Fallo escritura estándar: %s' % str(e))
            if not wrote:
                try:
                    fh = xbmcvfs.File(config_path, 'w')
                    fh.write(basic_config)
                    fh.close()
                    wrote = True
                except Exception as e2:
                    raise e2
            xbmcgui.Dialog().ok('Configuración Aplicada', 'Buffering básico configurado.\n\nReinicia Kodi para aplicar los cambios.')
            log('Configuración básica de buffering aplicada')
    except Exception as e:
        log('Error configurando buffering básico: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error configurando buffering: %s' % str(e))

def configure_advanced_buffering(config_path):
    try:
        dialog = xbmcgui.Dialog()
        buffer_size = dialog.select('Tamaño de Buffer', ['20 MB (básico)', '50 MB (recomendado)', '100 MB (alto)', '200 MB (máximo)'])
        if buffer_size == -1:
            return
        sizes = [20971520, 52428800, 104857600, 209715200]
        size_names = ['20 MB', '50 MB', '100 MB', '200 MB']
        selected_size = sizes[buffer_size]
        selected_name = size_names[buffer_size]
        read_factor = dialog.select('Factor de Lectura', ['2.0 (conservador)', '4.0 (recomendado)', '8.0 (agresivo)'])
        if read_factor == -1:
            return
        factors = [2.0, 4.0, 8.0]
        factor_names = ['2.0', '4.0', '8.0']
        selected_factor = factors[read_factor]
        selected_factor_name = factor_names[read_factor]
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
            dialog.ok('Configuración Aplicada', 'Buffering avanzado configurado.\n\nReinicia Kodi para aplicar los cambios.')
            log('Configuración avanzada de buffering aplicada: %s, %s' % (selected_name, selected_factor_name))
    except Exception as e:
        log('Error configurando buffering avanzado: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error configurando buffering: %s' % str(e))

def optimize_buffering_auto(config_path):
    try:
        mem_total = 0
        try:
            with open('/proc/meminfo') as f:
                for line in f:
                    if line.startswith('MemTotal:'):
                        mem_total = int(line.split()[1]) * 1024
                        break
        except Exception:
            mem_total = 512 * 1024 * 1024
        buffer_bytes = max(20*1024*1024, min(mem_total // 8, 200*1024*1024))
        read_factor = 4.0 if buffer_bytes <= 50*1024*1024 else (6.0 if buffer_bytes <= 100*1024*1024 else 8.0)
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
               '¿Aplicar estos valores?') % (format_size(mem_total), format_size(buffer_bytes), read_factor)
        if xbmcgui.Dialog().yesno('Optimización automática', msg, yeslabel='Aplicar', nolabel='Cancelar'):
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

def streaming_mode_adjust(config_path):
    try:
        dialog = xbmcgui.Dialog()
        bitrates = ['2 Mbps (SD)', '5 Mbps (HD)', '10 Mbps (FullHD)', '25 Mbps (4K comprimido)', '50 Mbps (4K alto)']
        idx = dialog.select('Selecciona bitrate objetivo', bitrates)
        if idx == -1:
            return
        mapping = [2, 5, 10, 25, 50]
        mbps = mapping[idx]
        seconds = 15
        buffer_bits = mbps * 1_000_000 * seconds
        buf = max(20*1024*1024, min(buffer_bits // 8, 200*1024*1024))
        factor = 4.0 if mbps <= 10 else (6.0 if mbps <= 25 else 8.0)
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
            buf if not cachepath else 0,
            factor,
            buf if not cachepath else 0,
            factor,
            ("        <cachepath>%s</cachepath>\n" % cachepath) if cachepath else ''
        )
        msg = ('Modo streaming:\n\nBitrate objetivo: %d Mbps\nBuffer en memoria: %s\nReadBufferFactor: %.1f%s\n\n¿Aplicar?') % (
            mbps, format_size(buf), factor, ('\nCachepath: %s' % cachepath) if cachepath else '')
        if not dialog.yesno('Modo streaming', msg, yeslabel='Aplicar', nolabel='Cancelar'):
            return
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

# Redirección de temp a USB
def view_special_temp_cache():
    try:
        dialog = xbmcgui.Dialog()
        temp_root = special_temp_path()
        cache_dir = os.path.join(temp_root, 'cache')
        target = cache_dir if os.path.exists(cache_dir) else temp_root
        total_size = get_folder_size(target)
        total_files = count_files_in_folder(target)
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
    try:
        dialog = xbmcgui.Dialog()
        if not is_linux_desktop():
            dialog.ok('No compatible', 'Esta función requiere Linux (no Android).')
            return
        temp_root = special_temp_path()
        if not temp_root or not os.path.exists(os.path.dirname(temp_root)):
            dialog.ok('Error', 'No se resolvió la ruta de temp.')
            return
        devices = detect_usb_devices()
        if not devices:
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
        backup_path = None
        try:
            if os.path.islink(temp_root):
                os.unlink(temp_root)
            elif os.path.exists(temp_root):
                if os.listdir(temp_root):
                    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                    backup_path = temp_root + '.bak-' + ts
                    os.rename(temp_root, backup_path)
                else:
                    os.rmdir(temp_root)
        except Exception as e:
            dialog.ok('Error', 'No se pudo preparar temp: %s' % str(e))
            return
        try:
            os.symlink(target_dir, temp_root)
        except Exception as e:
            try:
                if backup_path and not os.path.exists(temp_root):
                    os.rename(backup_path, temp_root)
            except Exception:
                pass
            dialog.ok('Error', 'No se pudo crear el enlace simbólico: %s' % str(e))
            return
        try:
            test_file = os.path.join(temp_root, '.temp_test')
            with open(test_file, 'w') as f:
                f.write('ok')
            os.remove(test_file)
            ok = True
        except Exception:
            ok = False
        try:
            st = {
                'linked': True,
                'link': temp_root,
                'target': target_dir,
                'backup': backup_path,
                'created_at': datetime.datetime.now().isoformat()
            }
            with open(temp_symlink_state_path(), 'w', encoding='utf-8') as f:
                json.dump(st, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        dialog.ok('Redirección aplicada', 'special://temp -> %s\nEscritura: %s\nReinicia Kodi para asegurar el uso.' % (target_dir, 'OK' if ok else 'FALLO'))
        log('Temp redirigida a %s (ok=%s)' % (target_dir, ok))
    except Exception as e:
        log('Error en redirect_temp_cache_to_usb: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error redirigiendo cache: %s' % str(e))

def revert_temp_cache_redirection():
    try:
        dialog = xbmcgui.Dialog()
        temp_root = special_temp_path()
        state = None
        try:
            p = temp_symlink_state_path()
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
        try:
            os.unlink(temp_root)
        except Exception as e:
            dialog.ok('Error', 'No se pudo eliminar el enlace: %s' % str(e))
            return
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
        try:
            with open(temp_symlink_state_path(), 'w', encoding='utf-8') as f:
                json.dump({'linked': False, 'link': temp_root, 'restored': restored, 'updated_at': datetime.datetime.now().isoformat()}, f)
        except Exception:
            pass
        dialog.ok('Listo', 'Temp local %s.' % ('restaurada desde backup' if restored else 'recreada vacía'))
        log('Temp revertida; restored=%s' % restored)
    except Exception as e:
        log('Error en revert_temp_cache_redirection: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error revirtiendo redirección: %s' % str(e))

def test_special_temp_cache_write():
    try:
        dialog = xbmcgui.Dialog()
        temp_root = special_temp_path()
        cache_dir = os.path.join(temp_root, 'cache')
        try:
            os.makedirs(cache_dir, exist_ok=True)
        except Exception as e:
            dialog.ok('Error', 'No se pudo crear cache: %s' % str(e))
            return
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
        target = os.path.realpath(cache_dir) if os.path.islink(cache_dir) else cache_dir
        dialog.ok('Prueba special://temp/cache', 'Ruta: %s\nEscritura: %s\nLectura: %s' % (target, 'OK' if ok_w else 'FALLO', 'OK' if ok_r else 'FALLO'))
    except Exception as e:
        log('Error en test_special_temp_cache_write: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error en prueba de temp/cache: %s' % str(e))

# Guardado/USB y cachepath
def save_buffering_to_usb(usb_path, config_content):
    try:
        log('Intentando guardar configuración en: %s' % usb_path)
        if not os.path.exists(usb_path):
            raise Exception('El USB ya no está accesible en: %s' % usb_path)
        if not os.access(usb_path, os.W_OK):
            raise Exception('No se puede escribir en el USB: %s' % usb_path)
        kodi_config_dir = os.path.join(usb_path, 'KodiConfig')
        log('Creando directorio de configuración: %s' % kodi_config_dir)
        try:
            if not os.path.exists(kodi_config_dir):
                os.makedirs(kodi_config_dir, mode=0o755)
                log('Directorio creado: %s' % kodi_config_dir)
        except Exception as e:
            raise Exception('No se pudo crear directorio KodiConfig: %s' % str(e))
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = 'advancedsettings_%s.xml' % timestamp
        file_path = os.path.join(kodi_config_dir, filename)
        log('Guardando archivo: %s' % file_path)
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(config_content)
            if not os.path.exists(file_path):
                raise Exception('El archivo no se creó correctamente')
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
    try:
        dialog = xbmcgui.Dialog()
        log('Iniciando proceso de guardado en USB')
        if not os.path.exists(config_path):
            log('No existe configuración personalizada')
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
                    return
            else:
                log('Usuario canceló creación de configuración')
                return
        log('Detectando dispositivos USB')
        usb_devices = detect_usb_devices()
        if not usb_devices:
            log('Detección automática falló. Ofreciendo selector manual de carpeta USB')
            sel = browse_for_usb_folder()
            if sel:
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
        usb_options = []
        for i, usb in enumerate(usb_devices):
            label = '%s - %s libre (%s en %s)' % (
                usb['name'], usb.get('free', 'N/A'), usb.get('size', 'N/A'), usb['path'])
            usb_options.append(label)
            log('USB opción %d: %s' % (i, label))
        usb_selection = dialog.select('Seleccionar %s para Guardar' % device_label(), usb_options)
        if usb_selection == -1:
            log('Usuario canceló selección de USB')
            return
        selected_usb = usb_devices[usb_selection]
        log('USB seleccionado: %s' % selected_usb['path'])
        log('Leyendo configuración actual')
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_content = f.read()
            log('Configuración leída, %d caracteres' % len(config_content))
        except Exception as e:
            dialog.ok('Error', 'Error leyendo configuración: %s' % str(e))
            return
        confirm_msg = ('Guardar configuración en:\n\n%s: %s\nRuta: %s\nEspacio libre: %s\n\n¿Continuar?') % (
            device_label(), selected_usb['name'], selected_usb['path'], selected_usb.get('free', 'Desconocido'))
        if not dialog.yesno('Confirmar Guardado', confirm_msg, yeslabel='Guardar', nolabel='Cancelar'):
            log('Usuario canceló confirmación de guardado')
            return
        try:
            saved_file = save_buffering_to_usb(selected_usb['path'], config_content)
            result_msg = ('Configuración guardada exitosamente:\n\nArchivo: %s\nUbicación: %s\n\nPuedes usar este archivo para restaurar\nla configuración en otros equipos Kodi\ncopiándolo a:\n~/.kodi/userdata/advancedsettings.xml') % (
                             os.path.basename(saved_file), os.path.dirname(saved_file))
            dialog.ok('Guardado Completado', result_msg)
            log('Guardado completado exitosamente: %s' % saved_file)
        except Exception as e:
            error_msg = 'Error guardando en %s:\n\n%s\n\nVerifica que:\n• Sigue conectado\n• Hay espacio suficiente\n• Tienes permisos de escritura' % (device_label(), str(e))
            dialog.ok('Error de Guardado', error_msg)
            log('Error en guardado: %s' % str(e))
        if dialog.yesno('Usar %s para buffering' % device_label(),
                        '¿Deseas que Kodi use este %s como directorio de cache (cachepath)\n'
                        'para el buffering? Esto permite usar más espacio que la RAM.\n\n'
                        'Nota: El medio debe ser rápido y estar siempre conectado.' % device_label(),
                        yeslabel='Configurar', nolabel='No'):
            try:
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
                parent = os.path.dirname(config_path)
                try:
                    if parent and not os.path.exists(parent):
                        os.makedirs(parent, exist_ok=True)
                except Exception:
                    pass
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
                dialog.ok('Buffer externo configurado',
                          'Se configuró cachepath en:\n%s\n\nReinicia Kodi para aplicar los cambios.' % cache_dir)
                log('Cachepath configurado en externo: %s' % cache_dir)
            except Exception as e:
                log('Error configurando cachepath: %s' % str(e))
                dialog.ok('Error', 'Error configurando cache en almacenamiento externo: %s' % str(e))
    except Exception as e:
        log('Error general en save_buffering_config_to_usb: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error guardando en USB: %s' % str(e))

def configure_usb_cachepath(config_path):
    try:
        dialog = xbmcgui.Dialog()
        devices = detect_usb_devices()
        if not devices:
            sel = browse_for_usb_folder()
            if sel:
                devices = [{'name': os.path.basename(sel) or 'USB seleccionado', 'path': sel}]
        if not devices:
            dialog.ok('Sin %s' % device_label(), 'No se detectaron %s y no se seleccionó carpeta.' % device_label().lower())
            return
        labels = ['%s (%s)' % (d['path'], d.get('free', '')) for d in devices]
        idx = dialog.select('Selecciona %s para cache' % device_label(), labels)
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
        dialog.ok('Cache externa configurada', 'cachepath: %s\nReinicia Kodi para aplicar.' % cache_dir)
        log('cachepath configurado en: %s' % cache_dir)
    except Exception as e:
        log('Error configurando USB como cache: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error configurando cache en almacenamiento externo: %s' % str(e))

def configure_external_cachepath_android(config_path):
    try:
        if not is_android():
            return configure_usb_cachepath(config_path)
        dialog = xbmcgui.Dialog()
        devices = detect_usb_devices()
        if not devices:
            sel = browse_for_usb_folder()
            if sel:
                devices = [{'name': os.path.basename(sel) or 'Almacenamiento', 'path': sel}]
        if not devices:
            dialog.ok('Sin almacenamiento', 'No se detectaron ubicaciones y no se seleccionó carpeta.')
            return
        labels = ['%s (%s)' % (d['path'], d.get('free', '')) for d in devices]
        idx = dialog.select('Selecciona almacenamiento para cache', labels)
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
        dialog.ok('Cache externa configurada', 'cachepath: %s\nReinicia Kodi para aplicar.' % cache_dir)
        log('cachepath configurado en: %s' % cache_dir)
    except Exception as e:
        log('Error configurando cache externo Android: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error configurando cache externo: %s' % str(e))

def read_speed(urls=None, timeout=15):
    try:
        urls = urls or [
            'https://download.thinkbroadband.com/10MB.zip',
            'https://speedtest-fra1.digitalocean.com/10mb.test',
            'https://speedtest-nyc3.digitalocean.com/10mb.test',
            'https://speedtest-sgp1.digitalocean.com/10mb.test',
            'https://speed.hetzner.de/10MB.bin',
            'https://proof.ovh.net/files/10Mb.dat'
        ]
        total_read = 0
        start = time.time()
        for url in urls:
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Kodi-SpeedTest'})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    chunk = resp.read(1024 * 64)
                    total_read += len(chunk)
                    while total_read < 2 * 1024 * 1024:
                        chunk = resp.read(1024 * 64)
                        if not chunk:
                            break
                        total_read += len(chunk)
                break
            except Exception:
                continue
        elapsed = max(0.001, time.time() - start)
        mbps = (total_read * 8) / (elapsed * 1_000_000)
        return round(mbps, 2), total_read, elapsed
    except Exception as e:
        log('Error en read_speed: %s' % str(e))
        return 0.0, 0, 0.0

def choose_speed_server():
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

def speed_test_and_recommend(config_path, urls=None):
    try:
        dialog = xbmcgui.Dialog()
        dialog.notification('Aspirando Kodi', 'Iniciando test de velocidad...', time=3000)
        mbps, read_bytes, elapsed = read_speed(urls=urls)
        if mbps <= 0:
            dialog.ok('Test de velocidad', 'No se pudo medir la velocidad. Revisa tu conexión.')
            return
        if mbps <= 5:
            bufsize = 20 * 1024 * 1024; factor = 3.0
        elif mbps <= 20:
            bufsize = 50 * 1024 * 1024; factor = 4.0
        elif mbps <= 50:
            bufsize = 100 * 1024 * 1024; factor = 6.0
        else:
            bufsize = 200 * 1024 * 1024; factor = 8.0
        msg = ('Resultado del test:\n\n'
               'Velocidad estimada: %.2f Mbps\n'
               'Datos leídos: %.1f MB en %.1f s\n\n'
               'Recomendación:\n'
               '- Buffer en memoria: %s\n'
               '- ReadBufferFactor: %.1f\n\n'
               '¿Aplicar esta configuración?') % (
                mbps, read_bytes/1024/1024, elapsed, format_size(bufsize), factor)
        if not dialog.yesno('Test de velocidad', msg, yeslabel='Aplicar', nolabel='Cancelar'):
            return
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
</advancedsettings>''' % (bufsize, factor, bufsize, factor)
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

def test_usb_cachepath(config_path):
    try:
        dialog = xbmcgui.Dialog()
        cpath = read_cachepath_from_config(config_path)
        if not cpath:
            temp_root = special_temp_path()
            if os.path.islink(temp_root):
                if dialog.yesno('Sin cachepath (usando temp)',
                                 'No hay cachepath en advancedsettings.xml, pero special://temp está redirigido.\n\n'
                                 '¿Quieres probar escritura en special://temp/cache en su lugar?',
                                 yeslabel='Probar', nolabel='Cancelar'):
                    test_special_temp_cache_write()
                return
            dialog.ok('Prueba de cache', 'No hay cachepath configurado en advancedsettings.xml')
            return
        try:
            os.makedirs(cpath, exist_ok=True)
        except Exception:
            pass
        test_file = os.path.join(cpath, '.cache_test.txt')
        write_ok = False
        read_ok = False
        try:
            with open(test_file, 'w', encoding='utf-8') as f:
                f.write('kodi-cache-test')
            write_ok = True
        except Exception as e:
            log('Fallo de escritura en cachepath: %s' % str(e))
        if write_ok:
            try:
                with open(test_file, 'r', encoding='utf-8') as f:
                    data = f.read().strip()
                read_ok = (data == 'kodi-cache-test')
            except Exception as e:
                log('Fallo de lectura en cachepath: %s' % str(e))
        try:
            if os.path.exists(test_file):
                os.remove(test_file)
        except Exception:
            pass
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
        dialog.ok('Prueba de cache externa', '\n'.join(msg))
    except Exception as e:
        log('Error en test_usb_cachepath: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error en prueba de cache: %s' % str(e))

def remove_buffering_config(config_path):
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
                              'Configuración de buffering eliminada.\n\nKodi usará valores por defecto.')
            log('Configuración de buffering eliminada')
    except Exception as e:
        log('Error eliminando configuración: %s' % str(e))
        xbmcgui.Dialog().ok('Error', 'Error eliminando configuración: %s' % str(e))
