"""Conservative, supervised read-only executor candidate (NOT OS isolated)."""
from .supervised import SupervisedReadOnlyExecutor, CommandReceipt
__all__ = ['SupervisedReadOnlyExecutor','CommandReceipt']
