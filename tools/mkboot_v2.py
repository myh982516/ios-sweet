#!/usr/bin/env python3
"""Minimal Android boot image v2 packer.

Drop-in stand-in for AOSP mkbootimg for the options shim/build.sh uses.
Ref: system/tools/mkbootimg/include/bootimg/bootimg.h (header v2, 1660 bytes).
"""
import argparse
import hashlib
import struct
import sys

PAGE = 4096
HEADER_V2_SIZE = 1660
MAGIC = b"ANDROID!"


def align(data, page=PAGE):
    return data + b"\0" * ((-len(data)) % page)


def parse_version(text):
    parts = [int(x) for x in text.split(".")]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def parse_patch(text):
    year, month = text.split("-")
    return int(year), int(month)


def encode_os(version, patch, max_size=0):
    a, b, c = version
    y, m = patch
    val = (a << 25) | (b << 18) | (c << 11) | (((y - 2000) & 0x7F) << 4) | (m & 0xF)
    if max_size:
        val = val | ((max_size & 0x1FF) << 4)
    return val


def arg_hex(text):
    return int(text, 0)


def main(argv=None):
    p = argparse.ArgumentParser(description="pack an Android boot image v2")
    p.add_argument("--header_version", type=int, default=2)
    p.add_argument("--kernel", required=True)
    p.add_argument("--ramdisk", default=None)
    p.add_argument("--second", default=None)
    p.add_argument("--dtb", default=None)
    p.add_argument("--recovery_dtbo", default=None)
    p.add_argument("--base", type=arg_hex, default=0)
    p.add_argument("--kernel_offset", type=arg_hex, default=0x00008000)
    p.add_argument("--ramdisk_offset", type=arg_hex, default=0x01000000)
    p.add_argument("--second_offset", type=arg_hex, default=0x00f00000)
    p.add_argument("--tags_offset", type=arg_hex, default=0x00000100)
    p.add_argument("--dtb_offset", type=arg_hex, default=0x01f00000)
    p.add_argument("--recovery_dtbo_offset", type=arg_hex, default=0)
    p.add_argument("--pagesize", type=arg_hex, default=PAGE)
    p.add_argument("--os_version", default="0.0.0")
    p.add_argument("--os_patch_level", default="2000-01")
    p.add_argument("--board", default="")
    p.add_argument("--cmdline", default="")
    p.add_argument("-o", "--output", required=True)
    args = p.parse_args(argv)

    if args.header_version != 2:
        sys.exit("only header v2 is supported")

    page = args.pagesize
    kernel = open(args.kernel, "rb").read()
    ramdisk = open(args.ramdisk, "rb").read() if args.ramdisk else b""
    second = open(args.second, "rb").read() if args.second else b""
    dtb = open(args.dtb, "rb").read() if args.dtb else b""
    dtbo = open(args.recovery_dtbo, "rb").read() if args.recovery_dtbo else b""

    # SHA1 id over the component sizes, matching AOSP mkbootimg behaviour.
    h = hashlib.sha1()
    for blob in (kernel, ramdisk, second, dtbo, dtb):
        h.update(blob)
        h.update(struct.pack("<I", len(blob)))
    image_id = h.digest()

    cmdline = args.cmdline.encode("ascii")[:511]
    name = args.board.encode("ascii")[:15]

    hdr = bytearray()
    hdr += MAGIC
    hdr += struct.pack("<I", len(kernel))
    hdr += struct.pack("<I", args.base + args.kernel_offset)
    hdr += struct.pack("<I", len(ramdisk))
    hdr += struct.pack("<I", args.base + args.ramdisk_offset)
    hdr += struct.pack("<I", len(second))
    hdr += struct.pack("<I", args.base + args.second_offset)
    hdr += struct.pack("<I", args.base + args.tags_offset)
    hdr += struct.pack("<I", page)
    hdr += struct.pack("<I", args.header_version)
    hdr += struct.pack("<I", encode_os(parse_version(args.os_version), parse_patch(args.os_patch_level)))
    hdr += name.ljust(16, b"\0")
    hdr += cmdline.ljust(512, b"\0")
    hdr += image_id.ljust(32, b"\0")  # id[8]; mkbootimg zero-pads the SHA1 to 32 bytes
    hdr += b"\0" * 1024  # extra_cmdline
    hdr += struct.pack("<I", len(dtbo))
    hdr += struct.pack("<Q", args.recovery_dtbo_offset)
    hdr += struct.pack("<I", HEADER_V2_SIZE)
    hdr += struct.pack("<I", len(dtb))
    hdr += struct.pack("<Q", args.base + args.dtb_offset)

    assert len(hdr) == HEADER_V2_SIZE, len(hdr)

    with open(args.output, "wb") as f:
        f.write(align(bytes(hdr), page))
        f.write(align(kernel, page))
        if ramdisk:
            f.write(align(ramdisk, page))
        if second:
            f.write(align(second, page))
        if dtbo:
            f.write(align(dtbo, page))
        if dtb:
            f.write(align(dtb, page))

    print("packed %s: kernel=%d ramdisk=%d dtb=%d page=%d" %
          (args.output, len(kernel), len(ramdisk), len(dtb), page))


if __name__ == "__main__":
    main()
