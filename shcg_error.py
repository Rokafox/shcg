"""
Multiple error classes
"""

class FlowError(Exception):
    """
    Invalid play actions.
    """
    pass

class AbilityToReadError(Exception):
    """
    Card must be played according to its written effects.
    """
    pass

class TimeError(Exception):
    """
    It is implemented in the future, or the past, or some other time that is not now.
    """
    pass

class AIError(Exception):
    """
    Not so intelligent after all.
    """
    pass

class CardNotFoundError(Exception):
    """
    いかさま禁止
    """
    pass