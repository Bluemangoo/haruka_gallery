import re
from abc import abstractmethod, ABCMeta
from enum import Enum
from typing import Any, Optional, TypeVar, List, Callable, Tuple

T = TypeVar("T")


class ArgParser:
    def __init__(self, s: Optional[str]):
        self._s: str = s or ""
        self._tokens: List[Tuple[int, int]] = []
        self._idx: int = 0
        self._build_tokens()

    def _build_tokens(self) -> None:
        self._tokens.clear()
        s = self._s
        n = len(s)
        i = 0
        while i < n:
            while i < n and s[i] == " ":
                i += 1
            if i >= n:
                break
            start = i
            while i < n and s[i] != " ":
                i += 1
            end = i
            if start < end:
                self._tokens.append((start, end))

    def _current_range(self) -> Optional[Tuple[int, int]]:
        self._skip_empty_tokens()
        if self._idx >= len(self._tokens):
            return None
        return self._tokens[self._idx]

    def _skip_empty_tokens(self) -> None:
        while self._idx < len(self._tokens):
            start, end = self._tokens[self._idx]
            if start < end and self._s[start:end].strip() != "":
                break
            self._idx += 1

    def peek(self, chars: Optional[int] = None) -> Optional[str]:
        rng = self._current_range()
        if rng is None:
            return None
        start, end = rng
        token = self._s[start:end]
        if chars is None:
            res = token.strip()
        else:
            if not isinstance(chars, int) or chars <= 0:
                return None
            take = min(chars, end - start)
            res = token[:take].strip()
        return res if res != "" else None

    def pop(self, chars: Optional[int] = None) -> Optional[str]:
        rng = self._current_range()
        if rng is None:
            return None
        start, end = rng
        token = self._s[start:end]
        if chars is None:
            res = token.strip()
            self._idx += 1
            # 防守：跳过任何空 token（不太可能）
            self._skip_empty_tokens()
            return res if res != "" else None
        else:
            if not isinstance(chars, int) or chars <= 0:
                return None
            token_len = end - start
            if chars >= token_len:
                # 忽略多余，只消费整个 token
                res = token.strip()
                self._idx += 1
                self._skip_empty_tokens()
                return res if res != "" else None
            else:
                part = token[:chars].strip()
                new_start = start + chars
                # new_start < end 因为 chars < token_len
                self._tokens[self._idx] = (new_start, end)
                # 更新后再做一次防守性跳过（一般不跳过，但保持一致）
                self._skip_empty_tokens()
                return part if part != "" else None

    def pop_all(self) -> str:
        rng = self._current_range()
        if rng is None:
            return ""
        start, _ = rng
        rest = self._s[start:].strip()
        self._idx = len(self._tokens)
        return rest

    def check_and_pop(self, expected: str) -> bool:
        token = self.peek()
        if token == expected:
            self.pop()
            return True
        return False

    def remaining_count(self) -> int:
        self._skip_empty_tokens()
        return max(0, len(self._tokens) - self._idx)

    def __repr__(self) -> str:
        rng = self._current_range()
        cur = None
        if rng:
            cur = self._s[rng[0]:rng[1]]
        return f"<ArgParser current={cur} remaining={self.remaining_count()}>"


class _ValueState[T]:
    is_set: bool
    value: Optional[T]

    def __init__(self):
        self.is_set = False
        self.value = None

    def set(self, value: T):
        self.is_set = True
        self.value = value


class _MultipleValueState[T](_ValueState[List[T]]):
    is_set: bool
    values: list[T]

    def __init__(self):
        super().__init__()
        self.values = []

    def set(self, value: T):
        self.is_set = True
        self.values.append(value)


class ArgValue(metaclass=ABCMeta):
    @abstractmethod
    def try_parse(self, value, state: _ValueState) -> bool:
        raise NotImplementedError


class ArgValueString(ArgValue):
    def try_parse(self, value, state: _ValueState[str]) -> bool:
        state.set(value)
        return True


class ArgValueStringWithRule(ArgValue):
    def __init__(self, rule: Callable[[str], bool]):
        self.rule = rule

    def try_parse(self, value, state: _ValueState[str]) -> bool:
        if self.rule(value):
            state.set(value)
            return True
        return False


class ArgValueInt(ArgValue):
    def try_parse(self, value, state: _ValueState[int]) -> bool:
        try:
            state.set(int(value))
            return True
        except ValueError:
            return False


class ArgValueEnum(ArgValue):
    def __init__(self, values: dict[str, str | Enum]):
        self.value_map = values

    def try_parse(self, value: str, state: _ValueState[str | Enum] = None) -> bool:
        if value in self.value_map:
            state.set(self.value_map[value])
            return True
        return False


class ArgValueLiteral(ArgValue):
    def __init__(self, literal_value):
        self.literal_value = literal_value

    def try_parse(self, value, state: _ValueState[bool]):
        if value == self.literal_value:
            state.set(True)
            return True
        return False


class ArgValueAmount(ArgValue):
    def __init__(self):
        pass

    def try_parse(self, value: str, state: _ValueState[int]):
        s = value
        if s.startswith("x"):
            s = s[1:]
        if s.isdigit():
            state.set(int(s))
            return True
        return False


class ArgValueList(ArgValue):
    def __init__(self, item_rule: ArgValue):
        self.item_rule = item_rule

    def try_parse(self, value: str, state: _MultipleValueState):
        items = re.split(r"[，,;]+", value)
        for item in items:
            if not self.item_rule.try_parse(item, state):
                return False
        return True


class ArgDefine(metaclass=ABCMeta):
    @abstractmethod
    def try_parse(self, value: str, state):
        raise NotImplementedError


class PositionalArg(ArgDefine):
    def try_parse(self, value: str, state: _ValueState[Any]):
        return self.rule.try_parse(value, state)

    def __init__(self, name, rule: ArgValue):
        self.name = name
        self.rule = rule


class OptionalArg(ArgDefine):
    def try_parse(self, value: str, state: _ValueState[bool]):
        return self.rule.try_parse(value, state)

    def __init__(self, name, rule: ArgValue):
        self.name = name
        self.rule = rule


class NamedArg(ArgDefine):
    def try_parse(self, value: str, state: _ValueState, args: ArgParser = None):
        if value == "--" + self.name:
            if self.no_input:
                state.set(True)
                return True
            args.pop()
            if self.rule.try_parse(args.peek(), state):
                return True
            # 已经pop了，无法回退，所以throw
            raise ValueError(f"对于'{self.name}'无效的值'{args.peek()}'")
        for alias in self.aliases_start_with:
            if value.startswith(alias):
                return self.rule.try_parse(value[len(alias):], state)
        return False

    def __init__(self, name, rule: ArgValue, aliases_start_with: list[str] = None, no_input: bool = False):
        self.name = name
        self.rule = rule
        self.aliases_start_with = aliases_start_with if aliases_start_with is not None else []
        self.no_input = no_input


class FinalStringArg(ArgDefine):
    def try_parse(self, value: str, state: _ValueState[str], args: ArgParser = None):
        if value == "--":
            args.pop()
            return self.rule.try_parse(args.pop_all(), state)
        return False

    def __init__(self, name, rule: ArgValueString):
        self.name = name
        self.rule = rule


class ArgParseResult:
    def __init__(self, result: dict[str, _ValueState], errors: list[str], unknown_args: list[str]):
        self.result = result
        self.errors = errors
        self.unknown_args = unknown_args

    def get(self, name: str):
        state = self.result.get(name)
        if state is None:
            return None
        if isinstance(state, _MultipleValueState):
            return state.values
        return state.value


class FullArgParser:
    pos_arg: list[PositionalArg]
    opt_arg: list[OptionalArg]
    named_arg: list[NamedArg]
    final_str_arg: Optional[FinalStringArg]
    multiple_value_args: list[str]

    def __init__(self):
        self.pos_arg = []
        self.opt_arg = []
        self.named_arg = []
        self.final_str_arg = None
        self.multiple_value_args = []

    def add_positional_arg(self, name: str, rule: ArgValue, multiple_value: bool = False):
        self.pos_arg.append(PositionalArg(name, rule))
        if multiple_value:
            self.multiple_value_args.append(name)

    def add_optional_arg(self, name: str, rule: ArgValue, multiple_value: bool = False):
        self.opt_arg.append(OptionalArg(name, rule))
        if multiple_value:
            self.multiple_value_args.append(name)

    def add_named_arg(self, name: str, rule: ArgValue, aliases_start_with: list[str] = None,
                      multiple_value: bool = False, no_input: bool = False):
        self.named_arg.append(NamedArg(name, rule, aliases_start_with, no_input))
        if multiple_value:
            self.multiple_value_args.append(name)

    def add_named_flag(self, name: str):
        self.named_arg.append(NamedArg(name, ArgValueString(), no_input=True))

    def set_final_string_arg(self, name: str, rule: ArgValueString, multiple_value: bool = False):
        self.final_str_arg = FinalStringArg(name, rule)
        if multiple_value:
            self.multiple_value_args.append(name)

    def parse(self, args: ArgParser) -> ArgParseResult:
        states = {}
        errors = set()
        unknown_args = []
        pos = self.pos_arg
        opt = self.opt_arg
        for name in self.multiple_value_args:
            states[name] = _MultipleValueState()

        while current := args.peek():
            try:
                flag = False
                for named in self.named_arg:
                    if named.try_parse(current, states.setdefault(named.name, _ValueState()), args):
                        args.pop()
                        flag = True
                        break
                if flag:
                    continue
                if pos:
                    if pos[0].try_parse(current, states.setdefault(pos[0].name, _ValueState())):
                        args.pop()
                        pos = pos[1:]
                        continue
                else:
                    for remaining_opt in opt:
                        if remaining_opt.try_parse(current, states.setdefault(remaining_opt.name, _ValueState())):
                            args.pop()
                            opt = [o for o in opt if o != remaining_opt]
                            flag = True
                            break
                if flag:
                    continue
                if (self.final_str_arg
                        and self.final_str_arg.try_parse(current,
                                                         states.setdefault(self.final_str_arg.name, _ValueState()),
                                                         args)):
                    continue
                unknown_args.append(args.pop())
            except ValueError as e:
                errors.add(str(e))
                args.pop()
        return ArgParseResult(states, list(errors), unknown_args)
