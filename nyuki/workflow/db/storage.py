import logging
from copy import deepcopy

from motor.motor_asyncio import AsyncIOMotorClient

from .triggers import TriggerCollection
from .data_processing import DataProcessingCollection
from .metadata import MetadataCollection
from .workflow_templates import WorkflowTemplatesCollection, TemplateState
from .task_templates import TaskTemplatesCollection
from .workflow_instances import WorkflowInstancesCollection
from .task_instances import TaskInstancesCollection


log = logging.getLogger(__name__)


class MongoStorage:

    def __init__(self):
        self._client = None
        self._db = None

        # Collections
        self._workflow_templates = None
        self._task_templates = None
        self._regexes = None
        self._lookups = None
        self._triggers = None
        self._metadata = None
        self._workflow_instances = None
        self._task_instances = None

    def configure(self, host, database, **kwargs):
        log.info("Setting up workflow mongo storage with host '%s'", host)
        self._client = AsyncIOMotorClient(host, **kwargs)
        self._db = self._client[database]
        log.info("Workflow database: '%s'", database)

        # Collections
        self._workflow_templates = WorkflowTemplatesCollection(self._db)
        self._task_templates = TaskTemplatesCollection(self._db)
        self._metadata = MetadataCollection(self._db)
        self._triggers = TriggerCollection(self._db)
        # self._regexes = DataProcessingCollection(self._db, 'regexes')
        # self._lookups = DataProcessingCollection(self._db, 'lookups')
        # self._workflow_instances = WorkflowInstancesCollection(self._db)
        # self._task_instances = TaskInstancesCollection(self._db)

    async def update_metadata(self, tid, metadata):
        """
        Update and return
        """
        return await self._metadata.update(tid, metadata)

    async def update_draft(self, template):
        """
        Update a template's draft and all its associated tasks.
        """
        metadata = await self._metadata.get_one(template['id'])
        if not metadata:
            metadata = {
                'workflow_template_id': template['id'],
                'title': template.pop('title'),
                'tags': template.pop('tags', []),
            }
            await self._metadata.insert(metadata)

        # Force set of values 'version' and 'draft'.
        template['version'] = await self._workflow_templates.get_last_version(
            template['id']
        ) + 1
        template['state'] = TemplateState.DRAFT.value

        # Split and insert tasks.
        tasks = template.pop('tasks')
        await self._task_templates.insert_many(deepcopy(tasks), template)

        # Insert template without tasks.
        await self._workflow_templates.insert_draft(template)
        template['tasks'] = tasks
        template.update({'title': metadata['title'], 'tags': metadata['tags']})
        return template

    async def publish_draft(self, template_id):
        """
        Publish a draft into an 'active' state, and archive the old active.
        """
        await self._workflow_templates.publish(template_id)
        log.info('Draft for template %s published', template_id[:8])

    async def get_for_topic(self, topic):
        """
        Return all the templates listening on a particular topic.
        This does not append the metadata.
        """
        templates = await self._workflow_templates.get_for_topic(topic)
        if templates:
            log.info(
                'Fetched %s templates for event from "%s"',
                len(templates), topic,
            )
        for template in templates:
            template['tasks'] = await self._task_templates.get(
                template['id'], template['version']
            )
        return templates

    async def get_templates(self, template_id=None, full=False):
        """
        Return all active/draft templates
        Limited to a small set of fields if 'full' is False.
        TODO: Pagination.
        """
        templates = await self._workflow_templates.get(template_id, full)
        for template in templates:
            metadata = await self._metadata.get_one(template['id'])
            template.update(metadata)
            if full is True:
                template['tasks'] = await self._task_templates.get(
                    template['id'], template['version']
                )
        return templates

    async def get_template(self, tid, draft=False, version=None):
        """
        Return the active template.
        """
        template = await self._workflow_templates.get_one(
            tid,
            draft=draft,
            version=int(version) if version else None,
        )
        if not template:
            return

        metadata = await self._metadata.get_one(tid)
        template.update(metadata)
        template['tasks'] = await self._task_templates.get(
            template['id'], template['version']
        )
        return template

    async def delete_template(self, tid, draft=False):
        """
        Delete a whole template or only its draft.
        """
        await self._workflow_templates.delete(tid, draft)
        if draft is False:
            await self._task_templates.delete_many(tid)
            await self._metadata.delete(tid)
            await self._triggers.delete(tid)
