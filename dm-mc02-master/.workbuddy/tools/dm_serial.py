# -*- coding: utf-8 -*-
"""
DM 电机 串口直驱工具  (USB-CAN 模块 UART -> 电机调试串口)
协议：达妙 USB-CDC 串口桥，把 CAN 帧封装进 30 字节串口帧
   TX 30B: 55 AA 1E 03 | sendTimes(4) | interval(4) | idType | canId(4) | ftype | dlc | ... | data(8) | tail
   RX 16B: AA | cmd | idType | canId(4,LE) | data(8) | 55
用法：
   python dm_serial.py probe              # 只读：刷新并解析反馈帧（不使能，电机不动）
   python dm_serial.py enable             # 使能（电机会建立力矩 / 变硬）
   python dm_serial.py disable            # 失能
   python dm_serial.py lock               # 使能 + 锁定在当前位置
   python dm_serial.py swing --amp 0.3    # 使能 + 小幅来回摆动
   python dm_serial.py mit --pos 0.5 --kp 20 --kd 1
"""
import argparse
import struct
import sys
import time

import serial

PORT = "COM8"
BAUD = 921600

P_MAX, V_MAX, T_MAX = 12.5, 30.0, 10.0
KP_MAX, KD_MAX = 500.0, 5.0

CMD_ENABLE = 0xFC
CMD_DISABLE = 0xFD
CMD_ZERO = 0xFE


def f2u(x, xmin, xmax, bits):
    x = max(xmin, min(xmax, float(x)))
    return int((x - xmin) * ((1 << bits) - 1) / (xmax - xmin))


def u2f(v, xmin, xmax, bits):
    return v * (xmax - xmin) / ((1 << bits) - 1) + xmin


def build_tx(can_id, data, send_times=1, interval=10):
    f = bytearray(30)
    f[0] = 0x55
    f[1] = 0xAA
    f[2] = 0x1E
    f[3] = 0x03
    f[4] = send_times & 0xFF
    f[5] = (send_times >> 8) & 0xFF
    f[6] = (send_times >> 16) & 0xFF
    f[7] = (send_times >> 24) & 0xFF
    f[8] = interval & 0xFF
    f[9] = (interval >> 8) & 0xFF
    f[10] = 0
    f[11] = 0
    f[12] = 0
    f[13] = can_id & 0xFF
    f[14] = (can_id >> 8) & 0xFF
    f[15] = 0
    f[16] = 0
    f[17] = 0
    f[18] = 0x08
    f[19] = 0
    f[20] = 0
    f[21:29] = bytes(data)
    f[29] = 0x00
    return bytes(f)


def pack_mit(pos, vel, kp, kd, tau):
    q = f2u(pos, -P_MAX, P_MAX, 16)
    dq = f2u(vel, -V_MAX, V_MAX, 12)
    kp_u = f2u(kp, 0, KP_MAX, 12)
    kd_u = f2u(kd, 0, KD_MAX, 12)
    t = f2u(tau, -T_MAX, T_MAX, 12)
    d = bytearray(8)
    d[0] = (q >> 8) & 0xFF
    d[1] = q & 0xFF
    d[2] = (dq >> 4) & 0xFF
    d[3] = ((dq & 0xF) << 4) | ((kp_u >> 8) & 0xF)
    d[4] = kp_u & 0xFF
    d[5] = (kd_u >> 4) & 0xFF
    d[6] = ((kd_u & 0xF) << 4) | ((t >> 8) & 0xF)
    d[7] = t & 0xFF
    return bytes(d)


# ---------------- 参数寄存器（RID）读写 ----------------
# 帧：对 CAN ID 0x7FF 发 [id_low, id_high, 0x33 读 / 0x55 写, RID, 4字节值(小端)]
RID_NAMES = {
    0: "UV_Value", 1: "KT_Value", 2: "OT_Value", 3: "OC_Value", 4: "ACC", 5: "DEC",
    6: "MAX_SPD", 7: "MST_ID", 8: "ESC_ID", 9: "TIMEOUT", 10: "CTRL_MODE",
    11: "Damp", 12: "Inertia", 16: "NPP", 17: "Rs", 18: "Ls", 19: "Flux", 20: "Gr",
    21: "PMAX", 22: "VMAX", 23: "TMAX", 35: "can_br", 36: "sub_ver",
    60: "VBus", 61: "TMOS", 62: "T_CEL",
}


def rid_is_uint32(rid):
    return (7 <= rid <= 10) or (13 <= rid <= 16) or (35 <= rid <= 36)


def decode_param(rid, raw):
    if rid_is_uint32(rid):
        return struct.unpack("<I", bytes(raw))[0]
    return struct.unpack("<f", bytes(raw))[0]


def encode_param(rid, value):
    if rid_is_uint32(rid):
        return struct.pack("<I", int(value) & 0xFFFFFFFF)
    return struct.pack("<f", float(value))


def read_param(bus, motor_id, rid, tries=8):
    lo, hi = motor_id & 0xFF, (motor_id >> 8) & 0xFF
    for _ in range(tries):
        bus.buf = bytearray()
        bus.send(0x7FF, [lo, hi, 0x33, rid, 0, 0, 0, 0])
        for _cid, cmd, d in bus.drain(0.12):
            if cmd == 0x11 and d[2] == 0x33 and d[3] == rid:
                return decode_param(rid, d[4:8])
    return None


def write_param(bus, motor_id, rid, value, tries=3):
    lo, hi = motor_id & 0xFF, (motor_id >> 8) & 0xFF
    payload = encode_param(rid, value)
    frame = [lo, hi, 0x55, rid] + list(payload)
    for _ in range(tries):
        bus.send(0x7FF, frame)
        time.sleep(0.06)
    bus.drain(0.1)
    return decode_param(rid, payload)


class Bus:
    def __init__(self, port=PORT, baud=BAUD):
        try:
            self.ser = serial.Serial(port, baud, timeout=0.05)
        except serial.SerialException as e:
            print("!! 打不开串口 %s：%s" % (port, e))
            print("   最常见原因：DMTool 还开着并占用了这个串口。")
            print("   请先在 DMTool 里点【关闭串口】，或直接关掉 DMTool，再重跑。")
            sys.exit(2)
        self.buf = bytearray()
        time.sleep(0.2)
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()

    def close(self):
        try:
            self.ser.close()
        except Exception:
            pass

    def send(self, can_id, data, n=1, interval=10):
        self.ser.write(build_tx(can_id, data, send_times=n, interval=interval))

    def drain(self, seconds=0.4):
        """读取并解析 16 字节反馈帧，返回 [(can_id, cmd, data8), ...]"""
        end = time.time() + seconds
        while time.time() < end:
            chunk = self.ser.read(512)
            if chunk:
                self.buf.extend(chunk)
        frames = []
        i = 0
        while i <= len(self.buf) - 16:
            if self.buf[i] == 0xAA and self.buf[i + 15] == 0x55:
                p = self.buf[i:i + 16]
                can_id = p[3] | (p[4] << 8) | (p[5] << 16) | (p[6] << 24)
                frames.append((can_id, p[1], bytes(p[7:15])))
                i += 16
            else:
                i += 1
        self.buf = bytearray(self.buf[i:])
        return frames


def decode_feedback(d):
    q = (d[1] << 8) | d[2]
    dq = (d[3] << 4) | (d[4] >> 4)
    tau = ((d[4] & 0xF) << 8) | d[5]
    return {
        "id": d[0] & 0x0F,
        "err": (d[0] >> 4) & 0x0F,
        "pos": u2f(q, -P_MAX, P_MAX, 16),
        "vel": u2f(dq, -V_MAX, V_MAX, 12),
        "tau": u2f(tau, -T_MAX, T_MAX, 12),
        "t_mos": d[6],
        "t_rotor": d[7],
    }


def show(frames, mst_id=0x11):
    hit = 0
    seen = []
    for can_id, cmd, d in frames:
        seen.append(hex(can_id))
        if can_id == mst_id and cmd == 0x11:
            f = decode_feedback(d)
            hit += 1
            print("  反馈 #%d  err=%d pos=%.4f rad  vel=%.3f rad/s  tau=%.3f Nm  T_mos=%d T_rotor=%d"
                  % (hit, f["err"], f["pos"], f["vel"], f["tau"], f["t_mos"], f["t_rotor"]))
    if not frames:
        print("  没收到任何帧（总线上没有应答）")
    elif hit == 0:
        print("  收到 %d 帧，但没有 0x%02X/0x11 电机反馈。出现的 ID: %s"
              % (len(frames), mst_id, ",".join(sorted(set(seen)))))
    return hit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["probe", "enable", "disable", "lock", "swing", "mit",
                                      "params", "fix", "scan"])
    ap.add_argument("--id", type=lambda s: int(s, 0), default=0x01, help="电机 CAN ID")
    ap.add_argument("--mst", type=lambda s: int(s, 0), default=0x11, help="电机反馈 ID")
    ap.add_argument("--pos", type=float, default=0.0)
    ap.add_argument("--amp", type=float, default=0.3)
    ap.add_argument("--kp", type=float, default=20.0)
    ap.add_argument("--kd", type=float, default=1.0)
    ap.add_argument("--tau", type=float, default=0.0)
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--mst-val", type=lambda s: int(s, 0), default=0x11, help="要写入的反馈 ID")
    ap.add_argument("--timeout", type=int, default=20000, help="要写入的 CAN 超时值，0=不改")
    a = ap.parse_args()

    bus = Bus()
    print("串口 %s @ %d 已打开，电机 CAN ID=0x%02X 反馈 ID=0x%02X" % (PORT, BAUD, a.id, a.mst))
    print("-" * 60)

    try:
        if a.stage == "probe":
            print("[1] 请求一帧反馈（0x7FF / 0xCC）—— 只读，不使能")
            for _ in range(3):
                bus.send(0x7FF, [a.id & 0xFF, (a.id >> 8) & 0xFF, 0xCC, 0, 0, 0, 0, 0])
                time.sleep(0.05)
            show(bus.drain(0.6), a.mst)

        elif a.stage in ("enable", "disable"):
            cmd = CMD_ENABLE if a.stage == "enable" else CMD_DISABLE
            data = [0xFF] * 7 + [cmd]
            print("[1] 发送 %s 命令 (data=FF*7+%02X)" % (a.stage.upper(), cmd))
            for _ in range(5):
                bus.send(a.id, data)
                time.sleep(0.02)
            bus.drain(0.3)
            print("[2] 复查反馈")
            bus.send(0x7FF, [a.id & 0xFF, (a.id >> 8) & 0xFF, 0xCC, 0, 0, 0, 0, 0])
            show(bus.drain(0.5), a.mst)

        elif a.stage == "lock":
            print("[1] 使能")
            for _ in range(5):
                bus.send(a.id, [0xFF] * 7 + [CMD_ENABLE])
                time.sleep(0.02)
            bus.drain(0.2)
            print("[2] 读当前位置")
            bus.send(0x7FF, [a.id & 0xFF, (a.id >> 8) & 0xFF, 0xCC, 0, 0, 0, 0, 0])
            fs = bus.drain(0.4)
            target = 0.0
            for cid, cmd, d in fs:
                if cid == a.mst and cmd == 0x11:
                    target = decode_feedback(d)["pos"]
            print("    当前位置 = %.4f rad，将以 kp=%.1f kd=%.1f 锁在这里" % (target, a.kp, a.kd))
            print("[3] 持续保持（%.1f 秒）" % (a.n * 0.02))
            for _ in range(a.n):
                bus.send(a.id, pack_mit(target, 0.0, a.kp, a.kd, 0.0))
                time.sleep(0.02)
            show(bus.drain(0.3), a.mst)

        elif a.stage == "swing":
            print("[1] 使能")
            for _ in range(5):
                bus.send(a.id, [0xFF] * 7 + [CMD_ENABLE])
                time.sleep(0.02)
            bus.drain(0.2)
            print("[2] 以 kp=%.1f kd=%.1f 低速摆动 ±%.2f rad（%.1f 秒）"
                  % (a.kp, a.kd, a.amp, a.n * 0.02))
            t0 = time.time()
            i = 0
            while i < a.n:
                ph = (time.time() - t0) * 1.0
                pos = a.amp * __import__("math").sin(2 * 3.14159 * 0.25 * ph)
                bus.send(a.id, pack_mit(pos, 0.0, a.kp, a.kd, 0.0))
                i += 1
                time.sleep(0.02)
            show(bus.drain(0.3), a.mst)

        elif a.stage == "mit":
            print("[1] 发送 MIT 帧 pos=%.3f kp=%.1f kd=%.1f tau=%.3f（%.1f 秒）"
                  % (a.pos, a.kp, a.kd, a.tau, a.n * 0.02))
            print("    提示：先发过 enable 才会动。")
            for _ in range(a.n):
                bus.send(a.id, pack_mit(a.pos, 0.0, a.kp, a.kd, a.tau))
                time.sleep(0.02)
            show(bus.drain(0.3), a.mst)

        elif a.stage == "scan":
            print("[扫描] 在 UART 上逐个 ID 发「读 MST_ID」，看谁应答")
            found = []
            for tid in range(1, 9):
                mst = read_param(bus, tid, 7, tries=4)
                esc = read_param(bus, tid, 8, tries=4) if mst is not None else None
                if mst is None:
                    print("  ID %d (0x%02X)  ->  无应答" % (tid, tid))
                else:
                    found.append(tid)
                    print("  ID %d (0x%02X)  ->  有应答：MST_ID=%s (0x%X)  ESC_ID=%s"
                          % (tid, tid, mst, mst, esc))
            print("-" * 60)
            if found:
                print("应答的电机 ID：%s" % found)
                print("用 --id %d 继续操作（改 Master ID 用 fix）" % found[0])
            else:
                print("1~8 全部静默 —— UART 上没有电机应答。")
                print("先看 DMTool 的「串口」页：断电重启时有没有打印")
                print("  DMBOT Motor Driver V4.0 / Debug Info / CAN ID ...")
                print("有打印 = 串口通、ID 不对；没打印 = 串口线/接头的问题。")

        elif a.stage == "params":
            print("[读参数] 电机 ID=0x%02X" % a.id)
            for rid in (7, 8, 9, 10, 35, 21, 22, 23, 16, 17, 18, 19, 20):
                v = read_param(bus, a.id, rid)
                if v is None:
                    print("  RID %-2d %-9s = (无应答)" % (rid, RID_NAMES.get(rid, "?")))
                elif rid in (7, 8, 9, 10, 35, 16):
                    print("  RID %-2d %-9s = %d  (0x%X)" % (rid, RID_NAMES.get(rid, "?"), v, v))
                else:
                    print("  RID %-2d %-9s = %.6g" % (rid, RID_NAMES.get(rid, "?"), v))

        elif a.stage == "fix":
            old_mst = read_param(bus, a.id, 7)
            old_esc = read_param(bus, a.id, 8)
            old_to = read_param(bus, a.id, 9)
            print("[1] 当前值：MST_ID=%s  ESC_ID=%s  TIMEOUT=%s"
                  % (old_mst, old_esc, old_to))
            if old_mst is None:
                print("!! 读不到参数。电机可能还在 Motor Mode / 参数读写只在待机态有效。")
                print("   请先断电重启电机，然后重跑（不要发 m）。")
            else:
                print("[2] 写入 MST_ID = 0x%X" % a.mst_val)
                write_param(bus, a.id, 7, a.mst_val)
                if a.timeout:
                    print("[3] 写入 TIMEOUT = %d" % a.timeout)
                    write_param(bus, a.id, 9, a.timeout)
                print("[4] 回读确认")
                time.sleep(0.2)
                print("    MST_ID  = %s" % read_param(bus, a.id, 7))
                print("    ESC_ID  = %s" % read_param(bus, a.id, 8))
                print("    TIMEOUT = %s" % read_param(bus, a.id, 9))
                print("\n    改完请断电重启一次，让新 ID 生效。")

    except KeyboardInterrupt:
        print("\n中断 —— 发失能")
        bus.send(a.id, [0xFF] * 7 + [CMD_DISABLE], n=3)
        time.sleep(0.1)
    finally:
        bus.close()
        print("-" * 60)
        print("串口已释放。结束前想彻底放松电机，可再跑一次：disable")


if __name__ == "__main__":
    main()
