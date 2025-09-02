import xbmc
import xbmcgui
import xbmcaddon
import json
import os
import time

# Servicio de arranque: ejecuta limpieza si está programada
addon = xbmcaddon.Addon()
addon_id = addon.getAddonInfo('id')
addon_name = addon.getAddonInfo('name')

try:
    addon_data_dir = xbmc.translatePath('special://profile/addon_data/%s' % addon_id)
except Exception:
    addon_data_dir = os.path.expanduser('~/.kodi/userdata/addon_data/%s' % addon_id)

schedule_path = os.path.join(addon_data_dir, 'schedule_clean.json')


def log(msg):
    xbmc.log('[%s][service] %s' % (addon_name, msg), xbmc.LOGINFO)


def run_clean():
    try:
        # Importar funciones desde default.py mediante ejecución
        # Nota: en Kodi, default.py está en la ruta del addon
        import importlib.util
        import sys
        addon_path = addon.getAddonInfo('path')
        default_path = os.path.join(addon_path, 'default.py')
        spec = importlib.util.spec_from_file_location('aspirando_default', default_path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules['aspirando_default'] = mod
        spec.loader.exec_module(mod)

        # Mostrar aviso previo
        try:
            with open(schedule_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            planned = data.get('planned', {})
        except Exception:
            planned = {}

        summary_lines = [
            'Iniciando limpieza programada...',
            '',
            'Se eliminarán (estimado):'
        ]
        def fmt(cat):
            info = planned.get(cat, {})
            files = info.get('files', 0)
            size = info.get('size', 0)
            return '%s: %d archivos (%s)' % (cat.capitalize(), files, mod.format_size(size))
        for c in ['cache', 'thumbnails', 'packages', 'temp']:
            summary_lines.append(fmt(c))
        text = '\n'.join(summary_lines)
        xbmcgui.Dialog().notification(addon_name, 'Limpieza programada iniciada', time=4000)
        xbmcgui.Dialog().textviewer('Limpieza Programada', text)
        xbmc.sleep(1000)

        # Ejecutar limpieza completa
        mod.clean_all()
        log('Limpieza programada ejecutada')
    except Exception as e:
        log('Error en limpieza programada: %s' % str(e))
        xbmcgui.Dialog().ok(addon_name, 'Error en limpieza programada: %s' % str(e))


class StartupMonitor(xbmc.Monitor):
    def __init__(self):
        super().__init__()
        self.started = False

    def onSettingsChanged(self):
        pass

class PlaybackMonitor(xbmc.Player):
    def __init__(self, mod):
        super().__init__()
        self.mod = mod
        self.was_playing = False

    def onAVStart(self):
        self.was_playing = True

    def onPlayBackStarted(self):
        self.was_playing = True

    def onPlayBackStopped(self):
        self._maybe_autoclean()

    def onPlayBackEnded(self):
        self._maybe_autoclean()

    def _maybe_autoclean(self):
        try:
            if self.mod.get_usb_autoclean_enabled():
                # Usar advancedsettings del perfil
                paths = self.mod.get_kodi_paths()
                cfg = paths.get('advancedsettings', '')
                self.mod.clean_usb_cachepath(cfg)
        except Exception as e:
            log('Auto-limpieza cache USB falló: %s' % str(e))


if __name__ == '__main__':
    try:
        # Esperar a que Kodi esté listo
        monitor = StartupMonitor()
        # Dar unos segundos de margen para que inicialice UI
        for _ in range(20):
            if monitor.abortRequested():
                break
            xbmc.sleep(250)
        
        # Comprobar si hay limpieza programada
        if os.path.exists(schedule_path):
            try:
                with open(schedule_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if data.get('scheduled'):
                    run_clean()
            finally:
                # Borrar programación para que no se repita
                try:
                    os.remove(schedule_path)
                except Exception:
                    pass
        else:
            log('Sin limpieza programada')

        # Cargar módulo principal para utilidades y activar monitor de reproducción
        try:
            import importlib.util, sys
            addon_path = addon.getAddonInfo('path')
            default_path = os.path.join(addon_path, 'default.py')
            spec = importlib.util.spec_from_file_location('aspirando_default', default_path)
            mod = importlib.util.module_from_spec(spec)
            sys.modules['aspirando_default'] = mod
            spec.loader.exec_module(mod)
            player = PlaybackMonitor(mod)
        except Exception as e:
            log('No se pudo iniciar PlaybackMonitor: %s' % str(e))

        # Bucle de servicio
        while not monitor.abortRequested():
            xbmc.sleep(500)
    except Exception as e:
        log('Error en servicio: %s' % str(e))
