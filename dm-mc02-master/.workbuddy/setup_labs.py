# -*- coding: utf-8 -*-
"""把三个实验工程改成位置无关 + 各自的电机数量配置"""
import os, re, io

ROOT = r"D:\singlechip\MC02_Labs"

LABS = {
    "01_三电机摆动": 3,
    "02_六电机双总线": 6,
    "03_单电机调试台": 1,
}

CFG_ALL = [
    ("&hfdcan1", "0x01", "0x11"),
    ("&hfdcan1", "0x02", "0x12"),
    ("&hfdcan1", "0x03", "0x13"),
    ("&hfdcan2", "0x04", "0x14"),
    ("&hfdcan2", "0x05", "0x15"),
    ("&hfdcan2", "0x06", "0x16"),
]


def patch_scripts(lab_dir):
    # build_firmware.py: 用脚本自身所在目录作为工程根
    p = os.path.join(lab_dir, "build_firmware.py")
    s = io.open(p, encoding="utf-8").read()
    s = s.replace(
        'PROJ = "D:/singlechip/MC02_CtrBoard-H7_ALL"',
        'PROJ = os.path.dirname(os.path.abspath(__file__)).replace(chr(92), "/")')
    io.open(p, "w", encoding="utf-8").write(s)

    # flash_firmware.py: 固件路径跟着工程走
    p = os.path.join(lab_dir, "flash_firmware.py")
    s = io.open(p, encoding="utf-8").read()
    s = s.replace(
        'HEX = "D:/singlechip/MC02_CtrBoard-H7_ALL/build_output/MC02_firmware.hex"',
        'HEX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_output", "MC02_firmware.hex")')
    io.open(p, "w", encoding="utf-8").write(s)


def patch_motor_count(lab_dir, n):
    p = os.path.join(lab_dir, "Bsp", "inc", "dm_motor.h")
    s = io.open(p, encoding="utf-8").read()
    s = re.sub(r"#define DM_MOTOR_NUM\s+\d+", "#define DM_MOTOR_NUM   %d" % n, s)
    io.open(p, "w", encoding="utf-8").write(s)


def patch_cfg_table(lab_dir, n):
    p = os.path.join(lab_dir, "App", "dm_ctrl_task.c")
    s = io.open(p, encoding="utf-8").read()

    head = "} dm_cfg[DM_MOTOR_NUM] =\n{"
    i = s.index(head) + len(head)
    j = s.index("};", i)

    lines = ["\n"] + ["    { %s, %s, %s },\n" % row for row in CFG_ALL[:n]]
    s = s[:i] + "".join(lines) + s[j:]
    io.open(p, "w", encoding="utf-8").write(s)


for lab, n in LABS.items():
    d = os.path.join(ROOT, lab)
    patch_scripts(d)
    patch_motor_count(d, n)
    patch_cfg_table(d, n)
    print("已配置 %-16s DM_MOTOR_NUM=%d" % (lab, n))

print("完成")
