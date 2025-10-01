import xbmc
import xbmcgui
import xbmcaddon
import json
import os
import time
import xbmcvfs

# Servicio de arranque: ejecuta limpieza si está programada
addon = xbmcaddon.Addon()
addon_id = addon.getAddonInfo('id')
addon_name = addon.getAddonInfo('name')

try:
    addon_data_dir = xbmcvfs.translatePath('special://profile/addon_data/%s' % addon_id)
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
                    # Si no es repetitivo, desactivar para próximos inicios
                    if not data.get('repeat', False):
                        try:
                            os.remove(schedule_path)
                        except Exception:
                            pass
            except Exception as e:
                log('Error leyendo programación: %s' % str(e))
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

        # Watchdog Android: detectar bloqueo de PVR tras activar Timeshift y problemas de memoria
        try:
            is_android = xbmc.getCondVisibility('system.platform.android')
        except Exception:
            is_android = False

        # Verificar si el usuario ya manejó el problema de PVR en Android
        android_pvr_handled_file = os.path.join(addon_data_dir, 'android_pvr_handled.flag')
        android_pvr_already_handled = os.path.exists(android_pvr_handled_file)
        
        # NUEVO: Monitor de memoria en Android para evitar cuelgues
        if is_android:
            try:
                # Verificar configuración de buffering segura para Android
                import importlib.util, sys
                addon_path = addon.getAddonInfo('path')
                default_path = os.path.join(addon_path, 'default.py')
                spec = importlib.util.spec_from_file_location('aspirando_default', default_path)
                mod = importlib.util.module_from_spec(spec)
                sys.modules['aspirando_default'] = mod
                spec.loader.exec_module(mod)
                
                # Obtener paths
                paths = mod.get_kodi_paths()
                cfg = paths.get('advancedsettings', '')
                
                if os.path.exists(cfg):
                    # Leer configuración actual
                    try:
                        with open(cfg, 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                        # Verificar si hay buffer excesivo (>80MB es peligroso en Android)
                        import re
                        mem_match = re.search(r'<cachemembuffersize>(\d+)</cachemembuffersize>', content)
                        if mem_match:
                            mem_size = int(mem_match.group(1))
                            # Si el buffer es mayor a 80MB, avisar
                            if mem_size > 83886080:  # 80MB
                                dlg = xbmcgui.Dialog()
                                if dlg.yesno('Advertencia: Buffer Alto en Android',
                                            'Se detectó buffer de %s en memoria.\n'
                                            'En Android esto puede causar cuelgues\n'
                                            'tras 2-3 minutos de reproducción.\n\n'
                                            '¿Reducir a un valor seguro (50MB)?' % mod.format_size(mem_size),
                                            yeslabel='Sí, reducir', nolabel='Dejar así'):
                                    # Aplicar perfil Android seguro
                                    safe_config = '''<advancedsettings>
    <network>
        <buffermode>1</buffermode>
        <cachemembuffersize>52428800</cachemembuffersize>
        <readbufferfactor>3.2</readbufferfactor>
    </network>
    <video>
        <memorysize>52428800</memorysize>
        <readbufferfactor>3.2</readbufferfactor>
    </video>
    <cache>
    </cache>
</advancedsettings>'''
                                    # Backup
                                    try:
                                        mod.backup_advancedsettings(cfg)
                                    except Exception:
                                        pass
                                    
                                    # Escribir configuración segura
                                    try:
                                        with open(cfg, 'w', encoding='utf-8') as f:
                                            f.write(safe_config)
                                        dlg.ok('Buffer Reducido',
                                              'Se aplicó configuración segura (50MB).\n'
                                              'Reinicia Kodi para aplicar cambios.')
                                        log('Buffer reducido a 50MB por seguridad en Android')
                                    except Exception as e:
                                        log('Error reduciendo buffer: %s' % str(e))
                    except Exception as e:
                        log('Error verificando buffer en Android: %s' % str(e))
            except Exception as e:
                log('Error en monitor de memoria Android: %s' % str(e))

        if is_android and not android_pvr_already_handled:
            try:
                # Esperar a que Kodi esté completamente iniciado
                log('Android detectado: esperando a que PVR cargue...')
                
                # Dar más tiempo para que Kodi y los addons se inicialicen completamente
                start = time.time()
                has_channels = False
                pvr_addon_enabled = False
                initialization_time = 180  # Aumentado a 180 segundos (3 minutos)
                
                while not monitor.abortRequested() and (time.time() - start) < initialization_time:
                    # Verificar si IPTV Simple está habilitado
                    try:
                        pvr_addon_enabled = xbmc.getCondVisibility('System.HasAddon(pvr.iptvsimple)')
                    except Exception:
                        pvr_addon_enabled = False
                    
                    # Solo verificar canales si el addon PVR está habilitado
                    if pvr_addon_enabled:
                        try:
                            has_tv = xbmc.getCondVisibility('PVR.HasTVChannels')
                            has_radio = xbmc.getCondVisibility('PVR.HasRadioChannels')
                            has_channels = bool(has_tv or has_radio)
                            
                            if has_channels:
                                log('PVR canales detectados correctamente')
                                break
                        except Exception:
                            pass
                    
                    # Mostrar progreso cada 20 segundos
                    elapsed = int(time.time() - start)
                    if elapsed % 20 == 0 and elapsed > 0:
                        log(f'Esperando PVR... {elapsed}s de {initialization_time}s')
                    
                    xbmc.sleep(3000)  # Verificar cada 3 segundos para dar más tiempo

                # Solo mostrar diálogo si hay un addon PVR habilitado pero sin canales
                if pvr_addon_enabled and not has_channels:
                    # Posible bloqueo por Timeshift/almacenamiento en Android
                    dlg = xbmcgui.Dialog()
                    choice = dlg.select('PVR bloqueado en Android', [
                        'Deshabilitar IPTV Simple ahora (recomendado)',
                        'Ajustar buffering a RAM y reiniciar',
                        'No hacer nada'
                    ])
                    
                    # Crear bandera para indicar que el usuario ya manejó este problema
                    try:
                        if not os.path.exists(addon_data_dir):
                            os.makedirs(addon_data_dir, exist_ok=True)
                        with open(android_pvr_handled_file, 'w') as f:
                            f.write('handled')
                    except Exception as e:
                        log('No se pudo crear archivo de bandera: %s' % str(e))
                    
                    if choice == 0:
                        try:
                            xbmc.executebuiltin('DisableAddon(pvr.iptvsimple)')
                            xbmc.sleep(800)
                            dlg.notification(addon_name, 'IPTV Simple deshabilitado. Revisa Timeshift y vuelve a habilitar.', time=5000)
                        except Exception as e:
                            log('No se pudo deshabilitar pvr.iptvsimple: %s' % str(e))
                    elif choice == 1:
                        try:
                            # Escribir advancedsettings para usar RAM (50MB)
                            # Cargar utilidades de default.py si están disponibles
                            try:
                                import importlib.util, sys
                                addon_path = addon.getAddonInfo('path')
                                default_path = os.path.join(addon_path, 'default.py')
                                spec = importlib.util.spec_from_file_location('aspirando_default', default_path)
                                mod = importlib.util.module_from_spec(spec)
                                sys.modules['aspirando_default'] = mod
                                spec.loader.exec_module(mod)
                            except Exception:
                                mod = None

                            if mod and hasattr(mod, 'get_kodi_paths'):
                                paths = mod.get_kodi_paths()
                                cfg = paths.get('advancedsettings', '')
                            else:
                                # Ruta por defecto del perfil
                                try:
                                    cfg = xbmcvfs.translatePath('special://profile/advancedsettings.xml')
                                except Exception:
                                    cfg = os.path.expanduser('~/.kodi/userdata/advancedsettings.xml')

                            # Copia de seguridad si es posible
                            try:
                                if mod and hasattr(mod, 'backup_advancedsettings'):
                                    mod.backup_advancedsettings(cfg)
                            except Exception:
                                pass

                            content = '''<advancedsettings>
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
    </cache>
</advancedsettings>'''
                            # Asegurar directorio
                            parent = os.path.dirname(cfg)
                            try:
                                if parent and not os.path.exists(parent):
                                    os.makedirs(parent, exist_ok=True)
                            except Exception:
                                pass
                            try:
                                with open(cfg, 'w', encoding='utf-8') as f:
                                    f.write(content)
                            except Exception:
                                fh = xbmcvfs.File(cfg, 'w')
                                fh.write(content)
                                fh.close()
                            if dlg.yesno('Buffering a RAM aplicado', 'Se aplicaron valores seguros (RAM).\n¿Reiniciar Kodi ahora?', yeslabel='Reiniciar', nolabel='Luego'):
                                xbmc.executebuiltin('RestartApp')
                        except Exception as e:
                            log('Error ajustando buffering seguro: %s' % str(e))
                else:
                    # PVR funcionando correctamente o no hay addon PVR habilitado
                    if not pvr_addon_enabled:
                        log('No hay addon PVR habilitado, omitiendo verificación')
                    else:
                        log('PVR funcionando correctamente')
                    
                    # Crear bandera para evitar verificaciones futuras innecesarias
                    try:
                        if not os.path.exists(addon_data_dir):
                            os.makedirs(addon_data_dir, exist_ok=True)
                        with open(android_pvr_handled_file, 'w') as f:
                            f.write('pvr_working_correctly')
                    except Exception as e:
                        log('No se pudo crear archivo de bandera (PVR OK): %s' % str(e))
            except Exception as e:
                log('Watchdog Android falló: %s' % str(e))

        # Bucle de servicio
        while not monitor.abortRequested():
            xbmc.sleep(500)
    except Exception as e:
        log('Error en servicio: %s' % str(e))
