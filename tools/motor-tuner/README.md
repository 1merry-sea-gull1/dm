# DM Motor Tuner

DM-MC02 六电机调试上位机第一版。

当前阶段是 **PC 端界面 + 协议层 + 模拟器**。DM-MC02 的 USB CDC 桥接固件还没有写入仓库，所以连接真实电机前必须先完成桥接固件。

## 启动软件

双击：

```text
tools/motor-tuner/run.bat
```

首次运行会：

1. 在 `.venv` 创建 Python 虚拟环境。
2. 安装 `PySide6`。
3. 启动桌面程序。

也可以手动运行：

```powershell
cd tools/motor-tuner
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python app.py
```

## 当前可用功能

- 模拟器模式，不需要硬件
- 串口/USB CDC 连接入口
- 六电机实时反馈表
- MIT、位置速度、速度控制页
- 使能、失能、设置零点
- 六路原始 CAN 帧发送
- MCU 六电机角色、总线、ID、方向、扭矩限幅编辑
- 参数保存到 `config.json`
- 通信日志

模拟器下可以先确认界面和操作流程：

1. 链路选择“模拟器”。
2. 点击“连接”。
3. 选择电机。
4. 点击“使能”。
5. 在 MIT 页设置 Kp、目标位置，勾选周期发送。
6. 观察右侧反馈表。

模拟器不会连接真实电机。

## 与真实硬件连接

真实链路：

```text
PC
 │ USB CDC 虚拟串口
DM-MC02 桥接固件
 │ FDCAN1 / FDCAN2, 1 Mbps
DM4310 电机
```

桥接固件需要实现：

- USB CDC 虚拟串口
- `protocol.py` 中的帧协议和 CRC16
- CAN1/CAN2 原始帧转发
- MCU 参数 flash 保存

在桥接固件完成前，串口模式无法控制电机。

## 协议

帧格式：

```text
magic A5 5A
version 1 byte
command 1 byte
sequence 2 bytes little-endian
payload length 2 bytes little-endian
payload <= 512 bytes
CRC16-CCITT-FALSE 2 bytes little-endian
```

CRC 覆盖 `version`、`command`、`sequence`、`length` 和 `payload`。

主要命令：

| 命令 | 值 | 说明 |
|---|---:|---|
| PING | 0x01 | 链路心跳 |
| ACK | 0x03 | 确认 |
| NACK | 0x04 | 拒绝 |
| CAN_TX | 0x10 | PC 请求发送一帧 CAN |
| CAN_RX | 0x11 | MCU 上报一帧 CAN |
| CAN_STREAM_START | 0x12 | 打开 CAN 事件流 |
| CAN_STREAM_STOP | 0x13 | 关闭 CAN 事件流 |
| MOTOR_PARAM_READ | 0x20 | 读取电机寄存器 |
| MOTOR_PARAM_WRITE | 0x21 | 写入电机寄存器 |
| MCU_CONFIG_GET | 0x30 | 读取 MCU 配置 |
| MCU_CONFIG_SET | 0x31 | 设置 MCU 配置 |
| MCU_CONFIG_SAVE | 0x32 | 保存到 Flash |
| MCU_CONFIG_RESET | 0x33 | 恢复默认配置 |

CAN 帧 payload：

```text
bus u8 | can_id u32 | flags u8 | dlc u8 | data[8] | timestamp_ms u32
```

## 下一步

1. 在 DM-balanceV1 上增加 USB CDC 和维护任务。
2. 实现 PING、CAN_TX、CAN_RX。
3. 联调模拟器与真实桥接。
4. 实现电机参数读写页面。
5. 实现 MCU 参数 Flash 保存。
6. 打包 `MotorTuner.exe`。

## 安全限制

- 真实电机模式下，电机运动前必须架空或可靠固定。
- 不要在未确认 ID、反馈 ID、方向、零点和限幅前运行平衡程序。
- PC 端定时发送只用于调试，不作为实时闭环控制器。
- 写电机 ID/MST ID 和保存零点前必须确认目标电机。
