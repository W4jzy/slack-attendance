"""Shared runtime setup, independent of the current working directory."""
import locale
import logging
import os
import sys
import threading
from pathlib import Path

from dotenv import load_dotenv


def configure_logging():
    """Send application and uncaught exception logs to the service output."""
    level = getattr(logging, os.getenv('LOG_LEVEL', 'INFO').upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
        stream=sys.stderr,
    )
    def unhandled(exc_type, exc_value, traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, traceback)
            return
        logging.getLogger('runtime').critical(
            'Unhandled exception', exc_info=(exc_type, exc_value, traceback))
    def thread_error(args):
        logging.getLogger('runtime').critical(
            'Unhandled exception in thread %s', args.thread.name if args.thread else 'unknown',
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
    sys.excepthook = unhandled
    threading.excepthook = thread_error


def load_environment():
    load_dotenv(os.getenv('ATTENDANCE_ENV', Path(__file__).with_name('.env')))


def configure_locale():
    for name in ('cs_CZ.UTF-8', 'cs_CZ.utf8', 'Czech_Czechia.1250', ''):
        try:
            locale.setlocale(locale.LC_COLLATE, name)
            return
        except locale.Error:
            continue
    logging.getLogger(__name__).warning('Czech sorting locale unavailable; using default')
