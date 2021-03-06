import os
import asyncio
import logging
import configparser
from contextlib import suppress

from ib_insync.objects import Object
from ib_insync.contract import Forex
from ib_insync.ib import IB
import ib_insync.util as util

__all__ = ['IBC', 'IBController', 'Watchdog']


class IBC(Object):
    """
    Programmatic control over starting and stopping TWS/Gateway
    using IBC (https://github.com/IbcAlpha/IBC).
    
    Arguments:
    
    * ``twsVersion`` (required): The major version number for TWS or gateway.
    * ``tradingMode``: 'live' or 'paper'.
    * ``userid``: IB account username. It is recommended to set the real
      username/password in a secured IBC config file.
    * ``password``: IB account password.
    * ``twsPath``: Path to the TWS installation folder.
    
      =======  ==============
      Default
      =======================
      Linux    ~/Jts
      OS X     ~/Applications
      Windows  C:\\\\Jts
      =======  ==============
      
    * ``twsSettingsPath``: Path to the TWS settings folder.
    
      ========  =============
      Default
      =======================
      Linux     ~/Jts
      OS X      ~/Jts
      Windows   Not available
      ========  =============
      
    * ``ibcPath``: Path to the IBC installation folder.
    
      ========  =============
      Default
      =======================
      Linux     /opt/ibc
      OS X      /opt/ibc
      Windows   C:\\\\IBC
      ========  =============
      
    * ``ibcIni``: Path to the IBC configuration file.
    
      ========  =============
      Default
      =======================
      Linux     ~/ibc/config.ini
      OS X      ~/ibc/config.ini
      Windows   %%HOMEPATH%%\\\\Documents\\\\IBC\\\\config.ini
      ========  =============
      
    * ``javaPath``: Path to Java executable.
      Default is to use the Java VM included with TWS/gateway.
    * ``fixuserid``: FIX account user id (gateway only).
    * ``fixpassword``: FIX account password (gateway only).
    
    To use IBC on Windows, the the proactor event loop must have been set:
    
    .. code-block:: python
        
        import asyncio
        asyncio.set_event_loop(asyncio.ProactorEventLoop())
    
    Example usage:
    
    .. code-block:: python
    
        ibc = IBC(969, gateway=True, tradingMode='live',
                userid='edemo', password='demouser')
        ibc.start()
        IB.run()
    """

    IbcLogLevel = logging.DEBUG

    _Args = dict(
        # key=(Default, UnixArg, WindowsArg)
        twsVersion=(None, '', ''),
        gateway=(None, '--gateway', '/Gateway'),
        tradingMode=(None, '--mode=', '/Mode:'),
        twsPath=(None, '--tws-path=', '/TwsPath:'),
        twsSettingsPath=(None, '--tws-settings-path=', ''),
        ibcPath=(None, '--ibc-path=', '/IbcPath:'),
        ibcIni=(None, '--ibc-ini=', '/Config:'),
        javaPath=(None, '--java-path=', '/JavaPath:'),
        userid=(None, '--user=', '/User:'),
        password=(None, '--pw=', '/PW:'),
        fixuserid=(None, '--fix-user=', '/FIXUser:'),
        fixpassword=(None, '--fix-pw=', '/FIXPW:'))

    defaults = {k: v[0] for k, v in _Args.items()}
    __slots__ = list(defaults) + ['_proc', '_logger', '_monitor']

    def __init__(self, *args, **kwargs):
        Object.__init__(self, *args, **kwargs)
        if not self.ibcPath:
            self.ibcPath = '/opt/ibc' if os.sys.platform != 'win32' \
                    else 'C:\\IBC'
        self._proc = None
        self._monitor = None
        self._logger = logging.getLogger('ib_insync.IBC')

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_exc):
        self.terminate()

    def start(self):
        """
        Launch TWS/IBG.
        """
        util.syncAwait(self.startAsync())

    def terminate(self):
        """
        Terminate TWS/IBG.
        """
        util.syncAwait(self.terminateAsync())

    async def startAsync(self):
        if self._proc:
            return
        self._logger.info('Starting')

        # create shell command
        win32 = os.sys.platform == 'win32'
        l = [f'{self.ibcPath}\\scripts\\StartIBC.bat' if win32 else
            f'{self.ibcPath}/scripts/ibcstart.sh']
        for k, v in self.dict().items():
            arg = IBC._Args[k][2 if win32 else 1]
            if v:
                if arg.endswith('=') or arg.endswith(':'):
                    l.append(f'{arg}{v}')
                elif arg:
                    l.append(arg)
                else:
                    l.append(str(v))
        cmd = ' '.join(l)

        # run shell command
        self._proc = await asyncio.create_subprocess_shell(cmd,
                env=os.environ,
                stdout=asyncio.subprocess.PIPE)
        self._monitor = asyncio.ensure_future(self.monitorAsync())

    async def terminateAsync(self):
        if not self._proc:
            return
        self._logger.info('Terminating')
        with suppress(ProcessLookupError):
            self._proc.terminate()
            await self._proc.wait()
        self._proc = None
        self._monitor.cancel()
        self._monitor = None

    async def monitorAsync(self):
        while self._proc:
            line = await self._proc.stdout.readline()
            if not line:
                break
            self._logger.log(IBC.IbcLogLevel, line.strip().decode())


class IBController(Object):
    """
    For new installations it is recommended to use IBC instead.
    
    Programmatic control over starting and stopping TWS/Gateway
    using IBController (https://github.com/ib-controller/ib-controller).
    
    On Windows the the proactor event loop must have been set:
    
    .. code-block:: python
        
        import asyncio
        asyncio.set_event_loop(asyncio.ProactorEventLoop())

    """
    defaults = dict(
        APP='TWS',  # 'TWS' or 'GATEWAY'
        TWS_MAJOR_VRSN='969',
        TRADING_MODE='live',  # 'live' or 'paper'
        IBC_INI='~/IBController/IBController.ini',
        IBC_PATH='~/IBController',
        TWS_PATH='~/Jts',
        LOG_PATH='~/IBController/Logs',
        TWSUSERID='',
        TWSPASSWORD='',
        JAVA_PATH='',
        TWS_CONFIG_PATH='')
    __slots__ = list(defaults) + ['_proc', '_logger', '_monitor']

    def __init__(self, *args, **kwargs):
        Object.__init__(self, *args, **kwargs)
        self._proc = None
        self._monitor = None
        self._logger = logging.getLogger('ib_insync.IBController')

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_exc):
        self.terminate()

    def start(self):
        """
        Launch TWS/IBG.
        """
        util.syncAwait(self.startAsync())

    def stop(self):
        """
        Cleanly shutdown TWS/IBG.
        """
        util.syncAwait(self.stopAsync())

    def terminate(self):
        """
        Terminate TWS/IBG.
        """
        util.syncAwait(self.terminateAsync())

    async def startAsync(self):
        if self._proc:
            return
        self._logger.info('Starting')

        # expand paths
        d = self.dict()
        for k, v in d.items():
            if k.endswith('_PATH') or k.endswith('_INI'):
                d[k] = os.path.expanduser(v)
        if not d['TWS_CONFIG_PATH']:
            d['TWS_CONFIG_PATH'] = d['TWS_PATH']
        self.update(**d)

        # run shell command
        ext = 'bat' if os.sys.platform == 'win32' else 'sh'
        cmd = f'{d["IBC_PATH"]}/Scripts/DisplayBannerAndLaunch.{ext}'
        env = {**os.environ, **d}
        self._proc = await asyncio.create_subprocess_shell(cmd, env=env,
                stdout=asyncio.subprocess.PIPE)
        self._monitor = asyncio.ensure_future(self.monitorAsync())

    async def stopAsync(self):
        if not self._proc:
            return
        self._logger.info('Stopping')

        # read ibcontroller ini file to get controller port
        txt = '[section]' + open(self.IBC_INI).read()
        config = configparser.ConfigParser()
        config.read_string(txt)
        contrPort = config.getint('section', 'IbControllerPort')

        _reader, writer = await asyncio.open_connection('127.0.0.1', contrPort)
        writer.write(b'STOP')
        await writer.drain()
        writer.close()
        await self._proc.wait()
        self._proc = None
        self._monitor.cancel()
        self._monitor = None

    async def terminateAsync(self):
        if not self._proc:
            return
        self._logger.info('Terminating')
        with suppress(ProcessLookupError):
            self._proc.terminate()
            await self._proc.wait()
        self._proc = None
        self._monitor.cancel()
        self._monitor = None

    async def monitorAsync(self):
        while self._proc:
            line = await self._proc.stdout.readline()
            if not line:
                break
            self._logger.info(line.strip().decode())


class Watchdog(Object):
    """
    Start, connect and watch over the TWS or gateway app to keep it running
    in the face of crashes, freezes and network outages.
    
    The idea is to wait until there is no traffic coming from the app for
    a certain amount of time (the ``appTimeout`` parameter). This triggers
    a historical request to be placed just to see if the app is still alive
    and well. If yes, then continue, if no then restart the whole app
    and reconnect. Restarting will also occur directly on error 1100.
    
    Arguments:
    
    * ``controller``: IBC or IBController instance;
    * ``host``, ``port``, ``clientId`` and ``connectTimeout``: Used for
      connecting to the app;
    * ``appStartupTime``: Time (in seconds) that the app is given to start up.
      Make sure that it is given ample time;
    * ``appTimeout``: Timeout (in seconds) for network traffic idle time;
    * ``retryDelay``: Time (in seconds) to restart app after a previous failure.
    
    Note: ``util.patchAsyncio()`` must have been called before.
    
    Example usage:
    
    .. code-block:: python
    
        util.patchAsyncio()

        ibc = IBC(969, gateway=True, tradingMode='paper')
        app = Watchdog(ibc, port=4002)
        app.start()
        IB.run()
        
    """
    defaults = dict(
        controller=None,
        host='127.0.0.1',
        port='7497',
        clientId=1,
        connectTimeout=2,
        ib=None,
        appStartupTime=30,
        appTimeout=20,
        retryDelay=1)
    __slots__ = list(defaults.keys()) + ['_watcher', '_logger']

    def __init__(self, *args, **kwargs):
        Object.__init__(self, *args, **kwargs)
        assert self.controller
        assert 0 < self.appTimeout < 60
        assert self.retryDelay > 0
        if self.ib is None:
            self.ib = IB()
        self.ib.client.apiError = self.onApiError
        self.ib.setCallback('error', self.onError)
        self._watcher = asyncio.ensure_future(self.watchAsync())
        self._logger = logging.getLogger('ib_insync.Watchdog')

    def start(self):
        self._logger.info('Starting')
        self.controller.start()
        IB.sleep(self.appStartupTime)
        try:
            self.ib.connect(self.host, self.port, self.clientId,
                    self.connectTimeout)
            self.ib.setTimeout(self.appTimeout)
        except:
            # a connection failure will be handled by the apiError callback
            pass

    def stop(self):
        self._logger.info('Stopping')
        self.ib.disconnect()
        self.controller.terminate()

    def scheduleRestart(self):
        self._logger.info(f'Schedule restart in {self.retryDelay}s')
        loop = asyncio.get_event_loop()
        loop.call_later(self.retryDelay, self.start)

    def onApiError(self, msg):
        self.stop()
        self.scheduleRestart()

    def onError(self, reqId, errorCode, errorString, contract):
        if errorCode == 1100:
            self._logger.info(f'Error 1100: {errorString}')
            self.stop()
            self.scheduleRestart()

    async def watchAsync(self):
        while True:
            await self.ib.wrapper.timeoutEvent.wait()
            # soft timeout, probe the app with a historical request
            contract = Forex('EURUSD')
            probe = self.ib.reqHistoricalDataAsync(
                    contract, '', '30 S', '5 secs', 'MIDPOINT', False)
            try:
                bars = await asyncio.wait_for(probe, 4)
                if not bars:
                    raise Exception()
                self.ib.setTimeout(self.appTimeout)
            except:
                # hard timeout, flush everything and start anew
                self._logger.error('Hard timeout')
                self.stop()
                self.scheduleRestart()


if __name__ == '__main__':
    util.logToConsole()
    util.patchAsyncio()
    ibc = IBC(969, gateway=True, tradingMode='paper')
#             userid='edemo', password='demouser')
    app = Watchdog(ibc, port=4002)
    app.start()
    IB.run()
