"""Shared runtime setup, independent of the current working directory."""
import locale
import logging
import os
from pathlib import Path

from dotenv import load_dotenv


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
