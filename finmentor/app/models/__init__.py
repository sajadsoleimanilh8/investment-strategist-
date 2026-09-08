"""Import every model here so Alembic autogenerate sees them."""
from app.models.user import User  # noqa: F401
from app.models.finance import FinancialProfile, IncomeRecord, ExpenseRecord  # noqa: F401
from app.models.goal import FinancialGoal  # noqa: F401
from app.models.market import MarketAsset, MarketSnapshot, WatchlistItem  # noqa: F401
from app.models.simulation import Simulation, ChatSession, EducationProgress  # noqa: F401
