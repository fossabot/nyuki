from contextlib import contextmanager

from tukio.task import TukioTaskError

from .placeholder_mapper import placeholder_mapper
from .selectors import generate_factory_schema


CONTACT_PROGRESS = 'contact-progress'


@contextmanager
def report_on_missing_data():
    try:
        yield
    except KeyError as exc:
        raise TukioTaskError({'missing_data': exc.args[0]})
