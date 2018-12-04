# -*- coding: utf-8 -*-
# Copyright 2018 ACSONE SA/NV
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from openerp.addons.connector.event import on_record_create, on_record_write
from openerp.addons.connector.queue.job import job

import logging
logger = logging.getLogger(__name__)


@job(retry_pattern={1: 2, 3: 6, 5: 10})
def connector_submit_sync_job(session, record_id):
    # Make sure two jobs don't submit the same sync_job
    session.cr.execute(
        "SELECT id FROM sosync_job_queue WHERE id = %s FOR UPDATE", (record_id,))

    # Make sure the sync_job still exists
    sync_job = session.env['sosync.job.queue'].browse(record_id)
    if not sync_job.exists():
        return "sosync.job.queue record (id=%s) no longer exists" % record_id

    # Submit the sync job
    logger.info("ASYNC submission of very high priority sync job (sosync.job.queue) with id %s" % record_id)
    sync_job.bulk_submit_sync_job()


def queue_job(session, record_id, vals):
    kwargs = {}
    connector_submit_sync_job.delay(session, record_id, **kwargs)


# Queue VERY high priority sync_jobs to immediately submit them by async queue
@on_record_create(model_names='sosync.job.queue')
def template_creation(session, model_name, record_id, vals):
    if vals.get('job_priority', 0) >= 1000000:
            queue_job(session, record_id, vals)


# Queue VERY high priority sync_jobs to immediately submit them by async queue
@on_record_write(model_names='sosync.job.queue')
def template_write(session, model_name, record_id, vals):
    if vals.get('job_priority', 0) >= 1000000:
            queue_job(session, record_id, vals)
