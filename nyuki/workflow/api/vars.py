import re
import logging
from pymongo.errors import AutoReconnect

from nyuki.api import Response, resource
from nyuki.workflow.validation import TemplateError


log = logging.getLogger(__name__)


class DataInspector(object):

    REGEX = [
        re.compile('{([a-zA-Z_\-]+)}', re.IGNORECASE),
        re.compile('@([a-zA-Z_\-]+)', re.IGNORECASE)
    ]

    @classmethod
    def iter(cls, node):
        if isinstance(node, dict):
            for value in node.values():
                yield from cls.iter(value)
        elif isinstance(node, list):
            for value in node:
                yield from cls.iter(value)
        else:
            yield node

    async def required_keys(self, tid, version=None, draft=False):
        template = await self.nyuki.storage.templates.get(
            tid=tid, version=version, draft=draft
        )
        if not template:
            raise TemplateError()
        template = template[0]
        keys = set()

        for task in template.get('tasks', []):
            for key, data in task.get('config', {}).items():
                # Get all evaluable inner-data
                for value in self.iter(data):
                    if not isinstance(value, str):
                        continue
                    for regex in self.REGEX:
                        for data_key in regex.findall(value):
                            keys.add(data_key)
        return list(keys)


@resource('/workflow/vars/{tid}', versions=['v1'])
class ApiVars(DataInspector):

    async def get(self, request, tid):
        try:
            keys = await self.required_keys(tid)
            return Response(body=keys)
        except TemplateError:
            return Response(status=404, body={'error': 'template not found'})
        except AutoReconnect:
            return Response(status=503)


@resource('/workflow/vars/{tid}/{version:\d+}', versions=['v1'])
class ApiVarsVersion(DataInspector):

    async def get(self, request, tid, version):
        try:
            keys = await self.required_keys(tid, version=version)
            return Response(body=keys)
        except TemplateError:
            return Response(status=404, body={'error': 'template not found'})
        except AutoReconnect:
            return Response(status=503)


@resource('/workflow/vars/{tid}/draft', versions=['v1'])
class ApiVarsDraft(DataInspector):

    async def get(self, request, tid):
        try:
            keys = await self.required_keys(tid, draft=True)
            return Response(body=keys)
        except TemplateError:
            return Response(status=404, body={'error': 'template not found'})
        except AutoReconnect:
            return Response(status=503)
