"""Strict decoder for bounded IEX TOPS 1.6 PCAPNG research prefixes.

Prices remain integer ten-thousandths of a dollar. Capture, send and event
timestamps are distinct integer nanoseconds. A partial prefix is never a full
session or a verified gzip checksum. Only Ethernet/IPv4/UDP is supported.
"""

import struct
import zlib
from collections import Counter
from pathlib import Path


def inflate_prefix(path: Path):
    decoder = zlib.decompressobj(31)
    raw = decoder.decompress(path.read_bytes())
    if decoder.unused_data:
        raise ValueError("Multiple gzip members or trailing bytes require a separate decoder")
    return raw, decoder.eof


def options(data, endian):
    at = 0
    while at < len(data):
        if at + 4 > len(data):
            raise ValueError("Short option header")
        code, size = struct.unpack_from(endian + "HH", data, at)
        at += 4
        if code == 0:
            if size != 0:
                raise ValueError("Invalid option terminator")
            return
        stop = at + ((size + 3) // 4) * 4
        if stop > len(data):
            raise ValueError("Truncated option")
        yield code, data[at:at + size]
        at = stop


def packets(data, stats, *, allow_partial=False):
    """Yield exact capture nanoseconds and complete frames; flag a partial tail."""
    at, endian, interfaces = 0, None, []
    while at < len(data):
        if len(data) - at < 12:
            break
        if data[at:at + 4] == b"\x0a\x0d\x0d\x0a":
            magic = data[at + 8:at + 12]
            endian = {b"\x4d\x3c\x2b\x1a": "<", b"\x1a\x2b\x3c\x4d": ">"}.get(magic)
            if endian is None:
                raise ValueError("Invalid PCAPNG byte-order magic")
        if endian is None:
            raise ValueError("Missing section header")
        kind, size = struct.unpack_from(endian + "II", data, at)
        if size < 12 or size % 4:
            raise ValueError("Invalid PCAPNG block length")
        if at + size > len(data):
            break
        if struct.unpack_from(endian + "I", data, at + size - 4)[0] != size:
            raise ValueError("PCAPNG trailing block length mismatch")
        body = data[at + 8:at + size - 4]
        stats["blocks"] += 1
        if kind == 0x0A0D0D0A:
            if len(body) < 16 or struct.unpack_from(endian + "HH", body, 4) != (1, 0):
                raise ValueError("Unsupported PCAPNG section version")
            interfaces = []
            stats["sections"] += 1
        elif kind == 1:
            link, reserved, snaplen = struct.unpack_from(endian + "HHI", body)
            if link != 1 or reserved != 0:
                raise ValueError("Only Ethernet capture is supported")
            resolution, offset = 1_000_000, 0
            for code, value in options(body[8:], endian):
                if code == 9:
                    if len(value) != 1:
                        raise ValueError("Invalid timestamp resolution")
                    r = value[0]
                    resolution = 2 ** (r & 127) if r & 128 else 10 ** r
                elif code == 14:
                    if len(value) != 8:
                        raise ValueError("Invalid timestamp offset")
                    offset = struct.unpack(endian + "q", value)[0]
            interfaces.append((snaplen, resolution, offset))
            stats["interfaces"] += 1
        elif kind == 6:
            interface, high, low, captured, original = struct.unpack_from(endian + "IIIII", body)
            if interface >= len(interfaces):
                raise ValueError("Unknown capture interface")
            snaplen, resolution, offset = interfaces[interface]
            if captured != original or (snaplen and captured > snaplen) or 20 + captured > len(body):
                raise ValueError("Truncated network packet")
            timestamp, remainder = divmod(((high << 32) | low) * 1_000_000_000, resolution)
            if remainder:
                raise ValueError("Subnanosecond capture cannot be rounded silently")
            stats["packets"] += 1
            yield timestamp + offset * 1_000_000_000, body[20:20 + captured]
        elif kind in (2, 3):
            raise ValueError("Unsupported packet-block type")
        else:
            stats["other_blocks"] += 1
        at += size
    stats["trailing_partial_bytes"] = len(data) - at
    if at != len(data) and not allow_partial:
        raise ValueError("Partial final PCAPNG block")


def udp_payload(frame):
    if len(frame) < 14:
        raise ValueError("Short Ethernet frame")
    kind = struct.unpack_from("!H", frame, 12)[0]
    at = 14
    while kind in (0x8100, 0x88A8):
        kind = struct.unpack_from("!H", frame, at + 2)[0]
        at += 4
    if kind != 0x0800:
        raise ValueError("Unsupported non-IPv4 packet")
    ip = frame[at:]
    header = (ip[0] & 15) * 4
    total = struct.unpack_from("!H", ip, 2)[0]
    fragments = struct.unpack_from("!H", ip, 6)[0]
    if ip[0] >> 4 != 4 or header < 20 or ip[9] != 17 or fragments & 0x3FFF:
        raise ValueError("Unsupported IP header/protocol/fragment")
    if total > len(ip) or total < header + 8:
        raise ValueError("Invalid IP length")
    udp = ip[header:total]
    length = struct.unpack_from("!H", udp, 4)[0]
    if length < 8 or length != len(udp):
        raise ValueError("Invalid UDP length")
    return udp[8:]


def segment(payload):
    if len(payload) < 40:
        raise ValueError("Short IEX transport header")
    version, reserved, protocol, channel, session, length, count, offset, sequence, sent = struct.unpack_from(
        "<BBHIIHHqqq", payload)
    if version != 1 or reserved or protocol != 0x8003 or len(payload) != 40 + length:
        raise ValueError("Unsupported TOPS transport or invalid payload length")
    messages, at = [], 40
    for _ in range(count):
        if at + 2 > len(payload):
            raise ValueError("Missing message length")
        size = struct.unpack_from("<H", payload, at)[0]
        at += 2
        if size < 10 or at + size > len(payload):
            raise ValueError("Incomplete or invalid TOPS message")
        messages.append(payload[at:at + size])
        at += size
    if at != len(payload):
        raise ValueError("Message count does not cover payload")
    return (protocol, channel, session), sequence, offset, length, sent, messages


def decode_message(data):
    kind = chr(data[0])
    row = {"type": kind, "flags": data[1], "event_ns": struct.unpack_from("<q", data, 2)[0]}
    if len(data) >= 18:
        row["symbol"] = data[10:18].decode("ascii").rstrip(" ")
    sizes = {"Q": 42, "T": 38, "B": 38, "D": 31}
    if kind in sizes and len(data) != sizes[kind]:
        raise ValueError("Unexpected TOPS message length")
    if kind == "Q":
        row.update(bid_size=struct.unpack_from("<I", data, 18)[0],
                   bid_price=struct.unpack_from("<q", data, 22)[0],
                   ask_price=struct.unpack_from("<q", data, 30)[0],
                   ask_size=struct.unpack_from("<I", data, 38)[0])
    elif kind in ("T", "B"):
        row.update(size=struct.unpack_from("<I", data, 18)[0],
                   price=struct.unpack_from("<q", data, 22)[0],
                   trade_id=struct.unpack_from("<q", data, 30)[0])
    elif kind == "D":
        row.update(round_lot=struct.unpack_from("<I", data, 18)[0],
                   adjusted_previous_close=struct.unpack_from("<q", data, 22)[0])
    return row


def read_prefix(path, symbols):
    raw, gzip_complete = inflate_prefix(path)
    stats, types, states, rows = Counter(), Counter(), {}, []
    first_capture, last_capture = None, None
    for capture, frame in packets(raw, stats, allow_partial=not gzip_complete):
        if last_capture is not None and capture < last_capture:
            raise ValueError("Decreasing capture timestamp")
        first_capture = capture if first_capture is None else first_capture
        last_capture = capture
        key, seq, offset, length, sent, messages = segment(udp_payload(frame))
        expected = states.get(key, (1, 0))
        if (seq, offset) != expected:
            raise ValueError(f"IEX sequence/offset gap or duplicate: {key}, {(seq, offset)}, {expected}")
        states[key] = (seq + len(messages), offset + length)
        for k, data in enumerate(messages):
            row = decode_message(data)
            types[row["type"]] += 1
            if row.get("symbol") in symbols or row["type"] == "S":
                row.update(capture_ns=capture, send_ns=sent, sequence=seq + k,
                           protocol=key[0], channel=key[1], session=key[2])
                rows.append(row)
    return rows, {**dict(stats), "message_types": dict(types), "first_capture_ns": first_capture,
                  "last_capture_ns": last_capture, "gzip_complete": gzip_complete,
                  "complete_session": False, "decoded_bytes": len(raw), "sequence_gaps": 0,
                  "stream_count": len(states)}
