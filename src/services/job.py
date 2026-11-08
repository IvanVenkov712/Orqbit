from sqlalchemy import and_, or_, select

from models.job import Job, PermissionPolicy
from models.user import User
from models.worker import Worker


def accessible_user_jobs_query(user: User):
    return select(Job).where(
        or_(
            Job.user_id == user.id,

            Job.permission_policy == PermissionPolicy.ALL,

            and_(
                Job.permission_policy.in_([
                    PermissionPolicy.PERMITTED_USERS,
                    PermissionPolicy.PERMITTED_WORKERS_AND_USERS,
                ]),
                Job.permitted_users.any(User.id == user.id),
            ),
        )
    )

def job_accessible_for_user(job: Job, user: User) -> bool:

    if job.permission_policy == PermissionPolicy.ALL:
        return True

    if job.user_id == user.id:
        return True

    if job.permission_policy in [PermissionPolicy.PERMITTED_USERS,
                                 PermissionPolicy.PERMITTED_WORKERS_AND_USERS]:
        return any(p_user.id == user.id for p_user in job.permitted_users)

    return False

def accessible_worker_jobs(worker: Worker):
    return select(Job).where(
        or_(
            Job.user_id == worker.user_id,
            Job.permission_policy == PermissionPolicy.ALL,
            and_(
                Job.permission_policy.in_(
                    [
                        PermissionPolicy.PERMITTED_USERS,
                        PermissionPolicy.PERMITTED_WORKERS_AND_USERS,
                    ]
                ),

                or_(
                    Job.permitted_users.any(User.id == worker.user_id),
                    Job.permitted_workers.any(Worker.id == worker.id)
                )
            ),
        )
    )


def job_accessible_for_worker(job: Job, worker: Worker) -> bool:
    if job.permission_policy == PermissionPolicy.ALL:
        return True

    if job.user_id == worker.user_id:
        return True
    
    if job_accessible_for_user(job, worker.user):
        return True
    
    if job.permission_policy in [PermissionPolicy.PERMITTED_WORKERS, 
                                 PermissionPolicy.PERMITTED_WORKERS_AND_USERS]:
        return any(w.id == worker.id for w in job.permitted_workers)
    
    return False
    
   
    
    
