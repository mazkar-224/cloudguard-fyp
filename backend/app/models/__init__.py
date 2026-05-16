# Import all models here so Alembic can find them when it scans Base.metadata.
# If a model file is not imported here, Alembic won't see its table and
# won't include it in auto-generated migrations.
from app.models.cost import AwsAccount, CostRecord

__all__ = ["AwsAccount", "CostRecord"]
