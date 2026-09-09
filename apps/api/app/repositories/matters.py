from app.models.matter import Matter
from app.repositories.base import WorkspaceScopedRepository


class MatterRepository(WorkspaceScopedRepository[Matter]):
    model = Matter
