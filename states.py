from aiogram.fsm.state import State, StatesGroup


class PeriodState(StatesGroup):
    waiting_for_period = State()
