from bot.config import cfg
from bot.strategy import Strategy

_executor = None


def get_executor():
    global _executor
    if _executor is None:
        from bot.executor import create_executor
        _executor = create_executor(Strategy())
    return _executor


def execute_intents(intents):
    return get_executor().execute(intents)


def reset_executor():
    global _executor
    _executor = None
