from smsggmedia import stream


def vram(addr: int, length: int) -> stream.Write:
    return stream.Write(target=stream.VRAM, address=addr, data=bytes(length))
