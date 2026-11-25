import struct, numpy as np

def save_dds_argb(arr, path):
    a = arr.astype(np.uint8)
    h, w = a.shape[:2]
    bgra = np.dstack([a[..., 2], a[..., 1], a[..., 0], a[..., 3]])
    data = bgra.tobytes()
    hdr = b'DDS ' + struct.pack('<7I', 124, 0x00001007, h, w, w * 4, 0, 1)
    hdr += b'\x00' * 44
    hdr += struct.pack('<2I4s5I', 32, 0x41, b'\x00\x00\x00\x00', 32, 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000)
    hdr += struct.pack('<4I', 0x1000, 0, 0, 0)
    hdr += b'\x00' * 4
    assert len(hdr) == 128, len(hdr)
    open(path, 'wb').write(hdr + data)
