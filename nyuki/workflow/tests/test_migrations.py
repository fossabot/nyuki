import os
import asyncio
from copy import deepcopy
from unittest import TestCase
from unittest.mock import MagicMock, patch

from nyuki.workflow.api.templates import TemplateCollection


class AsyncMock(MagicMock):

    """
    Enable the python3.5 'await' call to a magicmock
    """

    async def __call__(self, *args, **kwargs):
        return super(AsyncMock, self).__call__(*args, **kwargs)


TEMPLATES = {
    '1.0': {
        'id': 'workflow-template-uid',
        'title': 'test',
        'policy': 'start-new',
        'draft': True,
        'graph': {'1': []},
        'tasks': [
            {'id': '1', 'name': 'trigger_workflow', 'config': {
                'nyuki_api': 'pipeline/api',
                'template': 'task-template-uid',
                'draft': False,
                'timeout': 6000,
            }}
        ],
    }
}


class MigrationTests(TestCase):

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()

    def test_trigger_4_0(self):
        os.environ['SURYCAT_VERSION'] = '4.0'
        async def test():
            template = deepcopy(TEMPLATES['1.0'])
            await TemplateCollection._migrate(AsyncMock(), template)
            self.assertEquals(template['surycat_version'], '4.0')
            config = template['tasks'][0]['config']
            self.assertEquals(config['template']['service'], 'pipeline')
            self.assertEquals(config['template']['id'], 'task-template-uid')
            self.assertEquals(config['template']['draft'], False)
            self.assertEquals(config['blocking']['timeout'], 6000)
        self.loop.run_until_complete(test())

    def test_trigger_4_0_no_timeout(self):
        os.environ['SURYCAT_VERSION'] = '4.0'
        async def test():
            template = deepcopy(TEMPLATES['1.0'])
            del template['tasks'][0]['config']['timeout']
            await TemplateCollection._migrate(AsyncMock(), template)
            self.assertEquals(template['surycat_version'], '4.0')
            config = template['tasks'][0]['config']
            self.assertEquals(config['template']['service'], 'pipeline')
            self.assertEquals(config['template']['id'], 'task-template-uid')
            self.assertEquals(config['template']['draft'], False)
            self.assertNotIn('blocking', config)
        self.loop.run_until_complete(test())
