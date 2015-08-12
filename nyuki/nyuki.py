import signal
import threading
import logging
import logging.config

from nyuki.logging import DEFAULT_LOGGING
from nyuki.loop import EventLoop
from nyuki.bus import Bus


log = logging.getLogger(__name__)


class Nyuki(object):

    def __init__(self):
        # Let's assume we've fetch configs through the command line / conf file
        self.config = {
            'bus': {
                'host': 'prosody',
                'jid': 'test@localhost',
                'password': 'test'
            }
        }

        logging.config.dictConfig(DEFAULT_LOGGING)
        self._capabilities = dict()
        self._bus = Bus(**self.config['bus'])
        self._loop = EventLoop(loop=self._bus.loop)

    @property
    def event_loop(self):
        return self._loop

    @property
    def capabilities(self):
        return self._capabilities

    def _join(self):
        threads = threading.enumerate().remove(threading.main_thread()) or []
        for t in threads:
            t.join()

    def start(self):
        signal.signal(signal.SIGTERM, self.abort)
        signal.signal(signal.SIGINT, self.abort)
        self._bus.connect(block=True)

    def abort(self, signum=signal.SIGINT, frame=None):
        log.warning("Caught signal {}".format(signum))
        self.stop()

    def stop(self, timeout=5):
        self._bus.disconnect(timeout=timeout)
        self._join()
        log.info("Nyuki exiting")
