"""Reads the ActionScript 3 classes in an SWF and lists each method's bytecode as plain instructions.

Used by client_labels.py. It reads a file you already have and never runs the code it reads.
"""

from __future__ import annotations

import lzma
import struct
import zlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DO_ABC, SYMBOL_CLASS = 82, 76


@dataclass
class AbcClass:
    package: str
    name: str
    parent: str | None
    statics: dict[str, Any] = field(default_factory=dict)
    methods: dict[str, list[str]] = field(default_factory=dict)


def _decompress(data: bytes) -> bytes:
    if data[:3] == b"CWS":
        return data[:8] + zlib.decompress(data[8:])
    if data[:3] == b"ZWS":
        lzma_filter = lzma._decode_filter_properties(lzma.FILTER_LZMA1, data[12:17])  # type: ignore[attr-defined]
        decoder = lzma.LZMADecompressor(lzma.FORMAT_RAW, filters=[lzma_filter])
        return data[:8] + decoder.decompress(data[17:])
    return data


def _tags(data: bytes) -> Iterator[tuple[int, bytes]]:
    rect_bits = data[8] >> 3
    pos = 8 + (5 + rect_bits * 4 + 7) // 8 + 4
    while pos < len(data):
        header = struct.unpack_from("<H", data, pos)[0]
        pos += 2
        code, length = header >> 6, header & 0x3F
        if length == 0x3F:
            length = struct.unpack_from("<I", data, pos)[0]
            pos += 4
        yield code, data[pos : pos + length]
        pos += length
        if code == 0:
            return


class _Reader:
    def __init__(self, data: bytes) -> None:
        self.data, self.pos = data, 0

    def u8(self) -> int:
        value = self.data[self.pos]
        self.pos += 1
        return value

    def u16(self) -> int:
        value: int = struct.unpack_from("<H", self.data, self.pos)[0]
        self.pos += 2
        return value

    def u30(self) -> int:
        result = 0
        for shift in range(0, 35, 7):
            byte = self.u8()
            result |= (byte & 0x7F) << shift
            if not byte & 0x80:
                break
        return result

    def s32(self) -> int:
        value = self.u30()
        return value - (1 << 32) if value & 0x80000000 else value

    def f64(self) -> float:
        value: float = struct.unpack_from("<d", self.data, self.pos)[0]
        self.pos += 8
        return value

    def take(self, count: int) -> bytes:
        value = self.data[self.pos : self.pos + count]
        self.pos += count
        return value


ONE_NAME = {
    0x04: "getsuper", 0x05: "setsuper", 0x59: "getdescendants", 0x5D: "findpropstrict", 0x5E: "findproperty",
    0x5F: "finddef", 0x60: "getlex", 0x61: "setproperty", 0x66: "getproperty", 0x68: "initproperty",
    0x6A: "deleteproperty", 0x80: "coerce", 0x86: "astype", 0xB2: "istype",
}  # fmt: skip
ONE_INT = {
    0x08: "kill", 0x2C: "pushstring", 0x2D: "pushint", 0x2E: "pushuint", 0x2F: "pushdouble", 0x31: "pushnamespace",
    0x40: "newfunction", 0x41: "call", 0x42: "construct", 0x53: "applytype", 0x55: "newobject", 0x56: "newarray",
    0x58: "newclass", 0x5A: "newcatch", 0x62: "getlocal", 0x63: "setlocal", 0x6C: "getslot", 0x6D: "setslot",
    0x6E: "getglobalslot", 0x6F: "setglobalslot", 0x92: "inclocal", 0x94: "declocal", 0xC2: "inclocal_i",
    0xC3: "declocal_i", 0x06: "dxns", 0xF0: "debugline", 0xF2: "bkptline", 0x49: "constructsuper", 0x25: "pushshort",
    0xF1: "debugfile",
}  # fmt: skip
TWO = {
    0x43: "callmethod", 0x44: "callstatic", 0x45: "callsuper", 0x46: "callproperty", 0x4A: "constructprop",
    0x4C: "callproplex", 0x4E: "callsupervoid", 0x4F: "callpropvoid", 0x32: "hasnext2",
}  # fmt: skip
NONE = {
    0x01: "bkpt", 0x02: "nop", 0x03: "throw", 0x09: "label", 0x1C: "pushwith", 0x1D: "popscope", 0x1E: "nextname",
    0x1F: "hasnext", 0x20: "pushnull", 0x21: "pushundefined", 0x23: "nextvalue", 0x26: "pushtrue", 0x27: "pushfalse",
    0x28: "pushnan", 0x29: "pop", 0x2A: "dup", 0x2B: "swap", 0x30: "pushscope", 0x47: "returnvoid",
    0x48: "returnvalue", 0x57: "newactivation", 0x64: "getglobalscope", 0x70: "convert_s", 0x71: "esc_xelem",
    0x72: "esc_xattr", 0x73: "convert_i", 0x74: "convert_u", 0x75: "convert_d", 0x76: "convert_b", 0x78: "checkfilter",
    0x81: "coerce_b", 0x82: "coerce_a", 0x83: "coerce_i", 0x84: "coerce_d", 0x85: "coerce_s", 0x87: "astypelate",
    0x88: "coerce_u", 0x89: "coerce_o", 0x90: "negate", 0x91: "increment", 0x93: "decrement", 0x95: "typeof",
    0x96: "not", 0x97: "bitnot", 0xA0: "add", 0xA1: "subtract", 0xA2: "multiply", 0xA3: "divide", 0xA4: "modulo",
    0xA5: "lshift", 0xA6: "rshift", 0xA7: "urshift", 0xA8: "bitand", 0xA9: "bitor", 0xAA: "bitxor", 0xAB: "equals",
    0xAC: "strictequals", 0xAD: "lessthan", 0xAE: "lessequals", 0xAF: "greaterthan", 0xB0: "greaterequals",
    0xB1: "instanceof", 0xB3: "istypelate", 0xB4: "in", 0xC0: "increment_i", 0xC1: "decrement_i", 0xC4: "negate_i",
    0xC5: "add_i", 0xC6: "subtract_i", 0xC7: "multiply_i", 0xD0: "getlocal0", 0xD1: "getlocal1", 0xD2: "getlocal2",
    0xD3: "getlocal3", 0xD4: "setlocal0", 0xD5: "setlocal1", 0xD6: "setlocal2", 0xD7: "setlocal3",
    **dict.fromkeys((*range(0x35, 0x3F), 0x50, 0x51, 0x52), "memory"),
}  # fmt: skip


class _Abc:
    def __init__(self, data: bytes) -> None:
        r = self.r = _Reader(data)
        r.u16(), r.u16()
        self.ints = [0] + [r.s32() for _ in range(max(0, r.u30() - 1))]
        self.uints = [0] + [r.u30() for _ in range(max(0, r.u30() - 1))]
        self.floats = [0.0] + [r.f64() for _ in range(max(0, r.u30() - 1))]
        self.strings = [""] + [r.take(r.u30()).decode("utf-8", "replace") for _ in range(max(0, r.u30() - 1))]
        self.namespaces = [""]
        for _ in range(max(0, r.u30() - 1)):
            r.u8()
            self.namespaces.append(self.strings[r.u30()])
        for _ in range(max(0, r.u30() - 1)):
            for _ in range(r.u30()):
                r.u30()
        self.names: list[tuple[str, str]] = [("", "*")]
        for _ in range(max(0, r.u30() - 1)):
            self.names.append(self._multiname(r.u8()))
        for _ in range(r.u30()):
            count = r.u30()
            r.u30()
            for _ in range(count):
                r.u30()
            r.u30()
            flags = r.u8()
            if flags & 0x08:
                for _ in range(r.u30()):
                    r.u30(), r.u8()
            if flags & 0x80:
                for _ in range(count):
                    r.u30()
        for _ in range(r.u30()):
            r.u30()
            for _ in range(r.u30() * 2):
                r.u30()

    def _multiname(self, kind: int) -> tuple[str, str]:
        r = self.r
        if kind in (0x07, 0x0D):
            namespace = r.u30()
            return self.namespaces[namespace], self.strings[r.u30()]
        if kind in (0x0F, 0x10):
            return "", self.strings[r.u30()]
        if kind in (0x09, 0x0E):
            name = r.u30()
            r.u30()
            return "", self.strings[name]
        if kind in (0x1B, 0x1C):
            r.u30()
            return "", "*"
        if kind == 0x1D:
            r.u30()
            for _ in range(r.u30()):
                r.u30()
            return "", "Vector"
        if kind in (0x11, 0x12):
            return "", "*"
        raise ValueError(f"Unknown multiname kind {kind:#x}")

    def _traits(self) -> list[tuple[str, str, Any]]:
        r, out = self.r, []
        for _ in range(r.u30()):
            name = self.names[r.u30()][1]
            kind = r.u8()
            sort = kind & 0x0F
            if sort in (0, 6):
                r.u30(), r.u30()
                index = r.u30()
                value: Any = None
                if index:
                    value = {0x03: self.ints, 0x04: self.uints, 0x06: self.floats, 0x01: self.strings}.get(
                        r.u8(), [None] * (index + 1)
                    )[index]
                out.append(("value", name, value))
            elif sort in (1, 2, 3):
                r.u30()
                out.append(("method", name, r.u30()))
            else:
                r.u30(), r.u30()
                out.append(("other", name, None))
            if kind & 0x40:
                for _ in range(r.u30()):
                    r.u30()
        return out

    def classes(self) -> list[AbcClass]:
        r = self.r
        found: list[tuple[AbcClass, int, list[tuple[str, str, Any]]]] = []
        for _ in range(r.u30()):
            package, name = self.names[r.u30()]
            parent = self.names[r.u30()][1] or None
            flags = r.u8()
            if flags & 0x08:
                r.u30()
            for _ in range(r.u30()):
                r.u30()
            init = r.u30()
            found.append((AbcClass(package, name, parent), init, self._traits()))
        statics = []
        for _ in found:
            statics.append((r.u30(), self._traits()))
        for _ in range(r.u30()):
            r.u30()
            self._traits()
        bodies: dict[int, bytes] = {}
        for _ in range(r.u30()):
            method = r.u30()
            for _ in range(4):
                r.u30()
            bodies[method] = r.take(r.u30())
            for _ in range(r.u30() * 5):
                r.u30()
            self._traits()
        out = []
        for (cls, init, traits), (static_init, static_traits) in zip(found, statics, strict=True):
            cls.statics = {name: value for sort, name, value in static_traits if sort == "value"}
            methods = [("<init>", init), ("<cinit>", static_init)]
            methods += [(name, index) for sort, name, index in traits + static_traits if sort == "method"]
            cls.methods = {name: self.disassemble(bodies.get(index, b"")) for name, index in methods}
            out.append(cls)
        return out

    def disassemble(self, code: bytes) -> list[str]:
        r, out = _Reader(code), []
        while r.pos < len(code):
            op = r.u8()
            if op in NONE:
                out.append(NONE[op])
            elif op == 0x24:
                value = r.u8()
                out.append(f"pushbyte {value - 256 if value > 127 else value}")
            elif op == 0x65:
                out.append(f"getscopeobject {r.u8()}")
            elif op in ONE_NAME:
                out.append(f"{ONE_NAME[op]} {self.names[r.u30()][1]}")
            elif op in ONE_INT:
                name, value = ONE_INT[op], r.u30()
                if name in ("debugline", "debugfile"):
                    continue
                shown: Any = {
                    "pushstring": lambda v: repr(self.strings[v]),
                    "pushint": lambda v: self.ints[v],
                    "pushuint": lambda v: self.uints[v],
                    "pushdouble": lambda v: self.floats[v],
                }.get(name, lambda v: v)(value)
                out.append(f"{name} {shown}")
            elif op in TWO:
                name, first, count = TWO[op], r.u30(), r.u30()
                target = self.names[first][1] if name != "hasnext2" and name != "callmethod" else first
                out.append(f"{name} {target} ({count})")
            elif 0x0C <= op <= 0x1A:
                r.take(3)
                out.append(f"branch {op:#x}")
            elif op == 0x1B:
                r.take(3)
                r.take(3 * (r.u30() + 1))
                out.append("lookupswitch")
            elif op == 0xEF:
                r.u8(), r.u30(), r.u8(), r.u30()
            else:
                out.append(f"unknown {op:#x}")
                break
        return out


def read_classes(path: Path) -> list[AbcClass]:
    data = _decompress(path.read_bytes())
    classes: list[AbcClass] = []
    for code, body in _tags(data):
        if code == DO_ABC:
            end = body.index(b"\0", 4)
            classes += _Abc(body[end + 1 :]).classes()
    return classes
