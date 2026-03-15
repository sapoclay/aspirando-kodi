import json
import os
import platform
import re
import shutil
import time
import urllib.parse
import urllib.request
import zipfile

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs


UPDATE_BASE_URL = 'https://sapoclay.github.io/aspirando-kodi/'
STATE_FILENAME = 'update_state.json'
DOWNLOADS_DIRNAME = 'updates'
BACKUPS_DIRNAME = 'addon_update_backups'
HTTP_TIMEOUT = 20

ARCH_ALIASES = {
    'arm64': {'arm64', 'aarch64'},
    'armv7': {'armv7', 'armv7l', 'armhf', 'arm'},
    'x64': {'x64', 'x86_64', 'amd64'},
    'x86': {'x86', 'i386', 'i686'},
}

AUTO_UPDATE_INTERVALS = {
    '0': 6 * 3600,
    '1': 12 * 3600,
    '2': 24 * 3600,
    '3': 3 * 24 * 3600,
    '4': 7 * 24 * 3600,
}

addon = xbmcaddon.Addon()
addon_id = addon.getAddonInfo('id')
addon_name = addon.getAddonInfo('name')
addon_path = addon.getAddonInfo('path')
addon_version = addon.getAddonInfo('version')

try:
    addon_data_dir = xbmcvfs.translatePath('special://profile/addon_data/%s' % addon_id)
except Exception:
    addon_data_dir = os.path.expanduser('~/.kodi/userdata/addon_data/%s' % addon_id)

state_path = os.path.join(addon_data_dir, STATE_FILENAME)
downloads_dir = os.path.join(addon_data_dir, DOWNLOADS_DIRNAME)
backups_dir = os.path.join(addon_data_dir, BACKUPS_DIRNAME)


def log(message, level=xbmc.LOGINFO):
    xbmc.log('[%s][updater] %s' % (addon_name, message), level)


def _ensure_dir(path):
    if not path:
        return
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)


def _read_json(path, default=None):
    if default is None:
        default = {}
    try:
        with open(path, 'r', encoding='utf-8') as file_handle:
            return json.load(file_handle)
    except Exception:
        return default


def _write_json(path, data):
    _ensure_dir(os.path.dirname(path))
    with open(path, 'w', encoding='utf-8') as file_handle:
        json.dump(data, file_handle, indent=2, ensure_ascii=False)


def _get_setting_bool(setting_id, default=False):
    try:
        value = addon.getSetting(setting_id)
    except Exception:
        value = ''
    if value in ('', None):
        return default
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def _get_setting_value(setting_id, default=''):
    try:
        value = addon.getSetting(setting_id)
    except Exception:
        value = ''
    if value in ('', None):
        return default
    return str(value)


def is_auto_update_enabled():
    return _get_setting_bool('auto_update_enabled', True)


def is_auto_install_enabled():
    return _get_setting_bool('auto_update_install', False)


def get_update_interval_seconds():
    raw_value = _get_setting_value('auto_update_interval', '2')
    if raw_value in AUTO_UPDATE_INTERVALS:
        return AUTO_UPDATE_INTERVALS[raw_value]
    if raw_value.isdigit():
        numeric = int(raw_value)
        if numeric > 60:
            return numeric
    return AUTO_UPDATE_INTERVALS['2']


def get_state():
    return _read_json(state_path, {})


def save_state(data):
    _write_json(state_path, data)


def _normalize_version(version):
    parts = re.findall(r'\d+', str(version or '0'))
    normalized = [int(part) for part in parts]
    while normalized and normalized[-1] == 0:
        normalized.pop()
    return tuple(normalized or [0])


def compare_versions(left, right):
    left_parts = list(_normalize_version(left))
    right_parts = list(_normalize_version(right))
    max_length = max(len(left_parts), len(right_parts))
    left_parts.extend([0] * (max_length - len(left_parts)))
    right_parts.extend([0] * (max_length - len(right_parts)))
    if left_parts < right_parts:
        return -1
    if left_parts > right_parts:
        return 1
    return 0


def detect_platform():
    os_name = 'linux'
    try:
        if xbmc.getCondVisibility('system.platform.android'):
            os_name = 'android'
        elif xbmc.getCondVisibility('system.platform.windows'):
            os_name = 'windows'
        elif xbmc.getCondVisibility('system.platform.osx'):
            os_name = 'osx'
        elif xbmc.getCondVisibility('system.platform.linux'):
            os_name = 'linux'
    except Exception:
        system_name = platform.system().lower()
        if 'android' in system_name:
            os_name = 'android'
        elif 'windows' in system_name:
            os_name = 'windows'
        elif system_name in ('darwin', 'mac', 'macos'):
            os_name = 'osx'
        else:
            os_name = 'linux'

    machine = platform.machine().lower()
    arch = 'x64'
    for arch_name, aliases in ARCH_ALIASES.items():
        if machine in aliases:
            arch = arch_name
            break

    pretty_name = {
        'android': 'Android',
        'linux': 'Linux',
        'windows': 'Windows',
        'osx': 'macOS',
    }.get(os_name, os_name)
    return {
        'os': os_name,
        'arch': arch,
        'machine': machine or 'unknown',
        'label': '%s (%s)' % (pretty_name, arch),
    }


def _absolute_url(path_or_url):
    if not path_or_url:
        return ''
    if re.match(r'^https?://', path_or_url):
        return path_or_url
    return urllib.parse.urljoin(UPDATE_BASE_URL, str(path_or_url).lstrip('/'))


def _fetch_text(url):
    request = urllib.request.Request(
        url,
        headers={'User-Agent': '%s/%s' % (addon_id, addon_version)},
    )
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
        charset = response.headers.get_content_charset() or 'utf-8'
        return response.read().decode(charset, 'replace')


def _extract_version_from_name(file_name):
    match = re.search(r'(\d+(?:\.\d+)+)', file_name)
    return match.group(1) if match else ''


def _find_release_from_index():
    index_text = _fetch_text(UPDATE_BASE_URL)
    zip_links = re.findall(r'href=["\']([^"\']+\.zip)["\']', index_text, re.IGNORECASE)
    candidates = []
    for link in zip_links:
        absolute_url = _absolute_url(link)
        package_name = os.path.basename(urllib.parse.urlparse(absolute_url).path)
        if addon_id not in package_name:
            continue
        remote_version = _extract_version_from_name(package_name)
        if not remote_version:
            continue
        candidates.append({
            'remote_version': remote_version,
            'download_url': absolute_url,
            'notes': '',
            'sha256': '',
            'package_name': package_name,
        })

    if not candidates:
        raise RuntimeError('No se encontraron paquetes remotos del addon en %s' % UPDATE_BASE_URL)

    candidates.sort(
        key=lambda item: (_normalize_version(item['remote_version']), item['package_name']),
        reverse=True,
    )
    return candidates[0]


def _resolve_remote_release():
    return _find_release_from_index()


def _download_file(url, target_path):
    request = urllib.request.Request(
        url,
        headers={'User-Agent': '%s/%s' % (addon_id, addon_version)},
    )
    _ensure_dir(os.path.dirname(target_path))
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response, open(target_path, 'wb') as output_handle:
        shutil.copyfileobj(response, output_handle)
    return target_path


def _hash_file_sha256(path):
    import hashlib

    digest = hashlib.sha256()
    with open(path, 'rb') as file_handle:
        while True:
            chunk = file_handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _addon_xml_matches(path):
    try:
        with open(path, 'r', encoding='utf-8') as file_handle:
            content = file_handle.read(4096)
        return ('id="%s"' % addon_id) in content or ("id='%s'" % addon_id) in content
    except Exception:
        return False


def _locate_extracted_addon_dir(extract_root):
    direct_addon_xml = os.path.join(extract_root, 'addon.xml')
    if os.path.exists(direct_addon_xml) and _addon_xml_matches(direct_addon_xml):
        return extract_root

    preferred_path = os.path.join(extract_root, addon_id)
    preferred_addon_xml = os.path.join(preferred_path, 'addon.xml')
    if os.path.exists(preferred_addon_xml) and _addon_xml_matches(preferred_addon_xml):
        return preferred_path

    for root, dirs, files in os.walk(extract_root):
        if 'addon.xml' not in files:
            continue
        addon_xml_path = os.path.join(root, 'addon.xml')
        if _addon_xml_matches(addon_xml_path):
            return root
    raise RuntimeError('El paquete descargado no contiene un addon.xml valido para %s' % addon_id)


def _extract_package(zip_path):
    extract_root = os.path.join(downloads_dir, 'extract_%d' % int(time.time()))
    if os.path.exists(extract_root):
        shutil.rmtree(extract_root, ignore_errors=True)
    _ensure_dir(extract_root)
    with zipfile.ZipFile(zip_path, 'r') as zip_file:
        zip_file.extractall(extract_root)
    addon_dir = _locate_extracted_addon_dir(extract_root)
    return extract_root, addon_dir


def _make_backup(source_dir):
    _ensure_dir(backups_dir)
    backup_path = os.path.join(backups_dir, 'backup_%s' % time.strftime('%Y%m%d_%H%M%S'))
    shutil.copytree(
        source_dir,
        backup_path,
        ignore=shutil.ignore_patterns('.git', '.venv', '__pycache__', 'dist', '*.pyc', '*.pyo'),
    )
    return backup_path


def _sync_tree(source_dir, target_dir):
    copied_files = 0
    for root, dirs, files in os.walk(source_dir):
        rel_root = os.path.relpath(root, source_dir)
        if rel_root == '.':
            rel_root = ''
        destination_root = target_dir if not rel_root else os.path.join(target_dir, rel_root)
        _ensure_dir(destination_root)
        for directory in dirs:
            _ensure_dir(os.path.join(destination_root, directory))
        for file_name in files:
            source_path = os.path.join(root, file_name)
            destination_path = os.path.join(destination_root, file_name)
            _ensure_dir(os.path.dirname(destination_path))
            shutil.copy2(source_path, destination_path)
            copied_files += 1
    return copied_files


def _cleanup_pycache(target_dir):
    for root, dirs, files in os.walk(target_dir):
        for directory in list(dirs):
            if directory == '__pycache__':
                shutil.rmtree(os.path.join(root, directory), ignore_errors=True)


def check_for_updates(force=False, ignore_ignored=False):
    platform_info = detect_platform()
    state = get_state()
    now = int(time.time())

    if not force:
        last_check_ts = int(state.get('last_check_ts', 0) or 0)
        if (now - last_check_ts) < get_update_interval_seconds() and state.get('last_result'):
            cached = dict(state.get('last_result', {}))
            ignored_version = str(state.get('ignored_version', '') or '').strip()
            remote_version = str(cached.get('remote_version', '') or '').strip()
            is_ignored = bool(remote_version and remote_version == ignored_version)
            cached['ignored'] = is_ignored and not ignore_ignored
            cached['available'] = bool(cached.get('available_remotely')) and (ignore_ignored or not is_ignored)
            cached['cached'] = True
            return cached

    try:
        release = _resolve_remote_release()
        remote_version = release.get('remote_version', '')
        available = compare_versions(addon_version, remote_version) < 0
        ignored_version = str(state.get('ignored_version', '') or '').strip()
        is_ignored = bool(remote_version and remote_version == ignored_version)
        result = {
            'ok': True,
            'cached': False,
            'available': available and (ignore_ignored or not is_ignored),
            'available_remotely': available,
            'ignored': is_ignored and not ignore_ignored,
            'current_version': addon_version,
            'remote_version': remote_version,
            'download_url': release.get('download_url', ''),
            'package_name': release.get('package_name', ''),
            'platform': platform_info['label'],
            'notes': release.get('notes', ''),
            'sha256': release.get('sha256', ''),
            'checked_at': now,
        }
        state['last_check_ts'] = now
        state['last_result'] = result
        state['last_error'] = ''
        save_state(state)
        return result
    except Exception as error:
        message = str(error)
        log('Error comprobando actualizaciones: %s' % message, xbmc.LOGERROR)
        state['last_check_ts'] = now
        state['last_error'] = message
        save_state(state)
        return {
            'ok': False,
            'cached': False,
            'available': False,
            'available_remotely': False,
            'ignored': False,
            'current_version': addon_version,
            'remote_version': '',
            'download_url': '',
            'package_name': '',
            'platform': platform_info['label'],
            'notes': '',
            'error': message,
            'checked_at': now,
        }


def ignore_version(version):
    state = get_state()
    state['ignored_version'] = str(version or '')
    last_result = state.get('last_result')
    if isinstance(last_result, dict) and str(last_result.get('remote_version', '') or '').strip() == str(version or '').strip():
        last_result['ignored'] = True
        last_result['available'] = False
        state['last_result'] = last_result
    save_state(state)


def clear_ignored_version():
    state = get_state()
    if 'ignored_version' in state:
        state.pop('ignored_version', None)
        last_result = state.get('last_result')
        if isinstance(last_result, dict) and last_result.get('available_remotely'):
            last_result['ignored'] = False
            last_result['available'] = True
            state['last_result'] = last_result
        save_state(state)


def install_update(update_info, interactive=True):
    if not update_info.get('download_url'):
        raise RuntimeError('No hay URL de descarga para la actualizacion')

    _ensure_dir(addon_data_dir)
    _ensure_dir(downloads_dir)

    package_name = update_info.get('package_name') or os.path.basename(
        urllib.parse.urlparse(update_info.get('download_url', '')).path
    )
    package_path = os.path.join(downloads_dir, package_name)
    extract_root = ''
    backup_path = ''

    try:
        if interactive:
            xbmcgui.Dialog().notification(addon_name, 'Descargando actualizacion %s...' % update_info.get('remote_version', ''), time=3000)
        log('Descargando paquete de actualizacion desde %s' % update_info.get('download_url', ''))
        _download_file(update_info.get('download_url', ''), package_path)

        expected_sha256 = str(update_info.get('sha256', '') or '').strip().lower()
        if expected_sha256:
            actual_sha256 = _hash_file_sha256(package_path).lower()
            if actual_sha256 != expected_sha256:
                raise RuntimeError('El hash SHA-256 del paquete no coincide con el esperado')

        extract_root, extracted_addon_dir = _extract_package(package_path)
        backup_path = _make_backup(addon_path)
        copied_files = _sync_tree(extracted_addon_dir, addon_path)
        _cleanup_pycache(addon_path)

        state = get_state()
        state['installed_version'] = update_info.get('remote_version', '')
        state['installed_at'] = int(time.time())
        state['ignored_version'] = ''
        state['last_installed_package'] = package_name
        save_state(state)

        try:
            xbmc.executebuiltin('UpdateLocalAddons')
        except Exception:
            pass

        log('Actualizacion instalada correctamente: %s (%d archivos)' % (update_info.get('remote_version', ''), copied_files))
        return {
            'ok': True,
            'remote_version': update_info.get('remote_version', ''),
            'package_name': package_name,
            'backup_path': backup_path,
            'copied_files': copied_files,
        }
    except Exception:
        if backup_path and os.path.exists(backup_path):
            try:
                _sync_tree(backup_path, addon_path)
                _cleanup_pycache(addon_path)
                log('Rollback aplicado desde %s' % backup_path, xbmc.LOGWARNING)
            except Exception as rollback_error:
                log('Error aplicando rollback: %s' % str(rollback_error), xbmc.LOGERROR)
        raise
    finally:
        if extract_root and os.path.exists(extract_root):
            shutil.rmtree(extract_root, ignore_errors=True)


def prompt_restart_after_update():
    platform_info = detect_platform()
    os_name = platform_info['os']
    if os_name in ('linux', 'windows'):
        if xbmcgui.Dialog().yesno('Actualizacion instalada', 'La actualizacion se ha instalado correctamente.\n\n¿Reiniciar Kodi ahora?', yeslabel='Reiniciar', nolabel='Mas tarde'):
            try:
                xbmc.executebuiltin('Dialog.Close(all,true)')
            except Exception:
                pass
            xbmc.executebuiltin('RestartApp')
            return True
        return False

    xbmcgui.Dialog().ok(
        'Actualizacion instalada',
        'La actualizacion se ha instalado correctamente.\n\nEn %s debes cerrar y volver a abrir Kodi para cargar la nueva version.' % platform_info['label'],
    )
    return False


def build_update_message(update_info):
    lines = [
        'Version actual: %s' % update_info.get('current_version', addon_version),
        'Version remota: %s' % update_info.get('remote_version', '?'),
        'Paquete: %s' % (update_info.get('package_name', '') or 'No especificado'),
        'Plataforma detectada: %s' % update_info.get('platform', detect_platform()['label']),
    ]
    notes = str(update_info.get('notes', '') or '').strip()
    if notes:
        lines.extend(['', 'Novedades:', notes])
    return '\n'.join(lines)